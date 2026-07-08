"""SQLite 存储测试"""

import json
from pathlib import Path

from screen_watch.storage.sqlite_store import SqliteStore


def test_sqlite_store_roundtrip(tmp_path: Path) -> None:
    db = tmp_path / "test.db"
    store = SqliteStore(db)
    sid = store.start_session("wechat-live", "微信")
    event = {"ts": "2026-07-07T20:00:00+08:00", "type": "chat", "content": "hi"}
    store.save_event(sid, event)
    store.end_session(sid)

    conn = store._conn
    row = conn.execute("SELECT payload FROM monitor_events WHERE session_id=?", (sid,)).fetchone()
    assert row is not None
    payload = json.loads(row[0])
    assert payload["content"] == "hi"
    store.close()
