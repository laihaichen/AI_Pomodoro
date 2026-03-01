"""
skills.py — 技能类
======================================
Skill 永远是 Condition + Effect 的组合结构。
自身不含业务逻辑，只负责：
  1. 检查所有 Condition 是否满足（AND 逻辑）
  2. 检查全局触发次数是否未超限（写入磁盘持久化）
  3. 若满足，按序执行所有 Effect

trigger_event 字段声明技能在哪个时机被触发：
  "on_move"     → 每次推进番茄钟时（move.py）
  "on_victory"  → 宣布胜利结算时（dashboard）
  "on_defeat"   → 宣布失败结算时（dashboard）
  "on_rest_end" → 休息结束时（continue.py）
  "on_milestone"→ 里程碑达成时（update_stage.py）

global_uses：全局触发次数上限（跨进程持久化到 data/used_skills.json）
  None  → 无限制（默认）
  N > 0 → 整局游戏最多触发 N 次，超过后永久失效

注意：因为 move.py 每次调用都是新进程，纯内存的 duration_turns 方案
      无法跨进程保留状态，因此统一使用磁盘计数器（global_uses）。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING, Literal

if TYPE_CHECKING:
    from mod.conditions import BaseCondition
    from mod.effects import BaseEffect

_USED_SKILLS_FILE = Path(__file__).parent.parent / "data" / "used_skills.json"


def _load_used_skills() -> dict[str, int]:
    try:
        return json.loads(_USED_SKILLS_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _save_used_skills(data: dict[str, int]) -> None:
    _USED_SKILLS_FILE.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


TriggerEvent = Literal[
    "on_move",
    "on_victory",
    "on_defeat",
    "on_rest_end",
    "on_milestone",
]


class Skill:
    """技能 = Condition 列表（AND）+ Effect 列表（顺序执行）。

    属性说明：
        trigger_event:
            声明该技能在哪个游戏时机被触发（见模块顶部注释）。
            默认 "on_move"。

        active_or_passive:
            "passive" → 条件满足时自动触发（无需玩家操作）
            "active"  → 需要玩家主动选择；
                        context["player_used_skills"] 中需包含 self.name。

        global_uses:
            None  → 无次数限制，可无限触发。
            N > 0 → 整局游戏最多触发 N 次（磁盘持久化计数，跨进程安全）。
    """

    def __init__(
        self,
        name: str,
        conditions: "list[BaseCondition]",
        effects: "list[BaseEffect]",
        description: str = "",
        trigger_event: TriggerEvent = "on_move",
        active_or_passive: str = "passive",      # "passive" | "active"
        global_uses: "int | None" = None,        # None = 无限；正整数 = 全局限制次数
    ) -> None:
        self.name = name
        self.conditions: list[BaseCondition] = list(conditions)
        self.effects: list[BaseEffect] = list(effects)
        self.description = description
        self.trigger_event: TriggerEvent = trigger_event
        self.active_or_passive = active_or_passive
        self.global_uses = global_uses

    # ------------------------------------------------------------------
    # 磁盘持久化：次数查询 / 记录
    # ------------------------------------------------------------------

    def used_count(self) -> int:
        """从磁盘读取该技能已触发的次数。"""
        return _load_used_skills().get(self.name, 0)

    def _record_use(self) -> None:
        """在磁盘计数器里将该技能的触发次数 +1。"""
        data = _load_used_skills()
        data[self.name] = data.get(self.name, 0) + 1
        _save_used_skills(data)

    # ------------------------------------------------------------------
    # 状态查询
    # ------------------------------------------------------------------

    @property
    def is_expired(self) -> bool:
        """技能是否已耗尽全局次数限制（从磁盘读取）。"""
        if self.global_uses is None:
            return False
        return self.used_count() >= self.global_uses

    # ------------------------------------------------------------------
    # 核心接口
    # ------------------------------------------------------------------

    def can_activate(self, context: dict) -> bool:
        """检查技能是否可以触发：
          1. 全局次数未超限
          2. 若为主动技能，玩家本次明确选择了它
          3. 所有 Condition 满足（AND 逻辑）
        """
        if self.is_expired:
            return False
        if self.active_or_passive == "active":
            if self.name not in context.get("player_used_skills", []):
                return False
        return all(cond.is_met(context) for cond in self.conditions)

    def activate(self, context: dict) -> dict:
        """若条件满足则依序执行所有效果，并将触发次数写入磁盘。

        若条件不满足或次数已超限，直接返回原 context（无副作用）。
        """
        if not self.can_activate(context):
            return context
        for effect in self.effects:
            context = effect.apply(context)
        if self.global_uses is not None:
            self._record_use()
        return context

    # ------------------------------------------------------------------
    # 辅助
    # ------------------------------------------------------------------

    def __repr__(self) -> str:
        cond_names = [c.__class__.__name__ for c in self.conditions]
        eff_names  = [e.__class__.__name__ for e in self.effects]
        if self.global_uses is None:
            uses_str = "∞"
        else:
            used = self.used_count()
            uses_str = f"{used}/{self.global_uses}次"
        return (
            f"Skill(name={self.name!r}, "
            f"trigger={self.trigger_event}, "
            f"{self.active_or_passive}, "
            f"uses={uses_str}, "
            f"conditions={cond_names}, "
            f"effects={eff_names})"
        )
