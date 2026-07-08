"""
invest_core.types
=================
投资决策系统的核心类型定义（Pydantic models）。

所有 invest_core 子模块共享这些类型，是 invest_rules.md 的结构化表达。
"""

from __future__ import annotations

from datetime import datetime, date
from enum import Enum
from typing import Optional
from pydantic import BaseModel, Field


# ─── 市场评分等级 ────────────────────────────────────────────────────────────

class MarketGrade(str, Enum):
    A = "A"   # 80~100：三维共振做多
    B = "B"   # 60~79：两维共振
    C = "C"   # 40~59：一维共振
    D = "D"   # 20~39：空头共振
    E = "E"   # 0~19：强空信号


class MarketDirection(str, Enum):
    BULL = "bull"      # 做多
    NEUTRAL = "neutral" # 中性
    BEAR = "bear"      # 做空


# ─── 宏观数据类型 ─────────────────────────────────────────────────────────────

class NorthMoney(BaseModel):
    """北向资金"""
    hgt: float = 0.0       # 沪股通当日净流入（亿元）
    sgt: float = 0.0       # 深股通当日净流入（亿元）
    total: float = 0.0     # 合计
    ok: bool = True
    updated_at: Optional[datetime] = None


class ExchangeRate(BaseModel):
    """汇率"""
    usdcny: float = 7.0    # USD/CNY
    ok: bool = True
    updated_at: Optional[datetime] = None


class MacroIndicators(BaseModel):
    """宏观指标集合"""
    north_money: NorthMoney = Field(default_factory=NorthMoney)
    exchange_rate: ExchangeRate = Field(default_factory=ExchangeRate)
    erp: float = 0.0       # 股债收益差 E/P - 10Y国债（%）
    us10y: float = 0.0     # 美债10年收益率（%）
    turnover_rate: float = 0.0  # 全A换手率（%）
    ok: bool = True
    updated_at: Optional[datetime] = None


# ─── 技术数据类型 ─────────────────────────────────────────────────────────────

class IndexTech(BaseModel):
    """大盘技术指标"""
    code: str = ""
    name: str = ""
    price: float = 0.0
    change_pct: float = 0.0   # 涨跌幅（%）
    rsi14: float = 50.0       # RSI(14)
    ma5_dir: int = 0          # MA5方向：1=多头、-1=空头、0=中性
    ma20_dir: int = 0         # MA20方向
    ma60_dir: int = 0         # MA60方向
    ok: bool = True
    updated_at: Optional[datetime] = None


class StockTech(BaseModel):
    """个股技术指标"""
    code: str = ""
    name: str = ""
    price: float = 0.0
    change_pct: float = 0.0
    rsi14: float = 50.0
    ma5_dir: int = 0
    ma20_dir: int = 0
    atr14: float = 0.0       # ATR(14)
    vol_ratio: float = 1.0   # 量比（今日成交量/昨日）
    position_days: int = 0    # 持仓天数
    ok: bool = True
    updated_at: Optional[datetime] = None


# ─── 三维信号贡献 ─────────────────────────────────────────────────────────────

class SignalComponent(BaseModel):
    """单个信号维度贡献"""
    dimension: str           # 如 "north_money", "rsi", "ma_direction"
    score: float             # 贡献分值（可正可负）
    weight: float = 1.0      # 权重（预留）
    detail: str = ""         # 说明文字


# ─── 市场评分 ─────────────────────────────────────────────────────────────────

class MarketScore(BaseModel):
    """三维共振市场评分"""
    total: int = 50              # 总分 0~100
    grade: MarketGrade = MarketGrade.C
    direction: MarketDirection = MarketDirection.NEUTRAL

    # 分层贡献
    macro: int = 0               # 宏观层 -30~+30
    structure: int = 0           # 结构层 -20~+20
    tech: int = 0                # 技术层 -30~+30

    # 宏观层细分
    north_money_score: int = 0   # 北向 ±10
    exchange_rate_score: int = 0 # 汇率 ±5
    erp_score: int = 0          # ERP ±10
    us10y_score: int = 0        # 美债 ±10

    # 结构层细分
    industry_ratio_score: int = 0 # 行业涨跌比 ±10
    turnover_score: int = 0      # 换手率 ±8

    # 技术层细分
    rsi_score: int = 0           # RSI ±15
    ma_score: int = 0            # 均线方向 ±10
    index_change_score: int = 0  # 上证涨跌幅 ±5

    # 信号详情
    components: list[SignalComponent] = Field(default_factory=list)

    # 建议
    recommendation: str = "hold"  # buy / hold / sell / reduce
    confidence: float = 0.5       # 置信度 0~1

    # 状态
    updated_at: Optional[datetime] = None

    def grade_from_score(score: int) -> MarketGrade:
        if score >= 80: return MarketGrade.A
        if score >= 60: return MarketGrade.B
        if score >= 40: return MarketGrade.C
        if score >= 20: return MarketGrade.D
        return MarketGrade.E

    def direction_from_grade(grade: MarketGrade) -> MarketDirection:
        return {
            MarketGrade.A: MarketDirection.BULL,
            MarketGrade.B: MarketDirection.BULL,
            MarketGrade.C: MarketDirection.NEUTRAL,
            MarketGrade.D: MarketDirection.BEAR,
            MarketGrade.E: MarketDirection.BEAR,
        }[grade]


