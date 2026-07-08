"""screen-watch JSONL → zhibo-monitor 数据库入库"""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from typing import Any, Iterable, TextIO

from sqlalchemy.orm import Session

from app.core import database as db_module
from app.core.database import Base
from app.models.schema import DanmakuRecord, EventTask, LiveMetric
from zhibo_monitor.utils.logger import setup_logger

logger = setup_logger()
TZ_CN = timezone(timedelta(hours=8))

DEMO_EVENTS: list[dict[str, Any]] = [
    {
        "ts": "2026-07-07T20:00:00+08:00",
        "type": "metric",
        "viewer_count": 687,
        "raw": "687人看过",
    },
    {
        "ts": "2026-07-07T20:00:01+08:00",
        "type": "chat",
        "user": "张三",
        "content": "007GT多少钱",
        "raw": "张三: 007GT多少钱",
    },
    {
        "ts": "2026-07-07T20:00:02+08:00",
        "type": "chat",
        "user": "李四",
        "content": "猎装版真好看",
        "raw": "李四: 猎装版真好看",
    },
]


@dataclass
class IngestStats:
    metrics: int = 0
    chats: int = 0
    skipped: int = 0
    errors: int = 0


@dataclass
class IngestConfig:
    platform: str = "sph-client"
    room_id: str = "wechat-ocr"
    event_name: str = "微信客户端直播-OCR"
    car_brand: str = "unknown"
    car_model: str = ""
    event_id: str | None = None
    task_id: int | None = None
    finish_on_eof: bool = True
    chat_batch_size: int = 20


def _parse_ts(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def ensure_task(db: Session, cfg: IngestConfig) -> int:
    if cfg.task_id is not None:
        task = db.get(EventTask, cfg.task_id)
        if task is None:
            raise ValueError(f"task_id 不存在: {cfg.task_id}")
        if task.status != "running":
            task.status = "running"
            db.commit()
        return task.id

    task = EventTask(
        platform=cfg.platform,
        room_id=cfg.room_id,
        event_name=cfg.event_name,
        car_brand=cfg.car_brand,
        car_model=cfg.car_model or None,
        event_id=cfg.event_id,
        status="running",
    )
    db.add(task)
    db.commit()
    db.refresh(task)
    logger.info(
        "创建 ingest 任务 id=%s platform=%s room_id=%s",
        task.id,
        cfg.platform,
        cfg.room_id,
    )
    return task.id


def finish_task(db: Session, task_id: int) -> None:
    task = db.get(EventTask, task_id)
    if task and task.status == "running":
        task.status = "stopped"
        task.end_time = datetime.now(TZ_CN)
        db.commit()
        logger.info("任务已结束 id=%s", task_id)


def ingest_event(
    db: Session,
    task_id: int,
    event: dict[str, Any],
    stats: IngestStats,
    chat_buffer: list[dict[str, Any]],
) -> None:
    event_type = event.get("type")
    if event_type == "metric":
        viewer = int(event.get("viewer_count") or 0)
        metric = LiveMetric(
            task_id=task_id,
            online_count=viewer,
            like_count=0,
            danmaku_density=0,
        )
        ts = _parse_ts(event.get("ts"))
        if ts is not None:
            metric.timestamp = ts
        db.add(metric)
        db.commit()
        stats.metrics += 1
        logger.debug("metric viewer_count=%s", viewer)
        return

    if event_type == "chat":
        chat_buffer.append(event)
        if len(chat_buffer) >= 20:
            flush_chat_buffer(db, task_id, chat_buffer, stats)
        return

    stats.skipped += 1
    logger.debug("跳过未知事件 type=%s", event_type)


def flush_chat_buffer(
    db: Session,
    task_id: int,
    chat_buffer: list[dict[str, Any]],
    stats: IngestStats,
) -> None:
    if not chat_buffer:
        return

    records = []
    for item in chat_buffer:
        ts = _parse_ts(item.get("ts"))
        record = DanmakuRecord(
            task_id=task_id,
            user_name=item.get("user") or "",
            content=item.get("content") or "",
        )
        if ts is not None:
            record.timestamp = ts
        records.append(record)

    db.bulk_save_objects(records)
    db.commit()
    stats.chats += len(records)
    logger.info("批量写入弹幕 %d 条", len(records))
    chat_buffer.clear()


def iter_events(source: TextIO, *, demo: bool = False) -> Iterable[dict[str, Any]]:
    if demo:
        yield from DEMO_EVENTS
        return

    for line_no, raw in enumerate(source, start=1):
        line = raw.strip()
        if not line:
            continue
        try:
            yield json.loads(line)
        except json.JSONDecodeError as exc:
            logger.warning("第 %d 行 JSON 解析失败: %s", line_no, exc)
            continue


def run_ingest(
    source: TextIO,
    cfg: IngestConfig,
    *,
    demo: bool = False,
) -> dict[str, Any]:
    Base.metadata.create_all(bind=db_module.engine)
    stats = IngestStats()
    chat_buffer: list[dict[str, Any]] = []

    db: Session = db_module.SessionLocal()
    task_id: int | None = None
    try:
        task_id = ensure_task(db, cfg)
        for event in iter_events(source, demo=demo):
            try:
                ingest_event(db, task_id, event, stats, chat_buffer)
            except Exception as exc:
                stats.errors += 1
                logger.exception("入库事件失败: %s", exc)
                db.rollback()

        flush_chat_buffer(db, task_id, chat_buffer, stats)

        if cfg.finish_on_eof and not demo:
            finish_task(db, task_id)
        elif demo:
            finish_task(db, task_id)

    finally:
        db.close()

    return {
        "module": "ingest",
        "data_source": "demo" if demo else "stdin",
        "task_id": task_id,
        "platform": cfg.platform,
        "room_id": cfg.room_id,
        "metrics": stats.metrics,
        "chats": stats.chats,
        "skipped": stats.skipped,
        "errors": stats.errors,
    }
