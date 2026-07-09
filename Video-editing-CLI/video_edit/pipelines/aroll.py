"""A-Roll 主流水线（含断点续跑 / Multicam / 多格式导出）。"""

from __future__ import annotations

import json
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path

from loguru import logger

from video_edit.config import AppConfig
from video_edit.demo.fixtures import DEMO_SCRIPT, DEMO_TRANSCRIPT, write_demo_script
from video_edit.models.edit_decision import EditDecision
from video_edit.models.transcript import Transcript
from video_edit.services.align import align_script_to_transcript
from video_edit.services.audio import extract_audio, probe_duration
from video_edit.services.checkpoint import load_checkpoint, save_checkpoint, stage_completed
from video_edit.services.export_formats import export_all_formats
from video_edit.services.multicam import save_sync_map, sync_multicam
from video_edit.services.refine import refine_edit_decision
from video_edit.services.silence import detect_silence_regions
from video_edit.services.transcribe import load_transcript, save_transcript, transcribe_audio
from video_edit.services.whisperx_align import align_transcript_whisperx
from video_edit.utils.logger import remove_sink, task_logger


@dataclass
class PipelineResult:
    job_id: str
    output_dir: Path
    transcript_path: Path | None = None
    decisions_path: Path | None = None
    fcpxml_path: Path | None = None
    edl_path: Path | None = None
    srt_path: Path | None = None
    sync_map_path: Path | None = None
    jianying_path: Path | None = None
    exports: dict[str, Path] = field(default_factory=dict)
    summary: dict = field(default_factory=dict)


def _new_job_id(prefix: str | None = None) -> str:
    base = time.strftime("%Y%m%d_%H%M%S") + "_" + uuid.uuid4().hex[:8]
    return f"{prefix}_{base}" if prefix else base


