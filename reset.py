#!/usr/bin/env python3
"""=reset handler — wipe all game state back to Day-0 defaults.

Resets:
  Files (cleared / emptied):
    - prev_timestamp.txt
    - curr_timestamp.txt
    - pause_timestamp.txt
    - continue_timestamp.txt

  Alfred snippets (DB + JSON):
    - -countcard      → "0"
    - -violationcount → "0"
    - -interval       → "0"
    - -fortunevalue   → "1"  (默认吉，游戏还未开始)
"""
from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path

# ── file paths ──────────────────────────────────────────────────────────────
BASE = Path("/Users/haichenlai/Desktop/Prompt")
TIMESTAMP_FILES = [
    BASE / "prev_timestamp.txt",
    BASE / "curr_timestamp.txt",
    BASE / "pause_timestamp.txt",
    BASE / "continue_timestamp.txt",
]

# ── Alfred snippet config ───────────────────────────────────────────────────
PREFS = Path(
    "/Users/haichenlai/Library/Application Support/Alfred"
    "/Alfred.alfredpreferences"
)
DB_FILE = Path(
    "/Users/haichenlai/Library/Application Support/Alfred"
    "/Databases/snippets.alfdb"
)
SNIPPETS_DIR = PREFS / "snippets" / "学习时间追踪系统"

# (UID, json_filename, reset_value)
SNIPPETS: list[tuple[str, str, str]] = [
    ("247CAEF6-57F5-4BCC-8D87-3E87CDDA1D0E", "-countcard",      "0"),
    ("1076C34A-79DA-42CE-A75A-EF4C853B0C2F", "-violationcount", "0"),
    ("0352B20F-33EE-44A0-B570-FAAF2FA1E8E8", "-interval",       "0"),
    ("8BD89037-57B3-4964-A204-3D2D1F1250FA", "-fortunevalue",   "1"),
]

# ── helpers ─────────────────────────────────────────────────────────────────

def reset_files() -> list[str]:
    """Clear all timestamp files. Return list of status lines."""
    lines = []
    for f in TIMESTAMP_FILES:
        f.write_text("", encoding="utf-8")
        lines.append(f"  ✓ {f.name} → cleared")
    return lines


def reset_snippets() -> list[str]:
    """Reset all Alfred snippets to their default values. Return status lines."""
    lines = []
    errors = []

    with sqlite3.connect(DB_FILE) as con:
        for uid, name, value in SNIPPETS:
            # Update SQLite (what Alfred reads live)
            con.execute("UPDATE snippets SET snippet = ? WHERE uid = ?", (value, uid))
            if con.total_changes == 0:
                errors.append(f"  ✗ {name}: UID not found in DB")
                continue

            # Update JSON (sync/backup)
            matches = [
                p for p in SNIPPETS_DIR.iterdir()
                if p.name.startswith(f"{name} ") and p.suffix == ".json"
            ]
            if not matches:
                errors.append(f"  ✗ {name}: JSON file not found")
                continue
            json_path = matches[0]
            payload = json.loads(json_path.read_text(encoding="utf-8"))
            payload["alfredsnippet"]["snippet"] = value
            json_path.write_text(
                json.dumps(payload, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            lines.append(f"  ✓ {name} → \"{value}\"")

    lines.extend(errors)
    return lines


# ── main ────────────────────────────────────────────────────────────────────

def main() -> int:
    print("🔄 重置游戏状态...\n")

    print("📄 时间戳文件：")
    for line in reset_files():
        print(line)

    print("\n🎲 Alfred Snippets：")
    try:
        for line in reset_snippets():
            print(line)
    except (OSError, sqlite3.Error) as exc:
        print(f"  ✗ 写入失败：{exc}", file=sys.stderr)
        return 1

    print("\n✅ 全部重置完成。可以开始新的一天了。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
