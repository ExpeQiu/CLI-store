"""离线 demo 数据，供 verify.sh 与 --demo 使用"""

from __future__ import annotations

from datetime import datetime, timezone, timedelta

TZ_CN = timezone(timedelta(hours=8))


def demo_monitor_events() -> list[dict]:
    ts = datetime.now(TZ_CN).isoformat()
    return [
        {
            "ts": ts,
            "type": "metric",
            "viewer_count": 687,
            "raw": "687人看过",
            "confidence": 0.95,
        },
        {
            "ts": ts,
            "type": "chat",
            "user": "张三",
            "content": "007GT多少钱",
            "raw": "张三: 007GT多少钱",
            "confidence": 0.91,
        },
        {
            "ts": ts,
            "type": "chat",
            "user": "李四",
            "content": "猎装版真好看",
            "raw": "李四: 猎装版真好看",
            "confidence": 0.88,
        },
    ]


def demo_monitor_payload() -> dict:
    from screen_watch.__version__ import __version__

    return {
        "module": "monitor-run",
        "version": __version__,
        "data_source": "demo",
        "preset": "wechat-live",
        "fetched_at": datetime.now(TZ_CN).isoformat(),
        "count": 3,
        "events": demo_monitor_events(),
    }
