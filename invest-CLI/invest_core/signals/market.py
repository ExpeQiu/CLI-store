from typing import Optional
"""
invest_core.signals.market
==========================
三维共振市场评分引擎。

从 invest_core.data 获取原始指标，
按 invest_rules.md v2.3 的评分规则计算市场综合评分，
输出 MarketScore 结构化对象。
"""

from datetime import datetime
from invest_core.types import MarketScore, MarketGrade, MarketDirection, SignalComponent
from invest_core.data import macro, market


def score_market(macro_data: dict = None, tech_data: dict = None) -> MarketScore:
    """
    计算三维共振市场评分。

    Args:
        macro_data: 宏观数据结构（来自 fetch_all_macro），不传则实时拉取。
        tech_data: 指数技术指标（来自 fetch_all_index_tech），不传则实时拉取。

    Returns:
        MarketScore 对象（所有字段填充）。
    """
    if macro_data is None:
        macro_data = macro.fetch_all_macro()
    if tech_data is None:
        tech_data = market.fetch_all_index_tech()
    index_sh = tech_data.get("sh000001", {})  # 上证指数

    score = 50
    components: list[SignalComponent] = []

    # ── 宏观层 ────────────────────────────────────────────
    macro_layer = 0

    # 北向资金（±10）
    nm = macro_data.get("macro", {}).get("north_money", {})
    if nm.get("ok"):
        total = nm.get("total", 0)
        s = 10 if total > 50 else 5 if total > 10 else -10 if total < -50 else -5 if total < -10 else 0
        macro_layer += s
        components.append(SignalComponent(
            dimension="north_money", score=s,
            detail=f"净流入{total:.1f}亿" if total >= 0 else f"净流出{abs(total):.1f}亿"
        ))
    else:
        components.append(SignalComponent(dimension="north_money", score=0, detail="数据不可用"))

    # USD/CNY 汇率（±5）
    fx = macro_data.get("macro", {}).get("usd_cny", {})
    if fx.get("ok"):
        rate = fx.get("rate", 7.0)
        s = -5 if rate > 7.3 else -2 if rate > 7.1 else 5 if rate < 7.0 else 2 if rate < 7.1 else 0
        macro_layer += s
        components.append(SignalComponent(dimension="exchange_rate", score=s, detail=f"USD/CNY={rate:.4f}"))
    else:
        components.append(SignalComponent(dimension="exchange_rate", score=0, detail="数据不可用"))

    # ERP（±10）
    erp_data = macro_data.get("macro", {}).get("erp", {})
    if erp_data.get("ok"):
        s = erp_data.get("score", 0)
        macro_layer += s
        components.append(SignalComponent(
            dimension="erp", score=s,
            detail=f"ERP={erp_data['erp']:.2f}%（{erp_data.get('level', '')}）"
        ))
    else:
        components.append(SignalComponent(dimension="erp", score=0, detail="数据不可用"))

    # 美债10Y（±10）
    us10y_data = macro_data.get("macro", {}).get("us10y", {})
    if us10y_data.get("ok"):
        s = us10y_data.get("score", 0)
        macro_layer += s
        components.append(SignalComponent(
            dimension="us10y", score=s,
            detail=f"美债10Y={us10y_data['rate']:.3f}%（{us10y_data.get('level', '')}）"
        ))
    else:
        components.append(SignalComponent(dimension="us10y", score=0, detail="数据不可用"))

    # ── 结构层 ────────────────────────────────────────────
    structure_layer = 0

    # 行业涨跌比（±10）
    ir = macro_data.get("structure", {}).get("industry_ratio", {})
    if ir.get("ok"):
        s = ir.get("score", 0)
        structure_layer += s
        components.append(SignalComponent(
            dimension="industry_ratio", score=s,
            detail=f"{ir.get('ratio', 0)}%行业上涨（涨{ir.get('rising', 0)}跌{ir.get('falling', 0)}）"
        ))
    else:
        components.append(SignalComponent(dimension="industry_ratio", score=0, detail="数据不可用"))

    # 全A换手率（±8）
    tr = macro_data.get("structure", {}).get("turnover_rate", {})
    if tr.get("ok"):
        s = tr.get("score", 0)
        structure_layer += s
        components.append(SignalComponent(
            dimension="turnover_rate", score=s,
            detail=f"换手率{tr.get('turnover_rate', 0):.3f}%（{tr.get('level', '')}）"
        ))
    else:
        components.append(SignalComponent(dimension="turnover_rate", score=0, detail="数据不可用"))

    # ── 技术层 ────────────────────────────────────────────
    tech_layer = 0

    # RSI（±15）
    if index_sh.get("ok"):
        rsi = index_sh.get("rsi14", 50)
        if rsi > 80:      s = -15
        elif rsi > 70:    s = -8
        elif rsi < 20:    s = 15
        elif rsi < 30:    s = 8
        elif rsi < 45:    s = -3
        else:             s = 0
        tech_layer += s
        components.append(SignalComponent(dimension="rsi", score=s, detail=f"RSI(14)={rsi:.1f}"))
    else:
        components.append(SignalComponent(dimension="rsi", score=0, detail="数据不可用"))

    # 均线方向（±10）
    if index_sh.get("ok"):
        ma5_dir = index_sh.get("ma5_dir", 0)
        ma20_dir = index_sh.get("ma20_dir", 0)
        s = 0
        if ma5_dir == 1:  s += 3
        elif ma5_dir == -1: s -= 2
        if ma20_dir == 1:  s += 4
        elif ma20_dir == -1: s -= 2
        if s > 0 and ma5_dir == 1 and ma20_dir == 1: s += 3  # 多头排列额外奖励
        tech_layer += s
        components.append(SignalComponent(
            dimension="ma_direction", score=s,
            detail=f"MA5={'↑' if ma5_dir==1 else '↓' if ma5_dir==-1 else '→'} MA20={'↑' if ma20_dir==1 else '↓' if ma20_dir==-1 else '→'}"
        ))
    else:
        components.append(SignalComponent(dimension="ma_direction", score=0, detail="数据不可用"))

    # 上证涨跌幅（±5）
    if index_sh.get("ok"):
        chg = index_sh.get("change_pct", 0)
        if chg > 2:       s = 5
        elif chg > 0.5:   s = 2
        elif chg < -2:    s = -5
        elif chg < -0.5:  s = -2
        else:             s = 0
        tech_layer += s
        components.append(SignalComponent(dimension="index_change", score=s, detail=f"上证{chg:+.2f}%"))
    else:
        components.append(SignalComponent(dimension="index_change", score=0, detail="数据不可用"))

    # ── 综合 ──────────────────────────────────────────────
    total = max(0, min(100, score + macro_layer + structure_layer + tech_layer))
    grade = MarketScore.grade_from_score(total)
    direction = MarketScore.direction_from_grade(grade)

    if grade == MarketGrade.A:   rec, conf = "buy", 0.7
    elif grade == MarketGrade.B: rec, conf = "hold", 0.6
    elif grade == MarketGrade.C: rec, conf = "hold", 0.5
    elif grade == MarketGrade.D: rec, conf = "sell", 0.6
    else:                        rec, conf = "sell", 0.8

    return MarketScore(
        total=total, grade=grade, direction=direction,
        macro=macro_layer, structure=structure_layer, tech=tech_layer,
        north_money_score=next((c.score for c in components if c.dimension == "north_money"), 0),
        exchange_rate_score=next((c.score for c in components if c.dimension == "exchange_rate"), 0),
        erp_score=next((c.score for c in components if c.dimension == "erp"), 0),
        us10y_score=next((c.score for c in components if c.dimension == "us10y"), 0),
        industry_ratio_score=next((c.score for c in components if c.dimension == "industry_ratio"), 0),
        turnover_score=next((c.score for c in components if c.dimension == "turnover_rate"), 0),
        rsi_score=next((c.score for c in components if c.dimension == "rsi"), 0),
        ma_score=next((c.score for c in components if c.dimension == "ma_direction"), 0),
        index_change_score=next((c.score for c in components if c.dimension == "index_change"), 0),
        components=components,
        recommendation=rec, confidence=conf,
        updated_at=datetime.now(),
    )


def grade_description(grade: MarketGrade) -> str:
    return {
        MarketGrade.A: "三维共振做多信号，积极参与",
        MarketGrade.B: "两维共振，持有为主，谨慎加仓",
        MarketGrade.C: "一维共振，轻仓参与，禁止新建仓",
        MarketGrade.D: "空头共振，持有/减仓，不新建仓",
        MarketGrade.E: "强空信号，清仓离场，等待底部",
    }[grade]
