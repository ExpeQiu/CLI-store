from typing import Any, Dict, List

from social_monitor.utils.http_client import HttpClient
from social_monitor.utils.logger import setup_logger

logger = setup_logger(__name__)


class FeishuNotifier:
    """飞书 Webhook 通知"""

    def __init__(self, webhook_url: str):
        self.webhook_url = webhook_url
        self.http_client = HttpClient()

    def send(self, msg_type: str, content: dict) -> dict:
        payload = {"msg_type": msg_type, "content": content}
        logger.info("发送飞书通知 type=%s", msg_type)
        resp = self.http_client.post(self.webhook_url, json=payload)
        return resp.json()

    def notify_new_content(
        self, platform: str, count: int, items: List[Dict[str, Any]], account_name: str = ""
    ) -> None:
        if not items:
            return

        name = account_name or platform
        content = f"📢 **{name}** ({platform}) 新增 {count} 条动态\n\n"
        for item in items[:5]:
            title = item.get("title", item.get("text", ""))[:50]
            content += f"• {title}...\n"

        self.send("text", {"text": content})

    def notify_trending(self, platform: str, items: List[Dict[str, Any]]) -> None:
        if not items:
            return

        content = f"🔥 **{platform}** 热榜 TOP {len(items)}\n\n"
        for i, item in enumerate(items[:10], 1):
            word = item.get("word", item.get("title", ""))
            hot_value = item.get("hot_value", item.get("view", 0))
            content += f"{i}. {word} ({hot_value:,})\n"

        self.send("text", {"text": content})

    def close(self) -> None:
        self.http_client.close()
