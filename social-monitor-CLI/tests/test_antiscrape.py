"""反爬配置与请求计数测试"""

from social_monitor.utils.rate_limit_config import build_rate_limiter, get_rate_limit_settings
from social_monitor.utils.request_tracker import get_today_count, increment_request_count


def test_safe_mode_intervals(monkeypatch):
    monkeypatch.setattr(
        "social_monitor.utils.rate_limit_config.load_config",
        lambda: {"rate_limit": {"mode": "safe"}},
    )
    s = get_rate_limit_settings()
    assert s["min_interval"] == 10.0
    assert s["max_interval"] == 20.0
    rl = build_rate_limiter()
    assert rl.min_interval == 10.0


def test_request_counter(tmp_path, monkeypatch):
    from social_monitor.utils import request_tracker

    counter_file = tmp_path / "request_count.txt"
    monkeypatch.setattr(request_tracker, "COUNTER_FILE", counter_file)
    monkeypatch.setattr(request_tracker, "COUNTER_DIR", tmp_path)

    assert get_today_count() == 0
    assert increment_request_count() == 1
    assert get_today_count() == 1
