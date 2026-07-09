#!/usr/bin/env python3
"""环境验收脚本。"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def check_import(name: str) -> bool:
    try:
        __import__(name)
        return True
    except ImportError:
        return False


def main() -> int:
    print("[verify_env] Video-editing-CLI 环境检查")
    ok = True

    for pkg in ("click", "pydantic", "yaml", "loguru", "video_edit"):
        if check_import(pkg):
            print(f"  [ok] {pkg}")
        else:
            print(f"  [fail] {pkg}")
            ok = False

    ffmpeg = subprocess.run(["which", "ffmpeg"], capture_output=True, text=True)
    if ffmpeg.returncode == 0:
        print(f"  [ok] ffmpeg: {ffmpeg.stdout.strip()}")
    else:
        print("  [warn] ffmpeg 未安装（真实转录需要）")

    if check_import("faster_whisper"):
        print("  [ok] faster_whisper（可选，真实 ASR）")
    else:
        print("  [warn] faster_whisper 未安装（--demo 模式不受影响）")

    if not ok:
        return 1
    print("[verify_env] 通过")
    return 0


if __name__ == "__main__":
    sys.exit(main())
