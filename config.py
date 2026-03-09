#!/usr/bin/env python3
"""config.py — single source of truth for all paths, UIDs, and snippet defaults.

All other scripts import constants from here instead of defining them locally.
"""
from __future__ import annotations

import json
import os
import re as _re
import sqlite3
from dataclasses import dataclass, field
from pathlib import Path

# ── 运行模式 ─────────────────────────────────────────────────────────────────
# "alfred"     → 读写 Alfred SQLite（默认，需要安装 Alfred）
# "standalone" → 读写本地 JSON（无需 Alfred）
APP_MODE = os.environ.get("APP_MODE", "alfred")

# ── base paths ───────────────────────────────────────────────────────────────
BASE     = Path(__file__).resolve().parent
DATA_DIR = BASE / "data"
LOCAL_SNIPPETS_FILE = DATA_DIR / "snippets_local.json"    # standalone 模式存储

_ALFRED = Path.home() / "Library" / "Application Support" / "Alfred"
DB_FILE      = _ALFRED / "Databases" / "snippets.alfdb"
SNIPPETS_DIR = _ALFRED / "Alfred.alfredpreferences" / "snippets" / "学习时间追踪系统"

# ── 目标 AI 对话 URL（从 api_config.json 读取，两种模式共用）────────────────
API_CONFIG_FILE = BASE / "api_config.json"

def _load_target_urls() -> list[str]:
    """从 api_config.json 读取 target_urls，不存在则默认 gemini.google.com。"""
    try:
        cfg = json.loads(API_CONFIG_FILE.read_text(encoding="utf-8"))
        urls = cfg.get("target_urls", [])
        if urls:
            return urls
    except (FileNotFoundError, json.JSONDecodeError):
        pass
    return ["gemini.google.com", "aistudio.google.com"]

TARGET_URLS: list[str] = _load_target_urls()

# ── data file paths ──────────────────────────────────────────────────────────
CURR_TS_FILE        = DATA_DIR / "curr_timestamp.txt"
PREV_TS_FILE        = DATA_DIR / "prev_timestamp.txt"
FIRST_TS_FILE       = DATA_DIR / "first_timestamp.txt"
PAUSE_TS_FILE       = DATA_DIR / "pause_timestamp.txt"
CONT_TS_FILE        = DATA_DIR / "continue_timestamp.txt"
H_FILE              = DATA_DIR / "h_value.txt"
PENALIZED_REST_FILE = DATA_DIR / "penalized_rest_up_to.txt"
MILESTONE_GOALS_FILE = DATA_DIR / "milestone_goals.json"   # 各阶段进度条分母
HEALTH_FILE          = DATA_DIR / "health.txt"              # 健康度（初始9，只减不加）
FINAL_FATE_FILE      = DATA_DIR / "final_fate.txt"          # 最终命运值
BOSS_DEFEATED_FILE   = DATA_DIR / "is_boss_defeated.txt"    # Boss战结果（none/true/false）
THEME_FILE           = DATA_DIR / "theme.txt"               # 今日模拟人生故事主题


# ── snippet registry ─────────────────────────────────────────────────────────

@dataclass(frozen=True)
class Snippet:
    name: str           # Alfred snippet name prefix (e.g. "-healthy")
    default: str        # value written on =reset; empty string → not reset
    resettable: bool = True
    panel_label: str = ""  # AI面板显示名称；空字符串 = 不出现在游戏状态面板


