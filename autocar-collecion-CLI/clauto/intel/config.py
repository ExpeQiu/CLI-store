"""intel 模块配置"""

from __future__ import annotations

import os

# PostgreSQL（intel 三表所在库）
DATABASE_URL = os.getenv(
    "CLAUTO_INTEL_DATABASE_URL",
    os.getenv("DATABASE_URL", "postgresql://expeqiu@localhost:5432/postgres"),
)

# 飞书 Bitable — 情报库（技术推广评价体系.md）
FEISHU_APP_ID = os.getenv("FEISHU_APP_ID", "")
FEISHU_APP_SECRET = os.getenv("FEISHU_APP_SECRET", "")
FEISHU_INTEL_APP_TOKEN = os.getenv(
    "FEISHU_INTEL_APP_TOKEN", "VklebsOdxa9Y15sf9wdcSJMPn71"
)
FEISHU_INTEL_TABLE_ID = os.getenv("FEISHU_INTEL_TABLE_ID", "")

# Bitable 字段 → PG 列映射（同步时按字段名匹配，可在 .env 覆盖 JSON）
DEFAULT_FIELD_MAP = {
    "车企": "车企",
    "品牌": "车企",
    "车型": "车型",
    "发布类型": "发布类型",
    "预计发布日期": "预计发布日期",
    "动力类型": "动力类型",
    "价格区间": "价格区间",
    "价格": "价格区间",
    "平台": "平台",
    "智驾等级": "智驾等级",
    "智驾": "智驾等级",
    "配置亮点": "配置亮点",
    "分析师": "分析师",
    "分析状态": "分析状态",
}
