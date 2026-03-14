#!/usr/bin/env python3
"""stay_backup.py — 为 stay 动作生成 prompt 备份。

被 stay.applescript 调用，确保无论从 Dashboard 还是 Alfred 快捷键触发，
stay 的 prompt 都会被写入 prompt_backup.json。
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config import backup_prompt
from workflow.engine import load_template, expand_template

try:
    backup_prompt(expand_template(load_template("stay")), prompt_type="stay")
except Exception as exc:
    print(f"stay backup failed: {exc}", file=sys.stderr)
