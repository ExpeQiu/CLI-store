"""分镜数据模型。"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class WordTimestamp(BaseModel):
    text: str
    start_sec: float
    end_sec: float


class AudioResult(BaseModel):
    path: str
    duration_sec: float
    word_timestamps: list[WordTimestamp] = Field(default_factory=list)


class StoryboardMeta(BaseModel):
    aspect_ratio: str = "16:9"
    fps: int = 16
    profile: str = "fast"
    width: int = 512
    height: int = 288


class StoryboardFrame(BaseModel):
    index: int
    narration: str
    image_prompt: str
    motion_prompt: str = ""
    negative_prompt: str = "blurry, low quality, distorted, watermark, artifacts"
    duration_sec: float | None = None
    audio: AudioResult | None = None
    keyframe_path: str | None = None
    clip_path: str | None = None
    material_fallback: bool = False


class Storyboard(BaseModel):
    title: str
    frames: list[StoryboardFrame] = Field(default_factory=list)
    meta: StoryboardMeta = Field(default_factory=StoryboardMeta)

    def to_dict(self) -> dict[str, Any]:
        return self.model_dump()

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Storyboard:
        return cls.model_validate(data)

    def save_json(self, path: str) -> None:
        from pathlib import Path

        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(self.model_dump_json(indent=2, ensure_ascii=False), encoding="utf-8")

    @classmethod
    def load_json(cls, path: str) -> Storyboard:
        from pathlib import Path

        return cls.model_validate_json(Path(path).read_text(encoding="utf-8"))
