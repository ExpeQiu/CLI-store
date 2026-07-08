"""需扫码登录平台的统一登录流程。"""
from __future__ import annotations

import asyncio
import os
from typing import Awaitable, Callable, Dict, Optional

import typer
from playwright.async_api import Browser, BrowserContext, Page, Playwright, async_playwright

LOGIN_WAIT_SECONDS = 300
LOGIN_POLL_INTERVAL = 2
LOGIN_MAX_POLLS = LOGIN_WAIT_SECONDS // LOGIN_POLL_INTERVAL

PLATFORM_CONFIG: Dict[str, Dict[str, str]] = {
    "weibo": {
        "name": "微博",
        "login_url": "https://weibo.com/login.php",
        "success_hint": "微博直播 IM 登录态验证通过",
    },
    "sph": {
        "name": "视频号",
        "login_url": "https://channels.weixin.qq.com",
        "success_hint": "视频号登录态验证通过",
    },
}

LoginChecker = Callable[[Page], Awaitable[bool]]


async def _check_weibo_login(page: Page) -> bool:
    if "login" in page.url:
        return False
    if page.url.rstrip("/") not in ("https://weibo.com", "https://www.weibo.com"):
        await page.goto("https://weibo.com", wait_until="domcontentloaded")
        await asyncio.sleep(1)
    return await page.evaluate(
        """async () => {
          try {
            const resp = await fetch(
              '/l/!/2/wblive/room/get_access_token.json?live_id=1022:2321325313404713173126',
              { credentials: 'include' }
            );
            const data = await resp.json();
            return data && data.code === 100000;
          } catch { return false; }
        }"""
    )


async def _check_sph_login(page: Page) -> bool:
    if "login" in page.url.lower():
        return False
    return await page.evaluate(
        """() => {
          const text = document.body?.innerText || '';
          if (text.includes('扫码登录') || text.includes('微信登录') || text.includes('请使用微信扫描二维码')) {
            return false;
          }
          return location.hostname.includes('channels.weixin.qq.com');
        }"""
    )


LOGIN_CHECKERS: Dict[str, LoginChecker] = {
    "weibo": _check_weibo_login,
    "sph": _check_sph_login,
}


async def _save_state(context: BrowserContext, auth_file: str) -> None:
    await context.storage_state(path=auth_file)
    typer.echo(f"✅ 登录状态已保存至: {auth_file}")


async def _wait_user_confirm() -> None:
    typer.echo(
        f"🔓 登录窗口保持打开（最多等待 {LOGIN_WAIT_SECONDS // 60} 分钟）。"
        "请在浏览器中完成登录并确认无误后，回到终端按 Enter 保存并关闭。"
    )
    await asyncio.get_event_loop().run_in_executor(None, input)


async def run_platform_login(platform_name: str, auth_file: str) -> None:
    config = PLATFORM_CONFIG[platform_name]
    checker = LOGIN_CHECKERS[platform_name]

    browser: Optional[Browser] = None
    context: Optional[BrowserContext] = None
    playwright: Optional[Playwright] = None

    try:
        typer.echo(f"🚀 正在启动 {config['name']} 登录窗口，请在弹出的 Chromium 中完成扫码...")
        playwright = await async_playwright().start()
        browser = await playwright.chromium.launch(headless=False)

        context_kwargs: Dict[str, str] = {}
        if os.path.exists(auth_file):
            context_kwargs["storage_state"] = auth_file
        context = await browser.new_context(**context_kwargs)
        page = await context.new_page()
        await page.goto(config["login_url"], wait_until="domcontentloaded")

        typer.echo(
            f"⏳ 请在 {LOGIN_WAIT_SECONDS // 60} 分钟内完成登录"
            f"（使用弹出的 Chromium，不是系统浏览器）。"
        )

        logged_in = False
        for poll in range(1, LOGIN_MAX_POLLS + 1):
            await asyncio.sleep(LOGIN_POLL_INTERVAL)
            if await checker(page):
                logged_in = True
                await asyncio.sleep(2)
                await _save_state(context, auth_file)
                typer.echo(f"✅ {config['success_hint']}")
                break
            if poll % 15 == 0:
                remaining = LOGIN_WAIT_SECONDS - poll * LOGIN_POLL_INTERVAL
                typer.echo(f"⏳ 仍在等待登录... 剩余约 {max(0, remaining // 60)} 分钟")

        if not logged_in:
            typer.echo(
                f"⚠️ {LOGIN_WAIT_SECONDS // 60} 分钟内未检测到登录成功，"
                "仍将保存当前浏览器状态供后续尝试。"
            )
            await _save_state(context, auth_file)

        await _wait_user_confirm()
        await _save_state(context, auth_file)
    except KeyboardInterrupt:
        typer.echo("\n🛑 收到中断信号，正在保存当前浏览器状态...")
        if context:
            await _save_state(context, auth_file)
    finally:
        if browser:
            await browser.close()
        if playwright:
            await playwright.stop()
