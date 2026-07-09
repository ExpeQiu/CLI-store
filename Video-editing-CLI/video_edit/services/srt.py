"""SRT 字幕导出。"""

from __future__ import annotations

from pathlib import Path

from loguru import logger

from video_edit.models.edit_decision import EditDecision
from video_edit.models.transcript import Transcript


def _format_ts(sec: float) -> str:
    h = int(sec // 3600)
    m = int((sec % 3600) // 60)
    s = int(sec % 60)
    ms = int(round((sec - int(sec)) * 1000))
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def export_srt_from_transcript(
    transcript: Transcript,
    output_path: Path,
    *,
    decision: EditDecision | None = None,
) -> Path:
    lines: list[str] = []
    idx = 1

    if decision:
        timeline_offset = 0.0
        for keep in decision.keep_clips():
            for seg in transcript.segments:
                if seg.end <= keep.source_in or seg.start >= keep.source_out:
                    continue
                rel_start = max(seg.start, keep.source_in) - keep.source_in + timeline_offset
                rel_end = min(seg.end, keep.source_out) - keep.source_in + timeline_offset
                if rel_end <= rel_start:
                    continue
                lines.append(str(idx))
                lines.append(f"{_format_ts(rel_start)} --> {_format_ts(rel_end)}")
                lines.append(seg.text.strip())
                lines.append("")
                idx += 1
            timeline_offset += keep.source_out - keep.source_in
    else:
        for seg in transcript.segments:
            lines.append(str(idx))
            lines.append(f"{_format_ts(seg.start)} --> {_format_ts(seg.end)}")
            lines.append(seg.text.strip())
            lines.append("")
            idx += 1

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text("\n".join(lines), encoding="utf-8")
    logger.info("SRT 已导出: {}", output_path)
    return output_path
