"""多格式导出聚合。"""

from __future__ import annotations

from pathlib import Path

from loguru import logger

from video_edit.config import AppConfig, ExportConfig, PipelineConfig
from video_edit.models.edit_decision import EditDecision
from video_edit.models.transcript import Transcript
from video_edit.services.edl import export_edl
from video_edit.services.fcpxml import export_fcpxml
from video_edit.services.jianying import export_jianying_metadata
from video_edit.services.srt import export_srt_from_transcript


def export_all_formats(
    decision: EditDecision,
    video_path: Path,
    work_dir: Path,
    *,
    config: AppConfig,
    transcript: Transcript | None = None,
) -> dict[str, Path]:
    formats = [f.strip().lower() for f in config.export.formats if f.strip()]
    if not formats:
        formats = ["fcpxml"]

    outputs: dict[str, Path] = {}
    pipeline_cfg = config.pipeline
    export_cfg = config.export

    if "fcpxml" in formats:
        path = work_dir / "timeline.fcpxml"
        export_fcpxml(decision, video_path, path, pipeline_config=pipeline_cfg, export_config=export_cfg)
        outputs["fcpxml"] = path

    if "edl" in formats:
        path = work_dir / "timeline.edl"
        export_edl(decision, video_path, path, fps=pipeline_cfg.frame_rate)
        outputs["edl"] = path

    if "srt" in formats and transcript is not None:
        path = work_dir / "transcript.srt"
        export_srt_from_transcript(transcript, path, decision=decision)
        outputs["srt"] = path

    if "jianying" in formats:
        path = work_dir / "jianying_metadata.json"
        export_jianying_metadata(decision, video_path, path)
        outputs["jianying"] = path

    logger.info("多格式导出完成: {}", list(outputs.keys()))
    return outputs
