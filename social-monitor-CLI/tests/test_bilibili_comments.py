"""B站评论与 stat 测试"""

from unittest.mock import MagicMock, patch

from social_monitor.platforms.bilibili import BilibiliCollector


def test_fetch_video_stat_parses_fields():
    collector = BilibiliCollector()
    mock_resp = MagicMock()
    mock_resp.json.return_value = {
        "code": 0,
        "data": {
            "bvid": "BV1test",
            "aid": 123,
            "title": "标题",
            "stat": {
                "view": 100,
                "like": 10,
                "coin": 5,
                "favorite": 3,
                "share": 2,
                "reply": 4,
                "danmaku": 6,
            },
        },
    }
    collector.http_client = MagicMock()
    collector.http_client.get.return_value = mock_resp

    stat = collector.fetch_video_stat(bvid="BV1test")
    assert stat["view"] == 100
    assert stat["coin"] == 5
    assert stat["danmaku"] == 6


def test_fetch_hot_comments_includes_id():
    collector = BilibiliCollector()
    mock_resp = MagicMock()
    mock_resp.json.return_value = {
        "data": {
            "replies": [
                {
                    "rpid": 999,
                    "member": {"uname": "用户"},
                    "content": {"message": "评论"},
                    "like": 1,
                    "ctime": 0,
                }
            ]
        }
    }
    collector.http_client = MagicMock()
    collector.http_client.get.return_value = mock_resp

    comments = collector.fetch_hot_comments(123, limit=10)
    assert len(comments) == 1
    assert comments[0]["id"] == "999"
    assert comments[0]["content"] == "评论"
