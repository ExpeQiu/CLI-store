"""任务状态模型。"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class TaskStage(str, Enum):
    PENDING = "pending"
    STORYBOARD = "storyboard"
    TTS = "tts"
    KEYFRAME = "keyframe"
    I2V = "i2v"
    CONCAT = "concat"
    SUBTITLE = "subtitle"
    FINAL = "final"
    FAILED = "failed"
    CANCELLED = "cancelled"


STOP_AT_STAGES = [
    "storyboard",
    "tts",
    "keyframe",
    "i2v",
    "concat",
    "subtitle",
    "final",
]


class TaskRecord(BaseModel):
    task_id: str
    subject: str = ""
    stage: TaskStage = TaskStage.PENDING
    stop_at: str = "final"
    progress: float = 0.0
    outputs: dict[str, Any] = Field(default_factory=dict)
    error: str | None = None
    created_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    updated_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    output_dir: str = ""

    def touch(self) -> None:
        self.updated_at = datetime.now(timezone.utc).isoformat()
