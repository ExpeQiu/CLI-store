from typing import Optional, Tuple

from social_monitor.storage.base import BaseStorage
from social_monitor.storage.json_storage import JSONStorage
from social_monitor.storage.mysql_storage import MySQLStorage
from social_monitor.storage.postgres_storage import PostgresStorage
from social_monitor.utils.cookie_manager import load_config

STORAGE_LABELS = {
    "postgres": "PostgreSQL",
    "mysql": "MySQL",
    "json": "JSON",
}


def get_storage(storage_type: Optional[str] = None) -> Tuple[BaseStorage, str]:
    """根据配置创建存储实例，返回 (storage, 显示名称)"""
    config = load_config()
    st = storage_type or config.get("storage", {}).get("type", "postgres")

    if st == "postgres":
        return PostgresStorage(config.get("postgres", {})), STORAGE_LABELS["postgres"]
    if st == "mysql":
        return MySQLStorage(config.get("mysql", {})), STORAGE_LABELS["mysql"]

    data_dir = config.get("storage", {}).get("data_dir")
    return JSONStorage(data_dir=data_dir), STORAGE_LABELS["json"]


def close_storage(storage: BaseStorage) -> None:
    if hasattr(storage, "close"):
        storage.close()
