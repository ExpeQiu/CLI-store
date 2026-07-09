"""Pydantic 配置 Schema。"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class LLMConfig(BaseModel):
    provider: str = "openai_compatible"
    base_url: str = ""
    api_key: str = ""
    model: str = "qwen-plus"


class ComfyUIConfig(BaseModel):
    endpoint: str = "http://127.0.0.1:8188"
    base_path: str = ""
    default_profile: str = "fast"
    timeout_sec: int = 1800
    poll_interval_sec: float = 5.0


class ProviderConfig(BaseModel):
    priority: list[str] = Field(default_factory=lambda: ["autodl", "local", "commercial"])
    autodl_tunnel_script: str = ""
    commercial_endpoint: str = ""


class TTSConfig(BaseModel):
    provider: str = "edge"
    voice: str = "zh-CN-XiaoxiaoNeural"


class SubtitleConfig(BaseModel):
    mode: str = "edge"


class MaterialConfig(BaseModel):
    enabled: bool = True
    pexels_api_keys: list[str] = Field(default_factory=list)
    fallback_after_failures: int = 2


class PipelineConfig(BaseModel):
    max_frames: int = 8
    stop_at_default: str = "final"
    bgm_dir: str = "data/bgm"
    keyframe_workflow: str = "wan2.1_txt2img"
    flux_workflow: str = "flux_txt2img"
    i2v_workflow: str = "wan2.1_img2vid"
    t2v_workflow: str = "wan2.1_txt2vid"
    fps: int = 16
    use_flux_keyframe: bool = False
    # 镜间转场：cut=硬切 fade=淡入淡出
    transition: str = "fade"
    transition_duration_sec: float = 0.5
    # 首镜定调：后续镜 T2I prompt 前缀复用首镜风格锚点
    use_keyframe_consistency: bool = True
    # 过渡镜用 Ken Burns 替代 I2V（降本）
    ken_burns_for_transitions: bool = True
    ken_burns_zoom: float = 1.08
    # 单镜失败重试与跳过
    frame_max_retries: int = 2
    skip_failed_frames: bool = True
    profiles: dict[str, dict[str, Any]] = Field(
        default_factory=lambda: {
            "default": {"width": 832, "height": 480, "length": 49, "steps": 20},
            "fast": {"width": 512, "height": 288, "length": 25, "steps": 10},
        }
    )


class TasksConfig(BaseModel):
    max_concurrent_comfyui: int = 1
    log_dir: str = "logs/tasks"


class VplatformConfig(BaseModel):
    root: str = ""
    vplatform_root: str = ""
    llm: LLMConfig = Field(default_factory=LLMConfig)
    comfyui: ComfyUIConfig = Field(default_factory=ComfyUIConfig)
    provider: ProviderConfig = Field(default_factory=ProviderConfig)
    tts: TTSConfig = Field(default_factory=TTSConfig)
    subtitle: SubtitleConfig = Field(default_factory=SubtitleConfig)
    material: MaterialConfig = Field(default_factory=MaterialConfig)
    pipeline: PipelineConfig = Field(default_factory=PipelineConfig)
    tasks: TasksConfig = Field(default_factory=TasksConfig)
