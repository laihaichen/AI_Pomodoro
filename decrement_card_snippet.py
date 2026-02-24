#!/usr/bin/env python3
"""Decrement the Alfred snippet counter for -countcard (宿命卡).

Bind to =usecard in Alfred Workflow.
Mirrors increment_card_snippet.py — updates both SQLite (live) and JSON (backup).
"""
from __future__ import annotations

import json
import sqlite3
import sys

sys.path.insert(0, "/Users/haichenlai/Desktop/Prompt")
from config import DB_FILE, SNIPPETS  # noqa: E402


# ── helpers ────────────────────────────────────────────────────────────────

def read_current_from_db() -> int:
    snip = SNIPPETS["countcard"]
    with sqlite3.connect(DB_FILE) as con:
        row = con.execute(
            "SELECT snippet FROM snippets WHERE uid = ?", (snip.uid,)
        ).fetchone()
    if row is None:
        raise RuntimeError(f"UID {snip.uid!r} not found in {DB_FILE}")
    try:
        return int(row[0])
    except ValueError:
        raise RuntimeError(f"snippet field {row[0]!r} is not an integer string")


def write_to_db(new_value: str) -> None:
    snip = SNIPPETS["countcard"]
    with sqlite3.connect(DB_FILE) as con:
        con.execute(
            "UPDATE snippets SET snippet = ? WHERE uid = ?",
            (new_value, snip.uid),
        )
        if con.total_changes == 0:
            raise RuntimeError(f"UPDATE matched 0 rows for uid={snip.uid!r}")


def write_to_json(new_value: str) -> None:
    json_path = SNIPPETS["countcard"].json_path
    payload = json.loads(json_path.read_text(encoding="utf-8"))
    payload["alfredsnippet"]["snippet"] = new_value
    json_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


# ── main ───────────────────────────────────────────────────────────────────

def main() -> int:
    snip = SNIPPETS["countcard"]
    for p in (snip.json_path, DB_FILE):
        if not p.exists():
            print(f"File not found: {p}", file=sys.stderr)
            return 1

    try:
        current = read_current_from_db()
    except RuntimeError as exc:
        print(exc, file=sys.stderr)
        return 1

    new_value = str(current - 1)

    try:
        write_to_db(new_value)
        write_to_json(new_value)
    except (RuntimeError, OSError) as exc:
        print(f"Write failed: {exc}", file=sys.stderr)
        return 1

    print(f"countcard updated: {current} -> {new_value}  (DB + JSON both written)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
