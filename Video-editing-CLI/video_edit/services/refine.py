"""剪辑决策精修：气口保留 + 静音吸附 + 长停顿切分。"""

from __future__ import annotations

from loguru import logger

from video_edit.config import PipelineConfig
from video_edit.models.edit_decision import EditClip, EditDecision, EditStats
from video_edit.services.silence import SilenceRegion, snap_to_silence_boundary


def refine_edit_decision(
    decision: EditDecision,
    silences: list[SilenceRegion],
    pipeline_config: PipelineConfig,
) -> EditDecision:
    """基于静音区间精修 keep 片段边界，并标记长停顿。"""
    breath = pipeline_config.breath_gap_sec
    long_pause = pipeline_config.long_pause_sec
    pre = pipeline_config.pre_cut_buffer
    post = pipeline_config.post_cut_buffer
    min_keep = pipeline_config.min_keep_sec
    total = decision.total_source_sec

    kept = decision.keep_clips()
    if not kept:
        return decision

    refined_keeps: list[tuple[float, float, str, str]] = []
    long_pause_cuts = 0

    for clip in kept:
        rs = max(0.0, clip.source_in - pre)
        re = min(total, clip.source_out + post)
        rs = snap_to_silence_boundary(rs, silences, direction="before")
        re = snap_to_silence_boundary(re, silences, direction="after")

        # 保留片段内部的长停顿 → 切分
        internal_pauses = [
            s for s in silences if s.duration >= long_pause and rs < s.start and s.end < re
        ]
        if not internal_pauses:
            refined_keeps.append((rs, re, clip.script_ref, clip.reason))
            continue

        cursor = rs
        for pause in internal_pauses:
            if pause.start - cursor >= min_keep:
                refined_keeps.append((cursor, pause.start, clip.script_ref, clip.reason))
            long_pause_cuts += 1
            cursor = pause.end
        if re - cursor >= min_keep:
            refined_keeps.append((cursor, re, clip.script_ref, clip.reason))

    # 相邻 keep 之间保证气口
    merged: list[tuple[float, float, str, str]] = []
    for i, (rs, re, ref, reason) in enumerate(refined_keeps):
        if i > 0 and merged:
            prev_end = merged[-1][1]
            gap = rs - prev_end
            if 0 < gap < breath:
                rs = prev_end
            elif gap < 0:
                rs = prev_end
        if re - rs >= min_keep:
            merged.append((rs, re, ref, reason))

    new_clips = _ranges_to_clips(merged, total, decision.clips)
    kept_new = [c for c in new_clips if c.action == "keep"]
    output_sec = sum(c.source_out - c.source_in for c in kept_new)
    retain = output_sec / total if total > 0 else 0.0

    stats = decision.stats.model_copy()
    stats.long_pauses = stats.long_pauses + long_pause_cuts
    stats.breath_gaps_applied = max(stats.breath_gaps_applied, len(kept_new) - 1)
    stats.cuts = len([c for c in new_clips if c.action == "cut"])
    stats.kept_clips = len(kept_new)

    logger.info(
        "精修完成: keep={} cuts={} long_pauses={}",
        stats.kept_clips,
        stats.cuts,
        stats.long_pauses,
    )
    return decision.model_copy(
        update={
            "clips": new_clips,
            "total_output_sec": output_sec,
            "retain_ratio": round(retain, 4),
            "stats": stats,
        }
    )


def _ranges_to_clips(
    keeps: list[tuple[float, float, str, str]],
    total_duration: float,
    original_clips: list[EditClip],
) -> list[EditClip]:
    """重建 clips 列表，cut 区间继承原 reason（若可匹配）。"""
    cut_reason_map = _cut_reason_lookup(original_clips)
    clips: list[EditClip] = []
    cursor = 0.0
    keep_idx = 0
    cut_idx = 0

    for rs, re, ref, reason in keeps:
        if rs > cursor + 0.05:
            cut_idx += 1
            clips.append(
                EditClip(
                    id=f"cut_{cut_idx:03d}",
                    action="cut",
                    source_in=cursor,
                    source_out=rs,
                    reason=_reason_for_cut(cursor, rs, cut_reason_map),
                )
            )
        keep_idx += 1
        clips.append(
            EditClip(
                id=f"clip_{keep_idx:03d}",
                action="keep",
                source_in=rs,
                source_out=re,
                script_ref=ref,
                reason=reason,
            )
        )
        cursor = re

    if cursor < total_duration - 0.05:
        cut_idx += 1
        clips.append(
            EditClip(
                id=f"cut_{cut_idx:03d}",
                action="cut",
                source_in=cursor,
                source_out=total_duration,
                reason="trailing_unused",
            )
        )
    return clips


def _cut_reason_lookup(clips: list[EditClip]) -> list[EditClip]:
    return [c for c in clips if c.action == "cut"]


def _reason_for_cut(start: float, end: float, cuts: list[EditClip]) -> str:
    mid = (start + end) / 2
    for c in cuts:
        if c.source_in <= mid <= c.source_out:
            return c.reason
    return "gap_or_duplicate"
