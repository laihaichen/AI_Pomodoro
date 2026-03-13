#!/usr/bin/env python3
"""dashboard.py — local web dashboard for the learning tracker.

Usage:
    python3 dashboard.py
    then open http://localhost:5050 in a browser.

Auto-refreshes every 5 seconds via AJAX polling.
"""
from __future__ import annotations

import json
import os
import sqlite3
import subprocess
import sys
import threading
from datetime import datetime, timezone
from pathlib import Path as _Path

sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parent))
from config import (  # noqa: E402
    CURR_TS_FILE, PREV_TS_FILE, FIRST_TS_FILE,
    PAUSE_TS_FILE, CONT_TS_FILE,
    PENALIZED_REST_FILE, H_FILE,
    DB_FILE, SNIPPETS, MILESTONE_GOALS_FILE,
    HEALTH_FILE, FINAL_FATE_FILE, BOSS_DEFEATED_FILE, THEME_FILE,
    BOSSFIGHT_ACTIVE_TEXT,
    BASE, DATA_ROOT, FROZEN,
    DATA_DIR,
    APP_MODE,
    JURY_STATE_FILE, JURY_QUESTION_FILE, JURY_ANSWER_FILE, JURY_SIZE,
    read_snippet, write_snippet, update_total_score, backup_prompt,
)
from workflow.browser import get_browser_driver  # noqa: E402
from workflow import (  # noqa: E402
    move_workflow, usecard_workflow,
    pause_workflow,
    continue_workflow, stay_workflow,
)

from flask import Flask, jsonify, redirect, render_template, request

app = Flask(
    __name__,
    template_folder=str(BASE / "templates"),
    static_folder=str(BASE / "static"),
)

# ── Boss战触发文本（模块级常量，供 collect_state 与 api_setup 共享）────────────
_BOSSFIGHT_ACTIVE_TEXT = BOSSFIGHT_ACTIVE_TEXT  # re-exported from config

# write_snippet / read_snippet / update_total_score — imported from config


def generate_launch_prompt(
    hours: int,
    max_rest: str,
    difficulty: str,
    milestones: list[str],
    theme: str,
) -> str:
    """Build the launch prompt string from wizard inputs."""
    today = datetime.now().strftime("%Y年%m月%d日")
    milestone_defs = [
        ("3小时",  "第18条记录"),
        ("6小时",  "第36条记录"),
        ("9小时",  "第54条记录"),
        ("12小时", "第72条记录"),
    ]
    lines = [
        f"启动一个 {today} 的番茄钟学习管理系统，期望时长是 {hours} 小时",
        "启动所有模块。",
        f"最长休息时间：{max_rest} 分钟。",
        f"难度选择：{difficulty}",
    ]
    if milestones:
        lines.append("阶段目标：")
        for i, task in enumerate(milestones):
            label, record = milestone_defs[i]
            lines.append(f"{label} ({record}) 最低完成指标：{task}")
        lines.append("全天将是 " + " + ".join(milestones))
    return "\n".join(lines)


# ── data collection ──────────────────────────────────────────────────────────

def _read_txt(path) -> str:
    try:
        return path.read_text(encoding="utf-8").strip()
    except Exception:
        return ""


def _fmt_ts(iso: str) -> str:
    """Convert ISO timestamp to human-readable local time."""
    if not iso:
        return "—"
    try:
        dt = datetime.fromisoformat(iso)
        local = dt.astimezone()
        return local.strftime("%H:%M:%S")
    except Exception:
        return iso


