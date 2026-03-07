#!/usr/bin/env python3
"""tests/test_mod.py — mod/ 核心逻辑测试

覆盖：
  - HealthEffect / FinalFateEffect 的 apply()
  - Skill 的 global_uses 消耗
  - _sync_muelsyse_skills 的槽位场景
  - on_pre_move 先于 on_move 的执行顺序
"""

import json
import sys
import tempfile
import shutil
from pathlib import Path

# ── 测试前：创建隔离的 data 目录，避免污染真实数据 ──────────────────────────
_PROJECT = Path(__file__).parent.parent
sys.path.insert(0, str(_PROJECT))

_TMP_DATA = Path(tempfile.mkdtemp())
_REAL_DATA = _PROJECT / "data"


def _reset_tmp():
    """清空临时 data 目录，复制最小必需文件。"""
    if _TMP_DATA.exists():
        shutil.rmtree(_TMP_DATA)
    _TMP_DATA.mkdir()
    (_TMP_DATA / "health.txt").write_text("9", encoding="utf-8")
    (_TMP_DATA / "active_companions.json").write_text("[]", encoding="utf-8")
    (_TMP_DATA / "used_skills.json").write_text("{}", encoding="utf-8")
    (_TMP_DATA / "skill_cooldowns.json").write_text("{}", encoding="utf-8")
    (_TMP_DATA / "skill_effects.json").write_text("{}", encoding="utf-8")
    (_TMP_DATA / "pending_active_skills.json").write_text("[]", encoding="utf-8")
    (_TMP_DATA / "companion_log.json").write_text("[]", encoding="utf-8")
    (_TMP_DATA / "companions_locked.txt").write_text("false", encoding="utf-8")


# ── 猴子补丁：把所有 data 路径指向临时目录 ─────────────────────────────────
import mod.skills as _skills
import mod.companions as _companions
import mod.effects as _effects

_skills._DATA = _TMP_DATA
_skills._USED_SKILLS_FILE = _TMP_DATA / "used_skills.json"
_skills._COOLDOWNS_FILE = _TMP_DATA / "skill_cooldowns.json"
_skills._EFFECTS_FILE = _TMP_DATA / "skill_effects.json"
_skills._COMPANION_LOG_FILE = _TMP_DATA / "companion_log.json"

_companions._DATA_DIR = _TMP_DATA
_companions._ACTIVE_FILE = _TMP_DATA / "active_companions.json"
_companions._PENDING_FILE = _TMP_DATA / "pending_active_skills.json"
_companions._LOCKED_FILE = _TMP_DATA / "companions_locked.txt"
_companions._COOLDOWNS_FILE = _TMP_DATA / "skill_cooldowns.json"
_companions._EFFECTS_FILE = _TMP_DATA / "skill_effects.json"
_companions._USED_FILE = _TMP_DATA / "used_skills.json"

_effects._HEALTH_FILE = _TMP_DATA / "health.txt"

from mod.effects import HealthEffect, FinalFateEffect
from mod.skills import Skill
from mod.conditions import AlwaysCondition
from mod.companions import (
    COMPANION_REGISTRY, _sync_muelsyse_skills,
    _write_active_names, load_active_companions,
)


# ═══════════════════════════════════════════════════════════════════════════════
# 1. Effects 测试
# ═══════════════════════════════════════════════════════════════════════════════

def test_health_effect_adds_delta():
    _reset_tmp()
    ctx = HealthEffect(delta=+1).apply({})
    assert ctx["health"] == 10, f"expected 10, got {ctx['health']}"
    raw = (_TMP_DATA / "health.txt").read_text().strip()
    assert raw == "10", f"file should be 10, got {raw}"
    print("  ✅ HealthEffect(+1): 9 → 10")


def test_health_no_floor_below_zero():
    _reset_tmp()
    HealthEffect(delta=-20).apply({})
    raw = int((_TMP_DATA / "health.txt").read_text().strip())
    assert raw == 0, f"health should floor at 0, got {raw}"
    print("  ✅ HealthEffect(-20): floor at 0")


def test_health_can_exceed_10():
    _reset_tmp()
    HealthEffect(delta=+1).apply({})  # 9 → 10
    HealthEffect(delta=+3).apply({})  # 10 → 13
    raw = int((_TMP_DATA / "health.txt").read_text().strip())
    assert raw == 13, f"health should be 13 (soft cap), got {raw}"
    print("  ✅ HealthEffect allows health > 10 (soft cap)")


def test_final_fate_effect():
    ctx = FinalFateEffect(delta=+6).apply({"final_fate": 50})
    assert ctx["final_fate"] == 56, f"expected 56, got {ctx['final_fate']}"
    print("  ✅ FinalFateEffect(+6): 50 → 56")


# ═══════════════════════════════════════════════════════════════════════════════
# 2. Skill global_uses 测试
# ═══════════════════════════════════════════════════════════════════════════════