# ─── 个股持仓 ─────────────────────────────────────────────────────────────────

class Position(BaseModel):
    """持仓"""
    code: str = ""           # 股票代码（6位，字符串）
    name: str = ""
    shares: int = 0         # 股份数
    cost: float = 0.0       # 成本价
    current_price: float = 0.0
    market_value: float = 0.0   # 市值
    floating_pnl: float = 0.0   # 浮动盈亏（元）
    floating_pct: float = 0.0   # 浮动盈亏比例（%）
    stop_loss_price: float = 0.0 # 止损价（ATR动态或固定）
    entry_date: Optional[date] = None  # 建仓日期
    position_days: int = 0       # 持仓天数
    grade: str = "C"              # 市场等级（建仓时）
    triggered_take_profit: str = ""  # 已触发止盈档位（如 "3" 或 "3;trailing_stop"）
    # 技术指标
    tech: StockTech = Field(default_factory=StockTech)

    def calc_pnl(self) -> tuple[float, float]:
        self.market_value = round(self.shares * self.current_price, 2)
        self.floating_pnl = round(self.market_value - self.shares * self.cost, 2)
        self.floating_pct = round(self.floating_pnl / (self.shares * self.cost) * 100, 2) if self.shares * self.cost > 0 else 0.0
        return self.floating_pnl, self.floating_pct


# ─── 交易记录 ─────────────────────────────────────────────────────────────────

class Trade(BaseModel):
    """交易记录"""
    id: str = ""
    date: date
    action: str = ""           # buy / sell / reduce / add
    code: str = ""
    name: str = ""
    price: float = 0.0
    shares: int = 0
    amount: float = 0.0        # 金额
    reason: str = ""           # 交易原因
    signal_type: str = ""      # stop_loss / take_profit_1 / take_profit_2 / ...
    realized_pnl: float = 0.0  # 已实现盈亏（平仓时）


# ─── 信号 ─────────────────────────────────────────────────────────────────────

class Signal(BaseModel):
    """交易信号"""
    action: str = "hold"      # buy / sell / reduce / hold / tp_check
    code: str = ""
    name: str = ""
    reason: str = ""           # 信号原因
    confidence: float = 0.5
    triggered_rule: str = ""  # 触发的规则编号（如 "R5-tp3", "R2-stop_loss"）
    price: float = 0.0        # 触发价格
    shares: int = 0           # 建议股数（买入时）
    updated_at: datetime = Field(default_factory=datetime.now)


# ─── 止盈规则 ─────────────────────────────────────────────────────────────────

class TakeProfitRule(BaseModel):
    """止盈档位规则"""
    level: int               # 档位 1~5
    threshold: float         # 触发阈值（%浮盈）
    action: str              # reduce_1_3 / reduce_half / trailing_stop / cost_protection / rsi_condition
    description: str = ""
    condition: Optional[str] = None  # rsi_above_80 / None


class StopLossRule(BaseModel):
    """止损档位规则"""
    pct: float               # 亏损幅度（%）
    action: str              # warn / force_sell / deep_hold
    description: str = ""


# ─── 规则集 ────────────────────────────────────────────────────────────────────

class PositionLimit(BaseModel):
    """仓位限制"""
    single_stock_max: float = 0.20   # 单只股票最大仓位（占总资产%）
    single_etf_max: float = 0.30     # 单只ETF最大仓位
    single_bond_gold_max: float = 0.25  # 单只债券/黄金最大仓位
    industry_concentration: float = 0.40  # 同一行业最大仓位
    # ── 整体仓位（按市场等级）──
    min_position_by_grade: dict[str, float] = Field(default_factory=lambda: {
        "A": 0.50, "B": 0.40, "C": 0.30, "D": 0.10, "E": 0.00
    })
    max_position_by_grade: dict[str, float] = Field(default_factory=lambda: {
        "A": 0.70, "B": 0.70, "C": 0.60, "D": 0.30, "E": 0.10
    })


class MarketPhaseRules(BaseModel):
    """市场阶段规则"""
    min_hold_days: int = 10       # R1：禁止持仓<10天主动卖出
    stop_loss_warn: float = -3.0  # R2：-3% 预警
    stop_loss_force: float = -5.0 # R2：-5% 强制止损
    stop_loss_clear: float = -8.0  # R2：-8% 完全清仓
    stop_loss_deep: float = -15.0  # R2：-15% 深度套牢
    max_entries_per_stock: int = 2  # R3：每标的最多2次建仓


