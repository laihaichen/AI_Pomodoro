"""
工具：计算特定助手 / 团队（或无助手情况）的胜率
用法：
  python3 win_rate.py [助手1 助手2 ...] [--difficulty 难度] [--mode solo|multi]
规则：
  不传助手       计算无助手天
  一个助手       按 --mode 过滤（默认：含即算）
  两个及以上    精确团队匹配（助手列表必须与传入的人完全相等）
--mode 选项（仅单人时生效）：
  不传       只要包含该助手即算
  solo     该助手是当天唯一助手
  multi    该助手存在且当天还有其他助手
示例：
  python3 win_rate.py                        # 无助手
  python3 win_rate.py 能天使                 # 单人，包含即算
  python3 win_rate.py 能天使 --mode solo       # 单人，唯一
  python3 win_rate.py 能天使 角峰            # 团队：有且仅有这两人
  python3 win_rate.py 能天使 角峰 魔痹       # 团队：有且仅有这三人
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


def filter_records(records, assistants, mode):
    """
    助手过滤逻辑，返回 (matched, label)
    assistants: list
      []→无助手  [name]→单人+mode  [a,b,...]→精确团队匹配
    """
    if len(assistants) > 1:
        target = set(assistants)
        matched = [
            r for r in records
            if set(r.get("今日学习助手列表", [])) == target
        ]
        label = f"团队「{'\u3001'.join(assistants)}」[精确匹配]"
    elif len(assistants) == 1:
        name = assistants[0]
        base = [r for r in records if name in r.get("今日学习助手列表", [])]
        if mode == "solo":
            matched = [r for r in base if len(r.get("今日学习助手列表", [])) == 1]
            mode_label = "单人"
        elif mode == "multi":
            matched = [r for r in base if len(r.get("今日学习助手列表", [])) > 1]
            mode_label = "多人含"
        else:
            matched = base
            mode_label = "全模式"
        label = f"助手「{name}」[{mode_label}]"
    else:
        matched = [r for r in records if not r.get("今日学习助手列表")]
        label = "无助手"
    return matched, label


def calc_win_rate(assistants: list = None, difficulty: str = None, mode: str = None):
    records = load_records()

    # 难度过滤
    if difficulty:
        records = [r for r in records if r.get("当前游戏难度") == difficulty]

    matched, label = filter_records(records, assistants or [], mode)

    # 标题
    diff_label = f"（{difficulty}）" if difficulty else "（全难度）"
    print(f"{label} {diff_label}")

    if not matched:
        print("没有找到符合条件的记录。")
        return

    print(f"{'日期':<22} {'难度':<8} {'结果':<12} 当天助手")
    print("-" * 70)

    wins = 0
    for r in matched:
        is_win = r["是否胜利"] == "已胜利"
        if is_win:
            wins += 1
        tag = "✅ 胜利" if is_win else f"❌ 失败（{r['是否胜利'].replace('已失败，失败来源：', '')}）"
        diff_tag = r.get("当前游戏难度", "?")
        assistants_tag = "、".join(r.get("今日学习助手列表", [])) or "无"
        print(f"  {r['存档时间']:<20} {diff_tag:<8} {tag:<12} {assistants_tag}")

    total = len(matched)
    rate = wins / total * 100
    print("-" * 70)
    print(f"总场次: {total}，胜利: {wins}，失败: {total - wins}")
    print(f"胜率: {rate:.1f}%")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="计算助手胜率")
    parser.add_argument("assistants", nargs="*", default=[],
                        help="助手名称，空格分隔多个。不填=无助手，一个=单人+mode，多个=团队精确匹配")
    parser.add_argument("--difficulty", default=None, help="难度过滤，例如：硬核难度、平衡难度（不填=全难度）")
    parser.add_argument("--mode", choices=["solo", "multi"], default=None,
                        help="solo=该助手是当天唯一助手, multi=当天还有其他助手（仅单人时生效）")
    args = parser.parse_args()
    calc_win_rate(args.assistants, args.difficulty, args.mode)