def run_aroll_pipeline(
    *,
    video: Path | None,
    script: Path | None,
    output_dir: Path,
    config: AppConfig,
    demo: bool = False,
    stop_at: str | None = None,
    secondary_videos: list[Path] | None = None,
    resume: bool = False,
    work_dir: Path | None = None,
    job_id_prefix: str | None = None,
    fixed_job_id: str | None = None,
) -> PipelineResult:
    job_id = fixed_job_id or (work_dir.name if work_dir else _new_job_id(job_id_prefix))
    work_dir = work_dir or (output_dir / job_id)
    work_dir.mkdir(parents=True, exist_ok=True)
    log_dir = Path("logs/tasks") / job_id
    t0 = time.time()
    checkpoint = load_checkpoint(work_dir) if resume else None
    stages_done: list[str] = list(checkpoint.get("stages_done", [])) if checkpoint else []

    if demo:
        return _run_demo_pipeline(work_dir, log_dir, job_id, config, t0)

    if not video or not script:
        raise ValueError("非 demo 模式需要 --video 与 --script")
    if not video.is_file():
        raise FileNotFoundError(f"视频不存在: {video}")
    if not script.is_file():
        raise FileNotFoundError(f"脚本不存在: {script}")

    script_text = script.read_text(encoding="utf-8")
    transcript_path = work_dir / "transcript.json"
    decisions_path = work_dir / "edit_decisions.json"
    sync_map_path = work_dir / "sync_map.json"
    audio_path = work_dir / "audio.wav"

    transcript: Transcript | None = None
    decision: EditDecision | None = None

    # extract
    if not stage_completed(checkpoint, "extract"):
        sink_file, sink_id = task_logger(log_dir, "extract")
        try:
            logger.info("[extract] 开始")
            extract_audio(video, audio_path)
            if secondary_videos:
                sync_map = sync_multicam(video, secondary_videos)
                save_sync_map(sync_map, sync_map_path)
            stages_done.append("extract")
            save_checkpoint(work_dir, "extract", {"paths": {"audio": str(audio_path)}})
        finally:
            remove_sink(sink_id)
    elif resume and transcript_path.is_file():
        logger.info("[extract] 跳过（checkpoint）")

    if stop_at == "extract":
        return _summary_result(job_id, work_dir, stages_done, t0)

    # transcribe
    if not stage_completed(checkpoint, "transcribe"):
        sink_file, sink_id = task_logger(log_dir, "transcribe")
        try:
            logger.info("[transcribe] 开始")
            transcript = transcribe_audio(
                audio_path,
                config=config.transcribe,
                source_label=str(video),
            )
            if transcript.duration_sec <= 0:
                transcript.duration_sec = probe_duration(video)
            if config.transcribe.use_whisperx_align:
                try:
                    transcript = align_transcript_whisperx(
                        audio_path,
                        transcript,
                        language=config.transcribe.language,
                        device=config.transcribe.device,
                    )
                except Exception as exc:
                    logger.warning("WhisperX 对齐跳过: {}", exc)
            save_transcript(transcript, transcript_path)
            stages_done.append("transcribe")
            save_checkpoint(work_dir, "transcribe", {"paths": {"transcript": str(transcript_path)}})
        finally:
            remove_sink(sink_id)
    else:
        transcript = load_transcript(transcript_path)
        logger.info("[transcribe] 跳过（checkpoint）")

    if stop_at == "transcribe":
        return PipelineResult(
            job_id=job_id,
            output_dir=work_dir,
            transcript_path=transcript_path,
            sync_map_path=sync_map_path if sync_map_path.is_file() else None,
            summary=_build_summary(stages_done, t0, None),
        )

    # align
    if not stage_completed(checkpoint, "align"):
        sink_file, sink_id = task_logger(log_dir, "align")
        try:
            logger.info("[align] 开始")
            assert transcript is not None
            decision = align_script_to_transcript(
                script_text,
                transcript,
                align_config=config.align,
                pipeline_config=config.pipeline,
            )
            decision.source_video = str(video.resolve())
            decision.frame_rate = config.pipeline.frame_rate
            decisions_path.write_text(
                json.dumps(decision.model_dump(), ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            stages_done.append("align")
            save_checkpoint(work_dir, "align", {"paths": {"decisions": str(decisions_path)}})
        finally:
            remove_sink(sink_id)
    else:
        decision = EditDecision.model_validate(
            json.loads(decisions_path.read_text(encoding="utf-8"))
        )
        logger.info("[align] 跳过（checkpoint）")

    if stop_at == "align":
        return PipelineResult(
            job_id=job_id,
            output_dir=work_dir,
            transcript_path=transcript_path,
            decisions_path=decisions_path,
            summary=_build_summary(stages_done, t0, decision),
        )

    # refine
    if not stage_completed(checkpoint, "refine"):
        sink_file, sink_id = task_logger(log_dir, "refine")
        try:
            logger.info("[refine] 开始")
            assert decision is not None
            silences = detect_silence_regions(
                str(audio_path),
                threshold_db=config.pipeline.silence_threshold_db,
                min_duration_sec=0.3,
            )
            decision = refine_edit_decision(decision, silences, config.pipeline)
            decisions_path.write_text(
                json.dumps(decision.model_dump(), ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            stages_done.append("refine")
            save_checkpoint(work_dir, "refine", {"paths": {"decisions": str(decisions_path)}})
        finally:
            remove_sink(sink_id)
    else:
        decision = EditDecision.model_validate(
            json.loads(decisions_path.read_text(encoding="utf-8"))
        )
        logger.info("[refine] 跳过（checkpoint）")

    if stop_at == "refine":
        return PipelineResult(
            job_id=job_id,
            output_dir=work_dir,
            transcript_path=transcript_path,
            decisions_path=decisions_path,
            summary=_build_summary(stages_done, t0, decision),
        )

    # export
    exports: dict[str, Path] = {}
    if not stage_completed(checkpoint, "export"):
        sink_file, sink_id = task_logger(log_dir, "export")
        try:
            logger.info("[export] 开始")
            assert decision is not None
            if transcript is None and transcript_path.is_file():
                transcript = load_transcript(transcript_path)
            exports = export_all_formats(
                decision,
                video,
                work_dir,
                config=config,
                transcript=transcript,
            )
            stages_done.append("export")
            save_checkpoint(work_dir, "export", {"paths": {k: str(v) for k, v in exports.items()}})
        finally:
            remove_sink(sink_id)
    else:
        for fmt in config.export.formats:
            p = work_dir / {"fcpxml": "timeline.fcpxml", "edl": "timeline.edl", "srt": "transcript.srt", "jianying": "jianying_metadata.json"}.get(fmt, f"{fmt}.out")
            if p.is_file():
                exports[fmt] = p
        logger.info("[export] 跳过（checkpoint）")

    summary = _build_summary(stages_done, t0, decision)
    _write_summary(log_dir, summary)

    return PipelineResult(
        job_id=job_id,
        output_dir=work_dir,
        transcript_path=transcript_path,
        decisions_path=decisions_path,
        fcpxml_path=exports.get("fcpxml"),
        edl_path=exports.get("edl"),
        srt_path=exports.get("srt"),
        sync_map_path=sync_map_path if sync_map_path.is_file() else None,
        jianying_path=exports.get("jianying"),
        exports=exports,
        summary=summary,
    )


def _run_demo_pipeline(
    work_dir: Path,
    log_dir: Path,
    job_id: str,
    config: AppConfig,
    t0: float,
) -> PipelineResult:
    logger.info("[demo] 使用 Mock 数据运行流水线")
    script_path = work_dir / "script.txt"
    write_demo_script(script_path)
    transcript_path = work_dir / "transcript.json"
    decisions_path = work_dir / "edit_decisions.json"
    demo_video = work_dir / "demo_source.mp4"

    save_transcript(DEMO_TRANSCRIPT, transcript_path)
    decision = align_script_to_transcript(
        DEMO_SCRIPT,
        DEMO_TRANSCRIPT,
        align_config=config.align,
        pipeline_config=config.pipeline,
    )
    decision.source_video = str(demo_video)
    decision.frame_rate = config.pipeline.frame_rate
    decision = refine_edit_decision(decision, [], config.pipeline)
    decisions_path.write_text(
        json.dumps(decision.model_dump(), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    demo_video.write_bytes(b"")
    exports = export_all_formats(
        decision,
        demo_video,
        work_dir,
        config=config,
        transcript=DEMO_TRANSCRIPT,
    )

    stages = ["extract", "transcribe", "align", "refine", "export"]
    summary = _build_summary(stages, t0, decision, demo=True)
    _write_summary(log_dir, summary)

    return PipelineResult(
        job_id=job_id,
        output_dir=work_dir,
        transcript_path=transcript_path,
        decisions_path=decisions_path,
        fcpxml_path=exports.get("fcpxml"),
        edl_path=exports.get("edl"),
        srt_path=exports.get("srt"),
        jianying_path=exports.get("jianying"),
        exports=exports,
        summary=summary,
    )


def run_align_only(
    transcript_path: Path,
    script_path: Path,
    output_path: Path,
    config: AppConfig,
) -> EditDecision:
    transcript = load_transcript(transcript_path)
    script_text = script_path.read_text(encoding="utf-8")
    decision = align_script_to_transcript(
        script_text,
        transcript,
        align_config=config.align,
        pipeline_config=config.pipeline,
    )
    decision.frame_rate = config.pipeline.frame_rate
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(decision.model_dump(), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return decision


def run_export_only(
    decisions_path: Path,
    video_path: Path,
    output_dir: Path,
    config: AppConfig,
) -> PipelineResult:
    decision = EditDecision.model_validate(json.loads(decisions_path.read_text(encoding="utf-8")))
    exports = export_all_formats(decision, video_path, output_dir, config=config)
    return PipelineResult(
        job_id="export",
        output_dir=output_dir,
        decisions_path=decisions_path,
        fcpxml_path=exports.get("fcpxml"),
        edl_path=exports.get("edl"),
        exports=exports,
    )


def _build_summary(
    stages: list[str],
    t0: float,
    decision: EditDecision | None,
    demo: bool = False,
) -> dict:
    summary: dict = {
        "stages": stages,
        "elapsed_sec": round(time.time() - t0, 2),
        "demo": demo,
    }
    if decision:
        summary.update(
            {
                "retain_ratio": decision.retain_ratio,
                "total_source_sec": decision.total_source_sec,
                "total_output_sec": decision.total_output_sec,
                "kept_clips": decision.stats.kept_clips,
                "cuts": decision.stats.cuts,
                "duplicate_takes": decision.stats.duplicate_takes,
                "long_pauses": decision.stats.long_pauses,
                "llm_reviews": decision.stats.llm_reviews,
            }
        )
    return summary


def _write_summary(log_dir: Path, summary: dict) -> None:
    log_dir.mkdir(parents=True, exist_ok=True)
    (log_dir / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def _summary_result(
    job_id: str,
    work_dir: Path,
    stages: list[str],
    t0: float,
) -> PipelineResult:
    return PipelineResult(
        job_id=job_id,
        output_dir=work_dir,
        summary=_build_summary(stages, t0, None),
    )
