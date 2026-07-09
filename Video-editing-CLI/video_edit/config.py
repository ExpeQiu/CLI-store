"""配置加载。"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field


class PipelineConfig(BaseModel):
    frame_rate: float = 30.0
    breath_gap_sec: float = 0.4
    pre_cut_buffer: float = 0.1
    post_cut_buffer: float = 0.1
    silence_threshold_db: float = -40.0
    min_keep_sec: float = 0.3
    long_pause_sec: float = 1.5


class TranscribeConfig(BaseModel):
    model: str = "base"
    language: str = "zh"
    word_timestamps: bool = True
    device: str = "auto"
    use_whisperx_align: bool = False


class AlignConfig(BaseModel):
    match_threshold: float = 0.55
    ambiguous_low: float = 0.40
    use_llm_review: bool = False
    llm_model: str = "gpt-4o-mini"
    openai_api_key: str | None = None
    openai_base_url: str | None = None


class ExportConfig(BaseModel):
    fcpxml_version: str = "1.11"
    include_srt: bool = True
    media_path_style: str = "absolute"
    formats: list[str] = Field(default_factory=lambda: ["fcpxml", "edl", "srt"])


class MulticamConfig(BaseModel):
    enabled: bool = False
    sample_rate: int = 800
    max_lag_sec: float = 30.0


class BatchConfig(BaseModel):
    max_concurrent: int = 1
    auto_resume: bool = True


class AppConfig(BaseModel):
    pipeline: PipelineConfig = Field(default_factory=PipelineConfig)
    transcribe: TranscribeConfig = Field(default_factory=TranscribeConfig)
    align: AlignConfig = Field(default_factory=AlignConfig)
    export: ExportConfig = Field(default_factory=ExportConfig)
    multicam: MulticamConfig = Field(default_factory=MulticamConfig)
    batch: BatchConfig = Field(default_factory=BatchConfig)


def find_config_path(explicit: str | Path | None = None) -> Path | None:
    if explicit:
        path = Path(explicit).expanduser().resolve()
        return path if path.is_file() else None
    cwd = Path.cwd()
    for name in ("config.yaml", "config.yml"):
        candidate = cwd / name
        if candidate.is_file():
            return candidate
    project_root = Path(__file__).resolve().parent.parent
    for name in ("config.yaml", "config.yml", "config.yaml.example"):
        candidate = project_root / name
        if candidate.is_file():
            return candidate
    return None


def load_config(path: str | Path | None = None) -> AppConfig:
    config_path = find_config_path(path)
    if not config_path:
        return AppConfig()
    raw: dict[str, Any] = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    return AppConfig.model_validate(raw)


def init_config_file(target: Path, force: bool = False) -> Path:
    example = Path(__file__).resolve().parent.parent / "config.yaml.example"
    if target.exists() and not force:
        raise FileExistsError(f"配置已存在: {target}")
    if not example.is_file():
        raise FileNotFoundError("未找到 config.yaml.example")
    target.write_text(example.read_text(encoding="utf-8"), encoding="utf-8")
    return target
