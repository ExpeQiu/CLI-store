"""--demo 内置示例数据，供 verify.sh 离线验收"""

from __future__ import annotations

from datetime import datetime

from invest_core.types import AccountOverview, InvestState, Position


def _now() -> str:
    return datetime.now().isoformat()


def demo_macro() -> dict:
    ts = _now()
    return {
        "generated_at": ts,
        "macro": {
            "north_money": {
                "source": "north_money", "ok": True, "total": 35.2,
                "trend": "流入", "score": 5, "timestamp": ts,
            },
            "usd_cny": {
                "source": "usd_cny", "ok": True, "rate": 7.05,
                "score": 2, "timestamp": ts,
            },
            "erp": {
                "source": "erp", "ok": True, "erp": 4.5, "level": "合理",
                "score": 5, "timestamp": ts,
            },
            "us10y": {
                "source": "us10y", "ok": True, "rate": 4.2, "level": "中性",
                "score": 0, "timestamp": ts,
            },
        },
        "structure": {
            "industry_ratio": {
                "source": "industry_ratio", "ok": True, "ratio": 55,
                "rising": 22, "falling": 18, "score": 5, "timestamp": ts,
            },
            "turnover_rate": {
                "source": "turnover_rate", "ok": True, "turnover_rate": 1.2,
                "level": "正常", "score": 0, "timestamp": ts,
            },
        },
    }


def demo_index_tech() -> dict:
    ts = _now()
    base = {
        "ok": True, "price": 3200.5, "change_pct": 0.8,
        "rsi14": 55.0, "ma5_dir": 1, "ma20_dir": 1, "updated_at": ts,
    }
    return {
        "sh000001": {**base, "symbol": "sh000001", "name": "上证指数"},
        "sz399001": {**base, "symbol": "sz399001", "name": "深证成指", "price": 10500.0},
        "sz399006": {**base, "symbol": "sz399006", "name": "创业板指", "price": 2100.0},
    }


def demo_state() -> InvestState:
    return InvestState(
        version="2.3.0",
        account=AccountOverview(
            total_asset=500_000.0,
            cash=200_000.0,
            market_value=300_000.0,
            position_pct=60.0,
            positions=[
                Position(
                    code="600519", name="贵州茅台", shares=100,
                    cost=1680.0, current_price=1720.0,
                    market_value=172_000.0, floating_pct=2.38,
                ),
            ],
        ),
    )


def demo_quotes() -> dict:
    return {
        "600519": {"price": 1720.0, "name": "贵州茅台"},
        "000001": {"price": 12.5, "name": "平安银行"},
    }
