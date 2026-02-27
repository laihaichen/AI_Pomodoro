#!/usr/bin/env python3
"""dashboard.py — local web dashboard for the learning tracker.

Usage:
    python3 /Users/haichenlai/Desktop/Prompt/dashboard.py
    then open http://localhost:5050 in a browser.

Auto-refreshes every 5 seconds via AJAX polling.
"""
from __future__ import annotations

import json
import sqlite3
import subprocess
import sys
from datetime import datetime, timezone

sys.path.insert(0, "/Users/haichenlai/Desktop/Prompt")
from config import (  # noqa: E402
    CURR_TS_FILE, PREV_TS_FILE, FIRST_TS_FILE,
    PAUSE_TS_FILE, CONT_TS_FILE,
    PENALIZED_REST_FILE, H_FILE,
    DB_FILE, SNIPPETS,
)

from flask import Flask, jsonify, render_template_string, request

app = Flask(__name__)

# ── Boss战触发文本（模块级常量，供 collect_state 与 api_setup 共享）────────────
_BOSSFIGHT_ACTIVE_TEXT = """\
当前已经达到boss战节点，请AI根据游戏规则出题。

【boss战阶段规则回忆】

硬核难度：额外胜利条件 — Boss战

当距离完成当日目标还剩1条学习记录时自动触发Boss战
出题节点：在倒数第二条用户prompt对应的AI输出末尾，根据当日学习内容生成一题综合考核题
回答配额：玩家仅有1次回答机会（最后一条prompt）
作答方式：玩家必须将答案手写在白板上（白板手撕），并将白板上的手写答案拍照提交给AI进行审核
断网要求：玩家在开始回答的那一刻必须完全脱离任何互联网，不能从任何外部来源获取答案
唯一的例外：玩家允许查看学习时间追踪系统的历史记录（之前所有回合的AI回复内容），但不能产生历史记录之外的任何新记录（即不能发送新的prompt或使用任何在线资源）
判定规则（No Mercy）：若玩家答对则通过；若答错或未在最后一条prompt内作答，立即判定Boss战失败→模拟人生游戏失败，没有第二次机会
休息禁止：Boss战期间禁止开启休息功能，玩家不能利用休息时间钻空子
括号例外机制限制：Boss战期间，括号例外机制被允许使用的唯一理由是向AI声明比赛规则；玩家不能通过括号例外机制询问关于题目本身的任何内容
继承关系：硬核难度需同时满足平衡难度的阶段性最低任务指标，即所有条件叠加

对AI出题者的要求：

1. 客观性原则：所出的Boss战题目必须有客观的正确答案和客观的错误答案，玩家的回答应该是明确的正确或明确的错误（对错模糊的主观题不适合作为Boss战题目）
2. 难度适中原则：题目既不能太简单（否则不符合Boss的挑战性），也不能太难（超出白板手撕的合理难度范围）
3. 不超纲原则：所出的Boss战题目必须是玩家当天学习内容的反映，如果玩家当天吃透了所学内容，应该能够合理地成功完成Boss战题目
4. 评分标准：出题时需同时说明客观的评分标准，以便判定答案的正确性\
"""

# ── snippet writer (for setup wizard) ────────────────────────────────────────

def write_snippet_value(key: str, value: str) -> None:
    """Write a snippet value to both Alfred SQLite DB and JSON backup file."""
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
        f"启动一个 {today} 的学习时间追踪系统，期望时长是 {hours} 小时",
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
    lines.append(f"\n今天的模拟人生游戏故事主题：{theme}")
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

    # ── Alfred snippets from SQLite ──────────────────────────────────────────
    snippet_keys = [
        "total_rest_time", "countcard", "interval", "fortunevalue",
        "current_prompt_count", "stage", "overtime_penalty_range",
        "offset", "difficulty", "max_rest_time", "violationcount",
        "hour3", "hour6", "hour9", "hour12", "bossfight_stage",
    ]
    try:
        with sqlite3.connect(DB_FILE) as con:
            for key in snippet_keys:
                snip = SNIPPETS[key]
                row = con.execute(
                    "SELECT snippet FROM snippets WHERE uid = ?", (snip.uid,)
                ).fetchone()
                state[key] = row[0] if row else "—"
    except Exception as exc:
        for key in snippet_keys:
            state.setdefault(key, "DB error")
        state["db_error"] = str(exc)

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
        state.get(current_key, _DEFAULT_MILESTONE) if current_key else None
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
        write_snippet_value("current_task", _task_to_write)
    except Exception:
        pass  # 写入失败不影响 Dashboard 展示

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
                write_snippet_value("bossfight_stage", _BOSSFIGHT_ACTIVE_TEXT)
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

    return state


# ── Flask routes ─────────────────────────────────────────────────────────────

@app.route("/api/state")
def api_state():
    return jsonify(collect_state())


@app.route("/api/next-pomodoro", methods=["POST"])
def api_next_pomodoro():
    script = (
        'tell application id "com.runningwithcrayons.Alfred" '
        'to run trigger "btn_next_pomodoro" '
        'in workflow "com.pomodoro.ai" '
        'with argument "test"'
    )
    try:
        subprocess.run(["osascript", "-e", script], check=True, timeout=5)
        return jsonify({"ok": True})
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)}), 500


@app.route("/api/stay-pomodoro", methods=["POST"])
def api_stay_pomodoro():
    script = (
        'tell application id "com.runningwithcrayons.Alfred" '
        'to run trigger "btn_stay" '
        'in workflow "com.pomodoro.ai" '
        'with argument "test"'
    )
    try:
        subprocess.run(["osascript", "-e", script], check=True, timeout=5)
        return jsonify({"ok": True})
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)}), 500


