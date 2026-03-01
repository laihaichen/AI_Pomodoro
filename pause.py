#!/usr/bin/env python3
"""=pause handler — record the start of a rest period."""
from __future__ import annotations

import sys
from datetime import datetime, timezone

sys.path.insert(0, "/Users/haichenlai/Desktop/Prompt")
from config import PAUSE_TS_FILE, write_snippet  # noqa: E402


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
