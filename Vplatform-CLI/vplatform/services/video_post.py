"""FFmpeg 视频后处理 — 拼接、混音、字幕烧录。"""

from __future__ import annotations

import shutil
import subprocess
import tempfile
from functools import lru_cache
from pathlib import Path

from loguru import logger

from vplatform.models.storyboard import Storyboard


class VideoPostService:
    def concat_clips(
        self,
        clip_paths: list[str | Path],
        output_path: Path,
        fps: int = 16,
        transition: str = "cut",
        transition_duration: float = 0.5,
    ) -> Path:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        if not clip_paths:
            raise ValueError("无视频片段可拼接")

        if len(clip_paths) == 1:
            shutil.copy2(clip_paths[0], output_path)
            return output_path

        if transition == "fade" and transition_duration > 0:
            try:
                return self._concat_xfade(clip_paths, output_path, fps, transition_duration)
            except Exception as exc:
                logger.warning("xfade 转场失败，降级硬切: {}", exc)

        return self._concat_hard(clip_paths, output_path, fps)

    def _concat_hard(self, clip_paths: list[str | Path], output_path: Path, fps: int) -> Path:
        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False, encoding="utf-8") as f:
            for clip in clip_paths:
                f.write(f"file '{Path(clip).resolve()}'\n")
            list_file = f.name

        cmd = [
            "ffmpeg",
            "-y",
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            list_file,
            "-c:v",
            "libx264",
            "-crf",
            "18",
            "-pix_fmt",
            "yuv420p",
            "-r",
            str(fps),
            str(output_path),
        ]
        self._run(cmd, "concat")
        Path(list_file).unlink(missing_ok=True)
        logger.info("视频硬切拼接完成 {}", output_path)
        return output_path

    def _concat_xfade(
        self,
        clip_paths: list[str | Path],
        output_path: Path,
        fps: int,
        transition_duration: float,
    ) -> Path:
        """多段 clip 淡入淡出拼接（xfade）。"""
        durations = [self.probe_duration(p) for p in clip_paths]
        inputs: list[str] = []
        for clip in clip_paths:
            inputs.extend(["-i", str(Path(clip).resolve())])

        if len(clip_paths) == 2:
            offset = max(durations[0] - transition_duration, 0.01)
            filter_complex = (
                f"[0:v][1:v]xfade=transition=fade:duration={transition_duration}:offset={offset}[vout]"
            )
        else:
            parts: list[str] = []
            cumulative = durations[0]
            prev = "[0:v]"
            for i in range(1, len(clip_paths)):
                offset = max(cumulative - transition_duration, 0.01)
                out_label = f"[v{i}]" if i < len(clip_paths) - 1 else "[vout]"
                parts.append(
                    f"{prev}[{i}:v]xfade=transition=fade:duration={transition_duration}:offset={offset}{out_label}"
                )
                prev = out_label
                cumulative += durations[i] - transition_duration
            filter_complex = ";".join(parts)

        cmd = [
            "ffmpeg",
            "-y",
            *inputs,
            "-filter_complex",
            filter_complex,
            "-map",
            "[vout]",
            "-c:v",
            "libx264",
            "-crf",
            "18",
            "-pix_fmt",
            "yuv420p",
            "-r",
            str(fps),
            "-an",
            str(output_path),
        ]
        self._run(cmd, "concat_xfade")
        logger.info("视频 xfade 拼接完成 clips={} {}", len(clip_paths), output_path)
        return output_path

    def ken_burns_clip(
        self,
        image_path: str | Path,
        duration_sec: float,
        output_path: Path,
        fps: int = 16,
        zoom: float = 1.08,
    ) -> Path:
        """关键帧 Ken Burns 动效（zoompan），用于过渡镜降本。"""
        output_path.parent.mkdir(parents=True, exist_ok=True)
        frames = max(int(duration_sec * fps), fps)
        # 缓慢放大：从 1.0 到 zoom
        zoom_inc = (zoom - 1.0) / max(frames, 1)
        filter_expr = (
            f"zoompan=z='min(zoom+{zoom_inc:.6f},{zoom})':"
            f"x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':"
            f"d={frames}:s=512x288:fps={fps}"
        )
        cmd = [
            "ffmpeg",
            "-y",
            "-loop",
            "1",
            "-i",
            str(Path(image_path).resolve()),
            "-vf",
            filter_expr,
            "-t",
            str(duration_sec),
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            "-an",
            str(output_path),
        ]
        self._run(cmd, "ken_burns")
        logger.info("Ken Burns 片段完成 duration={:.1f}s {}", duration_sec, output_path)
        return output_path

    @staticmethod
    def probe_duration(video_path: str | Path) -> float:
        cmd = [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            str(Path(video_path).resolve()),
        ]
        try:
            proc = subprocess.run(cmd, check=True, capture_output=True, text=True)
            return max(float(proc.stdout.strip()), 0.5)
        except (subprocess.CalledProcessError, ValueError) as exc:
            logger.warning("ffprobe 失败 path={} err={}，使用默认 3s", video_path, exc)
            return 3.0

    def trim_to_duration(self, video_path: Path, duration_sec: float, output_path: Path) -> Path:
        cmd = [
            "ffmpeg",
            "-y",
            "-i",
            str(video_path),
            "-t",
            str(duration_sec),
            "-c:v",
            "libx264",
            "-c:a",
            "aac",
            str(output_path),
        ]
        self._run(cmd, "trim")
        return output_path

    def mux_narration(
        self,
        video_path: Path,
        storyboard: Storyboard,
        output_path: Path,
        bgm_path: Path | None = None,
        bgm_volume: float = 0.2,
    ) -> Path:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        audio_paths = [f.audio.path for f in storyboard.frames if f.audio]
        if not audio_paths:
            import shutil

            shutil.copy2(video_path, output_path)
            return output_path

        merged_audio = output_path.parent / "narration_merged.mp3"
        if len(audio_paths) == 1:
            import shutil

            shutil.copy2(audio_paths[0], merged_audio)
        else:
            inputs: list[str] = []
            for ap in audio_paths:
                inputs.extend(["-i", ap])
            cmd = ["ffmpeg", "-y", *inputs, "-filter_complex", f"concat=n={len(audio_paths)}:v=0:a=1", str(merged_audio)]
            self._run(cmd, "merge_audio")

        if bgm_path and bgm_path.exists():
            cmd = [
                "ffmpeg",
                "-y",
                "-i",
                str(video_path),
                "-i",
                str(merged_audio),
                "-i",
                str(bgm_path),
                "-filter_complex",
                f"[1:a]volume=1.0[narr];[2:a]volume={bgm_volume}[bgm];[narr][bgm]amix=inputs=2:duration=first[aout]",
                "-map",
                "0:v",
                "-map",
                "[aout]",
                "-c:v",
                "copy",
                "-c:a",
                "aac",
                "-shortest",
                str(output_path),
            ]
        else:
            cmd = [
                "ffmpeg",
                "-y",
                "-i",
                str(video_path),
                "-i",
                str(merged_audio),
                "-map",
                "0:v",
                "-map",
                "1:a",
                "-c:v",
                "copy",
                "-c:a",
                "aac",
                "-shortest",
                str(output_path),
            ]
        self._run(cmd, "mux")
        logger.info("音视频混合完成 {}", output_path)
        return output_path

    def burn_subtitles(self, video_path: Path, srt_path: Path, output_path: Path) -> Path:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        if _ffmpeg_has_subtitles_filter():
            return self._burn_subtitles_hard(video_path, srt_path, output_path)
        logger.warning("ffmpeg 未编译 libass/subtitles 滤镜，降级为软字幕封装")
        return self.embed_subtitles(video_path, srt_path, output_path)

    def embed_subtitles(self, video_path: Path, srt_path: Path, output_path: Path) -> Path:
        """将 SRT 作为字幕轨封装进 MP4（无需 libass）。"""
        cmd = [
            "ffmpeg",
            "-y",
            "-i",
            str(video_path),
            "-i",
            str(srt_path),
            "-map",
            "0:v",
            "-map",
            "0:a?",
            "-map",
            "1",
            "-c:v",
            "copy",
            "-c:a",
            "copy",
            "-c:s",
            "mov_text",
            "-metadata:s:s:0",
            "language=chi",
            "-disposition:s:0",
            "default",
            str(output_path),
        ]
        self._run(cmd, "subtitle_embed")
        logger.info("软字幕封装完成 {}（画面内不可见，播放器需开启字幕轨）", output_path)
        return output_path

    def _burn_subtitles_hard(self, video_path: Path, srt_path: Path, output_path: Path) -> Path:
        """使用 subtitles 滤镜烧录字幕（需 libass）。"""
        with tempfile.NamedTemporaryFile(suffix=".srt", delete=False) as tmp:
            shutil.copy2(srt_path, tmp.name)
            temp_srt = Path(tmp.name)

        try:
            escaped = str(temp_srt).replace("\\", "\\\\").replace(":", "\\:")
            cmd = [
                "ffmpeg",
                "-y",
                "-i",
                str(video_path),
                "-vf",
                f"subtitles={escaped}",
                "-c:a",
                "copy",
                str(output_path),
            ]
            self._run(cmd, "subtitle")
            logger.info("字幕烧录完成 {}", output_path)
            return output_path
        finally:
            temp_srt.unlink(missing_ok=True)

    def pick_bgm(self, bgm_dir: Path) -> Path | None:
        if not bgm_dir.exists():
            return None
        files = list(bgm_dir.glob("*.mp3")) + list(bgm_dir.glob("*.wav"))
        return files[0] if files else None

    @staticmethod
    def _run(cmd: list[str], stage: str) -> None:
        logger.debug("ffmpeg {} cmd={}", stage, " ".join(cmd))
        try:
            subprocess.run(cmd, check=True, capture_output=True, text=True)
        except subprocess.CalledProcessError as exc:
            stderr = (exc.stderr or "").strip()
            tail = stderr[-800:] if len(stderr) > 800 else stderr
            logger.error("ffmpeg 失败 stage={} stderr={}", stage, tail)
            raise RuntimeError(f"FFmpeg {stage} 失败: {tail[-300:]}") from exc
        except FileNotFoundError as exc:
            raise RuntimeError("未找到 ffmpeg，请先安装") from exc


@lru_cache(maxsize=1)
def _ffmpeg_has_subtitles_filter() -> bool:
    try:
        proc = subprocess.run(
            ["ffmpeg", "-h", "filter=subtitles"],
            capture_output=True,
            text=True,
            check=False,
        )
    except FileNotFoundError:
        return False
    output = f"{proc.stdout}\n{proc.stderr}"
    return "Unknown filter" not in output and "subtitles" in output.lower()
