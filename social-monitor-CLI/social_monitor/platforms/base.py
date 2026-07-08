from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional

from social_monitor.utils.http_client import HttpClient
from social_monitor.utils.logger import setup_logger
from social_monitor.utils.rate_limit_config import build_rate_limiter


class BaseCollector(ABC):
    """平台采集器基类"""

    platform_name: str = "unknown"

    def __init__(
        self,
        cookie: Optional[str] = None,
        headers: Optional[dict] = None,
        safe_mode: bool = False,
    ):
        self.cookie = cookie
        extra_headers = dict(headers or {})
        if cookie:
            extra_headers.setdefault("Cookie", cookie)
        self.http_client = HttpClient(headers=extra_headers or None)
        self.rate_limiter = build_rate_limiter(override_safe=safe_mode)
        self.logger = setup_logger(f"social-monitor.{self.platform_name}")

    @abstractmethod
    def fetch_user_content(self, account_id: str, **kwargs) -> List[Dict[str, Any]]:
        """采集用户内容"""

    def close(self) -> None:
        self.http_client.close()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()