SNIPPETS: dict[str, Snippet] = {
    # ── 时间 ─────────────────────────────────────────────────────────────────
    "current_time":           Snippet("-current-time",           "0",
                                      panel_label="本条时间"),
    # ── 学习进度 ──────────────────────────────────────────────────────────────
    "current_prompt_count":   Snippet("-current_prompt_count",   "0",
                                      panel_label="当前学习记录条数"),
    "total_count":            Snippet("-total-count",            "0",
                                      panel_label="学习记录总条数"),
    "total_score":            Snippet("-total-score",            "0",
                                      panel_label="当前总积分"),
    # ── 健康度（概率吉凶系统） ────────────────────────────────────────────────
    "healthy":                Snippet("-healthy",                "9",
                                      panel_label="健康度"),
    # ── 随机数 ───────────────────────────────────────────────────────────────
    "random_num":             Snippet("-random-num",             "0",
                                      panel_label="原始随机数"),
    # ── 最终命运值 ────────────────────────────────────────────────────────────
    "final_fate_value":       Snippet("-final-fate-value",       "0",
                                      panel_label="最终命运值"),
    # ── 超时惩罚 ─────────────────────────────────────────────────────────────
    "overtime_penalty_random_num": Snippet("-overtime-penalty-random-num", "0",
                                           panel_label="超时惩罚随机数"),
    # ── 时间计算 ─────────────────────────────────────────────────────────────
    "interval":               Snippet("-interval",               "0",
                                      panel_label="时间差"),
    "is_time_within_limit":   Snippet("-is-time-difference-within-the-limit", "未到15分钟，合规",
                                      panel_label="时间差是否合规的状态"),
    "fortune_and_misfortune": Snippet("-fortune-and-misfortune", "吉",
                                      panel_label="吉凶结果"),
    # ── 阶段性任务 ────────────────────────────────────────────────────────────
    "current_task":           Snippet("-current-task",           "无",
                                      panel_label="当前正在进行的阶段性任务"),
    "current_progress_indicator": Snippet("-current-progress-indicator", "0/0 未到达进度",
                                          panel_label="当前阶段性任务进度情况"),
    "stage":                  Snippet("-stage",                  "当前没有达到阶段性节点",
                                      panel_label="当前是否达到阶段性节点？"),
    # ── Boss战 ───────────────────────────────────────────────────────────────
    "bossfight_stage":        Snippet("-bossfight-stage",        "当前没有进入boss战节点",
                                      panel_label="当前是否进入boss战节点？"),
    # ── 命运预设事件 ─────────────────────────────────────────────────────────
    "foretold":               Snippet("-foretold",               "当前为第一条记录，没有预设事件",
                                      panel_label="应该加载的预设事件，上一轮的"),
    # ── 休息 & 统计 ───────────────────────────────────────────────────────────
    "total_rest_time":        Snippet("-total_rest_time",        "0",
                                      panel_label="累计休息时间"),
    "countcard":              Snippet("-countcard",              "0",
                                      panel_label="当前宿命卡持有数"),
    "violationcount":         Snippet("-violationcount",         "0",
                                      panel_label="人工智能当前违规次数"),
    "offset":                 Snippet("-offset",                 "0.0",
                                      panel_label="当前时间偏移值(超过正60直接判负)"),
    "is_victory":             Snippet("-is-victory",             "尚未胜利",
                                      panel_label="游戏胜利状态"),
    # ── 设置（不出现在面板）─────────────────────────────────────────────────
    "difficulty":             Snippet("-difficulty",             "", resettable=False),
    "max_rest_time":          Snippet("-max_rest_time",          "0", resettable=False),
    # ── 阶段性里程碑任务（每3小时一档，不出现在面板主行）───────────────────
    "hour3":                  Snippet("-hour3",                  "当前无阶段性任务"),
    "hour6":                  Snippet("-hour6",                  "当前无阶段性任务"),
    "hour9":                  Snippet("-hour9",                  "当前无阶段性任务"),
    "hour12":                 Snippet("-hour12",                 "当前无阶段性任务"),
    # ── 休息时间戳（不出现在面板）──────────────────────────────────────────
    "time_pause":             Snippet("-time-pause",             "0"),
    "time_cont":              Snippet("-time-cont",              "0"),
    # ── 学习助手系统 ─────────────────────────────────────────────────────────
    "is_eligible_for_reward": Snippet("-is-eligible-for-reward", "当前未超过90，无奖励",
                                      panel_label="是否应该触发幸运系统"),
    "current_clipboard":      Snippet("-current-clipboard",      "无剪切板信息",
                                      panel_label="你的当前学习正文"),
    "countinterventioncard":  Snippet("-countinterventioncard",  "0",
                                      panel_label="当前干预卡持有数"),
    "active_companions":      Snippet("-active-companions",  "[]",
                                      panel_label="当前助手列表（当前队伍列表）"),
}


# ── Alfred UID 自动发现（Alfred 模式启动时执行）──────────────────────────────
# snippet name → Alfred UID，从 Alfred snippets 目录的文件名自动解析
_ALFRED_UIDS: dict[str, str] = {}

def _discover_alfred_uids() -> None:
    """扫描 Alfred snippets 目录，从文件名解析 name → UID 映射。"""
    global _ALFRED_UIDS
    if not SNIPPETS_DIR.exists():
        return
    for f in SNIPPETS_DIR.glob("*.json"):
        m = _re.match(r'(.+) \[([A-F0-9-]+)\]\.json', f.name)
        if m:
            _ALFRED_UIDS[m.group(1)] = m.group(2)

if APP_MODE == "alfred":
    _discover_alfred_uids()

def _get_uid(key: str) -> str:
    """获取 snippet 的 Alfred UID。"""
    name = SNIPPETS[key].name
    uid = _ALFRED_UIDS.get(name, "")
    if not uid:
        raise RuntimeError(
            f"未找到 snippet '{name}' 的 Alfred UID。"
            f"请确认 Alfred snippets 目录 {SNIPPETS_DIR} 存在且包含对应文件。"
        )
    return uid


# ── snippet IO（公共读写函数）────────────────────────────────────────────────

