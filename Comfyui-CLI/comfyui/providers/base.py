"""Provider 抽象层。"""

from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any

from loguru import logger

from comfyui.config.schema import ComfyuiConfig
from comfyui.core.api import ComfyUIAPI, ComfyUIError


class Provider(ABC):
    @abstractmethod
    def run(self, workflow_data: dict[str, Any], params: dict[str, Any], output_dir: Path) -> list[Path]:
        ...


class LocalProvider(Provider):
    def __init__(self, api: ComfyUIAPI) -> None:
        self.api = api

    def run(self, workflow_data: dict[str, Any], params: dict[str, Any], output_dir: Path) -> list[Path]:
        from comfyui.core.prompt import build_prompt

        prompt = build_prompt(workflow_data, params)
        prompt_id = self.api.submit_workflow(prompt)
        self.api.wait_for_completion(prompt_id)
        files = self.api.get_output_files(prompt_id)
        if not files:
            raise ComfyUIError(f"未找到输出文件 prompt_id={prompt_id}")
        return [self.api.download_file(f, output_dir) for f in files]


class RunningHubProvider(Provider):
    """RunningHub 云端工作流执行（数字人等）。"""

    def __init__(self, config: ComfyuiConfig) -> None:
        self.config = config
        rh = config.providers.runninghub
        if not rh.enabled or not rh.api_key:
            raise ComfyUIError("RunningHub 未启用，请配置 providers.runninghub.enabled 与 api_key")

    def run(self, workflow_data: dict[str, Any], params: dict[str, Any], output_dir: Path) -> list[Path]:
        workflow_id = workflow_data.get("workflow_id")
        if not workflow_id:
            raise ComfyUIError("RunningHub 工作流缺少 workflow_id")

        # 桩实现：记录参数并提示用户配置 API
        logger.warning(
            "RunningHub 执行 workflow_id={} params={} — 需配置 RUNNINGHUB_API_KEY 后接入完整 API",
            workflow_id,
            list(params.keys()),
        )
        raise ComfyUIError(
            f"RunningHub 云端工作流 {workflow_id} 尚未接入完整 API。"
            "请设置 providers.runninghub.enabled=true 与 RUNNINGHUB_API_KEY，"
            "或换用本地 ComfyUI 工作流。"
        )


def get_provider(source: str, config: ComfyuiConfig, api: ComfyUIAPI) -> Provider:
    if source == "runninghub":
        return RunningHubProvider(config)
    return LocalProvider(api)