def collect_state() -> dict:
    state: dict = {}

    # ── txt files ────────────────────────────────────────────────────────────
    curr_raw   = _read_txt(CURR_TS_FILE)
    prev_raw   = _read_txt(PREV_TS_FILE)
    first_raw  = _read_txt(FIRST_TS_FILE)

    state["curr_ts_raw"] = curr_raw
    state["curr_ts"]  = _fmt_ts(curr_raw)
    state["prev_ts"]  = _fmt_ts(prev_raw)
    state["first_ts"] = _fmt_ts(first_raw)
    state["h_value"]  = _read_txt(H_FILE) or "0"

    # Most recent rest action: compare pause vs continue timestamps
    pause_raw = _read_txt(PAUSE_TS_FILE)
    cont_raw  = _read_txt(CONT_TS_FILE)
    if pause_raw and cont_raw:
        try:
            pause_is_newer = (
                datetime.fromisoformat(pause_raw) >= datetime.fromisoformat(cont_raw)
            )
        except Exception:
            pause_is_newer = True
    elif pause_raw:
        pause_is_newer = True
    else:
        pause_is_newer = False

    if pause_raw and pause_is_newer:
        state["last_rest_action"] = f"你在 {_fmt_ts(pause_raw)} 开始休息"
        state["last_rest_is_paused"] = True
    elif cont_raw and not pause_is_newer:
        state["last_rest_action"] = f"你在 {_fmt_ts(cont_raw)} 结束休息"
        state["last_rest_is_paused"] = False
    else:
        state["last_rest_action"] = "尚无休息记录"
        state["last_rest_is_paused"] = False

    # ── snippets（通过 read_snippet 自动分流 Alfred / standalone）─────────────
    snippet_keys = [
        "total_rest_time", "countcard", "interval", "is_time_within_limit",
        "current_prompt_count", "stage", "overtime_penalty_random_num",
        "offset", "difficulty", "max_rest_time", "violationcount",
        "hour3", "hour6", "hour9", "hour12", "bossfight_stage",
        "random_num", "foretold", "total_count", "is_victory", "total_score",
        "current_clipboard", "countinterventioncard",
        "fortune_and_misfortune", "is_eligible_for_reward",
    ]
    try:
        for key in snippet_keys:
            state[key] = read_snippet(key) or "—"
    except Exception as exc:
        for key in snippet_keys:
            state.setdefault(key, "DB error")
        state["db_error"] = str(exc)

    # ── 阶段性奖励待领取标记 ─────────────────────────────────────────────────
    from update_stage import is_milestone_reward_pending
    state["milestone_reward_pending"] = is_milestone_reward_pending()

    # ── 里程碑阶段计算 ───────────────────────────────────────────────────────
    # 1-18 → hour3，19-36 → hour6，37-54 → hour9，55-72 → hour12
    _MILESTONE_SLOTS = [
        (1,  18, "hour3"),
        (19, 36, "hour6"),
        (37, 54, "hour9"),
        (55, 72, "hour12"),
    ]
    _DEFAULT_MILESTONE = "当前无阶段性任务"
    try:
        count = int(state.get("current_prompt_count") or 0)
    except (ValueError, TypeError):
        count = 0

    current_key = None
    for lo, hi, key in _MILESTONE_SLOTS:
        if lo <= count <= hi:
            current_key = key
            break

    state["current_milestone_key"]  = current_key   # e.g. "hour3" or None
    state["current_milestone_text"] = (
        state.get(current_key, _DEFAULT_MILESTONE) if current_key
        else state.get("hour3", _DEFAULT_MILESTONE)  # count=0：预填第一阶段任务，避免首条 prompt 读到「无」
    )
    # 所有已设置（非默认）的里程碑列表
    state["milestones_set"] = [
        {"key": key, "label": label, "text": state.get(key, _DEFAULT_MILESTONE)}
        for key, label in [("hour3","0~3小时"), ("hour6","3~6小时"),
                           ("hour9","6~9小时"), ("hour12","9~12小时")]
        if state.get(key, _DEFAULT_MILESTONE) != _DEFAULT_MILESTONE
    ]

    # ── 同步写入 -current-task snippet ──────────────────────────────────────
    # 每次 /api/state 轮询时自动将「当前阶段任务」同步进 Alfred snippet
    try:
        _task_to_write = state["current_milestone_text"] or SNIPPETS["current_task"].default
        write_snippet("current_task", _task_to_write)
    except Exception:
        pass  # 写入失败不影响 Dashboard 展示

    # ── 同步写入 -current-progress-indicator snippet ──────────────────────────
    # 读取 milestone_goals.json 中当前槽位的分母，组合成「X/Y 未到达进度」写入 snippet
    try:
        _goals: dict = {}
        if MILESTONE_GOALS_FILE.exists():
            _goals = json.loads(MILESTONE_GOALS_FILE.read_text(encoding="utf-8"))
        # 当前槽位的分母（count=0 时也用 hour3 的分母）
        _goal_key = current_key or "hour3"
        _goal_val = _goals.get(_goal_key, 0)
        _denominator = int(_goal_val.get("denom", 1)) if isinstance(_goal_val, dict) else int(_goal_val)
        _denominator = max(1, _denominator)
        # 读取当前 snippet 值，解析分子（格式：「N/M ...」）
        _cur_indicator = read_snippet("current_progress_indicator")
        try:
            _parts        = _cur_indicator.split("/")
            _numerator    = int(_parts[0])
            # 解析旧 snippet 里的分母（格式：「N/M 标签」）
            _old_denom    = int(_parts[1].split()[0])
            # 分母变化 → 任务已切换，分子必须清零
            if _old_denom != _denominator:
                _numerator = 0
        except (ValueError, IndexError):
            _numerator = 0
        if _denominator > 0:
            if _numerator >= _denominator:
                # 区分「已提前完成但节点未到」与「节点已触发」两种状态
                _stage_val = state.get("stage", "")
                _stage_default = SNIPPETS["stage"].default  # "当前没有达到阶段性节点"
                if _stage_val == _stage_default:
                    _label = "已提前达成，等待节点"
                else:
                    _label = "已到达进度"
            else:
                _label = "未到达进度"
            _progress_str = f"{_numerator}/{_denominator} {_label}"
        else:
            _progress_str = SNIPPETS["current_progress_indicator"].default  # "0/1 未到达进度"
        write_snippet("current_progress_indicator", _progress_str)
        state["current_progress_indicator"] = _progress_str
        state["current_milestone_denominator"] = _denominator
        state["current_milestone_jury"] = bool(_goal_val.get("jury", False)) if isinstance(_goal_val, dict) else False
    except Exception:
        pass

    # ── Boss战节点自动触发 ────────────────────────────────────────────────────
    # 硬核难度下，每次轮询检查 current_prompt_count 是否等于目标条数
    # snippet 值格式：「等待Boss战节点（第N条）」→ 达到时改写为完整 boss 战文本
    try:
        import re as _re
        _diff     = state.get("difficulty", "")
        _bfs_cur  = state.get("bossfight_stage", "")
        if _diff == "硬核难度" and _bfs_cur not in ("当前难度不适用", _BOSSFIGHT_ACTIVE_TEXT):
            _m = _re.search(r"第(\d+)条", _bfs_cur)
            if _m and count == int(_m.group(1)):
                write_snippet("bossfight_stage", _BOSSFIGHT_ACTIVE_TEXT)
                state["bossfight_stage"] = _BOSSFIGHT_ACTIVE_TEXT
    except Exception:
        pass

    # ── 真实学习时长 = 墙上时间 - 累计休息时间 ──────────────────────────────
    if first_raw and curr_raw:
        try:
            first_dt     = datetime.fromisoformat(first_raw)
            curr_dt      = datetime.fromisoformat(curr_raw)
            wall_minutes = (curr_dt - first_dt).total_seconds() / 60
            total_rest   = float(state.get("total_rest_time") or 0)
            state["elapsed_minutes"] = round(wall_minutes - total_rest, 1)
        except Exception:
            state["elapsed_minutes"] = None
    else:
        state["elapsed_minutes"] = None

    # ── 健康度 & 最终命运值 ────────────────────────────────────────────
    try:
        h_text = HEALTH_FILE.read_text(encoding="utf-8").strip() if HEALTH_FILE.exists() else "9"
        state["health"] = int(h_text) if h_text.isdigit() else 9
    except Exception:
        state["health"] = 9

    try:
        ff_text = FINAL_FATE_FILE.read_text(encoding="utf-8").strip() if FINAL_FATE_FILE.exists() else ""
        state["final_fate"] = int(ff_text) if ff_text.lstrip("-").isdigit() else None
    except Exception:
        state["final_fate"] = None

    # ── Boss战结果 ────────────────────────────────────────────────────
    try:
        bd_text = BOSS_DEFEATED_FILE.read_text(encoding="utf-8").strip() if BOSS_DEFEATED_FILE.exists() else "none"
        state["boss_defeated"] = bd_text  # "none" / "true" / "false"
    except Exception:
        state["boss_defeated"] = "none"

    # ── 今日故事主题 ──────────────────────────────────────────────────
    try:
        state["theme"] = THEME_FILE.read_text(encoding="utf-8").strip() \
                         if THEME_FILE.exists() else ""
    except Exception:
        state["theme"] = ""

    return state


# ── Flask routes ─────────────────────────────────────────────────────────────

@app.route("/api/state")
def api_state():
    return jsonify(collect_state())


@app.route("/api/companion-log")
def api_companion_log():
    """Return pending companion skill log entries, then clear the file."""
    log_file = DATA_DIR / "companion_log.json"
    try:
        entries = json.loads(log_file.read_text(encoding="utf-8"))
    except Exception:
        entries = []
    if entries:
        log_file.write_text("[]", encoding="utf-8")
    return jsonify(entries)


@app.route("/api/companion-registry")
def api_companion_registry():
    """Return list of all available companions for the dropdown."""
    from mod.companions import get_registry_list
    return jsonify(get_registry_list())


@app.route("/api/companion-status")
def api_companion_status():
    """Return loaded companions with skill statuses + last chat replies."""
    from mod.companions import get_companion_status, is_locked, _read_active_names
    try:
        count = int(read_snippet("current_prompt_count") or "0")
    except Exception:
        count = 0
    # 读取上次聊天回复（从历史记录中提取最后一条 model 消息）
    chat_file = DATA_DIR / "companion_chat.json"
    try:
        chat_data = json.loads(chat_file.read_text(encoding="utf-8")) if chat_file.exists() else {}
    except Exception:
        chat_data = {}
    companions = get_companion_status(count)
    for c in companions:
        history = chat_data.get(c["name"], [])
        last = ""
        for msg in reversed(history):
            if msg.get("role") == "model":
                last = msg.get("parts", "")
                break
        c["last_reply"] = last
    return jsonify({
        "locked": is_locked(),
        "active_names": _read_active_names(),
        "companions": companions,
    })


@app.route("/api/companion-add", methods=["POST"])
def api_companion_add():
    """Add a companion to a slot."""
    from mod.companions import add_companion
    name = (request.json or {}).get("name", "")
    ok, msg = add_companion(name)
    return jsonify({"ok": ok, "msg": msg}), 200 if ok else 400


@app.route("/api/companion-remove", methods=["POST"])
def api_companion_remove():
    """Remove a companion from a slot."""
    from mod.companions import remove_companion
    name = (request.json or {}).get("name", "")
    ok, msg = remove_companion(name)
    return jsonify({"ok": ok, "msg": msg}), 200 if ok else 400


@app.route("/api/companion-lock", methods=["POST"])
def api_companion_lock():
    """Lock the companion lineup and auto-initialize jury from non-active companions."""
    from mod.companions import lock, is_locked, _read_active_names, COMPANION_REGISTRY
    import random as _rng
    if is_locked():
        return jsonify({"ok": False, "msg": "已锁定"}), 400
    lock()

    # ── 自动初始化陪审团：从非在场助手中随机抽取 ──
    active = _read_active_names()
    pool = [name for name in COMPANION_REGISTRY if name not in active]
    jury_count = min(JURY_SIZE, len(pool))
    jurors = _rng.sample(pool, jury_count) if jury_count > 0 else []

    jury_state = json.loads(JURY_STATE_FILE.read_text(encoding="utf-8")) if JURY_STATE_FILE.exists() else {}
    jury_state["jurors"] = jurors
    jury_state["status"] = "idle"
    JURY_STATE_FILE.write_text(json.dumps(jury_state, ensure_ascii=False, indent=2), encoding="utf-8")

    return jsonify({"ok": True, "msg": f"阵容已锁定，陪审团：{'、'.join(jurors) or '无'}"})


