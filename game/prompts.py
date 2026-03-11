"""game.prompts — Load game_prompt.md and assemble user messages."""
from __future__ import annotations

from pathlib import Path

_BASE = Path(__file__).resolve().parent.parent
_GAME_PROMPT_FILE = _BASE / "game_prompt.md"


def load_system_prompt() -> str:
    """Load the static narrative rules from game_prompt.md."""
    if _GAME_PROMPT_FILE.exists():
        return _GAME_PROMPT_FILE.read_text(encoding="utf-8")
    return "你是一个叙事AI，负责根据给定的状态和事件撰写角色的模拟人生故事。"


def build_user_message(
    *,
    character_name: str,
    story_type: str,
    age: int,
    fate_value: int,
    event_text: str | None,
    is_first_turn: bool,
    history: list[dict],
    destiny_override: str | None = None,
    intervention_info: str | None = None,
) -> str:
    """Assemble the user message for one narrative turn."""
    lines: list[str] = []

    # ── current state ─────────────────────────────────────────────────
    lines.append("## 当前状态")
    if character_name:
        lines.append(f"- 角色名：{character_name}")
    lines.append(f"- 故事类型：{story_type}")
    lines.append(f"- 当前年龄：{age}岁")
    lines.append(f"- 本轮命运值：{fate_value}")
    lines.append("")

    # ── destiny card override ─────────────────────────────────────────
    if destiny_override:
        lines.append(f"- ⚠️ 本轮使用宿命卡，强制触发事件：{destiny_override}")
        lines.append("")

    # ── story content for this turn ───────────────────────────────────
    lines.append("## 本轮应该讲的故事内容")
    if is_first_turn:
        lines.append(
            f"本轮是角色的诞生，请将命运值 {fate_value} 解读为角色出生时的境况，"
            f"并撰写角色1岁的出生故事。"
        )
    elif destiny_override:
        lines.append(f"宿命卡强制事件：{destiny_override}")
    elif event_text:
        lines.append(event_text)
    else:
        lines.append("（引擎未能查到对应事件，请根据命运值自由发挥）")
    lines.append("")

    # ── intervention card info ────────────────────────────────────────
    if intervention_info:
        lines.append("## 干预卡自定义事件覆盖")
        lines.append(intervention_info)
        lines.append("")

    # ── full story history ────────────────────────────────────────────
    if history:
        lines.append("## 完整故事历史（严禁矛盾）")
        lines.append("以下是角色从出生至今的完整故事记录。你必须严格遵守已有设定，")
        lines.append("不得遗忘、篡改或与之矛盾。")
        lines.append("")
        for turn in history:
            t_age = turn.get("age", "?")
            t_text = turn.get("story_text", "")
            lines.append(f"### {t_age}岁")
            lines.append(t_text)
            lines.append("")

    # ── requirements ──────────────────────────────────────────────────
    lines.append("## 要求")
    lines.append("1. 根据「本轮应该讲的故事内容」撰写本轮故事")
    lines.append("2. 故事正文不超过 500 字")
    lines.append("3. 输出统一 JSON（story_text + 7 槽位 event_registry）")
    lines.append("4. 故事必须与上方「完整故事历史」保持严格连贯")

    return "\n".join(lines)
