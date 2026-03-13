#!/usr/bin/env python3
"""CLI tool for the violation investigation Agent to archive complaint summaries.

Usage:
    python3 complaint_manage.py \
        --violation_behavior "AI的违规行为精简描述" \
        --violated_rules "第X章 X.X.X 条文标题：条文内容摘要"
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from config import DATA_ROOT  # noqa: E402

HISTORY_FILE = DATA_ROOT / "complaint_manager" / "complaints_history.json"


def load_history() -> list[dict]:
    if HISTORY_FILE.exists():
        try:
            data = json.loads(HISTORY_FILE.read_text(encoding="utf-8"))
            if isinstance(data, list):
                return data
        except (json.JSONDecodeError, OSError):
            pass
    return []


def save_history(records: list[dict]) -> None:
    HISTORY_FILE.parent.mkdir(parents=True, exist_ok=True)
    HISTORY_FILE.write_text(
        json.dumps(records, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Archive a violation complaint summary into complaints_history.json"
    )
    parser.add_argument(
        "--violation_behavior",
        required=True,
        help="Agent 精简总结的违规行为描述（理性精确，非情绪化原文）",
    )
    parser.add_argument(
        "--violated_rules",
        required=True,
        help="违反的具体规则条目编号及内容摘要",
    )
    args = parser.parse_args()

    record = {
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "violation_behavior": args.violation_behavior,
        "violated_rules": args.violated_rules,
    }

    history = load_history()
    history.append(record)
    save_history(history)

    print(f"✅ 违规记录已存档（共 {len(history)} 条）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
