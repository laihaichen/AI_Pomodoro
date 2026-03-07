#!/usr/bin/env python3
"""usecard_workflow.py — 编排：调 decrement_card_snippet.py → 展开 card 模板。

对应 Alfred Workflow: usecard
对应 AppleScript:     applescript/usecard.applescript (keystroke "-card")
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from workflow.engine import run_workflow  # noqa: E402


def run(clipboard_override: str | None = None) -> str:
    """执行 usecard workflow，返回展开后的完整 prompt。"""
    return run_workflow(
        template_name="card",
        pre_action=lambda: subprocess.run(
            [sys.executable, str(_PROJECT_ROOT / "decrement_card_snippet.py")],
            cwd=str(_PROJECT_ROOT),
        ),
        clipboard_override=clipboard_override,
    )


if __name__ == "__main__":
    print(run())
