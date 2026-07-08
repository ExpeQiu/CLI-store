"""内置演示数据，供 --demo / SOCIAL_MONITOR_MOCK_MODE 使用"""

from __future__ import annotations

from typing import Any, Dict, List


def demo_weibo_trending(count: int = 20) -> List[Dict[str, Any]]:
    base = [
        {"rank": 1, "word": "新能源汽车发布会", "hot_value": 1250000, "label": "沸"},
        {"rank": 2, "word": "智能驾驶技术突破", "hot_value": 980000, "label": "热"},
        {"rank": 3, "word": "固态电池量产", "hot_value": 756000, "label": "新"},
        {"rank": 4, "word": "鸿蒙智行新品", "hot_value": 620000, "label": ""},
        {"rank": 5, "word": "充电桩建设加速", "hot_value": 510000, "label": ""},
    ]
    return _expand(base, count, "word", "hot_value")


def demo_douyin_trending(count: int = 20) -> List[Dict[str, Any]]:
    base = [
        {"rank": 1, "word": "车展现场直击", "hot_value": 2100000},
        {"rank": 2, "word": "新能源车测评", "hot_value": 1800000},
        {"rank": 3, "word": "自动驾驶实测", "hot_value": 1500000},
    ]
    return _expand(base, count, "word", "hot_value")


def demo_zhihu_trending(count: int = 20) -> List[Dict[str, Any]]:
    base = [
        {"rank": 1, "title": "如何看待固态电池商业化进程？", "hot_value": 5200000},
        {"rank": 2, "title": "2026年最值得期待的新能源车型有哪些？", "hot_value": 4100000},
        {"rank": 3, "title": "智能驾驶 L3 落地面临哪些挑战？", "hot_value": 3800000},
    ]
    return _expand(base, count, "title", "hot_value")


def demo_bilibili_ranking(count: int = 20) -> List[Dict[str, Any]]:
    base = [
        {"title": "【演示】新能源汽车发布会全程回顾", "play": 128000, "video_review": 3200},
        {"title": "【演示】固态电池技术深度解析", "play": 96000, "video_review": 2100},
        {"title": "【演示】智能驾驶辅助系统实测", "play": 87000, "video_review": 1800},
    ]
    return _expand(base, count, "title", "play")


def _expand(
    base: List[Dict[str, Any]],
    count: int,
    text_key: str,
    num_key: str,
) -> List[Dict[str, Any]]:
    if count <= len(base):
        return base[:count]
    out = list(base)
    i = len(base)
    while len(out) < count:
        src = base[i % len(base)]
        out.append({
            **src,
            text_key: f"{src[text_key]} ({i + 1})",
            num_key: int(src.get(num_key, 0) * 0.9 ** (i - len(base) + 1)),
        })
        i += 1
    return out
