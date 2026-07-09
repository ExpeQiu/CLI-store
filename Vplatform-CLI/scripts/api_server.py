#!/usr/bin/env python3
"""Vplatform-CLI 轻量 REST API + Web 控制台。"""

from __future__ import annotations

import os
import sys
import threading
from pathlib import Path
from typing import Any

from loguru import logger

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from fastapi import BackgroundTasks, FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from uvicorn import run as uvicorn_run

from vplatform.core import VplatformCore
from vplatform.models.task import STOP_AT_STAGES, TaskRecord

app = FastAPI(title="Vplatform-CLI API", version="2.1.0")
_core: VplatformCore | None = None
_core_lock = threading.Lock()

WEB_DIR = PROJECT_ROOT / "web"
OUTPUTS_DIR = PROJECT_ROOT / "outputs"
OUTPUTS_DIR.mkdir(parents=True, exist_ok=True)


@app.get("/", include_in_schema=False)
def index_page() -> FileResponse:
    page = WEB_DIR / "index.html"
    if not page.exists():
        raise HTTPException(404, "web/index.html 不存在")
    return FileResponse(page)


def get_core() -> VplatformCore:
    global _core
    with _core_lock:
        if _core is None:
            _core = VplatformCore()
            logger.info("VplatformCore 已加载 root={}", _core.root)
        return _core


class PipelineRequest(BaseModel):
    subject: str = ""
    stop_at: str = Field(default="final")
    profile: str | None = None
    storyboard_file: str | None = None
    task_id: str | None = None


def _task_payload(record: TaskRecord) -> dict[str, Any]:
    return record.model_dump()


def _run_pipeline_job(payload: PipelineRequest) -> None:
    core = get_core()
    try:
        logger.info(
            "后台流水线启动 task_id={} stop_at={} subject={}",
            payload.task_id,
            payload.stop_at,
            payload.subject[:80],
        )
        core.run_pipeline(
            subject=payload.subject,
            stop_at=payload.stop_at,
            profile=payload.profile,
            storyboard_file=payload.storyboard_file,
            task_id=payload.task_id,
        )
        logger.info("后台流水线完成 task_id={}", payload.task_id)
    except Exception as exc:  # noqa: BLE001 — 后台任务需落盘错误
        logger.exception("后台流水线失败 task_id={}", payload.task_id)
        if payload.task_id:
            core.tasks.update(payload.task_id, error=str(exc))


@app.get("/api/v1/health")
def health() -> dict[str, Any]:
    return get_core().health()


@app.post("/api/v1/pipeline")
def pipeline_async(body: PipelineRequest, background: BackgroundTasks) -> dict[str, Any]:
    if body.stop_at not in STOP_AT_STAGES:
        raise HTTPException(400, f"无效 stop_at: {body.stop_at}")

    core = get_core()
    record = core.tasks.create(subject=body.subject, stop_at=body.stop_at)
    record.output_dir = str(PROJECT_ROOT / "outputs" / record.task_id)
    Path(record.output_dir).mkdir(parents=True, exist_ok=True)
    core.tasks._persist(record)

    job = PipelineRequest(
        subject=body.subject,
        stop_at=body.stop_at,
        profile=body.profile,
        storyboard_file=body.storyboard_file,
        task_id=record.task_id,
    )
    background.add_task(_run_pipeline_job, job)
    logger.info("任务已入队 task_id={}", record.task_id)
    return {"task_id": record.task_id, "status": "queued"}


@app.post("/api/v1/pipeline/sync")
def pipeline_sync(body: PipelineRequest) -> dict[str, Any]:
    if body.stop_at not in STOP_AT_STAGES:
        raise HTTPException(400, f"无效 stop_at: {body.stop_at}")

    core = get_core()
    record = core.run_pipeline(
        subject=body.subject,
        stop_at=body.stop_at,
        profile=body.profile,
        storyboard_file=body.storyboard_file,
        task_id=body.task_id,
    )
    return _task_payload(record)


@app.get("/api/v1/tasks/{task_id}")
def get_task(task_id: str) -> dict[str, Any]:
    core = get_core()
    record = core.tasks.get(task_id) or core.tasks.load_persisted(task_id)
    if not record:
        raise HTTPException(404, f"任务不存在: {task_id}")
    return _task_payload(record)


app.mount("/outputs", StaticFiles(directory=str(OUTPUTS_DIR)), name="outputs")


def main() -> None:
    host = os.getenv("VPLATFORM_API_HOST", "127.0.0.1")
    port = int(os.getenv("VPLATFORM_API_PORT", "8768"))
    print(f"[Vplatform-CLI] 控制台 http://{host}:{port}/")
    print(f"[Vplatform-CLI] API 文档 http://{host}:{port}/docs")
    uvicorn_run(app, host=host, port=port, log_level=os.getenv("LOG_LEVEL", "info").lower())


if __name__ == "__main__":
    main()
