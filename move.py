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
"""
from __future__ import annotations

import json
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, "/Users/haichenlai/Desktop/Prompt")
import update_h  # noqa: E402

# ── file paths ──────────────────────────────────────────────────────────────
BASE = Path("/Users/haichenlai/Desktop/Prompt")
PREV_TS_FILE = BASE / "prev_timestamp.txt"
CURR_TS_FILE = BASE / "curr_timestamp.txt"
PAUSE_TS_FILE = BASE / "pause_timestamp.txt"
CONT_TS_FILE = BASE / "continue_timestamp.txt"

# ── Alfred snippet config ───────────────────────────────────────────────────
PREFS = Path(
    "/Users/haichenlai/Library/Application Support/Alfred"
    "/Alfred.alfredpreferences"
)
DB_FILE = Path(
    "/Users/haichenlai/Library/Application Support/Alfred"
    "/Databases/snippets.alfdb"
)
SNIPPETS_DIR = PREFS / "snippets" / "学习时间追踪系统"

INTERVAL_UID = "0352B20F-33EE-44A0-B570-FAAF2FA1E8E8"
FORTUNE_UID  = "8BD89037-57B3-4964-A204-3D2D1F1250FA"

INTERVAL_JSON = SNIPPETS_DIR / f"-interval [{INTERVAL_UID}].json"
FORTUNE_JSON  = SNIPPETS_DIR / f"-fortunevalue [{FORTUNE_UID}].json"

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


def write_snippet_db(uid: str, value: str) -> None:
    with sqlite3.connect(DB_FILE) as con:
        con.execute("UPDATE snippets SET snippet = ? WHERE uid = ?", (value, uid))
        if con.total_changes == 0:
            raise RuntimeError(f"UID {uid!r} not found in DB")


def write_snippet_json(json_path: Path, value: str) -> None:
    payload = json.loads(json_path.read_text(encoding="utf-8"))
    payload["alfredsnippet"]["snippet"] = value
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def write_snippet(uid: str, json_path: Path, value: str) -> None:
    """Update both SQLite (live) and JSON (sync/backup)."""
    write_snippet_db(uid, value)
    write_snippet_json(json_path, value)


# ── main ────────────────────────────────────────────────────────────────────

def main() -> int:
    now = now_ts()

    # 1. Shift curr → prev, write new curr
    prev = read_ts(CURR_TS_FILE)          # old curr becomes new prev
    if prev is not None:
        write_ts(PREV_TS_FILE, prev)
    write_ts(CURR_TS_FILE, now)

    if prev is None:
        # First =move ever — no interval to compute yet
        print("First =move recorded. No interval computed yet.")
        return 0

    # 2. Compute raw interval
    raw_minutes = (now - prev).total_seconds() / 60

    # 3. Check whether a pause/continue pair falls inside (prev, now)
    pause_ts = read_ts(PAUSE_TS_FILE)
    cont_ts  = read_ts(CONT_TS_FILE)

    rest_minutes = 0.0
    if pause_ts is not None and cont_ts is not None and pause_ts > prev:
        # Rest happened within this learning interval — subtract it
        rest_minutes = (cont_ts - pause_ts).total_seconds() / 60
        rest_minutes = max(rest_minutes, 0.0)

    interval_minutes = raw_minutes - rest_minutes

    # 4. Determine 吉凶 (fortune value)
    fortune = "-1" if interval_minutes > 15 else "1"

    # 5. Write interval + fortune to Alfred snippets
    interval_str = f"{interval_minutes:.1f}"
    try:
        write_snippet(INTERVAL_UID, INTERVAL_JSON, interval_str)
        write_snippet(FORTUNE_UID,  FORTUNE_JSON,  fortune)
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
        f"-interval = {interval_str}，-fortunevalue = {fortune}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
