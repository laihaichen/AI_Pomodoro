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
    - data/game_state.json  (narrative engine — archived then reset)

  Alfred snippets (DB + JSON) — all SNIPPETS with resettable=True:
    - -countcard             → "0"
    - -violationcount        → "0"
    - -interval              → "0"
    - -is-time-difference-within-the-limit → "未到15分钟，合规"
    - -current_prompt_count  → "0"
    - -stage                 → "当前没有达到阶段性节点"
    - -bossfight-stage       → "当前没有进入boss战节点"
    - -total_rest_time       → "0"
    - -overtime-penalty-range → "{random:0..0}"
    - -offset                → "0.0"
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parent))
from config import DATA_DIR, BASE, SNIPPETS, MILESTONE_GOALS_FILE, HEALTH_FILE, FINAL_FATE_FILE, BOSS_DEFEATED_FILE, THEME_FILE, PROMPT_BACKUP_FILE, JURY_STATE_FILE, JURY_QUESTION_FILE, JURY_ANSWER_FILE, write_snippet  # noqa: E402

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
    # 纯文本状态文件重置
    (DATA_DIR / "companions_locked.txt").write_text("false", encoding="utf-8")
    lines.append("  ✓ companions_locked.txt → false")
    # JSON 文件重置（需保持合法 JSON）
    for json_file, empty_val in [
        ("active_companions.json",    "[]"),
        ("pending_active_skills.json","[]"),
        ("used_skills.json",          "{}"),
        ("companion_log.json",        "[]"),
        ("companion_chat.json",       "{}"),
        ("skill_cooldowns.json",      "{}"),
        ("skill_effects.json",        "{}"),
    ]:
        p = DATA_DIR / json_file
        p.write_text(empty_val, encoding="utf-8")
        lines.append(f"  ✓ {json_file} → {empty_val}")
    return lines


def reset_snippets() -> list[str]:
    """Reset all resettable Alfred snippets to their default values."""
    lines = []
    for key, snip in SNIPPETS.items():
        if not snip.resettable:
            continue
        try:
            write_snippet(key, snip.default)
            lines.append(f"  ✓ {snip.name} → \"{snip.default}\"")
        except Exception as exc:
            lines.append(f"  ✗ {snip.name}: {exc}")
    return lines


# ── main ────────────────────────────────────────────────────────────────────

