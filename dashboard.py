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
import sys
from datetime import datetime, timezone

sys.path.insert(0, "/Users/haichenlai/Desktop/Prompt")
from config import (  # noqa: E402
    CURR_TS_FILE, PREV_TS_FILE, FIRST_TS_FILE,
    PENALIZED_REST_FILE, H_FILE,
    DB_FILE, SNIPPETS,
)

from flask import Flask, jsonify, render_template_string, request

app = Flask(__name__)

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

    state["curr_ts"]             = _fmt_ts(curr_raw)
    state["prev_ts"]             = _fmt_ts(prev_raw)
    state["first_ts"]            = _fmt_ts(first_raw)
    state["penalized_rest_up_to"] = _read_txt(PENALIZED_REST_FILE) or "0"
    state["h_value"]             = _read_txt(H_FILE) or "0"

    # Elapsed time since first record (in minutes)
    if first_raw and curr_raw:
        try:
            first_dt = datetime.fromisoformat(first_raw)
            curr_dt  = datetime.fromisoformat(curr_raw)
            elapsed  = (curr_dt - first_dt).total_seconds() / 60
            state["elapsed_minutes"] = round(elapsed, 1)
        except Exception:
            state["elapsed_minutes"] = None
    else:
        state["elapsed_minutes"] = None

    # ── Alfred snippets from SQLite ──────────────────────────────────────────
    snippet_keys = [
        "total_rest_time", "countcard", "interval", "fortunevalue",
        "current_prompt_count", "stage", "overtime_penalty_range",
        "offset", "difficulty", "max_rest_time", "violationcount",
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

    return state


# ── Flask routes ─────────────────────────────────────────────────────────────

@app.route("/api/state")
def api_state():
    return jsonify(collect_state())


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
<title>🍅 学习追踪 Dashboard</title>
<style>
  * { box-sizing: border-box; margin: 0; padding: 0; }

  :root {
    --bg:        #0f0f1a;
    --surface:   #1e1e2e;
    --border:    #313244;
    --text:      #cdd6f4;
    --subtext:   #6c7086;
    --green:     #a6e3a1;
    --yellow:    #f9e2af;
    --red:       #f38ba8;
    --blue:      #89b4fa;
    --mauve:     #cba6f7;
    --peach:     #fab387;
    --teal:      #94e2d5;
  }

  body {
    background: var(--bg);
    color: var(--text);
    font-family: -apple-system, BlinkMacSystemFont, "SF Pro Display", "Helvetica Neue", sans-serif;
    min-height: 100vh;
    padding: 24px;
  }

  /* ── header ── */
  .header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    margin-bottom: 28px;
  }
  .header-left { display: flex; align-items: center; gap: 16px; }
  .tomato { font-size: 56px; line-height: 1; }
  .title-block h1 { font-size: 22px; font-weight: 700; color: var(--text); }
  .title-block p  { font-size: 13px; color: var(--subtext); margin-top: 2px; }
  .refresh-badge {
    font-size: 12px; color: var(--subtext);
    background: var(--surface); border: 1px solid var(--border);
    border-radius: 20px; padding: 6px 14px;
  }
  .refresh-badge span { color: var(--blue); font-weight: 600; }

  /* ── section labels ── */
  .section-label {
    font-size: 11px; font-weight: 600; letter-spacing: 0.1em;
    color: var(--subtext); text-transform: uppercase;
    margin: 24px 0 10px;
  }

  /* ── grid ── */
  .grid { display: grid; gap: 12px; }
  .grid-2 { grid-template-columns: repeat(2, 1fr); }
  .grid-3 { grid-template-columns: repeat(3, 1fr); }
  .grid-4 { grid-template-columns: repeat(4, 1fr); }

  /* ── card ── */
  .card {
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: 12px;
    padding: 16px 18px;
    transition: border-color 0.3s;
  }
  .card.accent-green  { border-left: 3px solid var(--green); }
  .card.accent-yellow { border-left: 3px solid var(--yellow); }
  .card.accent-red    { border-left: 3px solid var(--red); }
  .card.accent-blue   { border-left: 3px solid var(--blue); }
  .card.accent-mauve  { border-left: 3px solid var(--mauve); }
  .card.accent-peach  { border-left: 3px solid var(--peach); }
  .card.accent-teal   { border-left: 3px solid var(--teal); }

  .card-label {
    font-size: 11px; font-weight: 600; letter-spacing: 0.05em;
    color: var(--subtext); text-transform: uppercase; margin-bottom: 8px;
  }
  .card-value {
    font-size: 26px; font-weight: 700; color: var(--text);
    line-height: 1.1;
  }
  .card-value.small { font-size: 14px; font-weight: 500; line-height: 1.5; word-break: break-word; }
  .card-sub {
    font-size: 12px; color: var(--subtext); margin-top: 6px;
  }

  /* colour overrides for values */
  .val-green  { color: var(--green)  !important; }
  .val-yellow { color: var(--yellow) !important; }
  .val-red    { color: var(--red)    !important; }
  .val-blue   { color: var(--blue)   !important; }
  .val-mauve  { color: var(--mauve)  !important; }
  .val-peach  { color: var(--peach)  !important; }
  .val-teal   { color: var(--teal)   !important; }

  /* hero count card */
  .hero-card {
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: 16px;
    padding: 24px;
    display: flex;
    align-items: center;
    gap: 20px;
  }
  .hero-tomato { font-size: 48px; }
  .hero-count  { font-size: 64px; font-weight: 800; color: var(--peach); line-height: 1; }
  .hero-label  { font-size: 14px; color: var(--subtext); margin-top: 4px; }
  .hero-right  { display: flex; flex-direction: column; gap: 4px; }

  /* stage card (can be long text) */
  .stage-card .card-value.small {
    font-size: 13px;
    color: var(--yellow);
    white-space: pre-line;
  }
  .stage-ok { color: var(--green) !important; }
  .stage-na { color: var(--subtext) !important; }

  @media (max-width: 700px) {
    .grid-3, .grid-4 { grid-template-columns: repeat(2, 1fr); }
    .grid-2 { grid-template-columns: 1fr; }
  }

  /* ── setup button ── */
  .setup-btn {
    background: var(--mauve); color: #1e1e2e;
    border: none; border-radius: 20px;
    padding: 8px 18px; font-size: 13px; font-weight: 700;
    cursor: pointer; transition: opacity 0.2s;
  }
  .setup-btn:hover { opacity: 0.85; }

  /* ── wizard modal ── */
  .modal-overlay {
    display: none; position: fixed; inset: 0;
    background: rgba(0,0,0,0.7); z-index: 100;
    align-items: center; justify-content: center;
  }
  .modal-overlay.open { display: flex; }
  .modal {
    background: var(--surface); border: 1px solid var(--border);
    border-radius: 20px; padding: 36px 40px;
    width: min(560px, 95vw); max-height: 90vh;
    overflow-y: auto; position: relative;
  }
  .modal-close {
    position: absolute; top: 16px; right: 20px;
    background: none; border: none; color: var(--subtext);
    font-size: 20px; cursor: pointer;
  }
  .modal-close:hover { color: var(--text); }
  .wizard-progress {
    display: flex; gap: 6px; margin-bottom: 28px;
  }
  .wizard-dot {
    height: 4px; border-radius: 2px; flex: 1;
    background: var(--border); transition: background 0.3s;
  }
  .wizard-dot.done { background: var(--mauve); }
  .wizard-dot.active { background: var(--blue); }
  .wizard-step-title {
    font-size: 11px; font-weight: 600; letter-spacing: 0.1em;
    color: var(--subtext); text-transform: uppercase; margin-bottom: 6px;
  }
  .wizard-step-heading {
    font-size: 20px; font-weight: 700; color: var(--text);
    margin-bottom: 6px;
  }
  .wizard-step-hint {
    font-size: 13px; color: var(--subtext); margin-bottom: 20px;
    line-height: 1.6;
  }
  .wizard-input {
    width: 100%; background: var(--bg); border: 1px solid var(--border);
    border-radius: 10px; color: var(--text);
    font-size: 16px; padding: 12px 16px;
    outline: none; transition: border-color 0.2s;
    font-family: inherit;
  }
  .wizard-input:focus { border-color: var(--blue); }
  .wizard-input.error { border-color: var(--red); }
  .wizard-select {
    width: 100%; background: var(--bg); border: 1px solid var(--border);
    border-radius: 10px; color: var(--text);
    font-size: 16px; padding: 12px 16px;
    outline: none; appearance: none; cursor: pointer;
    font-family: inherit;
  }
  .wizard-select:focus { border-color: var(--blue); }
  .wizard-textarea {
    width: 100%; background: var(--bg); border: 1px solid var(--border);
    border-radius: 10px; color: var(--text);
    font-size: 14px; padding: 12px 16px;
    outline: none; resize: vertical; min-height: 90px;
    font-family: inherit; line-height: 1.6;
  }
  .wizard-textarea:focus { border-color: var(--blue); }
  .wizard-error {
    color: var(--red); font-size: 12px; margin-top: 6px; min-height: 18px;
  }
  .wizard-btns {
    display: flex; gap: 10px; margin-top: 24px; justify-content: flex-end;
  }
  .btn-prev {
    background: none; border: 1px solid var(--border);
    color: var(--subtext); border-radius: 10px;
    padding: 10px 22px; font-size: 14px; cursor: pointer;
    font-family: inherit;
  }
  .btn-prev:hover { border-color: var(--text); color: var(--text); }
  .btn-next {
    background: var(--blue); border: none; color: #1e1e2e;
    border-radius: 10px; padding: 10px 28px;
    font-size: 14px; font-weight: 700; cursor: pointer;
    font-family: inherit; transition: opacity 0.2s;
  }
  .btn-next:hover { opacity: 0.85; }
  .btn-copy {
    background: var(--green); border: none; color: #1e1e2e;
    border-radius: 10px; padding: 10px 24px;
    font-size: 14px; font-weight: 700; cursor: pointer;
    font-family: inherit; transition: opacity 0.2s;
  }
  .btn-copy:hover { opacity: 0.85; }
  .prompt-result {
    width: 100%; background: var(--bg); border: 1px solid var(--border);
    border-radius: 10px; color: var(--teal);
    font-size: 13px; padding: 14px 16px;
    font-family: "SF Mono", "Menlo", monospace;
    line-height: 1.7; resize: none; min-height: 220px;
    outline: none;
  }
  .copy-success { color: var(--green); font-size: 13px; margin-top: 8px; min-height: 20px; }
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
    <button class="setup-btn" onclick="openWizard()">⚙️ 设置初始化 Prompt</button>
    <div class="refresh-badge">每 <span>5</span> 秒刷新 · 上次更新：<span id="last-update">—</span></div>
  </div>
