from typing import Optional
"""
invest_core.executor.trader
==========================
交易执行层。

基于决策信号执行交易：
  - 读取 InvestState（持仓/账户）
  - 调用 signals.position.score_position 检查止盈/止损
  - 生成 Signal 列表（买/卖/减仓/观望）
  - 应用交易，更新 InvestState
  - 可选：同步到 Bitable

设计原则：
  - 不直接写 Bitable，由 broker.py 负责
  - 返回 Signal 列表供调用方决定如何通知/记录
  - 所有交易操作幂等
"""

from datetime import date, datetime
from invest_core.types import (
    InvestState, Position, Signal, Trade,
    RuleSet, MarketScore,
)
from invest_core.signals import position as pos_signal
from invest_core.data import market
from invest_core.executor import state


# ─── 止盈档位常量 ──────────────────────────────────────────────────────────

TP_THRESHOLDS = {
    5: 60.0,   # 减60%
    4: 40.0,   # RSI>80 减40%
    3: 25.0,   # 跟踪止损
    2: 15.0,   # 成本保护
    1: 8.0,    # 减1/3
}

STOP_LOSS_WARN   = -3.0
STOP_LOSS_FORCE  = -5.0
STOP_LOSS_CLEAR  = -8.0
STOP_LOSS_DEEP   = -15.0
MIN_HOLD_DAYS    = 10


# ─── 主检查函数 ────────────────────────────────────────────────────────────

def check_signals(
    state_invest: InvestState,
    market_score: MarketScore,
    rules: RuleSet,
    live_prices: dict = None,
) -> list[Signal]:
    """
    检查所有持仓的触发条件，返回需要执行的 Signal 列表。

    Args:
        state_invest: 当前状态
        market_score: 当前市场评分
        rules: 规则集
        live_prices: 可选，实时价格 dict[code, price]，不传则实时拉取

    Returns:
        list[Signal]：需要执行的操作（可能为空）
    """
    signals: list[Signal] = []
    positions = state_invest.account.positions

    # ── 批量获取实时价格 ──────────────────────────────────
    if live_prices is None:
        codes = [p.code for p in positions]
        if codes:
            quotes = market.tencent_quote(codes)
            live_prices = {code: quotes.get(code, {}).get("price", 0.0) for code in codes}

    # ── 逐个持仓检查 ─────────────────────────────────────
    for pos in positions:
        current_price = live_prices.get(pos.code, pos.current_price) if live_prices else pos.current_price
        pos.current_price = current_price
        pos.calc_pnl()

        sig = _check_position(pos, market_score, rules, live_prices)
        if sig and sig.action != "hold":
            signals.append(sig)

    # ── 买入信号检查 ────────────────────────────────────
    buy_signals = _check_buy_signals(state_invest, market_score, rules, live_prices)
    signals.extend(buy_signals)

    return signals


def _check_position(
    pos: Position,
    market_score: MarketScore,
    rules: RuleSet,
    live_prices: dict[str, float],
) -> Optional[Signal]:
    """检查单只持仓的触发信号"""
    code = pos.code
    pnl_pct = pos.floating_pct
    current_price = live_prices.get(code, pos.current_price) if live_prices else pos.current_price
    entry_price = pos.cost
    hold_days = pos.position_days

    # ── 止损检查 ────────────────────────────────────────
    if pnl_pct <= STOP_LOSS_DEEP:
        return Signal(
            action="sell", code=code, name=pos.name,
            reason=f"强制清仓（浮亏{pnl_pct:.1f}% ≤ -15%）",
            triggered_rule="R2-deep", price=current_price,
            shares=pos.shares, confidence=0.95,
        )

    if pnl_pct <= STOP_LOSS_FORCE:
        return Signal(
            action="sell", code=code, name=pos.name,
            reason=f"止损（浮亏{pnl_pct:.1f}% ≤ -5%）",
            triggered_rule="R2-force", price=current_price,
            shares=pos.shares, confidence=0.95,
        )

    if pnl_pct <= STOP_LOSS_CLEAR:
        return Signal(
            action="sell", code=code, name=pos.name,
            reason=f"完全清仓（浮亏{pnl_pct:.1f}% ≤ -8%）",
            triggered_rule="R2-clear", price=current_price,
            shares=pos.shares, confidence=0.95,
        )

    if pnl_pct <= STOP_LOSS_WARN:
        return Signal(
            action="warn", code=code, name=pos.name,
            reason=f"R2预警（浮亏{pnl_pct:.1f}%）",
            triggered_rule="R2-warn", price=current_price,
            confidence=0.8,
        )

    # ── R1：持仓<10天，不主动卖 ────────────────────────
    if hold_days < MIN_HOLD_DAYS:
        return None  # 不产生信号

    # ── 止盈检查（v2.2 档位阶梯）───────────────────────
    tp_sig = _check_take_profit(pos, current_price)
    if tp_sig:
        return tp_sig

    return None