@app.route("/api/companion-use-skill", methods=["POST"])
def api_companion_use_skill():
    """Queue an active skill for next move."""
    from mod.companions import write_pending_skill
    skill_name = (request.json or {}).get("skill", "")
    if not skill_name:
        return jsonify({"ok": False, "msg": "技能名为空"}), 400
    write_pending_skill(skill_name)
    return jsonify({"ok": True, "msg": f"{skill_name} 已排队"})


# ══════════════════════════════════════════════════════════════════════════════
# ██  陪审团 API
# ══════════════════════════════════════════════════════════════════════════════

@app.route("/api/jury/status")
def api_jury_status():
    """返回陪审团当前状态。"""
    try:
        state = json.loads(JURY_STATE_FILE.read_text(encoding="utf-8"))
    except Exception:
        state = {"jurors": [], "status": "idle"}

    # 读取陪审员头像 URL
    from mod.companions import COMPANION_REGISTRY
    juror_info = []
    for name in state.get("jurors", []):
        comp = COMPANION_REGISTRY.get(name)
        juror_info.append({
            "name": name,
            "avatar_url": comp.avatar_url if comp else "",
        })

    return jsonify({
        "jurors": juror_info,
        "status": state.get("status", "idle"),
        "votes": state.get("votes", []),
        "defense": state.get("defense", ""),
        "defender": state.get("defender", ""),
        "suspension_queue": state.get("suspension_queue", []),
        "suspension_index": state.get("suspension_index", 0),
        "history_count": len(state.get("history", [])),
    })


def _advance_progress():
    """陪审团通过时自动推进进度指示器 +1。"""
    try:
        cur = read_snippet("current_progress_indicator") or "0/1 未到达进度"
        parts = cur.split("/")
        numerator = int(parts[0].strip())
        denominator = int(parts[1].strip().split()[0])
        new_num = min(numerator + 1, denominator)
        label = "已到达进度" if new_num >= denominator > 0 else "未到达进度"
        write_snippet("current_progress_indicator", f"{new_num}/{denominator} {label}")
    except Exception:
        pass  # 进度格式异常不影响判决


@app.route("/api/jury/submit", methods=["POST"])
def api_jury_submit():
    """提交 question + answer，触发陪审团审议。"""
    from mod.companions import _read_active_names
    from jury.engine import (
        run_jury_trial, save_trial_to_history,
        apply_health_penalty, JurorVote,
    )
    from dataclasses import asdict

    data = request.get_json() or {}
    question = data.get("question", "").strip()
    answer = data.get("answer", "").strip()

    if not question or not answer:
        return jsonify({"ok": False, "msg": "问题和答案不能为空"}), 400

    # 检查陪审团是否就绪
    try:
        state = json.loads(JURY_STATE_FILE.read_text(encoding="utf-8"))
    except Exception:
        return jsonify({"ok": False, "msg": "陪审团未初始化"}), 400

    if not state.get("jurors"):
        return jsonify({"ok": False, "msg": "无陪审团成员"}), 400

    # 更新状态为审议中
    state["status"] = "deliberating"
    state["current_question"] = question
    state["current_answer"] = answer
    JURY_STATE_FILE.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")

    # 生成辩护意见（用第一个在场助手，Flash 模型节省成本）
    defense = ""
    defender_name = ""
    active = _read_active_names()
    if active:
        defender_name = active[0]
        try:
            from jury.providers import call_gemini
            # 加载辩护人角色资料
            _def_profile_path = BASE / "static" / "companions" / f"{defender_name}.md"
            _def_persona = _def_profile_path.read_text(encoding="utf-8") if _def_profile_path.exists() else ""
            _def_prompt = (
                f"你是「{defender_name}」。以下是你的角色资料：\n{_def_persona}\n\n"
                f"请以你的角色语气，为这位学生的回答做一个简短的辩护（100字以内）。\n\n"
                f"问题：{question}\n\n学生的回答：{answer}"
            )
            defense = call_gemini(_def_prompt)  # 默认 flash
        except Exception:
            defense = ""

    # 执行陪审团审判
    verdict = run_jury_trial(question, answer, defense)

    # 持久化投票 + 辩护到 state
    state = json.loads(JURY_STATE_FILE.read_text(encoding="utf-8"))
    state["votes"] = [asdict(v) for v in verdict.votes]
    state["defense"] = defense
    state["defender"] = defender_name

    if verdict.outcome == "suspended":
        state["status"] = "suspended"
        state["suspension_queue"] = [asdict(v) for v in verdict.suspension_queue]
        state["suspension_index"] = 0
        JURY_STATE_FILE.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")

        return jsonify({
            "ok": True,
            "outcome": "suspended",
            "report": verdict.report,
            "defense": defense,
            "defender": defender_name,
            "suspension_queue": [
                {"juror_name": v.juror_name, "question": v.suspension_question}
                for v in verdict.suspension_queue
            ],
        })

    # 非悬置：直接出判决
    if verdict.outcome == "health_minus_1":
        new_health = apply_health_penalty()
    else:
        new_health = None
    _advance_progress()  # 无论结果如何，做了就算进度 +1

    save_trial_to_history(question, answer, verdict)

    result = {
        "ok": True,
        "outcome": verdict.outcome,
        "report": verdict.report,
        "defense": defense,
        "defender": defender_name,
        "reject_count": verdict.reject_count,
        "approve_count": verdict.approve_count,
        "votes": [asdict(v) for v in verdict.votes],
    }
    if new_health is not None:
        result["new_health"] = new_health
    return jsonify(result)


@app.route("/api/jury/suspend-reply", methods=["POST"])
def api_jury_suspend_reply():
    """玩家回答悬置追问。"""
    from jury.engine import (
        resolve_suspension, finalize_verdict,
        save_trial_to_history, apply_health_penalty, JurorVote,
    )
    from dataclasses import asdict

    data = request.get_json() or {}
    reply = data.get("reply", "").strip()

    try:
        state = json.loads(JURY_STATE_FILE.read_text(encoding="utf-8"))
    except Exception:
        return jsonify({"ok": False, "msg": "状态读取失败"}), 500

    if state.get("status") != "suspended":
        return jsonify({"ok": False, "msg": "当前没有悬置追问"}), 400

    queue = state.get("suspension_queue", [])
    idx = state.get("suspension_index", 0)

    if idx >= len(queue):
        return jsonify({"ok": False, "msg": "所有追问已回答完毕"}), 400

    current = queue[idx]
    juror_name = current["juror_name"]
    sq = current.get("suspension_question", "")

    # 调用该陪审员做最终裁决
    new_vote = resolve_suspension(
        juror_name=juror_name,
        original_question=state.get("current_question", ""),
        original_answer=state.get("current_answer", ""),
        suspension_question=sq,
        student_reply=reply,
    )

    # 更新该陪审员在 votes 中的投票
    votes_data = state.get("votes", [])
    for i, v in enumerate(votes_data):
        if v["juror_name"] == juror_name:
            votes_data[i] = asdict(new_vote)
            break

    state["votes"] = votes_data
    state["suspension_index"] = idx + 1

    # 检查是否还有更多追问
    if state["suspension_index"] < len(queue):
        # 还有追问
        JURY_STATE_FILE.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
        next_q = queue[state["suspension_index"]]
        return jsonify({
            "ok": True,
            "done": False,
            "resolved_vote": asdict(new_vote),
            "next": {
                "juror_name": next_q["juror_name"],
                "question": next_q.get("suspension_question", ""),
                "index": state["suspension_index"],
                "total": len(queue),
            },
        })

    # 全部追问回答完毕 → 最终判决
    all_votes = [JurorVote(**v) for v in votes_data]
    verdict = finalize_verdict(all_votes)

    if verdict.outcome == "health_minus_1":
        new_health = apply_health_penalty()
    else:
        new_health = None
    _advance_progress()  # 无论结果如何，做了就算进度 +1

    save_trial_to_history(
        state.get("current_question", ""),
        state.get("current_answer", ""),
        verdict,
    )

    result = {
        "ok": True,
        "done": True,
        "outcome": verdict.outcome,
        "report": verdict.report,
        "reject_count": verdict.reject_count,
        "approve_count": verdict.approve_count,
        "votes": [asdict(v) for v in all_votes],
    }
    if new_health is not None:
        result["new_health"] = new_health
    return jsonify(result)


