#!/usr/bin/env python3
"""output_story.py — 导出模拟人生故事

功能:
  1. 扫描 output/ 目录下所有 Gemini* 开头的 txt 文件
  2. 提取 【X岁故事开始】…【X岁故事结束】 之间的全部内容
  3. 按年龄排序后写入 data/story_today.txt（覆盖写入）
  4. 删除已处理的 output/Gemini*.txt 源文件

用法:
  python3 output_story.py
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

BASE       = Path(__file__).resolve().parent.parent
OUTPUT_DIR = BASE / "output"
STORY_FILE = BASE / "data" / "story_today.txt"

# 正则：匹配 【X岁故事开始】 … 【X岁故事结束】（含分隔标记本身）
STORY_RE = re.compile(
    r"(【(\d+)岁故事开始】.*?【\d+岁故事结束】)",
    re.DOTALL,
)


def extract_stories(text: str) -> list[tuple[int, str]]:
    """从文本中提取所有故事片段，返回 [(年龄, 故事全文), …]。"""
    results: list[tuple[int, str]] = []
    for match in STORY_RE.finditer(text):
        full_story = match.group(1).strip()
        age = int(match.group(2))
        results.append((age, full_story))
    return results


def main() -> int:
    # ── 1. 收集所有 Gemini*.txt 文件 ──────────────────────────────────────
    gemini_files = sorted(OUTPUT_DIR.glob("Gemini*.txt"))
    if not gemini_files:
        print("⚠️  output/ 目录下没有找到 Gemini*.txt 文件，无事可做。")
        return 0

    print(f"📂 找到 {len(gemini_files)} 个文件：")
    for f in gemini_files:
        print(f"   • {f.name}")

    # ── 2. 提取故事 ──────────────────────────────────────────────────────
    all_stories: list[tuple[int, str]] = []
    for f in gemini_files:
        text = f.read_text(encoding="utf-8")
        stories = extract_stories(text)
        print(f"   {f.name} → 提取到 {len(stories)} 段故事")
        all_stories.extend(stories)

    if not all_stories:
        print("⚠️  未在任何文件中找到 【X岁故事开始】…【X岁故事结束】 格式的故事。")
        return 1

    # 按年龄排序（去重：同一年龄只保留最后出现的版本）
    seen: dict[int, str] = {}
    for age, story in all_stories:
        seen[age] = story  # 后出现的覆盖先出现的
    sorted_stories = [seen[age] for age in sorted(seen)]

    # ── 3. 写入 data/story_today.txt ─────────────────────────────────────
    STORY_FILE.parent.mkdir(parents=True, exist_ok=True)
    STORY_FILE.write_text("\n\n".join(sorted_stories) + "\n", encoding="utf-8")
    print(f"\n✅ 已导出 {len(sorted_stories)} 段故事 → {STORY_FILE}")

    # ── 4. 删除已处理的 Gemini*.txt 源文件 ───────────────────────────────
    for f in gemini_files:
        f.unlink()
        print(f"   🗑  已删除 {f.name}")

    print("\n🎉 全部完成。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
