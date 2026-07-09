"""数字人多步链编排。"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from loguru import logger

from comfyui.core.service import ComfyUIService


def run_lip_sync(
    service: ComfyUIService,
    portrait: Path,
    audio: Path,
    output_dir: Path | None = None,
    workflow_name: str | None = None,
) -> dict[str, Any]:
    """图 + 音频 → 口播视频（lip sync）。"""
    workflow = workflow_name or service.resolve_workflow_for_capability("digital", "lip_sync")
    workflow_data = service.registry.load(workflow)
    source = workflow_data.get("source", "local")

    if source == "runninghub":
        params = {
            "videoimage": str(portrait),
            "audio": str(audio),
        }
    else:
        uploaded = service.api.upload_image(portrait)
        params = {
            "image_name": uploaded,
            "audio_path": str(audio),
        }

    logger.info("数字人口播 workflow={} portrait={} audio={}", workflow, portrait, audio)
    return service.run_workflow(workflow, params, output_dir)


def run_pipeline(
    service: ComfyUIService,
    portrait: Path,
    script: str,
    product: Path | None = None,
    audio: Path | None = None,
    output_dir: Path | None = None,
) -> dict[str, Any]:
    """带货模式：拼图 → TTS(可选) → lip sync。"""
    steps: list[dict[str, Any]] = []

    compose_wf = service.resolve_workflow_for_capability("digital", "compose")
    compose_data = service.registry.load(compose_wf)
    if compose_data.get("source") == "runninghub":
        compose_params: dict[str, Any] = {
            "firstimage": str(portrait),
            "secondimage": str(product) if product else str(portrait),
            "goodstype": "product" if product else "portrait",
        }
    else:
        compose_params = {
            "positive_prompt": script,
            "image_name": service.api.upload_image(portrait),
        }

    logger.info("数字人 Step1 拼图 workflow={}", compose_wf)
    step1 = service.run_workflow(compose_wf, compose_params, output_dir)
    steps.append({"step": "compose", "result": step1})

    video_image = Path(step1["outputs"][0]) if step1.get("outputs") else portrait

    if audio is None:
        logger.warning("未提供音频，跳过 TTS；lip sync 需要 --audio 参数")
        return {"ok": False, "steps": steps, "error": "需要提供 --audio 或集成 TTS"}

    lip_result = run_lip_sync(service, video_image, audio, output_dir)
    steps.append({"step": "lip_sync", "result": lip_result})
    return {"ok": True, "steps": steps, "outputs": lip_result.get("outputs", [])}