@app.route("/api/jury/report")
def api_jury_report():
    """获取最近一次审议报告。"""
    try:
        state = json.loads(JURY_STATE_FILE.read_text(encoding="utf-8"))
    except Exception:
        return jsonify({"ok": False, "report": ""}), 500

    history = state.get("history", [])
    if not history:
        return jsonify({"ok": True, "report": "暂无审议记录。"})

    last = history[-1]
    return jsonify({
        "ok": True,
        "report": last.get("report", ""),
        "outcome": last.get("outcome", ""),
        "time": last.get("time", ""),
        "votes": last.get("votes", []),
    })


@app.route("/api/jury/send-report", methods=["POST"])
def api_jury_send_report():
    """复制报告到剪切板并触发 stay.applescript 发送到 AI 对话。"""
    data = request.get_json() or {}
    report = data.get("report", "").strip()
    if not report:
        return jsonify({"ok": False, "msg": "报告为空"}), 400

    try:
        # ① 写入剪切板
        subprocess.run(["pbcopy"], input=report.encode("utf-8"),
                       check=True, timeout=5)
        # ② 运行 stay.applescript
        stay_script = str(BASE / "applescript" / "stay.applescript")
        subprocess.run(["osascript", stay_script], check=True, timeout=15)
        return jsonify({"ok": True})
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)}), 500

COMPANION_CHAT_FILE = DATA_DIR / "companion_chat.json"


MAX_CHAT_HISTORY = 10  # 保留最多 10 轮对话（20 条消息）


def _roleplay_pipeline(character_name: str, message: str, history: list) -> str:
    """调用 Gemini API 进行角色扮演对话，支持多轮上下文，返回角色回复。"""
    import re
    import google.generativeai as genai

    cfg = _load_api_config()
    api_key = cfg.get("gemini_api_key", "")
    model_name = cfg.get("gemini_model", "gemini-3.1-pro-preview")
    if not api_key or api_key.startswith("在此"):
        raise ValueError("请先在 api_config.json 中填写有效的 Gemini API Key")

    # 动态读取角色资料
    profile_path = BASE / "static" / "companions" / f"{character_name}.md"
    if profile_path.exists():
        character_profile = profile_path.read_text(encoding="utf-8")
    else:
        character_profile = f"你扮演的角色是 {character_name}。"

    # 读取当前游戏状态面板
    panel_lines = []
    for key, snip in SNIPPETS.items():
        if snip.panel_label:
            try:
                val = read_snippet(key)
            except Exception:
                val = "（读取失败）"
            panel_lines.append(f"{snip.panel_label}：{val}")
    game_state = "\n".join(panel_lines) if panel_lines else "（暂无游戏状态数据）"

    # 实时读取当前剪切板内容
    try:
        clip = subprocess.run(["pbpaste"], capture_output=True, timeout=3).stdout.decode("utf-8", errors="replace").strip()
        if len(clip) > 2000:
            clip = clip[:2000] + "…（已截断）"
    except Exception:
        clip = "（读取失败）"

    system_prompt = (
        "你是一个角色扮演专家。\n\n"
        f"【背景】该角色是玩家的学习助手，和玩家一起合作完成一个番茄钟学习追踪游戏。"
        f"角色了解游戏规则，能看到玩家的当前状态面板，可以用角色本身的语气鼓励、提醒或陪伴玩家。\n\n"
        f"【你扮演的角色资料】\n{character_profile}\n\n"
        f"【玩家当前游戏状态面板】\n{game_state}\n\n"
        f"【玩家当前的剪切板信息】\n{clip}\n\n"
        "【回复规则】\n"
        "1. 你的回应字数在200字以内\n"
        "2. 尽可能根据角色的性格特点、语气和说话方式来扮演角色\n"
        "3. 保持角色的个性，不要跳出角色\n"
        "4. 用角色的口吻直接回复，不要加任何前缀或解释\n"
        "5. 可以根据玩家当前游戏状态给出符合角色性格的反应（如鼓励、调侃、关心等）\n"
        "6. 回复必须是纯文本，禁止使用任何 markdown 格式（不要用加粗、斜体、标题等）"
    )

    genai.configure(api_key=api_key)
    model = genai.GenerativeModel(
        model_name,
        system_instruction=system_prompt,
    )

    # 构建 Gemini 格式的历史记录
    gemini_history = []
    for msg in history:
        gemini_history.append({
            "role": msg["role"],
            "parts": [msg["parts"]],
        })

    chat = model.start_chat(history=gemini_history)
    response = chat.send_message(
        message,
        generation_config=genai.types.GenerationConfig(
            temperature=0.8,
            max_output_tokens=8192,
        ),
    )

    # 诊断
    try:
        fr = response.candidates[0].finish_reason
        print(f"[companion-chat] finish_reason={fr}")
    except Exception:
        pass
    # 拼接 parts
    try:
        parts = response.candidates[0].content.parts
        full_text = "".join(p.text for p in parts if hasattr(p, "text"))
    except Exception:
        full_text = response.text
    full_text = re.sub(r"\*{1,2}([^*]+)\*{1,2}", r"\1", full_text)
    return full_text.strip()


@app.route("/api/companion-chat", methods=["POST"])
def api_companion_chat():
    """角色扮演对话：接收角色名和消息，返回角色扮演回复（带多轮上下文）。"""
    data = request.get_json(silent=True) or {}
    name = data.get("name", "").strip()
    message = data.get("message", "").strip()
    if not name:
        return jsonify({"ok": False, "error": "角色名为空"}), 400
    if not message:
        return jsonify({"ok": False, "error": "消息为空"}), 400
    try:
        # 读取该角色的历史对话
        try:
            chat_data = json.loads(COMPANION_CHAT_FILE.read_text(encoding="utf-8")) \
                if COMPANION_CHAT_FILE.exists() else {}
        except Exception:
            chat_data = {}
        history = chat_data.get(name, [])

        # 调用 API（传入历史上下文）
        reply = _roleplay_pipeline(name, message, history)

        # 追加本轮对话到历史
        history.append({"role": "user", "parts": message})
        history.append({"role": "model", "parts": reply})
        # 限制最多 MAX_CHAT_HISTORY 轮（每轮 = user + model = 2 条）
        if len(history) > MAX_CHAT_HISTORY * 2:
            history = history[-(MAX_CHAT_HISTORY * 2):]
        chat_data[name] = history

        COMPANION_CHAT_FILE.write_text(
            json.dumps(chat_data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return jsonify({"ok": True, "reply": reply})
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)}), 500


@app.route("/api/next-pomodoro", methods=["POST"])
def api_next_pomodoro():
    # 记录 move 前的条数，用于让后台线程等 move 完成
    pre_move_count = read_snippet("current_prompt_count") or "0"
    try:
        if APP_MODE == "sandbox":
            data = request.get_json(silent=True) or {}
            # host 页面传 message；Dashboard 按钮不传 → 读系统剪贴板
            user_msg = data.get("message")          # None if from Dashboard
            clip_override = user_msg if user_msg else None
            text = move_workflow.run(clipboard_override=clip_override)
            backup_prompt(text, prompt_type="move")
            import host_ai
            reply = host_ai.chat(text)
            # 自动触发叙事引擎
            threading.Thread(
                target=_run_story_turn_bg,
                args=(pre_move_count,),
                daemon=True,
            ).start()
            return jsonify({"ok": True, "reply": reply})
        elif APP_MODE == "standalone":
            text = move_workflow.run()
            get_browser_driver().inject_and_send(text)
        else:
            script = (
                'tell application id "com.runningwithcrayons.Alfred" '
                'to run trigger "btn_next_pomodoro" '
                'in workflow "com.pomodoro.ai" '
                'with argument "test"'
            )
            subprocess.run(["osascript", "-e", script], check=True, timeout=5)
        # 自动触发叙事引擎（后台线程，不阻塞）
        threading.Thread(
            target=_run_story_turn_bg,
            args=(pre_move_count,),
            daemon=True,
        ).start()
        return jsonify({"ok": True})
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)}), 500


