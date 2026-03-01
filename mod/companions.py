"""
companions.py — 学习助手类 + 注册表 + 管理函数
======================================
Companion（学习助手）是玩家在游戏中可以招募的辅助角色。

运行时数据（data/）：
  active_companions.json     今日激活的助手名称列表（最多3个）
  companions_locked.txt      锁定状态（true/false）
  pending_active_skills.json 主动技能排队
  companion_log.json         技能触发 Toast 日志
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:
    from mod.skills import Skill, TriggerEvent

_DATA_DIR = Path(__file__).parent.parent / "data"
_ACTIVE_FILE    = _DATA_DIR / "active_companions.json"
_PENDING_FILE   = _DATA_DIR / "pending_active_skills.json"
_LOCKED_FILE    = _DATA_DIR / "companions_locked.txt"
_COOLDOWNS_FILE = _DATA_DIR / "skill_cooldowns.json"
_EFFECTS_FILE   = _DATA_DIR / "skill_effects.json"
_USED_FILE      = _DATA_DIR / "used_skills.json"

MAX_SLOTS = 3


# ── IO 工具 ──────────────────────────────────────────────────────────────────

def _read_json(path: Path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def _write_json(path: Path, data) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


# ── 锁定状态 ─────────────────────────────────────────────────────────────────

def is_locked() -> bool:
    try:
        return _LOCKED_FILE.read_text(encoding="utf-8").strip().lower() == "true"
    except Exception:
        return False


def lock() -> None:
    _LOCKED_FILE.write_text("true", encoding="utf-8")


# ── 激活列表管理 ─────────────────────────────────────────────────────────────

def _read_active_names() -> list[str]:
    return _read_json(_ACTIVE_FILE, [])


def _write_active_names(names: list[str]) -> None:
    _write_json(_ACTIVE_FILE, names)


def add_companion(name: str) -> tuple[bool, str]:
    """添加助手到槽位。返回 (成功?, 信息)。"""
    if is_locked():
        return False, "阵容已锁定"
    if name not in COMPANION_REGISTRY:
        return False, f"未知助手: {name}"
    active = _read_active_names()
    if len(active) >= MAX_SLOTS:
        return False, f"槽位已满（最多{MAX_SLOTS}个）"
    if name in active:
        return False, f"{name} 已在阵容中"
    active.append(name)
    _write_active_names(active)
    return True, f"{name} 已加入"


def remove_companion(name: str) -> tuple[bool, str]:
    """从槽位移除助手。返回 (成功?, 信息)。"""
    if is_locked():
        return False, "阵容已锁定"
    active = _read_active_names()
    if name not in active:
        return False, f"{name} 不在阵容中"
    active.remove(name)
    _write_active_names(active)
    return True, f"{name} 已移除"


# ── 主动技能排队 ─────────────────────────────────────────────────────────────

def consume_pending_skills() -> list[str]:
    """读取并清空 pending_active_skills.json，返回技能名称列表（一次性消费）。"""
    skills = _read_json(_PENDING_FILE, [])
    _PENDING_FILE.write_text("[]", encoding="utf-8")
    return skills


def write_pending_skill(skill_name: str) -> None:
    """向 pending_active_skills.json 追加一个主动技能意图（dashboard 调用）。"""
    skills = _read_json(_PENDING_FILE, [])
    if skill_name not in skills:
        skills.append(skill_name)
    _write_json(_PENDING_FILE, skills)


# ── 加载实例 ─────────────────────────────────────────────────────────────────

def load_active_companions() -> list[BaseCompanion]:
    """从 active_companions.json 读取激活助手名称，返回对应实例列表。"""
    names = _read_active_names()
    result = []
    for name in names:
        if name in COMPANION_REGISTRY:
            result.append(COMPANION_REGISTRY[name])
    return result


# ── 技能状态查询（供 dashboard API） ──────────────────────────────────────────

def get_skill_status(skill: "Skill", current_count: int) -> dict:
    """返回一个技能的当前状态信息字典。"""
    pending = _read_json(_PENDING_FILE, [])
    cooldowns = _read_json(_COOLDOWNS_FILE, {})
    effects = _read_json(_EFFECTS_FILE, {})
    used = _read_json(_USED_FILE, {})

    # CD 检查
    on_cd = False
    cd_remaining = 0
    if skill.cooldown_turns is not None:
        last = cooldowns.get(skill.name, -1)
        if last >= 0:
            elapsed = current_count - last
            if elapsed < skill.cooldown_turns:
                on_cd = True
                cd_remaining = skill.cooldown_turns - elapsed

    # 生效中检查
    in_effect = False
    effect_remaining = 0
    if skill.effect_duration is not None:
        eff = effects.get(skill.name, {})
        started = eff.get("started_at", -1)
        if started >= 0:
            elapsed = current_count - started
            if elapsed < skill.effect_duration:
                in_effect = True
                effect_remaining = skill.effect_duration - elapsed

    # 全局耗尽检查
    exhausted = False
    use_count = used.get(skill.name, 0)
    if skill.global_uses is not None and use_count >= skill.global_uses:
        exhausted = True

    # 已排队检查
    queued = skill.name in pending

    # 状态标签
    if exhausted:
        status = "exhausted"
        label = "已失效"
    elif in_effect:
        status = "in_effect"
        label = f"生效中（剩{effect_remaining}回合）"
    elif on_cd:
        status = "on_cooldown"
        label = f"冷却中（剩{cd_remaining}回合）"
    elif queued:
        status = "queued"
        label = "已排队"
    elif skill.active_or_passive == "passive":
        status = "passive"
        label = "被动"
    else:
        status = "available"
        label = "可使用"

    return {
        "name":        skill.name,
        "description": skill.description,
        "type":        skill.active_or_passive,
        "status":      status,
        "label":       label,
    }


def get_companion_status(current_count: int) -> list[dict]:
    """返回所有已装载助手及其技能状态（供 /api/companion-status 使用）。"""
    active_names = _read_active_names()
    result = []
    for name in active_names:
        comp = COMPANION_REGISTRY.get(name)
        if comp is None:
            continue
        skills_info = [get_skill_status(sk, current_count) for sk in comp.skills]
        result.append({
            "name":       comp.name,
            "avatar_url": comp.avatar_url,
            "description": comp.description,
            "skills":     skills_info,
        })
    return result


def get_registry_list() -> list[dict]:
    """返回所有可选助手的概要信息（供下拉列表使用）。"""
    return [
        {
            "name":       c.name,
            "avatar_url": c.avatar_url,
            "description": c.description[:80] if c.description else "",
        }
        for c in COMPANION_REGISTRY.values()
    ]


# ── 基类 ─────────────────────────────────────────────────────────────────────

class BaseCompanion:
    """所有学习助手的抽象基类。"""

    name: str = "unnamed_companion"
    description: str = ""
    avatar: str = ""   # 图片文件名，存于 static/companions/

    def __init__(self, **kwargs: Any) -> None:
        self._params = kwargs
        self.skills: list = []

    @property
    def avatar_url(self) -> str:
        if not self.avatar:
            return ""
        return f"/static/companions/{self.avatar}"

    # ------------------------------------------------------------------
    # 内部：按 trigger_event 筛选并激活
    # ------------------------------------------------------------------

    def _run_event(self, event: "TriggerEvent", context: dict) -> dict:
        context["companion_name"] = self.name
        for skill in self.skills:
            if skill.trigger_event == event:
                context = skill.activate(context)
        return context

    # ------------------------------------------------------------------
    # 钩子方法
    # ------------------------------------------------------------------

    def on_move(self, context: dict) -> dict:
        return self._run_event("on_move", context)

    def on_victory(self, context: dict) -> dict:
        return self._run_event("on_victory", context)

    def on_defeat(self, context: dict) -> dict:
        return self._run_event("on_defeat", context)

    def on_rest_end(self, context: dict) -> dict:
        return self._run_event("on_rest_end", context)

    def on_milestone(self, context: dict) -> dict:
        return self._run_event("on_milestone", context)

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}(name={self.name!r}, avatar={self.avatar!r})"


# ── 注册表 ───────────────────────────────────────────────────────────────────

COMPANION_REGISTRY: dict[str, BaseCompanion] = {}

_COMPANIONS_DIR = Path(__file__).parent.parent / "static" / "companions"


def _read_desc(filename: str) -> str:
    """从 static/companions/ 下的 .md 文件读取描述文本。"""
    p = _COMPANIONS_DIR / filename
    try:
        return p.read_text(encoding="utf-8").strip()
    except Exception:
        return ""


# ── 能天使 ────────────────────────────────────────────────────────────────────

def _make_exusiai() -> BaseCompanion:
    from mod.skills import Skill
    from mod.conditions import AlwaysCondition
    from mod.effects import FinalFateEffect

    comp = BaseCompanion()
    comp.name = "能天使"
    comp.avatar = "能天使.png"
    comp.description = _read_desc("能天使.md")
    comp.skills = [
        Skill(
            name="天使的祝福",
            description="无条件提供 +6 额外幸运值",
            conditions=[AlwaysCondition()],
            effects=[FinalFateEffect(delta=+6)],
            trigger_event="on_move",
            active_or_passive="passive",
        ),
    ]
    return comp


COMPANION_REGISTRY["能天使"] = _make_exusiai()
