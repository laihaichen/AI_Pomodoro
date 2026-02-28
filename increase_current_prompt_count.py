#!/usr/bin/env python3
"""increase_current_prompt_count.py — increment -current_prompt_count snippet.

Side effects on milestone transitions:
  count % 18 == 0          →  call update_stage.set_milestone()
  count % 18 == 1 and > 1  →  call update_stage.reset_stage()

Bind this script to the =move Alfred workflow so it runs automatically
every time a new prompt record is created.
"""
from __future__ import annotations

import json
import sqlite3
import sys
from datetime import datetime

sys.path.insert(0, "/Users/haichenlai/Desktop/Prompt")
from config import CURR_TS_FILE, DB_FILE, FIRST_TS_FILE, SNIPPETS  # noqa: E402
import update_stage  # noqa: E402


# ── helpers ─────────────────────────────────────────────────────────────────

def read_snippet_float(key: str) -> float:
    """Read a float value from Alfred SQLite by snippet key. Returns 0.0 on failure."""
    snip = SNIPPETS[key]
    with sqlite3.connect(DB_FILE) as con:
        row = con.execute(
            "SELECT snippet FROM snippets WHERE uid = ?", (snip.uid,)
        ).fetchone()
    if row is None:
        return 0.0
    try:
        return float(row[0])
    except ValueError:
        return 0.0


def write_offset(value: float) -> None:
    """Write offset minutes to -offset snippet (DB + JSON)."""
    str_value = f"{value:.1f}"
    snip = SNIPPETS["offset"]
    with sqlite3.connect(DB_FILE) as con:
        con.execute(
            "UPDATE snippets SET snippet = ? WHERE uid = ?",
            (str_value, snip.uid),
        )
    if snip.json_path.exists():
        payload = json.loads(snip.json_path.read_text(encoding="utf-8"))
        payload["alfredsnippet"]["snippet"] = str_value
        snip.json_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

def write_snippet(key: str, value: str) -> None:
    """Write a single snippet value to Alfred SQLite DB + JSON file."""
    snip = SNIPPETS[key]
    with sqlite3.connect(DB_FILE) as con:
        con.execute(
            "UPDATE snippets SET snippet = ? WHERE uid = ?",
            (value, snip.uid),
        )
    if snip.json_path.exists():
        payload = json.loads(snip.json_path.read_text(encoding="utf-8"))
        payload["alfredsnippet"]["snippet"] = value
        snip.json_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

def compute_and_write_offset(new_count: int) -> str:
    """
    offset = 期望总时间 - 真实总时间
           = ((new_count - 1) × 10 + total_rest) - (curr_ts - first_ts)

    说明：发送第 1 条记录时尚无区间时长，期望时间 = 0；
          发送第 N 条记录时已产生 N-1 个完整 10 分钟区间。
    Returns a short status string for printing.
    """
    def read_ts(path):
        if not path.exists():
            return None
        text = path.read_text(encoding="utf-8").strip()
        return datetime.fromisoformat(text) if text else None

    first_ts = read_ts(FIRST_TS_FILE)
    curr_ts  = read_ts(CURR_TS_FILE)
    if first_ts is None or curr_ts is None:
        return "(offset 误差：时间戳文件缺失)"

    real_total   = (curr_ts - first_ts).total_seconds() / 60
    total_rest   = read_snippet_float("total_rest_time")
    expect_total = (new_count - 1) * 10 + total_rest   # 第1条时 expect=0
    offset       = expect_total - real_total

    write_offset(offset)

    # 偏移量超过 +60 分钟 → 游戏直接判负
    if offset > 60:
        try:
            write_snippet("is_victory", "已失败，失败来源：时间偏移量超限")
            print(f"⚠️  offset={offset:.1f} > 60，游戏失败：is_victory → 已失败")
        except Exception as exc:
            print(f"is_victory 写入失败: {exc}", file=sys.stderr)
        # 积分 ×0.8
        try:
            snip = SNIPPETS["total_score"]
            with sqlite3.connect(DB_FILE) as _con:
                _row = _con.execute("SELECT snippet FROM snippets WHERE uid = ?", (snip.uid,)).fetchone()
            _cur = int(_row[0]) if _row else 0
            _new = round(_cur * 0.8)
            write_snippet("total_score", str(_new))
            print(f"  总积分 ×0.8 → {_new}")
        except Exception as exc:
            print(f"total_score ×0.8 失败: {exc}", file=sys.stderr)

    return f"-offset = {offset:.1f} 分钟（期望 {expect_total:.1f} - 真实 {real_total:.1f}）"



def read_count() -> int:
    """Read current -current_prompt_count from Alfred SQLite DB."""
    snip = SNIPPETS["current_prompt_count"]
    with sqlite3.connect(DB_FILE) as con:
        row = con.execute(
            "SELECT snippet FROM snippets WHERE uid = ?", (snip.uid,)
        ).fetchone()
    if row is None:
        raise RuntimeError(f"UID {snip.uid!r} not found in DB")
    try:
        return int(row[0])
    except ValueError:
        raise RuntimeError(f"snippet value {row[0]!r} is not an integer")


def write_count(value: int) -> None:
    """Update SQLite + JSON for -current_prompt_count."""
    str_value = str(value)
    snip = SNIPPETS["current_prompt_count"]

    with sqlite3.connect(DB_FILE) as con:
        con.execute(
            "UPDATE snippets SET snippet = ? WHERE uid = ?",
            (str_value, snip.uid),
        )

    if not snip.json_path.exists():
        raise RuntimeError("-current_prompt_count JSON file not found")
    payload = json.loads(snip.json_path.read_text(encoding="utf-8"))
    payload["alfredsnippet"]["snippet"] = str_value
    snip.json_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


# ── main ────────────────────────────────────────────────────────────────────

def main() -> int:
    try:
        current = read_count()
    except RuntimeError as exc:
        print(exc, file=sys.stderr)
        return 1

    new_count = current + 1

    try:
        write_count(new_count)
    except (RuntimeError, OSError) as exc:
        print(f"Write failed: {exc}", file=sys.stderr)
        return 1

    print(f"prompt count: {current} → {new_count}")

    # ── milestone state machine ─────────────────────────────────────────────
    try:
        if not update_stage.is_milestone_difficulty():
            update_stage.set_not_applicable()
            print(f"ℹ️  探索者难度，阶段性节点不适用（-stage → 当前难度不适用）")

        elif new_count % 18 == 0:
            update_stage.set_milestone()
            print(f"🎯 阶段性节点触发：第 {new_count} 条记录（{new_count // 18} × 18）")

        elif new_count % 18 == 1 and new_count > 1:
            update_stage.reset_stage()
            print(f"🔄 阶段性节点已过，-stage 重置（第 {new_count} 条记录）")

        else:
            # Mid-game, no milestone event — but if stage was left as
            # "not applicable" from a previous explorer-difficulty run,
            # restore it to the default so it doesn't linger.
            if update_stage.read_stage() == update_stage.STAGE_NOT_APPLICABLE:
                update_stage.reset_stage()
                print("ℹ️  难度已切换回 milestone 模式，-stage 已还原为默认值")

    except RuntimeError as exc:
        print(f"Stage update failed: {exc}", file=sys.stderr)
        return 1

    # ── offset ──────────────────────────────────────────────────────────────
    try:
        offset_info = compute_and_write_offset(new_count)
        print(offset_info)
    except Exception as exc:
        print(f"Offset 计算失败: {exc}", file=sys.stderr)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
