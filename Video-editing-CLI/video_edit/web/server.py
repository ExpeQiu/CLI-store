"""FastAPI Web 服务 — A-Roll 初剪 API。"""

from __future__ import annotations

import os
import shutil
import threading
import time
from pathlib import Path
from typing import Any

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from loguru import logger
from starlette.concurrency import run_in_threadpool

from video_edit.config import load_config
from video_edit.pipelines.aroll import run_aroll_pipeline
from video_edit.web.jobs import create_job, get_job, list_jobs, update_job

STAGES = ["extract", "transcribe", "align", "refine", "export"]
STAGE_PROGRESS = {
    "extract": 10,
    "transcribe": 30,
    "align": 55,
    "refine": 75,
    "export": 95,
}


def _public_base_url(request: Request | None = None) -> str:
    env_url = os.environ.get("VIDEO_EDIT_PUBLIC_URL", "").rstrip("/")
    if env_url:
        return env_url
    if request is not None:
        return str(request.base_url).rstrip("/")
    return "http://127.0.0.1:8766"


def _output_url(path: Path, root: Path) -> str:
    try:
        rel = path.resolve().relative_to(root.resolve())
        return f"/outputs/{rel.as_posix()}"
    except ValueError:
        return f"/outputs/{path.name}"


def _run_aroll_job(
    job_id: str,
    video_path: Path,
    script_path: Path,
    output_root: Path,
    stop_at: str | None,
    demo: bool,
) -> None:
    config = load_config()
    try:
        update_job(job_id, status="running", stage="extract", progress=5)

        def _progress_hook(stage: str) -> None:
            update_job(
                job_id,
                stage=stage,
                progress=STAGE_PROGRESS.get(stage, 50),
            )

        for stage in STAGES:
            if stop_at == stage:
                break
            _progress_hook(stage)

        result = run_aroll_pipeline(
            video=video_path if not demo else None,
            script=script_path if not demo else None,
            output_dir=output_root,
            config=config,
            demo=demo,
            stop_at=stop_at,
        )

        outputs: dict[str, Any] = {
            "job_id": result.job_id,
            "output_dir": str(result.output_dir),
            "summary": result.summary,
        }
        root = output_root.parent if output_root.name == "jobs" else output_root
        if result.transcript_path:
            outputs["transcript"] = str(result.transcript_path)
            outputs["transcript_url"] = _output_url(result.transcript_path, root)
        if result.decisions_path:
            outputs["decisions"] = str(result.decisions_path)
            outputs["decisions_url"] = _output_url(result.decisions_path, root)
        for fmt, path in result.exports.items():
            outputs[fmt] = str(path)
            outputs[f"{fmt}_url"] = _output_url(path, root)
        if result.sync_map_path:
            outputs["sync_map"] = str(result.sync_map_path)
            outputs["sync_map_url"] = _output_url(result.sync_map_path, root)

        update_job(
            job_id,
            status="completed",
            progress=100,
            stage="done",
            result=outputs,
        )
        logger.info("A-Roll 任务完成 job_id={}", job_id)
    except Exception as exc:
        logger.exception("A-Roll 任务失败 job_id={}", job_id)
        update_job(job_id, status="failed", error=str(exc), stage="error")


