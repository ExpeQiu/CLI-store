"""批量解析 account_id：按平台调用搜索接口并对齐 display_name"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from social_monitor.account.matcher import pick_best_candidate
from social_monitor.account.registry import AccountEntry
from social_monitor.config import get_rsshub_url
from social_monitor.platforms.bilibili import BilibiliCollector
from social_monitor.platforms.douyin import DouYinCollector
from social_monitor.platforms.wechat import WeChatCollector
from social_monitor.platforms.xiaohongshu import XiaoHongShuCollector
from social_monitor.account.auth import platform_auth_ready
from social_monitor.utils.cookie_manager import get_cookie
from social_monitor.utils.logger import setup_logger

logger = setup_logger(__name__)

RESOLVABLE_PLATFORMS = {"bilibili", "douyin", "wechat", "xiaohongshu"}


def _search_candidates(entry: AccountEntry, safe_mode: bool = True) -> List[Dict[str, Any]]:
    keyword = entry.display_name
    platform = entry.platform_key

    if platform == "bilibili":
        with BilibiliCollector(safe_mode=safe_mode) as c:
            return c.search_users(keyword)

    if platform == "douyin":
        cookie = get_cookie("douyin")
        with DouYinCollector(cookie=cookie, safe_mode=safe_mode) as c:
            return c.search_users(keyword, cookie=cookie)

    if platform == "wechat":
        with WeChatCollector(rsshub_url=get_rsshub_url(), safe_mode=safe_mode) as c:
            return c.search_accounts(keyword)

    if platform == "xiaohongshu":
        cookie = get_cookie("xiaohongshu")
        with XiaoHongShuCollector(cookie=cookie, safe_mode=safe_mode) as c:
            return c.search_users(keyword)

    return []


def resolve_entry(entry: AccountEntry, safe_mode: bool = True) -> Dict[str, Any]:
    base = entry.to_dict()
    base.update(
        {
            "resolved": False,
            "account_id_resolved": None,
            "match_score": None,
            "profile_url": None,
            "resolve_status": "skipped",
            "candidates": [],
            "error": None,
        }
    )

    if not entry.needs_resolve:
        if entry.status == "unsupported" or entry.platform_key not in RESOLVABLE_PLATFORMS:
            base["resolve_status"] = "unsupported_platform"
        elif entry.account_id not in ("-", ""):
            base["resolve_status"] = "already_set"
            base["account_id_resolved"] = entry.account_id
            base["resolved"] = True
        else:
            base["resolve_status"] = "skipped"
        return base

    if entry.platform_key not in RESOLVABLE_PLATFORMS:
        base["resolve_status"] = "unsupported_platform"
        return base

    if entry.platform_key == "douyin" and not platform_auth_ready("douyin"):
        base["resolve_status"] = "missing_login"
        base["error"] = "抖音需先登录: social-monitor config login douyin"
        return base

    if entry.platform_key == "xiaohongshu" and not platform_auth_ready("xiaohongshu"):
        base["resolve_status"] = "missing_login"
        base["error"] = "小红书需先登录: social-monitor config login xiaohongshu"
        return base

    try:
        candidates = _search_candidates(entry, safe_mode=safe_mode)
    except Exception as e:
        logger.exception(
            "解析失败 canonical=%s platform=%s",
            entry.canonical_name,
            entry.platform,
        )
        base["resolve_status"] = "error"
        base["error"] = str(e)
        return base

    if not candidates:
        base["resolve_status"] = "not_found"
        return base

    best, scored = pick_best_candidate(entry.display_name, candidates)
    base["candidates"] = scored[:5]

    if not best:
        base["resolve_status"] = "ambiguous"
        return base

    base.update(
        {
            "resolved": True,
            "resolve_status": "resolved",
            "account_id_resolved": best.get("account_id"),
            "match_score": best.get("match_score"),
            "profile_url": best.get("profile_url"),
        }
    )
    logger.info(
        "解析成功 canonical=%s platform=%s id=%s score=%s",
        entry.canonical_name,
        entry.platform,
        base["account_id_resolved"],
        base["match_score"],
    )
    return base


def resolve_entries(
    entries: List[AccountEntry],
    safe_mode: bool = True,
) -> List[Dict[str, Any]]:
    results = []
    for entry in entries:
        logger.info(
            "开始解析 [%s] %s / %s",
            entry.priority,
            entry.canonical_name,
            entry.platform,
        )
        results.append(resolve_entry(entry, safe_mode=safe_mode))
    return results


def build_monitor_yaml_snippet(results: List[Dict[str, Any]]) -> str:
    """将 resolved 结果汇总为 monitor.yaml 片段"""
    buckets: Dict[str, List[Dict[str, Any]]] = {
        "bilibili": [],
        "douyin": [],
        "wechat": [],
        "xiaohongshu": [],
    }
    for item in results:
        if not item.get("resolved") or item.get("resolve_status") != "resolved":
            continue
        key = item["platform_key"]
        if key not in buckets:
            continue
        buckets[key].append(item)

    lines = ["# 由 account resolve-p0 自动生成", ""]
    if buckets["bilibili"]:
        lines.append("bilibili:")
        lines.append("  accounts:")
        for item in buckets["bilibili"]:
            lines.append(f"    - uid: {item['account_id_resolved']}  # {item['canonical_name']}")
        lines.append("")

    if buckets["douyin"]:
        lines.append("douyin:")
        lines.append("  accounts:")
        for item in buckets["douyin"]:
            lines.append(
                f"    - sec_uid: {item['account_id_resolved']}  # {item['canonical_name']}"
            )
        lines.append("")

    if buckets["wechat"]:
        lines.append("wechat:")
        lines.append("  accounts:")
        for item in buckets["wechat"]:
            lines.append(f"    - {item['account_id_resolved']}  # {item['canonical_name']}")
        lines.append("")

    if buckets["xiaohongshu"]:
        lines.append("xiaohongshu:")
        lines.append("  users:")
        for item in buckets["xiaohongshu"]:
            lines.append(
                f"    - {item['account_id_resolved']}  # {item['canonical_name']}"
            )
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"
