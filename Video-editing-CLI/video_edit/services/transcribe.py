"""Whisper 转录（faster-whisper）。"""

from __future__ import annotations

import json
from pathlib import Path

from loguru import logger

from video_edit.config import TranscribeConfig
from video_edit.models.transcript import Transcript, TranscriptSegment, WordToken
from video_edit.services.audio import probe_duration
from video_edit.utils.errors import DependencyError


def _resolve_device(device: str) -> str:
    if device != "auto":
        return device
    try:
        import torch

        if torch.cuda.is_available():
            return "cuda"
        if getattr(torch.backends, "mps", None) and torch.backends.mps.is_available():
            return "mps"
    except ImportError:
        pass
    return "cpu"


def transcribe_audio(
    audio_path: Path,
    *,
    config: TranscribeConfig,
    source_label: str = "",
) -> Transcript:
    try:
        from faster_whisper import WhisperModel
    except ImportError as exc:
        raise DependencyError(
            "未安装 faster-whisper，请运行: pip install -e '.[whisper]'"
        ) from exc

    device = _resolve_device(config.device)
    compute_type = "float16" if device == "cuda" else "int8"
    logger.info("加载 Whisper 模型: {} (device={})", config.model, device)
    model = WhisperModel(config.model, device=device, compute_type=compute_type)

    segments_iter, info = model.transcribe(
        str(audio_path),
        language=config.language or None,
        word_timestamps=config.word_timestamps,
        vad_filter=True,
    )

    words: list[WordToken] = []
    segments: list[TranscriptSegment] = []
    seg_id = 0
    for seg in segments_iter:
        seg_text = (seg.text or "").strip()
        if not seg_text:
            continue
        segments.append(
            TranscriptSegment(
                id=seg_id,
                start=float(seg.start),
                end=float(seg.end),
                text=seg_text,
            )
        )
        if seg.words:
            for w in seg.words:
                token = (w.word or "").strip()
                if not token:
                    continue
                words.append(
                    WordToken(
                        text=token,
                        start=float(w.start),
                        end=float(w.end),
                        confidence=float(getattr(w, "probability", 1.0) or 1.0),
                    )
                )
        seg_id += 1

    duration = probe_duration(audio_path) if audio_path.is_file() else 0.0
    if words:
        duration = max(duration, words[-1].end)
    elif segments:
        duration = max(duration, segments[-1].end)

    transcript = Transcript(
        language=info.language or config.language,
        duration_sec=duration,
        source=source_label or str(audio_path),
        words=words,
        segments=segments,
    )
    logger.info(
        "转录完成: {} 词, {} 段, 时长 {:.1f}s",
        len(words),
        len(segments),
        duration,
    )
    return transcript


def save_transcript(transcript: Transcript, path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(transcript.model_dump(), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return path


def load_transcript(path: Path) -> Transcript:
    data = json.loads(path.read_text(encoding="utf-8"))
    return Transcript.model_validate(data)
