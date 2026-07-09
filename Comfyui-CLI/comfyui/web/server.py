"""FastAPI Web 服务 — 封装 ComfyUIService 供前端调用。"""

from __future__ import annotations

import os
import shutil
import tempfile
import threading
import time
from pathlib import Path
from typing import Any

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from loguru import logger
from pydantic import BaseModel, Field
from starlette.concurrency import run_in_threadpool

from comfyui.config.manager import get_config
from comfyui.config.root import resolve_comfyui_root
from comfyui.core.service import ComfyUIService
from comfyui.web.jobs import create_job, get_job, list_jobs, update_job

_WORKFLOW_CACHE: dict[str, Any] = {"at": 0.0, "data": None}
_WORKFLOW_CACHE_TTL = 60.0


class T2IRequest(BaseModel):
    prompt: str = Field(..., min_length=1)
    negative_prompt: str = ""
    workflow: str | None = None
    profile: str | None = None
    width: int | None = None
    height: int | None = None
    steps: int | None = None
    seed: int | None = None


class T2VRequest(BaseModel):
    prompt: str = Field(..., min_length=1)
    negative_prompt: str = ""
    workflow: str | None = None
    profile: str | None = None
    length: int | None = None


class RunRequest(BaseModel):
    workflow: str = Field(..., min_length=1)
    params: dict[str, Any] = Field(default_factory=dict)
    profile: str | None = None


def _build_service(root: Path | None = None) -> ComfyUIService:
    resolved = resolve_comfyui_root(explicit=root)
    config = get_config(resolved, reload=True)
    return ComfyUIService(resolved, config)


def _public_base_url(request: Request | None = None) -> str:
    env_url = os.environ.get("COMFYUI_CLI_PUBLIC_URL", "").rstrip("/")
    if env_url:
        return env_url
    if request is not None:
        return str(request.base_url).rstrip("/")
    return "http://127.0.0.1:8765"


def _output_url(path: str, root: Path) -> str:
    p = Path(path).resolve()
    try:
        rel = p.relative_to((root / "outputs").resolve())
        return f"/outputs/{rel.as_posix()}"
    except ValueError:
        return f"/outputs/{p.name}"


def _enrich_result(
    result: dict[str, Any],
    root: Path,
    base_url: str = "http://127.0.0.1:8765",
) -> dict[str, Any]:
    outputs = result.get("outputs", [])
    output_urls = [_output_url(p, root) for p in outputs]
    result["output_urls"] = output_urls
    result["output_absolute_urls"] = [f"{base_url.rstrip('/')}{url}" for url in output_urls]
    return result


def _run_job(job_id: str, fn, *args, base_url: str = "http://127.0.0.1:8765", **kwargs) -> None:
    service = kwargs.pop("_service")
    try:
        update_job(job_id, status="running")
        result = fn(*args, **kwargs)
        result = _enrich_result(result, service.root, base_url)
        update_job(job_id, status="completed", result=result)
        logger.info("任务完成 job_id={}", job_id)
    except Exception as exc:  # noqa: BLE001
        logger.exception("任务失败 job_id={}", job_id)
        update_job(job_id, status="failed", error=str(exc))


def _start_job_thread(
    job_id: str,
    fn,
    *args,
    base_url: str = "http://127.0.0.1:8765",
    **kwargs,
) -> None:
    """在独立线程执行生成任务，避免阻塞 Web 请求。"""
    thread = threading.Thread(
        target=_run_job,
        args=(job_id, fn, *args),
        kwargs={**kwargs, "base_url": base_url},
        daemon=True,
        name=f"comfyui-job-{job_id[:8]}",
    )
    thread.start()


def _list_workflows_cached(service: ComfyUIService, category: str | None = None) -> dict[str, Any]:
    now = time.time()
    if _WORKFLOW_CACHE["data"] and now - _WORKFLOW_CACHE["at"] < _WORKFLOW_CACHE_TTL:
        data = _WORKFLOW_CACHE["data"]
    else:
        items = []
        for name in service.registry.list_workflows():
            info = service.registry.inspect(name)
            ready, detail = service.workflow_status(name)
            items.append({**info, "ready": ready, **detail})
        data = {"root": str(service.root), "workflows": items}
        _WORKFLOW_CACHE["at"] = now
        _WORKFLOW_CACHE["data"] = data
        logger.debug("工作流缓存已刷新 count={}", len(items))

    if not category:
        return data
    filtered = [w for w in data["workflows"] if w.get("category") == category]
    return {"root": data["root"], "workflows": filtered}


