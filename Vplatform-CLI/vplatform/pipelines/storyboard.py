"""完整分镜流水线 — storyboard → TTS → keyframe → I2V → concat → subtitle → final。"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from loguru import logger

from vplatform.config.schema import VplatformConfig
from vplatform.models.storyboard import Storyboard
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

        try:
            # Step 1: 分镜（仅需 LLM/Mock，不依赖 ComfyUI）
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

            # Step 2: TTS（不依赖 ComfyUI）
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

            # Step 3: 关键帧
            self.tasks.update(record.task_id, stage=TaskStage.KEYFRAME, progress=0.35)
            kf_dir = out / "keyframes"
            workflow = self._resolve_keyframe_workflow()
            for frame in sb.frames:
                path = self._generate_keyframe(frame, kf_dir, workflow, profile_params, record.task_id)
                if path:
                    frame.keyframe_path = path
                    self.material.reset_failures()
                    continue
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
            sb.save_json(str(out / "storyboard.json"))
            if self.should_stop("keyframe", stop_at):
                return self.tasks.get(record.task_id)  # type: ignore[return-value]

            # Step 4: I2V
            self.tasks.update(record.task_id, stage=TaskStage.I2V, progress=0.55)
            clip_dir = out / "clips"
            for frame in sb.frames:
                if frame.material_fallback and frame.clip_path:
                    continue
                if not frame.keyframe_path:
                    continue
                duration = frame.audio.duration_sec if frame.audio else 3.0
                try:
                    path = self.comfyui.i2v(
                        frame.keyframe_path,
                        frame.motion_prompt or frame.image_prompt,
                        frame.negative_prompt,
                        duration,
                        clip_dir,
                        workflow_name=self.config.pipeline.i2v_workflow,
                        profile=profile_params,
                        fps=self.config.pipeline.fps,
                    )
                    frame.clip_path = str(path)
                    self.material.reset_failures()
                except ComfyUIError as exc:
                    self.material.record_failure()
                    self.tasks.write_stage_log(record.task_id, "i2v", f"frame={frame.index} fail={exc}")
                    if self.material.should_fallback():
                        clip = self.material.download_clip(
                            frame.motion_prompt[:40] or frame.image_prompt[:40],
                            clip_dir,
                            duration,
                        )
                        if clip:
                            frame.clip_path = str(clip)
                            frame.material_fallback = True
            sb.save_json(str(out / "storyboard.json"))
            if self.should_stop("i2v", stop_at):
                return self.tasks.get(record.task_id)  # type: ignore[return-value]

            # Step 5: 拼接
            self.tasks.update(record.task_id, stage=TaskStage.CONCAT, progress=0.7)
            clips = [f.clip_path for f in sb.frames if f.clip_path]
            if not clips:
                kf_ok = sum(1 for f in sb.frames if f.keyframe_path)
                raise RuntimeError(
                    f"无可用视频片段（关键帧成功={kf_ok}/{len(sb.frames)}，"
                    "请检查 ComfyUI 模型或配置 material.pexels_api_keys 降级）"
                )
            concat_path = out / "concat.mp4"
            self.video_post.concat_clips(clips, concat_path, fps=self.config.pipeline.fps)
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
            bgm = self.video_post.pick_bgm(self.root / self.config.pipeline.bgm_dir)
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

    def _generate_keyframe(
        self,
        frame: Any,
        kf_dir: Path,
        workflow: str,
        profile_params: dict[str, Any],
        task_id: str,
    ) -> str | None:
        wan = self.config.pipeline.keyframe_workflow
        workflows = [workflow] if workflow == wan else [workflow, wan]

        for wf in workflows:
            try:
                path = self.comfyui.t2i(
                    frame.image_prompt,
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

