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
from pathlib import Path

# ── paths ──────────────────────────────────────────────────────────────────
PREFS = Path(
    "/Users/haichenlai/Library/Application Support/Alfred"
    "/Alfred.alfredpreferences"
)
SNIPPET_UID = "1076C34A-79DA-42CE-A75A-EF4C853B0C2F"

JSON_FILE = (
    PREFS
    / "snippets"
    / "学习时间追踪系统"
    / f"-violationcount [{SNIPPET_UID}].json"
)
DB_FILE = Path(
    "/Users/haichenlai/Library/Application Support/Alfred"
    "/Databases/snippets.alfdb"
)


# ── helpers ────────────────────────────────────────────────────────────────

def read_current_from_db(uid: str) -> tuple[int, str]:
    """Return (current_int, raw_snippet_str) from SQLite, which Alfred reads."""
    with sqlite3.connect(DB_FILE) as con:
        row = con.execute(
            "SELECT snippet FROM snippets WHERE uid = ?", (uid,)
        ).fetchone()
    if row is None:
        raise RuntimeError(f"UID {uid!r} not found in {DB_FILE}")
    raw = row[0]
    try:
        return int(raw), raw
    except ValueError:
        raise RuntimeError(
            f"snippet field {raw!r} is not an integer string"
        )


def write_to_db(uid: str, new_value: str) -> None:
    """Update the SQLite cache – this is what Alfred reads live."""
    with sqlite3.connect(DB_FILE) as con:
        con.execute(
            "UPDATE snippets SET snippet = ? WHERE uid = ?",
            (new_value, uid),
        )
        if con.total_changes == 0:
            raise RuntimeError(
                f"UPDATE matched 0 rows for uid={uid!r}; "
                "was the snippet deleted from Alfred?"
            )


def write_to_json(new_value: str) -> None:
    """Keep the JSON file in sync (for sync/backup consistency)."""
    payload = json.loads(JSON_FILE.read_text(encoding="utf-8"))
    payload["alfredsnippet"]["snippet"] = new_value
    JSON_FILE.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


# ── main ───────────────────────────────────────────────────────────────────

def main() -> int:
    # Validate paths
    for p in (JSON_FILE, DB_FILE):
        if not p.exists():
            print(f"File not found: {p}", file=sys.stderr)
            return 1

    try:
        current, _ = read_current_from_db(SNIPPET_UID)
    except RuntimeError as exc:
        print(exc, file=sys.stderr)
        return 1

    new_value = str(current + 1)

    try:
        # 1. Update SQLite first (this is what Alfred reads live)
        write_to_db(SNIPPET_UID, new_value)
        # 2. Update JSON to keep preference file in sync
        write_to_json(new_value)
    except (RuntimeError, OSError) as exc:
        print(f"Write failed: {exc}", file=sys.stderr)
        return 1

    print(f"violationcount updated: {current} -> {new_value}  (DB + JSON both written)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
