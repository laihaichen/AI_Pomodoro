"""
effects.py — 技能/助手效果类
======================================
Effect 代表"技能触发后对游戏状态产生什么变化"。
未来可按需继承 BaseEffect 创建具体效果类型：
  - HealthEffect（修改健康度）
  - ScoreEffect（修改积分）
  - FateEffect（修改命运值计算）
  - RestEffect（修改休息时间限制）
等。

当前阶段：仅保留基础骨架，具体执行逻辑待定义。
"""

from __future__ import annotations
import sys
from pathlib import Path
from typing import Any

_PROJECT_ROOT = Path(__file__).parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))
from config import HEALTH_FILE as _HEALTH_FILE  # noqa: E402


class BaseEffect:
    """所有技能效果的抽象基类。"""

    name: str = "base_effect"
    description: str = ""

    def __init__(self, **kwargs: Any) -> None:
        # 预留：子类通过 kwargs 传入参数
        self._params = kwargs

    def apply(self, context: dict) -> dict:
        """执行效果，并返回更新后的上下文。

        Args:
            context: 包含当前游戏状态的字典

        Returns:
            应用效果后的上下文字典（可以是修改后的原对象或新对象）
        """
        raise NotImplementedError

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}({self._params})"


class FinalFateEffect(BaseEffect):
    """修改最终命运值（final_fate）的效果。

    在 context["final_fate"] 上叠加一个固定的 delta。
    示例：
        FinalFateEffect(delta=+10)   # 命运值 +10
        FinalFateEffect(delta=-20)   # 命运值 -20
    """

    name = "final_fate_effect"
    description = "修改本轮最终命运值。"

    def __init__(self, delta: int) -> None:
        """
        Args:
            delta: 对命运值的修改量（正数为增益，负数为减益）
        """
        super().__init__(delta=delta)
        self.delta = delta

    def apply(self, context: dict) -> dict:
        """将 delta 叠加到 context['final_fate'] 上。

        若 context 中不含 'final_fate'，则跳过（安全降级）。
        """
        if "final_fate" in context:
            context["final_fate"] = context["final_fate"] + self.delta
        return context

    def __repr__(self) -> str:
        sign = "+" if self.delta >= 0 else ""
        return f"FinalFateEffect(delta={sign}{self.delta})"


class HealthEffect(BaseEffect):
    """修改健康度的效果。

    直接读写 data/health.txt，叠加一个固定 delta。
    示例：
        HealthEffect(delta=+1)   # 健康度 +1
        HealthEffect(delta=-2)   # 健康度 -2
    """

    name = "health_effect"
    description = "修改当前健康度。"

    def __init__(self, delta: int) -> None:
        super().__init__(delta=delta)
        self.delta = delta

    def apply(self, context: dict) -> dict:
        import mod.effects as _mod
        health_file = _mod._HEALTH_FILE
        try:
            current = int(health_file.read_text(encoding="utf-8").strip()) \
                      if health_file.exists() else 9
        except ValueError:
            current = 9
        new_val = max(0, current + self.delta)
        health_file.write_text(str(new_val), encoding="utf-8")
        context["health"] = new_val
        return context

    def __repr__(self) -> str:
        sign = "+" if self.delta >= 0 else ""
        return f"HealthEffect(delta={sign}{self.delta})"
