"""SQLite 事件存储"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any

from screen_watch.utils.logger import setup_logger

logger = setup_logger()
TZ_CN = timezone(timedelta(hours=8))

DEFAULT_DB = Path("logs/screen-watch.db")


class SqliteStore:
    def __init__(self, db_path: str | Path = DEFAULT_DB) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(self.db_path)
        self._init_schema()

    def _init_schema(self) -> None:
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS monitor_sessions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                preset TEXT NOT NULL,
                window_title TEXT,
                started_at TEXT NOT NULL,
                ended_at TEXT
            )
            """
        )
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS monitor_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id INTEGER NOT NULL,
                ts TEXT NOT NULL,
                type TEXT NOT NULL,
                payload TEXT NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY(session_id) REFERENCES monitor_sessions(id)
            )
            """
        )
        self._conn.commit()

    def start_session(self, preset: str, window_title: str) -> int:
        now = datetime.now(TZ_CN).isoformat()
        cur = self._conn.execute(
            "INSERT INTO monitor_sessions (preset, window_title, started_at) VALUES (?, ?, ?)",
            (preset, window_title, now),
        )
        self._conn.commit()
        session_id = int(cur.lastrowid)
        logger.info("SQLite session=%s path=%s", session_id, self.db_path)
        return session_id

    def save_event(self, session_id: int, event: dict[str, Any]) -> None:
        ts = event.get("ts") or datetime.now(TZ_CN).isoformat()
        event_type = event.get("type", "unknown")
        now = datetime.now(TZ_CN).isoformat()
        self._conn.execute(
            "INSERT INTO monitor_events (session_id, ts, type, payload, created_at) VALUES (?, ?, ?, ?, ?)",
            (session_id, ts, event_type, json.dumps(event, ensure_ascii=False), now),
        )
        self._conn.commit()

    def end_session(self, session_id: int) -> None:
        now = datetime.now(TZ_CN).isoformat()
        self._conn.execute(
            "UPDATE monitor_sessions SET ended_at = ? WHERE id = ?",
            (now, session_id),
        )
        self._conn.commit()

    def close(self) -> None:
        self._conn.close()
