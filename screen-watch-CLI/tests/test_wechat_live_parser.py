"""解析器单元测试"""

import pytest

from screen_watch.parsers.wechat_live import (
    ChatDiffState,
    parse_chat_line,
    parse_viewer_count,
)


class TestViewerCount:
    def test_basic(self):
        r = parse_viewer_count("687人看过", r"(\d+(?:\.\d+)?万?)人(?:看过|观看|在线)")
        assert r is not None
        assert r["viewer_count"] == 687

    def test_wan(self):
        r = parse_viewer_count("1.2万人看过", r"(\d+(?:\.\d+)?万?)人(?:看过|观看|在线)")
        assert r is not None
        assert r["viewer_count"] == 12000


class TestChatLine:
    def test_colon_split(self):
        r = parse_chat_line("张三: 007GT多少钱")
        assert r["user"] == "张三"
        assert r["content"] == "007GT多少钱"

    def test_filter_notice(self):
        r = parse_chat_line("通知: 欢迎来到直播间", drop_prefixes=["通知:"])
        assert r is None


class TestChatDiff:
    def test_diff_new_lines(self):
        state = ChatDiffState(dedup_window=100)
        new = state.diff_lines(["A: hi", "B: hello"])
        assert len(new) == 2
        new2 = state.diff_lines(["A: hi", "B: hello", "C: new"])
        assert new2 == ["C: new"]
