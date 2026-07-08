from typing import Optional
"""
invest_core.signals
====================
三维共振市场评分 + 个股持仓评分。

导出：
  score_market()    — 三维共振市场评分
  score_position()  — 个股持仓评分（止盈/止损/R1~R5）
  check_buy_signal() — 建仓信号检查
  grade_description() — 评级描述
"""

from invest_core.signals.market import (
    score_market,
    grade_description,
)

from invest_core.signals.position import (
    score_position,
    check_buy_signal,
)