def create_app() -> FastAPI:
    root = Path(os.environ.get("VIDEO_EDIT_ROOT", Path.cwd())).resolve()
    outputs_dir = root / "outputs"
    uploads_dir = root / "uploads"
    outputs_dir.mkdir(parents=True, exist_ok=True)
    uploads_dir.mkdir(parents=True, exist_ok=True)

    app = FastAPI(title="Video-editing-CLI Web API", version="0.3.0")
    app.mount("/outputs", StaticFiles(directory=str(outputs_dir)), name="outputs")

    @app.get("/api/ping")
    async def ping():
        return {"ok": True, "service": "video-edit-cli"}

    @app.get("/api/health")
    async def health():
        status: dict[str, Any] = {"healthy": True, "root": str(root)}
        try:
            from video_edit.services.audio import require_ffmpeg

            require_ffmpeg()
            status["ffmpeg"] = "ok"
        except Exception as exc:
            status["ffmpeg"] = str(exc)
            status["healthy"] = False
        try:
            import faster_whisper  # noqa: F401

            status["faster_whisper"] = "ok"
        except ImportError:
            status["faster_whisper"] = "missing"
        try:
            import whisperx  # noqa: F401

            status["whisperx"] = "ok"
        except ImportError:
            status["whisperx"] = "missing"
        return status

    @app.get("/api/jobs")
    async def jobs_list(limit: int = 20):
        return {"jobs": list_jobs(limit=limit)}

    @app.get("/api/jobs/{job_id}")
    async def jobs_get(job_id: str, request: Request):
        job = get_job(job_id)
        if not job:
            raise HTTPException(status_code=404, detail="任务不存在")
        base = _public_base_url(request)
        result = job.get("result") or {}
        if result.get("fcpxml_url"):
            result["fcpxml_absolute_url"] = f"{base}{result['fcpxml_url']}"
        if result.get("decisions_url"):
            result["decisions_absolute_url"] = f"{base}{result['decisions_url']}"
        job = dict(job)
        job["result"] = result
        return job

    @app.post("/api/aroll/run")
    async def aroll_run(
        request: Request,
        video: UploadFile | None = File(None),
        script: UploadFile | None = File(None),
        script_text: str | None = Form(None),
        demo: bool = Form(False),
        stop_at: str | None = Form(None),
    ):
        if stop_at and stop_at not in STAGES:
            raise HTTPException(status_code=400, detail=f"stop_at 必须是 {STAGES} 之一")

        job_id = create_job("aroll", meta={"demo": demo, "stop_at": stop_at})
        work_dir = uploads_dir / "jobs" / job_id
        work_dir.mkdir(parents=True, exist_ok=True)

        if demo:
            thread = threading.Thread(
                target=_run_aroll_job,
                args=(job_id, work_dir / "dummy.mp4", work_dir / "script.txt", outputs_dir / "jobs", stop_at, True),
                daemon=True,
            )
            thread.start()
            return {"job_id": job_id, "status": "pending", "demo": True}

        if not video:
            raise HTTPException(status_code=400, detail="需要上传 video 或使用 demo=true")
        if not script and not script_text:
            raise HTTPException(status_code=400, detail="需要 script 文件或 script_text")

        video_path = work_dir / (video.filename or "source.mp4")
        with video_path.open("wb") as f:
            shutil.copyfileobj(video.file, f)

        script_path = work_dir / "script.txt"
        if script:
            with script_path.open("wb") as f:
                shutil.copyfileobj(script.file, f)
        else:
            script_path.write_text(script_text or "", encoding="utf-8")

        thread = threading.Thread(
            target=_run_aroll_job,
            args=(job_id, video_path, script_path, outputs_dir / "jobs", stop_at, False),
            daemon=True,
        )
        thread.start()
        return {"job_id": job_id, "status": "pending"}

    @app.get("/api/jobs/{job_id}/download/{kind}")
    async def download_artifact(job_id: str, kind: str):
        job = get_job(job_id)
        if not job or job.get("status") != "completed":
            raise HTTPException(status_code=404, detail="任务未完成或不存在")
        result = job.get("result") or {}
        key_map = {
            "fcpxml": "fcpxml",
            "edl": "edl",
            "decisions": "decisions",
            "transcript": "transcript",
            "srt": "srt",
            "jianying": "jianying",
            "sync_map": "sync_map",
        }
        path_key = key_map.get(kind)
        if not path_key:
            raise HTTPException(status_code=400, detail=f"未知类型: {kind}")
        file_path = result.get(path_key)
        if not file_path or not Path(file_path).is_file():
            raise HTTPException(status_code=404, detail="文件不存在")
        media_types = {
            "fcpxml": "application/xml",
            "edl": "text/plain",
            "decisions": "application/json",
            "transcript": "application/json",
            "srt": "text/plain",
            "jianying": "application/json",
            "sync_map": "application/json",
        }
        return FileResponse(
            file_path,
            media_type=media_types.get(kind, "application/octet-stream"),
            filename=Path(file_path).name,
        )

    return app
