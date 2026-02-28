"""
conditions.py — 技能/助手触发条件类
======================================
Condition 代表"某个学习助手技能是否可以触发"的判断逻辑。
未来可按需继承 BaseCondition 创建具体条件类型：
  - HealthCondition（健康度相关）
  - ScoreCondition（积分相关）
  - ProgressCondition（学习进度相关）
  - TimeCondition（时间/番茄钟相关）
等。

当前阶段：仅保留基础骨架，具体判断逻辑待定义。
"""

from __future__ import annotations
from typing import Any


class BaseCondition:
    """所有技能条件的抽象基类。"""

    name: str = "base_condition"
    description: str = ""

    def __init__(self, **kwargs: Any) -> None:
        # 预留：子类通过 kwargs 传入参数
        self._params = kwargs

    def is_met(self, context: dict) -> bool:
        """判断当前游戏上下文是否满足本条件。

        Args:
            context: 包含当前游戏状态的字典（如 health、score、progress 等）

        Returns:
            True 表示条件满足，False 表示不满足。
        """
        raise NotImplementedError

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}({self._params})"


class AlwaysCondition(BaseCondition):
    """永远满足的条件——用于无前提触发的技能。

    用法示例：
        skill = Skill(name="被动每轮触发", conditions=[always], effects=[...])
    """

    name = "always"
    description = "无任何前提，技能始终可触发。"

    def __init__(self) -> None:
        super().__init__()

    def is_met(self, context: dict) -> bool:  # noqa: ARG002
        return True

    def __repr__(self) -> str:
        return "AlwaysCondition()"


# 模块级单例，直接 import 使用：from mod.conditions import always
always = AlwaysCondition()

