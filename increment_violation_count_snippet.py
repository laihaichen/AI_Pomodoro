#!/usr/bin/env python3
"""Increment the Alfred snippet counter for -violationcount.

Uses the centralized read_snippet / write_snippet from config.py.
"""
from __future__ import annotations

import sys

sys.path.insert(0, "/Users/haichenlai/Desktop/Prompt")
from config import read_snippet, write_snippet  # noqa: E402


def main() -> int:
    try:
        current = int(read_snippet("violationcount") or "0")
    except (ValueError, RuntimeError) as exc:
        print(f"Read failed: {exc}", file=sys.stderr)
        return 1

    new_value = str(current + 1)

    try:
        write_snippet("violationcount", new_value)
    except (RuntimeError, OSError) as exc:
        print(f"Write failed: {exc}", file=sys.stderr)
        return 1

    print(f"violationcount updated: {current} -> {new_value}  (DB + JSON both written)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
