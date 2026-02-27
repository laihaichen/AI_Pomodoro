#!/usr/bin/env python3
"""=move handler.

On each call:
  1. Move curr_timestamp → prev_timestamp
  2. Write current time → curr_timestamp
  3. If there is a prev timestamp, compute the interval:
       - Check whether a pause/continue pair falls inside [prev, curr].
         (If pause_time <= prev_time the rest happened BEFORE this interval
          and is safely ignored — no reset needed.)
       - interval = (curr − prev) − (continue − pause)  [if rest inside]
       - interval = (curr − prev)                        [otherwise]
  4. Write interval minutes to Alfred snippet  -interval  (DB + JSON)
  5. Write +1 or -1 to Alfred snippet  -fortunevalue     (DB + JSON)
     rule: interval > 15 min  →  -1 (凶),  else  +1 (吉)
  6. Generate a fresh 1-100 random number and write to -random-num (DB + JSON)
     每条番茄钟绑定一个唯一随机数；用户多次展开 -go 不会刷新，
     只有下次推进番茄钟才刷新。
"""
from __future__ import annotations

import json
import random
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, "/Users/haichenlai/Desktop/Prompt")
from config import (  # noqa: E402
    CONT_TS_FILE, CURR_TS_FILE, DB_FILE, FIRST_TS_FILE,
    PAUSE_TS_FILE, PREV_TS_FILE, SNIPPETS,
)
import update_h  # noqa: E402


# ── helpers ─────────────────────────────────────────────────────────────────

def now_ts() -> datetime:
    return datetime.now(tz=timezone.utc)


def read_ts(path: Path) -> datetime | None:
    """Read an ISO-8601 timestamp from a file; return None if missing/empty."""
    if not path.exists():
        return None
    text = path.read_text(encoding="utf-8").strip()
    if not text:
        return None
    return datetime.fromisoformat(text)


def write_ts(path: Path, dt: datetime) -> None:
    path.write_text(dt.isoformat(), encoding="utf-8")


def write_snippet(key: str, value: str) -> None:
    """Update both SQLite (live) and JSON (sync/backup) for the given snippet key."""
    snip = SNIPPETS[key]
    with sqlite3.connect(DB_FILE) as con:
        con.execute("UPDATE snippets SET snippet = ? WHERE uid = ?", (value, snip.uid))
        if con.total_changes == 0:
            raise RuntimeError(f"UID {snip.uid!r} not found in DB")
    payload = json.loads(snip.json_path.read_text(encoding="utf-8"))
    payload["alfredsnippet"]["snippet"] = value
    snip.json_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


# ── main ────────────────────────────────────────────────────────────────────

def main() -> int:
    now = now_ts()

    # 1. Shift curr → prev, write new curr
    prev = read_ts(CURR_TS_FILE)
    if prev is not None:
        write_ts(PREV_TS_FILE, prev)
    write_ts(CURR_TS_FILE, now)

    if prev is None:
        write_ts(FIRST_TS_FILE, now)
        # 第1条记录：写入当前时间 + 生成随机数
        rand_num = random.randint(1, 100)
        try:
            write_snippet("current_time", now.astimezone().strftime("%Y-%m-%d %H:%M:%S"))
            write_snippet("random_num",   str(rand_num))
        except (RuntimeError, OSError) as exc:
            print(f"current_time/random_num write failed: {exc}", file=sys.stderr)
        print(f"First =move recorded. No interval computed yet.  -random-num = {rand_num}")
        return 0


    # 2. Compute raw interval
    raw_minutes = (now - prev).total_seconds() / 60

    # 3. Check whether a pause/continue pair falls inside (prev, now)
    pause_ts = read_ts(PAUSE_TS_FILE)
    cont_ts  = read_ts(CONT_TS_FILE)

    rest_minutes = 0.0
    if pause_ts is not None and cont_ts is not None and pause_ts > prev:
        rest_minutes = (cont_ts - pause_ts).total_seconds() / 60
        rest_minutes = max(rest_minutes, 0.0)

    interval_minutes = raw_minutes - rest_minutes

    # 4. Determine 吉凶 (fortune value)
    fortune_snippet = (
        "超出15分钟，不合规，应判断为凶(-1)"
        if interval_minutes > 15
        else "未到15分钟，合规"
    )
    fortune = "-1" if interval_minutes > 15 else "1"

    # 5. Write interval + fortune + current-time to Alfred snippets
    interval_str = f"{interval_minutes:.1f}"
    current_time_str = now.astimezone().strftime("%Y-%m-%d %H:%M:%S")
    rand_num = random.randint(1, 100)   # 每条番茄钟生成一个新随机数
    try:
        write_snippet("interval",     interval_str)
        write_snippet("fortunevalue", fortune_snippet)
        write_snippet("current_time", current_time_str)
        write_snippet("random_num",   str(rand_num))
    except (RuntimeError, OSError) as exc:
        print(f"Write failed: {exc}", file=sys.stderr)
        return 1

    # 6. H penalty: interval > 20 min charges the excess
    h_info = ""
    if interval_minutes > 20:
        delta = interval_minutes - 20
        new_h = update_h.accumulate_h(delta)
        h_info = f"  |  H += {delta:.1f} → H = {new_h:.1f}，range 已更新"

    # 7. Report
    rest_info = f" (休息扣除 {rest_minutes:.1f} 分钟)" if rest_minutes > 0 else ""
    verdict   = "凶 (-1)" if fortune == "-1" else "吉 (+1)"
    print(
        f"区间时间差：{interval_minutes:.1f} 分钟{rest_info}  →  {verdict}{h_info}\n"
        f"-interval = {interval_str}，-fortunevalue = {fortune}，-random-num = {rand_num}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
