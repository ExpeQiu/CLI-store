from typing import Any, Dict, Optional

import httpx

from social_monitor.utils.errors import ScrapeBlockedError
from social_monitor.utils.logger import setup_logger
from social_monitor.utils.rate_limit_config import get_rate_limit_settings
from social_monitor.utils.request_tracker import check_daily_limit, increment_request_count

logger = setup_logger(__name__)

DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json, text/plain, */*",
}


class HttpClient:
    """HTTP 客户端封装"""

    def __init__(
        self,
        timeout: float = 30.0,
        headers: Optional[Dict[str, str]] = None,
        track_requests: bool = True,
    ):
        merged = {**DEFAULT_HEADERS, **(headers or {})}
        self._client = httpx.Client(timeout=timeout, headers=merged, follow_redirects=True)
        self._track_requests = track_requests
        self._settings = get_rate_limit_settings()

    def _before_request(self) -> None:
        if not self._track_requests:
            return
        check_daily_limit(self._settings.get("daily_max_requests"))

    def _after_request(self, url: str, status_code: int) -> None:
        if self._track_requests:
            count = increment_request_count(1)
            if self._settings.get("daily_max_requests"):
                logger.debug(
                    "日请求 %d/%d url=%s",
                    count,
                    self._settings["daily_max_requests"],
                    url,
                )
        if self._settings.get("stop_on_403") and status_code in (403, 429):
            logger.error("采集被阻断 status=%s url=%s", status_code, url)
            raise ScrapeBlockedError(status_code, url)

    def get(
        self,
        url: str,
        params: Optional[Dict[str, Any]] = None,
        headers: Optional[Dict[str, str]] = None,
    ) -> httpx.Response:
        self._before_request()
        logger.debug("GET %s params=%s", url, params)
        resp = self._client.get(url, params=params, headers=headers)
        logger.debug("响应 status=%s url=%s", resp.status_code, url)
        self._after_request(url, resp.status_code)
        resp.raise_for_status()
        return resp

    def post(
        self,
        url: str,
        json: Optional[Dict[str, Any]] = None,
        headers: Optional[Dict[str, str]] = None,
    ) -> httpx.Response:
        self._before_request()
        logger.debug("POST %s", url)
        resp = self._client.post(url, json=json, headers=headers)
        self._after_request(url, resp.status_code)
        resp.raise_for_status()
        return resp

    def close(self) -> None:
        self._client.close()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()
