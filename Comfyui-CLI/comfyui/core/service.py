"""高层 ComfyUI 服务 — 工作流执行封装。"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any

from loguru import logger

from comfyui.config.schema import ComfyuiConfig
from comfyui.core.api import ComfyUIAPI, ComfyUIError, ProgressCallback
from comfyui.core.prompt import (
    build_prompt,
    check_required_nodes,
    load_workflow,
    merge_params,
    workflow_models_available,
)
from comfyui.core.registry import WorkflowRegistry
from comfyui.providers.base import get_provider


class ComfyUIService:
    def __init__(self, root: Path, config: ComfyuiConfig) -> None:
        self.root = root
        self.config = config
        self.registry = WorkflowRegistry(
            root,
            workflows_dir=config.workflows_dir,
            data_dir=config.data_workflows_dir,
        )
        self.api = ComfyUIAPI(
            endpoint=config.comfyui.endpoint,
            timeout=30,
            poll_interval=config.comfyui.poll_interval_sec,
        )
        self.timeout_sec = config.comfyui.timeout_sec

    def health_lite(self) -> dict[str, Any]:
        """轻量健康检查，仅探测 ComfyUI 连通性（供 Web 轮询）。"""
        ok = self.api.health_check()
        result: dict[str, Any] = {
            "endpoint": self.api.endpoint,
            "healthy": ok,
            "workflows_count": len(self.registry.list_workflows()),
        }
        if ok:
            try:
                result["devices"] = self.api.system_stats().get("devices", [])
            except ComfyUIError:
                result["healthy"] = False
        return result

    def health(self) -> dict[str, Any]:
        ok = self.api.health_check()
        result: dict[str, Any] = {"endpoint": self.api.endpoint, "healthy": ok}
        if ok:
            result["devices"] = self.api.system_stats().get("devices", [])
        workflows = []
        for name in self.registry.list_workflows():
            ready, detail = self.workflow_status(name)
            workflows.append({"name": name, "ready": ready, **detail})
        result["workflows"] = workflows
        return result

    def workflow_status(self, workflow_name: str) -> tuple[bool, dict[str, Any]]:
        workflow_data = load_workflow(self.registry.resolve(workflow_name))
        source = workflow_data.get("source", "local")
        if source == "runninghub":
            enabled = self.config.providers.runninghub.enabled
            return enabled, {
                "source": "runninghub",
                "workflow_id": workflow_data.get("workflow_id"),
                "cloud_enabled": enabled,
            }
        if not self.api.health_check():
            return False, {"source": "local", "comfyui_healthy": False}
        nodes_ok, missing_nodes = check_required_nodes(self.api, workflow_data)
        models_ok, missing_models = workflow_models_available(self.api, workflow_data)
        return nodes_ok and models_ok, {
            "source": "local",
            "comfyui_healthy": True,
            "missing_nodes": missing_nodes,
            "missing_models": missing_models,
        }

    def workflow_ready(self, workflow_name: str) -> bool:
        ready, _ = self.workflow_status(workflow_name)
        return ready

    def resolve_workflow_for_capability(self, category: str, capability: str) -> str:
        caps = self.config.capabilities
        if category == "image":
            mapping = caps.image.model_dump()
        elif category == "video":
            mapping = caps.video.model_dump()
        elif category == "digital":
            mapping = caps.digital.model_dump()
        else:
            raise ValueError(f"未知能力域: {category}")

        workflow_name = mapping.get(capability) or mapping.get("default")
        if not workflow_name:
            raise ValueError(f"未配置能力 {category}.{capability}")
        return workflow_name

    def run_workflow(
        self,
        workflow_name: str,
        params: dict[str, Any] | None = None,
        output_dir: Path | None = None,
        profile_name: str | None = None,
        on_progress: ProgressCallback | None = None,
    ) -> dict[str, Any]:
        workflow_data = load_workflow(self.registry.resolve(workflow_name))
        source = workflow_data.get("source", "local")
        profile = self._resolve_profile(profile_name)
        merged = merge_params(workflow_data, profile=profile, overrides=params or {})
        out_dir = output_dir or (self.root / self.config.output_dir)
        out_dir.mkdir(parents=True, exist_ok=True)

        start = time.time()
        provider = get_provider(source, self.config, self.api)

        if source == "runninghub":
            paths = provider.run(workflow_data, merged, out_dir)
            prompt_id = None
        else:
            prompt = build_prompt(workflow_data, merged)
            prompt_id = self.api.submit_workflow(prompt)
            self.api.wait_for_completion(
                prompt_id,
                timeout=self.timeout_sec,
                on_progress=on_progress,
            )
            files = self.api.get_output_files(prompt_id)
            output_nodes = workflow_data.get("output_nodes")
            if output_nodes:
                allowed = {str(n) for n in output_nodes}
                files = [f for f in files if str(f.get("node_id")) in allowed]
            if not files:
                raise ComfyUIError(f"未找到输出文件 prompt_id={prompt_id}")
            paths = [self.api.download_file(f, out_dir) for f in files]
            # 图片类工作流仅保留最后一张（SaveImage 多帧时取最终结果）
            if workflow_data.get("category") == "image" and len(paths) > 1:
                paths = [paths[-1]]

        duration = time.time() - start
        logger.info(
            "工作流完成 workflow={} duration={:.1f}s outputs={}",
            workflow_name,
            duration,
            [str(p) for p in paths],
        )
        return {
            "ok": True,
            "workflow": workflow_name,
            "prompt_id": prompt_id,
            "duration_sec": round(duration, 2),
            "outputs": [str(p) for p in paths],
            "params": merged,
        }

    def _resolve_profile(self, profile_name: str | None) -> dict[str, Any]:
        name = profile_name or self.config.comfyui.default_profile
        return dict(self.config.profiles.get(name, {}))

    def t2i(
        self,
        positive_prompt: str,
        output_dir: Path | None = None,
        negative_prompt: str | None = None,
        workflow_name: str | None = None,
        profile_name: str | None = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        workflow = workflow_name or self.resolve_workflow_for_capability("image", "t2i")
        workflow_data = load_workflow(self.registry.resolve(workflow))
        defaults = workflow_data.get("defaults", {})
        params = {
            "positive_prompt": positive_prompt,
            "negative_prompt": negative_prompt or defaults.get("negative_prompt", ""),
            **kwargs,
        }
        # 文生图固定单帧，避免 profile.length（视频用）导致一次输出多张图
        if "length" not in params:
            params["length"] = defaults.get("length", 1)
        return self.run_workflow(workflow, params, output_dir, profile_name)

    def t2v(
        self,
        positive_prompt: str,
        output_dir: Path | None = None,
        negative_prompt: str | None = None,
        workflow_name: str | None = None,
        profile_name: str | None = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        workflow = workflow_name or self.resolve_workflow_for_capability("video", "t2v")
        workflow_data = load_workflow(self.registry.resolve(workflow))
        defaults = workflow_data.get("defaults", {})
        params = {
            "positive_prompt": positive_prompt,
            "negative_prompt": negative_prompt or defaults.get("negative_prompt", ""),
            **kwargs,
        }
        return self.run_workflow(workflow, params, output_dir, profile_name)

    def i2v(
        self,
        image_path: str | Path,
        motion_prompt: str,
        output_dir: Path | None = None,
        negative_prompt: str | None = None,
        duration_sec: float | None = None,
        workflow_name: str | None = None,
        profile_name: str | None = None,
        fps: int | None = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        workflow = workflow_name or self.resolve_workflow_for_capability("video", "i2v")
        workflow_data = load_workflow(self.registry.resolve(workflow))
        defaults = workflow_data.get("defaults", {})
        fps_val = fps or self.config.capabilities.video.fps
        profile = self._resolve_profile(profile_name or self.config.comfyui.default_profile)
        length = kwargs.pop("length", None)
        if length is None:
            if duration_sec is not None:
                length = max(int(duration_sec * fps_val), 9)
            else:
                length = profile.get("length", defaults.get("length", 25))
            length = length + (length % 4)
            if length % 4 != 1:
                length += 1

        uploaded = self.api.upload_image(image_path)
        params = {
            "positive_prompt": motion_prompt,
            "negative_prompt": negative_prompt or defaults.get("negative_prompt", ""),
            "image_name": uploaded,
            "length": length,
            "fps": fps_val,
            **kwargs,
        }
        try:
            return self.run_workflow(workflow, params, output_dir, profile_name)
        except ComfyUIError:
            logger.warning("I2V 失败，降级为 T2V motion_prompt={}", motion_prompt[:60])
            combined = f"{motion_prompt}, based on keyframe image"
            return self.t2v(combined, output_dir, negative_prompt, profile_name=profile_name, **kwargs)

    def i2i(
        self,
        image_path: str | Path,
        positive_prompt: str,
        output_dir: Path | None = None,
        negative_prompt: str | None = None,
        workflow_name: str | None = None,
        profile_name: str | None = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """图生图 — 上传参考图后执行 i2i 工作流。"""
        workflow = workflow_name or self.resolve_workflow_for_capability("image", "i2i")
        workflow_data = load_workflow(self.registry.resolve(workflow))
        defaults = workflow_data.get("defaults", {})
        uploaded = self.api.upload_image(image_path)
        params = {
            "image_name": uploaded,
            "positive_prompt": positive_prompt,
            "negative_prompt": negative_prompt or defaults.get("negative_prompt", ""),
            **kwargs,
        }
        return self.run_workflow(workflow, params, output_dir, profile_name)

    def run(
        self,
        workflow_name: str,
        params: dict[str, Any] | None = None,
        output_dir: Path | None = None,
        profile_name: str | None = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """通用工作流执行（供 /api/run 与外部集成调用）。"""
        merged = {**(params or {}), **kwargs}
        return self.run_workflow(workflow_name, merged, output_dir, profile_name)
