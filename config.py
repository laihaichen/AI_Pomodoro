#!/usr/bin/env python3
"""config.py — single source of truth for all paths, UIDs, and snippet defaults.

All other scripts import constants from here instead of defining them locally.
"""
from __future__ import annotations

from dataclasses import dataclass
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


# ── snippet registry ─────────────────────────────────────────────────────────

@dataclass(frozen=True)
class Snippet:
    uid: str
    name: str       # Alfred snippet name prefix; also used for JSON filename
    default: str    # value written on =reset; empty string → not reset
    resettable: bool = True

    @property
    def json_filename(self) -> str:
        """Alfred stores JSON files as '<name> [<uid>].json'."""
        return f"{self.name} [{self.uid}].json"

    @property
    def json_path(self) -> Path:
        return SNIPPETS_DIR / self.json_filename


SNIPPETS: dict[str, Snippet] = {
    "countcard":              Snippet("247CAEF6-57F5-4BCC-8D87-3E87CDDA1D0E", "-countcard",              "0"),
    "violationcount":         Snippet("1076C34A-79DA-42CE-A75A-EF4C853B0C2F", "-violationcount",         "0"),
    "interval":               Snippet("0352B20F-33EE-44A0-B570-FAAF2FA1E8E8", "-interval",               "0"),
    "fortunevalue":           Snippet("8BD89037-57B3-4964-A204-3D2D1F1250FA", "-fortunevalue",           "未到15分钟，合规"),
    "current_prompt_count":   Snippet("F1ABD0D4-576F-4CA6-B9A9-BB1715B961DB", "-current_prompt_count",   "0"),
    "stage":                  Snippet("DB01CF4F-8C54-4F29-B535-9E99BEC5A4B3", "-stage",                  "当前没有达到阶段性节点"),
    "total_rest_time":        Snippet("B3689D50-EEDD-42FC-A4E5-D19A70BA709B", "-total_rest_time",        "0"),
    "overtime_penalty_range": Snippet("D3D8CE6B-3AE4-4A88-91A2-9D23E0804E2D", "-overtime-penalty-range", "{random:0..0}"),
    "offset":                 Snippet("E99CD789-4D10-4C17-9A3A-C5076BA33ADB", "-offset",                 "0.0"),
    "difficulty":             Snippet("BDEE3C98-A4A1-4A2B-9046-18A12FD66083", "-difficulty",             "", resettable=False),
    "max_rest_time":          Snippet("D197E8BC-85F4-45D0-82D4-814FA0DCA629", "-max_rest_time",          "0", resettable=False),
    # ── 阶段性里程碑任务（每3小时一档）──────────────────────────────────────
    "hour3":                  Snippet("FFAAA6C5-754A-4B84-9DA9-0B67F14CAA9E", "-hour3",                  "当前无阶段性任务"),
    "hour6":                  Snippet("3740920C-9296-4B2C-B62A-4F7D544F1D56", "-hour6",                  "当前无阶段性任务"),
    "hour9":                  Snippet("97DA8F51-E403-4DBB-B715-13326F170791", "-hour9",                  "当前无阶段性任务"),
    "hour12":                 Snippet("6A798717-84DA-4597-B5AA-5D481BC15E21", "-hour12",                 "当前无阶段性任务"),
    # ── 当前任务 ──────────────────────────────────────────────────────────────
    "current_task":           Snippet("38C24B4C-7AC7-43E6-B690-63DBE8FB4EAD", "-current-task",           "无"),
    # ── Boss战节点 ───────────────────────────────────────────────────────────
    "bossfight_stage":        Snippet("4899268D-842C-4BD9-A455-FBF75DB89993", "-bossfight-stage",        "当前没有进入boss战节点"),
    # ── 当前时间 ─────────────────────────────────────────────────────────────
    "current_time":           Snippet("9D341FDD-4978-449F-91CD-D108A9A64636", "-current-time",           "0"),
    # ── 休息时间戳 ───────────────────────────────────────────────────────────
    "time_pause":                    Snippet("320E3246-386D-4995-8708-148F7C5C2730", "-time-pause",                    "0"),
    "time_cont":                     Snippet("BD542EAD-9643-4A73-8358-4BF4D9223FC5", "-time-cont",                     "0"),
    # ── 进度指示器 ───────────────────────────────────────────────────────────
    "current_progress_indicator":    Snippet("B2B0E669-50DE-4C5E-9381-C5FBCF28A997", "-current-progress-indicator",    "0/0 未到达进度"),
}
