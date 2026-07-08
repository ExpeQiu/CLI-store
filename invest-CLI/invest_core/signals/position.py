"""
invest_core.signals.position
===========================
个股持仓评分引擎。

基于 invest_rules.md v2.3 规则，对持仓标的进行：
  - R1：持仓<10天短线禁止检查
  - R2：止损线检查（-3%预警/-5%强平/-8%清仓/-15%深套）
  - R4：60天跑输大盘复审
  - R5：止盈阶梯检查（v2.2）
  - C1/C2：仓位限制检查
  - 个股技术面（RSI/MA/ATR/量比）

输出 Signal 对象供 executor/trader.py 使用。
"""

from datetime import datetime, date
from typing import Optional
from invest_core.types import (
    Position, Signal, MarketScore, MarketGrade,
    TakeProfitRule, RuleSet,
)
from invest_core.data import market


def score_position(
    position: Position,
    market_score: MarketScore,
    rules: RuleSet,
) -> Signal:
    """
    对单只持仓计算决策信号。

    Args:
        position: 持仓对象
        market_score: 当前市场评分
        rules: 规则集

    Returns:
        Signal 对象：action / reason / triggered_rule / confidence
    """
    code = position.code
    name = position.name
    entry_price = position.cost
    current_price = position.current_price
    hold_days = position.position_days
    pnl_pct = position.floating_pct

    signal = Signal(code=code, name=name, price=current_price)
    reasons: list[str] = []

    # ── R1：持仓<10天，禁止主动卖出 ────────────────────────
    if hold_days < rules.market_phase.min_hold_days:
        reasons.append(f"R1：持仓{hold_days}天（<{rules.market_phase.min_hold_days}天，禁止主动卖出）")
        # 止损例外
        if pnl_pct <= rules.market_phase.stop_loss_force:
            signal.action = "sell"
            signal.reason = f"止损触发（{pnl_pct:.1f}%）"
            signal.triggered_rule = "R2"
            return signal
        signal.action = "hold"
        signal.reason = "；".join(reasons)
        signal.confidence = 0.9
        return signal

    # ── R2：止损线检查 ───────────────────────────────────
    for sl in rules.stop_loss_rules:
        if pnl_pct <= sl.pct:
            if sl.action == "warn":
                signal.action = "warn"
                signal.triggered_rule = f"R2-warn"
                reasons.append(f"R2：{sl.description}（{pnl_pct:.1f}%）")
            elif sl.action == "force_sell":
                signal.action = "sell"
                signal.triggered_rule = "R2-force"
                signal.reason = f"R2：{sl.description}（{pnl_pct:.1f}%）"
                return signal
            elif sl.action == "clear":
                signal.action = "sell"
                signal.triggered_rule = "R2-clear"
                signal.reason = f"R2：{sl.description}（{pnl_pct:.1f}%）"
                return signal
            elif sl.action == "deep_hold":
                signal.action = "hold"
                signal.triggered_rule = "R2-deep"
                reasons.append(f"R2：{sl.description}（{pnl_pct:.1f}%）")
            break

    # ── R5：止盈检查（v2.2，从高到低检查）─────────────────
    triggered_tp = position.triggered_take_profit or ""
    already_triggered = set(triggered_tp.split(";")) if triggered_tp else set()

    for tp_rule in sorted(rules.take_profit_rules, key=lambda r: r.level, reverse=True):
        level_key = str(tp_rule.level)
        if level_key in already_triggered:
            # 该档位已触发，检查跟踪止损/成本保护是否仍有效
            if tp_rule.action == "trailing_stop" and tp_rule.level == 3:
                # 跟踪止损：最近N日高点 - 2×ATR
                tech = market.fetch_stock_tech(code)
                if tech.get("ok"):
                    atr = tech.get("atr14", 0)
                    # 简化：用当前价与 entry_price × 1.02 比较（成本保护）
                    cost_protection = entry_price * 1.02
                    if current_price < cost_protection:
                        # 触发成本保护，强制止盈
                        signal.action = "sell"
                        signal.triggered_rule = "R5-tp3-cost-protection"
                        signal.reason = f"R5-3：跟踪止损触发，成本保护{current_price}<{cost_protection:.2f}"
                        return signal
                # 继续持有
                reasons.append(f"R5-3：跟踪止损中（未触发成本保护）")
            continue

        # 触发新档位
        if pnl_pct >= tp_rule.threshold:
            if tp_rule.action == "reduce_60pct":
                signal.action = "reduce"
                signal.triggered_rule = "R5-tp5"
                signal.reason = f"R5-5：+{pnl_pct:.1f}%≥{tp_rule.threshold}%，减60%"
                signal.shares = int(position.shares * 0.6)
                return signal
            elif tp_rule.action == "rsi_condition":
                # 需要 RSI 条件
                tech = market.fetch_stock_tech(code)
                rsi = tech.get("rsi14", 50) if tech.get("ok") else 50
                if rsi > 80:
                    signal.action = "reduce"
                    signal.triggered_rule = "R5-tp4-rsi"
                    signal.reason = f"R5-4：+{pnl_pct:.1f}%≥{tp_rule.threshold}%，RSI={rsi}>80，减40%"
                    signal.shares = int(position.shares * 0.4)
                else:
                    reasons.append(f"R5-4：+{pnl_pct:.1f}%≥{tp_rule.threshold}%，RSI={rsi}≤80，继续持有")
                # 不return，继续检查是否有更高档位
            elif tp_rule.action == "trailing_stop":
                reasons.append(f"R5-3：+{pnl_pct:.1f}%≥{tp_rule.threshold}%，启用跟踪止损")
                # 跟踪止损状态不立即触发卖出，记录即可
            elif tp_rule.action == "cost_protection":
                reasons.append(f"R5-2：+{pnl_pct:.1f}%≥{tp_rule.threshold}%，启用成本保护（{entry_price*1.02:.2f}）")
            elif tp_rule.action == "reduce_1_3":
                signal.action = "reduce"
                signal.triggered_rule = "R5-tp1"
                signal.reason = f"R5-1：+{pnl_pct:.1f}%≥{tp_rule.threshold}%，减1/3"
                signal.shares = int(position.shares / 3)
                return signal

    # ── R4：60天跑输大盘检查 ─────────────────────────────
    if hold_days > 60 and pnl_pct < -10:
        signal.action = "reduce"
        signal.triggered_rule = "R4"
        signal.reason = f"R4：持仓{hold_days}天亏损{pnl_pct:.1f}%，减仓50%"
        signal.shares = int(position.shares * 0.5)
        return signal

    # ── 最终持仓判断 ─────────────────────────────────────
    if signal.action in ("sell", "reduce"):
        pass  # 已在上面处理
    else:
        # 综合市场评分 + 个股技术面
        if market_score.grade in (MarketGrade.A, MarketGrade.B):
            signal.action = "hold"
            signal.reason = f"市场{MarketScore.grade.value}级，顺势持有"
            signal.confidence = 0.7
        elif market_score.grade == MarketGrade.C:
            # C级：已有持仓不强制卖出，但也不加仓
            signal.action = "hold"
            signal.reason = "市场C级，谨慎持有"
            signal.confidence = 0.6
        else:
            signal.action = "hold"
            signal.reason = f"市场{MarketScore.grade.value}级，关注止损"
            signal.confidence = 0.5

    signal.reason = "；".join(filter(None, [signal.reason] + reasons))
    if not signal.reason:
        signal.reason = f"浮盈{pnl_pct:.1f}%，持仓{hold_days}天，继续持有"
    return signal


