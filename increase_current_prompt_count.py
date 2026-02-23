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
from pathlib import Path

# ── import sibling script ───────────────────────────────────────────────────
sys.path.insert(0, str(Path(__file__).parent))
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

COUNT_UID = "F1ABD0D4-576F-4CA6-B9A9-BB1715B961DB"

# ── helpers ─────────────────────────────────────────────────────────────────

def read_count() -> int:
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
        if new_count % 18 == 0:
            # Landed exactly on a milestone (18, 36, 54, ...)
            update_stage.set_milestone()
            print(f"🎯 阶段性节点触发：第 {new_count} 条记录（{new_count // 18} × 18）")

        elif new_count % 18 == 1 and new_count > 1:
            # One past a milestone (19, 37, 55, ...) — reset stage
            update_stage.reset_stage()
            print(f"🔄 阶段性节点已过，-stage 重置（第 {new_count} 条记录）")

    except RuntimeError as exc:
        print(f"Stage update failed: {exc}", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
