#!/usr/bin/env python3
"""stay_workflow.py — 编排：展开 stay 模板（无 pre_action）。

对应 Alfred Workflow: stay
对应 AppleScript:     applescript/stay.applescript (keystroke "-stay")
"""
from __future__ import annotations

import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from workflow.engine import run_workflow  # noqa: E402


def run(clipboard_override: str | None = None) -> str:
    """执行 stay workflow，返回展开后的完整 prompt。"""
    return run_workflow(
        template_name="stay",
        pre_action=None,
        clipboard_override=clipboard_override,
    )


if __name__ == "__main__":
    print(run())
