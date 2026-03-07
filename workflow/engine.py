#!/usr/bin/env python3
"""engine.py — Snippet 模板展开引擎。

替代 Alfred 的 snippet 展开能力：
  - {snippet:-xxx}  → 从存储层读取对应 snippet 值
  - {clipboard}     → 当前剪贴板内容
"""
from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

# 确保项目根目录在 sys.path 中
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from config import SNIPPETS, read_snippet  # noqa: E402

# snippet Alfred name ("-current-time") → config key ("current_time")
_NAME_TO_KEY: dict[str, str] = {s.name: k for k, s in SNIPPETS.items()}

TEMPLATE_DIR = Path(__file__).resolve().parent / "templates"


# ── 占位符替换 ────────────────────────────────────────────────────────────────

def _get_clipboard() -> str:
    """读取系统剪贴板内容（跨平台）。"""
    try:
        result = subprocess.run(
            ["pbcopy"],  # 先检测 macOS
            capture_output=True, timeout=2,
        )
        # 如果 pbcopy 存在，则用 pbpaste 读取
        result = subprocess.run(
            ["pbpaste"],
            capture_output=True, text=True, timeout=2,
        )
        return result.stdout
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass

    # Linux: xclip
    try:
        result = subprocess.run(
            ["xclip", "-selection", "clipboard", "-o"],
            capture_output=True, text=True, timeout=2,
        )
        return result.stdout
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass

    return ""


def expand_template(template_text: str, clipboard_override: str | None = None) -> str:
    """将模板中的占位符替换为实际值。

    支持的占位符：
      - {snippet:-xxx}   → 从 read_snippet 读取值
      - {clipboard}      → 剪贴板内容（或 clipboard_override）
    """
    def _replace_snippet(match: re.Match) -> str:
        snippet_name = match.group(1)           # e.g. "-current-time"
        key = _NAME_TO_KEY.get(snippet_name)
        if key:
            return read_snippet(key)
        return match.group(0)                   # 未知占位符保留原文

    result = re.sub(r'\{snippet:([-\w]+)\}', _replace_snippet, template_text)

    clipboard = clipboard_override if clipboard_override is not None else _get_clipboard()
    result = result.replace("{clipboard}", clipboard)

    return result


def load_template(template_name: str) -> str:
    """加载模板文件内容。"""
    path = TEMPLATE_DIR / f"{template_name}.txt"
    if not path.exists():
        raise FileNotFoundError(f"模板文件不存在: {path}")
    return path.read_text(encoding="utf-8")


# ── 主入口 ────────────────────────────────────────────────────────────────────

def run_workflow(
    template_name: str,
    pre_action: callable | None = None,
    clipboard_override: str | None = None,
) -> str:
    """执行完整 workflow：pre_action → 展开模板 → 返回最终文本。

    浏览器投递由调用方（workflow 脚本）负责。
    返回展开后的完整 prompt 文本。
    """
    if pre_action:
        pre_action()

    template = load_template(template_name)
    return expand_template(template, clipboard_override=clipboard_override)
