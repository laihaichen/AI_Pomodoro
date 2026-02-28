"""
companions.py — 学习助手类
======================================
Companion（学习助手）是玩家在游戏中可以招募的辅助角色。
每个助手拥有：
  - 基础属性（名称、描述、稀有度等）
  - 被动技能列表（一组 condition + effect 的组合）

未来扩展方向：
  - PassiveSkill = BaseCondition + BaseEffect 的绑定
  - CompanionRegistry（助手注册表，管理所有可用助手）
  - 存档/读档集成（与 saves.jsonl 中的「今日学习助手列表」字段对接）

当前阶段：仅保留基础骨架，具体属性和技能待定义。
"""

from __future__ import annotations
from typing import Any


class BaseCompanion:
    """所有学习助手的抽象基类。"""

    name: str = "unnamed_companion"
    description: str = ""
    rarity: str = "common"  # common / rare / epic / legendary

    def __init__(self, **kwargs: Any) -> None:
        # 预留：子类通过 kwargs 传入个性化属性
        self._params = kwargs
        self.skills: list = []  # 待挂载的被动技能列表

    def on_move(self, context: dict) -> dict:
        """每次推进番茄钟时触发，遍历所有满足条件的技能并执行效果。

        Args:
            context: 当前游戏状态字典

        Returns:
            应用所有效果后的上下文字典
        """
        # 预留：遍历 self.skills，检查 condition.is_met 并调用 effect.apply
        return context

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}(name={self.name!r}, rarity={self.rarity!r})"
