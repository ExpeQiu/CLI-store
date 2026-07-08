from __future__ import annotations

import argparse
import sqlite3
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

from sqlalchemy import text

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.append(str(PROJECT_ROOT))

from app.core.database import SessionLocal  # noqa: E402
from app.models.schema import (  # noqa: E402
    DanmakuAnalysis,
    DanmakuRecord,
    EventTask,
    InteractionEvent,
    LiveMetric,
)


TABLE_ORDER = [
    ("event_tasks", EventTask),
    ("live_metrics", LiveMetric),
    ("danmaku_records", DanmakuRecord),
    ("danmaku_analysis", DanmakuAnalysis),
    ("interaction_events", InteractionEvent),
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="将 zhibo-monitor 的 SQLite 数据迁移到 PostgreSQL")
    parser.add_argument(
        "--sqlite-path",
        default=str(PROJECT_ROOT / "data" / "writer.db"),
        help="SQLite 数据库路径",
    )
    parser.add_argument(
        "--replace",
        action="store_true",
        help="迁移前清空 PostgreSQL 中现有表数据",
    )
    return parser.parse_args()


def parse_datetime(value: Any) -> datetime | None:
    if value in (None, ""):
        return None
    if isinstance(value, datetime):
        return value
    text_value = str(value).strip().replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(text_value)
    except ValueError:
        return None


def fetch_rows(sqlite_path: str, table_name: str) -> list[sqlite3.Row]:
    conn = sqlite3.connect(sqlite_path)
    conn.row_factory = sqlite3.Row
    try:
        cur = conn.cursor()
        cur.execute(f"SELECT * FROM {table_name} ORDER BY id ASC")
        return cur.fetchall()
    finally:
        conn.close()


def reset_sequences(db) -> None:
    for table_name, _ in TABLE_ORDER:
        db.execute(
            text(
                f"""
                SELECT setval(
                  pg_get_serial_sequence('{table_name}', 'id'),
                  COALESCE((SELECT MAX(id) FROM {table_name}), 1),
                  true
                )
                """
            )
        )


def main() -> int:
    args = parse_args()
    sqlite_path = Path(args.sqlite_path).expanduser().resolve()
    if not sqlite_path.exists():
      print(f"SQLite 文件不存在: {sqlite_path}", file=sys.stderr)
      return 1

    db = SessionLocal()
    try:
        if args.replace:
            db.execute(
                text(
                    """
                    TRUNCATE TABLE
                      danmaku_analysis,
                      danmaku_records,
                      interaction_events,
                      live_metrics,
                      event_tasks
                    RESTART IDENTITY CASCADE
                    """
                )
            )
            db.commit()

        event_rows = fetch_rows(str(sqlite_path), "event_tasks")
        metric_rows = fetch_rows(str(sqlite_path), "live_metrics")
        danmaku_rows = fetch_rows(str(sqlite_path), "danmaku_records")
        analysis_rows = fetch_rows(str(sqlite_path), "danmaku_analysis")
        interaction_rows = fetch_rows(str(sqlite_path), "interaction_events")

        for row in event_rows:
            db.merge(
                EventTask(
                    id=row["id"],
                    platform=row["platform"],
                    room_id=row["room_id"],
                    event_name=row["event_name"],
                    car_brand=row["car_brand"],
                    status=row["status"],
                    start_time=parse_datetime(row["start_time"]),
                    end_time=parse_datetime(row["end_time"]),
                )
            )

        for row in metric_rows:
            db.merge(
                LiveMetric(
                    id=row["id"],
                    task_id=row["task_id"],
                    timestamp=parse_datetime(row["timestamp"]),
                    online_count=row["online_count"] or 0,
                    like_count=row["like_count"] or 0,
                    danmaku_density=row["danmaku_density"] or 0,
                )
            )

        for row in danmaku_rows:
            db.merge(
                DanmakuRecord(
                    id=row["id"],
                    task_id=row["task_id"],
                    timestamp=parse_datetime(row["timestamp"]),
                    user_name=row["user_name"] or "",
                    user_id=row["user_id"],
                    user_level=row["user_level"],
                    content=row["content"] or "",
                )
            )

        for row in analysis_rows:
            db.merge(
                DanmakuAnalysis(
                    id=row["id"],
                    danmaku_id=row["danmaku_id"],
                    task_id=row["task_id"],
                    sentiment_score=row["sentiment_score"],
                    intent_score=row["intent_score"],
                    keywords=row["keywords"],
                )
            )

        for row in interaction_rows:
            db.merge(
                InteractionEvent(
                    id=row["id"],
                    task_id=row["task_id"],
                    timestamp=parse_datetime(row["timestamp"]),
                    user_name=row["user_name"] or "",
                    gift_name=row["gift_name"] or "",
                    gift_value=row["gift_value"] or 0.0,
                )
            )

        db.commit()
        reset_sequences(db)
        db.commit()

        print(
            "迁移完成: "
            f"event_tasks={len(event_rows)}, "
            f"live_metrics={len(metric_rows)}, "
            f"danmaku_records={len(danmaku_rows)}, "
            f"danmaku_analysis={len(analysis_rows)}, "
            f"interaction_events={len(interaction_rows)}"
        )
        return 0
    except Exception as exc:
        db.rollback()
        print(f"迁移失败: {exc}", file=sys.stderr)
        return 1
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
