"""情报采集器"""

from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger("intel_collect.collectors.feed")

DEMO_ITEMS = [
    {
        "title": "固态电池量产节点提前至2027年",
        "source": "行业情报",
        "url": "https://example.com/intel/1",
        "published_at": "2026-06-24T10:00:00+08:00",
        "tags": ["新能源", "电池"],
    },
    {
        "title": "L3 自动驾驶新规征求意见稿发布",
        "source": "政策监测",
        "url": "https://example.com/intel/2",
        "published_at": "2026-06-23T15:30:00+08:00",
        "tags": ["智驾", "政策"],
    },
    {
        "title": "头部车企联合建设超充网络",
        "source": "竞品动态",
        "url": "https://example.com/intel/3",
        "published_at": "2026-06-22T09:00:00+08:00",
        "tags": ["充电", "竞品"],
    },
]


def is_mock(demo: bool) -> bool:
    return demo or os.getenv("INTEL_COLLECT_MOCK_MODE", "").lower() in ("1", "true", "yes")


def fetch_intel(*, topic: str = "", limit: int = 20, demo: bool = False) -> dict[str, Any]:
    if is_mock(demo):
        items = DEMO_ITEMS[:limit]
        source = "demo"
    else:
        # 占位：后续接入 RSS / 定制爬虫
        logger.warning("live 模式尚未配置数据源，返回空结果")
        items = []
        source = "live"

    if topic:
        items = [i for i in items if topic.lower() in i["title"].lower() or topic in i.get("tags", [])]

    return {
        "module": "intel-feed",
        "data_source": source,
        "fetched_at": datetime.now(timezone.utc).astimezone().isoformat(),
        "topic": topic or None,
        "count": len(items),
        "items": items,
    }
