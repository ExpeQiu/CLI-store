"""微博直播页面 DOM 探测脚本，用于调试选择器。"""
from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

ROOM_ID = sys.argv[1] if len(sys.argv) > 1 else "1022:2321325313404713173126"
URL = f"https://weibo.com/l/wblive/p/show/{ROOM_ID}"
AUTH_FILE = PROJECT_ROOT / "auth" / "weibo_state.json"


async def main() -> None:
    from playwright.async_api import async_playwright

    storage_state = str(AUTH_FILE) if AUTH_FILE.exists() else None
    print(f"[probe] room_id={ROOM_ID}")
    print(f"[probe] url={URL}")
    print(f"[probe] auth={'yes' if storage_state else 'no'}")

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        ctx_kwargs = {"storage_state": storage_state} if storage_state else {}
        context = await browser.new_context(**ctx_kwargs)
        page = await context.new_page()

        await page.goto(URL, wait_until="domcontentloaded", timeout=60000)
        await asyncio.sleep(8)

        title = await page.title()
        current_url = page.url
        print(f"[probe] title={title}")
        print(f"[probe] current_url={current_url}")

        screenshot = PROJECT_ROOT / "weibo_debug.png"
        await page.screenshot(path=str(screenshot), full_page=True)
        print(f"[probe] screenshot={screenshot}")

        body_text = await page.evaluate("() => document.body?.innerText?.slice(0, 2000) || ''")
        print(f"[probe] body_text_preview:\n{body_text[:1500]}")

        dom_info = await page.evaluate(
            """() => {
              const chatLike = [];
              const all = document.querySelectorAll('*');
              for (const el of all) {
                const cls = (el.className || '').toString();
                const id = el.id || '';
                if (/chat|message|comment|danmu|barrage|room/i.test(cls + id)) {
                  const text = (el.innerText || '').trim().slice(0, 120);
                  if (text) {
                    chatLike.push({ tag: el.tagName, cls: cls.slice(0, 80), id: id.slice(0, 40), text });
                  }
                }
              }
              return chatLike.slice(0, 40);
            }"""
        )
        print(f"[probe] chat_like_nodes={len(dom_info)}")
        print(json.dumps(dom_info, ensure_ascii=False, indent=2))

        ws_frames = []
        page.on(
            "websocket",
            lambda ws: ws.on(
                "framereceived",
                lambda frame: ws_frames.append(str(frame)[:300]) if len(ws_frames) < 5 else None,
            ),
        )
        await asyncio.sleep(5)
        print(f"[probe] ws_frames_sample={len(ws_frames)}")
        for i, f in enumerate(ws_frames):
            print(f"  frame[{i}]: {f[:200]}")

        await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
