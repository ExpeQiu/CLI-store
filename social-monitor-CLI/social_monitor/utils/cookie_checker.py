from dataclasses import dataclass
from typing import Optional

from social_monitor.utils.cookie_manager import get_cookie, has_browser_session, mask_cookie
from social_monitor.utils.http_client import HttpClient
from social_monitor.utils.logger import setup_logger

logger = setup_logger(__name__)


@dataclass
class CheckResult:
    platform: str
    ok: bool
    message: str
    source: str = ""
    needs_cookie: bool = False


def check_platform(platform: str, cookie_override: Optional[str] = None) -> CheckResult:
    """检测平台 Cookie / 连通性"""
    checkers = {
        "weibo": _check_weibo,
        "xiaohongshu": _check_xiaohongshu,
        "douyin": _check_douyin,
        "zhihu": _check_zhihu,
        "bilibili": _check_bilibili,
        "wechat": _check_wechat,
    }
    checker = checkers.get(platform)
    if not checker:
        return CheckResult(platform, False, f"不支持的平台: {platform}")
    return checker(cookie_override)


def _check_weibo(cookie_override: Optional[str] = None) -> CheckResult:
    """微博：热搜免登录；有 Cookie 时额外探测"""
    from social_monitor.platforms.weibo import WeiboCollector

    source = "public_api"
    try:
        with WeiboCollector() as collector:
            data = collector.fetch_trending(max_count=1)
        if not data:
            return CheckResult("weibo", False, "微博热搜接口无数据", source, needs_cookie=False)
    except Exception as e:
        return CheckResult("weibo", False, f"微博热搜探测失败: {e}", source, needs_cookie=False)

    cookie = get_cookie("weibo", cookie_override)
    if cookie:
        source = "cookie"
        return CheckResult(
            "weibo", True, f"热搜可用，已配置 Cookie ({mask_cookie(cookie)})", source, needs_cookie=False
        )
    return CheckResult("weibo", True, "热搜可用（用户动态采集可选 Cookie）", source, needs_cookie=False)


def _check_xiaohongshu(cookie_override: Optional[str] = None) -> CheckResult:
    """小红书：优先 Playwright 登录态，其次 Cookie"""
    from social_monitor.utils.cookie_manager import get_cookie_source

    source = get_cookie_source("xiaohongshu", cookie_override)

    if has_browser_session("xiaohongshu"):
        try:
            from social_monitor.utils.browser import browser_fetch_json

            data = browser_fetch_json(
                "xiaohongshu",
                "https://edith.xiaohongshu.com/api/sns/web/v1/user/selfinfo",
            )
            if data.get("success"):
                nickname = data.get("data", {}).get("basic_info", {}).get("nickname", "")
                return CheckResult(
                    "xiaohongshu",
                    True,
                    f"浏览器登录态有效{f'，用户: {nickname}' if nickname else ''}",
                    f"browser + {source}",
                    needs_cookie=True,
                )
            return CheckResult(
                "xiaohongshu",
                False,
                f"浏览器登录态无效: {data.get('msg', 'unknown')}",
                source,
                needs_cookie=True,
            )
        except ImportError:
            return CheckResult(
                "xiaohongshu",
                False,
                "需要安装 Playwright: pip install 'social-monitor[browser]' && playwright install chromium",
                source,
                needs_cookie=True,
            )
        except Exception as e:
            return CheckResult("xiaohongshu", False, f"浏览器探测失败: {e}", source, needs_cookie=True)

    cookie = get_cookie("xiaohongshu", cookie_override)
    if not cookie:
        return CheckResult(
            "xiaohongshu",
            False,
            "未配置 Cookie 或浏览器登录态，请运行: social-monitor config login xiaohongshu",
            source,
            needs_cookie=True,
        )

    client = HttpClient(headers={"Cookie": cookie, "Referer": "https://www.xiaohongshu.com/"})
    try:
        resp = client.get("https://edith.xiaohongshu.com/api/sns/web/v1/user/selfinfo")
        data = resp.json()
        if data.get("success"):
            nickname = data.get("data", {}).get("basic_info", {}).get("nickname", "")
            return CheckResult(
                "xiaohongshu",
                True,
                f"Cookie 有效{f'，用户: {nickname}' if nickname else ''}（建议 config login 以支持签名）",
                source,
                needs_cookie=True,
            )
        return CheckResult(
            "xiaohongshu",
            False,
            f"Cookie 无效: {data.get('msg', 'unknown')}，请重新登录或更新 Cookie",
            source,
            needs_cookie=True,
        )
    except Exception as e:
        return CheckResult(
            "xiaohongshu",
            False,
            f"Cookie 探测失败: {e}（建议使用 config login xiaohongshu）",
            source,
            needs_cookie=True,
        )
    finally:
        client.close()