class RuleSet(BaseModel):
    """完整规则集（invest_rules.md 的结构化表达）"""
    version: str = "2.3"
    updated_at: str = "2026-05-30"

    # 仓位
    position_limits: PositionLimit = Field(default_factory=PositionLimit)

    # 市场阶段
    market_phase: MarketPhaseRules = Field(default_factory=MarketPhaseRules)

    # 止盈（v2.2）
    take_profit_rules: list[TakeProfitRule] = Field(default_factory=lambda: [
        TakeProfitRule(level=5, threshold=60.0, action="reduce_60pct", description="牛市顶部，减60%", condition=None),
        TakeProfitRule(level=4, threshold=40.0, action="rsi_condition", description="RSI>80减40%，否则持有", condition="rsi_above_80"),
        TakeProfitRule(level=3, threshold=25.0, action="trailing_stop", description="启用跟踪止损 high-2×ATR", condition=None),
        TakeProfitRule(level=2, threshold=15.0, action="cost_protection", description="启用成本保护 成本×1.02", condition=None),
        TakeProfitRule(level=1, threshold=8.0, action="reduce_1_3", description="减1/3仓位", condition=None),
    ])

    # 止损（快速查找）
    stop_loss_rules: list[StopLossRule] = Field(default_factory=lambda: [
        StopLossRule(pct=-3.0, action="warn", description="-3% 预警观察"),
        StopLossRule(pct=-5.0, action="force_sell", description="-5% 强制止损"),
        StopLossRule(pct=-8.0, action="clear", description="-8% 完全清仓"),
        StopLossRule(pct=-15.0, action="deep_hold", description="-15% 深度套牢"),
    ])

    # 三维评分权重映射（用于调试/可解释性）
    score_weights: dict[str, float] = Field(default_factory=lambda: {
        "north_money": 10.0,
        "exchange_rate": 5.0,
        "erp": 10.0,
        "us10y": 10.0,
        "industry_ratio": 10.0,
        "turnover_rate": 8.0,
        "rsi": 15.0,
        "ma_direction": 10.0,
        "index_change": 5.0,
    })

    # 评分等级阈值
    grade_thresholds: dict[str, tuple[int, int]] = Field(default_factory=lambda: {
        "A": (80, 100),
        "B": (60, 79),
        "C": (40, 59),
        "D": (20, 39),
        "E": (0, 19),
    })


# ─── 账户状态 ─────────────────────────────────────────────────────────────────

class AccountOverview(BaseModel):
    """账户概览"""
    total_asset: float = 0.0     # 总资产
    cash: float = 0.0           # 可用资金
    market_value: float = 0.0    # 持仓市值
    position_pct: float = 0.0    # 仓位占比（%）
    total_pnl: float = 0.0       # 累计盈亏（元）
    total_pnl_pct: float = 0.0   # 累计收益率（%）
    floating_pnl: float = 0.0   # 浮动盈亏
    unrealized_pct: float = 0.0  # 浮动收益率（%）
    positions: list[Position] = Field(default_factory=list)


class InvestState(BaseModel):
    """投资系统完整状态"""
    version: str = "2.3"
    updated_at: datetime = Field(default_factory=datetime.now)
    account: AccountOverview = Field(default_factory=AccountOverview)
    market_score: MarketScore = Field(default_factory=MarketScore)
    macro: MacroIndicators = Field(default_factory=MacroIndicators)
    trades: list[Trade] = Field(default_factory=list)
    signal_history: list[Signal] = Field(default_factory=list)

    # 冷却期标的（code → 冷却截止日期）
    cooling_stocks: dict[str, date] = Field(default_factory=dict)

    # 每只标的建仓次数（code → count）
    entry_count: dict[str, int] = Field(default_factory=dict)

    def grade(self) -> MarketGrade:
        return self.market_score.grade

    def position_value(self) -> float:
        return sum(p.market_value for p in self.account.positions)


# ─── 回测 ─────────────────────────────────────────────────────────────────────

class BacktestResult(BaseModel):
    """回测结果"""
    code: str = ""
    name: str = ""
    strategy: str = ""          # take_profit_v2.2 / hold / ...
    entry_date: date
    exit_date: date
    entry_price: float = 0.0
    exit_price: float = 0.0
    holding_days: int = 0
    pnl_pct: float = 0.0        # 收益率（%）
    vs_hold_pct: float = 0.0    # vs 持有策略超额收益
    trades_triggered: list[str] = Field(default_factory=list)  # 触发的交易信号
    max_drawdown: float = 0.0   # 最大回撤（%）
