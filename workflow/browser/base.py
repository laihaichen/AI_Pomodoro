#!/usr/bin/env python3
"""浏览器驱动抽象接口。"""
from __future__ import annotations

from abc import ABC, abstractmethod


class BrowserDriver(ABC):
    """所有浏览器驱动必须实现此接口。"""

    @abstractmethod
    def inject_and_send(self, text: str) -> bool:
        """将 text 注入 AI 聊天输入框并点击发送。

        Returns:
            True 如果成功发送到至少一个页面，False 否则。
        """
        ...
