"""
skills.py — 技能类
======================================
Skill 永远是 Condition + Effect 的组合结构。
自身不含业务逻辑，只负责：
  1. 检查所有 Condition 是否满足（AND 逻辑）
  2. 若满足，按序执行所有 Effect

设计原则：
  - Skill 是纯粹的"胶水层"，逻辑全部封装在 Condition/Effect 子类中
  - 单个 Condition/Effect 可跨多个 Skill 复用
  - 多条件（AND）和多效果（链式）均通过列表支持，无需改动接口

当前阶段：基础骨架，Condition/Effect 注入后即可使用。
"""

from __future__ import annotations
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from mod.conditions import BaseCondition
    from mod.effects import BaseEffect


class Skill:
    """技能 = Condition 列表（AND）+ Effect 列表（顺序执行）。"""

    def __init__(
        self,
        name: str,
        conditions: "list[BaseCondition]",
        effects: "list[BaseEffect]",
        description: str = "",
    ) -> None:
        """
        Args:
            name:        技能名称
            conditions:  触发条件列表，全部满足才执行效果（AND 逻辑）
            effects:     效果列表，条件满足时按序执行
            description: 技能说明（供 UI / 日志展示）
        """
        self.name = name
        self.conditions: list[BaseCondition] = list(conditions)
        self.effects: list[BaseEffect] = list(effects)
        self.description = description

    # ------------------------------------------------------------------
    # 核心接口
    # ------------------------------------------------------------------

    def can_activate(self, context: dict) -> bool:
        """检查所有条件是否均满足（AND 逻辑）。

        Args:
            context: 当前游戏状态字典（health、score、progress 等）

        Returns:
            True 表示技能可以触发。
        """
        return all(cond.is_met(context) for cond in self.conditions)

    def activate(self, context: dict) -> dict:
        """若条件满足则依序执行所有效果，并返回更新后的上下文。

        检查先于执行，若条件不满足则直接返回原 context（无副作用）。

        Args:
            context: 当前游戏状态字典

        Returns:
            执行所有效果后的上下文字典。
        """
        if not self.can_activate(context):
            return context
        for effect in self.effects:
            context = effect.apply(context)
        return context

    # ------------------------------------------------------------------
    # 辅助
    # ------------------------------------------------------------------

    def __repr__(self) -> str:
        cond_names = [c.__class__.__name__ for c in self.conditions]
        eff_names  = [e.__class__.__name__ for e in self.effects]
        return (
            f"Skill(name={self.name!r}, "
            f"conditions={cond_names}, "
            f"effects={eff_names})"
        )
