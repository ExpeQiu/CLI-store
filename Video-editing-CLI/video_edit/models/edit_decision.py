"""剪辑决策数据模型。"""

from __future__ import annotations

from pydantic import BaseModel, Field


class EditClip(BaseModel):
    id: str
    action: str  # keep | cut
    source_in: float
    source_out: float
    script_ref: str = ""
    reason: str = ""


class EditStats(BaseModel):
    cuts: int = 0
    kept_clips: int = 0
    breath_gaps_applied: int = 0
    duplicate_takes: int = 0
    mistake_retakes: int = 0
    long_pauses: int = 0
    llm_reviews: int = 0


class EditDecision(BaseModel):
    source_video: str = ""
    frame_rate: float = 30.0
    total_source_sec: float = 0.0
    total_output_sec: float = 0.0
    retain_ratio: float = 0.0
    clips: list[EditClip] = Field(default_factory=list)
    stats: EditStats = Field(default_factory=EditStats)

    def keep_clips(self) -> list[EditClip]:
        return [c for c in self.clips if c.action == "keep"]

    def cut_clips(self) -> list[EditClip]:
        return [c for c in self.clips if c.action == "cut"]
