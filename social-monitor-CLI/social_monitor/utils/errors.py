"""HTTP 采集相关异常与统一退出码"""

EXIT_OK = 0
EXIT_ERROR = 1
EXIT_NO_DATA = 2
EXIT_SCRAPE_FAIL = 3


class ScrapeBlockedError(Exception):
    """目标站点返回 403/429 等封禁状态"""

    def __init__(self, status_code: int, url: str, message: str = ""):
        self.status_code = status_code
        self.url = url
        super().__init__(message or f"采集被阻断 HTTP {status_code}: {url}")
