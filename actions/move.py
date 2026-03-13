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

import random
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parent))
from config import (  # noqa: E402
    CONT_TS_FILE, CURR_TS_FILE, FINAL_FATE_FILE, FIRST_TS_FILE,
    HEALTH_FILE, PAUSE_TS_FILE, PREV_TS_FILE, SNIPPETS,
    read_snippet, write_snippet, update_total_score,
)
import update_h     # noqa: E402
import update_stage # noqa: E402
from mod.companions import load_active_companions, consume_pending_skills  # noqa: E402


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


def probability_check(health: int) -> bool:
    """以 health×10% 的概率返回 True（吉）。"""
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
    """从 Alfred DB 读取当前 -overtime-penalty-random-num，缺失时为 0。"""
    val = read_snippet("overtime_penalty_random_num").strip()
    if val.lstrip("-").isdigit():
        return int(val)
    return 0


def write_final_fate(value: int) -> None:
    FINAL_FATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    FINAL_FATE_FILE.write_text(str(value), encoding="utf-8")


def fate_category(fate: int) -> str:
    """Return a simple tier key matching event_registry keys exactly."""
    if fate <= -90:
        return "FAIL"
    elif fate <= -60:
        return "NEG_HIGH"
    elif fate <= -30:
        return "NEG_MID"
    elif fate <= -1:
        return "NEG_LOW"
    elif fate <= 49:
        return "POS_LOW"
    elif fate <= 84:
        return "POS_MID"
    else:
        return "POS_HIGH"


# ── count / offset helpers ───────────────────────────────────────────────────

def _read_count() -> int:
    val = read_snippet("current_prompt_count")
    if not val:
        raise RuntimeError("current_prompt_count not found in DB")
    try:
        return int(val)
    except ValueError:
        raise RuntimeError(f"snippet value {val!r} is not an integer")


def _compute_and_write_offset(new_count: int) -> str:
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
                from update_stage import adjust_health
                new_health = adjust_health(-1)
                print(f"⚠️  offset={offset:.1f} > 60，健康度 -1 → {new_health}")
            except Exception as exc:
                print(f"offset 健康度扣除失败: {exc}", file=sys.stderr)
        return f"-offset = {offset:.1f} 分钟（期望 {expect_total:.1f} - 真实 {real_total:.1f}）"
    except Exception as exc:
        return f"(offset 计算异常: {exc})"


# ── main ────────────────────────────────────────────────────────────────────

