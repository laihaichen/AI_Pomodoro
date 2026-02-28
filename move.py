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
    CONT_TS_FILE, CURR_TS_FILE, DB_FILE, FINAL_FATE_FILE, FIRST_TS_FILE,
    HEALTH_FILE, PAUSE_TS_FILE, PREV_TS_FILE, SNIPPETS,
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


def probability_check(health: int) -> bool:
    """
    输入健康度（0-10整数），以 health*10% 的概率返回 True（吉）。
    与 rand_num（原始随机数）完全无关，使用独立的 random.random() 抽取。
    """
    if not (0 <= health <= 10):
        health = max(0, min(health, 10))
    return random.random() < health / 10.0


def read_health() -> int:
    """从 health.txt 读取健康度，缺失时默认 9。"""
    if not HEALTH_FILE.exists():
        return 9
    text = HEALTH_FILE.read_text(encoding="utf-8").strip()
    try:
        return max(0, min(int(text), 10))
    except ValueError:
        return 9


def read_overtime_penalty() -> int:
    """从 Alfred DB 读取当前 -overtime-penalty-random-num 数值，缺失时为 0。"""
    snip = SNIPPETS["overtime_penalty_random_num"]
    with sqlite3.connect(DB_FILE) as con:
        row = con.execute(
            "SELECT snippet FROM snippets WHERE uid = ?", (snip.uid,)
        ).fetchone()
    if row:
        val = str(row[0]).strip()
        if val.lstrip("-").isdigit():
            return int(val)
    return 0


def write_final_fate(value: int) -> None:
    """将最终命运值写入 data/final_fate.txt。"""
    FINAL_FATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    FINAL_FATE_FILE.write_text(str(value), encoding="utf-8")


def fate_category(fate: int) -> str:
    """根据最终命运值返回对应的事件等级标签。

    区间与 prompt.md 7.4.3 节事件预判系统一致：
      -100 ~ -90 → FAIL     失败事件
       -89 ~ -60 → NEG_HIGH 严重负面事件
       -60 ~ -30 → NEG_MID  中等负面事件
       -30 ~  -1 → NEG_LOW  轻度负面事件
         1 ~  49 → POS_LOW  轻度正面事件
        50 ~  84 → POS_MID  中等正面事件
        85 ~ 100 → POS_HIGH 高度正面事件
    0 不在任何预设区间（理论上概率极低），返回 POS_LOW 作安全兜底。
    """
    if fate <= -90:
        return "FAIL(-100~-90) 失败事件"
    elif fate <= -60:
        return "NEG_HIGH(-89~-60) 严重负面事件"
    elif fate <= -30:
        return "NEG_MID(-60~-30) 中等负面事件"
    elif fate <= -1:
        return "NEG_LOW(-30~-1) 轻度负面事件"
    elif fate <= 49:
        return "POS_LOW(1~49) 轻度正面事件"
    elif fate <= 84:
        return "POS_MID(50~84) 中等正面事件"
    else:
        return "POS_HIGH(85~100) 高度正面事件"


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
        # 第1条记录：生成随机数 + 吉凶判定（interval=0，必然 < 15min）
        health      = read_health()
        is_lucky    = probability_check(health)      # 独立概率抽取
        fortune_val = 1 if is_lucky else -1
        fortune_str = "吉" if is_lucky else "凶"
        rand_num    = random.randint(1, 100)          # 原始随机数，独立抽取
        overtime    = read_overtime_penalty()         # 首条通常为 0
        final_fate  = rand_num * fortune_val - overtime
        try:
            write_snippet("current_time",          now.astimezone().strftime("%Y-%m-%d %H:%M:%S"))
            write_snippet("random_num",             str(rand_num))
            write_snippet("is_time_within_limit",   "未到15分钟，合规")  # 首条到00间隔，必然合规
            write_snippet("healthy",               str(health))
            write_snippet("fortune_and_misfortune", fortune_str)
            write_snippet("final_fate_value",      str(final_fate))
            write_snippet("foretold",              SNIPPETS["foretold"].default)  # 第一条无上一轮JSON
            if final_fate <= -90:
                write_snippet("is_victory", "已失败，失败来源：命运值")
        except (RuntimeError, OSError) as exc:
            print(f"snippet write failed: {exc}", file=sys.stderr)
        write_final_fate(final_fate)
        print(
            f"First =move recorded.\n"
            f"  健康度={health}  概率判定={fortune_str}  原始随机数={rand_num}\n"
            f"  超时惩罚={overtime}  最终命运值={final_fate}"
        )
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

    # 4. 吉凶判定（两步独立随机）
    health = read_health()
    if interval_minutes >= 15:
        fortune_val = -1
        fortune_str = "凶 (超时)"
    else:
        is_lucky    = probability_check(health)   # 独立概率抽取，与 rand_num 无关
        fortune_val = 1 if is_lucky else -1
        fortune_str = "吉" if is_lucky else "凶 (命运不佳)"

    # 5. 原始随机数（独立抽取，仅用于命运值公式）
    rand_num = random.randint(1, 100)

    # 6. Write all snippets to Alfred
    interval_str       = f"{interval_minutes:.1f}"
    current_time_str   = now.astimezone().strftime("%Y-%m-%d %H:%M:%S")
    fortune_label      = "吉" if fortune_val == 1 else "凶"   # 纯结果，不含原因备注
    time_limit_str     = (
        "超出15分钟，系统自动判断为凶"
        if interval_minutes >= 15
        else "未到15分钟，合规"
    )
    try:
        write_snippet("interval",               interval_str)
        write_snippet("is_time_within_limit",   time_limit_str)   # 仅反映时间是否超标
        write_snippet("current_time",           current_time_str)
        write_snippet("random_num",             str(rand_num))
        write_snippet("healthy",                str(health))
        write_snippet("fortune_and_misfortune", fortune_label)    # 纯吉/凶
    except (RuntimeError, OSError) as exc:
        print(f"Write failed: {exc}", file=sys.stderr)
        return 1

    # 7. H penalty: interval > 20 min charges the excess
    h_info = ""
    if interval_minutes > 20:
        delta = interval_minutes - 20
        new_h = update_h.accumulate_h(delta)
        h_info = f"  |  H += {delta:.1f} → H = {new_h:.1f}"

    # 8. 最终命运值 = 原始随机数 × 吉凶值 - 超时惩罚随机数
    overtime   = read_overtime_penalty()
    final_fate = rand_num * fortune_val - overtime
    write_final_fate(final_fate)
    category   = fate_category(final_fate)
    try:
        write_snippet("final_fate_value", str(final_fate))
        write_snippet("foretold",         category)
        if final_fate <= -90:
            write_snippet("is_victory", "已失败，失败来源：命运值")
    except (RuntimeError, OSError) as exc:
        print(f"final_fate_value/foretold write failed: {exc}", file=sys.stderr)


    # 9. Report
    rest_info = f" (休息扣除 {rest_minutes:.1f} 分钟)" if rest_minutes > 0 else ""
    print(
        f"区间：{interval_minutes:.1f} min{rest_info}  健康度={health}{h_info}\n"
        f"吉凶={fortune_str}（概率判定独立）  原始随机数={rand_num}\n"
        f"超时惩罚={overtime}  最终命运值={final_fate}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
