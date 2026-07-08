from typing import Optional
"""
invest_core.executor
====================
状态管理、交易执行、Bitable适配器。

导出：
  load_state()    — 加载状态
  save_state()    — 保存状态
  check_signals() — 检查触发信号
  apply_signal()  — 应用信号到状态
  sync_to_bitable() — 同步到飞书Bitable
"""

from invest_core.executor.state import (
    load_state,
    save_state,
    get_position,
    add_position,
    remove_position,
    update_position_price,
    add_trade,
    add_signal,
    is_cooling,
    add_cooling,
    sync_from_snapshot,
    load_from_bitable,
    sync_to_bitable,
)

from invest_core.executor.trader import (
    check_signals,
    apply_signal,
)

from invest_core.executor.broker import (
    fetch_positions_from_bitable,
    sync_state_to_bitable,
    append_trade_to_bitable,
)
