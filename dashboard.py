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
    DB_FILE, SNIPPETS, MILESTONE_GOALS_FILE,
    HEALTH_FILE, FINAL_FATE_FILE, BOSS_DEFEATED_FILE,
    BASE,
)

from flask import Flask, jsonify, render_template, request

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


def update_total_score(delta: int = 0, factor: float = 1.0) -> int:
    """Read -total-score, add delta, multiply by factor, write back. Returns new value."""
    snip = SNIPPETS["total_score"]
    with sqlite3.connect(DB_FILE) as con:
        row = con.execute("SELECT snippet FROM snippets WHERE uid = ?", (snip.uid,)).fetchone()
    try:
        current = int(row[0]) if row else 0
    except (ValueError, TypeError):
        current = 0
    new_val = round((current + delta) * factor)
    write_snippet_value("total_score", str(new_val))
    return new_val


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
        "total_rest_time", "countcard", "interval", "is_time_within_limit",
        "current_prompt_count", "stage", "overtime_penalty_random_num",
        "offset", "difficulty", "max_rest_time", "violationcount",
        "hour3", "hour6", "hour9", "hour12", "bossfight_stage",
        "random_num", "foretold", "total_count", "is_victory", "total_score",
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
        write_snippet_value("current_task", _task_to_write)
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
        _denominator = int(_goals.get(_goal_key, 0))
        # 读取当前 snippet 值，解析分子（格式：「N/M ...」）
        _cur_indicator = ""
        with sqlite3.connect(DB_FILE) as _con:
            _row = _con.execute(
                "SELECT snippet FROM snippets WHERE uid = ?",
                (SNIPPETS["current_progress_indicator"].uid,)
            ).fetchone()
            _cur_indicator = _row[0] if _row else ""
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
            _label = "已到达进度" if _numerator >= _denominator else "未到达进度"
            _progress_str = f"{_numerator}/{_denominator} {_label}"
        else:
            _progress_str = SNIPPETS["current_progress_indicator"].default  # "0/0 未到达进度"
        write_snippet_value("current_progress_indicator", _progress_str)
        state["current_progress_indicator"] = _progress_str
        state["current_milestone_denominator"] = _denominator
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


@app.route("/api/divine-intervention", methods=["POST"])
def api_divine_intervention():
    """Copy the divine-intervention prompt to clipboard, then trigger stay.applescript."""
    data = request.get_json(silent=True) or {}
    prompt_text = data.get("prompt", "")
    try:
        # ① 写入剪切板
        subprocess.run(["pbcopy"], input=prompt_text.encode("utf-8"),
                       check=True, timeout=5)
        # ② 运行 stay.applescript
        stay_script = str(BASE / "applescript" / "stay.applescript")
        subprocess.run(["osascript", stay_script], check=True, timeout=10)
        return jsonify({"ok": True})
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)}), 500


AGENT_WORKSPACE    = BASE / "Agent_Workspace"
COMPLAINTS_FILE    = AGENT_WORKSPACE / "complaints.txt"
COMPLAINT_LOGIC    = AGENT_WORKSPACE / "complaint_logic.txt"
PROMPTS_FILE       = AGENT_WORKSPACE / "prompts.txt"
TERMINAL_SCRIPT    = BASE / "applescript" / "terminal.applescript"