def _run_story_turn_bg(pre_move_count: str):
    """后台执行叙事引擎，先等 move 完成再读 snippets。"""
    import time
    # 等待 move.py 写完 snippets（Alfred 模式下 move 是异步的）
    for _ in range(30):  # 最多等 15 秒
        current = read_snippet("current_prompt_count") or "0"
        if current != pre_move_count:
            break
        time.sleep(0.5)
    try:
        from game.engine import run_turn
        run_turn()
    except Exception as exc:
        print(f"[story] turn failed: {exc}", file=sys.stderr)


@app.route("/api/stay-pomodoro", methods=["POST"])
def api_stay_pomodoro():
    try:
        # 刷新「当前学习正文」— 仅非 sandbox 模式使用系统剪贴板
        if APP_MODE != "sandbox":
            try:
                clip = subprocess.run(["pbpaste"], capture_output=True, text=True, timeout=3).stdout.strip()
                if clip:
                    write_snippet("current_clipboard", clip[:8000])
            except Exception:
                pass
        if APP_MODE == "sandbox":
            data = request.get_json(silent=True) or {}
            user_msg = data.get("message")          # None if from Dashboard
            clip_override = user_msg if user_msg else None
            text = stay_workflow.run(clipboard_override=clip_override)
            backup_prompt(text, prompt_type="stay")
            import host_ai
            reply = host_ai.chat(text)
            return jsonify({"ok": True, "reply": reply})
        elif APP_MODE == "standalone":
            text = stay_workflow.run()
            backup_prompt(text, prompt_type="stay")
            get_browser_driver().inject_and_send(text)
        else:
            script = (
                'tell application id "com.runningwithcrayons.Alfred" '
                'to run trigger "btn_stay" '
                'in workflow "com.pomodoro.ai" '
                'with argument "test"'
            )
            subprocess.run(["osascript", "-e", script], check=True, timeout=5)
        return jsonify({"ok": True})
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)}), 500



AGENT_WORKSPACE    = DATA_ROOT / "Agent_Workspace"
AGENT_WORKSPACE.mkdir(parents=True, exist_ok=True)
COMPLAINTS_FILE    = AGENT_WORKSPACE / "complaints.txt"
COMPLAINT_LOGIC    = AGENT_WORKSPACE / "complaint_logic.txt"
API_CONFIG_FILE    = DATA_ROOT / "api_config.json"


def _load_api_config() -> dict:
    """从 api_config.json 中读取 Gemini API key 和模型名。"""
    if API_CONFIG_FILE.exists():
        return json.loads(API_CONFIG_FILE.read_text(encoding="utf-8"))
    return {}


def _investigate_violation(complaints_text: str, prompt_md_text: str) -> str:
    """针对违规投诉，向 Gemini 发起规则条文调查，返回结构化调查报告文本。"""
    import google.generativeai as genai

    cfg = _load_api_config()
    api_key = cfg.get("gemini_api_key", "")
    model_name = cfg.get("gemini_model_lite", "gemini-3-flash-preview")
    if not api_key or api_key.startswith("在此"):
        raise ValueError("请先在 api_config.json 中填写有效的 Gemini API Key")

    genai.configure(api_key=api_key)
    model = genai.GenerativeModel(model_name)

    system_prompt = (
        "你是一个游戏规则条文检索器。\n"
        "用户会提供一段AI违规输出和抱怨描述，以及完整的游戏规则文档（prompt.md）。\n"
        "你的任务是：\n"
        "1. 仔细分析用户的抱怨，理解AI哪里违规了\n"
        "2. 在游戏规则文档中检索被违反的具体条文\n"
        "3. 输出调查报告，格式包含【违规行为归纳】、【违反规则条文】（列出条目编号及要点）、【结论】\n"
        "请直接输出调查报告，不要添加任何前缀或解释。"
    )

    user_message = (
        f"以下是用户的违规投诉：\n\n{complaints_text}\n\n"
        f"{'='*60}\n\n"
        f"以下是完整的游戏规则文档（prompt.md）：\n\n{prompt_md_text}"
    )

    response = model.generate_content(
        [system_prompt, user_message],
        generation_config=genai.types.GenerationConfig(
            temperature=0.2,
            max_output_tokens=2048,
        ),
    )
    return response.text


def _violation_agent_background(complaints_text: str):
    """后台线程：调用 Gemini API → 写入 complaint_logic.txt → 调用 complaint_manage.py 存档。"""
    try:
        prompt_md_path = BASE / "docs" / "prompt.md"
        prompt_md = prompt_md_path.read_text(encoding="utf-8") if prompt_md_path.exists() else ""

        result = _investigate_violation(complaints_text, prompt_md)
        COMPLAINT_LOGIC.write_text(result, encoding="utf-8")

        # 自动存档：提取精简的违规行为和条文编号
        # 从 Agent 返回的结构化报告中提取关键字段
        behavior_summary = result.split("【违反规则条文】")[0].replace("【违规行为归纳】", "").strip() \
            if "【违反规则条文】" in result else result[:200]
        rules_summary = result.split("【结论】")[0].split("【违反规则条文】")[-1].strip() \
            if "【违反规则条文】" in result else "见 complaint_logic.txt"

        from complaint_manager.complaint_manage import load_history, save_history
        from datetime import datetime as _dt
        record = {
            "timestamp": _dt.now().strftime("%Y-%m-%d %H:%M:%S"),
            "violation_behavior": behavior_summary[:500],
            "violated_rules": rules_summary[:500],
        }
        history = load_history()
        history.append(record)
        save_history(history)
    except Exception as exc:
        # 将错误写入 complaint_logic.txt 以便前端轮询发现
        COMPLAINT_LOGIC.write_text(f"❌ 调查失败：{exc}", encoding="utf-8")


@app.route("/api/violation-start", methods=["POST"])
def api_violation_start():
    """Step 2 后台初始化：清空工作文件 → 写入投诉 → 异步调用 Gemini API 执行规则调查。"""
    data       = request.get_json(silent=True) or {}
    violations = data.get("violations", "").strip()
    source     = data.get("source", "").strip()
    try:
        AGENT_WORKSPACE.mkdir(parents=True, exist_ok=True)
        # ① 清空两个工作文件
        COMPLAINTS_FILE.write_text("", encoding="utf-8")
        COMPLAINT_LOGIC.write_text("", encoding="utf-8")
        # ② 写入用户填写的违规来源 + 违规描述
        formatted = (
            f"【违规来源（用户认为AI的输出中产生违规的那个文本块）】\n{source}\n\n"
            f"【用户抱怨（为违规来源的抱怨）】\n{violations}"
        )
        COMPLAINTS_FILE.write_text(formatted, encoding="utf-8")
        # ③ 在后台线程中调用 Gemini API（非阻塞，前端通过 /api/violation-poll 轮询结果）
        thread = threading.Thread(
            target=_violation_agent_background,
            args=(formatted,),
            daemon=True,
        )
        thread.start()
        return jsonify({"ok": True})
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)}), 500


@app.route("/api/violation-poll", methods=["GET"])
def api_violation_poll():
    """轮询：检查 complaint_logic.txt 是否已被 Agent 写入结果。"""
    try:
        content = COMPLAINT_LOGIC.read_text(encoding="utf-8").strip() \
                  if COMPLAINT_LOGIC.exists() else ""
        if content:
            return jsonify({"ok": True, "ready": True, "expected": content})
        return jsonify({"ok": True, "ready": False})
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)}), 500


