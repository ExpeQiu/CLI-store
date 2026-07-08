"""监控任务采集路径：social-monitor 直采 vs Octopus 模板"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

BACKEND_SM = "social_monitor"
BACKEND_OCTOPUS = "octopus"


@dataclass(frozen=True)
class TaskRoute:
    """单条监控任务的推荐采集路径"""

    key: str
    label: str
    platform: str
    recommended: str
    content_type: str
    sm_cli_hint: str
    reason: str
    octopus_template: Optional[str] = None
    fallback: Optional[str] = None
    octopus_args: tuple[str, ...] = field(default_factory=tuple)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "key": self.key,
            "label": self.label,
            "platform": self.platform,
            "recommended": self.recommended,
            "fallback": self.fallback,
            "octopus_template": self.octopus_template,
            "content_type": self.content_type,
            "sm_cli_hint": self.sm_cli_hint,
            "reason": self.reason,
            "octopus_args": list(self.octopus_args),
        }


# 默认推荐路径（可被 monitor.yaml routes 覆盖）
TASK_ROUTES: Dict[str, TaskRoute] = {
    "weibo:trending": TaskRoute(
        key="weibo:trending",
        label="微博日热搜",
        platform="weibo",
        recommended=BACKEND_SM,
        octopus_template="weibo-trending",
        content_type="trending",
        sm_cli_hint="fetch weibo-trending --date --save",
        reason="公开 API 轻量，日快照 1 次即可",
        fallback=BACKEND_OCTOPUS,
        octopus_args=("--date",),
    ),
    "weibo:user_timeline": TaskRoute(
        key="weibo:user_timeline",
        label="微博用户动态",
        platform="weibo",
        recommended=BACKEND_SM,
        octopus_template="weibo-user-posts",
        content_type="user_timeline",
        sm_cli_hint="fetch weibo --uid --pages 1 --save --diff",
        reason="API 直采稳定、成本低",
        fallback=BACKEND_OCTOPUS,
        octopus_args=("--uid",),
    ),
    "wechat:articles": TaskRoute(
        key="wechat:articles",
        label="公众号文章",
        platform="wechat",
        recommended=BACKEND_SM,
        octopus_template="wechat-articles",
        content_type="articles",
        sm_cli_hint="fetch wechat --wxid --save --diff",
        reason="RSSHub 链路简单；Octopus 作 Cookie/反爬兜底",
        fallback=BACKEND_OCTOPUS,
        octopus_args=("--wxid",),
    ),
    "bilibili:videos": TaskRoute(
        key="bilibili:videos",
        label="B站 UP 视频",
        platform="bilibili",
        recommended=BACKEND_SM,
        octopus_template="bilibili-up-videos",
        content_type="videos",
        sm_cli_hint="fetch bilibili --uid --save --diff",
        reason="公开 API 满足日更监控",
        fallback=BACKEND_OCTOPUS,
        octopus_args=("--uid",),
    ),
    "bilibili:video_stat": TaskRoute(
        key="bilibili:video_stat",
        label="B站视频互动数据",
        platform="bilibili",
        recommended=BACKEND_SM,
        content_type="video_stat",
        sm_cli_hint="fetch bilibili-comments（含 stat）",
        reason="增量新视频附带拉取",
        fallback=None,
    ),
    "bilibili:danmaku_words": TaskRoute(
        key="bilibili:danmaku_words",
        label="B站弹幕词云",
        platform="bilibili",
        recommended=BACKEND_SM,
        octopus_template="bilibili-danmaku",
        content_type="danmaku_words",
        sm_cli_hint="fetch bilibili-danmaku --bvid --words",
        reason="API 直采弹幕 XML",
        fallback=BACKEND_OCTOPUS,
        octopus_args=("--bvid",),
    ),
    "bilibili:comments": TaskRoute(
        key="bilibili:comments",
        label="B站视频评论",
        platform="bilibili",
        recommended=BACKEND_SM,
        octopus_template="bilibili-comments",
        content_type="comments",
        sm_cli_hint="fetch bilibili-comments --bvid --limit 20",
        reason="热评 API 稳定",
        fallback=BACKEND_OCTOPUS,
        octopus_args=("--bvid",),
    ),
    "bilibili:live_danmaku": TaskRoute(
        key="bilibili:live_danmaku",
        label="B站直播弹幕",
        platform="bilibili",
        recommended=BACKEND_SM,
        content_type="live_danmaku",
        sm_cli_hint="fetch live-danmaku --room-id --duration 1800",
        reason="WebSocket 直采，无需浏览器",
        fallback=None,
    ),
    "douyin:videos": TaskRoute(
        key="douyin:videos",
        label="抖音账号视频",
        platform="douyin",
        recommended=BACKEND_SM,
        octopus_template="douyin-user-videos",
        content_type="videos",
        sm_cli_hint="fetch douyin --sec-uid --save --diff",
        reason="Cookie + API 可满足日更",
        fallback=BACKEND_OCTOPUS,
        octopus_args=("--sec-uid",),
    ),
    "douyin:comments": TaskRoute(
        key="douyin:comments",
        label="抖音视频评论",
        platform="douyin",
        recommended=BACKEND_SM,
        octopus_template="douyin-comments",
        content_type="comments",
        sm_cli_hint="fetch douyin-comments --aweme-id",
        reason="默认 sm 直采；反爬加重时可切 Octopus",
        fallback=BACKEND_OCTOPUS,
        octopus_args=("--aweme-id",),
    ),
    "douyin:live_danmaku": TaskRoute(
        key="douyin:live_danmaku",
        label="抖音直播弹幕",
        platform="douyin",
        recommended=BACKEND_OCTOPUS,
        octopus_template="douyin-live-danmaku",
        content_type="live_danmaku",
        sm_cli_hint="（不支持直采）import octopus",
        reason="无 WebSocket 直采能力，固定走 Octopus",
        fallback=None,
        octopus_args=("--room-id",),
    ),
    "xiaohongshu:topic_search": TaskRoute(
        key="xiaohongshu:topic_search",
        label="小红书主题搜索",
        platform="xiaohongshu",
        recommended=BACKEND_SM,
        octopus_template="xhs-keyword-search",
        content_type="topic_notes",
        sm_cli_hint="fetch xiaohongshu-search --keyword --save --diff",
        reason="默认 Playwright；频繁 403 时可切 Octopus",
        fallback=BACKEND_OCTOPUS,
        octopus_args=("--keyword",),
    ),
    "xiaohongshu:comments": TaskRoute(
        key="xiaohongshu:comments",
        label="小红书笔记评论",
        platform="xiaohongshu",
        recommended=BACKEND_SM,
        octopus_template="xhs-comments",
        content_type="comments",
        sm_cli_hint="fetch xiaohongshu-comments --note-id",
        reason="与主题搜索同路径策略",
        fallback=BACKEND_OCTOPUS,
        octopus_args=("--note-id",),
    ),
    "xiaohongshu:user_notes": TaskRoute(
        key="xiaohongshu:user_notes",
        label="小红书用户笔记",
        platform="xiaohongshu",
        recommended=BACKEND_SM,
        octopus_template="xhs-user-notes",
        content_type="user_notes",
        sm_cli_hint="fetch xiaohongshu --user-id",
        reason="用户维度采集",
        fallback=BACKEND_OCTOPUS,
        octopus_args=("--user-id",),
    ),
}


def list_task_routes() -> List[Dict[str, Any]]:
    return [r.to_dict() for r in TASK_ROUTES.values()]


def get_task_route(key: str) -> Optional[TaskRoute]:
    return TASK_ROUTES.get(key)


def _route_override_map(monitor_cfg: Dict[str, Any]) -> Dict[str, str]:
    """合并全局 routes 与各平台 routes 子配置"""
    merged: Dict[str, str] = {}
    global_routes = monitor_cfg.get("routes") or {}
    for k, v in global_routes.items():
        if v in (BACKEND_SM, BACKEND_OCTOPUS):
            merged[str(k)] = v

    for platform, section in monitor_cfg.items():
        if not isinstance(section, dict):
            continue
        plat_routes = section.get("routes") or {}
        for task, backend in plat_routes.items():
            if backend not in (BACKEND_SM, BACKEND_OCTOPUS):
                continue
            key = task if ":" in str(task) else f"{platform}:{task}"
            merged[key] = backend
    return merged


def _template_override_map(monitor_cfg: Dict[str, Any]) -> Dict[str, str]:
    merged: Dict[str, str] = {}
    octopus_section = monitor_cfg.get("octopus") or {}
    templates = octopus_section.get("templates") or {}
    for k, v in templates.items():
        if v:
            merged[str(k)] = str(v)

    for platform, section in monitor_cfg.items():
        if not isinstance(section, dict):
            continue
        for field in ("octopus_templates", "octopus_live_template"):
            if field == "octopus_live_template" and section.get(field):
                merged["douyin:live_danmaku"] = str(section[field])
            tpl_map = section.get("octopus_templates") or {}
            for task, tpl in tpl_map.items():
                if tpl:
                    key = task if ":" in str(task) else f"{platform}:{task}"
                    merged[key] = str(tpl)
    return merged


def resolve_backend(route_key: str, monitor_cfg: Dict[str, Any]) -> str:
    overrides = _route_override_map(monitor_cfg)
    if route_key in overrides:
        return overrides[route_key]
    route = TASK_ROUTES.get(route_key)
    if route:
        return route.recommended
    return BACKEND_SM


def resolve_octopus_template(route_key: str, monitor_cfg: Dict[str, Any]) -> Optional[str]:
    overrides = _template_override_map(monitor_cfg)
    if route_key in overrides:
        return overrides[route_key]
    route = TASK_ROUTES.get(route_key)
    return route.octopus_template if route else None


def resolve_route(route_key: str, monitor_cfg: Dict[str, Any]) -> Dict[str, Any]:
    route = TASK_ROUTES.get(route_key)
    if not route:
        return {
            "key": route_key,
            "backend": BACKEND_SM,
            "recommended": BACKEND_SM,
            "fallback": None,
            "octopus_template": None,
            "content_type": "unknown",
        }

    backend = resolve_backend(route_key, monitor_cfg)
    return {
        "key": route.key,
        "label": route.label,
        "platform": route.platform,
        "backend": backend,
        "recommended": route.recommended,
        "fallback": route.fallback,
        "octopus_template": resolve_octopus_template(route_key, monitor_cfg),
        "content_type": route.content_type,
        "sm_cli_hint": route.sm_cli_hint,
        "reason": route.reason,
        "octopus_args": list(route.octopus_args),
    }


def build_octopus_cli_args(route_key: str, ctx: Dict[str, Any]) -> List[str]:
    """根据路由定义与上下文拼 Octopus CLI 参数"""
    route = TASK_ROUTES.get(route_key)
    if not route:
        return []

    args: List[str] = []
    for flag in route.octopus_args:
        param = flag.lstrip("-").replace("-", "_")
        value = ctx.get(param)
        if value is None:
            continue
        args.extend([flag, str(value)])
    return args


def get_octopus_cli(monitor_cfg: Dict[str, Any]) -> str:
    octopus_section = monitor_cfg.get("octopus") or {}
    for section in monitor_cfg.values():
        if isinstance(section, dict) and section.get("octopus_cli"):
            return str(section["octopus_cli"])
    return str(octopus_section.get("cli", "octopus"))