def main() -> int:
    # 0. 抓取当前剪切板内容，保存为"当前学习正文"
    try:
        import subprocess
        clip = subprocess.run(["pbpaste"], capture_output=True, text=True, timeout=3).stdout.strip()
        if clip:
            write_snippet("current_clipboard", clip[:8000])  # 截断防止过长
    except Exception as exc:
        print(f"clipboard capture failed: {exc}", file=sys.stderr)

    now = now_ts()

    # 1. Shift curr → prev，写新 curr
    prev = read_ts(CURR_TS_FILE)
    if prev is not None:
        write_ts(PREV_TS_FILE, prev)
    write_ts(CURR_TS_FILE, now)

    is_first = (prev is None)
    if is_first:
        write_ts(FIRST_TS_FILE, now)

    # ── 2. 区间 & H 惩罚 ─────────────────────────────────────────────────────
    rest_minutes     = 0.0
    h_info           = ""
    if is_first:
        interval_minutes = 0.0
    else:
        raw_minutes = (now - prev).total_seconds() / 60
        pause_ts = read_ts(PAUSE_TS_FILE)
        cont_ts  = read_ts(CONT_TS_FILE)
        if pause_ts is not None and cont_ts is not None and pause_ts > prev:
            rest_minutes = max((cont_ts - pause_ts).total_seconds() / 60, 0.0)
        interval_minutes = raw_minutes - rest_minutes
        if interval_minutes > 20:
            delta = interval_minutes - 20
            new_h = update_h.accumulate_h(delta)
            h_info = f"  |  H += {delta:.1f} → H = {new_h:.1f}"

    # ── 2.5 Companion on_pre_move 钩子（在健康度读取前执行，如赫默+1） ──
    try:
        pre_companions = load_active_companions()
        if pre_companions:
            pre_ctx = {}
            for companion in pre_companions:
                pre_ctx = companion.on_pre_move(pre_ctx)
    except Exception as exc:
        print(f"companion on_pre_move failed: {exc}", file=sys.stderr)

    # ── 3. 吉凶判定 ──────────────────────────────────────────────────────────
    health = read_health()

    # 每次 move 都基于当前 H 重新掷超时惩罚随机数
    current_h = update_h.read_h()
    update_h.write_overtime_range(current_h)

    if interval_minutes >= 15:
        fortune_val = -1
        fortune_str = "凶 (超时)"
    else:
        is_lucky    = probability_check(health)
        fortune_val = 1 if is_lucky else -1
        fortune_str = "吉" if is_lucky else ("凶" if is_first else "凶 (命运不佳)")

    # ── 4. 随机数 & 最终命运值 ────────────────────────────────────────────────
    rand_num   = random.randint(1, 100)
    overtime   = read_overtime_penalty()
    final_fate = rand_num * fortune_val - overtime

    # ── 4.5 Companion on_move 钩子（在 snippet 写入前，允许技能修改 final_fate）──
    try:
        companions = load_active_companions()
        if companions:
            try:
                prompt_count = int(read_snippet("current_prompt_count") or "0")
            except Exception:
                prompt_count = 0
            ctx = {
                "final_fate":           final_fate,
                "rand_num":             rand_num,
                "fortune_val":          fortune_val,
                "overtime":             overtime,
                "health":               health,
                "interval_minutes":     interval_minutes,
                "is_first":             is_first,
                "player_used_skills":   consume_pending_skills(),
                "current_prompt_count": prompt_count,
            }
            for companion in companions:
                ctx = companion.on_move(ctx)
            final_fate = ctx["final_fate"]   # 读回可能被技能修改后的值
    except Exception as exc:
        print(f"companion on_move failed: {exc}", file=sys.stderr)

    write_final_fate(final_fate)

    # ── 5. 写入所有 snippets ──────────────────────────────────────────────────
    fortune_label  = "吉" if fortune_val == 1 else "凶"
    time_limit_str = (
        "未到15分钟，合规"
        if is_first or interval_minutes < 15
        else "超出15分钟，触发严厉监督"
    )
    foretold_val = SNIPPETS["foretold"].default if is_first else fate_category(final_fate)
    try:
        if not is_first:
            _mins = int(interval_minutes)
            _secs = int((interval_minutes - _mins) * 60)
            write_snippet("interval", f"{_mins}分{_secs:02d}秒")
        write_snippet("is_time_within_limit",   time_limit_str)
        write_snippet("current_time",           now.astimezone().strftime("%Y-%m-%d %H:%M:%S"))
        write_snippet("random_num",             str(rand_num))
        write_snippet("healthy",                str(health))
        write_snippet("fortune_and_misfortune", fortune_label)
        write_snippet("final_fate_value",       str(final_fate))
        write_snippet("foretold",               foretold_val)
        if final_fate <= -90:
            write_snippet("is_victory", "已失败，失败来源：命运值")
    except (RuntimeError, OSError) as exc:
        print(f"snippet write failed: {exc}", file=sys.stderr)
        return 1

    # ── 6. 幸运系统 ──────────────────────────────────────────────────────────
    _LUCKY_MSG = "幸运系统已触发"
    try:
        _DEFAULT = SNIPPETS["is_eligible_for_reward"].default
        if final_fate >= 90:
            # 检查是否满足换分门槛：宿命卡≥5 且 干预卡≥2
            _fate_cards = int(read_snippet("countcard") or 0)
            _intv_cards = int(read_snippet("countinterventioncard") or 0)
            if _fate_cards >= 5 and _intv_cards >= 2:
                _LUCKY_MSG += "\n\n[SCORE_EXCHANGE_AVAILABLE]"
            write_snippet("is_eligible_for_reward", _LUCKY_MSG)
        else:
            if read_snippet("is_eligible_for_reward").strip() != _DEFAULT:
                write_snippet("is_eligible_for_reward", _DEFAULT)
    except Exception as exc:
        print(f"is_eligible_for_reward update failed: {exc}", file=sys.stderr)

    # ── 7. 积分 ──────────────────────────────────────────────────────────────
    new_score = None
    try:
        new_score = update_total_score(delta=final_fate)
        # 超额健康度加成：health > 10 时，每回合额外 (health-10)*10 积分
        if health > 10:
            _hp_bonus = (health - 10) * 10
            new_score = update_total_score(delta=_hp_bonus)
            print(f"💪 超额健康度加成：健康度{health} → +{_hp_bonus} 积分")
        if final_fate <= -90:
            new_score = update_total_score(factor=0.9)
    except Exception as exc:
        print(f"total_score update failed: {exc}", file=sys.stderr)

    # ── 8. 计数 + 里程碑 ─────────────────────────────────────────────────────
    new_count = 1
    try:
        current   = _read_count()
        new_count = current + 1
        write_snippet("current_prompt_count", str(new_count))
        print(f"prompt count: {current} → {new_count}")
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

    # ── 8b. Boss战节点触发 ────────────────────────────────────────────────────
    try:
        _diff_cur = read_snippet("difficulty")
        if _diff_cur == "硬核难度":
            _total = int(read_snippet("total_count") or 0)
            if _total > 0 and new_count == _total - 1:
                # 倒数第2条：触发出题
                from config import BOSSFIGHT_ACTIVE_TEXT
                write_snippet("bossfight_stage", BOSSFIGHT_ACTIVE_TEXT)
                print(f"⚔️ Boss战节点触发！第 {new_count} 条记录")
            elif _total > 0 and new_count >= _total:
                # 最后一条：玩家已交卷
                _BOSS_SUBMITTED = (
                    "⚔️ Boss战答案已提交。\n"
                    "玩家已在最后一条记录上交答案，等待AI判定结果。\n"
                    "若答案正确→游戏胜利；若答案错误→游戏失败。"
                )
                write_snippet("bossfight_stage", _BOSS_SUBMITTED)
                print(f"⚔️ Boss战答案已提交！第 {new_count} 条（最后一条）")
    except Exception as exc:
        print(f"bossfight check failed: {exc}", file=sys.stderr)

    # ── 9. Offset ────────────────────────────────────────────────────────────
    print(_compute_and_write_offset(new_count))

    # ── 10. 报告 ─────────────────────────────────────────────────────────────
    if is_first:
        print(
            f"First =move recorded.\n"
            f"  健康度={health}  概率判定={fortune_str}  原始随机数={rand_num}\n"
            f"  超时惩罚={overtime}  最终命运值={final_fate}  总积分={new_score}"
        )
    else:
        rest_info = f" (休息扣除 {rest_minutes:.1f} 分钟)" if rest_minutes > 0 else ""
        print(
            f"区间：{interval_minutes:.1f} min{rest_info}  健康度={health}{h_info}\n"
            f"吉凶={fortune_str}（概率判定独立）  原始随机数={rand_num}\n"
            f"超时惩罚={overtime}  最终命运值={final_fate}  总积分={new_score}"
        )

    # ── 11. Prompt 备份 ──────────────────────────────────────────────────────
    try:
        from workflow.engine import load_template, expand_template
        from config import backup_prompt
        backup_prompt(expand_template(load_template("go")), prompt_type="move")
    except Exception as exc:
        print(f"prompt backup failed: {exc}", file=sys.stderr)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