def _init_local_snippets() -> None:
    """首次 standalone 启动时，从 SNIPPETS 的 default 值初始化本地 JSON。"""
    if LOCAL_SNIPPETS_FILE.exists():
        return
    data = {k: s.default for k, s in SNIPPETS.items()}
    LOCAL_SNIPPETS_FILE.write_text(
        json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def _read_local(key: str) -> str:
    """从本地 JSON 读取 snippet 值。"""
    try:
        data = json.loads(LOCAL_SNIPPETS_FILE.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return SNIPPETS[key].default
    return data.get(key, SNIPPETS[key].default)


def _write_local(key: str, value: str) -> None:
    """写入本地 JSON。"""
    try:
        data = json.loads(LOCAL_SNIPPETS_FILE.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        data = {k: s.default for k, s in SNIPPETS.items()}
    data[key] = value
    LOCAL_SNIPPETS_FILE.write_text(
        json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def _read_alfred(key: str) -> str:
    """从 Alfred SQLite 读取 snippet 值。"""
    uid = _get_uid(key)
    with sqlite3.connect(DB_FILE) as con:
        row = con.execute(
            "SELECT snippet FROM snippets WHERE uid = ?", (uid,)
        ).fetchone()
    return row[0] if row else ""


def _write_alfred(key: str, value: str) -> None:
    """写入 Alfred SQLite + JSON 备份文件。"""
    uid = _get_uid(key)
    name = SNIPPETS[key].name
    with sqlite3.connect(DB_FILE) as con:
        con.execute(
            "UPDATE snippets SET snippet = ? WHERE uid = ?",
            (value, uid),
        )
    json_path = SNIPPETS_DIR / f"{name} [{uid}].json"
    if json_path.exists():
        payload = json.loads(json_path.read_text(encoding="utf-8"))
        payload["alfredsnippet"]["snippet"] = value
        json_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )


def read_snippet(key: str) -> str:
    """读取 snippet 值，根据 APP_MODE 自动分流。"""
    if APP_MODE == "standalone":
        return _read_local(key)
    return _read_alfred(key)


def write_snippet(key: str, value: str) -> None:
    """写入 snippet 值，根据 APP_MODE 自动分流。"""
    if APP_MODE == "standalone":
        _write_local(key, value)
    else:
        _write_alfred(key, value)


def update_total_score(delta: int = 0, factor: float = 1.0) -> int:
    """读取 -total-score，加 delta，乘 factor，写回。返回新值。"""
    try:
        current = int(read_snippet("total_score"))
    except (ValueError, TypeError):
        current = 0
    new_val = round((current + delta) * factor)
    write_snippet("total_score", str(new_val))
    return new_val


# ── prompt 备份 ──────────────────────────────────────────────────────────────
PROMPT_BACKUP_FILE = DATA_DIR / "prompt_backup.json"


def _read_current_state() -> dict:
    """从 snippet 读取当前游戏状态，返回结构化字典。"""
    def _int(key: str) -> int:
        try:
            return int(read_snippet(key) or "0")
        except (ValueError, TypeError):
            return 0

    def _float(key: str) -> float:
        try:
            return float(read_snippet(key) or "0")
        except (ValueError, TypeError):
            return 0.0

    interval = _float("interval")
    return {
        "prompt_count":    _int("current_prompt_count"),
        "total_count":     _int("total_count"),
        "health":          _int("healthy"),
        "fortune":         read_snippet("fortune_and_misfortune") or "—",
        "random_num":      _int("random_num"),
        "overtime_penalty": _int("overtime_penalty_random_num"),
        "final_fate":      _int("final_fate_value"),
        "interval":        interval,
        "is_overtime":     interval >= 15,
        "offset":          _float("offset"),
        "total_rest":      _float("total_rest_time"),
        "total_score":     _int("total_score"),
        "violation_count": _int("violationcount"),
        "is_victory":      read_snippet("is_victory") or "—",
    }


def backup_prompt(
    text: str,
    prompt_type: str = "unknown",
    state: dict | None = None,
) -> None:
    """将发送的 prompt 备份到 data/prompt_backup.json（结构化列表）。

    Args:
        text: 发送的 prompt 全文。
        prompt_type: "move" / "stay" / "init" / "divine" / "violation" 等。
        state: 游戏状态字典；None 时自动从 snippet 读取。
    """
    from datetime import datetime

    if state is None:
        try:
            state = _read_current_state()
        except Exception:
            state = {}

    record = {
        "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "type": prompt_type,
        "state": state,
        "prompt_text": text,
    }

    try:
        raw = PROMPT_BACKUP_FILE.read_text(encoding="utf-8")
        data = json.loads(raw)
        if not isinstance(data, list):
            # 兼容旧格式（dict），迁移为 list
            data = []
    except (FileNotFoundError, json.JSONDecodeError):
        data = []

    data.append(record)
    PROMPT_BACKUP_FILE.write_text(
        json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
    )

