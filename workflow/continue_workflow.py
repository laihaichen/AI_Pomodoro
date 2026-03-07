#!/usr/bin/env python3
"""continue_workflow.py — 编排：调 continue.py → 展开 continue 模板。

对应 Alfred Workflow: continue
对应 AppleScript:     applescript/continue.applescript (keystroke "-continue")
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
    """执行 continue workflow，返回展开后的完整 prompt。"""
    return run_workflow(
        template_name="continue",
        pre_action=lambda: subprocess.run(
            [sys.executable, str(_PROJECT_ROOT / "continue.py")],
            cwd=str(_PROJECT_ROOT),
        ),
        clipboard_override=clipboard_override,
    )


if __name__ == "__main__":
    print(run())
