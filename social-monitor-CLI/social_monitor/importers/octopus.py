"""Octopus 导出数据入库"""

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from social_monitor.storage.factory import get_storage
from social_monitor.utils.logger import setup_logger

logger = setup_logger(__name__)


def normalize_octopus_items(
    raw: Any,
    platform: str,
    content_type: str,
    room_id: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """将 Octopus JSON 转为 sm_content 条目"""
    if isinstance(raw, dict):
        items = raw.get("items") or raw.get("data") or [raw]
    elif isinstance(raw, list):
        items = raw
    else:
        raise ValueError("Octopus JSON 须为数组或含 items/data 的对象")

    normalized = []
    for i, item in enumerate(items):
        if not isinstance(item, dict):
            continue
        content = item.get("content") or item.get("text") or item.get("message", "")
        normalized.append(
            {
                "id": str(item.get("id", i)),
                "content": content,
                "text": content,
                "user": item.get("user") or item.get("uname", ""),
                "timestamp": item.get("timestamp") or item.get("time", 0),
                "platform": platform,
                "content_type": content_type,
                "room_id": room_id or item.get("room_id", ""),
            }
        )
    return normalized


def import_octopus_file(
    file_path: Path,
    platform: str,
    content_type: str,
    account_id: str,
    storage=None,
    mode: str = "append",
) -> int:
    """读取 Octopus JSON 并写入存储"""
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(path)

    with open(path, "r", encoding="utf-8") as f:
        raw = json.load(f)

    room_id = account_id.replace("live_", "") if account_id.startswith("live_") else None
    items = normalize_octopus_items(raw, platform, content_type, room_id=room_id)
    if not items:
        logger.warning("Octopus 文件无有效条目: %s", path)
        return 0

    close_after = False
    if storage is None:
        storage, _ = get_storage()
        close_after = True

    try:
        total = storage.save(platform, account_id, items, mode=mode)
        logger.info(
            "Octopus 入库 platform=%s account=%s count=%d file=%s",
            platform,
            account_id,
            total,
            path,
        )
        return total
    finally:
        if close_after:
            from social_monitor.storage.factory import close_storage

            close_storage(storage)
