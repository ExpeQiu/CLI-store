"""字幕生成服务 — Edge TTS 时间戳优先。"""

from __future__ import annotations

from pathlib import Path

from loguru import logger

from vplatform.config.schema import SubtitleConfig
from vplatform.models.storyboard import Storyboard


class SubtitleService:
    def __init__(self, config: SubtitleConfig) -> None:
        self.config = config

    def from_storyboard(self, storyboard: Storyboard, output_dir: Path) -> Path:
        output_dir.mkdir(parents=True, exist_ok=True)
        srt_path = output_dir / "subtitles.srt"

        if self.config.mode == "whisper":
            logger.warning("Whisper 模式未安装，降级 Edge 时间戳")
            return self._edge_srt(storyboard, srt_path)

        return self._edge_srt(storyboard, srt_path)

    def _edge_srt(self, storyboard: Storyboard, srt_path: Path) -> Path:
        offset = 0.0
        entries: list[str] = []
        idx = 1

        for frame in storyboard.frames:
            if not frame.audio:
                continue
            if frame.audio.word_timestamps:
                for wt in frame.audio.word_timestamps:
                    entries.append(self._srt_entry(idx, wt.start_sec + offset, wt.end_sec + offset, wt.text))
                    idx += 1
            else:
                end = offset + frame.audio.duration_sec
                entries.append(self._srt_entry(idx, offset, end, frame.narration))
                idx += 1
            offset += frame.audio.duration_sec

        srt_path.write_text("\n\n".join(entries) + "\n", encoding="utf-8")
        vtt_path = self._write_vtt(srt_path)
        logger.info("字幕已生成 {} entries={} vtt={}", srt_path, idx - 1, vtt_path)
        return srt_path

    @staticmethod
    def _write_vtt(srt_path: Path) -> Path:
        import re

        vtt_path = srt_path.with_suffix(".vtt")
        srt_text = srt_path.read_text(encoding="utf-8")
        vtt_body = re.sub(r"(\d{2}:\d{2}:\d{2}),(\d{3})", r"\1.\2", srt_text)
        vtt_path.write_text(f"WEBVTT\n\n{vtt_body}", encoding="utf-8")
        return vtt_path

    @staticmethod
    def _srt_entry(index: int, start: float, end: float, text: str) -> str:
        def fmt(sec: float) -> str:
            h = int(sec // 3600)
            m = int((sec % 3600) // 60)
            s = int(sec % 60)
            ms = int((sec % 1) * 1000)
            return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"

        return f"{index}\n{fmt(start)} --> {fmt(end)}\n{text}"
