from unittest.mock import MagicMock, patch

from social_monitor.platforms.bilibili import BilibiliCollector
from social_monitor.utils.bilibili_wbi import (
    get_mixin_key,
    sign_wbi_params,
    BilibiliWbiSigner,
)


def test_get_mixin_key():
    orig = "7cd084941338484aae1ad7825bcc1b34" + "4932caff0ff746eab6f01bf08b70ac45"
    key = get_mixin_key(orig)
    assert len(key) == 32
    assert key == get_mixin_key(orig)


def test_sign_wbi_params_adds_rid_and_wts():
    signed = sign_wbi_params(
        {"mid": 1, "pn": 1},
        img_key="7cd084941338484aae1ad7825bcc1b34",
        sub_key="4932caff0ff746eab6f01bf08b70ac45",
    )
    assert "w_rid" in signed
    assert "wts" in signed
    assert len(signed["w_rid"]) == 32


def test_wbi_signer_fetches_keys_from_nav():
    mock_client = MagicMock()
    mock_resp = MagicMock()
    mock_resp.json.return_value = {
        "data": {
            "wbi_img": {
                "img_url": "https://i0.hdslb.com/bfs/wbi/7cd084941338484aae1ad7825bcc1b34.png",
                "sub_url": "https://i0.hdslb.com/bfs/wbi/4932caff0ff746eab6f01bf08b70ac45.png",
            }
        }
    }
    mock_client.get.return_value = mock_resp

    signer = BilibiliWbiSigner(mock_client)
    img_key, sub_key = signer.get_keys()
    assert img_key == "7cd084941338484aae1ad7825bcc1b34"
    assert sub_key == "4932caff0ff746eab6f01bf08b70ac45"


def test_fetch_live_danmaku_returns_empty_when_offline():
    collector = BilibiliCollector()
    with patch.object(
        collector,
        "fetch_live_room_info",
        return_value={
            "room_id": 22603245,
            "title": "测试房间",
            "live_status": 0,
        },
    ):
        data = collector.fetch_live_danmaku(22603245, duration=5)
    assert data == []
    collector.close()


def test_fetch_user_videos_uses_wbi_when_available():
    collector = BilibiliCollector()
    sample = {
        "code": 0,
        "data": {
            "list": {
                "vlist": [
                    {
                        "bvid": "BV1test0000",
                        "title": "测试视频",
                        "description": "",
                        "pic": "",
                        "length": "03:00",
                        "play": 100,
                        "comment": 1,
                        "created": 1700000000,
                    }
                ]
            }
        },
    }
    with patch.object(collector, "_request_wbi_json", return_value=sample) as mock_wbi:
        videos = collector.fetch_user_videos(614946423)
    assert len(videos) == 1
    assert videos[0]["bvid"] == "BV1test0000"
    mock_wbi.assert_called_once()
    assert "wbi/arc/search" in mock_wbi.call_args[0][0]
    collector.close()


def test_fetch_user_videos_falls_back_to_arc_list():
    collector = BilibiliCollector()
    archive = {
        "bvid": "BV1fallback",
        "title": "回退视频",
        "pic": "",
        "duration": 90,
        "pubdate": 1700000000,
        "stat": {"view": 10, "reply": 1},
    }
    mock_resp = MagicMock()
    mock_resp.json.return_value = {"code": 0, "data": {"archives": [archive]}}
    with patch.object(collector, "_request_wbi_json", return_value=None):
        with patch.object(collector.http_client, "get", return_value=mock_resp):
            videos = collector.fetch_user_videos(1573049)
    assert len(videos) == 1
    assert videos[0]["bvid"] == "BV1fallback"
    collector.close()
