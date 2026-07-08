"""LLM 分镜规划服务。"""

from __future__ import annotations

import json
import re
from pathlib import Path

import httpx
from loguru import logger

from vplatform.config.schema import LLMConfig, PipelineConfig
from vplatform.models.storyboard import Storyboard, StoryboardFrame, StoryboardMeta


class StoryboardService:
    def __init__(
        self,
        root: Path,
        llm_config: LLMConfig,
        pipeline_config: PipelineConfig,
    ) -> None:
        self.root = root
        self.llm_config = llm_config
        self.pipeline_config = pipeline_config
        self.prompt_path = root / "prompts" / "storyboard.txt"

    def plan(self, subject: str, profile: str = "fast") -> Storyboard:
        if not self.llm_config.api_key or not self.llm_config.base_url:
            logger.warning("LLM 未配置，使用模板分镜")
            return self._mock_storyboard(subject, profile)

        try:
            return self._llm_plan(subject, profile)
        except Exception as exc:
            logger.error("LLM 分镜失败，降级模板: {}", exc)
            return self._mock_storyboard(subject, profile)

    def load_from_file(self, path: str | Path) -> Storyboard:
        return Storyboard.load_json(str(path))

    def _system_prompt(self) -> str:
        if self.prompt_path.exists():
            return self.prompt_path.read_text(encoding="utf-8")
        return (
            "你是短视频分镜编剧。根据用户主题生成 JSON，格式："
            '{"title":"标题","frames":[{"index":0,"narration":"旁白","image_prompt":"英文图像描述",'
            '"motion_prompt":"英文运动描述","negative_prompt":"blurry, low quality"}]}。'
            f"生成 {self.pipeline_config.max_frames} 个以内分镜，旁白中文，prompt 英文。"
        )

    def _llm_plan(self, subject: str, profile: str) -> Storyboard:
        profile_params = self.pipeline_config.profiles.get(profile, {})
        width = profile_params.get("width", 512)
        height = profile_params.get("height", 288)

        payload = {
            "model": self.llm_config.model,
            "messages": [
                {"role": "system", "content": self._system_prompt()},
                {"role": "user", "content": f"主题：{subject}"},
            ],
            "temperature": 0.7,
        }
        url = f"{self.llm_config.base_url.rstrip('/')}/chat/completions"
        headers = {"Authorization": f"Bearer {self.llm_config.api_key}"}

        with httpx.Client(timeout=120) as client:
            resp = client.post(url, json=payload, headers=headers)
            resp.raise_for_status()
            content = resp.json()["choices"][0]["message"]["content"]

        data = self._extract_json(content)
        sb = Storyboard.model_validate(data)
        sb.meta = StoryboardMeta(
            aspect_ratio="16:9",
            fps=self.pipeline_config.fps,
            profile=profile,
            width=width,
            height=height,
        )
        logger.info("分镜生成完成 title={} frames={}", sb.title, len(sb.frames))
        return sb

    def _mock_storyboard(self, subject: str, profile: str) -> Storyboard:
        profile_params = self.pipeline_config.profiles.get(profile, {})
        frames = [
            StoryboardFrame(
                index=i,
                narration=f"关于{subject}，这是第{i + 1}个精彩画面。",
                image_prompt=f"Cinematic scene about {subject}, shot {i + 1}, studio lighting, 8k",
                motion_prompt=f"Slow camera movement, scene {i + 1} about {subject}",
            )
            for i in range(min(3, self.pipeline_config.max_frames))
        ]
        return Storyboard(
            title=subject,
            frames=frames,
            meta=StoryboardMeta(
                profile=profile,
                fps=self.pipeline_config.fps,
                width=profile_params.get("width", 512),
                height=profile_params.get("height", 288),
            ),
        )

    @staticmethod
    def _extract_json(text: str) -> dict:
        match = re.search(r"\{[\s\S]*\}", text)
        if not match:
            raise ValueError("LLM 响应中未找到 JSON")
        return json.loads(match.group())