@app.route("/api/violation-report", methods=["POST"])
def api_violation_report():
    """构建违规通告 prompt（附完整 prompt.md），写入剪切板并触发 stay.applescript。"""
    data       = request.get_json(silent=True) or {}
    violations = data.get("violations", "").strip()
    source     = data.get("source", "").strip()
    expected   = data.get("expected", "").strip()
    try:
        prompt_md_path = BASE / "docs" / "prompt.md"
        prompt_md = prompt_md_path.read_text(encoding="utf-8") \
                    if prompt_md_path.exists() else "（prompt.md 文件不存在）"

        full_prompt = (
            "【违规通告】\n"
            "AI 已违反《番茄钟学习管理系统》核心游戏规则\n\n"
            f"违规来源（AI输出中违规的文本块）：{source}\n\n"
            f"规则调查员的调查报告结果：{expected}\n"
            f"违规描述：{violations}\n"
            "提出警告：\n"
            "（1）在AI修改其违规行为之前，游戏无法继续\n"
            "（2）AI必须重新阅读prompt.md，确保没有遗忘或误解重要游戏规则\n"
            "（3）对于已经发生的人生事件，AI可以无需修改自己的错判，但是必须警醒自己的错误（唯一的例外：叙事严重崩坏溃烂，必须修改。）\n\n"
            "---\n\n"
            + prompt_md
        )

        subprocess.run(["pbcopy"], input=full_prompt.encode("utf-8"),
                       check=True, timeout=5)
        # violationcount += 1（原 increment_violation_count_snippet.py 内联）
        cur_viol = int(read_snippet("violationcount") or "0")
        write_snippet("violationcount", str(cur_viol + 1))
        if APP_MODE == "standalone":
            # standalone: 用 stay_workflow 发送，full_prompt 作为 clipboard 内容
            text = stay_workflow.run(clipboard_override=full_prompt)
            backup_prompt(text, prompt_type="violation")
            get_browser_driver().inject_and_send(text)
        else:
            # alfred: 写入剪切板 + 调用 stay.applescript
            subprocess.run(["pbcopy"], input=full_prompt.encode("utf-8"),
                           check=True, timeout=5)
            stay_script = str(BASE / "applescript" / "stay.applescript")
            subprocess.run(["osascript", stay_script], check=True, timeout=10)
            try:
                backup_prompt(full_prompt, prompt_type="violation")
            except Exception:
                pass
        return jsonify({"ok": True})
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)}), 500


@app.route("/api/pause", methods=["POST"])
def api_pause():
    try:
        if APP_MODE == "standalone":
            text = pause_workflow.run()
            get_browser_driver().inject_and_send(text)
        else:
            script = (
                'tell application id "com.runningwithcrayons.Alfred" '
                'to run trigger "btn_pause" '
                'in workflow "com.pomodoro.ai" '
                'with argument "test"'
            )
            subprocess.run(["osascript", "-e", script], check=True, timeout=5)
        return jsonify({"ok": True})
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)}), 500


@app.route("/api/continue", methods=["POST"])
def api_continue():
    try:
        if APP_MODE == "standalone":
            text = continue_workflow.run()
            get_browser_driver().inject_and_send(text)
        else:
            script = (
                'tell application id "com.runningwithcrayons.Alfred" '
                'to run trigger "btn_continue" '
                'in workflow "com.pomodoro.ai" '
                'with argument "test"'
            )
            subprocess.run(["osascript", "-e", script], check=True, timeout=5)
        return jsonify({"ok": True})
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)}), 500


@app.route("/api/getcard", methods=["POST"])
def api_getcard():
    """宿命卡 +1：只增加 snippet 计数器。"""
    try:
        current = int(read_snippet("countcard") or "0")
        write_snippet("countcard", str(current + 1))
        return jsonify({"ok": True})
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)}), 500

@app.route("/api/getinterventioncard", methods=["POST"])
def api_getinterventioncard():
    """干预卡 +1：只增加 snippet 计数器。"""
    try:
        current = int(read_snippet("countinterventioncard") or "0")
        write_snippet("countinterventioncard", str(current + 1))
        return jsonify({"ok": True})
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)}), 500




@app.route("/api/prompt-backup", methods=["GET"])
def api_prompt_backup():
    """返回最近 5 条 prompt 备份（结构化格式）。"""
    from config import PROMPT_BACKUP_FILE
    try:
        data = json.loads(PROMPT_BACKUP_FILE.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        data = []
    if isinstance(data, list):
        recent = data[-5:][::-1]  # 最后 5 条，倒序
    else:
        # 兼容旧 dict 格式
        items = sorted(data.items(), key=lambda x: x[0], reverse=True)[:5]
        recent = [{"time": t, "type": "unknown", "state": {}, "prompt_text": v} for t, v in items]
    return jsonify({"backups": recent})


@app.route("/api/target-urls", methods=["GET"])
def api_get_target_urls():
    """读取当前 target_urls 配置。"""
    from config import TARGET_URLS
    return jsonify({"urls": TARGET_URLS})


@app.route("/api/target-urls", methods=["POST"])
def api_set_target_urls():
    """写入 target_urls 到 api_config.json。"""
    from config import API_CONFIG_FILE
    data = request.get_json(silent=True) or {}
    urls = data.get("urls", [])
    if not urls or not isinstance(urls, list):
        return jsonify({"ok": False, "error": "urls 必须是非空列表"}), 400
    try:
        try:
            cfg = json.loads(API_CONFIG_FILE.read_text(encoding="utf-8"))
        except (FileNotFoundError, json.JSONDecodeError):
            cfg = {}
        cfg["target_urls"] = urls
        API_CONFIG_FILE.write_text(
            json.dumps(cfg, ensure_ascii=False, indent=4), encoding="utf-8"
        )
        import config
        config.TARGET_URLS = urls
        return jsonify({"ok": True, "urls": urls})
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)}), 500


@app.route("/api/setup", methods=["POST"])
def api_setup():
    data = request.get_json()
    try:
        hours      = int(data["hours"])
        max_rest   = str(int(data["max_rest"]))
        difficulty = data["difficulty"]
        milestones = data.get("milestones", [])
        theme      = data.get("theme", "").strip()

        write_snippet("max_rest_time", max_rest)
        write_snippet("difficulty",    difficulty)

        # ── 写入里程碑阶段任务 ────────────────────────────────────────────
        # 与 JS MILESTONE_DEFS 保持一致：门槛 3/6/9/12 小时对应 hour3/6/9/12
        _MILESTONE_MAP = [
            (3,  "hour3"),
            (6,  "hour6"),
            (9,  "hour9"),
            (12, "hour12"),
        ]
        # 先全部重置为默认值（防止旧数据残留）
        default_milestone = SNIPPETS["hour3"].default  # "当前无阶段性任务"
        for _, key in _MILESTONE_MAP:
            write_snippet(key, default_milestone)

        # 再按学习时长写入用户填写的内容
        applicable_keys = [key for threshold, key in _MILESTONE_MAP if hours >= threshold]
        for key, text in zip(applicable_keys, milestones):
            if text:  # 跳过空字符串
                write_snippet(key, text)

        # ── 写入进度条分母 + 陪审团标记到 milestone_goals.json ────────────────
        denominators = data.get("denominators", [])  # 与 milestones[] 等长的整数列表
        jury_flags   = data.get("jury_flags", [])    # 与 milestones[] 等长的布尔列表
        goals: dict[str, dict] = {
            "hour3":  {"denom": 1, "jury": False},
            "hour6":  {"denom": 1, "jury": False},
            "hour9":  {"denom": 1, "jury": False},
            "hour12": {"denom": 1, "jury": False},
        }
        for i, key in enumerate(applicable_keys):
            denom = 0
            if i < len(denominators):
                try:
                    denom = max(1, int(denominators[i]))
                except (ValueError, TypeError):
                    pass
            jury = jury_flags[i] if i < len(jury_flags) else False
            goals[key] = {"denom": denom, "jury": bool(jury)}
        MILESTONE_GOALS_FILE.parent.mkdir(parents=True, exist_ok=True)
        MILESTONE_GOALS_FILE.write_text(
            json.dumps(goals, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        # 同步重置 -current-progress-indicator（分子清零）
        _init_goal = goals.get("hour3", {})
        _init_denom = _init_goal.get("denom", 1) if isinstance(_init_goal, dict) else 1
        _init_denom = max(1, _init_denom)
        write_snippet(
            "current_progress_indicator",
            f"0/{_init_denom} 未到达进度"
        )

        # ── 学习记录总条数 ───────────────────────────────────────────────────
        write_snippet("total_count", str(hours * 6))

        # ── Boss战节点初始化 ──────────────────────────────────────────────────
        if difficulty == "硬核难度":
            # 触发节点：倒数第2条prompt输出（即第 hours*6 - 1 条）
            bossfight_target = hours * 6 - 1
            write_snippet("bossfight_stage", f"等待Boss战节点（第{bossfight_target}条）")
        else:
            write_snippet("bossfight_stage", "当前难度不适用")

        # ── 今日故事主题 ─────────────────────────────────────────────────────
        THEME_FILE.parent.mkdir(parents=True, exist_ok=True)
        THEME_FILE.write_text(theme, encoding="utf-8")

        prompt = generate_launch_prompt(hours, max_rest, difficulty, milestones, theme)
        return jsonify({"ok": True, "prompt": prompt})
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)}), 500