def _t2i_kwargs(body: T2IRequest) -> dict[str, Any]:
    kwargs: dict[str, Any] = {}
    if body.width is not None:
        kwargs["width"] = body.width
    if body.height is not None:
        kwargs["height"] = body.height
    if body.steps is not None:
        kwargs["steps"] = body.steps
    if body.seed is not None:
        kwargs["seed"] = body.seed
    return kwargs


def create_app(root: Path | None = None) -> FastAPI:
    resolved = resolve_comfyui_root(explicit=root)
    static_dir = resolved / "web" / "static"
    outputs_dir = resolved / "outputs"
    outputs_dir.mkdir(parents=True, exist_ok=True)

    app = FastAPI(
        title="Comfyui-CLI Web",
        description="ComfyUI 图片/视频生成简易 Web 界面",
        version="0.2.0",
    )
    app.state.root = resolved
    app.state.service = _build_service(resolved)

    @app.get("/api/ping")
    async def api_ping() -> dict[str, str]:
        return {"ok": "true", "service": "comfyui-cli-web"}

    @app.get("/api/health")
    async def api_health(full: bool = False) -> dict[str, Any]:
        service: ComfyUIService = app.state.service
        if full:
            return await run_in_threadpool(service.health)
        return await run_in_threadpool(service.health_lite)

    @app.get("/api/workflows")
    async def api_workflows(category: str | None = None) -> dict[str, Any]:
        service: ComfyUIService = app.state.service
        return await run_in_threadpool(_list_workflows_cached, service, category)

    @app.get("/api/workflows/{workflow_name}")
    async def api_workflow_detail(workflow_name: str) -> dict[str, Any]:
        service: ComfyUIService = app.state.service
        try:
            info = service.registry.inspect(workflow_name)
            ready, detail = await run_in_threadpool(service.workflow_status, workflow_name)
            return {"workflow": {**info, "ready": ready, **detail}}
        except FileNotFoundError as exc:
            raise HTTPException(status_code=404, detail=f"工作流不存在: {workflow_name}") from exc

    @app.get("/api/workflows/{workflow_name}/validate")
    async def api_workflow_validate(workflow_name: str) -> dict[str, Any]:
        service: ComfyUIService = app.state.service
        try:
            ready, detail = await run_in_threadpool(service.workflow_status, workflow_name)
            return {"workflow": workflow_name, "ready": ready, **detail}
        except FileNotFoundError as exc:
            raise HTTPException(status_code=404, detail=f"工作流不存在: {workflow_name}") from exc

    @app.get("/api/config")
    async def api_config() -> dict[str, Any]:
        service: ComfyUIService = app.state.service
        cfg = service.config
        return {
            "endpoint": cfg.comfyui.endpoint,
            "default_profile": cfg.comfyui.default_profile,
            "profiles": {k: dict(v) for k, v in cfg.profiles.items()},
            "capabilities": cfg.capabilities.model_dump(),
        }

    @app.get("/api/jobs")
    async def api_jobs() -> dict[str, Any]:
        return {"jobs": list_jobs()}

    @app.get("/api/jobs/{job_id}")
    async def api_job(job_id: str) -> dict[str, Any]:
        job = get_job(job_id)
        if not job:
            raise HTTPException(status_code=404, detail="任务不存在")
        return job

    @app.post("/api/image/t2i")
    async def api_t2i(body: T2IRequest, request: Request) -> dict[str, Any]:
        service: ComfyUIService = app.state.service
        base_url = _public_base_url(request)
        job_id = create_job("t2i", {"prompt": body.prompt[:80]})
        _start_job_thread(
            job_id,
            service.t2i,
            body.prompt,
            output_dir=service.root / service.config.output_dir,
            negative_prompt=body.negative_prompt or None,
            workflow_name=body.workflow,
            profile_name=body.profile,
            _service=service,
            base_url=base_url,
            **_t2i_kwargs(body),
        )
        return {"job_id": job_id, "status": "pending"}

    @app.post("/api/image/i2i")
    async def api_i2i(
        request: Request,
        image: UploadFile = File(...),
        prompt: str = Form(...),
        negative_prompt: str = Form(""),
        workflow: str | None = Form(None),
        profile: str | None = Form(None),
        steps: int | None = Form(None),
        seed: int | None = Form(None),
        denoise: float | None = Form(None),
    ) -> dict[str, Any]:
        service: ComfyUIService = app.state.service
        base_url = _public_base_url(request)
        suffix = Path(image.filename or "upload.png").suffix or ".png"
        tmp_dir = Path(tempfile.mkdtemp(prefix="comfyui_web_i2i_"))
        tmp_path = tmp_dir / f"input{suffix}"
        try:
            with tmp_path.open("wb") as f:
                shutil.copyfileobj(image.file, f)
        except Exception as exc:
            shutil.rmtree(tmp_dir, ignore_errors=True)
            raise HTTPException(status_code=400, detail=f"图片上传失败: {exc}") from exc

        job_id = create_job("i2i", {"prompt": prompt[:80]})
        extra: dict[str, Any] = {}
        if steps is not None:
            extra["steps"] = steps
        if seed is not None:
            extra["seed"] = seed
        if denoise is not None:
            extra["denoise"] = denoise

        def _run_i2i() -> None:
            try:
                _run_job(
                    job_id,
                    service.i2i,
                    tmp_path,
                    prompt,
                    output_dir=service.root / service.config.output_dir,
                    negative_prompt=negative_prompt or None,
                    workflow_name=workflow,
                    profile_name=profile,
                    _service=service,
                    base_url=base_url,
                    **extra,
                )
            finally:
                shutil.rmtree(tmp_dir, ignore_errors=True)

        threading.Thread(target=_run_i2i, daemon=True, name=f"comfyui-job-{job_id[:8]}").start()
        return {"job_id": job_id, "status": "pending"}

    @app.post("/api/video/t2v")
    async def api_t2v(body: T2VRequest, request: Request) -> dict[str, Any]:
        service: ComfyUIService = app.state.service
        base_url = _public_base_url(request)
        job_id = create_job("t2v", {"prompt": body.prompt[:80]})
        kwargs: dict[str, Any] = {}
        if body.length:
            kwargs["length"] = body.length
        _start_job_thread(
            job_id,
            service.t2v,
            body.prompt,
            output_dir=service.root / service.config.output_dir,
            negative_prompt=body.negative_prompt or None,
            workflow_name=body.workflow,
            profile_name=body.profile,
            _service=service,
            base_url=base_url,
            **kwargs,
        )
        return {"job_id": job_id, "status": "pending"}

    @app.post("/api/video/i2v")
    async def api_i2v(
        request: Request,
        image: UploadFile = File(...),
        prompt: str = Form(...),
        negative_prompt: str = Form(""),
        workflow: str | None = Form(None),
        profile: str | None = Form(None),
        duration: float | None = Form(None),
        length: int | None = Form(None),
    ) -> dict[str, Any]:
        service: ComfyUIService = app.state.service
        base_url = _public_base_url(request)
        suffix = Path(image.filename or "upload.png").suffix or ".png"
        tmp_dir = Path(tempfile.mkdtemp(prefix="comfyui_web_"))
        tmp_path = tmp_dir / f"input{suffix}"
        try:
            with tmp_path.open("wb") as f:
                shutil.copyfileobj(image.file, f)
        except Exception as exc:
            shutil.rmtree(tmp_dir, ignore_errors=True)
            raise HTTPException(status_code=400, detail=f"图片上传失败: {exc}") from exc

        job_id = create_job("i2v", {"prompt": prompt[:80]})

        def _run_i2v() -> None:
            try:
                _run_job(
                    job_id,
                    service.i2v,
                    tmp_path,
                    prompt,
                    output_dir=service.root / service.config.output_dir,
                    negative_prompt=negative_prompt or None,
                    duration_sec=duration,
                    workflow_name=workflow,
                    profile_name=profile,
                    length=length,
                    _service=service,
                    base_url=base_url,
                )
            finally:
                shutil.rmtree(tmp_dir, ignore_errors=True)

        threading.Thread(target=_run_i2v, daemon=True, name=f"comfyui-job-{job_id[:8]}").start()
        return {"job_id": job_id, "status": "pending"}

    @app.post("/api/run")
    async def api_run(body: RunRequest, request: Request) -> dict[str, Any]:
        service: ComfyUIService = app.state.service
        base_url = _public_base_url(request)
        job_id = create_job("run", {"workflow": body.workflow})
        _start_job_thread(
            job_id,
            service.run,
            body.workflow,
            params=body.params,
            output_dir=service.root / service.config.output_dir,
            profile_name=body.profile,
            _service=service,
            base_url=base_url,
        )
        return {"job_id": job_id, "status": "pending"}

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(_request, exc: Exception) -> JSONResponse:
        logger.exception("未处理异常: {}", exc)
        return JSONResponse(status_code=500, content={"detail": str(exc)})

    app.mount("/outputs", StaticFiles(directory=str(outputs_dir)), name="outputs")
    if static_dir.is_dir():
        app.mount("/", StaticFiles(directory=str(static_dir), html=True), name="static")
    else:
        logger.warning("静态目录不存在: {}", static_dir)

    return app
