"""内存任务队列 — 用于 Web 异步生成。"""

from __future__ import annotations

import threading
import time
import uuid
from typing import Any

from loguru import logger

_lock = threading.Lock()
_jobs: dict[str, dict[str, Any]] = {}


def create_job(kind: str, meta: dict[str, Any] | None = None) -> str:
    job_id = str(uuid.uuid4())
    now = time.time()
    with _lock:
        _jobs[job_id] = {
            "id": job_id,
            "kind": kind,
            "status": "pending",
            "created_at": now,
            "updated_at": now,
            "meta": meta or {},
            "result": None,
            "error": None,
        }
    logger.info("创建任务 job_id={} kind={}", job_id, kind)
    return job_id


def update_job(job_id: str, **fields: Any) -> None:
    with _lock:
        job = _jobs.get(job_id)
        if not job:
            return
        job.update(fields)
        job["updated_at"] = time.time()


def get_job(job_id: str) -> dict[str, Any] | None:
    with _lock:
        job = _jobs.get(job_id)
        return dict(job) if job else None


def list_jobs(limit: int = 20) -> list[dict[str, Any]]:
    with _lock:
        items = sorted(_jobs.values(), key=lambda j: j["updated_at"], reverse=True)
        return [dict(j) for j in items[:limit]]
