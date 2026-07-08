from typing import Any, Dict, Optional

from social_monitor.utils.cookie_manager import get_browser_dir, save_cookie
from social_monitor.utils.logger import setup_logger

logger = setup_logger(__name__)

LOGIN_URLS = {
    "xiaohongshu": "https://www.xiaohongshu.com",
    "douyin": "https://www.douyin.com",
}

# 登录成功时常见的 Cookie 名
LOGIN_COOKIE_HINTS = {
    "xiaohongshu": {"web_session", "xsecappid"},
    "douyin": {"sessionid", "sessionid_ss", "sid_guard", "uid_tt", "passport_csrf_token"},
}


def _require_playwright():
    try:
        from playwright.sync_api import sync_playwright

        return sync_playwright
    except ImportError as e:
        raise ImportError(
            "Playwright 未安装，请执行:\n"
            "  pip install 'social-monitor[browser]'\n"
            "  playwright install chromium"
        ) from e


def browser_login(platform: str, wait_seconds: int = 300) -> None:
    """打开浏览器供用户手动登录，保存持久化会话"""
    if platform not in LOGIN_URLS:
        raise ValueError(f"不支持 browser login 的平台: {platform}")

    sync_playwright = _require_playwright()
    user_data_dir = get_browser_dir(platform)
    user_data_dir.mkdir(parents=True, exist_ok=True)

    logger.info("启动浏览器登录 platform=%s dir=%s", platform, user_data_dir)
    with sync_playwright() as p:
        context = p.chromium.launch_persistent_context(
            str(user_data_dir),
            headless=False,
            viewport={"width": 1280, "height": 800},
            args=["--disable-blink-features=AutomationControlled"],
        )
        page = context.pages[0] if context.pages else context.new_page()
        page.goto(LOGIN_URLS[platform])

        print(f"\n请在浏览器中完成 {platform} 登录...")
        print(f"登录成功后等待最多 {wait_seconds} 秒自动检测，或关闭浏览器窗口结束。\n")

        # 轮询检测登录状态（小红书：页面出现用户相关 cookie）
        logged_in = False
        cookie_str = ""
        for _ in range(wait_seconds // 2):
            page.wait_for_timeout(2000)
            cookies = context.cookies()
            hints = LOGIN_COOKIE_HINTS.get(platform, set())
            if hints:
                names = {c["name"] for c in cookies}
                if names & hints:
                    logged_in = True
                    break
            if not context.pages:
                break

        cookies = context.cookies()
        domain_filter = "xiaohongshu.com" if platform == "xiaohongshu" else "douyin.com"
        cookie_str = "; ".join(
            f"{c['name']}={c['value']}"
            for c in cookies
            if domain_filter in c.get("domain", "")
        )
        if cookie_str:
            save_cookie(platform, cookie_str)

        context.close()

    if logged_in or cookie_str:
        logger.info("登录态已保存 platform=%s", platform)
    else:
        logger.warning("未检测到明确登录态，请运行 config check %s 验证", platform)


def browser_fetch_json(
    platform: str,
    url: str,
    params: Optional[Dict[str, Any]] = None,
    method: str = "GET",
    body: Optional[Dict[str, Any]] = None,
) -> dict:
    """通过浏览器上下文发起请求，自动携带 Cookie 与签名"""
    if platform not in LOGIN_URLS:
        raise ValueError(f"不支持 browser fetch 的平台: {platform}")

    browser_dir = get_browser_dir(platform)
    if not browser_dir.exists():
        raise RuntimeError(f"请先运行: social-monitor config login {platform}")

    sync_playwright = _require_playwright()
    logger.info("浏览器采集 platform=%s url=%s", platform, url)

    with sync_playwright() as p:
        context = p.chromium.launch_persistent_context(
            str(browser_dir),
            headless=True,
            args=["--disable-blink-features=AutomationControlled"],
        )
        page = context.pages[0] if context.pages else context.new_page()
        page.goto(LOGIN_URLS[platform], wait_until="domcontentloaded", timeout=60000)
        page.wait_for_timeout(2000)

        result = page.evaluate(
            """
            async ({url, params, method, body}) => {
                const u = new URL(url);
                if (params) {
                    Object.entries(params).forEach(([k, v]) => {
                        if (v !== '' && v != null) u.searchParams.set(k, String(v));
                    });
                }
                const opts = {
                    method: method || 'GET',
                    credentials: 'include',
                    headers: { 'Accept': 'application/json', 'Content-Type': 'application/json' },
                };
                if (body && method !== 'GET') {
                    opts.body = JSON.stringify(body);
                }
                const resp = await fetch(u.toString(), opts);
                const text = await resp.text();
                try {
                    return JSON.parse(text);
                } catch {
                    throw new Error('HTTP ' + resp.status + ': ' + text.slice(0, 200));
                }
            }
            """,
            {"url": url, "params": params or {}, "method": method, "body": body},
        )
        context.close()

    return result
