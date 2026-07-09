"""WISP-COPY 重复 take 检测测试。"""

from video_edit.config import AlignConfig, PipelineConfig
from video_edit.demo.fixtures import DEMO_SCRIPT, DEMO_TRANSCRIPT
from video_edit.services.align import align_script_to_transcript, wisp_copy_align


def test_wisp_copy_detects_duplicate_takes():
    result = wisp_copy_align(
        DEMO_SCRIPT,
        DEMO_TRANSCRIPT,
        align_config=AlignConfig(match_threshold=0.5),
        pipeline_config=PipelineConfig(),
    )
    assert result.stats.duplicate_takes >= 1
    reasons = {c.reason for c in result.labeled_cuts}
    assert "duplicate_take" in reasons or "mistake_retake" in reasons


def test_wisp_copy_keeps_last_take_for_sentence():
    decision = align_script_to_transcript(
        DEMO_SCRIPT,
        DEMO_TRANSCRIPT,
        align_config=AlignConfig(match_threshold=0.5),
        pipeline_config=PipelineConfig(),
    )
    kept = decision.keep_clips()
    first_keep = kept[0]
    # 最后一次 take 约 8.0s 起，而非 1.0s 或 4.0s
    assert first_keep.source_in >= 7.5
