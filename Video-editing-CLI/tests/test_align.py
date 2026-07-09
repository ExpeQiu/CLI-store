"""对齐引擎测试。"""

from video_edit.config import AlignConfig, PipelineConfig
from video_edit.demo.fixtures import DEMO_SCRIPT, DEMO_TRANSCRIPT
from video_edit.services.align import align_script_to_transcript


def test_demo_align_keeps_script_sentences():
    decision = align_script_to_transcript(
        DEMO_SCRIPT,
        DEMO_TRANSCRIPT,
        align_config=AlignConfig(match_threshold=0.5),
        pipeline_config=PipelineConfig(),
    )
    kept = decision.keep_clips()
    assert len(kept) >= 3
    assert decision.retain_ratio > 0
    assert decision.stats.kept_clips == len(kept)


def test_align_produces_cut_regions():
    decision = align_script_to_transcript(
        DEMO_SCRIPT,
        DEMO_TRANSCRIPT,
        align_config=AlignConfig(),
        pipeline_config=PipelineConfig(),
    )
    assert decision.stats.cuts >= 1
    total = decision.total_output_sec + sum(
        c.source_out - c.source_in for c in decision.cut_clips()
    )
    assert abs(total - decision.total_source_sec) < 1.0
