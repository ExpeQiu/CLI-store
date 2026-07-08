"""VplatformCore — 统一入口。"""

from __future__ import annotations

from pathlib import Path

from loguru import logger

from vplatform._version import __version__
from vplatform.config.manager import ConfigManager, get_project_root
from vplatform.config.schema import VplatformConfig
from vplatform.pipelines.storyboard import StoryboardPipeline
from vplatform.services.comfyui import ComfyUIService
from vplatform.tasks.manager import TaskManager


class VplatformCore:
    def __init__(self, root: Path | None = None) -> None:
        self.root = root or get_project_root()
        self.config_manager = ConfigManager(self.root)
        self.config: VplatformConfig = self.config_manager.load()
        self.tasks = TaskManager(log_dir=self.root / self.config.tasks.log_dir)
        self.comfyui = ComfyUIService(
            root=self.root,
            endpoint=self.config.comfyui.endpoint,
            timeout_sec=self.config.comfyui.timeout_sec,
            poll_interval=self.config.comfyui.poll_interval_sec,
        )
        logger.debug("VplatformCore 初始化 root={}", self.root)

    def health(self) -> dict:
        return {
            "vplatform_root": str(self.root),
            "version": __version__,
            "comfyui": self.comfyui.health(),
            "workflows": __import__(
                "vplatform.workflows.registry", fromlist=["WorkflowRegistry"]
            ).WorkflowRegistry(self.root).list_workflows(),
        }

    def reload_config(self) -> VplatformConfig:
        self.config = self.config_manager.load(reload=True)
        self.comfyui = ComfyUIService(
            root=self.root,
            endpoint=self.config.comfyui.endpoint,
            timeout_sec=self.config.comfyui.timeout_sec,
            poll_interval=self.config.comfyui.poll_interval_sec,
        )
        return self.config

    def pipeline(self) -> StoryboardPipeline:
        return StoryboardPipeline(
            root=self.root,
            config=self.config,
            tasks=self.tasks,
            comfyui=self.comfyui,
        )

    def run_pipeline(
        self,
        subject: str = "",
        stop_at: str | None = None,
        profile: str | None = None,
        storyboard_file: str | None = None,
        task_id: str | None = None,
    ):
        return self.pipeline().run(
            subject=subject,
            stop_at=stop_at or self.config.pipeline.stop_at_default,
            profile=profile or self.config.comfyui.default_profile,
            storyboard_file=storyboard_file,
            task_id=task_id,
        )
