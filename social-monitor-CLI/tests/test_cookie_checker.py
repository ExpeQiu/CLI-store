from unittest.mock import MagicMock, patch

from social_monitor.utils.cookie_checker import CheckResult, check_platform


def test_check_bilibili_ok():
    mock_collector = MagicMock()
    mock_collector.fetch_trending.return_value = [{"title": "test"}]
    mock_collector.__enter__ = MagicMock(return_value=mock_collector)
    mock_collector.__exit__ = MagicMock(return_value=False)

    with patch("social_monitor.platforms.bilibili.BilibiliCollector", return_value=mock_collector):
        result = check_platform("bilibili")
    assert result.ok is True
    assert result.platform == "bilibili"


def test_check_xiaohongshu_no_auth():
    with patch("social_monitor.utils.cookie_manager.has_browser_session", return_value=False):
        with patch("social_monitor.utils.cookie_manager.get_cookie", return_value=None):
            with patch("social_monitor.utils.cookie_manager.get_cookie_source", return_value="none"):
                result = check_platform("xiaohongshu")
    assert result.ok is False
    assert "login" in result.message
