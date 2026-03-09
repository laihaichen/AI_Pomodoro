"""
工具：计算特定助手（或无助手情况）的番茄钟均条积分
用法：
  python3 avg_score_per_session.py [助手名称] [--difficulty 难度]
示例：
  python3 avg_score_per_session.py 能天使
  python3 avg_score_per_session.py 能天使 --difficulty 硬核难度
  python3 avg_score_per_session.py --difficulty 平衡难度
  python3 avg_score_per_session.py
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


def calc_avg_score_per_session(assistant_name: str = None, difficulty: str = None):
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

    print(f"{'日期':<22} {'总积分':>8} {'预期总条数':>10} {'每条均值':>10}")
    print("-" * 56)

    total_score = 0
    total_sessions = 0

    for r in matched:
        score = r["总积分"]
        sessions = r["当天预期总条数"]
        avg = score / sessions
        diff_tag = r.get("当前游戏难度", "?")
        print(f"  {r['存档时间']:<20} {score:>8} {sessions:>10} {avg:>9.1f}  [{diff_tag}]")
        total_score += score
        total_sessions += sessions

    overall_avg = total_score / total_sessions
    print("-" * 56)
    print(f"合计: 总积分={total_score}, 总条数={total_sessions}")
    print(f"加权平均每条积分: {overall_avg:.1f}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="计算番茄钟均条积分")
    parser.add_argument("assistant", nargs="?", default=None, help="助手名称（不填=无助手）")
    parser.add_argument("--difficulty", default=None, help="难度过滤，例如：硬核难度、平衡难度（不填=全难度）")
    args = parser.parse_args()
    calc_avg_score_per_session(args.assistant, args.difficulty)
