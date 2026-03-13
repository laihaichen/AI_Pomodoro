"""
jury/providers.py — 多提供商 AI API 调用封装
============================================
每个陪审员分配到不同公司的模型，确保投票独立性。
API key 统一从 api_config.json 读取。
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

_PROJECT_ROOT = Path(__file__).parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))
from config import DATA_ROOT  # noqa: E402

_CONFIG_FILE = DATA_ROOT / "api_config.json"

# ── 陪审员模型配置 ────────────────────────────────────────────────────────────
# 索引与 jurors[] 顺序对应：juror[0] → Gemini, juror[1] → Claude, juror[2] → OpenAI
JUROR_MODELS = [
    {"provider": "gemini",   "model": "gemini-3-flash-preview"},
    {"provider": "gemini",   "model": "gemini-3-flash-preview"},
    {"provider": "gemini",   "model": "gemini-3-flash-preview"},
]


def _load_config() -> dict:
    try:
        return json.loads(_CONFIG_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {}


# ── Gemini ────────────────────────────────────────────────────────────────────

def call_gemini(prompt: str, model: str = "gemini-3-flash-preview") -> str:
    """调用 Google Gemini API，返回纯文本回复。"""
    import google.generativeai as genai

    cfg = _load_config()
    api_key = cfg.get("gemini_api_key", "")
    if not api_key:
        raise ValueError("api_config.json 中缺少 gemini_api_key")

    genai.configure(api_key=api_key)
    m = genai.GenerativeModel(model)
    response = m.generate_content(
        prompt,
        generation_config=genai.types.GenerationConfig(
            temperature=0.3,
            max_output_tokens=2048,
        ),
    )
    try:
        return response.text.strip()
    except Exception:
        return response.candidates[0].content.parts[0].text.strip()


# ── Anthropic (Claude) ────────────────────────────────────────────────────────

def call_anthropic(prompt: str, model: str = "claude-haiku-4-5-20251001") -> str:
    """调用 Anthropic Claude API，返回纯文本回复。"""
    import anthropic

    cfg = _load_config()
    api_key = cfg.get("anthropic_api_key", "")
    if not api_key:
        raise ValueError("api_config.json 中缺少 anthropic_api_key")

    client = anthropic.Anthropic(api_key=api_key)
    message = client.messages.create(
        model=model,
        max_tokens=2048,
        temperature=0.3,
        messages=[{"role": "user", "content": prompt}],
    )
    return message.content[0].text.strip()


# ── OpenAI ────────────────────────────────────────────────────────────────────

def call_openai(prompt: str, model: str = "gpt-5.4") -> str:
    """调用 OpenAI API，返回纯文本回复。"""
    import openai

    cfg = _load_config()
    api_key = cfg.get("openai_api_key", "")
    if not api_key:
        raise ValueError("api_config.json 中缺少 openai_api_key")

    client = openai.OpenAI(api_key=api_key)
    response = client.chat.completions.create(
        model=model,
        temperature=0.3,
        max_completion_tokens=2048,
        messages=[{"role": "user", "content": prompt}],
    )
    return response.choices[0].message.content.strip()


# ── 统一调度 ──────────────────────────────────────────────────────────────────

_DISPATCH = {
    "gemini":    call_gemini,
    "anthropic": call_anthropic,
    "openai":    call_openai,
}


def call_provider(provider: str, prompt: str, model: str) -> str:
    """根据 provider 名称分发到对应的 API 调用函数。"""
    fn = _DISPATCH.get(provider)
    if fn is None:
        raise ValueError(f"未知的 AI 提供商: {provider}")
    return fn(prompt, model)
