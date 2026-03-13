"""tests/test_move_logic.py — P0 测试：命运值计算与分类。

验证：
  - fate_category 区间映射正确性（含边界值）
  - probability_check 输入边界行为
  - 健康度读取容错
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from actions.move import fate_category, probability_check, read_health  # noqa: E402
import config as _cfg  # noqa: E402


# ── fate_category 区间映射 ───────────────────────────────────────────────────

class TestFateCategory:
    """命运值区间边界是整个游戏最核心的判定逻辑之一。"""

    @pytest.mark.parametrize("fate,expected", [
        # FAIL: <= -90
        (-100, "FAIL"),
        (-90,  "FAIL"),
        # NEG_HIGH: -89 ~ -60
        (-89,  "NEG_HIGH"),
        (-60,  "NEG_HIGH"),
        # NEG_MID: -59 ~ -30
        (-59,  "NEG_MID"),
        (-30,  "NEG_MID"),
        # NEG_LOW: -29 ~ -1
        (-29,  "NEG_LOW"),
        (-1,   "NEG_LOW"),
        # POS_LOW: 0 ~ 49
        (0,    "POS_LOW"),
        (49,   "POS_LOW"),
        # POS_MID: 50 ~ 84
        (50,   "POS_MID"),
        (84,   "POS_MID"),
        # POS_HIGH: 85+
        (85,   "POS_HIGH"),
        (100,  "POS_HIGH"),
        (999,  "POS_HIGH"),
    ])
    def test_boundaries(self, fate, expected):
        assert fate_category(fate) == expected

    def test_zero_is_positive(self):
        """0 应该属于正面区间（POS_LOW），不惩罚玩家。"""
        assert fate_category(0) == "POS_LOW"

    def test_negative_one_is_negative(self):
        """-1 应该属于负面区间（NEG_LOW）。"""
        assert fate_category(-1) == "NEG_LOW"


# ── probability_check ────────────────────────────────────────────────────────

class TestProbabilityCheck:
    def test_health_10_always_lucky(self):
        """健康度 10 → 100% 概率吉，连续 100 次都该是吉。"""
        results = [probability_check(10) for _ in range(100)]
        assert all(results)

    def test_health_0_always_unlucky(self):
        """健康度 0 → 0% 概率吉，连续 100 次都该是凶。"""
        results = [probability_check(0) for _ in range(100)]
        assert not any(results)

    def test_health_clamped_negative(self):
        """负数健康度应等效于 0。"""
        results = [probability_check(-5) for _ in range(100)]
        assert not any(results)

    def test_health_clamped_over_10(self):
        """超过 10 的健康度应等效于 10。"""
        results = [probability_check(15) for _ in range(100)]
        assert all(results)


# ── read_health 容错 ─────────────────────────────────────────────────────────

class TestReadHealth:
    @pytest.fixture(autouse=True)
    def isolated_health(self, tmp_path, monkeypatch):
        self.health_file = tmp_path / "health.txt"
        monkeypatch.setattr("actions.move.HEALTH_FILE", self.health_file)
        yield

    def test_missing_file_returns_9(self):
        assert read_health() == 9

    def test_normal_value(self):
        self.health_file.write_text("7", encoding="utf-8")
        assert read_health() == 7

    def test_clamps_to_0(self):
        self.health_file.write_text("-3", encoding="utf-8")
        assert read_health() == 0

    def test_clamps_to_10(self):
        self.health_file.write_text("15", encoding="utf-8")
        assert read_health() == 10

    def test_garbage_returns_9(self):
        self.health_file.write_text("abc", encoding="utf-8")
        assert read_health() == 9

    def test_empty_file_returns_9(self):
        self.health_file.write_text("", encoding="utf-8")
        assert read_health() == 9
