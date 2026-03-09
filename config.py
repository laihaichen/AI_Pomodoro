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


# ── Boss战触发文本（move.py + dashboard.py 共用）──────────────────────────────
BOSSFIGHT_ACTIVE_TEXT = """\
当前已经达到boss战节点，请AI根据游戏规则出题。

【boss战阶段规则回忆】

硬核难度：额外胜利条件 — Boss战

当距离完成当日目标还剩1条学习记录时自动触发Boss战
出题节点：在倒数第二条用户prompt对应的AI输出末尾，根据当日学习内容生成一题综合考核题
回答配额：玩家仅有1次回答机会（最后一条prompt）
作答方式：玩家必须将答案手写在白板上（白板手撕），并将白板上的手写答案拍照提交给AI进行审核
断网要求：玩家在开始回答的那一刻必须完全脱离任何互联网，不能从任何外部来源获取答案
唯一的例外：玩家允许查看番茄钟学习管理系统的历史记录（之前所有回合的AI回复内容），但不能产生历史记录之外的任何新记录（即不能发送新的prompt或使用任何在线资源）
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
                                      panel_label="当前学习记录条数（今天第几条记录，1条=10分钟期望学习时长）"),
    "total_count":            Snippet("-total-count",            "0",
                                      panel_label="学习记录总条数（当天目标总条数）"),
    "total_score":            Snippet("-total-score",            "0",
                                      panel_label="当前总积分（累计，可正可负）"),
    # ── 健康度（概率吉凶系统） ────────────────────────────────────────────────
    "healthy":                Snippet("-healthy",                "9",
                                      panel_label="健康度（满分10，初始9，只减不加）"),
    # ── 随机数 ───────────────────────────────────────────────────────────────
    "random_num":             Snippet("-random-num",             "0",
                                      panel_label="原始随机数（1~100）"),
    # ── 最终命运值 ────────────────────────────────────────────────────────────
    "final_fate_value":       Snippet("-final-fate-value",       "0",
                                      panel_label="最终命运值（范围-100~100，正=好运，负=厄运，≥90触发幸运系统）"),
    # ── 超时惩罚 ─────────────────────────────────────────────────────────────
    "overtime_penalty_random_num": Snippet("-overtime-penalty-random-num", "0",
                                           panel_label="超时惩罚随机数（0=无惩罚，>0表示因超时被扣除的命运值）"),
    # ── 时间计算 ─────────────────────────────────────────────────────────────
    "interval":               Snippet("-interval",               "0",
                                      panel_label="时间差（单位：分钟，两条记录之间的间隔，≥15分钟会强制判凶）"),
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
                                      panel_label="累计休息时间（单位：分钟）"),
    "countcard":              Snippet("-countcard",              "0",
                                      panel_label="当前宿命卡持有数"),
    "violationcount":         Snippet("-violationcount",         "0",
                                      panel_label="人工智能当前违规次数"),
    "offset":                 Snippet("-offset",                 "0.0",
                                      panel_label="当前时间偏移值（单位：分钟，负值=安全，正值且>60=判负）"),
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

