"""WISP-COPY 脚本-转录对齐引擎。"""

from __future__ import annotations

import difflib
from dataclasses import dataclass, field

from loguru import logger

from video_edit.config import AlignConfig, PipelineConfig
from video_edit.models.edit_decision import EditClip, EditDecision, EditStats
from video_edit.models.transcript import Transcript, WordToken
from video_edit.services.llm_review import AmbiguousMatch, review_ambiguous_matches
from video_edit.services.text_utils import normalize_text, split_script_sentences


@dataclass
class MatchSpan:
    script_idx: int
    script_text: str
    word_start_idx: int
    word_end_idx: int
    score: float
    start: float
    end: float


@dataclass
class LabeledCut:
    source_in: float
    source_out: float
    reason: str


@dataclass
class WispCopyResult:
    keep_ranges: list[tuple[float, float, str, str]] = field(default_factory=list)
    labeled_cuts: list[LabeledCut] = field(default_factory=list)
    stats: EditStats = field(default_factory=EditStats)


def _words_to_normalized_chars(words: list[WordToken]) -> tuple[str, list[int]]:
    chars: list[str] = []
    char_to_word: list[int] = []
    for wi, word in enumerate(words):
        for ch in normalize_text(word.text):
            chars.append(ch)
            char_to_word.append(wi)
    return "".join(chars), char_to_word


