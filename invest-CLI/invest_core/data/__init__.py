from typing import Optional
"""
invest_core.data
================
宏观 + 行情数据获取。

导出：
  fetch_all_macro()      — 全部宏观数据
  fetch_north_money()    — 北向资金
  fetch_erp()           — 股债收益差
  fetch_us10y()         — 美债10Y
  fetch_turnover_rate()  — 全A换手率
  fetch_industry_ratio() — 行业涨跌比
  fetch_index_tech()     — 指数技术指标
  fetch_stock_tech()     — 个股技术指标
  tencent_quote()        — 腾讯实时行情
  wilder_rsi()           — RSI计算
"""

from invest_core.data.macro import (
    fetch_all_macro,
    fetch_north_money,
    fetch_usd_cny,
    fetch_erp,
    fetch_us10y,
    fetch_turnover_rate,
    fetch_industry_ratio,
)

from invest_core.data.market import (
    fetch_sina_kline,
    wilder_rsi,
    calc_atr,
    stock_code_to_sina,
    stock_code_to_tencent,
    tencent_quote,
    fetch_index_tech,
    fetch_stock_tech,
    fetch_all_index_tech,
)
