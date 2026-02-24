#!/usr/bin/env python3
"""=pause handler — record the start of a rest period."""
from __future__ import annotations

import sys
from datetime import datetime, timezone

sys.path.insert(0, "/Users/haichenlai/Desktop/Prompt")
from config import PAUSE_TS_FILE  # noqa: E402


def main() -> int:
    now = datetime.now(tz=timezone.utc)
    PAUSE_TS_FILE.write_text(now.isoformat(), encoding="utf-8")
    print(f"休息开始记录：{now.isoformat()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