def _find_all_matches(
    script_norm: str,
    transcript_chars: str,
    char_to_word: list[int],
    words: list[WordToken],
    *,
    min_score: float,
) -> list[MatchSpan]:
    if not script_norm or not transcript_chars:
        return []

    matches: list[MatchSpan] = []
    script_len = len(script_norm)
    max_end = len(transcript_chars)
    min_win = max(1, int(script_len * 0.55))
    max_win = min(max_end, int(script_len * 2.0) + 6)

    for win_len in range(min_win, max_win + 1):
        step = max(1, win_len // 8)
        for start in range(0, max_end - win_len + 1, step):
            end = start + win_len
            chunk = transcript_chars[start:end]
            ratio = difflib.SequenceMatcher(None, script_norm, chunk).ratio()
            if ratio < min_score:
                continue
            word_start = char_to_word[start]
            word_end = char_to_word[end - 1]
            matches.append(
                MatchSpan(
                    script_idx=-1,
                    script_text="",
                    word_start_idx=word_start,
                    word_end_idx=word_end,
                    score=ratio,
                    start=words[word_start].start,
                    end=words[word_end].end,
                )
            )

    # 去重：相近起点只留最高分
    matches.sort(key=lambda m: (-m.score, m.word_start_idx))
    deduped: list[MatchSpan] = []
    for m in matches:
        if any(abs(m.word_start_idx - d.word_start_idx) <= 2 for d in deduped):
            continue
        deduped.append(m)
    deduped.sort(key=lambda m: m.word_start_idx)
    return deduped


def _pick_winner(candidates: list[MatchSpan]) -> MatchSpan:
    best_score = max(c.score for c in candidates)
    finalists = [c for c in candidates if c.score >= best_score - 0.05]
    return max(finalists, key=lambda c: c.word_start_idx)


def wisp_copy_align(
    script: str,
    transcript: Transcript,
    *,
    align_config: AlignConfig,
    pipeline_config: PipelineConfig,
) -> WispCopyResult:
    sentences = split_script_sentences(script)
    words = list(transcript.words)
    if not words and transcript.segments:
        words = [
            WordToken(text=seg.text, start=seg.start, end=seg.end)
            for seg in transcript.segments
        ]

    if not words:
        return WispCopyResult(
            labeled_cuts=[
                LabeledCut(0.0, transcript.duration_sec, "empty_transcript"),
            ],
            stats=EditStats(cuts=1),
        )

    transcript_chars, char_to_word = _words_to_normalized_chars(words)
    labeled_cuts: list[LabeledCut] = []
    winners: list[MatchSpan] = []
    ambiguous_items: list[AmbiguousMatch] = []
    prev_word_end = -1
    duplicate_count = 0
    mistake_count = 0

    for si, sentence in enumerate(sentences):
        script_norm = normalize_text(sentence)
        if not script_norm:
            continue

        all_matches = _find_all_matches(
            script_norm,
            transcript_chars,
            char_to_word,
            words,
            min_score=align_config.ambiguous_low,
        )
        ordered = [m for m in all_matches if m.word_start_idx > prev_word_end]
        if not ordered:
            logger.warning("未匹配脚本句 {}: {}", si, sentence[:40])
            continue

        strong = [m for m in ordered if m.score >= align_config.match_threshold]
        if not strong:
            best = max(ordered, key=lambda m: m.score)
            if align_config.ambiguous_low <= best.score < align_config.match_threshold:
                ambiguous_items.append(
                    AmbiguousMatch(
                        script_idx=si,
                        script_text=sentence,
                        candidate_text=_span_text(words, best),
                        score=best.score,
                        start=best.start,
                        end=best.end,
                    )
                )
            logger.warning("低置信匹配 句{} score={:.2f}", si, best.score)
            continue

        winner = _pick_winner(strong)
        winner.script_idx = si
        winner.script_text = sentence

        for m in strong:
            if m.word_start_idx >= winner.word_start_idx:
                continue
            duplicate_count += 1
            reason = "duplicate_take"
            if m.score < winner.score - 0.08:
                mistake_count += 1
                reason = "mistake_retake"
            labeled_cuts.append(LabeledCut(m.start, m.end, reason))

        winners.append(winner)
        prev_word_end = winner.word_end_idx
        logger.debug(
            "WISP 句{} score={:.2f} [{:.2f}-{:.2f}] dup={}",
            si,
            winner.score,
            winner.start,
            winner.end,
            len(strong) - 1,
        )

    llm_verdicts = review_ambiguous_matches(ambiguous_items, config=align_config)
    llm_reviews = 0
    for item in ambiguous_items:
        if llm_verdicts.get(item.script_idx, False):
            llm_reviews += 1
            span = _find_all_matches(
                normalize_text(item.script_text),
                transcript_chars,
                char_to_word,
                words,
                min_score=align_config.ambiguous_low,
            )
            span = [m for m in span if m.word_start_idx > prev_word_end]
            if span:
                w = max(span, key=lambda m: m.score)
                w.script_idx = item.script_idx
                w.script_text = item.script_text
                winners.append(w)
                prev_word_end = w.word_end_idx

    winners.sort(key=lambda w: w.word_start_idx)
    keep_ranges = [
        (w.start, w.end, f"句{w.script_idx + 1}", "matched_script") for w in winners
    ]

    return WispCopyResult(
        keep_ranges=keep_ranges,
        labeled_cuts=labeled_cuts,
        stats=EditStats(
            duplicate_takes=duplicate_count,
            mistake_retakes=mistake_count,
            llm_reviews=llm_reviews,
        ),
    )


def _span_text(words: list[WordToken], span: MatchSpan) -> str:
    return "".join(w.text for w in words[span.word_start_idx : span.word_end_idx + 1])


def align_script_to_transcript(
    script: str,
    transcript: Transcript,
    *,
    align_config: AlignConfig,
    pipeline_config: PipelineConfig,
) -> EditDecision:
    result = wisp_copy_align(
        script,
        transcript,
        align_config=align_config,
        pipeline_config=pipeline_config,
    )

    if not result.keep_ranges and result.labeled_cuts:
        only = result.labeled_cuts[0]
        if only.reason == "empty_transcript":
            return EditDecision(
                total_source_sec=transcript.duration_sec,
                retain_ratio=0.0,
                clips=[
                    EditClip(
                        id="cut_all",
                        action="cut",
                        source_in=only.source_in,
                        source_out=only.source_out,
                        reason=only.reason,
                    )
                ],
                stats=result.stats,
            )

    return build_edit_decision(
        result.keep_ranges,
        transcript.duration_sec,
        pipeline_config,
        labeled_cuts=result.labeled_cuts,
        extra_stats=result.stats,
    )


def build_edit_decision(
    keep_ranges: list[tuple[float, float, str, str]],
    total_duration: float,
    pipeline_config: PipelineConfig,
    *,
    labeled_cuts: list[LabeledCut] | None = None,
    extra_stats: EditStats | None = None,
) -> EditDecision:
    pre = pipeline_config.pre_cut_buffer
    post = pipeline_config.post_cut_buffer
    breath = pipeline_config.breath_gap_sec
    min_keep = pipeline_config.min_keep_sec

    refined: list[tuple[float, float, str, str]] = []
    for i, (start, end, ref, reason) in enumerate(keep_ranges):
        rs = max(0.0, start - pre)
        re = min(total_duration, end + post)
        if i > 0 and refined:
            prev_end = refined[-1][1]
            gap = rs - prev_end
            if 0 < gap < breath:
                rs = prev_end
        if re - rs >= min_keep:
            refined.append((rs, re, ref, reason))

    clips: list[EditClip] = []
    cursor = 0.0
    keep_idx = 0
    cut_idx = 0
    breath_count = 0
    labeled = labeled_cuts or []

    for rs, re, ref, reason in refined:
        if rs > cursor + 0.05:
            cut_idx += 1
            clips.append(
                EditClip(
                    id=f"cut_{cut_idx:03d}",
                    action="cut",
                    source_in=cursor,
                    source_out=rs,
                    reason=_resolve_cut_reason(cursor, rs, labeled),
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
        if keep_idx > 1:
            breath_count += 1
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

    kept = [c for c in clips if c.action == "keep"]
    output_sec = sum(c.source_out - c.source_in for c in kept)
    retain = output_sec / total_duration if total_duration > 0 else 0.0

    stats = extra_stats or EditStats()
    stats.cuts = len([c for c in clips if c.action == "cut"])
    stats.kept_clips = len(kept)
    stats.breath_gaps_applied = breath_count

    return EditDecision(
        total_source_sec=total_duration,
        total_output_sec=output_sec,
        retain_ratio=round(retain, 4),
        clips=clips,
        stats=stats,
    )


def _resolve_cut_reason(start: float, end: float, labeled: list[LabeledCut]) -> str:
    mid = (start + end) / 2
    for cut in labeled:
        if cut.source_in <= mid <= cut.source_out:
            return cut.reason
    overlap_scores: dict[str, float] = {}
    for cut in labeled:
        overlap = max(0.0, min(end, cut.source_out) - max(start, cut.source_in))
        if overlap > 0:
            overlap_scores[cut.reason] = overlap_scores.get(cut.reason, 0) + overlap
    if overlap_scores:
        return max(overlap_scores, key=overlap_scores.get)
    return "gap_or_duplicate"
