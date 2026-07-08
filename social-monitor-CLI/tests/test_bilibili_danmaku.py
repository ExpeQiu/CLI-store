import json
from unittest.mock import MagicMock, patch

import pytest

from social_monitor.platforms.bilibili import BilibiliCollector
from social_monitor.utils.bilibili_live import (
    build_auth_packet,
    pack_packet,
    parse_live_messages,
    unpack_packets,
)
from social_monitor.utils.danmaku_words import extract_danmaku_words

SAMPLE_XML = """<?xml version="1.0" encoding="UTF-8"?>
<i>
  <d p="12.34,1,25,16777215,1700000000,0,abc,0">前方高能</d>
  <d p="20.00,1,25,16777215,1700000001,0,def,0">前方高能预警</d>
  <d p="30.50,1,25,16777215,1700000002,0,ghi,0">awsl</d>
</i>
"""


def test_pack_and_unpack_packet():
    body = b'{"cmd":"DANMU_MSG"}'
    packed = pack_packet(body)
    packets = unpack_packets(packed)
    assert len(packets) == 1
    assert packets[0][2] == body


def test_parse_live_danmaku_message():
    payload = json.dumps(
        {
            "cmd": "DANMU_MSG",
            "info": [
                [0, 1, 25, 16777215, 1, 0, 0, 0, 0],
                "测试弹幕",
                [0, "测试用户", 0, 0, 12345],
            ],
            "roomid": 123,
        },
        ensure_ascii=False,
    ).encode("utf-8")
    raw = pack_packet(payload)
    messages = parse_live_messages(raw)
    assert len(messages) == 1
    assert messages[0]["content"] == "测试弹幕"
    assert messages[0]["user"] == "测试用户"


def test_extract_danmaku_words():
    danmaku = [
        {"content": "前方高能"},
        {"content": "前方高能"},
        {"content": "awsl"},
    ]
    words = extract_danmaku_words(danmaku, top_n=10)
    assert words[0]["word"] == "前方高能"
    assert words[0]["count"] == 2


def test_fetch_video_danmaku_parses_xml():
    collector = BilibiliCollector()
    mock_resp = MagicMock()
    mock_resp.text = SAMPLE_XML
    collector.http_client.get = MagicMock(return_value=mock_resp)

    data = collector.fetch_video_danmaku(cid=12345)
    assert len(data) == 3
    assert data[0]["content"] == "前方高能"
    assert data[0]["platform"] == "bilibili_video"
    collector.close()


def test_fetch_danmaku_words_uses_video_danmaku():
    collector = BilibiliCollector()
    with patch.object(collector, "fetch_video_danmaku", return_value=[
        {"content": "前方高能"},
        {"content": "前方高能"},
    ]):
        words = collector.fetch_danmaku_words(bvid="BV1xx411c7mD", top_n=5)
    assert words[0]["word"] == "前方高能"
    assert words[0]["count"] == 2
    collector.close()


def test_build_auth_packet_contains_room_id():
    packet = build_auth_packet(22603245)
    assert b"22603245" in packet
