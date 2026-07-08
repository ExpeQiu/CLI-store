"""配置读写测试"""

from pathlib import Path

from screen_watch.config import wechat_live_default
from screen_watch.config_io import save_config


def test_save_config_roundtrip(tmp_path: Path) -> None:
    cfg = wechat_live_default()
    path = save_config(cfg, tmp_path / "config.yaml")
    text = path.read_text(encoding="utf-8")
    assert "wechat-live" in text
    assert "viewer_count" in text
