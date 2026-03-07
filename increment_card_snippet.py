#!/usr/bin/env python3
"""Increment the Alfred snippet counter for -countcard (宿命卡).

Alfred maintains TWO sources of truth:
  1. JSON file  – the on-disk "preference" file (synced / backed up)
  2. snippets.alfdb – a SQLite cache that Alfred *actually reads* at runtime

This script uses the centralized read_snippet / write_snippet from config.py
to update *both* atomically so the live Alfred instance and the preference
file stay in sync.
"""
from __future__ import annotations

import sys

sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parent))
from config import read_snippet, write_snippet  # noqa: E402


def main() -> int:
    try:
        current = int(read_snippet("countcard") or "0")
    except (ValueError, RuntimeError) as exc:
        print(f"Read failed: {exc}", file=sys.stderr)
        return 1

    new_value = str(current + 1)

    try:
        write_snippet("countcard", new_value)
    except (RuntimeError, OSError) as exc:
        print(f"Write failed: {exc}", file=sys.stderr)
        return 1

    print(f"snippet updated: {current} -> {new_value}  (DB + JSON both written)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
