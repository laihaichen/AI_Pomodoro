"""
skills.py — 技能类
======================================
Skill 是 Condition + Effect 的组合结构，包含三个独立的限制维度：

  global_uses      整局最多触发 N 次（None = 无限）
  cooldown_turns   每次触发后 N 回合内不可再激活（None = 无 CD）
  effect_duration  每次触发后效果持续 N 回合（None = 即时，无持续期）

这三者互相独立，不能互相取代：
  "生效6回合，CD10回合"的技能 → effect_duration=6, cooldown_turns=10, global_uses=None

持久化文件（均存于 data/）：
  used_skills.json       → {技能名: 已触发次数}       （global_uses 追踪）
  skill_cooldowns.json   → {技能名: 上次触发时 count}  （CD 追踪）
  skill_effects.json     → {技能名: {started_at: count, duration: N}}  （生效期追踪）

trigger_event 字段声明触发时机：
  "on_move"     → 每次推进番茄钟（move.py）
  "on_victory"  → 宣布胜利结算（dashboard）
  "on_defeat"   → 宣布失败结算（dashboard）
  "on_rest_end" → 休息结束（continue.py）
  "on_milestone"→ 里程碑达成（update_stage.py）
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING, Literal

if TYPE_CHECKING:
    from mod.conditions import BaseCondition
    from mod.effects import BaseEffect

import sys
_PROJECT_ROOT = Path(__file__).parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))
from config import DATA_DIR as _DATA  # noqa: E402

_USED_SKILLS_FILE    = _DATA / "used_skills.json"
_COOLDOWNS_FILE      = _DATA / "skill_cooldowns.json"
_EFFECTS_FILE        = _DATA / "skill_effects.json"
_COMPANION_LOG_FILE  = _DATA / "companion_log.json"


# ── 磁盘 IO 工具 ─────────────────────────────────────────────────────────────

def _read(path: Path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def _write(path: Path, data) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def _append_companion_log(companion: str, skill: str, description: str) -> None:
    """向 companion_log.json 追加一条技能触发记录，供 dashboard 展示 Toast。"""
    from datetime import datetime
    logs = _read(_COMPANION_LOG_FILE, [])
    logs.append({
        "companion":   companion,
        "skill":       skill,
        "description": description,
        "ts":          datetime.now().strftime("%H:%M:%S"),
    })
    _write(_COMPANION_LOG_FILE, logs)


# ── 类型别名 ─────────────────────────────────────────────────────────────────

TriggerEvent = Literal[
    "on_pre_move",
    "on_move",
    "on_victory",
    "on_defeat",
    "on_rest_end",
    "on_milestone",
]


# ── Skill 类 ─────────────────────────────────────────────────────────────────

class Skill:
    """技能 = Condition 列表（AND）+ Effect 列表（顺序执行）。

    三个独立限制维度（均可为 None 表示"无此限制"）：
        global_uses     : 整局最多触发 N 次
        cooldown_turns  : 单次触发后 N 回合 CD
        effect_duration : 单次触发后效果持续 N 回合（影响 context["skill_active_*"]）

    active_or_passive:
        "passive" → 条件满足时自动触发
        "active"  → 需 context["player_used_skills"] 中包含 self.name
    """

    def __init__(
        self,
        name: str,
        conditions: "list[BaseCondition]",
        effects: "list[BaseEffect]",
        description: str = "",
        trigger_event: TriggerEvent = "on_move",
        active_or_passive: str = "passive",
        global_uses: "int | None" = None,       # 整局触发上限
        cooldown_turns: "int | None" = None,    # 触发后 CD 回合数
        effect_duration: "int | None" = None,   # 效果持续回合数
    ) -> None:
        self.name = name
        self.conditions: list[BaseCondition] = list(conditions)
        self.effects: list[BaseEffect] = list(effects)
        self.description = description
        self.trigger_event: TriggerEvent = trigger_event
        self.active_or_passive = active_or_passive
        self.global_uses = global_uses
        self.cooldown_turns = cooldown_turns
        self.effect_duration = effect_duration

    # ------------------------------------------------------------------
    # 磁盘查询
    # ------------------------------------------------------------------

    def used_count(self) -> int:
        return _read(_USED_SKILLS_FILE, {}).get(self.name, 0)

    def last_used_at(self) -> int:
        """上次触发时的 prompt_count（-1 表示从未使用）。"""
        return _read(_COOLDOWNS_FILE, {}).get(self.name, -1)

    def effect_started_at(self) -> int:
        """本次效果开始时的 prompt_count（-1 表示当前无生效中的效果）。"""
        return _read(_EFFECTS_FILE, {}).get(self.name, {}).get("started_at", -1)

    # ------------------------------------------------------------------
    # 状态查询（依赖 context 中的 current_prompt_count）
    # ------------------------------------------------------------------

    def is_global_expired(self) -> bool:
        if self.global_uses is None:
            return False
        return self.used_count() >= self.global_uses

    def is_on_cooldown(self, current_count: int) -> bool:
        if self.cooldown_turns is None:
            return False
        last = self.last_used_at()
        if last < 0:   # 从未使用过 → 不在 CD 中
            return False
        return current_count - last < self.cooldown_turns

    def is_in_effect(self, current_count: int) -> bool:
        """效果是否仍在持续（用于阻止重复激活，或向 effects 传递"当前生效"信号）。"""
        if self.effect_duration is None:
            return False
        started = self.effect_started_at()
        if started < 0:
            return False
        return current_count - started < self.effect_duration

    # ------------------------------------------------------------------
    # 核心接口
    # ------------------------------------------------------------------

    def can_activate(self, context: dict) -> bool:
        """检查技能是否可以触发：
          1. 全局次数未超限
          2. 不在 CD 中
          3. 效果未在生效中（有 effect_duration 的技能不可重叠激活）
          4. 若为主动技能，玩家本次明确选择了它
          5. 所有 Condition 满足（AND 逻辑）
        """
        count = context.get("current_prompt_count", 0)

        if self.is_global_expired():
            return False
        if self.is_on_cooldown(count):
            return False
        if self.effect_duration is not None and self.is_in_effect(count):
            return False
        if self.active_or_passive == "active":
            if self.name not in context.get("player_used_skills", []):
                return False
        return all(cond.is_met(context) for cond in self.conditions)

    def activate(self, context: dict) -> dict:
        """若条件满足则依序执行所有效果，并将状态写入磁盘。
        若技能处于生效期（is_in_effect），自动重复执行 effects（不消耗 uses/CD）。
        """
        count = context.get("current_prompt_count", 0)

        # ── 持续性效果：生效期内每回合自动执行，不消耗计数 ──
        if self.effect_duration is not None and self.is_in_effect(count):
            for effect in self.effects:
                context = effect.apply(context)
            started = self.effect_started_at()
            remaining = self.effect_duration - (count - started)
            _append_companion_log(
                companion=context.get("companion_name", "助手"),
                skill=self.name,
                description=f"{self.description or self.name}（剩余 {remaining} 回合）",
            )
            return context

        if not self.can_activate(context):
            return context

        for effect in self.effects:
            context = effect.apply(context)

        # ── 磁盘持久化 ───────────────────────────────────────────────
        # global_uses 计数
        if self.global_uses is not None:
            data = _read(_USED_SKILLS_FILE, {})
            data[self.name] = data.get(self.name, 0) + 1
            _write(_USED_SKILLS_FILE, data)

        # CD 记录
        if self.cooldown_turns is not None:
            data = _read(_COOLDOWNS_FILE, {})
            data[self.name] = count
            _write(_COOLDOWNS_FILE, data)

        # 生效期记录
        if self.effect_duration is not None:
            data = _read(_EFFECTS_FILE, {})
            data[self.name] = {"started_at": count, "duration": self.effect_duration}
            _write(_EFFECTS_FILE, data)

        # companion log（Toast 通知）
        _append_companion_log(
            companion=context.get("companion_name", "助手"),
            skill=self.name,
            description=self.description or self.name,
        )

        return context

    # ------------------------------------------------------------------
    # 辅助
    # ------------------------------------------------------------------

    def __repr__(self) -> str:
        parts = [f"Skill(name={self.name!r}", f"trigger={self.trigger_event}",
                 self.active_or_passive]
        if self.global_uses is not None:
            parts.append(f"uses={self.used_count()}/{self.global_uses}")
        if self.cooldown_turns is not None:
            parts.append(f"cd={self.cooldown_turns}回合")
        if self.effect_duration is not None:
            parts.append(f"duration={self.effect_duration}回合")
        return ", ".join(parts) + ")"
