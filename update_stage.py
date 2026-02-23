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
from pathlib import Path

# ── Alfred snippet config ───────────────────────────────────────────────────
PREFS = Path(
    "/Users/haichenlai/Library/Application Support/Alfred"
    "/Alfred.alfredpreferences"
)
DB_FILE = Path(
    "/Users/haichenlai/Library/Application Support/Alfred"
    "/Databases/snippets.alfdb"
)
SNIPPETS_DIR = PREFS / "snippets" / "学习时间追踪系统"

STAGE_UID      = "DB01CF4F-8C54-4F29-B535-9E99BEC5A4B3"
DIFFICULTY_UID = "BDEE3C98-A4A1-4A2B-9046-18A12FD66083"

# Difficulties that support milestone logic
MILESTONE_DIFFICULTIES = {"平衡难度", "硬核难度"}

# ── stage strings ───────────────────────────────────────────────────────────

STAGE_DEFAULT        = "当前没有达到阶段性节点"
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

# ── helpers ─────────────────────────────────────────────────────────────────

def write_snippet(uid: str, value: str) -> None:
    """Update SQLite (live) and JSON (backup) for the given snippet UID."""
    # 1. SQLite
    with sqlite3.connect(DB_FILE) as con:
        con.execute("UPDATE snippets SET snippet = ? WHERE uid = ?", (value, uid))
        if con.total_changes == 0:
            raise RuntimeError(f"UID {uid!r} not found in DB")

    # 2. JSON — find by prefix since [ ] break glob
    matches = [
        p for p in SNIPPETS_DIR.iterdir()
        if p.name.startswith("-stage ") and p.suffix == ".json"
    ]
    if not matches:
        raise RuntimeError("-stage JSON file not found in snippets dir")
    json_path = matches[0]
    payload = json.loads(json_path.read_text(encoding="utf-8"))
    payload["alfredsnippet"]["snippet"] = value
    json_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def read_stage() -> str:
    """Return the current -stage snippet value, or empty string on failure."""
    with sqlite3.connect(DB_FILE) as con:
        row = con.execute(
            "SELECT snippet FROM snippets WHERE uid = ?", (STAGE_UID,)
        ).fetchone()
    return row[0].strip() if row else ""


def read_difficulty() -> str:
    """Return the current -difficulty snippet value, or empty string on failure."""
    with sqlite3.connect(DB_FILE) as con:
        row = con.execute(
            "SELECT snippet FROM snippets WHERE uid = ?", (DIFFICULTY_UID,)
        ).fetchone()
    return row[0].strip() if row else ""


def is_milestone_difficulty() -> bool:
    """Return True only when the selected difficulty supports milestone logic."""
    return read_difficulty() in MILESTONE_DIFFICULTIES


def set_milestone() -> None:
    write_snippet(STAGE_UID, STAGE_MILESTONE)
    print("✅ -stage → 阶段性节点 alert 已写入")


def reset_stage() -> None:
    write_snippet(STAGE_UID, STAGE_DEFAULT)
    print("✅ -stage → 默认值（当前没有达到阶段性节点）已写入")


def set_not_applicable() -> None:
    write_snippet(STAGE_UID, STAGE_NOT_APPLICABLE)
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
