"""采集路径注册与解析测试"""

from social_monitor.monitor.routes import (
    BACKEND_OCTOPUS,
    BACKEND_SM,
    build_octopus_cli_args,
    resolve_backend,
    resolve_route,
)


def test_default_douyin_live_is_octopus():
    assert resolve_backend("douyin:live_danmaku", {}) == BACKEND_OCTOPUS


def test_route_override_global():
    cfg = {"routes": {"xiaohongshu:topic_search": BACKEND_OCTOPUS}}
    assert resolve_backend("xiaohongshu:topic_search", cfg) == BACKEND_OCTOPUS


def test_route_override_platform_section():
    cfg = {"douyin": {"routes": {"comments": BACKEND_OCTOPUS}}}
    assert resolve_backend("douyin:comments", cfg) == BACKEND_OCTOPUS


def test_template_override():
    cfg = {
        "octopus": {"templates": {"douyin:live_danmaku": "custom-live-tpl"}},
    }
    resolved = resolve_route("douyin:live_danmaku", cfg)
    assert resolved["octopus_template"] == "custom-live-tpl"


def test_build_octopus_args():
    args = build_octopus_cli_args("douyin:live_danmaku", {"room_id": "99"})
    assert args == ["--room-id", "99"]


def test_weibo_defaults_sm():
    assert resolve_backend("weibo:user_timeline", {}) == BACKEND_SM
    route = resolve_route("weibo:user_timeline", {})
    assert route["fallback"] == BACKEND_OCTOPUS
