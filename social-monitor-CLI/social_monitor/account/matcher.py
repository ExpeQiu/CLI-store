"""账号名匹配：display_name 与搜索结果候选对齐"""

from __future__ import annotations

import re
import unicodedata
from difflib import SequenceMatcher
from typing import Any, Dict, List, Optional, Tuple


def normalize_name(name: str) -> str:
    """统一大小写、空白与常见符号，便于跨平台比对"""
    text = unicodedata.normalize("NFKC", name or "")
    text = text.lower()
    text = re.sub(r"[\s_\-·|｜/\\]+", "", text)
    text = re.sub(r"[^\w\u4e00-\u9fff]", "", text)
    return text


def chinese_core(name: str) -> str:
    return re.sub(r"[^\u4e00-\u9fff]", "", normalize_name(name))


def score_name_match(display_name: str, candidate_name: str) -> float:
    a = normalize_name(display_name)
    b = normalize_name(candidate_name)
    if not a or not b:
        return 0.0
    if a == b:
        return 1.0
    if a in b or b in a:
        shorter = min(len(a), len(b))
        longer = max(len(a), len(b))
        return 0.88 + 0.1 * (shorter / longer)

    ratio = SequenceMatcher(None, a, b).ratio()
    ca = chinese_core(display_name)
    cb = chinese_core(candidate_name)
    if ca and cb:
        if ca == cb:
            return max(ratio, 0.9)
        if ca in cb or cb in ca:
            return max(ratio, 0.85)
        ratio = max(ratio, SequenceMatcher(None, ca, cb).ratio())
    return ratio


def pick_best_candidate(
    display_name: str,
    candidates: List[Dict[str, Any]],
    name_key: str = "name",
    min_score: float = 0.82,
) -> Tuple[Optional[Dict[str, Any]], List[Dict[str, Any]]]:
    """返回最佳候选与带分数的完整列表"""
    scored: List[Dict[str, Any]] = []
    for item in candidates:
        name = str(item.get(name_key) or "")
        score = score_name_match(display_name, name)
        scored.append({**item, "match_score": round(score, 4)})

    scored.sort(key=lambda x: x["match_score"], reverse=True)
    if not scored:
        return None, []

    best = scored[0]
    if best["match_score"] < min_score:
        return None, scored
    if len(scored) > 1 and scored[1]["match_score"] >= min_score:
        gap = best["match_score"] - scored[1]["match_score"]
        same_core = chinese_core(display_name) == chinese_core(str(scored[1].get(name_key) or ""))
        if gap < 0.05 and not same_core:
            return None, scored
    return best, scored
