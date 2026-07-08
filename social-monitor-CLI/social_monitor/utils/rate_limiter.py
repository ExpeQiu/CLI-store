import random
import time
from typing import Optional


class RateLimiter:
    """请求频率限制器"""

    def __init__(self, min_interval: float = 2.0, max_interval: float = 3.0):
        self.min_interval = min_interval
        self.max_interval = max_interval
        self._last_request: Optional[float] = None

    def wait(self) -> None:
        if self._last_request is not None:
            elapsed = time.time() - self._last_request
            delay = random.uniform(self.min_interval, self.max_interval)
            if elapsed < delay:
                time.sleep(delay - elapsed)
        self._last_request = time.time()
