#!/usr/bin/env python3
"""=pause handler — record the start of a rest period."""
from __future__ import annotations

import json
import sqlite3
import sys
from datetime import datetime, timezone

sys.path.insert(0, "/Users/haichenlai/Desktop/Prompt")
from config import DB_FILE, PAUSE_TS_FILE, SNIPPETS  # noqa: E402


def write_snippet(key: str, value: str) -> None:
    """Update both SQLite and JSON for the given snippet key."""
    snip = SNIPPETS[key]
    with sqlite3.connect(DB_FILE) as con:
        con.execute("UPDATE snippets SET snippet = ? WHERE uid = ?", (value, snip.uid))
    if snip.json_path.exists():
        payload = json.loads(snip.json_path.read_text(encoding="utf-8"))
        payload["alfredsnippet"]["snippet"] = value
        snip.json_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )


def main() -> int:
    now = datetime.now(tz=timezone.utc)
    PAUSE_TS_FILE.write_text(now.isoformat(), encoding="utf-8")

    # 同步写入 -time-pause snippet（本地时间，人类可读格式）
    time_str = now.astimezone().strftime("%Y-%m-%d %H:%M:%S")
    try:
        write_snippet("time_pause", time_str)
    except (RuntimeError, OSError) as exc:
        print(f"time_pause write failed: {exc}", file=sys.stderr)

    print(f"休息开始记录：{time_str}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
