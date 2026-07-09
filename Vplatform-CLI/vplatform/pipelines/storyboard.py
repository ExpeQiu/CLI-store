"""完整分镜流水线 — storyboard → TTS → keyframe → I2V → concat → subtitle → final。"""

from __future__ import annotations

import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

from loguru import logger

from vplatform.config.schema import VplatformConfig
from vplatform.models.storyboard import Storyboard, StoryboardFrame
from vplatform.models.task import TaskRecord, TaskStage
from vplatform.pipelines.base import LinearPipeline
from vplatform.services.comfyui import ComfyUIError, ComfyUIService
from vplatform.services.material import MaterialFallbackService
from vplatform.services.provider_router import ProviderRouter
from vplatform.services.storyboard import StoryboardService
from vplatform.services.subtitle import SubtitleService
from vplatform.services.tts import TTSService
from vplatform.services.video_post import VideoPostService
from vplatform.tasks.manager import TaskManager


def _extract_style_anchor(image_prompt: str, max_len: int = 120) -> str:
    text = " ".join(image_prompt.split())
    text = re.sub(r"\s*,\s*8k\s*$", "", text, flags=re.IGNORECASE)
    return text[:max_len].rstrip(", ")


class StoryboardPipeline(LinearPipeline):
    def __init__(
        self,
        root: Path,
        config: VplatformConfig,
        tasks: TaskManager,
        comfyui: ComfyUIService | None = None,
    ) -> None:
        self.root = root
        self.config = config
        self.tasks = tasks
        self.router = ProviderRouter(root, config.provider, config.comfyui.endpoint)
        self.comfyui = comfyui or ComfyUIService(
            root=root,
            endpoint=config.comfyui.endpoint,
            timeout_sec=config.comfyui.timeout_sec,
            poll_interval=config.comfyui.poll_interval_sec,
        )
        self.storyboard_svc = StoryboardService(root, config.llm, config.pipeline)
        self.tts = TTSService(config.tts)
        self.subtitle = SubtitleService(config.subtitle)
        self.video_post = VideoPostService()
        self.material = MaterialFallbackService(config.material)

    def run(
        self,
        subject: str = "",
        stop_at: str = "final",
        profile: str = "fast",
        storyboard_file: str | None = None,
        task_id: str | None = None,
    ) -> TaskRecord:
        record = self.tasks.get(task_id) if task_id else None
        if not record:
            output_dir = self.root / "outputs" / "pipeline"
            output_dir.mkdir(parents=True, exist_ok=True)
            record = self.tasks.create(subject=subject, stop_at=stop_at)
            record.output_dir = str(self.root / "outputs" / record.task_id)
            Path(record.output_dir).mkdir(parents=True, exist_ok=True)
            self.tasks._persist(record)

        out = Path(record.output_dir)
        stop_at = stop_at or record.stop_at
        profile_params = self.config.pipeline.profiles.get(profile, {})
        pipe = self.config.pipeline

        try:
            # Step 1: 分镜
            self.tasks.update(record.task_id, stage=TaskStage.STORYBOARD, progress=0.1)
            if storyboard_file:
                sb = self.storyboard_svc.load_from_file(storyboard_file)
            else:
                sb = self.storyboard_svc.plan(subject, profile=profile)
            sb.save_json(str(out / "storyboard.json"))
            self.tasks.update(record.task_id, outputs={"storyboard": str(out / "storyboard.json")})
            self.tasks.write_stage_log(record.task_id, "storyboard", f"frames={len(sb.frames)}")
            if self.should_stop("storyboard", stop_at):
                return self.tasks.get(record.task_id)  # type: ignore[return-value]

            # Step 2: TTS
            self.tasks.update(record.task_id, stage=TaskStage.TTS, progress=0.2)
            tts_dir = out / "audio"
            for frame in sb.frames:
                frame.audio = self.tts.synthesize(frame, tts_dir)
                frame.duration_sec = frame.audio.duration_sec
            sb.save_json(str(out / "storyboard.json"))
            if self.should_stop("tts", stop_at):
                return self.tasks.get(record.task_id)  # type: ignore[return-value]

            # Step 3 起需要 ComfyUI
            endpoint, provider = self.router.select_endpoint()
            self.comfyui.api.endpoint = endpoint.rstrip("/")
            self.tasks.write_stage_log(record.task_id, "provider", f"使用 {provider} @ {endpoint}")

            # Step 3: 关键帧（首镜定调 + 并行生成）
            self.tasks.update(record.task_id, stage=TaskStage.KEYFRAME, progress=0.35)
            kf_dir = out / "keyframes"
            workflow = self._resolve_keyframe_workflow()
            style_anchor: str | None = None

            if sb.frames:
                first = sb.frames[0]
                path = self._generate_keyframe_with_retry(
                    first, kf_dir, workflow, profile_params, record.task_id, style_anchor=None
                )
                if path:
                    first.keyframe_path = path
                    self.material.reset_failures()
                    if pipe.use_keyframe_consistency:
                        style_anchor = _extract_style_anchor(first.image_prompt)
                        self.tasks.write_stage_log(
                            record.task_id, "keyframe", f"style_anchor={style_anchor[:60]}"
                        )
                else:
                    self._handle_keyframe_failure(first, kf_dir, record.task_id)

            remaining = sb.frames[1:]
            if remaining:
                max_workers = max(1, self.config.tasks.max_concurrent_comfyui)
                with ThreadPoolExecutor(max_workers=max_workers) as pool:
                    futures = {
                        pool.submit(
                            self._generate_keyframe_with_retry,
                            frame,
                            kf_dir,
                            workflow,
                            profile_params,
                            record.task_id,
                            style_anchor if pipe.use_keyframe_consistency else None,
                        ): frame
                        for frame in remaining
                    }
                    for future in as_completed(futures):
                        frame = futures[future]
                        try:
                            path = future.result()
                        except Exception as exc:
                            logger.warning("关键帧并行任务异常 frame={} err={}", frame.index, exc)
                            path = None
                        if path:
                            frame.keyframe_path = path
                            self.material.reset_failures()
                        else:
                            self._handle_keyframe_failure(frame, kf_dir, record.task_id)

            sb.save_json(str(out / "storyboard.json"))
            if self.should_stop("keyframe", stop_at):
                return self.tasks.get(record.task_id)  # type: ignore[return-value]

            # Step 4: I2V / Ken Burns
            self.tasks.update(record.task_id, stage=TaskStage.I2V, progress=0.55)
            clip_dir = out / "clips"
            i2v_targets = [
                f
                for f in sb.frames
                if not (f.material_fallback and f.clip_path) and f.keyframe_path
            ]
            max_workers = max(1, self.config.tasks.max_concurrent_comfyui)
            with ThreadPoolExecutor(max_workers=max_workers) as pool:
                futures = {
                    pool.submit(self._render_clip, frame, clip_dir, profile_params, record.task_id): frame
                    for frame in i2v_targets
                }
                for future in as_completed(futures):
                    frame = futures[future]
                    try:
                        future.result()
                    except Exception as exc:
                        logger.warning("片段渲染异常 frame={} err={}", frame.index, exc)
                        if not pipe.skip_failed_frames:
                            raise

            sb.save_json(str(out / "storyboard.json"))
            if self.should_stop("i2v", stop_at):
                return self.tasks.get(record.task_id)  # type: ignore[return-value]

            # Step 5: 拼接（支持 xfade 转场）
            self.tasks.update(record.task_id, stage=TaskStage.CONCAT, progress=0.7)
            clips = [f.clip_path for f in sb.frames if f.clip_path]
            if not clips:
                kf_ok = sum(1 for f in sb.frames if f.keyframe_path)
                raise RuntimeError(
                    f"无可用视频片段（关键帧成功={kf_ok}/{len(sb.frames)}，"
                    "请检查 ComfyUI 模型或配置 material.pexels_api_keys 降级）"
                )
            concat_path = out / "concat.mp4"
            self.video_post.concat_clips(
                clips,
                concat_path,
                fps=pipe.fps,
                transition=pipe.transition,
                transition_duration=pipe.transition_duration_sec,
            )
            self.tasks.update(record.task_id, outputs={"concat": str(concat_path)})
            if self.should_stop("concat", stop_at):
                return self.tasks.get(record.task_id)  # type: ignore[return-value]

            # Step 6: 字幕
            self.tasks.update(record.task_id, stage=TaskStage.SUBTITLE, progress=0.85)
            srt_path = self.subtitle.from_storyboard(sb, out)
            self.tasks.update(record.task_id, outputs={"subtitle": str(srt_path)})
            if self.should_stop("subtitle", stop_at):
                return self.tasks.get(record.task_id)  # type: ignore[return-value]

            # Step 7: 成片
            self.tasks.update(record.task_id, stage=TaskStage.FINAL, progress=0.95)
            bgm = self.video_post.pick_bgm(self.root / pipe.bgm_dir)
            muxed = out / "muxed.mp4"
            self.video_post.mux_narration(concat_path, sb, muxed, bgm_path=bgm)
            final = out / "final.mp4"
            self.video_post.burn_subtitles(muxed, srt_path, final)
            self.tasks.update(
                record.task_id,
                stage=TaskStage.FINAL,
                progress=1.0,
                outputs={"final": str(final), "storyboard": str(out / "storyboard.json")},
            )
            self.tasks.write_stage_log(record.task_id, "final", f"output={final}")
            logger.info("流水线完成 task_id={} final={}", record.task_id, final)
            return self.tasks.get(record.task_id)  # type: ignore[return-value]

        except Exception as exc:
            logger.exception("流水线失败 task_id={}", record.task_id)
            self.tasks.update(record.task_id, error=str(exc))
            self.tasks.write_stage_log(record.task_id, "error", str(exc))
            raise

    def _should_ken_burns(self, frame: StoryboardFrame) -> bool:
        pipe = self.config.pipeline
        if frame.render_mode == "ken_burns":
            return True
        if pipe.ken_burns_for_transitions and frame.shot_type == "transition":
            return True
        return False

    def _render_clip(
        self,
        frame: StoryboardFrame,
        clip_dir: Path,
        profile_params: dict[str, Any],
        task_id: str,
    ) -> None:
        duration = frame.audio.duration_sec if frame.audio else 3.0
        pipe = self.config.pipeline

        if self._should_ken_burns(frame) and frame.keyframe_path:
            out = clip_dir / f"kenburns_{frame.index:03d}.mp4"
            self.video_post.ken_burns_clip(
                frame.keyframe_path,
                duration,
                out,
                fps=pipe.fps,
                zoom=pipe.ken_burns_zoom,
            )
            frame.clip_path = str(out)
            self.tasks.write_stage_log(task_id, "i2v", f"frame={frame.index} mode=ken_burns")
            return

        last_exc: Exception | None = None
        for attempt in range(1, pipe.frame_max_retries + 2):
            try:
                path = self.comfyui.i2v(
                    frame.keyframe_path,
                    frame.motion_prompt or frame.image_prompt,
                    frame.negative_prompt,
                    duration,
                    clip_dir,
                    workflow_name=pipe.i2v_workflow,
                    profile=profile_params,
                    fps=pipe.fps,
                )
                frame.clip_path = str(path)
                self.material.reset_failures()
                return
            except ComfyUIError as exc:
                last_exc = exc
                self.tasks.write_stage_log(
                    task_id, "i2v", f"frame={frame.index} attempt={attempt} fail={exc}"
                )

        self.material.record_failure()
        if self.material.should_fallback():
            clip = self.material.download_clip(
                (frame.motion_prompt or frame.image_prompt)[:40],
                clip_dir,
                duration,
            )
            if clip:
                frame.clip_path = str(clip)
                frame.material_fallback = True
                return

        if pipe.skip_failed_frames:
            logger.warning("跳过失败分镜 frame={} err={}", frame.index, last_exc)
            self.tasks.write_stage_log(task_id, "i2v", f"frame={frame.index} skipped")
            return
        raise ComfyUIError(f"分镜 {frame.index} I2V 失败: {last_exc}") from last_exc

    def _handle_keyframe_failure(self, frame: StoryboardFrame, kf_dir: Path, task_id: str) -> None:
        self.material.record_failure()
        if self.material.should_fallback():
            clip = self.material.download_clip(
                frame.image_prompt[:40],
                kf_dir,
                frame.audio.duration_sec if frame.audio else 3.0,
            )
            if clip:
                frame.clip_path = str(clip)
                frame.material_fallback = True
                self.tasks.write_stage_log(task_id, "keyframe", f"frame={frame.index} pexels_fallback")

    def _resolve_keyframe_workflow(self) -> str:
        wan = self.config.pipeline.keyframe_workflow
        flux = self.config.pipeline.flux_workflow

        if not self.config.pipeline.use_flux_keyframe:
            logger.info("use_flux_keyframe=false，使用 {}", wan)
            return wan

        try:
            if self.comfyui.workflow_ready(flux):
                logger.info("FLUX 工作流就绪 workflow={}", flux)
                return flux
            logger.warning("FLUX 不可用，降级 {}", wan)
        except (FileNotFoundError, ComfyUIError) as exc:
            logger.warning("FLUX 检查失败 {}，降级 {}", exc, wan)
        return wan

    def _generate_keyframe_with_retry(
        self,
        frame: StoryboardFrame,
        kf_dir: Path,
        workflow: str,
        profile_params: dict[str, Any],
        task_id: str,
        style_anchor: str | None,
    ) -> str | None:
        pipe = self.config.pipeline
        prompt = frame.image_prompt
        if style_anchor and frame.index > 0:
            prompt = f"{style_anchor}, {prompt}"

        for attempt in range(1, pipe.frame_max_retries + 2):
            path = self._generate_keyframe(frame, kf_dir, workflow, profile_params, task_id, prompt)
            if path:
                return path
            self.tasks.write_stage_log(
                task_id, "keyframe", f"frame={frame.index} attempt={attempt} retry"
            )
        return None

    def _generate_keyframe(
        self,
        frame: StoryboardFrame,
        kf_dir: Path,
        workflow: str,
        profile_params: dict[str, Any],
        task_id: str,
        prompt: str | None = None,
    ) -> str | None:
        image_prompt = prompt or frame.image_prompt
        wan = self.config.pipeline.keyframe_workflow
        workflows = [workflow] if workflow == wan else [workflow, wan]

        for wf in workflows:
            try:
                path = self.comfyui.t2i(
                    image_prompt,
                    frame.negative_prompt,
                    kf_dir,
                    workflow_name=wf,
                    profile=profile_params,
                )
                if wf != workflow:
                    self.tasks.write_stage_log(
                        task_id, "keyframe", f"frame={frame.index} fallback={wf}"
                    )
                return str(path)
            except ComfyUIError as exc:
                self.tasks.write_stage_log(
                    task_id, "keyframe", f"frame={frame.index} workflow={wf} fail={exc}"
                )
        return None