@app.route("/api/violation-start", methods=["POST"])
def api_violation_start():
    """Step 2 后台初始化：清空工作文件 → 写入 violations → 复制 prompts.txt → 运行 terminal.applescript。"""
    data       = request.get_json(silent=True) or {}
    violations = data.get("violations", "").strip()
    try:
        AGENT_WORKSPACE.mkdir(parents=True, exist_ok=True)
        # ① 清空两个工作文件
        COMPLAINTS_FILE.write_text("", encoding="utf-8")
        COMPLAINT_LOGIC.write_text("", encoding="utf-8")
        # ② 写入用户填写的违规描述
        COMPLAINTS_FILE.write_text(violations, encoding="utf-8")
        # ③ 将 prompts.txt 复制到剪切板
        prompts_text = PROMPTS_FILE.read_text(encoding="utf-8") \
                       if PROMPTS_FILE.exists() else ""
        subprocess.run(["pbcopy"], input=prompts_text.encode("utf-8"),
                       check=True, timeout=5)
        # ④ 触发 terminal.applescript（唤醒规则调查 Agent）
        subprocess.Popen(["osascript", str(TERMINAL_SCRIPT)])
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
    expected   = data.get("expected", "").strip()
    try:
        prompt_md_path = BASE / "prompt.md"
        prompt_md = prompt_md_path.read_text(encoding="utf-8") \
                    if prompt_md_path.exists() else "（prompt.md 文件不存在）"

        full_prompt = (
            "【违规通告】\n"
            "AI 已违反《学习时间追踪系统》核心游戏规则\n\n"
            f"规则调查员的调查报告结果：{expected}\n"
            f"违规描述：{violations}\n"
            "提出警告：\n"
            "（1）在AI修改其违规行为之前，游戏无法继续\n"
            "（2）AI必须重新阅读prompt.md，确保没有遗忘或误解重要游戏规则\n"
            "（3）对于已经发生的人生事件，AI可以无需修改自己的错判，但是必须警醒自己的错误\n\n"
            "---\n\n"
            + prompt_md
        )

        subprocess.run(["pbcopy"], input=full_prompt.encode("utf-8"),
                       check=True, timeout=5)
        subprocess.run(
            ["python3", str(BASE / "increment_violation_count_snippet.py")],
            check=True, timeout=10,
        )
        stay_script = str(BASE / "applescript" / "stay.applescript")
        subprocess.run(["osascript", stay_script], check=True, timeout=10)
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

        # ── 写入进度条分母到 milestone_goals.json ────────────────────────────
        denominators = data.get("denominators", [])  # 与 milestones[] 等长的整数列表
        goals: dict[str, int] = {"hour3": 0, "hour6": 0, "hour9": 0, "hour12": 0}
        for key, denom in zip(applicable_keys, denominators):
            try:
                goals[key] = max(0, int(denom))
            except (ValueError, TypeError):
                goals[key] = 0
        MILESTONE_GOALS_FILE.parent.mkdir(parents=True, exist_ok=True)
        MILESTONE_GOALS_FILE.write_text(
            json.dumps(goals, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        # 同步重置 -current-progress-indicator（分子清零）
        _init_denom = goals.get("hour3", 0)
        write_snippet_value(
            "current_progress_indicator",
            f"0/{_init_denom} 未到达进度" if _init_denom > 0
            else SNIPPETS["current_progress_indicator"].default
        )

        # ── 学习记录总条数 ───────────────────────────────────────────────────
        write_snippet_value("total_count", str(hours * 6))

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


@app.route("/api/health-adjust", methods=["POST"])
def api_health_adjust():
    """Decrease (or increase) health by delta, clamped to [0, 10]."""
    data  = request.get_json()
    delta = int(data.get("delta", 0))
    try:
        current = int(HEALTH_FILE.read_text(encoding="utf-8").strip()) \
                  if HEALTH_FILE.exists() else 9
        new_val = max(0, min(current + delta, 10))
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
            write_snippet_value("is_victory", "已失败，失败来源：boss战失败")
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
        write_snippet_value("is_victory", "已胜利")
        # 胜利结算 → ×1.2
        final_score = update_total_score(factor=1.1)

        # ── 写入游戏存档 ────────────────────────────────────────────────────
        def _read_snip(key: str) -> str:
            try:
                s = SNIPPETS[key]
                with sqlite3.connect(DB_FILE) as _c:
                    row = _c.execute("SELECT snippet FROM snippets WHERE uid = ?", (s.uid,)).fetchone()
                return (row[0] or "").strip() if row else ""
            except Exception:
                return ""

        # 里程碑列表：hour3 / hour6 / hour9 / hour12 对应任务文字（过滤空槽位）
        milestone_keys  = ["hour3", "hour6", "hour9", "hour12"]
        milestone_slots = ["3小时节点", "6小时节点", "9小时节点", "12小时节点"]
        milestones = []
        for label, key in zip(milestone_slots, milestone_keys):
            text = _read_snip(key)
            if text and text not in ("0", ""):
                milestones.append({"节点": label, "任务": text})

        save_data = {
            "当天预期总条数":   int(_read_snip("total_count") or 0),
            "当天设置的休息总时长": _read_snip("max_rest_time"),
            "总积分":           final_score,
            "是否胜利":         "已胜利",
            "当前游戏难度":     _read_snip("difficulty"),
            "今日里程碑任务总览": milestones,
            "今日学习助手列表": [],
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
        def _read_snip(key: str) -> str:
            try:
                s = SNIPPETS[key]
                with sqlite3.connect(DB_FILE) as _c:
                    row = _c.execute("SELECT snippet FROM snippets WHERE uid = ?", (s.uid,)).fetchone()
                return (row[0] or "").strip() if row else ""
            except Exception:
                return ""

        # 当前积分（失败结算不额外乘以系数，惩罚已在触发时执行）
        snip = SNIPPETS["total_score"]
        with sqlite3.connect(DB_FILE) as _c:
            row = _c.execute("SELECT snippet FROM snippets WHERE uid = ?", (snip.uid,)).fetchone()
        final_score = int((row[0] or "0").strip()) if row else 0

        # 里程碑列表
        milestone_keys  = ["hour3", "hour6", "hour9", "hour12"]
        milestone_slots = ["3小时节点", "6小时节点", "9小时节点", "12小时节点"]
        milestones = []
        for label, key in zip(milestone_slots, milestone_keys):
            text = _read_snip(key)
            if text and text not in ("0", ""):
                milestones.append({"节点": label, "任务": text})

        # 读取当前失败状态（保留失败来源文字）
        is_victory_val = _read_snip("is_victory") or "已失败"

        save_data = {
            "当天预期总条数":    int(_read_snip("total_count") or 0),
            "当天设置的休息总时长": _read_snip("max_rest_time"),
            "总积分":            final_score,
            "是否胜利":          is_victory_val,
            "当前游戏难度":      _read_snip("difficulty"),
            "今日里程碑任务总览": milestones,
            "今日学习助手列表":  [],
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


@app.route("/api/reset", methods=["POST"])


def api_reset():
    """Run reset.py to wipe all game state back to Day-0 defaults."""
    try:
        import subprocess as _sp
        result = _sp.run(
            ["python3", "/Users/haichenlai/Desktop/Prompt/reset.py"],
            capture_output=True, text=True, timeout=15
        )
        output = result.stdout + result.stderr
        ok = result.returncode == 0
        return jsonify({"ok": ok, "output": output})
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)}), 500


@app.route("/api/progress-step", methods=["POST"])

def api_progress_step():
    """Increment or decrement the progress indicator numerator by delta (+1 / -1)."""
    data = request.get_json()
    delta = int(data.get("delta", 0))
    try:
        # Read current value from Alfred DB
        with sqlite3.connect(DB_FILE) as con:
            row = con.execute(
                "SELECT snippet FROM snippets WHERE uid = ?",
                (SNIPPETS["current_progress_indicator"].uid,)
            ).fetchone()
        cur = row[0] if row else "0/0 未到达进度"

        # Parse "N/M ..." format
        parts = cur.split("/")
        numerator   = int(parts[0].strip())
        denominator = int(parts[1].strip().split()[0])

        # Clamp new numerator to [0, denominator]
        new_num = max(0, min(numerator + delta, denominator))
        label   = "已到达进度" if new_num >= denominator > 0 else "未到达进度"
        new_str = f"{new_num}/{denominator} {label}"

        write_snippet_value("current_progress_indicator", new_str)
        return jsonify({"ok": True, "value": new_str})
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)}), 500


@app.route("/")
def index():
    return render_template("dashboard.html")



# ── HTML / CSS / JS → 已拆分到独立文件 ─────────────────────────────────────
# templates/dashboard.html  — HTML 结构
# static/dashboard.css      — 样式
# static/dashboard.js       — 交互逻辑



# ── entry point ──────────────────────────────────────────────────────────────

if __name__ == "__main__":
    port = 5050
    print(f"🍅 Dashboard 启动中...")
    print(f"   请在浏览器打开 http://localhost:{port}")
    print(f"   按 Ctrl+C 停止\n")
    app.run(host="127.0.0.1", port=port, debug=False)
