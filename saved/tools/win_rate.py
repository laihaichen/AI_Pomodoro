"""
工具：计算特定助手（或无助手情况）的胜率
用法：
  python3 win_rate.py [助手名称] [--difficulty 难度]
示例：
  python3 win_rate.py 能天使
  python3 win_rate.py 能天使 --difficulty 硬核难度
  python3 win_rate.py --difficulty 平衡难度
  python3 win_rate.py
"""

import json
import sys
import os
import argparse

SAVES_PATH = os.path.join(os.path.dirname(__file__), "..", "saves.jsonl")


def load_records():
    records = []
    with open(SAVES_PATH, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                records.append(json.loads(line))
    return records


def calc_win_rate(assistant_name: str = None, difficulty: str = None):
    records = load_records()

    # 难度过滤
    if difficulty:
        records = [r for r in records if r.get("当前游戏难度") == difficulty]

    # 助手过滤
    if assistant_name:
        matched = [
            r for r in records
            if assistant_name in r.get("今日学习助手列表", [])
        ]
        label = f"助手「{assistant_name}」"
    else:
        matched = [
            r for r in records
            if not r.get("今日学习助手列表")
        ]
        label = "无助手"

    # 标题附加难度信息
    diff_label = f"（{difficulty}）" if difficulty else "（全难度）"
    print(f"{label} {diff_label}")

    if not matched:
        print(f"没有找到符合条件的记录。")
        return

    print(f"{'日期':<22} {'难度':<8} {'结果'}")
    print("-" * 58)

    wins = 0
    for r in matched:
        is_win = r["是否胜利"] == "已胜利"
        if is_win:
            wins += 1
        tag = "✅ 胜利" if is_win else f"❌ 失败（{r['是否胜利'].replace('已失败，失败来源：', '')}）"
        diff_tag = r.get("当前游戏难度", "?")
        print(f"  {r['存档时间']:<20} {diff_tag:<8} {tag}")

    total = len(matched)
    rate = wins / total * 100
    print("-" * 58)
    print(f"总场次: {total}，胜利: {wins}，失败: {total - wins}")
    print(f"胜率: {rate:.1f}%")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="计算助手胜率")
    parser.add_argument("assistant", nargs="?", default=None, help="助手名称（不填=无助手）")
    parser.add_argument("--difficulty", default=None, help="难度过滤，例如：硬核难度、平衡难度（不填=全难度）")
    args = parser.parse_args()
    calc_win_rate(args.assistant, args.difficulty)
