"""
jury/prompts.py — 陪审员 prompt 模板
=====================================
构建发给每位陪审员的评审 prompt，包含：
  - 角色人设（从 static/companions/xxx.md 加载）
  - 评分标准
  - 待审问题 + 答案 + 辩护意见
  - 输出格式约束（JSON）
"""

from __future__ import annotations

from pathlib import Path

_COMPANIONS_DIR = Path(__file__).parent.parent / "static" / "companions"

# ── 评分标准（所有陪审员共用）──────────────────────────────────────────────────

RUBRIC = """\
你是一位公正严格的学习成果评审员。你需要根据以下标准评估学生的回答：

【评分维度】
1. 核心知识覆盖：回答是否涵盖了问题要求的关键知识点？
2. 准确性：回答中是否存在明显的事实错误或概念混淆？
3. 深度与逻辑：回答是否展现了深入思考和逻辑推理，而非表面复述？

【投票选项】
- "approve"（赞成）：回答整体合格，核心知识点已覆盖，无重大错误
- "reject"（反对）：回答存在严重缺陷（核心知识缺失、重大事实错误、明显敷衍）
- "suspend"（悬置）：你无法仅从答案判断学生是否真正理解，需要追问一个简短问题来验证

【重要原则】
- 不要求完美，允许小瑕疵
- 重点关注「是否真正理解」而非「格式是否漂亮」
- 如果选择 "suspend"，你必须提供一个简短追问（限50字以内），且追问应该足够简单，学生能在50字以内作答
"""

# ── 输出格式约束 ──────────────────────────────────────────────────────────────

OUTPUT_FORMAT = """\
你必须以纯 JSON 格式回复，不要包含 markdown 代码块标记，不要加任何解释文字。
JSON 格式如下：
{
  "vote": "approve 或 reject 或 suspend",
  "reasoning": "你的判断理由（100字以内）",
  "suspension_question": "仅当 vote 为 suspend 时填写追问问题（50字以内），否则留空字符串"
}
"""


def build_juror_prompt(
    juror_name: str,
    question: str,
    answer: str,
    defense: str = "",
) -> str:
    """构建完整的陪审员评审 prompt。"""

    # 加载角色人设
    profile_path = _COMPANIONS_DIR / f"{juror_name}.md"
    if profile_path.exists():
        persona = profile_path.read_text(encoding="utf-8").strip()
        persona_block = (
            f"【你的角色身份】\n"
            f"你是「{juror_name}」，以下是你的角色资料：\n{persona}\n\n"
            f"评审时请保持角色的性格特点和语气，但必须公正客观。\n"
        )
    else:
        persona_block = f"【你的角色身份】\n你是评审员「{juror_name}」。\n"

    # 组装
    parts = [
        persona_block,
        f"【评审标准】\n{RUBRIC}\n",
        f"【待审问题】\n{question}\n",
        f"【学生的回答】\n{answer}\n",
    ]

    if defense.strip():
        parts.append(f"【辩护意见（来自学生的学习助手）】\n{defense}\n")
        parts.append(
            "注意：辩护意见仅供参考，你应该独立判断，不受辩护者影响。\n"
        )

    parts.append(f"【输出格式要求】\n{OUTPUT_FORMAT}")

    return "\n".join(parts)


def build_suspension_followup_prompt(
    juror_name: str,
    original_question: str,
    original_answer: str,
    suspension_question: str,
    student_reply: str,
) -> str:
    """构建悬置追问后的最终评判 prompt。"""

    profile_path = _COMPANIONS_DIR / f"{juror_name}.md"
    if profile_path.exists():
        persona = profile_path.read_text(encoding="utf-8").strip()
        persona_block = f"你是「{juror_name}」。\n{persona}\n\n"
    else:
        persona_block = f"你是评审员「{juror_name}」。\n"

    return (
        f"{persona_block}"
        f"你之前审查了一个学生的回答，选择了悬置并追问。以下是完整上下文：\n\n"
        f"【原始问题】\n{original_question}\n\n"
        f"【学生原始回答】\n{original_answer}\n\n"
        f"【你的追问】\n{suspension_question}\n\n"
        f"【学生的临场回答（限时2分钟，不可查阅资料）】\n"
        f"{student_reply if student_reply.strip() else '（学生未在限时内作答）'}\n\n"
        f"现在请给出最终判断。你只能投 approve 或 reject，不能再次悬置。\n\n"
        f"【输出格式要求】\n{OUTPUT_FORMAT}"
    )
