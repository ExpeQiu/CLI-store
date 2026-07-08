import json
from typing import Any, Dict, List, Optional

from social_monitor.storage.base import BaseStorage
from social_monitor.utils.diff_helper import item_key
from social_monitor.utils.logger import setup_logger

logger = setup_logger(__name__)


class MySQLStorage(BaseStorage):
    """MySQL 存储（可选依赖 pymysql）"""

    def __init__(self, config: dict):
        try:
            import pymysql
        except ImportError as e:
            raise ImportError("MySQL 存储需要安装 pymysql: pip install pymysql") from e

        self.connection = pymysql.connect(
            host=config["host"],
            port=config.get("port", 3306),
            user=config["user"],
            password=config["password"],
            database=config["database"],
            charset="utf8mb4",
        )
        self.create_table()

    def save(
        self, platform: str, account_id: str, items: List[Dict[str, Any]], mode: str = "append"
    ) -> int:
        logger.info("MySQL 保存 platform=%s account=%s count=%d", platform, account_id, len(items))
        with self.connection.cursor() as cursor:
            for item in items:
                cursor.execute(
                    """
                    INSERT INTO sm_content
                    (platform, account_id, content_id, title, content_text,
                     publish_at, likes_count, comments_count, reposts_count,
                     raw_data, created_at)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NOW())
                    ON DUPLICATE KEY UPDATE
                    likes_count = VALUES(likes_count),
                    comments_count = VALUES(comments_count),
                    reposts_count = VALUES(reposts_count)
                    """,
                    (
                        platform,
                        account_id,
                        item_key(item),
                        item.get("title", item.get("word", "")),
                        item.get("text", item.get("desc", "")),
                        item.get("publish_at", item.get("created_at", "")),
                        item.get("attitudes_count", item.get("liked_count", item.get("likes", item.get("hot_value", 0)))),
                        item.get("comments_count", item.get("comment_count", 0)),
                        item.get("reposts_count", 0),
                        json.dumps(item, ensure_ascii=False),
                    ),
                )
        self.connection.commit()
        return len(items)

    def load(self, platform: str, account_id: str) -> List[Dict[str, Any]]:
        with self.connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT raw_data FROM sm_content
                WHERE platform = %s AND account_id = %s
                ORDER BY created_at DESC
                """,
                (platform, account_id),
            )
            rows = cursor.fetchall()
        return [json.loads(row[0]) for row in rows if row[0]]

    def create_table(self) -> None:
        with self.connection.cursor() as cursor:
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS sm_content (
                    id BIGINT AUTO_INCREMENT PRIMARY KEY,
                    platform VARCHAR(50) NOT NULL,
                    account_id VARCHAR(100) NOT NULL,
                    content_id VARCHAR(100),
                    title VARCHAR(500),
                    content_text TEXT,
                    publish_at VARCHAR(50),
                    likes_count INT DEFAULT 0,
                    comments_count INT DEFAULT 0,
                    reposts_count INT DEFAULT 0,
                    raw_data JSON,
                    created_at DATETIME DEFAULT NOW(),
                    INDEX idx_platform_account (platform, account_id),
                    UNIQUE KEY uk_content (platform, account_id, content_id)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
                """
            )
        self.connection.commit()

    def close(self) -> None:
        self.connection.close()
