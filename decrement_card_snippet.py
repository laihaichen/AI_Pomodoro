#!/usr/bin/env python3
"""Decrement the Alfred snippet counter for -countcard (宿命卡).

Bind to =usecard in Alfred Workflow.
Mirrors increment_card_snippet.py — updates both SQLite (live) and JSON (backup).
"""
from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path

# ── paths ──────────────────────────────────────────────────────────────────
PREFS = Path(
    "/Users/haichenlai/Library/Application Support/Alfred"
    "/Alfred.alfredpreferences"
)
SNIPPET_UID = "247CAEF6-57F5-4BCC-8D87-3E87CDDA1D0E"

JSON_FILE = (
    PREFS
    / "snippets"
    / "学习时间追踪系统"
    / f"-countcard [{SNIPPET_UID}].json"
)
DB_FILE = Path(
    "/Users/haichenlai/Library/Application Support/Alfred"
    "/Databases/snippets.alfdb"
)


# ── helpers ────────────────────────────────────────────────────────────────

def read_current_from_db(uid: str) -> int:
    with sqlite3.connect(DB_FILE) as con:
        row = con.execute(
            "SELECT snippet FROM snippets WHERE uid = ?", (uid,)
        ).fetchone()
    if row is None:
        raise RuntimeError(f"UID {uid!r} not found in {DB_FILE}")
    try:
        return int(row[0])
    except ValueError:
        raise RuntimeError(f"snippet field {row[0]!r} is not an integer string")


def write_to_db(uid: str, new_value: str) -> None:
    with sqlite3.connect(DB_FILE) as con:
        con.execute(
            "UPDATE snippets SET snippet = ? WHERE uid = ?",
            (new_value, uid),
        )
        if con.total_changes == 0:
            raise RuntimeError(f"UPDATE matched 0 rows for uid={uid!r}")


def write_to_json(new_value: str) -> None:
    payload = json.loads(JSON_FILE.read_text(encoding="utf-8"))
    payload["alfredsnippet"]["snippet"] = new_value
    JSON_FILE.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


# ── main ───────────────────────────────────────────────────────────────────

def main() -> int:
    for p in (JSON_FILE, DB_FILE):
        if not p.exists():
            print(f"File not found: {p}", file=sys.stderr)
            return 1

    try:
        current = read_current_from_db(SNIPPET_UID)
    except RuntimeError as exc:
        print(exc, file=sys.stderr)
        return 1

    new_value = str(current - 1)

    try:
        write_to_db(SNIPPET_UID, new_value)
        write_to_json(new_value)
    except (RuntimeError, OSError) as exc:
        print(f"Write failed: {exc}", file=sys.stderr)
        return 1

    print(f"countcard updated: {current} -> {new_value}  (DB + JSON both written)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
