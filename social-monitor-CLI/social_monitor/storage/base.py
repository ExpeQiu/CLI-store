from abc import ABC, abstractmethod
from typing import Any, Dict, List


class BaseStorage(ABC):
    """存储基类"""

    @abstractmethod
    def save(
        self, platform: str, account_id: str, items: List[Dict[str, Any]], mode: str = "append"
    ) -> int:
        """保存数据，返回总条数"""

    @abstractmethod
    def load(self, platform: str, account_id: str) -> List[Dict[str, Any]]:
        """加载数据"""
