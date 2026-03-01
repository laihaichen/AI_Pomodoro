"""
companions.py — 学习助手类
======================================
Companion（学习助手）是玩家在游戏中可以招募的辅助角色。
每个助手拥有：
  - 基础属性（名称、描述、稀有度等）
  - 技能列表（Skill 实例，各自声明了 trigger_event）

钩子方法对应关系：
  on_move()      ← trigger_event = "on_move"      每次推进番茄钟（move.py）
  on_victory()   ← trigger_event = "on_victory"   宣布胜利结算（dashboard）
  on_defeat()    ← trigger_event = "on_defeat"    宣布失败结算（dashboard）
  on_rest_end()  ← trigger_event = "on_rest_end"  休息结束（continue.py）
  on_milestone() ← trigger_event = "on_milestone" 里程碑达成（update_stage.py）

运行时数据：
  - 今日激活的助手列表：data/active_companions.json
  - 主动技能待触发队列：data/pending_active_skills.json

当前阶段：骨架已含完整钩子，具体 Companion 子类待定义。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:
    from mod.skills import TriggerEvent

_DATA_DIR = Path(__file__).parent.parent / "data"
_ACTIVE_COMPANIONS_FILE  = _DATA_DIR / "active_companions.json"
_PENDING_SKILLS_FILE     = _DATA_DIR / "pending_active_skills.json"


# ── 工具函数 ─────────────────────────────────────────────────────────────────

def load_active_companions() -> "list[BaseCompanion]":
    """从 active_companions.json 读取今日激活的助手名称，返回对应实例列表。

    目前返回空列表（占位），待 Companion 注册表实现后补全。
    """
    try:
        names: list[str] = json.loads(_ACTIVE_COMPANIONS_FILE.read_text(encoding="utf-8"))
    except Exception:
        names = []
    # TODO: 从注册表按名称查找并实例化
    return []


def consume_pending_skills() -> list[str]:
    """读取并清空 pending_active_skills.json，返回技能名称列表（一次性消费）。"""
    try:
        skills: list[str] = json.loads(_PENDING_SKILLS_FILE.read_text(encoding="utf-8"))
    except Exception:
        skills = []
    _PENDING_SKILLS_FILE.write_text("[]", encoding="utf-8")
    return skills


def write_pending_skill(skill_name: str) -> None:
    """向 pending_active_skills.json 追加一个主动技能意图（dashboard 调用）。"""
    try:
        skills: list[str] = json.loads(_PENDING_SKILLS_FILE.read_text(encoding="utf-8"))
    except Exception:
        skills = []
    if skill_name not in skills:
        skills.append(skill_name)
    _PENDING_SKILLS_FILE.write_text(
        json.dumps(skills, ensure_ascii=False),
        encoding="utf-8",
    )


# ── 基类 ─────────────────────────────────────────────────────────────────────

class BaseCompanion:
    """所有学习助手的抽象基类。"""

    name: str = "unnamed_companion"
    description: str = ""
    rarity: str = "common"  # common / rare / epic / legendary

    def __init__(self, **kwargs: Any) -> None:
        self._params = kwargs
        self.skills: list = []  # 挂载的 Skill 实例列表

    # ------------------------------------------------------------------
    # 内部：按 trigger_event 筛选并激活
    # ------------------------------------------------------------------

    def _run_event(self, event: "TriggerEvent", context: dict) -> dict:
        for skill in self.skills:
            if skill.trigger_event == event:
                context = skill.activate(context)
        return context

    # ------------------------------------------------------------------
    # 钩子方法（由各调用方在对应时机调用）
    # ------------------------------------------------------------------

    def on_move(self, context: dict) -> dict:
        """每次推进番茄钟时触发（move.py）。"""
        return self._run_event("on_move", context)

    def on_victory(self, context: dict) -> dict:
        """宣布胜利结算时触发（dashboard）。"""
        return self._run_event("on_victory", context)

    def on_defeat(self, context: dict) -> dict:
        """宣布失败结算时触发（dashboard）。"""
        return self._run_event("on_defeat", context)

    def on_rest_end(self, context: dict) -> dict:
        """休息结束时触发（continue.py）。"""
        return self._run_event("on_rest_end", context)

    def on_milestone(self, context: dict) -> dict:
        """里程碑达成/失败结算时触发（update_stage.py）。"""
        return self._run_event("on_milestone", context)

    # ------------------------------------------------------------------
    # 辅助
    # ------------------------------------------------------------------

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}(name={self.name!r}, rarity={self.rarity!r})"
