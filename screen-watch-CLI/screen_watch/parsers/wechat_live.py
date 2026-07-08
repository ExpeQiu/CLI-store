"""微信客户端直播 OCR 结果解析"""

from __future__ import annotations

import re
from collections import deque
from dataclasses import dataclass, field
from typing import Any


@dataclass
class ChatDiffState:
    dedup_window: int = 500
    _seen: deque[str] = field(default_factory=deque)
    _prev_lines: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        self._seen = deque(maxlen=self.dedup_window)

    def diff_lines(self, lines: list[str]) -> list[str]:
        """行级 diff，返回新增行"""
        new_lines: list[str] = []
        prev_set = set(self._prev_lines)
        for line in lines:
            line = line.strip()
            if not line or line in prev_set:
                continue
            if line in self._seen:
                continue
            new_lines.append(line)
            self._seen.append(line)
        self._prev_lines = lines
        return new_lines


def parse_viewer_count(text: str, pattern: str) -> dict[str, Any] | None:
    match = re.search(pattern, text.replace(" ", ""))
    if not match:
        return None
    num_str = match.group(1)
    if "万" in num_str:
        count = int(float(num_str.replace("万", "")) * 10000)
    else:
        count = int(float(num_str))
    return {
        "type": "metric",
        "viewer_count": count,
        "raw": match.group(0),
    }


def parse_chat_line(
    line: str,
    *,
    drop_prefixes: list[str] | None = None,
    drop_contains: list[str] | None = None,
) -> dict[str, Any] | None:
    drop_prefixes = drop_prefixes or []
    drop_contains = drop_contains or []

    for prefix in drop_prefixes:
        if line.startswith(prefix):
            return None
    for token in drop_contains:
        if token in line:
            return None

    if ":" in line or "：" in line:
        sep = ":" if ":" in line else "："
        parts = line.split(sep, 1)
        if len(parts) == 2:
            user, content = parts[0].strip(), parts[1].strip()
            if user and content:
                return {
                    "type": "chat",
                    "user": user,
                    "content": content,
                    "raw": line,
                }

    if len(line) >= 2:
        return {"type": "chat", "user": "", "content": line, "raw": line}
    return None


def ocr_lines_to_text(lines: list[dict[str, Any]]) -> str:
    """OCR 结果 [{text, ...}] → 合并文本"""
    return "\n".join(item.get("text", "") for item in lines if item.get("text"))


def ocr_lines_to_sorted_rows(lines: list[dict[str, Any]]) -> list[str]:
    """按 bbox y 坐标排序后逐行输出"""
    def y_top(item: dict) -> float:
        bbox = item.get("bbox") or [[0, 0]]
        return float(bbox[0][1])

    sorted_lines = sorted(lines, key=y_top)
    return [item.get("text", "").strip() for item in sorted_lines if item.get("text")]
