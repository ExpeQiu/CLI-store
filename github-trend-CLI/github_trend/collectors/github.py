"""GitHub Trending 采集"""

from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from typing import Any

import httpx

logger = logging.getLogger("github_trend.collectors.github")

DEMO_ITEMS = [
    {
        "rank": 1,
        "repo": "openai/codex",
        "description": "Lightweight coding agent",
        "language": "Rust",
        "stars_today": 1200,
        "url": "https://github.com/openai/codex",
    },
    {
        "rank": 2,
        "repo": "anthropics/claude-code",
        "description": "Agentic coding tool",
        "language": "TypeScript",
        "stars_today": 980,
        "url": "https://github.com/anthropics/claude-code",
    },
    {
        "rank": 3,
        "repo": "langchain-ai/langgraph",
        "description": "Build resilient language agents",
        "language": "Python",
        "stars_today": 750,
        "url": "https://github.com/langchain-ai/langgraph",
    },
]


def is_mock(demo: bool) -> bool:
    return demo or os.getenv("GITHUB_TREND_MOCK_MODE", "").lower() in ("1", "true", "yes")


def fetch_trending(*, since: str = "daily", spoken_language: str = "", demo: bool = False) -> dict[str, Any]:
    if is_mock(demo):
        items = DEMO_ITEMS
        source = "demo"
    else:
        try:
            items = _fetch_live(since=since, spoken_language=spoken_language)
            source = "live"
        except Exception as e:
            logger.error("GitHub Trending 采集失败: %s", e)
            raise

    return {
        "module": "github-trending",
        "data_source": source,
        "fetched_at": datetime.now(timezone.utc).astimezone().isoformat(),
        "since": since,
        "count": len(items),
        "items": items,
    }


def _fetch_live(*, since: str, spoken_language: str) -> list[dict[str, Any]]:
    params: dict[str, str] = {"since": since}
    if spoken_language:
        params["spoken_language_code"] = spoken_language
    headers = {}
    token = os.getenv("GITHUB_TOKEN") or os.getenv("GITHUB_TREND_TOKEN")
    if token:
        headers["Authorization"] = f"Bearer {token}"

    url = "https://api.github.com/search/repositories"
    # GitHub 无官方 trending API，使用 stars 增量近似
    q = "stars:>100"
    if since == "weekly":
        q += " pushed:>2026-06-18"
    elif since == "monthly":
        q += " pushed:>2026-05-25"
    else:
        q += " pushed:>2026-06-24"
    params = {"q": q, "sort": "stars", "order": "desc", "per_page": 30}

    with httpx.Client(timeout=30.0, headers=headers) as client:
        resp = client.get(url, params=params)
        resp.raise_for_status()
        data = resp.json()

    items = []
    for i, repo in enumerate(data.get("items", [])[:30], 1):
        items.append({
            "rank": i,
            "repo": repo.get("full_name", ""),
            "description": repo.get("description") or "",
            "language": repo.get("language") or "",
            "stars_today": repo.get("stargazers_count", 0),
            "url": repo.get("html_url", ""),
        })
    return items


def fetch_high_stars(demo: bool = False) -> list[dict[str, Any]]:
    """
    获取近7天活跃的高星项目（stars>5000，近7天有推送）。
    用于飞书 Bitable 同步。
    """
    if demo or os.getenv("GITHUB_TREND_MOCK_MODE", "").lower() in ("1", "true", "yes"):
        return [
            {"name": "openai/codex", "stars": 25000, "lang": "Rust",
             "desc": "Lightweight coding agent", "url": "https://github.com/openai/codex",
             "growth": "+1200"},
            {"name": "anthropics/claude-code", "stars": 18000, "lang": "TypeScript",
             "desc": "Agentic coding tool", "url": "https://github.com/anthropics/claude-code",
             "growth": "+980"},
            {"name": "langchain-ai/langgraph", "stars": 12000, "lang": "Python",
             "desc": "Build resilient language agents", "url": "https://github.com/langchain-ai/langgraph",
             "growth": "+750"},
        ]

    import math
    from datetime import datetime, timezone

    headers = {}
    token = os.getenv("GITHUB_TOKEN") or os.getenv("GITHUB_TREND_TOKEN")
    if token:
        headers["Authorization"] = f"Bearer {token}"

    week_ago = datetime.now(timezone.utc).timestamp() - 7 * 24 * 60 * 60
    week_ago_str = datetime.fromtimestamp(week_ago, tz=timezone.utc).strftime("%Y-%m-%d")

    queries = [
        {"q": f"stars:>10000 pushed:>{week_ago_str}", "label": "Top Stars (7d active)"},
        {"q": f"stars:5000..10000 pushed:>{week_ago_str}", "label": "Mid Stars (7d active)"},
    ]

    all_projects: list[dict[str, Any]] = []
    seen: set[str] = set()

    with httpx.Client(timeout=30.0, headers=headers) as client:
        for query in queries:
            params = {"q": query["q"], "sort": "stars", "order": "desc", "per_page": 20}
            try:
                resp = client.get("https://api.github.com/search/repositories", params=params)
                resp.raise_for_status()
                data = resp.json()
                for repo in data.get("items", []):
                    full_name = repo.get("full_name", "")
                    if full_name in seen:
                        continue
                    seen.add(full_name)
                    all_projects.append({
                        "name": full_name.split("/")[1],
                        "repo": full_name,
                        "stars": repo.get("stargazers_count", 0),
                        "lang": repo.get("language") or "-",
                        "desc": (repo.get("description") or "")[:100],
                        "url": repo.get("html_url", ""),
                        "topics": ",".join((repo.get("topics") or [])[:5]),
                        "pushed_at": repo.get("pushed_at", ""),
                        "growth": "-",
                    })
            except Exception as e:
                logger.warning("Query failed (%s): %s", query["label"], e)

    logger.info("Fetched %d unique projects", len(all_projects))
    return all_projects