@app.route("/api/pause", methods=["POST"])
def api_pause():
    script = (
        'tell application id "com.runningwithcrayons.Alfred" '
        'to run trigger "btn_pause" '
        'in workflow "com.pomodoro.ai" '
        'with argument "test"'
    )
    try:
        subprocess.run(["osascript", "-e", script], check=True, timeout=5)
        return jsonify({"ok": True})
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)}), 500


@app.route("/api/continue", methods=["POST"])
def api_continue():
    script = (
        'tell application id "com.runningwithcrayons.Alfred" '
        'to run trigger "btn_continue" '
        'in workflow "com.pomodoro.ai" '
        'with argument "test"'
    )
    try:
        subprocess.run(["osascript", "-e", script], check=True, timeout=5)
        return jsonify({"ok": True})
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)}), 500


@app.route("/api/getcard", methods=["POST"])
def api_getcard():
    script = (
        'tell application id "com.runningwithcrayons.Alfred" '
        'to run trigger "btn_getcard" '
        'in workflow "com.pomodoro.ai" '
        'with argument "test"'
    )
    try:
        subprocess.run(["osascript", "-e", script], check=True, timeout=5)
        return jsonify({"ok": True})
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)}), 500


@app.route("/api/usecard", methods=["POST"])
def api_usecard():
    script = (
        'tell application id "com.runningwithcrayons.Alfred" '
        'to run trigger "btn_usecard" '
        'in workflow "com.pomodoro.ai" '
        'with argument "test"'
    )
    try:
        subprocess.run(["osascript", "-e", script], check=True, timeout=5)
        return jsonify({"ok": True})
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

        write_snippet_value("max_rest_time", max_rest)
        write_snippet_value("difficulty",    difficulty)

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
            write_snippet_value(key, default_milestone)

        # 再按学习时长写入用户填写的内容
        applicable_keys = [key for threshold, key in _MILESTONE_MAP if hours >= threshold]
        for key, text in zip(applicable_keys, milestones):
            if text:  # 跳过空字符串
                write_snippet_value(key, text)

        # ── Boss战节点初始化 ──────────────────────────────────────────────────
        if difficulty == "硬核难度":
            # 触发节点：倒数第2条prompt输出（即第 hours*6 - 1 条）
            bossfight_target = hours * 6 - 1
            write_snippet_value("bossfight_stage", f"等待Boss战节点（第{bossfight_target}条）")
        else:
            write_snippet_value("bossfight_stage", "当前难度不适用")

        prompt = generate_launch_prompt(hours, max_rest, difficulty, milestones, theme)
        return jsonify({"ok": True, "prompt": prompt})
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)}), 500


@app.route("/")
def index():
    return render_template_string(HTML)


# ── HTML / CSS / JS (single-file frontend) ───────────────────────────────────

