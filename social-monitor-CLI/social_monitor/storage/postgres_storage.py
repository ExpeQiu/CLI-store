import json
import os
from typing import Any, Dict, List

from social_monitor.storage.base import BaseStorage
from social_monitor.utils.diff_helper import item_key
from social_monitor.utils.logger import setup_logger

logger = setup_logger(__name__)


class PostgresStorage(BaseStorage):
    """PostgreSQL 存储（可选依赖 psycopg2）"""

    def __init__(self, config: dict):
        try:
            import psycopg2
            import psycopg2.extras
        except ImportError as e:
            raise ImportError(
                "PostgreSQL 存储需要安装 psycopg2: pip install 'social-monitor[postgres]'"
            ) from e

        self._psycopg2 = psycopg2
        self.connection = psycopg2.connect(
            host=config.get("host", "localhost"),
            port=config.get("port", 5432),
            user=config.get("user", "postgres"),
            password=config.get("password", ""),
            dbname=config.get("database", "social_monitor"),
        )
        self.connection.autocommit = False
        self._event_context = self._load_event_context()
        self.create_table()

    @staticmethod
    def _load_event_context() -> Dict[str, str | None]:
        """从 SIM 任务环境变量读取场次上下文（event-live / event-post 注入）"""
        keys = ("event_id", "event_name", "brand", "car_model")
        env_map = {
            "event_id": ("SIM_EVENT_ID", "EVENT_ID"),
            "event_name": ("SIM_EVENT_NAME", "EVENT_NAME"),
            "brand": ("SIM_EVENT_BRAND", "EVENT_BRAND"),
            "car_model": ("SIM_EVENT_MODEL", "EVENT_MODEL"),
        }
        ctx: Dict[str, str | None] = {}
        for field, env_keys in env_map.items():
            val = ""
            for ek in env_keys:
                val = os.environ.get(ek, "").strip()
                if val:
                    break
            ctx[field] = val or None
        return ctx

    def save(
        self, platform: str, account_id: str, items: List[Dict[str, Any]], mode: str = "append"
    ) -> int:
        logger.info(
            "PostgreSQL 保存 platform=%s account=%s mode=%s count=%d",
            platform,
            account_id,
            mode,
            len(items),
        )
        if mode == "replace":
            with self.connection.cursor() as cursor:
                cursor.execute(
                    "DELETE FROM sm_content WHERE platform = %s AND account_id = %s",
                    (platform, account_id),
                )

        with self.connection.cursor() as cursor:
            for item in items:
                cursor.execute(
                    """
                    INSERT INTO sm_content
                    (platform, account_id, content_id, title, content_text,
                     publish_at, likes_count, comments_count, reposts_count,
                     raw_data, event_id, event_name, brand, car_model, created_at)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NOW())
                    ON CONFLICT (platform, account_id, content_id)
                    DO UPDATE SET
                        title = EXCLUDED.title,
                        content_text = EXCLUDED.content_text,
                        publish_at = EXCLUDED.publish_at,
                        likes_count = EXCLUDED.likes_count,
                        comments_count = EXCLUDED.comments_count,
                        reposts_count = EXCLUDED.reposts_count,
                        raw_data = EXCLUDED.raw_data,
                        event_id = COALESCE(EXCLUDED.event_id, sm_content.event_id),
                        event_name = COALESCE(EXCLUDED.event_name, sm_content.event_name),
                        brand = COALESCE(EXCLUDED.brand, sm_content.brand),
                        car_model = COALESCE(EXCLUDED.car_model, sm_content.car_model)
                    """,
                    self._row_params(platform, account_id, item),
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

        result = []
        for row in rows:
            raw = row[0]
            if not raw:
                continue
            if isinstance(raw, dict):
                result.append(raw)
            else:
                result.append(json.loads(raw))
        return result

    def create_table(self) -> None:
        with self.connection.cursor() as cursor:
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS sm_content (
                    id BIGSERIAL PRIMARY KEY,
                    platform VARCHAR(50) NOT NULL,
                    account_id VARCHAR(100) NOT NULL,
                    content_id VARCHAR(100) NOT NULL DEFAULT '',
                    title VARCHAR(500),
                    content_text TEXT,
                    publish_at VARCHAR(50),
                    likes_count INT DEFAULT 0,
                    comments_count INT DEFAULT 0,
                    reposts_count INT DEFAULT 0,
                    raw_data JSONB,
                    event_id VARCHAR(100),
                    event_name VARCHAR(200),
                    brand VARCHAR(100),
                    car_model VARCHAR(200),
                    created_at TIMESTAMPTZ DEFAULT NOW(),
                    UNIQUE (platform, account_id, content_id)
                )
                """
            )
            cursor.execute(
                "ALTER TABLE sm_content ADD COLUMN IF NOT EXISTS event_id VARCHAR(100)"
            )
            cursor.execute(
                "ALTER TABLE sm_content ADD COLUMN IF NOT EXISTS event_name VARCHAR(200)"
            )
            cursor.execute(
                "ALTER TABLE sm_content ADD COLUMN IF NOT EXISTS brand VARCHAR(100)"
            )
            cursor.execute(
                "ALTER TABLE sm_content ADD COLUMN IF NOT EXISTS car_model VARCHAR(200)"
            )
            cursor.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_sm_content_event_id
                ON sm_content (event_id)
                """
            )
            cursor.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_sm_content_platform_account
                ON sm_content (platform, account_id)
                """
            )
        self.connection.commit()

    def close(self) -> None:
        self.connection.close()

    def _row_params(self, platform: str, account_id: str, item: Dict[str, Any]) -> tuple:
        content_id = item_key(item)
        event_id = item.get("event_id") or item.get("_event_id") or self._event_context.get("event_id")
        event_name = item.get("event_name") or item.get("_event_name") or self._event_context.get("event_name")
        brand = item.get("brand") or item.get("_brand") or self._event_context.get("brand")
        car_model = item.get("car_model") or item.get("_car_model") or self._event_context.get("car_model")
        return (
            platform,
            account_id,
            content_id,
            item.get("title", item.get("word", "")),
            item.get("text", item.get("desc", "")),
            str(item.get("publish_at", item.get("created_at", ""))),
            item.get("attitudes_count", item.get("liked_count", item.get("likes", item.get("hot_value", 0)))),
            item.get("comments_count", item.get("comment_count", 0)),
            item.get("reposts_count", 0),
            json.dumps(item, ensure_ascii=False),
            event_id,
            event_name,
            brand,
            car_model,
        )
