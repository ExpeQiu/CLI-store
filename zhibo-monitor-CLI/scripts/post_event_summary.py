from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from sqlalchemy import distinct, func

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.append(str(PROJECT_ROOT))

from app.core.database import SessionLocal  # noqa: E402
from app.models.schema import DanmakuRecord, EventTask, LiveMetric  # noqa: E402


def _format_dt(value: datetime | None) -> str:
    if value is None:
        return "-"
    return value.strftime("%Y-%m-%d %H:%M:%S")


def _safe_int(value: Any) -> int:
    return int(value or 0)


def _safe_float(value: Any) -> float:
    return float(value or 0.0)


@dataclass
class SummaryResult:
    task_id: int
    platform: str
    room_id: str
    event_name: str
    car_brand: str
    status: str
    task_start_time: str
    last_data_time: str
    danmaku_total: int
    unique_users: int
    first_danmaku_time: str
    last_danmaku_time: str
    heat_peak: int
    heat_peak_time: str
    heat_average: float
    heat_samples: int
    first_metric_time: str
    last_metric_time: str


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="赛后快速导出单场发布会基础统计")
    parser.add_argument("--task-id", type=int, help="按任务 ID 查询")
    parser.add_argument("--event-name", help="按发布会名称查询，默认取最新一条")
    parser.add_argument("--room-id", help="按房间号查询，默认取最新一条")
    parser.add_argument(
        "--json",
        action="store_true",
        help="以 JSON 格式输出，方便后续接脚本或导出",
    )
    return parser


def _select_task(args: argparse.Namespace) -> EventTask | None:
    db = SessionLocal()
    try:
        query = db.query(EventTask)

        if args.task_id is not None:
            return query.filter(EventTask.id == args.task_id).first()

        if args.event_name:
            query = query.filter(EventTask.event_name == args.event_name)

        if args.room_id:
            query = query.filter(EventTask.room_id == args.room_id)

        return query.order_by(EventTask.start_time.desc(), EventTask.id.desc()).first()
    finally:
        db.close()


def _collect_summary(task: EventTask) -> SummaryResult:
    db = SessionLocal()
    try:
        danmaku_total, unique_users, first_danmaku_time, last_danmaku_time = db.query(
            func.count(DanmakuRecord.id),
            func.count(distinct(DanmakuRecord.user_name)),
            func.min(DanmakuRecord.timestamp),
            func.max(DanmakuRecord.timestamp),
        ).filter(DanmakuRecord.task_id == task.id).one()

        heat_peak_row = (
            db.query(LiveMetric.online_count, LiveMetric.timestamp)
            .filter(LiveMetric.task_id == task.id)
            .order_by(LiveMetric.online_count.desc(), LiveMetric.timestamp.asc())
            .first()
        )

        heat_average, heat_samples, first_metric_time, last_metric_time = db.query(
            func.avg(LiveMetric.online_count),
            func.count(LiveMetric.id),
            func.min(LiveMetric.timestamp),
            func.max(LiveMetric.timestamp),
        ).filter(LiveMetric.task_id == task.id).one()

        last_data_time = max(
            [dt for dt in [last_danmaku_time, last_metric_time, task.end_time, task.start_time] if dt],
            default=None,
        )

        return SummaryResult(
            task_id=task.id,
            platform=task.platform,
            room_id=task.room_id,
            event_name=task.event_name,
            car_brand=task.car_brand,
            status=task.status,
            task_start_time=_format_dt(task.start_time),
            last_data_time=_format_dt(last_data_time),
            danmaku_total=_safe_int(danmaku_total),
            unique_users=_safe_int(unique_users),
            first_danmaku_time=_format_dt(first_danmaku_time),
            last_danmaku_time=_format_dt(last_danmaku_time),
            heat_peak=_safe_int(heat_peak_row[0] if heat_peak_row else 0),
            heat_peak_time=_format_dt(heat_peak_row[1] if heat_peak_row else None),
            heat_average=round(_safe_float(heat_average), 2),
            heat_samples=_safe_int(heat_samples),
            first_metric_time=_format_dt(first_metric_time),
            last_metric_time=_format_dt(last_metric_time),
        )
    finally:
        db.close()


def _print_text(summary: SummaryResult) -> None:
    print("=== 赛后快速统计 ===")
    print(f"任务 ID: {summary.task_id}")
    print(f"发布会: {summary.event_name}")
    print(f"平台: {summary.platform}")
    print(f"品牌: {summary.car_brand}")
    print(f"房间号: {summary.room_id}")
    print(f"状态: {summary.status}")
    print(f"任务开始: {summary.task_start_time}")
    print(f"最后数据时间: {summary.last_data_time}")
    print("")
    print("互动概览")
    print(f"- 弹幕总量: {summary.danmaku_total}")
    print(f"- 独立发言用户数: {summary.unique_users}")
    print(f"- 首条弹幕时间: {summary.first_danmaku_time}")
    print(f"- 末条弹幕时间: {summary.last_danmaku_time}")
    print("")
    print("热度概览")
    print(f"- 热度峰值: {summary.heat_peak}")
    print(f"- 峰值出现时间: {summary.heat_peak_time}")
    print(f"- 平均热度: {summary.heat_average}")
    print(f"- 热度采样点数: {summary.heat_samples}")
    print(f"- 首个热度采样时间: {summary.first_metric_time}")
    print(f"- 最后热度采样时间: {summary.last_metric_time}")


def main() -> int:
    parser = _build_parser()
    args = parser.parse_args()

    task = _select_task(args)
    if task is None:
        print("未找到符合条件的发布会任务，请先检查 task_id、event_name 或 room_id。", file=sys.stderr)
        return 1

    summary = _collect_summary(task)

    if args.json:
        print(json.dumps(asdict(summary), ensure_ascii=False, indent=2))
    else:
        _print_text(summary)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
