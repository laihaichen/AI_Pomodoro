#!/usr/bin/env python3
"""update_h.py — shared module for accumulating H and writing -overtime-penalty-range.

H (超时惩罚数字) accumulates from two sources:
  1. move.py   : interval > 20 min  →  H += (interval - 20)
  2. continue.py: total_rest > max_rest  →  H += (total_rest - penalized_rest_up_to)

-overtime-penalty-range format:
  H == 0  →  "{random:0..0}"   (no penalty, Alfred expands to 0)
  H >  0  →  "{random:1..2H}"  e.g. H=11 → "{random:1..22}"

State files (in data/):
  h_value.txt               : current H (float, minutes), default 0
  penalized_rest_up_to.txt  : total_rest already penalized (float, minutes),
                              initialised to max_rest_time on reset
"""
from __future__ import annotations

import json
import sqlite3
import sys

sys.path.insert(0, "/Users/haichenlai/Desktop/Prompt")
from config import DB_FILE, H_FILE, PENALIZED_REST_FILE, SNIPPETS  # noqa: E402


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
        return read_max_rest()
    text = PENALIZED_REST_FILE.read_text(encoding="utf-8").strip()
    try:
        return float(text) if text else read_max_rest()
    except ValueError:
        return read_max_rest()


def write_penalized_rest(value: float) -> None:
    PENALIZED_REST_FILE.write_text(f"{value:.2f}", encoding="utf-8")


def read_max_rest() -> float:
    """Read -max_rest_time snippet from SQLite."""
    snip = SNIPPETS["max_rest_time"]
    with sqlite3.connect(DB_FILE) as con:
        row = con.execute(
            "SELECT snippet FROM snippets WHERE uid = ?", (snip.uid,)
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
    h_int = int(h)
    if h_int <= 0:
        range_str = "{random:0..0}"
    else:
        range_str = "{random:1.." + str(h_int * 2) + "}"

    snip = SNIPPETS["overtime_penalty_range"]

    with sqlite3.connect(DB_FILE) as con:
        con.execute(
            "UPDATE snippets SET snippet = ? WHERE uid = ?",
            (range_str, snip.uid),
        )

    if snip.json_path.exists():
        payload = json.loads(snip.json_path.read_text(encoding="utf-8"))
        payload["alfredsnippet"]["snippet"] = range_str
        snip.json_path.write_text(
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
    write_penalized_rest(total_rest_minutes)
    return accumulate_h(excess)


if __name__ == "__main__":
    h = read_h()
    p = read_penalized_rest()
    m = read_max_rest()
    print(f"H = {h:.1f} 分钟")
    print(f"已计入休息惩罚截止：{p:.1f} 分钟  |  max_rest = {m:.1f} 分钟")
    h_int = int(h)
    rng = "{random:0..0}" if h_int == 0 else "{random:1.." + str(h_int * 2) + "}"
    print(f"-overtime-penalty-range = {rng}")
