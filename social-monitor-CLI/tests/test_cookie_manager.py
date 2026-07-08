import os
from pathlib import Path
from unittest.mock import patch

from social_monitor.utils.cookie_manager import (
    get_cookie,
    get_cookie_source,
    mask_cookie,
    save_cookie,
)


def test_mask_cookie():
    assert mask_cookie("") == "(empty)"
    assert mask_cookie("short") == "***"
    assert mask_cookie("abcdefghijklmnopq") == "abcdefgh...nopq"


def test_cookie_priority(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    import social_monitor.utils.cookie_manager as cm

    monkeypatch.setattr(cm, "CONFIG_DIR", tmp_path / ".social-monitor")
    monkeypatch.setattr(cm, "CONFIG_FILE", tmp_path / ".social-monitor" / "config.yaml")
    monkeypatch.setattr(cm, "COOKIE_DIR", tmp_path / ".social-monitor" / "cookies")

    # CLI override
    assert get_cookie("weibo", override="cli_cookie") == "cli_cookie"

    # env var
    monkeypatch.setenv("SM_WEIBO_COOKIE", "env_cookie")
    assert get_cookie("weibo") == "env_cookie"

    # file
    monkeypatch.delenv("SM_WEIBO_COOKIE", raising=False)
    save_cookie("weibo", "file_cookie")
    assert get_cookie("weibo") == "file_cookie"
    assert "file:" in get_cookie_source("weibo")
