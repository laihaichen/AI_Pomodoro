#!/usr/bin/env python3
"""increase_current_prompt_count.py — increment -current_prompt_count snippet.

Side effects on milestone transitions:
  count % 18 == 0          →  call update_stage.set_milestone()
  count % 18 == 1 and > 1  →  call update_stage.reset_stage()

Bind this script to the =move Alfred workflow so it runs automatically
every time a new prompt record is created.
"""
from __future__ import annotations

import json
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

# ── import sibling script ───────────────────────────────────────────────────
# Use a hardcoded absolute path so this works both in terminal AND when
# Alfred pastes the code into a temp file (where __file__ would point to /tmp/).
sys.path.insert(0, "/Users/haichenlai/Desktop/Prompt")
import update_stage  # noqa: E402

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

COUNT_UID      = "F1ABD0D4-576F-4CA6-B9A9-BB1715B961DB"
OFFSET_UID     = "E99CD789-4D10-4C17-9A3A-C5076BA33ADB"
TOTAL_REST_UID = "B3689D50-EEDD-42FC-A4E5-D19A70BA709B"

BASE           = Path("/Users/haichenlai/Desktop/Prompt")
FIRST_TS_FILE  = BASE / "first_timestamp.txt"
CURR_TS_FILE   = BASE / "curr_timestamp.txt"

def read_snippet_float(uid: str) -> float:
    """Read a float value from Alfred SQLite by UID. Returns 0.0 on failure."""
    with sqlite3.connect(DB_FILE) as con:
        row = con.execute(
            "SELECT snippet FROM snippets WHERE uid = ?", (uid,)
        ).fetchone()
    if row is None:
        return 0.0
    try:
        return float(row[0])
    except ValueError:
        return 0.0


def write_offset(value: float) -> None:
    """Write offset minutes to -offset snippet (DB + JSON)."""
    str_value = f"{value:.1f}"
    with sqlite3.connect(DB_FILE) as con:
        con.execute(
            "UPDATE snippets SET snippet = ? WHERE uid = ?",
            (str_value, OFFSET_UID),
        )
    matches = [
        p for p in SNIPPETS_DIR.iterdir()
        if p.name.startswith("-offset ") and p.suffix == ".json"
    ]
    if matches:
        payload = json.loads(matches[0].read_text(encoding="utf-8"))
        payload["alfredsnippet"]["snippet"] = str_value
        matches[0].write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )


def compute_and_write_offset(new_count: int) -> str:
    """
    offset = 期望总时间 - 真实总时间
           = (new_count × 10 + total_rest) - (curr_ts - first_ts)
    Returns a short status string for printing.
    """
    # Read timestamps
    def read_ts(path: Path) -> datetime | None:
        if not path.exists():
            return None
        text = path.read_text(encoding="utf-8").strip()
        return datetime.fromisoformat(text) if text else None

    first_ts = read_ts(FIRST_TS_FILE)
    curr_ts  = read_ts(CURR_TS_FILE)
    if first_ts is None or curr_ts is None:
        return "(offset 误差：时间戳文件缺失)"

    real_total   = (curr_ts - first_ts).total_seconds() / 60
    total_rest   = read_snippet_float(TOTAL_REST_UID)
    expect_total = new_count * 10 + total_rest
    offset       = expect_total - real_total

    write_offset(offset)
    return f"-offset = {offset:.1f} 分钟（期望 {expect_total:.1f} - 真实 {real_total:.1f}）"


def read_count() -> int:
    """Read current -current_prompt_count from Alfred SQLite DB."""
    with sqlite3.connect(DB_FILE) as con:
        row = con.execute(
            "SELECT snippet FROM snippets WHERE uid = ?", (COUNT_UID,)
        ).fetchone()
    if row is None:
        raise RuntimeError(f"UID {COUNT_UID!r} not found in DB")
    try:
        return int(row[0])
    except ValueError:
        raise RuntimeError(f"snippet value {row[0]!r} is not an integer")


def write_count(value: int) -> None:
    """Update SQLite + JSON for -current_prompt_count."""
    str_value = str(value)

    with sqlite3.connect(DB_FILE) as con:
        con.execute(
            "UPDATE snippets SET snippet = ? WHERE uid = ?",
            (str_value, COUNT_UID),
        )

    matches = [
        p for p in SNIPPETS_DIR.iterdir()
        if p.name.startswith("-current_prompt_count ") and p.suffix == ".json"
    ]
    if not matches:
        raise RuntimeError("-current_prompt_count JSON file not found")
    json_path = matches[0]
    payload = json.loads(json_path.read_text(encoding="utf-8"))
    payload["alfredsnippet"]["snippet"] = str_value
    json_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


# ── main ────────────────────────────────────────────────────────────────────

def main() -> int:
    try:
        current = read_count()
    except RuntimeError as exc:
        print(exc, file=sys.stderr)
        return 1

    new_count = current + 1

    try:
        write_count(new_count)
    except (RuntimeError, OSError) as exc:
        print(f"Write failed: {exc}", file=sys.stderr)
        return 1

    print(f"prompt count: {current} → {new_count}")

    # ── milestone state machine ─────────────────────────────────────────────
    try:
        if not update_stage.is_milestone_difficulty():
            # Explorer difficulty — milestone logic does not apply
            update_stage.set_not_applicable()
            print(f"ℹ️  探索者难度，阶段性节点不适用（-stage → 当前难度不适用）")

        elif new_count % 18 == 0:
            # Landed exactly on a milestone (18, 36, 54, ...)
            update_stage.set_milestone()
            print(f"🎯 阶段性节点触发：第 {new_count} 条记录（{new_count // 18} × 18）")

        elif new_count % 18 == 1 and new_count > 1:
            # One past a milestone (19, 37, 55, ...) — reset stage
            update_stage.reset_stage()
            print(f"🔄 阶段性节点已过，-stage 重置（第 {new_count} 条记录）")

        else:
            # Mid-game, no milestone event — but if stage was left as
            # "not applicable" from a previous explorer-difficulty run,
            # restore it to the default so it doesn't linger.
            if update_stage.read_stage() == update_stage.STAGE_NOT_APPLICABLE:
                update_stage.reset_stage()
                print("ℹ️  难度已切换回 milestone 模式，-stage 已还原为默认值")

    except RuntimeError as exc:
        print(f"Stage update failed: {exc}", file=sys.stderr)
        return 1

    # ── offset ──────────────────────────────────────────────────────────────
    try:
        offset_info = compute_and_write_offset(new_count)
        print(offset_info)
    except Exception as exc:
        print(f"Offset 计算失败: {exc}", file=sys.stderr)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
