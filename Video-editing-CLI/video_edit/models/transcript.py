"""转录数据模型。"""

from __future__ import annotations

from pydantic import BaseModel, Field


class WordToken(BaseModel):
    text: str
    start: float
    end: float
    confidence: float = 1.0


class TranscriptSegment(BaseModel):
    id: int
    start: float
    end: float
    text: str


class Transcript(BaseModel):
    language: str = "zh"
    duration_sec: float = 0.0
    source: str = ""
    words: list[WordToken] = Field(default_factory=list)
    segments: list[TranscriptSegment] = Field(default_factory=list)

    def full_text(self) -> str:
        if self.words:
            return "".join(w.text for w in self.words)
        return "".join(s.text for s in self.segments)
