#!/usr/bin/env python3
"""update_h.py — shared module for accumulating H and writing -overtime-penalty-range.

H (超时惩罚数字) accumulates from two sources:
  1. move.py   : interval > 20 min  →  H += (interval - 20)
  2. continue.py: total_rest > max_rest  →  H += (total_rest - penalized_rest_up_to)

-overtime-penalty-range format:
  H == 0  →  "{random:0..0}"   (no penalty, Alfred expands to 0)
  H >  0  →  "{random:1..2H}"  e.g. H=11 → "{random:1..22}"

State files (in /Users/haichenlai/Desktop/Prompt/):
  h_value.txt               : current H (float, minutes), default 0
  penalized_rest_up_to.txt  : total_rest already penalized (float, minutes),
                              initialised to max_rest_time on reset
"""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path

# ── paths ───────────────────────────────────────────────────────────────────
BASE = Path("/Users/haichenlai/Desktop/Prompt")
H_FILE                  = BASE / "h_value.txt"
PENALIZED_REST_FILE     = BASE / "penalized_rest_up_to.txt"

DB_FILE = Path(
    "/Users/haichenlai/Library/Application Support/Alfred"
    "/Databases/snippets.alfdb"
)
SNIPPETS_DIR = (
    Path("/Users/haichenlai/Library/Application Support/Alfred"
         "/Alfred.alfredpreferences")
    / "snippets" / "学习时间追踪系统"
)

OVERTIME_RANGE_UID  = "D3D8CE6B-3AE4-4A88-91A2-9D23E0804E2D"
MAX_REST_UID        = "D197E8BC-85F4-45D0-82D4-814FA0DCA629"


# ── state helpers ────────────────────────────────────────────────────────────

def read_h() -> float:
    """Read current H from file (minutes). Returns 0 if file missing/empty."""
    if not H_FILE.exists():
        return 0.0
    text = H_FILE.read_text(encoding="utf-8").strip()
    try:
        return float(text) if text else 0.0
    except ValueError:
        return 0.0


def write_h(value: float) -> None:
    H_FILE.write_text(f"{value:.2f}", encoding="utf-8")


def read_penalized_rest() -> float:
    """Minutes of rest already charged to H. Initialised to max_rest on reset."""
    if not PENALIZED_REST_FILE.exists():
        return read_max_rest()   # conservative: treat as if no penalty yet
    text = PENALIZED_REST_FILE.read_text(encoding="utf-8").strip()
    try:
        return float(text) if text else read_max_rest()
    except ValueError:
        return read_max_rest()


def write_penalized_rest(value: float) -> None:
    PENALIZED_REST_FILE.write_text(f"{value:.2f}", encoding="utf-8")


def read_max_rest() -> float:
    """Read -max_rest_time snippet from SQLite."""
    with sqlite3.connect(DB_FILE) as con:
        row = con.execute(
            "SELECT snippet FROM snippets WHERE uid = ?", (MAX_REST_UID,)
        ).fetchone()
    if row is None:
        return 0.0
    try:
        return float(row[0])
    except ValueError:
        return 0.0


# ── snippet writer ────────────────────────────────────────────────────────────

def write_overtime_range(h: float) -> None:
    """Write the Alfred dynamic placeholder for -overtime-penalty-range."""
    h_int = int(h)   # truncate — only whole minutes count
    if h_int <= 0:
        range_str = "{random:0..0}"
    else:
        range_str = "{random:1.." + str(h_int * 2) + "}"

    # SQLite
    with sqlite3.connect(DB_FILE) as con:
        con.execute(
            "UPDATE snippets SET snippet = ? WHERE uid = ?",
            (range_str, OVERTIME_RANGE_UID),
        )

    # JSON
    matches = [
        p for p in SNIPPETS_DIR.iterdir()
        if p.name.startswith("-overtime-penalty-range ") and p.suffix == ".json"
    ]
    if matches:
        json_path = matches[0]
        payload = json.loads(json_path.read_text(encoding="utf-8"))
        payload["alfredsnippet"]["snippet"] = range_str
        json_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )


# ── public API ────────────────────────────────────────────────────────────────

def accumulate_h(delta_minutes: float) -> float:
    """Add delta_minutes to H, update -overtime-penalty-range. Returns new H."""
    if delta_minutes <= 0:
        return read_h()
    new_h = read_h() + delta_minutes
    write_h(new_h)
    write_overtime_range(new_h)
    return new_h


def check_rest_penalty(total_rest_minutes: float) -> float:
    """
    Check if total_rest now exceeds the previously penalized watermark.
    If so, charge the excess to H. Returns new H (unchanged if no excess).
    """
    penalized_up_to = read_penalized_rest()
    excess = total_rest_minutes - penalized_up_to
    if excess <= 0:
        return read_h()
    # Update watermark first, then accumulate
    write_penalized_rest(total_rest_minutes)
    return accumulate_h(excess)


if __name__ == "__main__":
    # Quick status dump
    h = read_h()
    p = read_penalized_rest()
    m = read_max_rest()
    print(f"H = {h:.1f} 分钟")
    print(f"已计入休息惩罚截止：{p:.1f} 分钟  |  max_rest = {m:.1f} 分钟")
    h_int = int(h)
    rng = "{random:0..0}" if h_int == 0 else "{random:1.." + str(h_int * 2) + "}"
    print(f"-overtime-penalty-range = {rng}")