def _check_take_profit(pos: Position, current_price: float) -> Optional[Signal]:
    """
    检查止盈档位（v2.2）。
    单向阶梯：只触发当前未触发的最高档。
    """
    pnl_pct = pos.floating_pct
    code = pos.code
    entry_price = pos.cost
    name = pos.name

    triggered_raw = pos.triggered_take_profit or ""
    triggered: set[str] = set(triggered_raw.split(";")) if triggered_raw else set()

    # ── Level 5: +60% ─────────────────────────────────
    if pnl_pct >= TP_THRESHOLDS[5] and "5" not in triggered:
        shares = int(pos.shares * 0.6)
        return Signal(
            action="sell", code=code, name=name,
            reason=f"R5-5：+{pnl_pct:.1f}% ≥ +60%，减60%",
            triggered_rule="R5-tp5", price=current_price,
            shares=shares, confidence=0.9,
        )

    # ── Level 4: +40% RSI>80 减40% ───────────────────
    if pnl_pct >= TP_THRESHOLDS[4] and "4" not in triggered:
        tech = market.fetch_stock_tech(code)
        rsi = tech.get("rsi14", 50) if tech.get("ok") else 50
        if rsi > 80:
            shares = int(pos.shares * 0.4)
            return Signal(
                action="sell", code=code, name=name,
                reason=f"R5-4：+{pnl_pct:.1f}% ≥ +40%，RSI={rsi}>80，减40%",
                triggered_rule="R5-tp4-rsi", price=current_price,
                shares=shares, confidence=0.85,
            )
        else:
            # 趋势延续，继续持有
            triggered.add("4")
            pos.triggered_take_profit = ";".join(sorted(triggered))

    # ── Level 3: +25% 跟踪止损 ─────────────────────────
    if pnl_pct >= TP_THRESHOLDS[3] and "3" not in triggered:
        tech = market.fetch_stock_tech(code)
        atr = tech.get("atr14", 0) if tech.get("ok") else 0
        if atr > 0:
            trailing_stop = round(current_price - 2 * atr, 2)
        else:
            trailing_stop = round(current_price * 0.92, 2)
        triggered.add("3")
        triggered.add(f"ts:{trailing_stop}")
        pos.triggered_take_profit = ";".join(sorted(triggered))
        # 不立即触发卖出，只记录状态

    # ── Level 2: +15% 成本保护 ────────────────────────
    if pnl_pct >= TP_THRESHOLDS[2] and "2" not in triggered:
        cost_protect = round(entry_price * 1.02, 2)
        triggered.add("2")
        triggered.add(f"cp:{cost_protect}")
        pos.triggered_take_profit = ";".join(sorted(triggered))

    # ── Level 1: +8% 减1/3 ────────────────────────────
    if pnl_pct >= TP_THRESHOLDS[1] and "1" not in triggered:
        shares = int(pos.shares / 3)
        return Signal(
            action="sell", code=code, name=name,
            reason=f"R5-1：+{pnl_pct:.1f}% ≥ +8%，减1/3",
            triggered_rule="R5-tp1", price=current_price,
            shares=shares, confidence=0.8,
        )

    # ── 跟踪止损触发检查 ────────────────────────────────
    for t in list(triggered):
        if t.startswith("ts:"):
            ts_price = float(t.split(":")[1])
            if current_price < ts_price:
                shares = int(pos.shares * 0.5)
                return Signal(
                    action="sell", code=code, name=name,
                    reason=f"跟踪止损触发（现价={current_price}<止损={ts_price}，减50%）",
                    triggered_rule="R5-ts", price=current_price,
                    shares=shares, confidence=0.9,
                )

    # ── 成本保护触发检查 ────────────────────────────────
    for t in list(triggered):
        if t.startswith("cp:"):
            cp_price = float(t.split(":")[1])
            if current_price < cp_price:
                return Signal(
                    action="sell", code=code, name=name,
                    reason=f"成本保护触发（现价={current_price}<保护={cp_price}，清仓）",
                    triggered_rule="R5-cp", price=current_price,
                    shares=pos.shares, confidence=0.95,
                )

    return None


