"""通知渠道抽象。"""

from __future__ import annotations

from abc import ABC, abstractmethod


class Notifier(ABC):
    """所有通知渠道的最小接口。"""

    @abstractmethod
    def send(self, message: str) -> None:
        """发送文本；失败时抛异常，由 dispatcher 隔离。"""
