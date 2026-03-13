#!/usr/bin/env python3
"""pause_workflow.py — 编排：调 pause.py → 展开 pause 模板。

对应 Alfred Workflow: pause
对应 AppleScript:     applescript/pause.applescript (keystroke "-pause")
"""
from __future__ import annotations


import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from workflow.engine import run_workflow  # noqa: E402


def run(clipboard_override: str | None = None) -> str:
    """执行 pause workflow，返回展开后的完整 prompt。"""
    from actions.pause import main as _pause_main
    return run_workflow(
        template_name="pause",
        pre_action=lambda: _pause_main(),
        clipboard_override=clipboard_override,
    )


if __name__ == "__main__":
    print(run())
