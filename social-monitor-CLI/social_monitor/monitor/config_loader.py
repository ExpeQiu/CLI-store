"""加载 monitor.yaml"""

from pathlib import Path
from typing import Any, Dict

import yaml

from social_monitor.utils.cookie_manager import MONITOR_FILE


def load_monitor_config(path: Path = None) -> Dict[str, Any]:
    cfg_path = path or MONITOR_FILE
    if not cfg_path.exists():
        return {}
    with open(cfg_path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    return data or {}


def normalize_accounts(section: Dict[str, Any], key: str = "accounts") -> list:
    """兼容 accounts: [1,2] 或 accounts: [{uid: 1}]"""
    raw = section.get(key) or []
    result = []
    for item in raw:
        if isinstance(item, dict):
            result.append(item)
        else:
            result.append(item)
    return result