def _check_douyin(cookie_override: Optional[str] = None) -> CheckResult:
    from social_monitor.platforms.douyin import DouYinCollector
    from social_monitor.utils.cookie_manager import get_cookie_source

    source = get_cookie_source("douyin", cookie_override)
    try:
        with DouYinCollector() as collector:
            data = collector.fetch_trending(max_count=1)
        if not data:
            return CheckResult("douyin", False, "抖音热榜无数据", source)
    except Exception as e:
        return CheckResult("douyin", False, f"抖音热榜探测失败: {e}", source)

    cookie = get_cookie("douyin", cookie_override)
    if cookie:
        return CheckResult(
            "douyin", True, f"热榜可用，已配置 Cookie ({mask_cookie(cookie)})", source, needs_cookie=False
        )
    return CheckResult("douyin", True, "热榜可用（用户视频采集需 Cookie）", source, needs_cookie=False)


def _check_zhihu(cookie_override: Optional[str] = None) -> CheckResult:
    from social_monitor.platforms.zhihu import ZhihuCollector
    from social_monitor.utils.cookie_manager import get_cookie_source

    source = get_cookie_source("zhihu", cookie_override)
    try:
        with ZhihuCollector() as collector:
            data = collector.fetch_trending(max_count=1)
        if not data:
            return CheckResult("zhihu", False, "知乎热榜无数据", source)
    except Exception as e:
        return CheckResult("zhihu", False, f"知乎热榜探测失败: {e}", source)

    cookie = get_cookie("zhihu", cookie_override)
    if not cookie:
        return CheckResult("zhihu", True, "热榜可用（高赞回答采集建议配置 Cookie）", source)

    client = HttpClient(headers={"Cookie": cookie, "X-API-VERSION": "3.0.40"})
    try:
        resp = client.get("https://www.zhihu.com/api/v4/me")
        data = resp.json()
        if data.get("name"):
            return CheckResult("zhihu", True, f"Cookie 有效，用户: {data['name']}", source, needs_cookie=False)
        return CheckResult("zhihu", False, "Cookie 无效或已过期", source, needs_cookie=False)
    except Exception as e:
        return CheckResult("zhihu", False, f"Cookie 探测失败: {e}", source, needs_cookie=False)
    finally:
        client.close()


def _check_bilibili(_cookie_override: Optional[str] = None) -> CheckResult:
    from social_monitor.platforms.bilibili import BilibiliCollector

    try:
        with BilibiliCollector() as collector:
            data = collector.fetch_trending(rid=0)
        if data:
            return CheckResult("bilibili", True, "B站排行榜可用（无需 Cookie）", "public_api")
        return CheckResult("bilibili", False, "B站排行榜无数据", "public_api")
    except Exception as e:
        return CheckResult("bilibili", False, f"B站探测失败: {e}", "public_api")


def _check_wechat(_cookie_override: Optional[str] = None) -> CheckResult:
    from social_monitor.config import get_rsshub_url

    url = get_rsshub_url()
    client = HttpClient()
    try:
        resp = client.get(url, headers={"Accept": "text/html"})
        if resp.status_code < 500:
            return CheckResult("wechat", True, f"RSSHub 可达: {url}", "rsshub")
        return CheckResult("wechat", False, f"RSSHub 响应异常: HTTP {resp.status_code}", "rsshub")
    except Exception as e:
        return CheckResult(
            "wechat",
            False,
            f"RSSHub 不可达 ({url}): {e}，请部署 RSSHub 或修改 rsshub_url",
            "rsshub",
        )
    finally:
        client.close()