HTML = r"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>学习追踪 Dashboard</title>
<style>
  * { box-sizing: border-box; margin: 0; padding: 0; }

  :root {
    --bg:      #111111;
    --surface: #1a1a1a;
    --border:  #2c2c2c;
    --text:    #e0e0e0;
    --dim:     #555555;
    --bright:  #ffffff;
  }

  body {
    background: var(--bg);
    color: var(--text);
    font-family: -apple-system, BlinkMacSystemFont, "SF Pro Text", "Helvetica Neue", sans-serif;
    min-height: 100vh;
    padding: 24px;
  }

  /* ── header ── */
  .header {
    display: flex; align-items: center;
    justify-content: space-between; margin-bottom: 28px;
  }
  .header-left { display: flex; align-items: center; gap: 16px; }
  .tomato { font-size: 48px; line-height: 1; }
  .title-block h1 { font-size: 20px; font-weight: 600; color: var(--text); }
  .title-block p  { font-size: 12px; color: var(--dim); margin-top: 3px; }
  .refresh-badge, .pomodoro-timer {
    font-size: 12px; color: var(--dim);
    background: var(--surface); border: 1px solid var(--border);
    border-radius: 20px; padding: 6px 14px;
  }

  /* ── section labels ── */
  .section-label {
    font-size: 10px; font-weight: 600; letter-spacing: 0.12em;
    color: var(--dim); text-transform: uppercase;
    margin: 22px 0 8px;
    border-bottom: 1px solid var(--border); padding-bottom: 6px;
  }

  /* ── grid ── */
  .grid { display: grid; gap: 10px; }
  .grid-2 { grid-template-columns: repeat(2, 1fr); }
  .grid-3 { grid-template-columns: repeat(3, 1fr); }
  .grid-4 { grid-template-columns: repeat(4, 1fr); }

  /* ── card ── */
  .card {
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: 10px;
    padding: 14px 16px;
  }
  /* all accent-* classes are now no-ops — same as .card */
  .card.accent-green, .card.accent-yellow, .card.accent-red,
  .card.accent-blue,  .card.accent-mauve,  .card.accent-peach,
  .card.accent-teal   { border: 1px solid var(--border); }

  .card-label {
    font-size: 10px; font-weight: 600; letter-spacing: 0.06em;
    color: var(--dim); text-transform: uppercase; margin-bottom: 8px;
  }
  .card-value {
    font-size: 24px; font-weight: 700; color: var(--text); line-height: 1.1;
  }
  .card-value.small {
    font-size: 13px; font-weight: 400; line-height: 1.6; word-break: break-word;
  }
  .card-sub { font-size: 11px; color: var(--dim); margin-top: 5px; }

  /* value states — monochrome only */
  .val-green  { color: var(--text)   !important; }
  .val-yellow { color: var(--text)   !important; }
  .val-red    { color: var(--bright) !important; font-weight: 700; }
  .val-blue   { color: var(--text)   !important; }
  .val-mauve  { color: var(--text)   !important; }
  .val-peach  { color: var(--text)   !important; }
  .val-teal   { color: var(--text)   !important; }

  /* hero card */
  .hero-card {
    background: var(--surface); border: 1px solid var(--border);
    border-radius: 12px; padding: 22px;
    display: flex; align-items: center; gap: 18px;
  }
  .hero-tomato { font-size: 40px; }
  .hero-count  { font-size: 60px; font-weight: 800; color: var(--bright); line-height: 1; }
  .hero-label  { font-size: 13px; color: var(--dim); margin-top: 4px; }
  .hero-right  { display: flex; flex-direction: column; gap: 4px; }

  /* action buttons */
  .next-pomodoro-btn {
    background: var(--border); border: 1px solid #3a3a3a;
    border-radius: 10px; color: var(--text);
    font-size: 12px; font-weight: 600;
    padding: 10px 12px; cursor: pointer; line-height: 1.5;
    text-align: center; transition: background 0.15s, color 0.15s;
    text-decoration: none; font-family: inherit;
    display: flex; align-items: center; justify-content: center;
    flex-direction: column;
  }
  .next-pomodoro-btn .btn-sub {
    font-weight: 400; font-size: 0.85em; opacity: 0.7; margin-top: 3px;
  }
  .next-pomodoro-btn:hover  { background: #333333; color: var(--bright); }
  .next-pomodoro-btn:active { background: #444444; }
  .next-pomodoro-btn:disabled { opacity: 0.5; cursor: not-allowed; }

  /* stage */
  .stage-card .card-value.small { font-size: 13px; white-space: pre-line; }
  .stage-ok { color: var(--dim)  !important; }
  .stage-na { color: var(--dim)  !important; }

  @media (max-width: 700px) {
    .grid-3, .grid-4 { grid-template-columns: repeat(2, 1fr); }
    .grid-2 { grid-template-columns: 1fr; }
  }

  /* ── setup button ── */
  .setup-btn {
    background: var(--border); border: 1px solid #3a3a3a;
    color: var(--text); border-radius: 20px;
    padding: 7px 16px; font-size: 12px; font-weight: 600;
    cursor: pointer; transition: background 0.15s; font-family: inherit;
  }
  .setup-btn:hover { background: #333333; color: var(--bright); }

  /* ── wizard modal ── */
  .modal-overlay {
    display: none; position: fixed; inset: 0;
    background: rgba(0,0,0,0.75); z-index: 100;
    align-items: center; justify-content: center;
  }
  .modal-overlay.open { display: flex; }
  .modal {
    background: var(--surface); border: 1px solid var(--border);
    border-radius: 16px; padding: 32px 36px;
    width: min(540px, 95vw); max-height: 90vh;
    overflow-y: auto; position: relative;
  }
  .modal-close {
    position: absolute; top: 14px; right: 18px;
    background: none; border: none; color: var(--dim);
    font-size: 18px; cursor: pointer;
  }
  .modal-close:hover { color: var(--text); }
  .wizard-progress { display: flex; gap: 5px; margin-bottom: 26px; }
  .wizard-dot {
    height: 3px; border-radius: 2px; flex: 1;
    background: var(--border); transition: background 0.3s;
  }
  .wizard-dot.done   { background: var(--dim); }
  .wizard-dot.active { background: var(--text); }
  .wizard-step-title {
    font-size: 10px; font-weight: 600; letter-spacing: 0.1em;
    color: var(--dim); text-transform: uppercase; margin-bottom: 6px;
  }
  .wizard-step-heading {
    font-size: 18px; font-weight: 700; color: var(--text); margin-bottom: 6px;
  }
  .wizard-step-hint {
    font-size: 13px; color: var(--dim); margin-bottom: 18px; line-height: 1.6;
  }
  .wizard-input {
    width: 100%; background: var(--bg); border: 1px solid var(--border);
    border-radius: 8px; color: var(--text); font-size: 15px;
    padding: 11px 14px; outline: none; transition: border-color 0.2s;
    font-family: inherit;
  }
  .wizard-input:focus { border-color: var(--dim); }
  .wizard-input.error { border-color: var(--text); }
  .wizard-select {
    width: 100%; background: var(--bg); border: 1px solid var(--border);
    border-radius: 8px; color: var(--text); font-size: 15px;
    padding: 11px 14px; outline: none; appearance: none;
    cursor: pointer; font-family: inherit;
  }
  .wizard-select:focus { border-color: var(--dim); }
  .wizard-textarea {
    width: 100%; background: var(--bg); border: 1px solid var(--border);
    border-radius: 8px; color: var(--text); font-size: 13px;
    padding: 11px 14px; outline: none; resize: vertical; min-height: 80px;
    font-family: inherit; line-height: 1.6;
  }
  .wizard-textarea:focus { border-color: var(--dim); }
  .wizard-error { color: var(--text); font-size: 12px; margin-top: 6px; min-height: 18px; }
  .wizard-btns {
    display: flex; gap: 10px; margin-top: 22px; justify-content: flex-end;
  }
  .btn-prev {
    background: none; border: 1px solid var(--border);
    color: var(--dim); border-radius: 8px; padding: 9px 20px;
    font-size: 13px; cursor: pointer; font-family: inherit;
  }
  .btn-prev:hover { border-color: var(--text); color: var(--text); }
  .btn-next {
    background: var(--text); border: none; color: var(--bg);
    border-radius: 8px; padding: 9px 26px;
    font-size: 13px; font-weight: 700; cursor: pointer;
    font-family: inherit; transition: opacity 0.15s;
  }
  .btn-next:hover { opacity: 0.85; }
  .btn-copy {
    background: var(--text); border: none; color: var(--bg);
    border-radius: 8px; padding: 9px 22px;
    font-size: 13px; font-weight: 700; cursor: pointer;
    font-family: inherit; transition: opacity 0.15s;
  }
  .btn-copy:hover { opacity: 0.85; }
  .prompt-result {
    width: 100%; background: var(--bg); border: 1px solid var(--border);
    border-radius: 8px; color: var(--text);
    font-size: 12px; padding: 12px 14px;
    font-family: "SF Mono", "Menlo", monospace;
    line-height: 1.7; resize: none; min-height: 200px; outline: none;
  }
  .copy-success { color: var(--text); font-size: 12px; margin-top: 8px; min-height: 20px; }
</style>
</head>
<body>

<div class="header">
  <div class="header-left">
    <div class="tomato">🍅</div>
    <div class="title-block">
      <h1>学习追踪 Dashboard</h1>
      <p>实时读取 Alfred Snippets &amp; 本地数据文件</p>
    </div>
  </div>
  <div style="display:flex;align-items:center;gap:12px;">
    <button class="setup-btn" onclick="openWizard()">设置初始化 Prompt</button>
    <div class="pomodoro-timer">本次番茄钟计时：<span id="tomato-timer" style="font-weight:700;color:var(--bright); font-variant-numeric: tabular-nums;">0秒</span></div>
    <div class="refresh-badge">每 5 秒刷新 · 上次更新：<span id="last-update">—</span></div>
  </div>
</div>

<!-- ── 番茄钟进度 ── -->
<div class="section-label">番茄钟进度</div>
<div class="hero-card" id="hero-card">
  <div class="hero-tomato" style="font-size:32px; color:var(--dim);">#</div>
  <div>
    <div class="hero-count" id="val-current_prompt_count">—</div>
    <div class="hero-label">当前第几条番茄钟记录</div>
  </div>
  <div style="display:flex;gap:8px;align-items:stretch;margin-left:16px;flex:1;">
    <button class="next-pomodoro-btn" style="flex:2;min-width:130px;"
            onclick="triggerNextPomodoro(this)"
            title="执行 AppleScript：btn_next_pomodoro">
      <span>推进番茄钟记录<br>并向AI发送学习进度</span>
      <span class="btn-sub">（请记得剪切板上有内容）</span>
    </button>
    <button class="next-pomodoro-btn" style="flex:2;min-width:130px;"
            onclick="triggerStayPomodoro(this)"
            title="执行 AppleScript：btn_stay">
      <span>不推进番茄钟记录<br>并向AI发送学习进度</span>
      <span class="btn-sub">（请记得剪切板上有内容）</span>
    </button>
    <button class="next-pomodoro-btn" style="flex:1;min-width:80px;"
            onclick="triggerPause(this)"
            title="执行 AppleScript：btn_pause">
      进入休息时间
    </button>
    <button class="next-pomodoro-btn" style="flex:1;min-width:80px;"
            onclick="triggerContinue(this)"
            title="执行 AppleScript：btn_continue">
      从休息时间恢复
    </button>
    <button class="next-pomodoro-btn" style="flex:1;min-width:80px;"
            onclick="triggerGetCard(this)"
            title="执行 AppleScript：btn_getcard">
      获得一张宿命卡
    </button>
    <button class="next-pomodoro-btn" style="flex:1;min-width:80px;"
            onclick="triggerUseCard(this)"
            title="执行 AppleScript：btn_usecard">
      <span>使用一张宿命卡</span>
      <span class="btn-sub">（请将想锁定的区间复制到剪切板）</span>
    </button>
  </div>
  <div class="hero-right" style="margin-left:auto; text-align:right;">
    <div style="font-size:12px;color:var(--dim);">当前难度</div>
    <div id="val-difficulty" style="font-size:18px;font-weight:700;color:var(--text);">—</div>
  </div>
</div>

<!-- ── 时间戳 ── -->
<div class="section-label">时间戳</div>
<div class="grid grid-4">
  <div class="card accent-blue">
    <div class="card-label">当前时间戳</div>
    <div class="card-value" id="val-curr_ts" style="font-size:20px;">—</div>
    <div class="card-sub">curr_timestamp.txt</div>
  </div>
  <div class="card accent-blue">
    <div class="card-label">上一次时间戳</div>
    <div class="card-value" id="val-prev_ts" style="font-size:20px;">—</div>
    <div class="card-sub">prev_timestamp.txt</div>
  </div>
  <div class="card accent-teal">
    <div class="card-label">今日开始时间</div>
    <div class="card-value" id="val-first_ts" style="font-size:20px;">—</div>
    <div class="card-sub">first_timestamp.txt</div>
  </div>
  <div class="card accent-teal">
    <div class="card-label">已学习时长</div>
    <div class="card-value" id="val-elapsed_minutes" style="font-size:20px;">—</div>
    <div class="card-sub">分钟（curr - first）</div>
  </div>
</div>

<!-- ── 时间间隔 & 吉凶 ── -->
<div class="section-label">本轮区间</div>
<div class="grid grid-3">
  <div class="card accent-peach">
    <div class="card-label">当前时间间隔</div>
    <div class="card-value" id="val-interval">—</div>
    <div class="card-sub">分钟（&gt;15 min → 凶）</div>
  </div>
  <div class="card">
    <div class="card-label">是否超时？（吉凶值）</div>
    <div class="card-value small" id="val-fortunevalue">—</div>
  </div>
  <div class="card">
    <div class="card-label">时间偏移量</div>
    <div class="card-value" id="val-offset">—</div>
    <div class="card-sub">偏移量 &gt; 60 → 判负</div>
  </div>
</div>

<!-- ── 休息 ── -->
<div class="section-label">休息状态</div>
<div class="grid grid-3">
  <div class="card accent-green">
    <div class="card-label">最大允许休息时间</div>
    <div class="card-value" id="val-max_rest_time">—</div>
    <div class="card-sub">分钟（-max_rest_time snippet）</div>
  </div>
  <div class="card accent-green">
    <div class="card-label">今日累计休息时间</div>
    <div class="card-value" id="val-total_rest_time">—</div>
    <div class="card-sub">分钟（-total_rest_time snippet）</div>
  </div>
  <div class="card" id="card-last-rest">
    <div class="card-label">最近休息操作</div>
    <div class="card-value small" id="val-last_rest_action">—</div>
  </div>
</div>

<!-- ── 惩罚 ── -->
<div class="section-label">超时惩罚</div>
<div class="grid grid-3">
  <div class="card accent-red">
    <div class="card-label">累计超时惩罚 H</div>
    <div class="card-value" id="val-h_value">—</div>
    <div class="card-sub">分钟（h_value.txt）</div>
  </div>
  <div class="card accent-red">
    <div class="card-label">超时惩罚随机数范围</div>
    <div class="card-value small" id="val-overtime_penalty_range">—</div>
    <div class="card-sub">-overtime-penalty-range</div>
  </div>
  <div class="card accent-mauve">
    <div class="card-label">宿命卡数量</div>
    <div class="card-value" id="val-countcard">—</div>
    <div class="card-sub">-countcard snippet</div>
  </div>
</div>

<!-- ── 阶段性节点 ── -->
<div class="section-label">阶段性节点 &amp; 游戏状态</div>
<div class="grid grid-2" style="margin-bottom:10px;">
  <div class="card" id="card-milestones-set">
    <div class="card-label">今日里程碑任务总览</div>
    <div id="val-milestones-set" class="card-value small" style="line-height:2;">—</div>
  </div>
  <div class="card" id="card-current-milestone">
    <div class="card-label">当前阶段任务</div>
    <div id="val-current-milestone-label" style="font-size:10px;color:var(--dim);margin-bottom:4px;"></div>
    <div id="val-current-milestone-text" class="card-value small">—</div>
  </div>
</div>
<div class="grid grid-2">
  <div class="card stage-card">
    <div class="card-label">当前阶段性节点状态</div>
    <div class="card-value small" id="val-stage">—</div>
  </div>
  <div class="card accent-mauve">
    <div class="card-label">违规次数</div>
    <div class="card-value" id="val-violationcount">—</div>
    <div class="card-sub">-violationcount snippet</div>
  </div>
</div>
<div class="grid grid-2" style="margin-top:10px;">
  <div class="card" id="card-bossfight">
    <div class="card-label">⚔️ Boss战节点状态</div>
    <div class="card-value small" id="val-bossfight_stage">—</div>
    <div class="card-sub">-bossfight-stage snippet</div>
  </div>
</div>


<!-- ── Setup Wizard Modal ── -->
<div class="modal-overlay" id="wizard-overlay">
  <div class="modal">
    <button class="modal-close" onclick="closeWizard()">✕</button>
    <div class="wizard-progress" id="wizard-progress"></div>
    <div id="wizard-body"></div>
  </div>
</div>

<script>
// ── Wizard state ────────────────────────────────────────────────────────────
let wData = {};      // collected answers
let wSteps = [];     // built after hours is known
let wCurrent = 0;    // current step index

const MILESTONE_DEFS = [
  { range: "0 ~ 3小时",   record: "第18条记录", hours: 3  },
  { range: "3 ~ 6小时",   record: "第36条记录", hours: 6  },
  { range: "6 ~ 9小时",   record: "第54条记录", hours: 9  },
  { range: "9 ~ 12小时",  record: "第72条记录", hours: 12 },
];

// difficulty === "" 表示尚未选择（向导第一次构建时，不插入里程碑）
function buildSteps(hours, difficulty) {
  const steps = [];
  const needMilestones = difficulty && difficulty !== "探索者难度";
  const milestoneCount = MILESTONE_DEFS.filter(m => hours >= m.hours).length;

  // Step 0: hours
  steps.push({ id: "hours", type: "number",
    title: "计划学习时长", heading: "今天计划学习几小时？",
    hint: "请输入 1 ~ 14 之间的整数。",
    min: 1, max: 14, placeholder: "例：9",
  });

  // Step 1: difficulty（移到最前，决定是否需要里程碑步骤）
  steps.push({ id: "difficulty", type: "select",
    title: "游戏难度", heading: "请选择今天的游戏难度",
    hint: "硬核 / 平衡难度需要设置阶段性最低指标；探索者难度跳过此步骤。",
    options: ["硬核难度", "平衡难度", "探索者难度"],
  });

  // 里程碑步骤 — 仅当难度为硬核或平衡，且学习时长已知时插入
  if (needMilestones) {
    MILESTONE_DEFS.forEach((m, i) => {
      if (hours >= m.hours) {
        steps.push({ id: `milestone_${i}`, type: "text",
          title: `阶段目标 ${i+1} / ${milestoneCount}`,
          heading: `${m.range} 阶段最低完成指标`,
          hint: `${m.range}（${m.record}）达到时，你希望完成什么任务？`,
          placeholder: "例：完成 3 道算法题",
        });
      }
    });
  }

  // 最长休息时间
  steps.push({ id: "max_rest", type: "number",
    title: "休息设置", heading: "今天允许的最长休息时间",
    hint: "单位：分钟。",
    min: 1, max: 300, placeholder: "例：120",
  });

  // 故事主题
  steps.push({ id: "theme", type: "textarea",
    title: "故事主题", heading: "今天的模拟人生故事主题",
    hint: "描述你希望 AI 为今天的学习旅程设定的故事背景与主角。",
    placeholder: '例：主人公是一个降生在 “KK诈骗园区” 的1岁婴儿，并且被一群诈骗犯养大。',
    required: false,
  });

  // 结果页
  steps.push({ id: "result", type: "result",
    title: "初始化完成", heading: "你的初始化 Prompt 已生成",
    hint: "以下内容已自动写入 -max_rest_time 与 -difficulty。请将 Prompt 复制给 AI 聊天工具开始今天的学习。",
  });

  return steps;
}

// ── Modal open/close ────────────────────────────────────────────────────────
function openWizard() {
  wData = {};
  wCurrent = 0;
  wSteps = buildSteps(0, ""); // hours=0, difficulty="" → 无里程碑，直到两者都已知
  document.getElementById("wizard-overlay").classList.add("open");
  renderStep();
}
function closeWizard() {
  document.getElementById("wizard-overlay").classList.remove("open");
}
document.getElementById("wizard-overlay").addEventListener("click", e => {
  if (e.target === e.currentTarget) closeWizard();
});

// ── Render current step ──────────────────────────────────────────────────────
function renderProgress() {
  const prog = document.getElementById("wizard-progress");
  prog.innerHTML = wSteps.map((_, i) => {
    let cls = "wizard-dot";
    if (i < wCurrent) cls += " done";
    else if (i === wCurrent) cls += " active";
    return `<div class="${cls}"></div>`;
  }).join("");
}

function renderStep() {
  renderProgress();
  const step = wSteps[wCurrent];
  const body = document.getElementById("wizard-body");
  const isLast = wCurrent === wSteps.length - 1;
  const isFirst = wCurrent === 0;
  const savedVal = wData[step.id] ?? "";

  let inputHTML = "";
  if (step.type === "number") {
    inputHTML = `<input id="w-input" class="wizard-input" type="number"
      min="${step.min}" max="${step.max}" placeholder="${step.placeholder}"
      value="${savedVal}" />`;
  } else if (step.type === "text") {
    inputHTML = `<input id="w-input" class="wizard-input" type="text"
      placeholder="${step.placeholder}" value="${savedVal}" />`;
  } else if (step.type === "select") {
    const opts = step.options.map(o =>
      `<option value="${o}" ${o === savedVal ? "selected" : ""}>${o}</option>`
    ).join("");
    inputHTML = `<select id="w-input" class="wizard-select">${opts}</select>`;
  } else if (step.type === "textarea") {
    inputHTML = `<textarea id="w-input" class="wizard-textarea"
      placeholder="${step.placeholder}">${savedVal}</textarea>`;
  } else if (step.type === "result") {
    inputHTML = `<textarea id="w-result" class="prompt-result" readonly></textarea>
      <div class="copy-success" id="copy-msg"></div>`;
  }

  const prevBtn = isFirst ? "" :
    `<button class="btn-prev" onclick="wizardPrev()">← 上一步</button>`;

  let nextBtn = "";
  if (step.type === "result") {
    nextBtn = `<button class="btn-copy" onclick="copyPrompt()">📋 复制 Prompt</button>`;
  } else {
    nextBtn = `<button class="btn-next" onclick="wizardNext()">
      ${isLast ? "完成" : "下一步 →"}</button>`;
  }

  body.innerHTML = `
    <div class="wizard-step-title">步骤 ${wCurrent + 1} / ${wSteps.length}</div>
    <div class="wizard-step-heading">${step.heading}</div>
    <div class="wizard-step-hint">${step.hint}</div>
    ${inputHTML}
    <div class="wizard-error" id="w-error"></div>
    <div class="wizard-btns">${prevBtn}${nextBtn}</div>
  `;

  // If result step, fetch prompt from backend
  if (step.type === "result") {
    submitSetup();
  }

  // Auto-focus input
  const inp = document.getElementById("w-input");
  if (inp) { inp.focus(); inp.addEventListener("keydown", e => { if (e.key === "Enter" && step.type !== "textarea") wizardNext(); }); }
}

// ── Validate and advance ────────────────────────────────────────────────────
function wizardNext() {
  const step = wSteps[wCurrent];
  const errEl = document.getElementById("w-error");
  errEl.textContent = "";

  if (step.type === "number") {
    const inp = document.getElementById("w-input");
    const val = parseInt(inp.value);
    if (isNaN(val) || val < step.min || val > step.max) {
      inp.classList.add("error");
      errEl.textContent = `请输入 ${step.min} ~ ${step.max} 之间的整数。`;
      return;
    }
    inp.classList.remove("error");
    wData[step.id] = val;
    // hours 确定后重建步骤（difficulty 此时可能已知或未知）
    if (step.id === "hours") {
      wSteps = buildSteps(val, wData.difficulty || "");
    }
  } else if (step.type === "text") {
    const inp = document.getElementById("w-input");
    const val = inp.value.trim();
    if (!val) {
      inp.classList.add("error");
      errEl.textContent = "请输入内容。";
      return;
    }
    inp.classList.remove("error");
    wData[step.id] = val;
  } else if (step.type === "select") {
    const val = document.getElementById("w-input").value;
    wData[step.id] = val;
    // difficulty 确定后重建步骤，动态决定是否插入里程碑步骤
    if (step.id === "difficulty") {
      wSteps = buildSteps(wData.hours || 0, val);
    }
  } else if (step.type === "textarea") {
    wData[step.id] = (document.getElementById("w-input").value || "").trim();
  }

  wCurrent++;
  renderStep();
}

function wizardPrev() {
  wCurrent--;
  renderStep();
}

// ── Submit to backend ────────────────────────────────────────────────────────
function submitSetup() {
  const milestones = [];
  wSteps.forEach(s => {
    if (s.id.startsWith("milestone_")) milestones.push(wData[s.id] || "");
  });

  fetch("/api/setup", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      hours:      wData.hours,
      max_rest:   wData.max_rest,
      difficulty: wData.difficulty,
      milestones: milestones,
      theme:      wData.theme || "",
    }),
  })
  .then(r => r.json())
  .then(d => {
    if (d.ok) {
      document.getElementById("w-result").value = d.prompt;
    } else {
      document.getElementById("w-result").value = "生成失败：" + d.error;
    }
  })
  .catch(err => {
    document.getElementById("w-result").value = "网络错误：" + err;
  });
}

