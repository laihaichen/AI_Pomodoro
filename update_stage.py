#!/usr/bin/env python3
"""update_stage.py — set or reset the -stage Alfred snippet.

Can be called standalone or imported as a module by
increase_current_prompt_count.py.

Usage:
  python3 update_stage.py set    # set to milestone-reached alert
  python3 update_stage.py reset  # reset to "no milestone" default
"""
from __future__ import annotations

import json
import sqlite3
import sys

sys.path.insert(0, "/Users/haichenlai/Desktop/Prompt")
from config import DB_FILE, HEALTH_FILE, SNIPPETS  # noqa: E402

# ── stage strings ───────────────────────────────────────────────────────────

STAGE_DEFAULT        = SNIPPETS["stage"].default
STAGE_NOT_APPLICABLE = "当前难度不适用"

STAGE_MILESTONE = (
    "当前已经达到阶段性节点\n"
    "\n"
    "请检查用户是否完成阶段性任务\n"
    "\n"
    "如果用户成功完成阶段性任务，则发放奖励\n"
    "\n"
    "如果用户没有成功完成阶段性任务，则宣布游戏失败，退出时间追踪系统。\n"
    "\n"
    "阶段性奖励列表\n"
    "\n"
    "- [神圣干预：玩家为角色X+1岁的事件预判栏目选择一个命运值区间"
    "（高度正面85~100、中等正面50~84、轻度正面1~49、轻度负面-1~-30、"
    "中等负面-31~-60、严重负面-61~-89），并为该区间填写一个自定义的事件描述；"
    "该描述将替换AI原本生成的该区间事件内容；实际触发仍需命运值落在玩家选择的区间；"
    "⚠️ 约束：不能在负面事件里写正面情节，或在正面事件里写负面情节]\n"
    "\n"
    "- [宿命卡count + 1：玩家获得1张宿命卡，可在之后任意年龄使用]\n"
)

_REWARD_LIST = (
    "阶段性奖励列表\n"
    "\n"
    "- [神圣干预：玩家为角色X+1岁的事件预判栏目选择一个命运值区间"
    "（高度正面85~100、中等正面50~84、轻度正面1~49、轻度负面-1~-30、"
    "中等负面-31~-60、严重负面-61~-89），并为该区间填写一个自定义的事件描述；"
    "该描述将替换AI原本生成的该区间事件内容；实际触发仍需命运值落在玩家选择的区间；"
    "⚠️ 约束：不能在负面事件里写正面情节，或在正面事件里写负面情节]\n"
    "\n"
    "- [宿命卡count + 1：玩家获得1张宿命卡，可在之后任意年龄使用]\n"
)

STAGE_MILESTONE_SUCCESS = (
    "阶段性节点已达到，进度已达成！\n"
    "\n"
    "请发放奖励，要求玩家从奖励列表中选择一项\n"
    "\n"
    + _REWARD_LIST
)

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
    """Update SQLite (live) and JSON (backup) for -stage."""
    snip = SNIPPETS["stage"]
    with sqlite3.connect(DB_FILE) as con:
        con.execute("UPDATE snippets SET snippet = ? WHERE uid = ?", (value, snip.uid))
        if con.total_changes == 0:
            raise RuntimeError(f"UID {snip.uid!r} not found in DB")
    payload = json.loads(snip.json_path.read_text(encoding="utf-8"))
    payload["alfredsnippet"]["snippet"] = value
    snip.json_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def read_stage() -> str:
    """Return the current -stage snippet value, or empty string on failure."""
    snip = SNIPPETS["stage"]
    with sqlite3.connect(DB_FILE) as con:
        row = con.execute(
            "SELECT snippet FROM snippets WHERE uid = ?", (snip.uid,)
        ).fetchone()
    return row[0].strip() if row else ""


def read_difficulty() -> str:
    """Return the current -difficulty snippet value, or empty string on failure."""
    snip = SNIPPETS["difficulty"]
    with sqlite3.connect(DB_FILE) as con:
        row = con.execute(
            "SELECT snippet FROM snippets WHERE uid = ?", (snip.uid,)
        ).fetchone()
    return row[0].strip() if row else ""


def is_milestone_difficulty() -> bool:
    """Return True only when the selected difficulty supports milestone logic."""
    return read_difficulty() in MILESTONE_DIFFICULTIES


def read_progress_indicator() -> str:
    """Return the current -current-progress-indicator value from Alfred DB."""
    snip = SNIPPETS["current_progress_indicator"]
    with sqlite3.connect(DB_FILE) as con:
        row = con.execute(
            "SELECT snippet FROM snippets WHERE uid = ?", (snip.uid,)
        ).fetchone()
    return row[0].strip() if row else ""


def is_progress_reached(indicator: str) -> bool:
    """判断进度指示器是否显示“已到达进度”。
    格式举例： '3/5 已到达进度' → True
               '2/5 未到达进度' → False
    """
    return "已到达进度" in indicator


def adjust_health(delta: int) -> int:
    """delta 常为负数（如 -5）。返回更新后的健康度。"""
    try:
        current = int(HEALTH_FILE.read_text(encoding="utf-8").strip()) \
                  if HEALTH_FILE.exists() else 9
    except ValueError:
        current = 9
    new_val = max(0, min(current + delta, 10))
    HEALTH_FILE.parent.mkdir(parents=True, exist_ok=True)
    HEALTH_FILE.write_text(str(new_val), encoding="utf-8")
    return new_val


def check_and_set_milestone() -> None:
    """读取进度指示器，根据结果写入 -stage，未达成时自动扣除 -5 健康度。
    达成时：+200 总积分。"""
    indicator = read_progress_indicator()
    if is_progress_reached(indicator):
        _write_stage(STAGE_MILESTONE_SUCCESS)
        # 积分奖励 +300
        try:
            snip = SNIPPETS["total_score"]
            with sqlite3.connect(DB_FILE) as con:
                row = con.execute("SELECT snippet FROM snippets WHERE uid = ?", (snip.uid,)).fetchone()
            current = int(row[0]) if row else 0
            new_score = current + 200
            with sqlite3.connect(DB_FILE) as con:
                con.execute("UPDATE snippets SET snippet = ? WHERE uid = ?", (str(new_score), snip.uid))
            if snip.json_path.exists():
                payload = json.loads(snip.json_path.read_text(encoding="utf-8"))
                payload["alfredsnippet"]["snippet"] = str(new_score)
                snip.json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
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
