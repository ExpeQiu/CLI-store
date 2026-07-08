"""内存任务注册表 + stop_at 支持。"""

from __future__ import annotations

import json
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from loguru import logger

from vplatform.models.task import STOP_AT_STAGES, TaskRecord, TaskStage


class TaskManager:
    def __init__(self, log_dir: Path | None = None) -> None:
        self._tasks: dict[str, TaskRecord] = {}
        self._lock = threading.Lock()
        self.log_dir = log_dir or Path("logs/tasks")
        self.log_dir.mkdir(parents=True, exist_ok=True)

    def create(
        self,
        subject: str = "",
        stop_at: str = "final",
        output_dir: str = "",
    ) -> TaskRecord:
        if stop_at not in STOP_AT_STAGES:
            raise ValueError(f"无效 stop_at: {stop_at}, 可选: {STOP_AT_STAGES}")

        task_id = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S") + "_" + uuid.uuid4().hex[:8]
        record = TaskRecord(
            task_id=task_id,
            subject=subject,
            stop_at=stop_at,
            output_dir=output_dir,
        )
        with self._lock:
            self._tasks[task_id] = record
        self._persist(record)
        logger.info("任务已创建 task_id={} stop_at={}", task_id, stop_at)
        return record

    def get(self, task_id: str) -> TaskRecord | None:
        with self._lock:
            return self._tasks.get(task_id)

    def list_tasks(self) -> list[TaskRecord]:
        with self._lock:
            return list(self._tasks.values())

    def update(
        self,
        task_id: str,
        *,
        stage: TaskStage | None = None,
        progress: float | None = None,
        outputs: dict[str, Any] | None = None,
        error: str | None = None,
    ) -> TaskRecord:
        with self._lock:
            record = self._tasks.get(task_id)
            if not record:
                raise KeyError(f"任务不存在: {task_id}")
            if stage is not None:
                record.stage = stage
            if progress is not None:
                record.progress = progress
            if outputs is not None:
                record.outputs.update(outputs)
            if error is not None:
                record.error = error
                record.stage = TaskStage.FAILED
            record.touch()

        self._persist(record)
        return record

    def cancel(self, task_id: str) -> TaskRecord:
        return self.update(task_id, stage=TaskStage.CANCELLED)

    def write_stage_log(self, task_id: str, stage: str, message: str) -> None:
        stage_dir = self.log_dir / task_id
        stage_dir.mkdir(parents=True, exist_ok=True)
        log_file = stage_dir / f"{stage}.log"
        ts = datetime.now(timezone.utc).isoformat()
        with log_file.open("a", encoding="utf-8") as f:
            f.write(f"[{ts}] {message}\n")
        logger.debug("stage_log task_id={} stage={} msg={}", task_id, stage, message[:120])

    def _persist(self, record: TaskRecord) -> None:
        path = self.log_dir / f"{record.task_id}.json"
        path.write_text(record.model_dump_json(indent=2), encoding="utf-8")

    def load_persisted(self, task_id: str) -> TaskRecord | None:
        path = self.log_dir / f"{task_id}.json"
        if not path.exists():
            return None
        record = TaskRecord.model_validate_json(path.read_text(encoding="utf-8"))
        with self._lock:
            self._tasks[task_id] = record
        return record