function copyPrompt() {
  const text = document.getElementById("w-result").value;
  navigator.clipboard.writeText(text).then(() => {
    const msg = document.getElementById("copy-msg");
    msg.textContent = "✅ 已复制到剪贴板！";
    setTimeout(() => { msg.textContent = ""; }, 3000);
  });
}

// ── Alfred triggers ──────────────────────────────────────────────────────────
function _alfredTrigger(btn, endpoint) {
  const orig = btn.innerHTML;
  btn.disabled = true;
  btn.innerHTML = "⏳ 发送中...";
  fetch(endpoint, { method: "POST" })
    .then(r => r.json())
    .then(d => {
      btn.innerHTML = d.ok ? "✅ 已发送！" : "❌ 失败：" + d.error;
      setTimeout(() => { btn.innerHTML = orig; btn.disabled = false; }, 2500);
    })
    .catch(() => {
      btn.innerHTML = "❌ 网络错误";
      setTimeout(() => { btn.innerHTML = orig; btn.disabled = false; }, 2500);
    });
}

function triggerNextPomodoro(btn) { _alfredTrigger(btn, "/api/next-pomodoro"); }
function triggerStayPomodoro(btn)  { _alfredTrigger(btn, "/api/stay-pomodoro"); }
function triggerPause(btn)         { _alfredTrigger(btn, "/api/pause"); }
function triggerContinue(btn)      { _alfredTrigger(btn, "/api/continue"); }
function triggerGetCard(btn)       { _alfredTrigger(btn, "/api/getcard"); }
function triggerUseCard(btn)       { _alfredTrigger(btn, "/api/usecard"); }

