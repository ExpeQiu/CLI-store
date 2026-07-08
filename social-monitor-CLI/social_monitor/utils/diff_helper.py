from typing import Any, Dict, List, Optional, Set, Tuple

from social_monitor.storage.base import BaseStorage
from social_monitor.utils.logger import setup_logger

logger = setup_logger(__name__)


def item_key(item: Dict[str, Any]) -> str:
    """生成去重键"""
    for field in ("id", "note_id", "bvid", "word", "title"):
        val = item.get(field)
        if val:
            return str(val)
    return str(hash(frozenset(item.items())))


def diff_items(
    existing: List[Dict[str, Any]], new_items: List[Dict[str, Any]]
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """对比增量，返回 (新增项, 合并后全量)"""
    seen: Set[str] = {item_key(x) for x in existing}
    added = []
    merged = list(existing)
    for item in new_items:
        key = item_key(item)
        if key not in seen:
            seen.add(key)
            added.append(item)
            merged.append(item)
    return added, merged


def load_and_diff(
    storage: BaseStorage,
    platform: str,
    account_id: str,
    new_items: List[Dict[str, Any]],
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]], int]:
    """加载历史、计算增量、保存合并结果，返回 (新增, 全量, 历史条数)"""
    existing = storage.load(platform, account_id)
    added, merged = diff_items(existing, new_items)
    if new_items:
        storage.save(platform, account_id, merged, mode="replace")
    logger.info(
        "增量对比 platform=%s account=%s 历史=%d 本次=%d 新增=%d",
        platform,
        account_id,
        len(existing),
        len(new_items),
        len(added),
    )
    return added, merged, len(existing)
