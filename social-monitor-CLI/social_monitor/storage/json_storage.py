import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from social_monitor.storage.base import BaseStorage
from social_monitor.utils.logger import setup_logger

logger = setup_logger(__name__)


class JSONStorage(BaseStorage):
    """JSON 文件存储"""

    def __init__(self, data_dir: Optional[str] = None):
        self.data_dir = Path(data_dir or Path.home() / ".social-monitor" / "data")
        self.data_dir.mkdir(parents=True, exist_ok=True)

    def _filepath(self, platform: str, account_id: str) -> Path:
        safe_id = account_id.replace("/", "_")
        return self.data_dir / f"{platform}_{safe_id}.json"

    def save(
        self, platform: str, account_id: str, items: List[Dict[str, Any]], mode: str = "append"
    ) -> int:
        filepath = self._filepath(platform, account_id)
        logger.info("保存数据 platform=%s account=%s mode=%s count=%d", platform, account_id, mode, len(items))

        if mode == "append" and filepath.exists():
            with open(filepath, "r", encoding="utf-8") as f:
                existing = json.load(f)
            existing_ids = {item.get("id") for item in existing if item.get("id")}
            for item in items:
                if item.get("id") not in existing_ids:
                    existing.append(item)
            items = existing

        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(items, f, ensure_ascii=False, indent=2)

        logger.info("已写入 %s，共 %d 条", filepath, len(items))
        return len(items)

    def load(self, platform: str, account_id: str) -> List[Dict[str, Any]]:
        filepath = self._filepath(platform, account_id)
        if not filepath.exists():
            return []
        with open(filepath, "r", encoding="utf-8") as f:
            return json.load(f)
