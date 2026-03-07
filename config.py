#!/usr/bin/env python3
"""config.py — single source of truth for all paths, UIDs, and snippet defaults.

All other scripts import constants from here instead of defining them locally.
"""
from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass, field
from pathlib import Path

# ── base paths ───────────────────────────────────────────────────────────────
BASE     = Path("/Users/haichenlai/Desktop/Prompt")
DATA_DIR = BASE / "data"

_ALFRED = Path("/Users/haichenlai/Library/Application Support/Alfred")
DB_FILE      = _ALFRED / "Databases" / "snippets.alfdb"
SNIPPETS_DIR = _ALFRED / "Alfred.alfredpreferences" / "snippets" / "学习时间追踪系统"

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
    uid: str
    name: str           # Alfred snippet name prefix; also used for JSON filename
    default: str        # value written on =reset; empty string → not reset
    resettable: bool = True
    panel_label: str = ""  # AI面板显示名称；空字符串 = 不出现在游戏状态面板

    @property
    def json_filename(self) -> str:
        """Alfred stores JSON files as '<name> [<uid>].json'."""
        return f"{self.name} [{self.uid}].json"

    @property
    def json_path(self) -> Path:
        return SNIPPETS_DIR / self.json_filename


SNIPPETS: dict[str, Snippet] = {
    # ── 时间 ─────────────────────────────────────────────────────────────────
    "current_time":           Snippet("9D341FDD-4978-449F-91CD-D108A9A64636", "-current-time",           "0",
                                      panel_label="本条时间"),
    # ── 学习进度 ──────────────────────────────────────────────────────────────
    "current_prompt_count":   Snippet("F1ABD0D4-576F-4CA6-B9A9-BB1715B961DB", "-current_prompt_count",   "0",
                                      panel_label="当前学习记录条数"),
    "total_count":            Snippet("378F254A-D42A-42F2-82C1-52861B01648E", "-total-count",            "0",
                                      panel_label="学习记录总条数"),
    "total_score":            Snippet("41D7BAA8-D43B-4FEF-BF83-2A5B8A509979", "-total-score",            "0",
                                      panel_label="当前总积分"),
    # ── 健康度（概率吉凶系统） ────────────────────────────────────────────────
    "healthy":                Snippet("1186A78C-D0B8-4F9A-880A-B039B1BBB5E9", "-healthy",                "9",
                                      panel_label="健康度"),
    # ── 随机数 ───────────────────────────────────────────────────────────────
    "random_num":             Snippet("2C5EB3C4-C0A2-4E57-B43F-E9986256F225", "-random-num",             "0",
                                      panel_label="原始随机数"),
    # ── 最终命运值 ────────────────────────────────────────────────────────────
    "final_fate_value":       Snippet("373A5619-9AE9-4739-B7FE-7D511F660F80", "-final-fate-value",       "0",
                                      panel_label="最终命运值"),
    # ── 超时惩罚 ─────────────────────────────────────────────────────────────
    "overtime_penalty_random_num": Snippet("D3D8CE6B-3AE4-4A88-91A2-9D23E0804E2D", "-overtime-penalty-random-num", "0",
                                           panel_label="超时惩罚随机数"),
    # ── 时间计算 ─────────────────────────────────────────────────────────────
    "interval":               Snippet("0352B20F-33EE-44A0-B570-FAAF2FA1E8E8", "-interval",               "0",
                                      panel_label="时间差"),
    "is_time_within_limit":   Snippet("8BD89037-57B3-4964-A204-3D2D1F1250FA", "-is-time-difference-within-the-limit", "未到15分钟，合规",
                                      panel_label="时间差是否合规的状态"),
    "fortune_and_misfortune": Snippet("5BBAE44F-7BEC-4F9B-A578-58A9F7F84CF4", "-fortune-and-misfortune", "吉",
                                      panel_label="吉凶结果"),
    # ── 阶段性任务 ────────────────────────────────────────────────────────────
    "current_task":           Snippet("38C24B4C-7AC7-43E6-B690-63DBE8FB4EAD", "-current-task",           "无",
                                      panel_label="当前正在进行的阶段性任务"),
    "current_progress_indicator": Snippet("B2B0E669-50DE-4C5E-9381-C5FBCF28A997", "-current-progress-indicator", "0/0 未到达进度",
                                          panel_label="当前阶段性任务进度情况"),
    "stage":                  Snippet("DB01CF4F-8C54-4F29-B535-9E99BEC5A4B3", "-stage",                  "当前没有达到阶段性节点",
                                      panel_label="当前是否达到阶段性节点？"),
    # ── Boss战 ───────────────────────────────────────────────────────────────
    "bossfight_stage":        Snippet("4899268D-842C-4BD9-A455-FBF75DB89993", "-bossfight-stage",        "当前没有进入boss战节点",
                                      panel_label="当前是否进入boss战节点？"),
    # ── 命运预设事件 ─────────────────────────────────────────────────────────
    "foretold":               Snippet("FDAF9504-8D5C-41CF-8286-1B62AA250B7D", "-foretold",               "当前为第一条记录，没有预设事件",
                                      panel_label="应该加载的预设事件，上一轮的"),
    # ── 休息 & 统计 ───────────────────────────────────────────────────────────
    "total_rest_time":        Snippet("B3689D50-EEDD-42FC-A4E5-D19A70BA709B", "-total_rest_time",        "0",
                                      panel_label="累计休息时间"),
    "countcard":              Snippet("247CAEF6-57F5-4BCC-8D87-3E87CDDA1D0E", "-countcard",              "0",
                                      panel_label="当前宿命卡持有数"),
    "violationcount":         Snippet("1076C34A-79DA-42CE-A75A-EF4C853B0C2F", "-violationcount",         "0",
                                      panel_label="人工智能当前违规次数"),
    "offset":                 Snippet("E99CD789-4D10-4C17-9A3A-C5076BA33ADB", "-offset",                 "0.0",
                                      panel_label="当前时间偏移值(超过正60直接判负)"),
    "is_victory":             Snippet("B58339D5-FF40-4734-BDDB-E5D3113AE066", "-is-victory",             "尚未胜利",
                                      panel_label="游戏胜利状态"),
    # ── 设置（不出现在面板）─────────────────────────────────────────────────
    "difficulty":             Snippet("BDEE3C98-A4A1-4A2B-9046-18A12FD66083", "-difficulty",             "", resettable=False),
    "max_rest_time":          Snippet("D197E8BC-85F4-45D0-82D4-814FA0DCA629", "-max_rest_time",          "0", resettable=False),
    # ── 阶段性里程碑任务（每3小时一档，不出现在面板主行）───────────────────
    "hour3":                  Snippet("FFAAA6C5-754A-4B84-9DA9-0B67F14CAA9E", "-hour3",                  "当前无阶段性任务"),
    "hour6":                  Snippet("3740920C-9296-4B2C-B62A-4F7D544F1D56", "-hour6",                  "当前无阶段性任务"),
    "hour9":                  Snippet("97DA8F51-E403-4DBB-B715-13326F170791", "-hour9",                  "当前无阶段性任务"),
    "hour12":                 Snippet("6A798717-84DA-4597-B5AA-5D481BC15E21", "-hour12",                 "当前无阶段性任务"),
    # ── 休息时间戳（不出现在面板）──────────────────────────────────────────
    "time_pause":             Snippet("320E3246-386D-4995-8708-148F7C5C2730", "-time-pause",             "0"),
    "time_cont":              Snippet("BD542EAD-9643-4A73-8358-4BF4D9223FC5", "-time-cont",              "0"),
    # ── 学习助手系统 ─────────────────────────────────────────────────────────
    "is_eligible_for_reward": Snippet("CFCCE93B-4480-4898-9056-8331A5A2764B",  "-is-eligible-for-reward", "当前未超过85，无奖励",
                                      panel_label="是否应该触发幸运系统"),
    "current_clipboard":      Snippet("DFE00B87-E72B-4A9B-8E73-007DEF65EE0D",  "-current-clipboard",      "无剪切板信息",
                                      panel_label="你的当前学习正文"),
    "countinterventioncard":  Snippet("99B29E07-A3F8-4E88-84EF-1CE76F9D2AB4",  "-countinterventioncard",  "0",
                                      panel_label="当前干预卡持有数"),
}


# ── snippet IO（公共读写函数）────────────────────────────────────────────────

def read_snippet(key: str) -> str:
    """从 Alfred SQLite 读取 snippet 值。找不到则返回空字符串。"""
    snip = SNIPPETS[key]
    with sqlite3.connect(DB_FILE) as con:
        row = con.execute(
            "SELECT snippet FROM snippets WHERE uid = ?", (snip.uid,)
        ).fetchone()
    return row[0] if row else ""


def write_snippet(key: str, value: str) -> None:
    """同时写入 Alfred SQLite + JSON 备份文件。"""
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
    """读取 -total-score，加 delta，乘 factor，写回。返回新值。"""
    try:
        current = int(read_snippet("total_score"))
    except (ValueError, TypeError):
        current = 0
    new_val = round((current + delta) * factor)
    write_snippet("total_score", str(new_val))
    return new_val