def test_skill_global_uses_exhaustion():
    _reset_tmp()
    skill = Skill(
        name="test_once",
        conditions=[AlwaysCondition()],
        effects=[FinalFateEffect(delta=+1)],
        trigger_event="on_move",
        active_or_passive="passive",
        global_uses=1,
    )
    assert not skill.is_global_expired(), "should not be expired before use"
    ctx = skill.activate({"final_fate": 0, "current_prompt_count": 1, "companion_name": "test"})
    assert ctx["final_fate"] == 1, "effect should have fired"
    assert skill.is_global_expired(), "should be expired after 1 use"
    ctx2 = skill.activate({"final_fate": 0, "current_prompt_count": 2, "companion_name": "test"})
    assert ctx2["final_fate"] == 0, "effect should NOT fire (exhausted)"
    print("  ✅ global_uses=1: fires once then exhausted")


# ═══════════════════════════════════════════════════════════════════════════════
# 3. 缪尔赛思 _sync_muelsyse_skills 测试
# ═══════════════════════════════════════════════════════════════════════════════

def test_sync_copies_left_skills():
    _reset_tmp()
    _write_active_names(["赫默", "缪尔赛思"])
    _sync_muelsyse_skills()
    m = COMPANION_REGISTRY["缪尔赛思"]
    assert len(m.skills) == 1, f"expected 1 cloned skill, got {len(m.skills)}"
    assert m.skills[0].name == "流形·强化治疗"
    assert m.skills[0].trigger_event == "on_pre_move"
    assert m.skills[0].global_uses == 1
    print("  ✅ 左侧=赫默: 克隆 '流形·强化治疗' (on_pre_move, uses=1)")


def test_sync_copies_unlimited_skill():
    _reset_tmp()
    _write_active_names(["能天使", "缪尔赛思"])
    _sync_muelsyse_skills()
    m = COMPANION_REGISTRY["缪尔赛思"]
    assert len(m.skills) == 1
    assert m.skills[0].name == "流形·天使的祝福"
    assert m.skills[0].global_uses is None, "should inherit unlimited uses"
    print("  ✅ 左侧=能天使: 克隆 '流形·天使的祝福' (on_move, 无限)")


def test_sync_leftmost_no_skills():
    _reset_tmp()
    _write_active_names(["缪尔赛思"])
    _sync_muelsyse_skills()
    m = COMPANION_REGISTRY["缪尔赛思"]
    assert len(m.skills) == 0, "leftmost should have no skills"
    print("  ✅ 最左侧: 无技能")


def test_sync_independent_uses():
    """流形技能的使用次数独立于原技能"""
    _reset_tmp()
    _write_active_names(["赫默", "缪尔赛思"])
    _sync_muelsyse_skills()
    m = COMPANION_REGISTRY["缪尔赛思"]
    h = COMPANION_REGISTRY["赫默"]
    # 消耗流形技能
    m.skills[0].activate({"current_prompt_count": 1, "companion_name": "缪尔赛思"})
    assert m.skills[0].is_global_expired(), "流形 skill should be exhausted"
    # 赫默自己的原技能不受影响（名字不同 → 计数器独立）
    assert not h.skills[0].is_global_expired(), "赫默 original should NOT be exhausted"
    print("  ✅ 流形使用次数独立于原技能")


# ═══════════════════════════════════════════════════════════════════════════════
# 4. 执行顺序测试
# ═══════════════════════════════════════════════════════════════════════════════

def test_pre_move_before_move():
    """验证 on_pre_move 的 companions 先于 on_move 执行"""
    _reset_tmp()
    _write_active_names(["赫默", "能天使"])
    companions = load_active_companions()
    order = []
    for c in companions:
        for s in c.skills:
            order.append(s.trigger_event)
    # 赫默 on_pre_move 应在能天使 on_move 之前
    assert order == ["on_pre_move", "on_move"], f"unexpected order: {order}"
    print("  ✅ on_pre_move(赫默) 先于 on_move(能天使)")


# ═══════════════════════════════════════════════════════════════════════════════
# Runner
# ═══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    tests = [
        ("Effects", [
            test_health_effect_adds_delta,
            test_health_no_floor_below_zero,
            test_health_can_exceed_10,
            test_final_fate_effect,
        ]),
        ("Skill global_uses", [
            test_skill_global_uses_exhaustion,
        ]),
        ("缪尔赛思 sync", [
            test_sync_copies_left_skills,
            test_sync_copies_unlimited_skill,
            test_sync_leftmost_no_skills,
            test_sync_independent_uses,
        ]),
        ("执行顺序", [
            test_pre_move_before_move,
        ]),
    ]

    passed = failed = 0
    for group, fns in tests:
        print(f"\n{'─'*60}")
        print(f"  {group}")
        print(f"{'─'*60}")
        for fn in fns:
            try:
                fn()
                passed += 1
            except Exception as e:
                print(f"  ❌ {fn.__name__}: {e}")
                failed += 1

    print(f"\n{'═'*60}")
    print(f"  结果: {passed} passed, {failed} failed")
    print(f"{'═'*60}")

    # 清理临时目录
    shutil.rmtree(_TMP_DATA, ignore_errors=True)
    raise SystemExit(1 if failed else 0)
