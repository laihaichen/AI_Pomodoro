#!/usr/bin/env python3
"""=continue handler — record the end of a rest period."""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

BASE = Path("/Users/haichenlai/Desktop/Prompt")
CONT_TS_FILE  = BASE / "continue_timestamp.txt"
PAUSE_TS_FILE = BASE / "pause_timestamp.txt"


def main() -> int:
    now = datetime.now(tz=timezone.utc)
    CONT_TS_FILE.write_text(now.isoformat(), encoding="utf-8")

    # Sanity check: report how long the rest was
    if PAUSE_TS_FILE.exists():
        pause_text = PAUSE_TS_FILE.read_text(encoding="utf-8").strip()
        if pause_text:
            pause_ts = datetime.fromisoformat(pause_text)
            rest_min = (now - pause_ts).total_seconds() / 60
            print(f"休息结束：本次休息 {rest_min:.1f} 分钟")
            return 0

    print(f"休息结束记录：{now.isoformat()}（未找到对应的 pause 记录）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
