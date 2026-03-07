#!/usr/bin/env python3
"""=continue handler — record the end of a rest period and update -total_rest_time."""
from __future__ import annotations

import json
import sqlite3
import sys
from datetime import datetime, timezone

sys.path.insert(0, "/Users/haichenlai/Desktop/Prompt")
from config import CONT_TS_FILE, PAUSE_TS_FILE, SNIPPETS, read_snippet, write_snippet  # noqa: E402
import update_h  # noqa: E402


# ── helpers ─────────────────────────────────────────────────────────────────

def read_total_rest() -> float:
    """Read current -total_rest_time."""
    try:
        return float(read_snippet("total_rest_time") or "0")
    except ValueError:
        return 0.0


def write_total_rest(value: float) -> None:
    """Write updated -total_rest_time."""
    write_snippet("total_rest_time", f"{value:.1f}")


# ── main ────────────────────────────────────────────────────────────────────

def main() -> int:
    now = datetime.now(tz=timezone.utc)

    # 1. Write continue timestamp (used by move.py for interval deduction)
    CONT_TS_FILE.write_text(now.isoformat(), encoding="utf-8")

    # 同步写入 -time-cont snippet（本地时间，人类可读格式）
    time_str = now.astimezone().strftime("%Y-%m-%d %H:%M:%S")
    try:
        write_snippet("time_cont", time_str)
    except (RuntimeError, OSError) as exc:
        print(f"time_cont write failed: {exc}", file=sys.stderr)

    # 2. Calculate this rest's duration
    if not PAUSE_TS_FILE.exists():
        print(f"休息结束记录：{time_str}（未找到对应的 pause 记录）")
        return 0

    pause_text = PAUSE_TS_FILE.read_text(encoding="utf-8").strip()
    if not pause_text:
        print("休息结束：pause_timestamp.txt 为空，无法计算时长")
        return 0

    pause_ts = datetime.fromisoformat(pause_text)
    rest_min = (now - pause_ts).total_seconds() / 60

    # 3. Accumulate into -total_rest_time
    try:
        prev_total = read_total_rest()
        new_total  = prev_total + rest_min
        write_total_rest(new_total)
    except (RuntimeError, OSError) as exc:
        print(f"写入 -total_rest_time 失败：{exc}", file=sys.stderr)
        return 1

    # 4. Check rest overtime penalty
    h_info = ""
    try:
        new_h = update_h.check_rest_penalty(new_total)
        max_rest = update_h.read_max_rest()
        if new_total > max_rest:
            h_info = f"  |  休息超限！H = {new_h:.1f}，range 已更新"
    except Exception as exc:
        h_info = f"  |  H 计算失败: {exc}"

    print(
        f"休息结束：本次休息 {rest_min:.1f} 分钟  |  "
        f"今日累计休息 {new_total:.1f} 分钟{h_info}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
