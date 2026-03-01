#!/usr/bin/env python3
"""=move handler（整合自 increase_current_prompt_count.py）。

On each call:
  1. Move curr_timestamp → prev_timestamp
  2. Write current time → curr_timestamp
  3. Compute interval, 吉凶, 命运值, write all Alfred snippets
  4. Increment -current_prompt_count
  5. Check milestone state machine (every 18 prompts)
  6. Compute and write time offset (-offset)
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
    read_snippet, write_snippet, update_total_score,
)
import update_h     # noqa: E402
import update_stage # noqa: E402


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


# write_snippet / read_snippet / update_total_score — imported from config



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
    val = read_snippet("overtime_penalty_random_num").strip()
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


# ── count / offset helpers (merged from increase_current_prompt_count.py) ──

def _read_count() -> int:
    """Read -current_prompt_count from Alfred DB."""
    val = read_snippet("current_prompt_count")
    if not val:
        raise RuntimeError("current_prompt_count not found in DB")
    try:
        return int(val)
    except ValueError:
        raise RuntimeError(f"snippet value {val!r} is not an integer")


def _compute_and_write_offset(new_count: int) -> str:
    """
    offset = 期望总时间 - 真实总时间
           = ((new_count - 1) × 10 + total_rest) - (curr_ts - first_ts)
    Returns a short status string.
    """
    try:
        first_raw = FIRST_TS_FILE.read_text(encoding="utf-8").strip() if FIRST_TS_FILE.exists() else ""
        curr_raw  = CURR_TS_FILE.read_text(encoding="utf-8").strip()  if CURR_TS_FILE.exists()  else ""
        if not first_raw or not curr_raw:
            return "(offset 误差：时间戳文件缺失)"
        real_total   = (datetime.fromisoformat(curr_raw) - datetime.fromisoformat(first_raw)).total_seconds() / 60
        total_rest   = float(read_snippet("total_rest_time") or "0")
        expect_total = (new_count - 1) * 10 + total_rest
        offset       = expect_total - real_total
        write_snippet("offset", f"{offset:.1f}")
        if offset > 60:
            try:
                write_snippet("is_victory", "已失败，失败来源：时间偏移量超限")
                print(f"⚠️  offset={offset:.1f} > 60，游戏失败：is_victory → 已失败")
                _cur = int(read_snippet("total_score") or "0")
                _new = round(_cur * 0.9)
                write_snippet("total_score", str(_new))
                print(f"  总积分 ×0.9 → {_new}")
            except Exception as exc:
                print(f"offset 惩罚写入失败: {exc}", file=sys.stderr)
        return f"-offset = {offset:.1f} 分钟（期望 {expect_total:.1f} - 真实 {real_total:.1f}）"
    except Exception as exc:
        return f"(offset 计算异常: {exc})"


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
        # 幸运系统：final_fate >= 85 时写入触发提示，否则还原默认值
        try:
            _LUCKY_MSG = (
                "最终命运值>=85，幸运系统已触发\n\n"
                "##### 幸运操作列表\n\n"
                "- [神圣干预：玩家为角色X+1岁的事件预判栏目选择一个命运值区间"
                "（高度正面85~100、中等正面50~84、轻度正面1~49、"
                "轻度负面-1~-30、中等负面-31~-60、严重负面-61~-89），"
                "并为该区间填写一个自定义的事件描述；该描述将替换AI原本生成的该区间事件内容；"
                "实际触发仍需命运值落在玩家选择的区间；"
                "⚠️ 约束：不能在负面事件里写正面情节，或在正面事件里写负面情节]\n"
                "- [宿命卡count + 1：玩家获得1张宿命卡，可在之后任意年龄使用]"
            )
            _DEFAULT = SNIPPETS["is_eligible_for_reward"].default
            if final_fate >= 85:
                write_snippet("is_eligible_for_reward", _LUCKY_MSG)
            else:
                # 仅当当前值不是默认值时才写，避免多余写入
                _cur_val = read_snippet("is_eligible_for_reward").strip()
                if _cur_val != _DEFAULT:
                    write_snippet("is_eligible_for_reward", _DEFAULT)
        except Exception as exc:
            print(f"is_eligible_for_reward update failed: {exc}", file=sys.stderr)
        # 积分：累加命运值；失败时再 ×0.9
        try:
            new_score = update_total_score(delta=final_fate)
            if final_fate <= -90:
                new_score = update_total_score(factor=0.9)
            print(f"  总积分={new_score}")
        except Exception as exc:
            print(f"total_score update failed: {exc}", file=sys.stderr)
        write_final_fate(final_fate)
        print(
            f"First =move recorded.\n"
            f"  健康度={health}  概率判定={fortune_str}  原始随机数={rand_num}\n"
            f"  超时惩罚={overtime}  最终命运值={final_fate}"
        )
        # ── 计数 + 里程碑 + offset（首条）──────────────────────────────────
        try:
            current = _read_count()
            new_count = current + 1
            write_snippet("current_prompt_count", str(new_count))
            print(f"prompt count: {current} → {new_count}")
            # 里程碑状态机
            if not update_stage.is_milestone_difficulty():
                update_stage.set_not_applicable()
            elif new_count % 18 == 0:
                update_stage.set_milestone()
            elif new_count % 18 == 1 and new_count > 1:
                update_stage.reset_stage()
            else:
                if update_stage.read_stage() == update_stage.STAGE_NOT_APPLICABLE:
                    update_stage.reset_stage()
        except Exception as exc:
            print(f"count/milestone failed: {exc}", file=sys.stderr)
        print(_compute_and_write_offset(new_count if 'new_count' in dir() else 1))
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

    # 幸运系统：final_fate >= 85 时写入触发提示，否则还原默认值
    try:
        _LUCKY_MSG = (
            "最终命运值>=85，幸运系统已触发\n\n"
            "##### 幸运操作列表\n\n"
            "- [神圣干预：玩家为角色X+1岁的事件预判栏目选择一个命运值区间"
            "（高度正面85~100、中等正面50~84、轻度正面1~49、"
            "轻度负面-1~-30、中等负面-31~-60、严重负面-61~-89），"
            "并为该区间填写一个自定义的事件描述；该描述将替换AI原本生成的该区间事件内容；"
            "实际触发仍需命运值落在玩家选择的区间；"
            "⚠️ 约束：不能在负面事件里写正面情节，或在正面事件里写负面情节]\n"
            "- [宿命卡count + 1：玩家获得1张宿命卡，可在之后任意年龄使用]"
        )
        _DEFAULT = SNIPPETS["is_eligible_for_reward"].default
        if final_fate >= 85:
            write_snippet("is_eligible_for_reward", _LUCKY_MSG)
        else:
            _cur_val = read_snippet("is_eligible_for_reward").strip()
            if _cur_val != _DEFAULT:
                write_snippet("is_eligible_for_reward", _DEFAULT)
    except Exception as exc:
        print(f"is_eligible_for_reward update failed: {exc}", file=sys.stderr)

    # 积分：累加命运值；失败时再 ×0.9
    try:
        new_score = update_total_score(delta=final_fate)
        if final_fate <= -90:
            new_score = update_total_score(factor=0.9)
    except Exception as exc:
        print(f"total_score update failed: {exc}", file=sys.stderr)
        new_score = None

    # 9. Report
    rest_info = f" (休息扣除 {rest_minutes:.1f} 分钟)" if rest_minutes > 0 else ""
    print(
        f"区间：{interval_minutes:.1f} min{rest_info}  健康度={health}{h_info}\n"
        f"吉凶={fortune_str}（概率判定独立）  原始随机数={rand_num}\n"
        f"超时惩罚={overtime}  最终命运值={final_fate}  总积分={new_score}"
    )

    # 10. 计数 + 里程碑 + offset
    try:
        current   = _read_count()
        new_count = current + 1
        write_snippet("current_prompt_count", str(new_count))
        print(f"prompt count: {current} → {new_count}")
        # 里程碑状态机
        if not update_stage.is_milestone_difficulty():
            update_stage.set_not_applicable()
            print("ℹ️  探索者难度，阶段性节点不适用")
        elif new_count % 18 == 0:
            update_stage.set_milestone()
            print(f"🎯 阶段性节点触发：第 {new_count} 条记录")
        elif new_count % 18 == 1 and new_count > 1:
            update_stage.reset_stage()
            print(f"🔄 阶段性节点已过，-stage 重置")
        else:
            if update_stage.read_stage() == update_stage.STAGE_NOT_APPLICABLE:
                update_stage.reset_stage()
                print("ℹ️  难度已切换回 milestone 模式，-stage 已还原")
    except Exception as exc:
        print(f"count/milestone failed: {exc}", file=sys.stderr)

    print(_compute_and_write_offset(new_count if 'new_count' in locals() else 1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
