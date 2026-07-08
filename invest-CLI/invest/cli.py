"""invest CLI 入口（Click）"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from typing import Optional

import click

from invest.__version__ import __version__
from invest.config import is_mock_mode
from invest.utils.demo import demo_index_tech, demo_macro, demo_quotes, demo_state
from invest.utils.errors import EXIT_ERROR, EXIT_NO_DATA, EXIT_OK, EXIT_SCRAPE_FAIL
from invest.utils.logger import setup_logger
from invest_core.data import fetch_all_macro, tencent_quote
from invest_core.executor import apply_signal, check_signals, load_state, save_state
from invest_core.rules import load_rules
from invest_core.signals import grade_description, score_market
from invest_core.types import Signal

logger = setup_logger()
_FORMATS = ("json", "table")


def _iso_now() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat()


def _data_source(demo: bool) -> str:
    return "demo" if demo else "live"


def _emit(payload: dict, fmt: str, output: Optional[str]) -> int:
    if fmt == "json":
        text = json.dumps(payload, ensure_ascii=False, indent=2, default=str)
    else:
        lines = [f"# {payload.get('module', 'invest')}"]
        for key, val in payload.items():
            if key in ("module", "version", "data_source", "fetched_at", "warnings"):
                continue
            lines.append(f"{key}: {val}")
        text = "\n".join(lines)

    if output:
        from pathlib import Path
        Path(output).expanduser().write_text(text, encoding="utf-8")
        click.echo(f"已写入 {output}", err=True)
    else:
        click.echo(text)

    if payload.get("data_source") == "live" and payload.get("empty"):
        return EXIT_NO_DATA
    return EXIT_OK


def _macro_detail(key: str, m: dict) -> str:
    if key == "north_money":
        return f"净流入{m.get('total', 0):+.1f}亿 趋势={m.get('trend', '')}"
    if key == "usd_cny":
        return f"USD/CNY={m.get('rate', 0):.4f}"
    if key == "erp":
        return f"ERP={m.get('erp', 0):.2f}% ({m.get('level', '')})"
    if key == "us10y":
        return f"美债10Y={m.get('rate', 0):.3f}% ({m.get('level', '')})"
    return m.get("error", "")


def _score_payload(ms, demo: bool) -> dict:
    return {
        "module": "market-score",
        "version": __version__,
        "data_source": _data_source(demo),
        "fetched_at": _iso_now(),
        "total": ms.total,
        "grade": {"value": ms.grade.value, "label": grade_description(ms.grade)},
        "recommendation": ms.recommendation,
        "confidence": ms.confidence,
        "components": [
            {"dimension": c.dimension, "score": c.score, "detail": c.detail}
            for c in ms.components
        ],
    }


def _status_payload(state, ms, demo: bool) -> dict:
    return {
        "module": "account-status",
        "version": __version__,
        "data_source": _data_source(demo),
        "fetched_at": _iso_now(),
        "account": {
            "total_asset": state.account.total_asset,
            "cash": state.account.cash,
            "market_value": state.account.market_value,
            "position_pct": state.account.position_pct,
            "positions": [
                {
                    "code": p.code, "name": p.name, "shares": p.shares,
                    "cost": p.cost, "current_price": p.current_price,
                    "market_value": p.market_value, "floating_pct": p.floating_pct,
                }
                for p in state.account.positions
            ],
        },
        "market_score": {
            "total": ms.total,
            "grade": ms.grade.value,
            "label": grade_description(ms.grade),
        },
    }


@click.group()
@click.version_option(version=__version__, prog_name="invest")
@click.option("-v", "--verbose", is_flag=True, help="DEBUG 日志")
@click.option("-q", "--quiet", is_flag=True, help="仅 WARNING 及以上")
@click.pass_context
def cli(ctx, verbose: bool, quiet: bool):
    """投资决策系统 CLI — 宏观评分、信号生成、模拟交易"""
    if quiet:
        logger.setLevel(logging.WARNING)
    elif verbose:
        logger.setLevel(logging.DEBUG)


@cli.group()
def account():
    """账户与持仓"""


@account.command("status")
@click.option("--format", "fmt", default="table", type=click.Choice(_FORMATS))
@click.option("-o", "--output", default=None, help="输出文件路径")
@click.option("--demo", is_flag=True, help="内置示例数据，不访问外网")
def account_status(fmt, output, demo):
    """账户状态 + 当前市场评分"""
    demo = is_mock_mode(demo)
    logger.info("account status demo=%s", demo)
    try:
        state = demo_state() if demo else load_state()
        if demo:
            ms = score_market(demo_macro(), demo_index_tech())
        else:
            ms = score_market()
    except Exception:
        logger.exception("账户状态获取失败")
        raise SystemExit(EXIT_SCRAPE_FAIL)

    payload = _status_payload(state, ms, demo)
    if fmt == "table":
        click.echo(f"账户概览  版本={state.version}", err=True)
        click.echo(
            f"总资产: ¥{state.account.total_asset:,.0f}  "
            f"现金: ¥{state.account.cash:,.0f}  "
            f"市值: ¥{state.account.market_value:,.0f}",
            err=True,
        )
        click.echo(
            f"持仓: {len(state.account.positions)} 只  "
            f"仓位: {state.account.position_pct:.1f}%",
            err=True,
        )
        click.echo(
            f"市场评分  {ms.total:.0f}分 / {ms.grade.value}级  "
            f"{grade_description(ms.grade)}",
            err=True,
        )
        for c in ms.components:
            sign = "+" if c.score > 0 else ""
            click.echo(f"  {c.dimension:<20} {sign}{c.score:>3}  {c.detail}", err=True)
        raise SystemExit(EXIT_OK)
    raise SystemExit(_emit(payload, fmt, output))


@cli.group()
def market():
    """市场数据与评分"""


@market.command("macro")
@click.option("--format", "fmt", default="table", type=click.Choice(_FORMATS))
@click.option("-o", "--output", default=None)
@click.option("--demo", is_flag=True, help="内置示例数据")
def market_macro(fmt, output, demo):
    """宏观数据概览"""
    demo = is_mock_mode(demo)
    logger.info("market macro demo=%s", demo)
    try:
        data = demo_macro() if demo else fetch_all_macro()
    except Exception:
        logger.exception("宏观数据获取失败")
        raise SystemExit(EXIT_SCRAPE_FAIL)

    items = []
    warnings = []
    for key in ["north_money", "usd_cny", "erp", "us10y"]:
        m = data.get("macro", {}).get(key, {})
        ok = m.get("ok", False)
        items.append({"key": key, "ok": ok, "detail": _macro_detail(key, m)})
        if not ok:
            warnings.append(f"{key}: {m.get('error', '不可用')}")

    payload = {
        "module": "market-macro",
        "version": __version__,
        "data_source": _data_source(demo),
        "fetched_at": _iso_now(),
        "count": len(items),
        "items": items,
        "warnings": warnings,
        "empty": not any(i["ok"] for i in items),
    }

    if fmt == "table":
        click.echo("宏观数据", err=True)
        for item in items:
            icon = "OK" if item["ok"] else "FAIL"
            click.echo(f"  [{icon}] {item['key']:<15} {item['detail']}", err=True)
        code = EXIT_OK if any(i["ok"] for i in items) else EXIT_NO_DATA
        raise SystemExit(code)
    raise SystemExit(_emit(payload, fmt, output))


@market.command("score")
@click.option("--format", "fmt", default="table", type=click.Choice(_FORMATS))
@click.option("-o", "--output", default=None)
@click.option("--demo", is_flag=True, help="内置示例数据")
def market_score(fmt, output, demo):
    """市场评分（三维共振）"""
    demo = is_mock_mode(demo)
    logger.info("market score demo=%s", demo)
    try:
        if demo:
            ms = score_market(demo_macro(), demo_index_tech())
        else:
            ms = score_market()
    except Exception:
        logger.exception("市场评分失败")
        raise SystemExit(EXIT_SCRAPE_FAIL)

    payload = _score_payload(ms, demo)
    if fmt == "table":
        click.echo(
            f"市场评分  {ms.total:.0f}分 / {ms.grade.value}级  "
            f"{grade_description(ms.grade)}",
            err=True,
        )
        click.echo(
            f"信号: {ms.recommendation}  置信度: {ms.confidence:.0%}",
            err=True,
        )
        for c in ms.components:
            sign = "+" if c.score > 0 else ""
            click.echo(f"  {c.dimension:<20} {sign}{c.score:>3}  {c.detail}", err=True)
        raise SystemExit(EXIT_OK)
    raise SystemExit(_emit(payload, fmt, output))


@cli.group()
def signal():
    """决策信号"""


@signal.command("list")
@click.option("--format", "fmt", default="table", type=click.Choice(_FORMATS))
@click.option("-o", "--output", default=None)
@click.option("--demo", is_flag=True, help="内置示例数据")
def signal_list(fmt, output, demo):
    """当前所有决策信号"""
    demo = is_mock_mode(demo)
    logger.info("signal list demo=%s", demo)
    try:
        state = demo_state() if demo else load_state()
        if demo:
            ms = score_market(demo_macro(), demo_index_tech())
            live_prices = {p.code: p.current_price for p in state.account.positions}
            signals = check_signals(state, ms, load_rules(), live_prices=live_prices)
        else:
            ms = score_market()
            signals = check_signals(state, ms, load_rules())
    except Exception:
        logger.exception("信号检查失败")
        raise SystemExit(EXIT_SCRAPE_FAIL)

    items = [
        {
            "action": s.action, "code": s.code, "name": s.name,
            "price": s.price, "reason": s.reason,
        }
        for s in signals
    ]
    payload = {
        "module": "signal-list",
        "version": __version__,
        "data_source": _data_source(demo),
        "fetched_at": _iso_now(),
        "count": len(items),
        "items": items,
        "empty": len(items) == 0,
    }

    if fmt == "table":
        if not signals:
            click.echo("暂无触发信号", err=True)
            raise SystemExit(EXIT_OK)
        for sig in signals:
            icon = {"buy": "BUY", "sell": "SELL", "hold": "HOLD", "warn": "WARN"}.get(
                sig.action, "???"
            )
            click.echo(f"  [{icon}] {sig.code} {sig.name}  @ ¥{sig.price}", err=True)
            click.echo(f"     原因: {sig.reason}", err=True)
        raise SystemExit(EXIT_OK)
    raise SystemExit(_emit(payload, fmt, output))


@cli.group()
def trade():
    """模拟交易（写入本地 state）"""


@trade.command("buy")
@click.argument("code")
@click.argument("shares", type=int)
@click.option("--dry-run", is_flag=True, help="只预览，不写入 state")
def trade_buy(code, shares, dry_run):
    """模拟买入"""
    logger.info("trade buy code=%s shares=%s dry_run=%s", code, shares, dry_run)
    if is_mock_mode():
        prices = demo_quotes()
    else:
        try:
            prices = tencent_quote([code])
        except Exception:
            logger.exception("行情获取失败")
            raise SystemExit(EXIT_SCRAPE_FAIL)

    price_data = prices.get(code, {}) or prices.get(code.zfill(6), {})
    price = price_data.get("price", 0)
    if price == 0:
        click.echo(f"无法获取 {code} 行情", err=True)
        raise SystemExit(EXIT_SCRAPE_FAIL)

    if dry_run:
        click.echo(f"[dry-run] 模拟买入 {code} x {shares} @ ¥{price}", err=True)
        raise SystemExit(EXIT_OK)

    state = load_state()
    sig = Signal(
        action="buy", code=code, name=code,
        price=price, shares=shares,
        reason="manual", confidence=1.0,
    )
    state = apply_signal(state, sig)
    save_state(state)
    click.echo(f"模拟买入 {code} x {shares} @ ¥{price}", err=True)
    raise SystemExit(EXIT_OK)


@trade.command("sell")
@click.argument("code")
@click.argument("shares", type=int)
@click.option("--reason", default="manual", help="卖出原因")
@click.option("--dry-run", is_flag=True, help="只预览，不写入 state")
def trade_sell(code, shares, reason, dry_run):
    """模拟卖出"""
    logger.info("trade sell code=%s shares=%s dry_run=%s", code, shares, dry_run)
    if is_mock_mode():
        prices = demo_quotes()
    else:
        try:
            prices = tencent_quote([code])
        except Exception:
            logger.exception("行情获取失败")
            raise SystemExit(EXIT_SCRAPE_FAIL)

    price_data = prices.get(code, {}) or prices.get(code.zfill(6), {})
    price = price_data.get("price", 0)
    if dry_run:
        click.echo(f"[dry-run] 模拟卖出 {code} x {shares} @ ¥{price}", err=True)
        raise SystemExit(EXIT_OK)

    state = load_state()
    sig = Signal(
        action="sell", code=code, name=code,
        price=price, shares=shares,
        reason=reason, confidence=1.0,
    )
    state = apply_signal(state, sig)
    save_state(state)
    click.echo(f"模拟卖出 {code} x {shares} @ ¥{price}", err=True)
    raise SystemExit(EXIT_OK)


def main() -> int:
    try:
        cli(standalone_mode=False)
        return EXIT_OK
    except SystemExit as e:
        code = e.code
        if code is None:
            return EXIT_OK
        if isinstance(code, int):
            return code
        return EXIT_ERROR
    except click.ClickException:
        return EXIT_ERROR
    except Exception:
        logger.exception("未捕获异常")
        return EXIT_ERROR


if __name__ == "__main__":
    sys.exit(main())