def main() -> int:
    no_archive = "--no-archive" in sys.argv
    if no_archive:
        print("🔄 重置游戏状态（不保存模式）...\n")
    else:
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

    # Reset milestone_goals.json — 分母全部清零
    try:
        MILESTONE_GOALS_FILE.parent.mkdir(parents=True, exist_ok=True)
        _default_goal = {"denom": 0, "jury": False}
        MILESTONE_GOALS_FILE.write_text(
            json.dumps({
                "hour3": _default_goal, "hour6": _default_goal,
                "hour9": _default_goal, "hour12": _default_goal
            }, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        print("  ✓ milestone_goals.json → all zeros")
    except Exception as exc:
        print(f"  ✗ milestone_goals.json 重置失败：{exc}", file=sys.stderr)

    # Reset health.txt → 9
    try:
        HEALTH_FILE.parent.mkdir(parents=True, exist_ok=True)
        HEALTH_FILE.write_text("9", encoding="utf-8")
        print("  ✓ health.txt → 9")
    except Exception as exc:
        print(f"  ✗ health.txt 重置失败：{exc}", file=sys.stderr)

    # Clear final_fate.txt
    try:
        FINAL_FATE_FILE.write_text("", encoding="utf-8")
        print("  ✓ final_fate.txt → cleared")
    except Exception as exc:
        print(f"  ✗ final_fate.txt 清空失败：{exc}", file=sys.stderr)

    # Reset is_boss_defeated.txt → none
    try:
        BOSS_DEFEATED_FILE.parent.mkdir(parents=True, exist_ok=True)
        BOSS_DEFEATED_FILE.write_text("none", encoding="utf-8")
        print("  ✓ is_boss_defeated.txt → none")
    except Exception as exc:
        print(f"  ✗ is_boss_defeated.txt 重置失败：{exc}", file=sys.stderr)

    # Clear theme.txt
    try:
        THEME_FILE.write_text("", encoding="utf-8")
        print("  ✓ theme.txt → cleared")
    except Exception as exc:
        print(f"  ✗ theme.txt 清空失败：{exc}", file=sys.stderr)

    # Clear jury system files
    try:
        _jury_default = json.dumps({
            "jurors": [], "status": "idle",
            "current_question": "", "current_answer": "",
            "votes": [], "suspension_queue": [], "suspension_index": 0,
            "history": []
        }, ensure_ascii=False, indent=2)
        JURY_STATE_FILE.write_text(_jury_default, encoding="utf-8")
        JURY_QUESTION_FILE.write_text("", encoding="utf-8")
        JURY_ANSWER_FILE.write_text("", encoding="utf-8")
        print("  ✓ jury_state.json / jury_question.md / jury_answer.md → cleared")
    except Exception as exc:
        print(f"  ✗ 陪审团文件清空失败：{exc}", file=sys.stderr)

    # Archive & clear prompt_backup.json
    try:
        if not no_archive:
            raw = PROMPT_BACKUP_FILE.read_text(encoding="utf-8")
            data = json.loads(raw)
            if isinstance(data, list) and len(data) > 0:
                try:
                    date_str = data[0]["time"][:10]
                except (KeyError, IndexError, TypeError):
                    from datetime import date
                    date_str = date.today().isoformat()
                archive_dir = BASE / "saved" / "prompt_backup"
                archive_dir.mkdir(parents=True, exist_ok=True)
                archive_path = archive_dir / f"{date_str}.json"
                if archive_path.exists():
                    try:
                        existing = json.loads(archive_path.read_text(encoding="utf-8"))
                        if isinstance(existing, list):
                            data = existing + data
                    except (json.JSONDecodeError, Exception):
                        pass
                archive_path.write_text(
                    json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
                )
                print(f"  ✓ prompt_backup.json → 归档至 saved/prompt_backup/{date_str}.json（{len(data)} 条）")
            else:
                print("  ✓ prompt_backup.json 为空，无需归档")
        else:
            print("  ⚡ prompt_backup.json → 跳过归档（不保存模式）")
        PROMPT_BACKUP_FILE.write_text("[]", encoding="utf-8")
        print("  ✓ prompt_backup.json → []")
    except Exception as exc:
        print(f"  ✗ prompt_backup.json 归档/清空失败：{exc}", file=sys.stderr)
    # Archive & clear story_today.txt
    story_file = BASE / "data" / "story_today.txt"
    try:
        if not no_archive:
            story_text = story_file.read_text(encoding="utf-8").strip()
            if story_text:
                from datetime import date as _date
                date_str = _date.today().isoformat()
                story_dir = BASE / "saved" / "stories"
                story_dir.mkdir(parents=True, exist_ok=True)
                story_path = story_dir / f"{date_str}.txt"
                if story_path.exists():
                    story_text = story_path.read_text(encoding="utf-8") + "\n\n---\n\n" + story_text
                story_path.write_text(story_text, encoding="utf-8")
                print(f"  ✓ story_today.txt → 归档至 saved/stories/{date_str}.txt")
            else:
                print("  ✓ story_today.txt 为空，无需归档")
        else:
            print("  ⚡ story_today.txt → 跳过归档（不保存模式）")
        story_file.write_text("", encoding="utf-8")
        print("  ✓ story_today.txt → cleared")
    except Exception as exc:
        print(f"  ✗ story_today.txt 归档/清空失败：{exc}", file=sys.stderr)

    # Archive & clear game_state.json (narrative engine state)
    game_state_file = DATA_DIR / "game_state.json"
    try:
        if not no_archive and game_state_file.exists():
            gs_text = game_state_file.read_text(encoding="utf-8").strip()
            gs_data = json.loads(gs_text) if gs_text else {}
            history = gs_data.get("history", [])
            if history:
                from datetime import date as _date2
                date_str = _date2.today().isoformat()
                gs_dir = BASE / "saved" / "stories"
                gs_dir.mkdir(parents=True, exist_ok=True)
                gs_path = gs_dir / f"{date_str}_game_state.json"
                gs_path.write_text(
                    json.dumps(gs_data, ensure_ascii=False, indent=2),
                    encoding="utf-8",
                )
                print(f"  ✓ game_state.json → 归档至 saved/stories/{date_str}_game_state.json（{len(history)} 轮）")
            else:
                print("  ✓ game_state.json 无故事历史，无需归档")
        else:
            if not no_archive:
                print("  ✓ game_state.json 不存在，无需归档")
            else:
                print("  ⚡ game_state.json → 跳过归档（不保存模式）")
        # Reset to empty defaults
        game_state_file.write_text(
            json.dumps({
                "story_type": "", "character_name": "",
                "generation": 1, "main_line_failed": False,
                "pending_destiny": None, "history": []
            }, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        print("  ✓ game_state.json → reset to defaults")
    except Exception as exc:
        print(f"  ✗ game_state.json 归档/重置失败：{exc}", file=sys.stderr)

    # Clean up story generating flag
    flag_file = DATA_DIR / "story_generating.flag"
    flag_file.unlink(missing_ok=True)

    print("\n✅ 全部重置完成。可以开始新的一天了。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
