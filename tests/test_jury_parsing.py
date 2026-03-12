"""tests/test_jury_parsing.py — P1 测试：陪审团 JSON 解析容错。

验证：
  - 正常 JSON 解析
  - Markdown 代码块包裹的 JSON
  - 嵌套在文字中的 JSON
  - 完全胡说八道的回复 → 默认 approve
  - 投票计票逻辑
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from jury.engine import _parse_juror_response, finalize_verdict, JurorVote  # noqa: E402


# ── JSON 解析容错 ────────────────────────────────────────────────────────────

class TestParseJurorResponse:
    def test_clean_json(self):
        raw = '{"vote": "approve", "reasoning": "不错", "suspension_question": ""}'
        result = _parse_juror_response(raw)
        assert result["vote"] == "approve"
        assert result["reasoning"] == "不错"

    def test_markdown_wrapped_json(self):
        raw = '```json\n{"vote": "reject", "reasoning": "太差了", "suspension_question": ""}\n```'
        result = _parse_juror_response(raw)
        assert result["vote"] == "reject"

    def test_json_embedded_in_text(self):
        raw = '好的，以下是我的判断：\n{"vote": "suspend", "reasoning": "需要追问", "suspension_question": "你确定吗？"}\n以上就是我的回答。'
        result = _parse_juror_response(raw)
        assert result["vote"] == "suspend"
        assert result["suspension_question"] == "你确定吗？"

    def test_total_garbage_defaults_to_approve(self):
        """完全无法解析时，不惩罚玩家。"""
        raw = "哇这个问题好难啊我完全不知道怎么回答让我想想..."
        result = _parse_juror_response(raw)
        assert result["vote"] == "approve"

    def test_empty_string_defaults_to_approve(self):
        result = _parse_juror_response("")
        assert result["vote"] == "approve"

    def test_keyword_extraction_fallback(self):
        """JSON 格式不规范但能提取到关键词。"""
        raw = 'blah blah "vote": "reject" blah "reasoning": "不及格" blah'
        result = _parse_juror_response(raw)
        assert result["vote"] == "reject"
        assert result["reasoning"] == "不及格"

    def test_case_insensitive_vote(self):
        raw = '{"vote": "APPROVE", "reasoning": "ok", "suspension_question": ""}'
        result = _parse_juror_response(raw)
        assert result["vote"] == "APPROVE"  # 原始解析保留大小写，engine 里 .lower() 处理


# ── 投票计票逻辑 ──────────────────────────────────────────────────────────────

class TestFinalizeVerdict:
    def _vote(self, name, vote):
        return JurorVote(juror_name=name, provider="test", model="test", vote=vote)

    def test_all_approve(self):
        votes = [self._vote("A", "approve"), self._vote("B", "approve"), self._vote("C", "approve")]
        v = finalize_verdict(votes)
        assert v.outcome == "health_unchanged"
        assert v.approve_count == 3
        assert v.reject_count == 0

    def test_two_reject_means_penalty(self):
        votes = [self._vote("A", "reject"), self._vote("B", "reject"), self._vote("C", "approve")]
        v = finalize_verdict(votes)
        assert v.outcome == "health_minus_1"
        assert v.reject_count == 2

    def test_all_reject(self):
        votes = [self._vote("A", "reject"), self._vote("B", "reject"), self._vote("C", "reject")]
        v = finalize_verdict(votes)
        assert v.outcome == "health_minus_1"
        assert v.reject_count == 3

    def test_one_reject_safe(self):
        """1 票反对不足以扣血。"""
        votes = [self._vote("A", "reject"), self._vote("B", "approve"), self._vote("C", "approve")]
        v = finalize_verdict(votes)
        assert v.outcome == "health_unchanged"
        assert v.reject_count == 1

    def test_boundary_exactly_two_reject(self):
        """恰好 2 票反对 = 惩罚（>= 2 的边界）。"""
        votes = [self._vote("A", "reject"), self._vote("B", "reject")]
        v = finalize_verdict(votes)
        assert v.outcome == "health_minus_1"