</div>

<!-- ── 番茄钟进度 ── -->
<div class="section-label">番茄钟进度</div>
<div class="hero-card" id="hero-card">
  <div class="hero-tomato">🍅</div>
  <div>
    <div class="hero-count" id="val-current_prompt_count">—</div>
    <div class="hero-label">当前第几条番茄钟记录</div>
  </div>
  <div class="hero-right" style="margin-left:auto; text-align:right;">
    <div style="font-size:13px;color:var(--subtext);">当前难度</div>
    <div id="val-difficulty" style="font-size:20px;font-weight:700;color:var(--mauve);">—</div>
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
  <div class="card accent-yellow">
    <div class="card-label">已计入惩罚的休息截止</div>
    <div class="card-value" id="val-penalized_rest_up_to">—</div>
    <div class="card-sub">分钟（penalized_rest_up_to.txt）</div>
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
  { range: "0 ~ 3小时",  record: "第18条记录", hours: 3 },
  { range: "3 ~ 6小时",  record: "第36条记录", hours: 6 },
  { range: "6 ~ 9小时",  record: "第54条记录", hours: 9 },
];

function buildSteps(hours) {
  const steps = [];

  // Step 0: hours (already collected, we rebuild after)
  steps.push({ id: "hours", type: "number",
    title: "计划学习时长", heading: "今天计划学习几小时？",
    hint: "请输入 1 ~ 14 之间的整数。",
    min: 1, max: 14, placeholder: "例：10",
  });

  // Milestone steps
  MILESTONE_DEFS.forEach((m, i) => {
    if (hours >= m.hours) {
      steps.push({ id: `milestone_${i}`, type: "text",
        title: `阶段目标 ${i+1} / ${Math.floor(hours/3)}`,
        heading: `${m.range} 阶段最低完成指标`,
        hint: `${m.range}（${m.record}）达到时，你希望完成什么任务？`,
        placeholder: "例：完成 3 道算法题",
      });
    }
  });

  // Max rest
  steps.push({ id: "max_rest", type: "number",
    title: "休息设置", heading: "今天允许的最长休息时间",
    hint: "单位：分钟。建议 20 ~ 60 分钟。",
    min: 1, max: 300, placeholder: "例：30",
  });

  // Difficulty
  steps.push({ id: "difficulty", type: "select",
    title: "游戏难度", heading: "请选择今天的游戏难度",
    hint: "难度影响阶段性节点检查和 Boss 战规则。",
    options: ["硬核难度", "平衡难度", "探索者难度"],
  });

  // Theme
  steps.push({ id: "theme", type: "textarea",
    title: "故事主题", heading: "今天的模拟人生故事主题",
    hint: "描述你希望 AI 为今天的学习旅程设定的故事背景与主角。",
    placeholder: "例：以一名刚入职的程序员为主角，在高压项目中寻找成长与平衡的故事。",
    required: false,
  });

  // Result
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
  wSteps = buildSteps(0); // start with step 0 only until hours known
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
    // After hours step, rebuild full step list
    if (step.id === "hours") {
      wSteps = buildSteps(val);
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
    wData[step.id] = document.getElementById("w-input").value;
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

// ── Dashboard data refresh ───────────────────────────────────────────────────
const REFRESH_MS = 5000;
let countdown = REFRESH_MS / 1000;

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
      setVal("val-max_rest_time",           d.max_rest_time);
      setVal("val-total_rest_time",         d.total_rest_time);
      setVal("val-penalized_rest_up_to",    d.penalized_rest_up_to);

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

      // update time
      document.getElementById("last-update").textContent =
        new Date().toLocaleTimeString("zh-CN");
      countdown = REFRESH_MS / 1000;
    })
    .catch(err => {
      document.getElementById("last-update").textContent = "读取失败";
    });
}

// countdown display
setInterval(() => {
  countdown = Math.max(0, countdown - 1);
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
