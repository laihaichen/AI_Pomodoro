#!/usr/bin/env python3
"""update_stage.py — set or reset the -stage Alfred snippet.

Can be called standalone or imported as a module by
increase_current_prompt_count.py.

Usage:
  python3 update_stage.py set    # set to milestone-reached alert
  python3 update_stage.py reset  # reset to "no milestone" default
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from config import HEALTH_FILE, SNIPPETS, DATA_DIR, read_snippet, write_snippet  # noqa: E402

MILESTONE_REWARD_FLAG = DATA_DIR / "milestone_reward.flag"


def is_milestone_reward_pending() -> bool:
    return MILESTONE_REWARD_FLAG.exists()


def set_milestone_reward(on: bool) -> None:
    if on:
        MILESTONE_REWARD_FLAG.parent.mkdir(parents=True, exist_ok=True)
        MILESTONE_REWARD_FLAG.write_text("1", encoding="utf-8")
    else:
        MILESTONE_REWARD_FLAG.unlink(missing_ok=True)

# ── stage strings ───────────────────────────────────────────────────────────

STAGE_DEFAULT        = SNIPPETS["stage"].default
STAGE_NOT_APPLICABLE = "当前难度不适用"


STAGE_MILESTONE_SUCCESS = "阶段性节点已达到，进度已达成！"

STAGE_MILESTONE_FAIL = (
    "阶段性节点已达到，但进度未达成\n"
    "\n"
    "健康度已由后台自动扣除 -5\n"
    "\n"
    "请在面板上确认健康度数值是否正确\n"
)

# Difficulties that support milestone logic
MILESTONE_DIFFICULTIES = {"平衡难度", "硬核难度"}


# ── helpers ─────────────────────────────────────────────────────────────────

def _write_stage(value: str) -> None:
    """Update -stage snippet."""
    write_snippet("stage", value)


def read_stage() -> str:
    """Return the current -stage snippet value."""
    return read_snippet("stage").strip()


def read_difficulty() -> str:
    """Return the current -difficulty snippet value."""
    return read_snippet("difficulty").strip()


def is_milestone_difficulty() -> bool:
    """Return True only when the selected difficulty supports milestone logic."""
    return read_difficulty() in MILESTONE_DIFFICULTIES


def read_progress_indicator() -> str:
    """Return the current -current-progress-indicator value."""
    return read_snippet("current_progress_indicator").strip()


def is_progress_reached(indicator: str) -> bool:
    """判断进度指示器是否显示“已到达进度”。
    格式举例： '3/5 已到达进度' → True
               '2/5 未到达进度' → False
    """
    return "已到达进度" in indicator or "已提前达成" in indicator


def adjust_health(delta: int) -> int:
    """delta 常为负数（如 -5）。返回更新后的健康度。"""
    try:
        current = int(HEALTH_FILE.read_text(encoding="utf-8").strip()) \
                  if HEALTH_FILE.exists() else 9
    except ValueError:
        current = 9
    new_val = max(0, current + delta)
    HEALTH_FILE.parent.mkdir(parents=True, exist_ok=True)
    HEALTH_FILE.write_text(str(new_val), encoding="utf-8")
    return new_val


def check_and_set_milestone() -> None:
    """读取进度指示器，根据结果写入 -stage，未达成时自动扣除 -5 健康度。
    达成时：+200 总积分。"""
    indicator = read_progress_indicator()
    if is_progress_reached(indicator):
        _write_stage(STAGE_MILESTONE_SUCCESS)
        set_milestone_reward(True)  # 标记阶段性奖励待领取
        # 积分奖励 +200
        try:
            current = int(read_snippet("total_score") or "0")
            new_score = current + 200
            write_snippet("total_score", str(new_score))
            print(f"✅ 进度已达成（{indicator}）  -stage → 奖励模式  总积分 +300 → {new_score}")
        except Exception as exc:
            print(f"⚠️  总积分写入失败: {exc}")
            print(f"✅ 进度已达成（{indicator}）  -stage → 奖励模式")
    else:
        new_health = adjust_health(-5)
        _write_stage(STAGE_MILESTONE_FAIL)
        print(f"⚠️  进度未达成（{indicator}）  -5 健康度 → {new_health}，-stage → 惩罚模式")


def set_milestone() -> None:
    """Backward-compat alias: 自动检测进度并写入对应结果。"""
    check_and_set_milestone()


def reset_stage() -> None:
    _write_stage(STAGE_DEFAULT)
    print("✅ -stage → 默认值（当前没有达到阶段性节点）已写入")


def set_not_applicable() -> None:
    _write_stage(STAGE_NOT_APPLICABLE)
    print("✅ -stage → 当前难度不适用（探索者难度）已写入")


# ── main (standalone usage) ─────────────────────────────────────────────────

def main() -> int:
    if len(sys.argv) < 2 or sys.argv[1] not in ("set", "reset"):
        print("Usage: python3 update_stage.py set | reset", file=sys.stderr)
        return 1
    try:
        if sys.argv[1] == "set":
            set_milestone()
        else:
            reset_stage()
    except RuntimeError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