// ── Dashboard data refresh ───────────────────────────────────────────────────
const REFRESH_MS = 5000;
let countdown = REFRESH_MS / 1000;
let currTsRaw = null; // Store ISO string for the timer

function setVal(id, text) {
  const el = document.getElementById(id);
  if (el) el.textContent = text ?? "—";
}

function applyClass(id, cls) {
  const el = document.getElementById(id);
  if (!el) return;
  el.className = el.className.replace(/\bval-\w+/g, "");
  if (cls) el.classList.add(cls);
}

function refreshData() {
  fetch("/api/state")
    .then(r => r.json())
    .then(d => {
      // timestamps
      currTsRaw = d.curr_ts_raw;
      setVal("val-curr_ts",  d.curr_ts);
      setVal("val-prev_ts",  d.prev_ts);
      setVal("val-first_ts", d.first_ts);

      // elapsed
      if (d.elapsed_minutes !== null && d.elapsed_minutes !== undefined) {
        const h = Math.floor(d.elapsed_minutes / 60);
        const m = Math.round(d.elapsed_minutes % 60);
        setVal("val-elapsed_minutes", h > 0 ? `${h}h ${m}m` : `${m} 分钟`);
      } else {
        setVal("val-elapsed_minutes", "—");
      }

      // prompt count
      setVal("val-current_prompt_count", d.current_prompt_count);

      // difficulty
      setVal("val-difficulty", d.difficulty);

      // interval — color by >15
      const ivl = parseFloat(d.interval);
      setVal("val-interval", isNaN(ivl) ? d.interval : ivl.toFixed(1) + " 分钟");
      const ivlCard = document.querySelector(".card.accent-peach");
      if (!isNaN(ivl)) {
        applyClass("val-interval", ivl > 15 ? "val-red" : "val-green");
      }

      // fortune
      const fortune = d.fortunevalue || "";
      setVal("val-fortunevalue", fortune);
      applyClass("val-fortunevalue",
        fortune.includes("凶") ? "val-red" : fortune.includes("合规") ? "val-green" : null
      );

      // offset — color by >60
      const off = parseFloat(d.offset);
      setVal("val-offset", isNaN(off) ? d.offset : off.toFixed(1));
      applyClass("val-offset",
        isNaN(off) ? null : off > 60 ? "val-red" : off > 40 ? "val-yellow" : "val-green"
      );

      // rest
      setVal("val-max_rest_time",    d.max_rest_time);
      setVal("val-total_rest_time",  d.total_rest_time);

      // last rest action — colour by pause/continue state
      setVal("val-last_rest_action", d.last_rest_action);
      const restCard = document.getElementById("card-last-rest");
      if (restCard) {
        restCard.className = "card " + (d.last_rest_is_paused ? "accent-yellow" : "accent-green");
      }
      applyClass("val-last_rest_action", d.last_rest_is_paused ? "val-yellow" : "val-green");

      // penalty
      const hv = parseFloat(d.h_value);
      setVal("val-h_value", isNaN(hv) ? d.h_value : hv.toFixed(1) + " 分钟");
      applyClass("val-h_value", !isNaN(hv) && hv > 0 ? "val-red" : "val-green");

      setVal("val-overtime_penalty_range", d.overtime_penalty_range);
      applyClass("val-overtime_penalty_range",
        d.overtime_penalty_range === "{random:0..0}" ? "val-green" : "val-yellow"
      );

      // cards
      setVal("val-countcard",      d.countcard);
      setVal("val-violationcount", d.violationcount);
      applyClass("val-violationcount",
        parseInt(d.violationcount) > 0 ? "val-red" : "val-green"
      );

      // milestones overview — 今日里程碑任务总览（非默认值的组）
      const msEl = document.getElementById("val-milestones-set");
      if (msEl) {
        const set = d.milestones_set || [];
        if (set.length === 0) {
          msEl.textContent = "暂无已设置的阶段性任务";
          msEl.style.color = "var(--dim)";
        } else {
          msEl.innerHTML = set.map(m =>
            `<span style="display:block;">
              <span style="color:var(--dim);font-size:10px;">${m.label}</span>
              &nbsp;${m.text}
            </span>`
          ).join("");
          msEl.style.color = "";
        }
      }

      // current milestone — 当前阶段任务
      const cmLabel = document.getElementById("val-current-milestone-label");
      const cmText  = document.getElementById("val-current-milestone-text");
      const keyLabelMap = { hour3:"0~3小时", hour6:"3~6小时", hour9:"6~9小时", hour12:"9~12小时" };
      if (cmLabel && cmText) {
        if (d.current_milestone_key && d.current_milestone_text) {
          cmLabel.textContent = keyLabelMap[d.current_milestone_key] || d.current_milestone_key;
          cmText.textContent  = d.current_milestone_text;
          cmText.className    = "card-value small val-green";
        } else {
          cmLabel.textContent = "";
          cmText.textContent  = "番茄钟尚未开始";
          cmText.className    = "card-value small";
          cmText.style.color  = "var(--dim)";
        }
      }

      // stage
      const stage = d.stage || "";
      const stageEl = document.getElementById("val-stage");
      if (stageEl) {
        stageEl.textContent = stage;
        stageEl.className = "card-value small";
        if (stage.includes("达到阶段性节点") && !stage.includes("没有")) {
          stageEl.classList.add("val-yellow");
        } else if (stage.includes("没有")) {
          stageEl.classList.add("stage-ok");
        } else if (stage.includes("不适用")) {
          stageEl.classList.add("stage-na");
        }
      }

      // bossfight stage
      const bfs     = d.bossfight_stage || "";
      const bfsEl   = document.getElementById("val-bossfight_stage");
      const bfsCard = document.getElementById("card-bossfight");
      if (bfsEl) {
        bfsEl.textContent   = bfs;
        bfsEl.className     = "card-value small";
        bfsEl.style.color   = "";
        if (bfsCard) bfsCard.style.borderColor = "";
        if (bfs.includes("已经达到boss战节点")) {
          bfsEl.classList.add("val-red");
          if (bfsCard) bfsCard.style.borderColor = "rgba(255,80,80,0.6)";
        } else if (bfs.includes("不适用")) {
          bfsEl.style.color = "var(--dim)";
        } else if (bfs.includes("等待")) {
          bfsEl.classList.add("val-green");
        }
      }

      // update time
      document.getElementById("last-update").textContent =
        new Date().toLocaleTimeString("zh-CN");
      countdown = REFRESH_MS / 1000;
    })
    .catch(err => {
      document.getElementById("last-update").textContent = "读取失败";
    });
}

// countdown display and tomato timer
setInterval(() => {
  countdown = Math.max(0, countdown - 1);
  
  if (currTsRaw) {
    const startDt = new Date(currTsRaw);
    const nowDt = new Date();
    const diffSecs = Math.floor((nowDt - startDt) / 1000);
    
    const timerEl = document.getElementById("tomato-timer");
    if (diffSecs >= 0 && timerEl) {
      if (diffSecs < 60) {
        timerEl.textContent = `${diffSecs}秒`;
      } else {
        const m = Math.floor(diffSecs / 60);
        const s = diffSecs % 60;
        timerEl.textContent = `${m}分钟${s}秒`;
      }
    }
  }
}, 1000);

// data refresh
refreshData();
setInterval(refreshData, REFRESH_MS);
</script>
</body>
</html>
"""

# ── entry point ──────────────────────────────────────────────────────────────

if __name__ == "__main__":
    port = 5050
    print(f"🍅 Dashboard 启动中...")
    print(f"   请在浏览器打开 http://localhost:{port}")
    print(f"   按 Ctrl+C 停止\n")
    app.run(host="127.0.0.1", port=port, debug=False)
