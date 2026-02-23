#!/usr/bin/env python3
"""=continue handler — record the end of a rest period and update -total_rest_time."""
from __future__ import annotations

import json
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

BASE = Path("/Users/haichenlai/Desktop/Prompt")
CONT_TS_FILE  = BASE / "continue_timestamp.txt"
PAUSE_TS_FILE = BASE / "pause_timestamp.txt"

# ── Alfred snippet config ───────────────────────────────────────────────────
DB_FILE = Path(
    "/Users/haichenlai/Library/Application Support/Alfred"
    "/Databases/snippets.alfdb"
)
SNIPPETS_DIR = (
    Path("/Users/haichenlai/Library/Application Support/Alfred"
         "/Alfred.alfredpreferences")
    / "snippets" / "学习时间追踪系统"
)
TOTAL_REST_UID = "B3689D50-EEDD-42FC-A4E5-D19A70BA709B"


# ── helpers ─────────────────────────────────────────────────────────────────

def read_total_rest() -> float:
    """Read current -total_rest_time from SQLite (in minutes)."""
    with sqlite3.connect(DB_FILE) as con:
        row = con.execute(
            "SELECT snippet FROM snippets WHERE uid = ?", (TOTAL_REST_UID,)
        ).fetchone()
    if row is None:
        raise RuntimeError(f"UID {TOTAL_REST_UID!r} not found in DB")
    try:
        return float(row[0])
    except ValueError:
        return 0.0  # treat malformed value as 0


def write_total_rest(value: float) -> None:
    """Write updated -total_rest_time to SQLite + JSON."""
    str_value = f"{value:.1f}"

    # SQLite (what Alfred reads live)
    with sqlite3.connect(DB_FILE) as con:
        con.execute(
            "UPDATE snippets SET snippet = ? WHERE uid = ?",
            (str_value, TOTAL_REST_UID),
        )

    # JSON (sync/backup)
    matches = [
        p for p in SNIPPETS_DIR.iterdir()
        if p.name.startswith("-total_rest_time ") and p.suffix == ".json"
    ]
    if not matches:
        raise RuntimeError("-total_rest_time JSON file not found")
    json_path = matches[0]
    payload = json.loads(json_path.read_text(encoding="utf-8"))
    payload["alfredsnippet"]["snippet"] = str_value
    json_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


# ── main ────────────────────────────────────────────────────────────────────

def main() -> int:
    now = datetime.now(tz=timezone.utc)

    # 1. Write continue timestamp (used by move.py for interval deduction)
    CONT_TS_FILE.write_text(now.isoformat(), encoding="utf-8")

    # 2. Calculate this rest's duration
    if not PAUSE_TS_FILE.exists():
        print(f"休息结束记录：{now.isoformat()}（未找到对应的 pause 记录）")
        return 0

    pause_text = PAUSE_TS_FILE.read_text(encoding="utf-8").strip()
    if not pause_text:
        print("休息结束：pause_timestamp.txt 为空，无法计算时长")
        return 0

    pause_ts = datetime.fromisoformat(pause_text)
    rest_min = (now - pause_ts).total_seconds() / 60

    # 3. Accumulate into -total_rest_time
    try:
        prev_total = read_total_rest()
        new_total  = prev_total + rest_min
        write_total_rest(new_total)
    except (RuntimeError, OSError) as exc:
        print(f"写入 -total_rest_time 失败：{exc}", file=sys.stderr)
        return 1

    print(
        f"休息结束：本次休息 {rest_min:.1f} 分钟  |  "
        f"今日累计休息 {new_total:.1f} 分钟"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
