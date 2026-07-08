"""日请求计数，用于反爬配额控制"""

from datetime import date
from pathlib import Path
from typing import Optional

from social_monitor.utils.logger import setup_logger

logger = setup_logger(__name__)

COUNTER_DIR = Path.home() / ".social-monitor"
COUNTER_FILE = COUNTER_DIR / "request_count.txt"


def _today_key() -> str:
    return date.today().isoformat()


def _read_counter() -> tuple[str, int]:
    if not COUNTER_FILE.exists():
        return _today_key(), 0
    text = COUNTER_FILE.read_text(encoding="utf-8").strip()
    if not text:
        return _today_key(), 0
    parts = text.split(",", 1)
    if len(parts) != 2:
        return _today_key(), 0
    day, count = parts[0], parts[1]
    try:
        return day, int(count)
    except ValueError:
        return _today_key(), 0


def get_today_count() -> int:
    day, count = _read_counter()
    if day != _today_key():
        return 0
    return count


def increment_request_count(delta: int = 1) -> int:
    """递增计数并返回今日总数"""
    COUNTER_DIR.mkdir(parents=True, exist_ok=True)
    day, count = _read_counter()
    today = _today_key()
    if day != today:
        count = 0
    count += delta
    COUNTER_FILE.write_text(f"{today},{count}", encoding="utf-8")
    logger.debug("日请求计数 today=%s count=%d", today, count)
    return count


def check_daily_limit(max_requests: Optional[int]) -> None:
    """超过日上限时抛出异常"""
    if not max_requests or max_requests <= 0:
        return
    current = get_today_count()
    if current >= max_requests:
        from social_monitor.utils.errors import ScrapeBlockedError

        raise ScrapeBlockedError(
            429,
            "daily-limit",
            f"已达日请求上限 {max_requests}（当前 {current}），请明日再试",
        )
