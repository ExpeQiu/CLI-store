"""WhisperX 强制对齐（可选，提升词级时间戳精度）。"""

from __future__ import annotations

from pathlib import Path

from loguru import logger

from video_edit.models.transcript import Transcript, TranscriptSegment, WordToken
from video_edit.utils.errors import DependencyError


def align_transcript_whisperx(
    audio_path: Path,
    transcript: Transcript,
    *,
    language: str,
    device: str = "auto",
) -> Transcript:
    """用 WhisperX 对已有 segment 文本做强制对齐，刷新 words 时间戳。"""
    try:
        import whisperx
    except ImportError as exc:
        raise DependencyError(
            "未安装 whisperx，请运行: pip install -e '.[whisperx]'"
        ) from exc

    if not transcript.segments:
        logger.warning("无 segments，跳过 WhisperX 对齐")
        return transcript

    resolved_device = _resolve_device(device)
    logger.info("WhisperX 强制对齐 (device={}, lang={})", resolved_device, language)

    audio = whisperx.load_audio(str(audio_path))
    align_model, metadata = whisperx.load_align_model(
        language_code=language,
        device=resolved_device,
    )

    segment_dicts = [
        {"start": seg.start, "end": seg.end, "text": seg.text}
        for seg in transcript.segments
    ]
    aligned = whisperx.align(
        segment_dicts,
        align_model,
        metadata,
        audio,
        resolved_device,
        return_char_alignments=False,
    )

    words: list[WordToken] = []
    segments: list[TranscriptSegment] = []
    for i, seg in enumerate(aligned.get("segments", [])):
        text = (seg.get("text") or "").strip()
        start = float(seg.get("start", 0))
        end = float(seg.get("end", start))
        segments.append(TranscriptSegment(id=i, start=start, end=end, text=text))
        for w in seg.get("words") or []:
            token = (w.get("word") or "").strip()
            if not token:
                continue
            w_start = w.get("start")
            w_end = w.get("end")
            if w_start is None or w_end is None:
                continue
            words.append(
                WordToken(
                    text=token,
                    start=float(w_start),
                    end=float(w_end),
                    confidence=float(w.get("score", 1.0) or 1.0),
                )
            )

    duration = transcript.duration_sec
    if words:
        duration = max(duration, words[-1].end)
    elif segments:
        duration = max(duration, segments[-1].end)

    logger.info("WhisperX 对齐完成: {} 词", len(words))
    return Transcript(
        language=language,
        duration_sec=duration,
        source=transcript.source,
        words=words,
        segments=segments,
    )


def _resolve_device(device: str) -> str:
    if device != "auto":
        return device
    try:
        import torch

        if torch.cuda.is_available():
            return "cuda"
        if getattr(torch.backends, "mps", None) and torch.backends.mps.is_available():
            return "cpu"  # whisperx 在 mps 上常不稳定
    except ImportError:
        pass
    return "cpu"
