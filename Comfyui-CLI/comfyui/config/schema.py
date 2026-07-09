"""Pydantic 配置 Schema。"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class ComfyUIConfig(BaseModel):
    endpoint: str = "http://127.0.0.1:8188"
    base_path: str = ""
    default_profile: str = "fast"
    timeout_sec: int = 1800
    poll_interval_sec: float = 5.0


class LocalProviderConfig(BaseModel):
    enabled: bool = True


class RunningHubProviderConfig(BaseModel):
    enabled: bool = False
    api_key: str = ""
    base_url: str = "https://www.runninghub.cn"


class ProvidersConfig(BaseModel):
    local: LocalProviderConfig = Field(default_factory=LocalProviderConfig)
    runninghub: RunningHubProviderConfig = Field(default_factory=RunningHubProviderConfig)


class ImageCapabilities(BaseModel):
    default: str = "wan2.1_txt2img"
    t2i: str = "wan2.1_txt2img"
    i2i: str | None = None


class VideoCapabilities(BaseModel):
    t2v: str = "wan2.1_txt2vid"
    i2v: str = "wan2.1_img2vid"
    fps: int = 16


class DigitalCapabilities(BaseModel):
    compose: str = "digital_image"
    lip_sync: str = "digital_combination"
    customize: str = "digital_customize"


class CapabilitiesConfig(BaseModel):
    image: ImageCapabilities = Field(default_factory=ImageCapabilities)
    video: VideoCapabilities = Field(default_factory=VideoCapabilities)
    digital: DigitalCapabilities = Field(default_factory=DigitalCapabilities)


class ComfyuiConfig(BaseModel):
    root: str = ""
    comfyui: ComfyUIConfig = Field(default_factory=ComfyUIConfig)
    providers: ProvidersConfig = Field(default_factory=ProvidersConfig)
    capabilities: CapabilitiesConfig = Field(default_factory=CapabilitiesConfig)
    profiles: dict[str, dict[str, Any]] = Field(
        default_factory=lambda: {
            "default": {"width": 832, "height": 480, "length": 49, "steps": 20},
            "fast": {"width": 512, "height": 288, "length": 25, "steps": 10},
        }
    )
    workflows_dir: str = "workflows"
    data_workflows_dir: str = "data/workflows"
    output_dir: str = "outputs"
