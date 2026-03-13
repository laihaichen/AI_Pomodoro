#!/usr/bin/env python3
"""host_ai.py — Sandbox mode: built-in Gemini host for the Pomodoro system.

Manages conversation history and calls the Gemini API with prompt.md
as the system prompt.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

_BASE = Path(__file__).resolve().parent
sys.path.insert(0, str(_BASE))

from config import BASE, DATA_ROOT  # noqa: E402

PROMPT_FILE = BASE / "docs" / "prompt.md"             # 只读资源
HOST_HISTORY_FILE = DATA_ROOT / "data" / "host_history.json"   # 可写数据
HOST_DISABLED_FLAG = DATA_ROOT / "data" / "host_disabled.flag" # 可写 flag
API_CONFIG_FILE = DATA_ROOT / "api_config.json"                # 可写配置


# ── disabled flag ────────────────────────────────────────────────────────────

def is_host_disabled() -> bool:
    return HOST_DISABLED_FLAG.exists()


def set_host_disabled(on: bool) -> None:
    if on:
        HOST_DISABLED_FLAG.parent.mkdir(parents=True, exist_ok=True)
        HOST_DISABLED_FLAG.write_text("1", encoding="utf-8")
    else:
        HOST_DISABLED_FLAG.unlink(missing_ok=True)


# ── history persistence ─────────────────────────────────────────────────────

def load_history() -> list[dict]:
    """Load conversation history: [{role: "user"|"model", parts: [text]}]."""
    if HOST_HISTORY_FILE.exists():
        try:
            return json.loads(HOST_HISTORY_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return []


def save_history(history: list[dict]) -> None:
    HOST_HISTORY_FILE.parent.mkdir(parents=True, exist_ok=True)
    HOST_HISTORY_FILE.write_text(
        json.dumps(history, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def append_turn(user_message: str, ai_reply: str) -> None:
    """Append one user+model exchange to history."""
    history = load_history()
    history.append({"role": "user", "parts": [user_message]})
    history.append({"role": "model", "parts": [ai_reply]})
    save_history(history)


# ── system prompt ────────────────────────────────────────────────────────────

def load_system_prompt() -> str:
    if PROMPT_FILE.exists():
        return PROMPT_FILE.read_text(encoding="utf-8")
    return "你是一个番茄钟学习管理助手。"


# ── Gemini API call ──────────────────────────────────────────────────────────

def _load_api_config() -> dict:
    try:
        return json.loads(API_CONFIG_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def chat(user_message: str) -> str:
    """Send user_message to Gemini with full conversation history.

    Returns the AI reply text.
    Raises on API errors.
    """
    import google.generativeai as genai

    if is_host_disabled():
        raise RuntimeError("主持人回应已关闭")

    cfg = _load_api_config()
    api_key = cfg.get("gemini_api_key", "")
    model_name = cfg.get("gemini_model", "gemini-2.0-flash")

    if not api_key or api_key.startswith("在此"):
        raise ValueError("请先在 api_config.json 中填写有效的 Gemini API Key")

    genai.configure(api_key=api_key)
    model = genai.GenerativeModel(
        model_name,
        system_instruction=load_system_prompt(),
    )

    # Build history for the chat session
    history = load_history()
    chat_session = model.start_chat(history=history)

    response = chat_session.send_message(
        user_message,
        generation_config=genai.types.GenerationConfig(
            temperature=0.7,
            max_output_tokens=8192,
        ),
    )

    reply = response.text.strip()

    # Persist the exchange
    append_turn(user_message, reply)

    return reply
