"""ingest 单元测试"""

from __future__ import annotations

import io
import json
from pathlib import Path

import pytest
from sqlalchemy.orm import sessionmaker

from app.core import database as db_module
from app.core.database import Base
from app.ingest import screen_watch as ingest_mod
from app.models.schema import DanmakuRecord, EventTask, LiveMetric


@pytest.fixture()
def ingest_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    db_file = tmp_path / "ingest_test.db"
    url = f"sqlite:///{db_file}"
    engine = db_module.create_engine(url, connect_args={"check_same_thread": False})
    Session = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    monkeypatch.setattr(db_module, "engine", engine)
    monkeypatch.setattr(db_module, "SessionLocal", Session)
    Base.metadata.create_all(bind=engine)
    yield Session
    Base.metadata.drop_all(bind=engine)


def test_ingest_demo(ingest_env):
    from app.ingest.screen_watch import IngestConfig, run_ingest

    cfg = IngestConfig(platform="sph-client", room_id="test-room")
    result = run_ingest(io.StringIO(""), cfg, demo=True)
    assert result["data_source"] == "demo"
    assert result["metrics"] == 1
    assert result["chats"] == 2

    db = ingest_env()
    try:
        task = db.get(EventTask, result["task_id"])
        assert task.platform == "sph-client"
        assert task.status == "stopped"
        assert db.query(LiveMetric).filter_by(task_id=result["task_id"]).count() == 1
        assert db.query(DanmakuRecord).filter_by(task_id=result["task_id"]).count() == 2
    finally:
        db.close()


def test_ingest_jsonl_stdin(ingest_env):
    from app.ingest.screen_watch import IngestConfig, run_ingest

    lines = [
        {"type": "metric", "viewer_count": 100},
        {"type": "chat", "user": "A", "content": "hello"},
    ]
    payload = "\n".join(json.dumps(x, ensure_ascii=False) for x in lines) + "\n"
    cfg = IngestConfig(platform="sph-client", room_id="pipe-test")
    result = run_ingest(io.StringIO(payload), cfg, demo=False)
    assert result["metrics"] == 1
    assert result["chats"] == 1
