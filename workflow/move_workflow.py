#!/usr/bin/env python3
"""move_workflow.py — 编排：调 move.py 计算 → 展开 go 模板。

对应 Alfred Workflow: move (快捷键触发)
对应 AppleScript:     applescript/move.applescript (keystroke "-go")
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
    """执行 move workflow，返回展开后的完整 prompt。"""
    return run_workflow(
        template_name="go",
        pre_action=lambda: subprocess.run(
            [sys.executable, str(_PROJECT_ROOT / "actions" / "move.py")],
            cwd=str(_PROJECT_ROOT),
        ),
        clipboard_override=clipboard_override,
    )


if __name__ == "__main__":
    print(run())
