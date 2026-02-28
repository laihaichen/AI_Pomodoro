"""
effects.py — 技能/助手效果类
======================================
Effect 代表"技能触发后对游戏状态产生什么变化"。
未来可按需继承 BaseEffect 创建具体效果类型：
  - HealthEffect（修改健康度）
  - ScoreEffect（修改积分）
  - FateEffect（修改命运值计算）
  - RestEffect（修改休息时间限制）
等。

当前阶段：仅保留基础骨架，具体执行逻辑待定义。
"""

from __future__ import annotations
from typing import Any


class BaseEffect:
    """所有技能效果的抽象基类。"""

    name: str = "base_effect"
    description: str = ""

    def __init__(self, **kwargs: Any) -> None:
        # 预留：子类通过 kwargs 传入参数
        self._params = kwargs

    def apply(self, context: dict) -> dict:
        """执行效果，并返回更新后的上下文。

        Args:
            context: 包含当前游戏状态的字典

        Returns:
            应用效果后的上下文字典（可以是修改后的原对象或新对象）
        """
        raise NotImplementedError

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}({self._params})"
