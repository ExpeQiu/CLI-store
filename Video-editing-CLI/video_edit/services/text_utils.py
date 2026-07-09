"""文本归一化与脚本分句。"""

from __future__ import annotations

import re
import unicodedata


_PUNCT = re.compile(
    r"[\s\u3000，。！？、；："
    r"「」『』（）()\[\]【】《》…—\-,.!?;:'·\"]+"
)


def normalize_text(text: str) -> str:
    text = unicodedata.normalize("NFKC", text)
    text = _PUNCT.sub("", text)
    return text.lower()


def split_script_sentences(script: str) -> list[str]:
    lines: list[str] = []
    for block in script.splitlines():
        block = block.strip()
        if not block or block.startswith("#"):
            continue
        parts = re.split(r"(?<=[。！？!?])\s*", block)
        for part in parts:
            part = part.strip()
            if part:
                lines.append(part)
    if not lines and script.strip():
        lines.append(script.strip())
    return lines
