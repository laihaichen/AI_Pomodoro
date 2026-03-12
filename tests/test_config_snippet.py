"""tests/test_config_snippet.py — P0 测试：snippet 持久化层可靠性。

验证：
  - 原子写入：kill -9 场景下数据不丢失
  - JSON 损坏恢复：文件损坏时自动用默认值重建
  - 读写一致性：写入后读出的值相同
  - 默认值 fallback：文件不存在时返回注册表默认值
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

# 确保项目根目录在 sys.path 中
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config import SNIPPETS, _write_local, _read_local  # noqa: E402
import config as _cfg  # noqa: E402


@pytest.fixture(autouse=True)
def isolated_snippets(tmp_path, monkeypatch):
    """每个测试用独立的临时目录，不污染真实数据。"""
    fake_file = tmp_path / "snippets_local.json"
    monkeypatch.setattr(_cfg, "LOCAL_SNIPPETS_FILE", fake_file)
    yield fake_file


# ── 基本读写 ──────────────────────────────────────────────────────────────────

class TestReadWrite:
    def test_write_then_read_returns_same_value(self, isolated_snippets):
        _write_local("total_score", "42")
        assert _read_local("total_score") == "42"

    def test_write_preserves_other_keys(self, isolated_snippets):
        _write_local("total_score", "100")
        _write_local("healthy", "7")
        assert _read_local("total_score") == "100"
        assert _read_local("healthy") == "7"

    def test_multiple_writes_keep_latest(self, isolated_snippets):
        _write_local("total_score", "10")
        _write_local("total_score", "20")
        _write_local("total_score", "30")
        assert _read_local("total_score") == "30"


# ── 默认值 fallback ──────────────────────────────────────────────────────────

class TestDefaults:
    def test_read_missing_file_returns_default(self, isolated_snippets):
        # 文件不存在
        assert _read_local("healthy") == SNIPPETS["healthy"].default

    def test_read_missing_key_returns_default(self, isolated_snippets):
        _write_local("total_score", "42")
        # healthy 没被写过，应返回默认值
        assert _read_local("healthy") == SNIPPETS["healthy"].default


# ── JSON 损坏恢复 ─────────────────────────────────────────────────────────────

class TestCorruptionRecovery:
    def test_empty_file_recovers_on_write(self, isolated_snippets):
        """模拟 kill -9 导致空文件的场景。"""
        isolated_snippets.write_text("", encoding="utf-8")

        # 写入一个值——不应该崩溃，应该重建所有默认值 + 新写入的值
        _write_local("total_score", "50")
        assert _read_local("total_score") == "50"

        # 其他字段应该是默认值（而不是丢失）
        data = json.loads(isolated_snippets.read_text(encoding="utf-8"))
        assert "healthy" in data
        assert data["healthy"] == SNIPPETS["healthy"].default

    def test_truncated_json_recovers_on_write(self, isolated_snippets):
        """模拟 kill -9 导致 JSON 截断的场景。"""
        isolated_snippets.write_text('{"total_score": "100", "heal', encoding="utf-8")

        _write_local("total_score", "999")
        assert _read_local("total_score") == "999"

    def test_garbage_content_recovers(self, isolated_snippets):
        """文件内容完全是垃圾。"""
        isolated_snippets.write_text("这不是JSON！@#$%", encoding="utf-8")

        _write_local("healthy", "5")
        assert _read_local("healthy") == "5"

    def test_empty_file_read_returns_default(self, isolated_snippets):
        """读空文件时不崩溃，返回默认值。"""
        isolated_snippets.write_text("", encoding="utf-8")
        assert _read_local("healthy") == SNIPPETS["healthy"].default


# ── 原子写入验证 ──────────────────────────────────────────────────────────────

class TestAtomicWrite:
    def test_write_uses_rename_not_direct_write(self, isolated_snippets, monkeypatch):
        """验证 _write_local 使用 tmp → rename 模式。"""
        rename_calls = []
        original_rename = Path.rename

        def spy_rename(self, target):
            rename_calls.append((str(self), str(target)))
            return original_rename(self, target)

        monkeypatch.setattr(Path, "rename", spy_rename)

        _write_local("total_score", "42")

        # 应该有一次 rename 调用，且源文件是 .tmp
        assert len(rename_calls) == 1
        src, dst = rename_calls[0]
        assert src.endswith(".tmp")
        assert dst == str(isolated_snippets)

    def test_original_survives_if_tmp_write_fails(self, isolated_snippets):
        """如果临时文件写入失败，原文件应完好。"""
        # 先写入正常数据
        _write_local("total_score", "100")
        assert _read_local("total_score") == "100"

        # 把 .tmp 所在目录设为只读，让 tmp.write_text 失败
        tmp_path = isolated_snippets.with_suffix(".tmp")

        original_content = isolated_snippets.read_text(encoding="utf-8")

        # 尝试写入，模拟失败（通过让 rename 的源文件被拦截）
        import unittest.mock as mock
        with mock.patch.object(Path, "write_text", side_effect=OSError("模拟磁盘满")):
            with pytest.raises(OSError):
                _write_local("total_score", "999")

        # 原文件内容应该完全不变
        assert isolated_snippets.read_text(encoding="utf-8") == original_content
        assert json.loads(original_content)["total_score"] == "100"
