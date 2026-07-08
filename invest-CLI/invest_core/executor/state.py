from typing import Optional
"""
invest_core.executor.state
=========================
统一状态管理层。

核心原则：invest_state.json 是唯一数据源。
Bitable/CSV 是可选的持久化适配器。

InvestState 包含：
  - account: 账户概览
  - market_score: 当前市场评分
  - macro: 宏观指标
  - positions: 持仓列表
  - trades: 交易记录
  - signal_history: 信号历史
  - cooling_stocks: 标的冷却期
  - entry_count: 每只标的建仓次数
"""

import json
from pathlib import Path
from datetime import datetime, date
from invest_core.types import InvestState, AccountOverview, Position, Trade, Signal


# ─── 状态文件路径 ──────────────────────────────────────────────────────────

from invest_core.paths import get_state_dir, get_state_file

STATE_DIR = get_state_dir()
STATE_FILE = get_state_file()
STATE_DIR.mkdir(parents=True, exist_ok=True)


# ─── 加载 / 保存 ────────────────────────────────────────────────────────────

def load_state() -> InvestState:
    """
    从 invest_state.json 加载状态。
    文件不存在或损坏时返回空的 InvestState。
    """
    if not STATE_FILE.exists():
        return InvestState()

    try:
        data = json.loads(STATE_FILE.read_text(encoding="utf-8"))
        return InvestState.model_validate(data)
    except Exception:
        return InvestState()


def save_state(state: InvestState) -> None:
    """保存状态到 invest_state.json（原子写入）"""
    state.updated_at = datetime.now()
    tmp = STATE_FILE.with_suffix(".tmp")
    tmp.write_text(
        json.dumps(state.model_dump(), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    tmp.replace(STATE_FILE)


# ─── 持仓操作 ──────────────────────────────────────────────────────────────

def get_position(state: InvestState, code: str) -> Optional[Position]:
    """根据代码查找持仓"""
    for p in state.account.positions:
        if p.code == code:
            return p
    return None


def add_position(state: InvestState, position: Position) -> InvestState:
    """新增持仓（买入选中）"""
    existing = get_position(state, position.code)
    if existing:
        # 合并：加权平均成本
        total_shares = existing.shares + position.shares
        avg_cost = (existing.shares * existing.cost + position.shares * position.cost) / total_shares
        existing.shares = total_shares
        existing.cost = round(avg_cost, 4)
        existing.current_price = position.current_price
        existing.calc_pnl()
        return state

    position.entry_date = date.today()
    state.account.positions.append(position)
    # 更新建仓次数
    state.entry_count[position.code] = state.entry_count.get(position.code, 0) + 1
    _recalc_account(state)
    return state


def remove_position(state: InvestState, code: str, shares: Optional[int] = None) -> InvestState:
    """
    减少或清除持仓。

    Args:
        state: 当前状态
        code: 股票代码
        shares: 要减少的股数，None 表示全部清除
    """
    for i, p in enumerate(state.account.positions):
        if p.code == code:
            if shares is None or shares >= p.shares:
                # 全清
                state.account.positions.pop(i)
            else:
                p.shares -= shares
                p.calc_pnl()
            break
    _recalc_account(state)
    return state


def update_position_price(state: InvestState, code: str, current_price: float) -> InvestState:
    """更新持仓价格（行情刷新时调用）"""
    for p in state.account.positions:
        if p.code == code:
            p.current_price = current_price
            p.calc_pnl()
    _recalc_account(state)
    return state


# ─── 交易记录 ──────────────────────────────────────────────────────────────

def add_trade(state: InvestState, trade: Trade) -> InvestState:
    """追加交易记录"""
    state.trades.append(trade)
    return state


# ─── 信号历史 ──────────────────────────────────────────────────────────────

def add_signal(state: InvestState, signal: Signal) -> InvestState:
    """追加信号到历史"""
    state.signal_history.append(signal)
    # 保留最近100条
    if len(state.signal_history) > 100:
        state.signal_history = state.signal_history[-100:]
    return state


# ─── 冷却期 ───────────────────────────────────────────────────────────────

def is_cooling(state: InvestState, code: str) -> bool:
    """标的是否在冷却期内"""
    expiry = state.cooling_stocks.get(code)
    if expiry is None:
        return False
    return date.today() < expiry


def add_cooling(state: InvestState, code: str, days: int = 30) -> InvestState:
    """添加标的冷却期"""
    state.cooling_stocks[code] = date.today() + datetime.timedelta(days=days)
    return state


# ─── 账户重算 ─────────────────────────────────────────────────────────────

def _recalc_account(state: InvestState) -> None:
    """重新计算账户概览（市值/仓位/盈亏）"""
    total = 0.0
    for p in state.account.positions:
        total += p.market_value

    state.account.market_value = round(total, 2)
    state.account.position_pct = round(
        state.account.market_value / state.account.total_asset * 100, 2
    ) if state.account.total_asset > 0 else 0.0
    state.account.floating_pnl = round(
        state.account.market_value - sum(p.shares * p.cost for p in state.account.positions), 2
    )
    state.account.unrealized_pct = round(
        state.account.floating_pnl / sum(p.shares * p.cost for p in state.account.positions) * 100, 2
    ) if sum(p.shares * p.cost for p in state.account.positions) > 0 else 0.0


def sync_from_snapshot(state: InvestState, snapshot: dict) -> InvestState:
    """
    从持仓快照（holdings_snapshot.json）同步持仓数据。
    用于初始加载或定期对账。
    """
    positions = []
    for item in snapshot.get("positions", []):
        p = Position(
            code=item.get("code", ""),
            name=item.get("name", ""),
            shares=item.get("shares", 0),
            cost=item.get("cost", 0.0),
            current_price=item.get("current_price", 0.0),
            position_days=item.get("position_days", 0),
        )
        p.calc_pnl()
        positions.append(p)

    state.account.positions = positions
    state.account.total_asset = snapshot.get("total_asset", 0.0)
    state.account.cash = snapshot.get("cash", 0.0)
    _recalc_account(state)
    return state


# ─── Bitable 适配器（可选）─────────────────────────────────────────────────

def load_from_bitable() -> InvestState:
    """
    从飞书 Bitable 加载持仓数据（虚拟账户）。
    需要 Bitable token，不可用时静默返回空状态。
    """
    # 延迟导入，避免循环依赖
    try:
        from invest_core.executor.broker import fetch_positions_from_bitable
        data = fetch_positions_from_bitable()
        if data:
            state = load_state()
            for p in data:
                state = add_position(state, p)
            return state
    except Exception:
        pass
    return InvestState()


def sync_to_bitable(state: InvestState) -> bool:
    """
    同步状态到飞书 Bitable。
    失败时静默返回 False，不中断主流程。
    """
    try:
        from invest_core.executor.broker import sync_state_to_bitable
        return sync_state_to_bitable(state)
    except Exception:
        return False
