"""从 config 读取 rate_limit 并构造 RateLimiter"""

from typing import Any, Dict, Optional

from social_monitor.utils.cookie_manager import load_config
from social_monitor.utils.rate_limiter import RateLimiter

SAFE_INTERVALS = (10.0, 20.0)
NORMAL_INTERVALS = (2.0, 3.0)


def get_rate_limit_settings(override_safe: bool = False) -> Dict[str, Any]:
    config = load_config()
    rl = config.get("rate_limit") or {}
    mode = "safe" if override_safe else rl.get("mode", "normal")
    if mode == "safe":
        min_i, max_i = SAFE_INTERVALS
    else:
        min_i = float(rl.get("min_interval", NORMAL_INTERVALS[0]))
        max_i = float(rl.get("max_interval", NORMAL_INTERVALS[1]))
    return {
        "mode": mode,
        "min_interval": min_i,
        "max_interval": max_i,
        "daily_max_requests": int(rl.get("daily_max_requests", 0) or 0),
        "stop_on_403": bool(rl.get("stop_on_403", True)),
    }


def build_rate_limiter(override_safe: bool = False) -> RateLimiter:
    s = get_rate_limit_settings(override_safe=override_safe)
    return RateLimiter(min_interval=s["min_interval"], max_interval=s["max_interval"])
