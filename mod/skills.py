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
    """技能 = Condition 列表（AND）+ Effect 列表（顺序执行）。

    属性说明：
        active_or_passive:
            "passive" → 条件满足时自动触发（无需玩家操作）
            "active"  → 需要玩家主动选择使用

        duration_turns / remaining_turns:
            None               → 永久生效，每回合均可触发（"每回合"）
            正整数 N            → 有限持续时长；remaining_turns 初始 = duration_turns，
                                  每次成功 activate 后自动递减，归零后技能失效（"接下来 N 回合"）
    """

    def __init__(
        self,
        name: str,
        conditions: "list[BaseCondition]",
        effects: "list[BaseEffect]",
        description: str = "",
        active_or_passive: str = "passive",    # "passive" | "active"
        duration_turns: "int | None" = None,   # None = 永久；正整数 = 持续回合数
    ) -> None:
        self.name = name
        self.conditions: list[BaseCondition] = list(conditions)
        self.effects: list[BaseEffect] = list(effects)
        self.description = description
        self.active_or_passive = active_or_passive
        self.duration_turns = duration_turns
        # remaining_turns 跟踪当前剩余回合；None 表示永久
        self.remaining_turns: "int | None" = duration_turns

    # ------------------------------------------------------------------
    # 状态查询
    # ------------------------------------------------------------------

    @property
    def is_expired(self) -> bool:
        """技能是否已耗尽（仅限有限持续技能）。"""
        return self.remaining_turns is not None and self.remaining_turns <= 0

    # ------------------------------------------------------------------
    # 核心接口
    # ------------------------------------------------------------------

    def can_activate(self, context: dict) -> bool:
        """检查技能是否可以触发（AND 逻辑 + 未过期检查）。"""
        if self.is_expired:
            return False
        return all(cond.is_met(context) for cond in self.conditions)

    def activate(self, context: dict) -> dict:
        """若条件满足则依序执行所有效果，并递减剩余回合数。

        若条件不满足或技能已过期，直接返回原 context（无副作用）。
        """
        if not self.can_activate(context):
            return context
        for effect in self.effects:
            context = effect.apply(context)
        # 递减剩余回合（永久技能 remaining_turns 为 None，不处理）
        if self.remaining_turns is not None:
            self.remaining_turns = max(0, self.remaining_turns - 1)
        return context

    # ------------------------------------------------------------------
    # 辅助
    # ------------------------------------------------------------------

    def __repr__(self) -> str:
        cond_names = [c.__class__.__name__ for c in self.conditions]
        eff_names  = [e.__class__.__name__ for e in self.effects]
        dur = f"∞" if self.duration_turns is None else f"{self.remaining_turns}/{self.duration_turns}回合"
        return (
            f"Skill(name={self.name!r}, "
            f"{self.active_or_passive}, "
            f"duration={dur}, "
            f"conditions={cond_names}, "
            f"effects={eff_names})"
        )