@app.route("/api/health-adjust", methods=["POST"])
def api_health_adjust():
    """Decrease (or increase) health by delta, clamped to [0, 10]."""
    data  = request.get_json()
    delta = int(data.get("delta", 0))
    try:
        current = int(HEALTH_FILE.read_text(encoding="utf-8").strip()) \
                  if HEALTH_FILE.exists() else 9
        new_val = max(0, current + delta)
        HEALTH_FILE.parent.mkdir(parents=True, exist_ok=True)
        HEALTH_FILE.write_text(str(new_val), encoding="utf-8")
        return jsonify({"ok": True, "health": new_val})
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)}), 500


@app.route("/api/boss-defeated", methods=["POST"])
def api_boss_defeated():
    """Record boss battle result. Payload: {result: 'true' | 'false'}"""
    data   = request.get_json()
    result = data.get("result", "").strip()
    if result not in ("true", "false"):
        return jsonify({"ok": False, "error": "result must be 'true' or 'false'"}), 400
    try:
        BOSS_DEFEATED_FILE.parent.mkdir(parents=True, exist_ok=True)
        BOSS_DEFEATED_FILE.write_text(result, encoding="utf-8")
        if result == "true":
            # Boss胜利 → +800
            update_total_score(delta=800)
        else:
            # Boss失败 → 写入游戏失败状态，-300，再 ×0.9
            write_snippet("is_victory", "已失败，失败来源：boss战失败")
            update_total_score(delta=-300)
            update_total_score(factor=0.9)
        return jsonify({"ok": True, "boss_defeated": result})
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)}), 500


@app.route("/api/declare-victory", methods=["POST"])
def api_declare_victory():
    """Settle the game as a victory. No server-side re-validation needed —
    all failure paths are auto-written by backend scripts before this point."""
    try:
        write_snippet("is_victory", "已胜利")
        # 胜利结算 → ×1.1
        final_score = update_total_score(factor=1.1)

        # ── 写入游戏存档 ────────────────────────────────────────────────────
        # 里程碑列表：hour3 / hour6 / hour9 / hour12 对应任务文字（过滤空槽位）
        milestone_keys  = ["hour3", "hour6", "hour9", "hour12"]
        milestone_slots = ["3小时节点", "6小时节点", "9小时节点", "12小时节点"]
        milestones = []
        for label, key in zip(milestone_slots, milestone_keys):
            text = read_snippet(key)
            if text and text not in ("0", "", "当前无阶段性任务"):
                milestones.append({"节点": label, "任务": text})

        save_data = {
            "当天预期总条数":   int(read_snippet("total_count") or 0),
            "当天设置的休息总时长": read_snippet("max_rest_time"),
            "总积分":           final_score,
            "是否胜利":         "已胜利",
            "当前游戏难度":     read_snippet("difficulty"),
            "今日里程碑任务总览": milestones,
            "今日学习助手列表": json.loads((DATA_DIR / "active_companions.json").read_text(encoding="utf-8")) if (DATA_DIR / "active_companions.json").exists() else [],
            "存档时间":         datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        }

        save_dir = BASE / "saved"
        save_dir.mkdir(parents=True, exist_ok=True)
        saves_jsonl = save_dir / "saves.jsonl"
        # 追加一行（JSONL格式）—— 永不覆盖历史，pandas 可直接 read_json(lines=True)
        with saves_jsonl.open("a", encoding="utf-8") as f:
            f.write(json.dumps(save_data, ensure_ascii=False) + "\n")
        print(f"💾  游戏存档已追加至 saves.jsonl（当前共 {sum(1 for _ in saves_jsonl.open())} 条）")

        return jsonify({"ok": True, "save_file": "saves.jsonl"})
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)}), 500


@app.route("/api/declare-defeat", methods=["POST"])
def api_declare_defeat():
    """Settle the game as a defeat. Writes the same save fields as declare-victory."""
    try:
        # 当前积分（失败结算不额外乘以系数，惩罚已在触发时执行）
        final_score = int(read_snippet("total_score") or 0)

        # 里程碑列表
        milestone_keys  = ["hour3", "hour6", "hour9", "hour12"]
        milestone_slots = ["3小时节点", "6小时节点", "9小时节点", "12小时节点"]
        milestones = []
        for label, key in zip(milestone_slots, milestone_keys):
            text = read_snippet(key)
            if text and text not in ("0", "", "当前无阶段性任务"):
                milestones.append({"节点": label, "任务": text})

        # 读取当前失败状态（保留失败来源文字）
        is_victory_val = read_snippet("is_victory") or "已失败"

        save_data = {
            "当天预期总条数":    int(read_snippet("total_count") or 0),
            "当天设置的休息总时长": read_snippet("max_rest_time"),
            "总积分":            final_score,
            "是否胜利":          is_victory_val,
            "当前游戏难度":      read_snippet("difficulty"),
            "今日里程碑任务总览": milestones,
            "今日学习助手列表":  json.loads((DATA_DIR / "active_companions.json").read_text(encoding="utf-8")) if (DATA_DIR / "active_companions.json").exists() else [],
            "存档时间":          datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        }

        save_dir = BASE / "saved"
        save_dir.mkdir(parents=True, exist_ok=True)
        saves_jsonl = save_dir / "saves.jsonl"
        with saves_jsonl.open("a", encoding="utf-8") as f:
            f.write(json.dumps(save_data, ensure_ascii=False) + "\n")
        print(f"💾  失败存档已追加至 saves.jsonl")

        return jsonify({"ok": True, "save_file": "saves.jsonl"})
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)}), 500

@app.route("/api/claim-lucky-score", methods=["POST"])
def api_claim_lucky_score():
    """Exchange lucky reward for +5 score (instead of drawing a card)."""
    try:
        cur = read_snippet("is_eligible_for_reward")
        if "[SCORE_EXCHANGE_AVAILABLE]" not in cur:
            return jsonify({"ok": False, "error": "换分条件不满足"}), 400

        # +5 积分
        score_raw = read_snippet("total_score") or "0"
        new_score = int(score_raw) + 5
        write_snippet("total_score", str(new_score))

        # 清除幸运奖励状态
        write_snippet("is_eligible_for_reward", SNIPPETS["is_eligible_for_reward"].default)

        return jsonify({"ok": True, "new_score": new_score})
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)}), 500


@app.route("/api/claim-lucky-card", methods=["POST"])
def api_claim_lucky_card():
    """玩家领卡后清除幸运奖励状态（不加积分）。"""
    try:
        cur = read_snippet("is_eligible_for_reward")
        if "幸运系统已触发" not in cur:
            return jsonify({"ok": False, "error": "幸运系统未触发"}), 400
        write_snippet("is_eligible_for_reward", SNIPPETS["is_eligible_for_reward"].default)
        return jsonify({"ok": True})
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)}), 500


