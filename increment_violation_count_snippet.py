#!/usr/bin/env python3
"""Increment the Alfred snippet counter for -violationcount.

Alfred maintains TWO sources of truth:
  1. JSON file  – the on-disk "preference" file (synced / backed up)
  2. snippets.alfdb – a SQLite cache that Alfred *actually reads* at runtime

Changing only the JSON is silently ignored because Alfred never re-reads it
while running.  This script updates *both* atomically so the live Alfred
instance and the preference file stay in sync.
"""
from __future__ import annotations

import json
import sqlite3
import sys

sys.path.insert(0, "/Users/haichenlai/Desktop/Prompt")
from config import DB_FILE, SNIPPETS  # noqa: E402


# ── helpers ────────────────────────────────────────────────────────────────

def read_current_from_db() -> tuple[int, str]:
    """Return (current_int, raw_snippet_str) from SQLite, which Alfred reads."""
    snip = SNIPPETS["violationcount"]
    with sqlite3.connect(DB_FILE) as con:
        row = con.execute(
            "SELECT snippet FROM snippets WHERE uid = ?", (snip.uid,)
        ).fetchone()
    if row is None:
        raise RuntimeError(f"UID {snip.uid!r} not found in {DB_FILE}")
    raw = row[0]
    try:
        return int(raw), raw
    except ValueError:
        raise RuntimeError(f"snippet field {raw!r} is not an integer string")


def write_to_db(new_value: str) -> None:
    """Update the SQLite cache – this is what Alfred reads live."""
    snip = SNIPPETS["violationcount"]
    with sqlite3.connect(DB_FILE) as con:
        con.execute(
            "UPDATE snippets SET snippet = ? WHERE uid = ?",
            (new_value, snip.uid),
        )
        if con.total_changes == 0:
            raise RuntimeError(
                f"UPDATE matched 0 rows for uid={snip.uid!r}; "
                "was the snippet deleted from Alfred?"
            )


def write_to_json(new_value: str) -> None:
    """Keep the JSON file in sync (for sync/backup consistency)."""
    json_path = SNIPPETS["violationcount"].json_path
    payload = json.loads(json_path.read_text(encoding="utf-8"))
    payload["alfredsnippet"]["snippet"] = new_value
    json_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


# ── main ───────────────────────────────────────────────────────────────────

def main() -> int:
    snip = SNIPPETS["violationcount"]
    for p in (snip.json_path, DB_FILE):
        if not p.exists():
            print(f"File not found: {p}", file=sys.stderr)
            return 1

    try:
        current, _ = read_current_from_db()
    except RuntimeError as exc:
        print(exc, file=sys.stderr)
        return 1

    new_value = str(current + 1)

    try:
        write_to_db(new_value)
        write_to_json(new_value)
    except (RuntimeError, OSError) as exc:
        print(f"Write failed: {exc}", file=sys.stderr)
        return 1

    print(f"violationcount updated: {current} -> {new_value}  (DB + JSON both written)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
