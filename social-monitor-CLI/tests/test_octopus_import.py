"""Octopus 导入测试"""

import json
from pathlib import Path
from unittest.mock import MagicMock

from social_monitor.importers.octopus import import_octopus_file, normalize_octopus_items


def test_normalize_octopus_list():
    raw = [{"content": "hello", "user": "u1", "timestamp": 1}]
    items = normalize_octopus_items(raw, "douyin", "live_danmaku", room_id="99")
    assert len(items) == 1
    assert items[0]["text"] == "hello"
    assert items[0]["room_id"] == "99"


def test_import_octopus_file(tmp_path):
    f = tmp_path / "live.json"
    f.write_text(json.dumps([{"content": "弹幕", "user": "A"}]), encoding="utf-8")
    storage = MagicMock()
    storage.save.return_value = 1

    count = import_octopus_file(
        f,
        platform="douyin",
        content_type="live_danmaku",
        account_id="live_123",
        storage=storage,
    )
    assert count == 1
    storage.save.assert_called_once()
