"""弹幕词频统计"""

from __future__ import annotations

import re
from collections import Counter
from typing import Any, Dict, List


def extract_danmaku_words(
    danmaku_list: List[Dict[str, Any]],
    top_n: int = 50,
    min_len: int = 2,
) -> List[Dict[str, Any]]:
    """从弹幕列表提取高频词（中文连续字符）"""
    counter: Counter[str] = Counter()
    pattern = re.compile(rf"[\u4e00-\u9fff]{{{min_len},}}")

    for item in danmaku_list:
        content = str(item.get("content", "")).strip()
        if not content or content.startswith("["):
            continue
        for word in pattern.findall(content):
            counter[word] += 1

    return [{"word": word, "count": count} for word, count in counter.most_common(top_n)]
