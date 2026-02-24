#!/usr/bin/env python3
"""=reset handler — wipe all game state back to Day-0 defaults.

Resets:
  Files (cleared / emptied):
    - data/prev_timestamp.txt
    - data/curr_timestamp.txt
    - data/pause_timestamp.txt
    - data/continue_timestamp.txt
    - data/first_timestamp.txt
    - data/h_value.txt
    - data/penalized_rest_up_to.txt

  Alfred snippets (DB + JSON) — all SNIPPETS with resettable=True:
    - -countcard             → "0"
    - -violationcount        → "0"
    - -interval              → "0"
    - -fortunevalue          → "未到15分钟，合规"
    - -current_prompt_count  → "0"
    - -stage                 → "当前没有达到阶段性节点"
    - -total_rest_time       → "0"
    - -overtime-penalty-range → "{random:0..0}"
    - -offset                → "0.0"
"""
from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, "/Users/haichenlai/Desktop/Prompt")
from config import DATA_DIR, DB_FILE, SNIPPETS, SNIPPETS_DIR  # noqa: E402

# ── data files to clear on reset ─────────────────────────────────────────────
DATA_FILES_TO_CLEAR = [
    DATA_DIR / "prev_timestamp.txt",
    DATA_DIR / "curr_timestamp.txt",
    DATA_DIR / "pause_timestamp.txt",
    DATA_DIR / "continue_timestamp.txt",
    DATA_DIR / "first_timestamp.txt",
    DATA_DIR / "h_value.txt",
    DATA_DIR / "penalized_rest_up_to.txt",
]

# ── helpers ─────────────────────────────────────────────────────────────────

def reset_files() -> list[str]:
    """Clear all data files. Return list of status lines."""
    lines = []
    for f in DATA_FILES_TO_CLEAR:
        f.write_text("", encoding="utf-8")
        lines.append(f"  ✓ {f.name} → cleared")
    return lines


def reset_snippets() -> list[str]:
    """Reset all resettable Alfred snippets to their default values."""
    lines = []
    errors = []

    with sqlite3.connect(DB_FILE) as con:
        for snip in (s for s in SNIPPETS.values() if s.resettable):
            con.execute(
                "UPDATE snippets SET snippet = ? WHERE uid = ?",
                (snip.default, snip.uid),
            )
            if con.total_changes == 0:
                errors.append(f"  ✗ {snip.name}: UID not found in DB")
                continue

            if not snip.json_path.exists():
                errors.append(f"  ✗ {snip.name}: JSON file not found")
                continue
            payload = json.loads(snip.json_path.read_text(encoding="utf-8"))
            payload["alfredsnippet"]["snippet"] = snip.default
            snip.json_path.write_text(
                json.dumps(payload, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            lines.append(f"  ✓ {snip.name} → \"{snip.default}\"")

    lines.extend(errors)
    return lines


# ── main ────────────────────────────────────────────────────────────────────

def main() -> int:
    print("🔄 重置游戏状态...\n")

    print("📄 数据文件：")
    for line in reset_files():
        print(line)

    print("\n🎲 Alfred Snippets：")
    try:
        for line in reset_snippets():
            print(line)
    except (OSError, sqlite3.Error) as exc:
        print(f"  ✗ 写入失败：{exc}", file=sys.stderr)
        return 1

    # Seed penalized_rest_up_to.txt with current max_rest_time
    # so continue.py knows the correct baseline for rest penalty.
    try:
        import update_h as _uh
        max_rest = _uh.read_max_rest()
        _uh.write_penalized_rest(max_rest)
        print(f"  ✓ penalized_rest_up_to → {max_rest:.1f} (= max_rest_time)")
    except Exception as exc:
        print(f"  ✗ penalized_rest_up_to 初始化失败：{exc}", file=sys.stderr)

    print("\n✅ 全部重置完成。可以开始新的一天了。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
