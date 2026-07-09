"""CLI 输出工具。"""

from __future__ import annotations

import json
import sys
from typing import Any


def emit(data: Any, *, as_json: bool = True) -> None:
    if as_json:
        print(json.dumps(data, ensure_ascii=False, indent=2, default=str))
    elif isinstance(data, str):
        print(data)
    else:
        print(json.dumps(data, ensure_ascii=False, indent=2, default=str))


def emit_error(message: str, *, code: int = 1) -> int:
    emit({"ok": False, "error": message}, as_json=True)
    return code
