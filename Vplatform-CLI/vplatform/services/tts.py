"""Edge TTS 语音合成服务。"""

from __future__ import annotations

import asyncio
import json
import subprocess
import tempfile
from pathlib import Path

import edge_tts
from loguru import logger

from vplatform.config.schema import TTSConfig
from vplatform.models.storyboard import AudioResult, StoryboardFrame, WordTimestamp


class TTSService:
    def __init__(self, config: TTSConfig) -> None:
        self.config = config

    def synthesize(self, frame: StoryboardFrame, output_dir: Path) -> AudioResult:
        output_dir.mkdir(parents=True, exist_ok=True)
        out_path = output_dir / f"frame_{frame.index:03d}.mp3"
        logger.info("TTS 合成 frame={} text={}", frame.index, frame.narration[:40])

        word_timestamps: list[WordTimestamp] = []
        communicate = edge_tts.Communicate(
            frame.narration,
            self.config.voice,
            boundary="WordBoundary",
        )

        async def _run() -> None:
            nonlocal word_timestamps
            submaker = edge_tts.SubMaker()
            with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as tmp:
                tmp_path = tmp.name
            try:
                audio_chunks: list[bytes] = []
                async for chunk in communicate.stream():
                    if chunk["type"] == "audio":
                        audio_chunks.append(chunk["data"])
                    elif chunk["type"] in ("WordBoundary", "SentenceBoundary"):
                        submaker.feed(chunk)
                Path(tmp_path).write_bytes(b"".join(audio_chunks))
                out_path.write_bytes(Path(tmp_path).read_bytes())

                word_timestamps = self._extract_word_timestamps(submaker, frame.narration)
            finally:
                Path(tmp_path).unlink(missing_ok=True)

        asyncio.run(_run())
        duration = self._probe_duration(out_path)
        if not word_timestamps:
            word_timestamps = [
                WordTimestamp(text=frame.narration.strip(), start_sec=0.0, end_sec=duration)
            ]
            logger.debug("TTS 使用整句时间轴 fallback frame={}", frame.index)
        logger.info("TTS 完成 frame={} duration={:.2f}s", frame.index, duration)
        return AudioResult(path=str(out_path), duration_sec=duration, word_timestamps=word_timestamps)

    @staticmethod
    def _extract_word_timestamps(submaker: edge_tts.SubMaker, narration: str) -> list[WordTimestamp]:
        """从 SubMaker 解析词级时间轴；不同 edge-tts 版本 API 不一致时使用 fallback。"""
        words: list[WordTimestamp] = []

        cues = getattr(submaker, "cues", None)
        if cues is not None:
            try:
                for cue in cues:
                    start_raw = getattr(cue, "start", None)
                    end_raw = getattr(cue, "end", None)
                    content = getattr(cue, "content", None) or getattr(cue, "text", "")
                    if start_raw is None or end_raw is None:
                        continue
                    start = (
                        start_raw.total_seconds()
                        if hasattr(start_raw, "total_seconds")
                        else float(start_raw) / 1e7
                    )
                    end = (
                        end_raw.total_seconds()
                        if hasattr(end_raw, "total_seconds")
                        else float(end_raw) / 1e7
                    )
                    if content:
                        words.append(WordTimestamp(text=str(content), start_sec=start, end_sec=end))
                if words:
                    return words
            except (TypeError, AttributeError, ValueError) as exc:
                logger.warning("SubMaker.cues 解析失败: {}", exc)

        generate_words = getattr(submaker, "generate_words", None)
        if callable(generate_words):
            try:
                for item in generate_words():
                    words.append(
                        WordTimestamp(
                            text=str(item.get("text", "")),
                            start_sec=float(item.get("start", 0)),
                            end_sec=float(item.get("end", 0)),
                        )
                    )
                if words:
                    return words
            except (TypeError, ValueError) as exc:
                logger.warning("SubMaker.generate_words 失败: {}", exc)

        # 帧级 fallback：按 narration 分句占位，时长在 synthesize 中补全
        text = narration.strip()
        if text:
            words.append(WordTimestamp(text=text, start_sec=0.0, end_sec=0.0))
        return words

    @staticmethod
    def _probe_duration(path: Path) -> float:
        try:
            result = subprocess.run(
                [
                    "ffprobe",
                    "-v",
                    "quiet",
                    "-print_format",
                    "json",
                    "-show_format",
                    str(path),
                ],
                capture_output=True,
                text=True,
                check=True,
            )
            data = json.loads(result.stdout)
            return float(data["format"]["duration"])
        except (subprocess.CalledProcessError, KeyError, ValueError, FileNotFoundError):
            logger.warning("ffprobe 不可用，使用默认时长 3s")
            return 3.0
