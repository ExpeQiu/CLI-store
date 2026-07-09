"""CMX3600 EDL 导出（Premiere / Avid 兼容）。"""

from __future__ import annotations

from pathlib import Path

from loguru import logger

from video_edit.models.edit_decision import EditDecision


def _sec_to_edl_tc(sec: float, fps: float = 30.0) -> str:
    if sec < 0:
        sec = 0.0
    frames_total = int(round(sec * fps))
    f = frames_total % int(fps)
    s_total = frames_total // int(fps)
    s = s_total % 60
    m_total = s_total // 60
    m = m_total % 60
    h = m_total // 60
    return f"{h:02d}:{m:02d}:{s:02d}:{f:02d}"


def export_edl(
    decision: EditDecision,
    video_path: Path,
    output_path: Path,
    *,
    title: str = "A-Roll Edit",
    fps: float = 30.0,
) -> Path:
    keep_clips = decision.keep_clips()
    if not keep_clips:
        raise ValueError("无保留片段，无法导出 EDL")

    reel = video_path.stem[:8].upper().replace(" ", "_")
    lines = [f"TITLE: {title}", f"FCM: NON-DROP FRAME", ""]

    timeline_cursor = 0.0
    for i, clip in enumerate(keep_clips, start=1):
        src_in = clip.source_in
        src_out = clip.source_out
        dur = src_out - src_in
        rec_in = timeline_cursor
        rec_out = timeline_cursor + dur

        lines.append(
            f"{i:03d}  {reel:<8} V     C        "
            f"{_sec_to_edl_tc(src_in, fps)} {_sec_to_edl_tc(src_out, fps)} "
            f"{_sec_to_edl_tc(rec_in, fps)} {_sec_to_edl_tc(rec_out, fps)}"
        )
        lines.append(f"* FROM CLIP NAME: {video_path.name}")
        if clip.script_ref:
            lines.append(f"* {clip.script_ref}")
        lines.append("")
        timeline_cursor = rec_out

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text("\n".join(lines), encoding="utf-8")
    logger.info("EDL 已导出: {} ({} 事件)", output_path, len(keep_clips))
    return output_path
