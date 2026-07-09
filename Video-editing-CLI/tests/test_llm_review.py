"""LLM 复核测试。"""

from unittest.mock import patch

from video_edit.config import AlignConfig
from video_edit.services.llm_review import AmbiguousMatch, review_ambiguous_matches


def test_llm_review_disabled_returns_keep():
    items = [
        AmbiguousMatch(
            script_idx=0,
            script_text="测试句",
            candidate_text="测试",
            score=0.45,
            start=1.0,
            end=2.0,
        )
    ]
    result = review_ambiguous_matches(items, config=AlignConfig(use_llm_review=False))
    assert result[0] is True


def test_llm_review_mock_api():
    items = [
        AmbiguousMatch(
            script_idx=1,
            script_text="今天我们来聊聊AI辅助剪辑",
            candidate_text="今天我们来聊聊AI辅助视频剪辑",
            score=0.48,
            start=4.0,
            end=6.1,
        )
    ]
    config = AlignConfig(use_llm_review=True, openai_api_key="test-key")

    class FakeResp:
        def raise_for_status(self):
            return None

        def json(self):
            return {"choices": [{"message": {"content": '{"keep": true}'}}]}

    with patch("httpx.post", return_value=FakeResp()):
        result = review_ambiguous_matches(items, config=config)
    assert result[1] is True
