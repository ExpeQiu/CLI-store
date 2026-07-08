"""微博直播：播放后探测弹幕/评论/WebSocket 数据。"""
from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

ROOM_ID = sys.argv[1] if len(sys.argv) > 1 else "1022:2321325313404713173126"
URL = f"https://weibo.com/l/wblive/p/show/{ROOM_ID}"
AUTH_FILE = PROJECT_ROOT / "auth" / "weibo_state.json"


async def main() -> None:
    from playwright.async_api import async_playwright

    ws_logs: list[str] = []
    http_logs: list[str] = []

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(storage_state=str(AUTH_FILE))
        page = await context.new_page()

        def on_ws(ws):
            ws_logs.append(f"WS open: {ws.url}")
            ws.on("framereceived", lambda f: ws_logs.append(f"WS recv: {str(f)[:400]}") if len(ws_logs) < 30 else None)

        page.on("websocket", on_ws)
        page.on("response", lambda r: http_logs.append(f"{r.status} {r.url[:120]}") if "live" in r.url.lower() or "comment" in r.url.lower() or "chat" in r.url.lower() else None)

        await page.goto(URL, wait_until="domcontentloaded", timeout=60000)
        await asyncio.sleep(3)

        # 点击播放
        play_btn = page.locator(".wbpv-big-play-button, .vjs-big-play-button, button[aria-label*='播放']")
        if await play_btn.count() > 0:
            print("[probe] clicking play button")
            await play_btn.first.click()
            await asyncio.sleep(5)
        else:
            print("[probe] no play button, trying video click")
            video = page.locator("video")
            if await video.count() > 0:
                await video.first.click()
                await asyncio.sleep(5)

        await page.screenshot(path=str(PROJECT_ROOT / "weibo_after_play.png"), full_page=True)
        print("[probe] saved weibo_after_play.png")

        body = await page.evaluate("() => document.body.innerText.slice(0, 2500)")
        print(f"[probe] body after play:\n{body[:1800]}")

        nodes = await page.evaluate(
            """() => {
              const out = [];
              for (const el of document.querySelectorAll('[class*="Comment"], [class*="comment"], [class*="chat"], [class*="Chat"], [class*="danmu"], [class*="message"]')) {
                const t = (el.innerText || '').trim();
                if (t && t.length < 200) out.push({cls: el.className.toString().slice(0,100), text: t});
              }
              return out.slice(0, 30);
            }"""
        )
        print("[probe] comment/chat nodes:")
        print(json.dumps(nodes, ensure_ascii=False, indent=2))

        await asyncio.sleep(8)
        print(f"[probe] ws_logs ({len(ws_logs)}):")
        for line in ws_logs[:20]:
            print(" ", line)
        print(f"[probe] http_logs ({len(http_logs)}):")
        for line in http_logs[:20]:
            print(" ", line)

        await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
