"""统一 JSON 输出元数据"""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any


def wrap_json(
    payload_key: str,
    payload: Any,
    *,
    module: str,
    data_source: str,
    warnings: list[str] | None = None,
) -> str:
    """生成带统一元数据的 JSON 输出"""
    data = {
        "module": module,
        "data_source": data_source,
        "fetched_at": datetime.now().isoformat(),
        "fetch_time": datetime.now().isoformat(),
        "warnings": warnings or [],
        payload_key: payload,
    }
    if isinstance(payload, list):
        data["count"] = len(payload)
    return json.dumps(data, ensure_ascii=False, indent=2)


def source_banner(data_source: str, warnings: list[str] | None = None) -> str:
    """Markdown 数据来源标注"""
    labels = {
        "live": "实时抓取",
        "demo": "演示数据 [DEMO]",
        "empty": "无数据",
    }
    label = labels.get(data_source, data_source)
    lines = [f"> 数据来源: {label}"]
    for w in warnings or []:
        lines.append(f"> ⚠️ {w}")
    return "\n".join(lines)
