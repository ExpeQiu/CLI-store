import json
from unittest.mock import MagicMock, patch

from social_monitor.platforms.weibo import WeiboCollector


def test_parse_cards():
    collector = WeiboCollector()
    cards = [
        {
            "mblog": {
                "id": "123",
                "text": "测试微博",
                "created_at": "Mon Jun 16 10:00:00 +0800 2026",
                "reposts_count": 1,
                "comments_count": 2,
                "attitudes_count": 3,
                "user": {"screen_name": "test", "followers_count": 100},
                "source": "iPhone",
            }
        }
    ]
    results = collector._parse_cards(cards)
    assert len(results) == 1
    assert results[0]["id"] == "123"
    assert results[0]["text"] == "测试微博"
    assert results[0]["screen_name"] == "test"


def test_fetch_trending_mock():
    mock_resp = MagicMock()
    mock_resp.json.return_value = {
        "data": {
            "realtime": [
                {"rank": 1, "word": "测试热搜", "num": 999, "label_name": "热"}
            ]
        }
    }
    collector = WeiboCollector()
    with patch.object(collector.http_client, "get", return_value=mock_resp):
        trending = collector.fetch_trending(max_count=10)
    assert len(trending) == 1
    assert trending[0]["word"] == "测试热搜"
