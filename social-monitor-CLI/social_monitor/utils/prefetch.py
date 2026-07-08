"""采集前平台就绪检测"""

from typing import Optional

import click

from social_monitor.utils.cookie_checker import check_platform
from social_monitor.utils.cookie_manager import get_cookie, has_browser_session


# 采集前必须通过的检测（Cookie 无效则中断）
STRICT_CHECK = {
    "xiaohongshu": True,
    "zhihu-answers": True,
}

# 有 Cookie 时才检测
COOKIE_OPTIONAL_CHECK = {
    "douyin-user": True,
    "weibo-user": False,
}


def ensure_ready(
    check_key: str,
    platform: str,
    cookie: Optional[str] = None,
    skip: bool = False,
) -> None:
    """采集前检测，失败则抛出 ClickException"""
    if skip:
        return

    needs_strict = STRICT_CHECK.get(check_key, False)
    if check_key == "xiaohongshu":
        if not get_cookie("xiaohongshu", cookie) and not has_browser_session("xiaohongshu"):
            raise click.ClickException(
                "小红书未就绪，请运行: social-monitor config login xiaohongshu"
            )
        needs_strict = True

    if check_key == "zhihu-answers" and not get_cookie("zhihu", cookie):
        raise click.ClickException("知乎回答采集需要 Cookie，请 config cookie set zhihu")

    if check_key == "douyin-user" and not get_cookie("douyin", cookie):
        click.echo("提示: 抖音用户视频采集未配置 Cookie，结果可能为空", err=True)
        return

    if not needs_strict and check_key not in COOKIE_OPTIONAL_CHECK:
        return

    result = check_platform(platform, cookie_override=cookie)
    if not result.ok:
        raise click.ClickException(f"{platform} 未就绪: {result.message}")
