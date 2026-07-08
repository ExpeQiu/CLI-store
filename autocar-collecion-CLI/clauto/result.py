"""统一抓取结果封装"""

from dataclasses import dataclass, field
from typing import Any, Generic, TypeVar

T = TypeVar("T")

SOURCE_LIVE = "live"
SOURCE_DEMO = "demo"
SOURCE_EMPTY = "empty"


@dataclass
class ScrapeResult(Generic[T]):
    """抓取结果，含数据来源标记"""

    data: T
    source: str = SOURCE_LIVE
    warnings: list[str] = field(default_factory=list)

    @property
    def is_demo(self) -> bool:
        return self.source == SOURCE_DEMO

    @property
    def is_live(self) -> bool:
        return self.source == SOURCE_LIVE

    @property
    def ok(self) -> bool:
        if self.source == SOURCE_DEMO:
            return True
        if isinstance(self.data, list):
            return len(self.data) > 0
        if isinstance(self.data, dict):
            return bool(self.data)
        return self.data is not None