def _check_buy_signals(
    state_invest: InvestState,
    market_score: MarketScore,
    rules: RuleSet,
    live_prices: dict = None,
) -> list[Signal]:
    """
    检查买入信号（建仓/补仓）。
    包括：
      - 市场评分达到要求时，根据 watchlist 建仓
      - C级市场仓位低于下限时的强制补仓
    """
    signals: list[Signal] = []
    grade = market_score.grade.value
    score = market_score.total

    # 仓位下限
    min_pos = rules.position_limits.min_position_by_grade.get(grade, 0.3)
    max_pos = rules.position_limits.max_position_by_grade.get(grade, 0.6)

    current_pos_pct = state_invest.account.position_pct / 100.0  # 转为小数
    total_asset = state_invest.account.total_asset
    cash = state_invest.account.cash

    if current_pos_pct < min_pos:
        # C级以下市场仓位不足，需要补仓
        # 简化：从持仓中最看好的标的补仓（此处可接入 watchlist）
        # 暂时不自动买入，只产生预警信号
        shortage = (min_pos - current_pos_pct) * total_asset
        signals.append(Signal(
            action="buy", code="", name="补仓提醒",
            reason=f"仓位{current_pos_pct*100:.1f}% < 下限{min_pos*100:.0f}%（{grade}级），缺口¥{shortage:.0f}",
            triggered_rule="C2-min-position", price=0,
            confidence=0.7,
        ))

    # 市场做多信号，买入 watchlist 标的
    if score >= 60 and grade in ("A", "B"):
        # 从 signal_history 中找最近的 buy 信号标的作为 watchlist 替代
        # 实际应该从外部 watchlist 传入，此处做占位
        pass

    return signals


# ─── 信号应用到状态 ─────────────────────────────────────────────────────────

def apply_signal(
    state_invest: InvestState,
    signal: Signal,
) -> InvestState:
    """
    将 Signal 应用到 InvestState（模拟执行，不写 Bitable）。

    Args:
        state_invest: 当前状态
        signal: 要执行的信号

    Returns:
        更新后的 InvestState（内存）
    """
    now = datetime.now()
    code = signal.code
    price = signal.price
    shares = signal.shares

    if signal.action == "sell":
        pos = state.get_position(state_invest, code)
        if not pos:
            return state_invest

        sell_shares = min(shares or pos.shares, pos.shares)
        amount = round(sell_shares * price, 2)

        # 记交易
        trade = Trade(
            id=f"{now.strftime('%Y%m%d%H%M%S')}_{code}",
            date=date.today(),
            action="sell",
            code=code,
            name=pos.name,
            price=price,
            shares=sell_shares,
            amount=amount,
            reason=signal.reason or signal.triggered_rule,
            signal_type=signal.triggered_rule or "manual",
        )
        state_invest = state.add_trade(state_invest, trade)

        # 更新持仓
        if sell_shares >= pos.shares:
            state_invest = state.remove_position(state_invest, code)
        else:
            pos.shares -= sell_shares
            pos.calc_pnl()

        # 更新现金
        state_invest.account.cash += amount

    elif signal.action == "buy" and code:
        amount = round(shares * price, 2)
        if amount > state_invest.account.cash:
            # 现金不足，跳过
            return state_invest

        pos = Position(
            code=code,
            name=signal.name or code,
            shares=shares,
            cost=price,
            current_price=price,
            entry_date=date.today(),
            position_days=0,
        )
        pos.calc_pnl()
        state_invest = state.add_position(state_invest, pos)
        state_invest.account.cash -= amount

    state_invest = state.add_signal(state_invest, signal)
    return state_invest
