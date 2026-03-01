#!/usr/bin/env python3
"""increase_current_prompt_count.py — increment -current_prompt_count snippet.

Side effects on milestone transitions:
  count % 18 == 0          →  call update_stage.set_milestone()
  count % 18 == 1 and > 1  →  call update_stage.reset_stage()

Bind this script to the =move Alfred workflow so it runs automatically
every time a new prompt record is created.
"""
from __future__ import annotations

import sys
from datetime import datetime

sys.path.insert(0, "/Users/haichenlai/Desktop/Prompt")
from config import CURR_TS_FILE, FIRST_TS_FILE, SNIPPETS, read_snippet, write_snippet  # noqa: E402
import update_stage  # noqa: E402


# ── helpers ─────────────────────────────────────────────────────────────────

# read_snippet / write_snippet — imported from config

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
    total_rest   = float(read_snippet("total_rest_time") or "0")
    expect_total = (new_count - 1) * 10 + total_rest   # 第1条时 expect=0
    offset       = expect_total - real_total

    write_snippet("offset", f"{offset:.1f}")

    # 偏移量超过 +60 分钟 → 游戏直接判负
    if offset > 60:
        try:
            write_snippet("is_victory", "已失败，失败来源：时间偏移量超限")
            print(f"⚠️  offset={offset:.1f} > 60，游戏失败：is_victory → 已失败")
        except Exception as exc:
            print(f"is_victory 写入失败: {exc}", file=sys.stderr)
        # 积分 ×0.9
        try:
            _cur = int(read_snippet("total_score") or "0")
            _new = round(_cur * 0.9)
            write_snippet("total_score", str(_new))
            print(f"  总积分 ×0.9 → {_new}")
        except Exception as exc:
            print(f"total_score ×0.9 失败: {exc}", file=sys.stderr)

    return f"-offset = {offset:.1f} 分钟（期望 {expect_total:.1f} - 真实 {real_total:.1f}）"



def read_count() -> int:
    """Read current -current_prompt_count from Alfred SQLite DB."""
    val = read_snippet("current_prompt_count")
    if not val:
        raise RuntimeError("current_prompt_count not found in DB")
    try:
        return int(val)
    except ValueError:
        raise RuntimeError(f"snippet value {val!r} is not an integer")


def write_count(value: int) -> None:
    """Update SQLite + JSON for -current_prompt_count."""
    write_snippet("current_prompt_count", str(value))


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