def check_buy_signal(
    code: str,
    market_score: MarketScore,
    rules: RuleSet,
    stock_tech: dict = None,
) -> Signal:
    """
    检查是否可以买入某标的（建仓信号）。

    Args:
        code: 股票代码
        market_score: 当前市场评分
        rules: 规则集
        stock_tech: 可选，个股技术指标（不传则实时拉取）

    Returns:
        Signal：action=buy 且 reason 包含建仓条件
    """
    if stock_tech is None:
        stock_tech = market.fetch_stock_tech(code)

    signal = Signal(code=code, name=stock_tech.get("name", code))

    # B1：三维共振至少2维做多
    dims_positive = sum([
        1 if market_score.macro >= 0 else 0,
        1 if market_score.structure >= 0 else 0,
        1 if market_score.tech >= 0 else 0,
    ])
    if dims_positive < 2:
        signal.action = "avoid"
        signal.reason = f"B1：三维仅{dims_positive}维做多，禁止建仓"
        signal.confidence = 0.9
        return signal

    # B2：RSI 30~65（不追高，不接刀）
    rsi = stock_tech.get("rsi14", 50)
    if rsi > 70:
        signal.action = "avoid"
        signal.reason = f"B2：RSI={rsi}>70（追高），禁止建仓"
        signal.confidence = 0.9
        return signal
    if rsi < 25:
        signal.action = "watch"
        signal.reason = f"B2：RSI={rsi}<25（超卖），等待企稳"
        signal.confidence = 0.6
        return signal
    if rsi < 30 or rsi > 65:
        signal.action = "watch"
        signal.reason = f"B2：RSI={rsi}（偏界），等待更优位置"
        signal.confidence = 0.5
        return signal

    # B3：价格在20日均线上方
    price = stock_tech.get("price", 0)
    ma20 = stock_tech.get("ma20", 0)
    if ma20 > 0 and price < ma20:
        signal.action = "avoid"
        signal.reason = f"B3：价格{price}<MA20{ma20}，禁止逆势建仓"
        signal.confidence = 0.8
        return signal

    # C级市场禁止新建仓
    if market_score.grade == MarketGrade.C:
        signal.action = "avoid"
        signal.reason = f"C级市场禁止新建仓（评分={market_score.total}）"
        signal.confidence = 0.9
        return signal
    if market_score.grade in (MarketGrade.D, MarketGrade.E):
        signal.action = "avoid"
        signal.reason = f"{market_score.grade}级市场空头，禁止建仓"
        signal.confidence = 0.9
        return signal

    # 通过全部检查
    signal.action = "buy"
    signal.reason = (
        f"建仓信号：B1({dims_positive}维↑)B2(RSI={rsi})B3(MA20↑)"
        f"市场{MarketScore.grade.value}级（{market_score.total}分）"
    )
    signal.confidence = 0.75
    return signal
