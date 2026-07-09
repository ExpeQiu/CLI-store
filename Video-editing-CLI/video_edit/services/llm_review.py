"""LLM 歧义区间复核（OpenAI 兼容 API）。"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass

from loguru import logger

from video_edit.config import AlignConfig


@dataclass
class AmbiguousMatch:
    script_idx: int
    script_text: str
    candidate_text: str
    score: float
    start: float
    end: float


def review_ambiguous_matches(
    items: list[AmbiguousMatch],
    *,
    config: AlignConfig,
) -> dict[int, bool]:
    """返回 script_idx -> 是否保留该候选。失败时默认保留。"""
    if not items or not config.use_llm_review:
        return {item.script_idx: True for item in items}

    api_key = config.openai_api_key or os.getenv("OPENAI_API_KEY")
    if not api_key:
        logger.warning("未配置 OPENAI_API_KEY，跳过 LLM 复核")
        return {item.script_idx: True for item in items}

    try:
        import httpx
    except ImportError as exc:
        logger.warning("未安装 httpx，跳过 LLM 复核: {}", exc)
        return {item.script_idx: True for item in items}

    results: dict[int, bool] = {}
    for item in items:
        verdict = _review_single(item, api_key=api_key, config=config)
        results[item.script_idx] = verdict
        logger.info(
            "LLM 复核 句{} -> {}",
            item.script_idx + 1,
            "保留" if verdict else "删除",
        )
    return results


def _review_single(item: AmbiguousMatch, *, api_key: str, config: AlignConfig) -> bool:
    import httpx

    base_url = (config.openai_base_url or os.getenv("OPENAI_BASE_URL") or "https://api.openai.com/v1").rstrip("/")
    prompt = (
        "你是口播剪辑助手。判断转录片段是否与脚本句子匹配且应保留在成片中。\n"
        f"脚本句：{item.script_text}\n"
        f"转录段：{item.candidate_text}\n"
        f"相似度：{item.score:.2f}\n"
        '只回复 JSON：{"keep": true} 或 {"keep": false}'
    )
    payload = {
        "model": config.llm_model,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0,
        "response_format": {"type": "json_object"},
    }
    try:
        resp = httpx.post(
            f"{base_url}/chat/completions",
            headers={"Authorization": f"Bearer {api_key}"},
            json=payload,
            timeout=30.0,
        )
        resp.raise_for_status()
        content = resp.json()["choices"][0]["message"]["content"]
        data = json.loads(content)
        return bool(data.get("keep", True))
    except Exception as exc:
        logger.warning("LLM 复核失败，默认保留: {}", exc)
        return True
