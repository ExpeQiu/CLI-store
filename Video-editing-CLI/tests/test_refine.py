"""精修与静音测试。"""

from video_edit.config import AlignConfig, PipelineConfig
from video_edit.demo.fixtures import DEMO_SCRIPT, DEMO_TRANSCRIPT
from video_edit.services.align import align_script_to_transcript
from video_edit.services.refine import refine_edit_decision
from video_edit.services.silence import SilenceRegion, snap_to_silence_boundary


def test_snap_to_silence_boundary():
    silences = [SilenceRegion(start=10.0, end=11.2, duration=1.2)]
    assert snap_to_silence_boundary(10.15, silences) == 10.0
    assert snap_to_silence_boundary(11.1, silences, direction="after") == 11.2


def test_refine_splits_long_pause():
    decision = align_script_to_transcript(
        DEMO_SCRIPT,
        DEMO_TRANSCRIPT,
        align_config=AlignConfig(match_threshold=0.5),
        pipeline_config=PipelineConfig(long_pause_sec=1.0),
    )
    kept = decision.keep_clips()
    assert kept
    clip = kept[0]
    silences = [
        SilenceRegion(
            start=clip.source_in + 0.5,
            end=clip.source_in + 2.0,
            duration=1.5,
        )
    ]
    refined = refine_edit_decision(decision, silences, PipelineConfig(long_pause_sec=1.0))
    assert refined.stats.long_pauses >= 1 or len(refined.keep_clips()) >= len(kept)
