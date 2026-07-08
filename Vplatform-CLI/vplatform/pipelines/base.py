"""线性流水线基类 — 模板方法。"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from vplatform.models.task import STOP_AT_STAGES, TaskRecord


class LinearPipeline(ABC):
    @abstractmethod
    def run(self, **kwargs: Any) -> TaskRecord:
        ...

    @staticmethod
    def should_stop(current_stage: str, stop_at: str) -> bool:
        if stop_at not in STOP_AT_STAGES:
            return False
        order = STOP_AT_STAGES
        return order.index(current_stage) >= order.index(stop_at)
