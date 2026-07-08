"""解析前登录态检查：抖音 / 小红书需登录后搜索用户"""

from __future__ import annotations

from typing import Callable, Dict, List, Optional, Set

from social_monitor.account.registry import AccountEntry
from social_monitor.utils.cookie_checker import check_platform
from social_monitor.utils.cookie_manager import get_cookie, has_browser_session
from social_monitor.utils.logger import setup_logger

logger = setup_logger(__name__)

LOGIN_PLATFORMS: Dict[str, Dict[str, str]] = {
    "douyin": {
        "label": "抖音",
        "hint": "用户搜索需登录，将打开浏览器扫码/验证码登录",
    },
    "xiaohongshu": {
        "label": "小红书",
        "hint": "用户搜索需登录，将打开浏览器完成登录（推荐 Playwright 会话）",
    },
}


def platform_auth_ready(platform: str) -> bool:
    """平台是否具备搜索用户所需的登录态"""
    if platform == "douyin":
        return bool(get_cookie("douyin"))
    if platform == "xiaohongshu":
        if has_browser_session("xiaohongshu"):
            result = check_platform("xiaohongshu")
            return result.ok
        return bool(get_cookie("xiaohongshu"))
    return True


def platforms_needing_login(entries: List[AccountEntry]) -> Set[str]:
    needed = {e.platform_key for e in entries if e.platform_key in LOGIN_PLATFORMS}
    return {p for p in needed if not platform_auth_ready(p)}


def ensure_login_for_entries(
    entries: List[AccountEntry],
    *,
    interactive: bool = True,
    login_fn: Optional[Callable[[str], None]] = None,
) -> List[str]:
    """
    确保待解析条目涉及的平台已登录。
    返回已完成登录流程的平台 key 列表。
    """
    missing = sorted(platforms_needing_login(entries))
    if not missing:
        logger.info("抖音/小红书登录态已就绪，跳过登录")
        return []

    logged_in: List[str] = []
    for platform in missing:
        meta = LOGIN_PLATFORMS[platform]
        logger.info("需要登录 platform=%s (%s)", platform, meta["label"])

        if not interactive:
            raise RuntimeError(
                f"{meta['label']} 未登录，请先执行: social-monitor config login {platform}"
            )

        try:
            import click

            click.echo(f"\n>>> {meta['label']}：{meta['hint']}", err=True)
            if not click.confirm(f"是否现在登录 {meta['label']}？", default=True):
                click.echo(f"已跳过 {meta['label']}，相关账号将标记为 missing_login", err=True)
                continue
        except ImportError:
            pass

        if login_fn:
            login_fn(platform)
        else:
            from social_monitor.utils.browser import browser_login

            browser_login(platform)

        if platform_auth_ready(platform):
            result = check_platform(platform)
            logger.info("%s 登录完成: %s", meta["label"], result.message)
            logged_in.append(platform)
        else:
            logger.warning("%s 登录后仍未检测到有效 Cookie/会话", meta["label"])

    still_missing = platforms_needing_login(entries)
    if still_missing and interactive:
        names = "、".join(LOGIN_PLATFORMS[p]["label"] for p in sorted(still_missing))
        logger.warning("以下平台仍未就绪，相关条目将跳过: %s", names)

    return logged_in
