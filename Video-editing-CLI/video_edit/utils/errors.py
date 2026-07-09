"""自定义异常。"""

from __future__ import annotations


class VideoEditError(Exception):
    """业务错误。"""


class DependencyError(VideoEditError):
    """缺少外部依赖（ffmpeg / whisper）。"""