@app.route("/api/claim-milestone-card", methods=["POST"])
def api_claim_milestone_card():
    """玩家领卡后清除阶段性奖励状态。"""
    try:
        from update_stage import is_milestone_reward_pending, set_milestone_reward
        if not is_milestone_reward_pending():
            return jsonify({"ok": False, "error": "无阶段性奖励待领取"}), 400
        set_milestone_reward(False)
        return jsonify({"ok": True})
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)}), 500


@app.route("/api/reset", methods=["POST"])


def api_reset():
    """Run reset.py to wipe all game state back to Day-0 defaults."""
    try:
        data = request.get_json(silent=True) or {}
        # 直接调用 reset.main() — 打包后 subprocess 不可用
        from actions.reset import main as _reset_main
        import io, contextlib
        # 传递 --no-archive 参数
        _saved_argv = sys.argv[:]
        if data.get("no_archive"):
            sys.argv = ["reset.py", "--no-archive"]
        else:
            sys.argv = ["reset.py"]
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(buf):
            rc = _reset_main()
        sys.argv = _saved_argv
        output = buf.getvalue()
        return jsonify({"ok": rc == 0, "output": output})
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)}), 500


@app.route("/api/progress-step", methods=["POST"])

def api_progress_step():
    """Increment or decrement the progress indicator numerator by delta (+1 / -1)."""
    data = request.get_json()
    delta = int(data.get("delta", 0))

    # 当前阶段如已勾选「经过陪审团系统」，禁止手动调整进度
    try:
        goals = json.loads(MILESTONE_GOALS_FILE.read_text(encoding="utf-8")) if MILESTONE_GOALS_FILE.exists() else {}
        count = int(read_snippet("current_prompt_count") or "0")
        total = int(read_snippet("total_count") or "0")
        if total > 0:
            frac = count / total
            key = "hour12" if frac > 0.75 else "hour9" if frac > 0.5 else "hour6" if frac > 0.25 else "hour3"
        else:
            key = "hour3"
        goal_val = goals.get(key, {})
        if isinstance(goal_val, dict) and goal_val.get("jury", False):
            return jsonify({"ok": False, "error": "当前阶段已启用陪审团系统，进度只能通过陪审团推进"})
    except Exception:
        pass
    try:
        cur = read_snippet("current_progress_indicator") or "0/1 未到达进度"

        # Parse "N/M ..." format
        parts = cur.split("/")
        numerator   = int(parts[0].strip())
        denominator = int(parts[1].strip().split()[0])

        # Clamp new numerator to [0, denominator]
        new_num = max(0, min(numerator + delta, denominator))
        label   = "已到达进度" if new_num >= denominator > 0 else "未到达进度"
        new_str = f"{new_num}/{denominator} {label}"

        write_snippet("current_progress_indicator", new_str)
        return jsonify({"ok": True, "value": new_str})
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)}), 500


@app.route("/")
def index():
    return render_template("dashboard.html", app_mode=APP_MODE)


@app.route("/jury")
def jury_page():
    return render_template("jury.html")


@app.route("/story")
def story_page():
    return render_template("story.html")


@app.route("/host")
def host_page():
    return render_template("host.html", app_mode=APP_MODE)


@app.route("/api/host/history")
def api_host_history():
    import host_ai
    return jsonify({"ok": True, "history": host_ai.load_history()})


@app.route("/api/host/disable", methods=["POST"])
def api_host_disable():
    import host_ai
    host_ai.set_host_disabled(True)
    return jsonify({"ok": True})


@app.route("/api/host/status")
def api_host_status():
    import host_ai
    return jsonify({"disabled": host_ai.is_host_disabled()})


# ══════════════════════════════════════════════════════════════════════════════
# ██  叙事面板 API
# ══════════════════════════════════════════════════════════════════════════════

@app.route("/api/story/state")
def api_story_state():
    """Return current story state for the narrative panel."""
    from game.engine import get_story_state
    return jsonify(get_story_state())


@app.route("/api/story/rerun", methods=["POST"])
def api_story_rerun():
    """Re-generate the last story turn."""
    from game.engine import rerun_turn
    result = rerun_turn()
    return jsonify(result), 200 if result.get("ok") else 500


@app.route("/api/story/use-card", methods=["POST"])
def api_story_use_card():
    """Use an intervention or destiny card."""
    from game.engine import use_card
    data = request.get_json() or {}
    card_type = data.get("type", "")
    zone = data.get("zone", "")
    event_text = data.get("event_text", "")
    result = use_card(card_type, zone, event_text)
    return jsonify(result), 200 if result.get("ok") else 400


@app.route("/api/story/disable", methods=["POST"])
def api_story_disable():
    """本局关闭故事生成（仅 reset 可恢复）。"""
    from game.engine import set_story_disabled
    set_story_disabled(True)
    return jsonify({"ok": True})


# ── HTML / CSS / JS → 已拆分到独立文件 ─────────────────────────────────────
# templates/dashboard.html  — HTML 结构
# static/dashboard.css      — 样式
# static/dashboard.js       — 交互逻辑


# ── 首次启动向导 ─────────────────────────────────────────────────────────────

def _needs_setup() -> bool:
    """检测是否需要首次设置（api_config.json 不存在或缺少 key）。"""
    cfg_path = DATA_ROOT / "api_config.json"
    if not cfg_path.exists():
        return True
    try:
        cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
        return not cfg.get("gemini_api_key", "").strip()
    except Exception:
        return True


@app.before_request
def check_setup():
    """如果尚未完成初始配置 → 重定向到 /setup。"""
    if _needs_setup():
        # 放行 setup 相关路由和静态资源
        allowed = ("/setup", "/api/setup-config", "/static/")
        if not any(request.path.startswith(p) for p in allowed):
            return redirect("/setup")


@app.route("/setup")
def setup_page():
    """首次启动向导页面。"""
    if not _needs_setup():
        return redirect("/")
    return render_template("setup.html")


@app.route("/api/setup-config", methods=["POST"])
def api_setup_config():
    """保存首次配置（API Key + 运行模式）。"""
    global APP_MODE
    data = request.get_json()
    api_key = (data.get("api_key") or "").strip()
    app_mode = data.get("app_mode", "sandbox").strip()

    if not api_key:
        return jsonify({"ok": False, "error": "API Key 不能为空"}), 400

    cfg_path = DATA_ROOT / "api_config.json"
    # 读取现有配置（如果有），保留其他字段
    existing = {}
    if cfg_path.exists():
        try:
            existing = json.loads(cfg_path.read_text(encoding="utf-8"))
        except Exception:
            pass

    existing["gemini_api_key"] = api_key
    # 设置默认模型（如果没有）
    existing.setdefault("gemini_model", "gemini-2.5-flash-preview-05-20")
    existing.setdefault("gemini_model_lite", "gemini-2.0-flash")
    existing.setdefault("target_urls", ["gemini.google.com", "aistudio"])

    cfg_path.write_text(
        json.dumps(existing, ensure_ascii=False, indent=4),
        encoding="utf-8",
    )

    # 运行时更新 APP_MODE
    import config as _cfg_mod
    _cfg_mod.APP_MODE = app_mode
    APP_MODE = app_mode
    os.environ["APP_MODE"] = app_mode

    return jsonify({"ok": True})


# ── entry point ──────────────────────────────────────────────────────────────

if __name__ == "__main__":
    port = 5050
    print(f"🍅 Dashboard 启动中...")
    print(f"   请在浏览器打开 http://localhost:{port}")
    print(f"   按 Ctrl+C 停止\n")
    # 打包模式下自动打开浏览器
    if FROZEN:
        import webbrowser
        threading.Timer(1.0, lambda: webbrowser.open(f"http://localhost:{port}")).start()
    app.run(host="127.0.0.1", port=port, debug=False)

