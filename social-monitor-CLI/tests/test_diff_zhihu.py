from unittest.mock import MagicMock, patch

from social_monitor.utils.diff_helper import diff_items, item_key


def test_item_key():
    assert item_key({"id": "123", "title": "a"}) == "123"
    assert item_key({"word": "热搜"}) == "热搜"


def test_diff_items():
    existing = [{"id": "1", "title": "a"}, {"id": "2", "title": "b"}]
    new = [{"id": "2", "title": "b"}, {"id": "3", "title": "c"}]
    added, merged = diff_items(existing, new)
    assert len(added) == 1
    assert added[0]["id"] == "3"
    assert len(merged) == 3


def test_zhihu_fetch_trending_mock():
    mock_resp = MagicMock()
    mock_resp.json.return_value = {
        "data": [
            {
                "target": {
                    "id": 123,
                    "title": "测试问题",
                    "type": "question",
                    "answer_count": 10,
                    "follower_count": 100,
                    "url": "https://api.zhihu.com/questions/123",
                },
                "detail_text": "100 万热度",
                "card_label": {"type": "hot"},
            }
        ]
    }
    from social_monitor.platforms.zhihu import ZhihuCollector

    collector = ZhihuCollector()
    with patch.object(collector.http_client, "get", return_value=mock_resp):
        trending = collector.fetch_trending(max_count=5)
    assert len(trending) == 1
    assert trending[0]["title"] == "测试问题"
    assert trending[0]["url"] == "https://www.zhihu.com/question/123"
