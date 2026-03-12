"""
jury/engine.py — 陪审团核心引擎
================================
并行调用 3 名陪审员（不同 AI 提供商），收集投票，产生判决。
支持悬置队列机制。
"""

from __future__ import annotations

import json
import re
import traceback
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path
from typing import Optional

from jury.providers import JUROR_MODELS, call_provider
from jury.prompts import build_juror_prompt, build_suspension_followup_prompt

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))
from config import JURY_STATE_FILE, HEALTH_FILE  # noqa: E402


# ── 数据结构 ──────────────────────────────────────────────────────────────────

@dataclass
class JurorVote:
    """单个陪审员的投票结果。"""
    juror_name: str
    provider: str
    model: str
    vote: str                    # "approve" | "reject" | "suspend"
    reasoning: str = ""
    suspension_question: str = ""
    error: str = ""              # 调用失败时的错误信息


@dataclass
class JuryVerdict:
    """陪审团最终判决。"""
    outcome: str                 # "health_unchanged" | "health_minus_1" | "suspended"
    votes: list[JurorVote] = field(default_factory=list)
    suspension_queue: list[JurorVote] = field(default_factory=list)
    reject_count: int = 0
    approve_count: int = 0
    report: str = ""


# ── JSON 解析 ─────────────────────────────────────────────────────────────────

def _parse_juror_response(raw: str) -> dict:
    """从 AI 回复中提取 JSON 对象，多层容错处理。"""
    # 1. 尝试直接解析
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        pass

    # 2. 去掉 markdown 代码块标记
    cleaned = re.sub(r"^```(?:json)?\s*", "", raw.strip())
    cleaned = re.sub(r"\s*```$", "", cleaned)
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        pass

    # 3. 贪心匹配最外层 {...}（支持嵌套大括号）
    start = raw.find("{")
    if start >= 0:
        depth = 0
        for i in range(start, len(raw)):
            if raw[i] == "{":
                depth += 1
            elif raw[i] == "}":
                depth -= 1
                if depth == 0:
                    try:
                        return json.loads(raw[start:i + 1])
                    except json.JSONDecodeError:
                        break

    # 4. 关键词提取兜底：从原始文本中检测投票意图
    raw_lower = raw.lower()
    vote = "approve"  # 默认不惩罚

    # 检测 vote 关键词
    vote_match = re.search(r'"vote"\s*:\s*"(approve|reject|suspend)"', raw, re.IGNORECASE)
    if vote_match:
        vote = vote_match.group(1).lower()

    # 提取 reasoning
    reasoning = ""
    reason_match = re.search(r'"reasoning"\s*:\s*"([^"]*)', raw)
    if reason_match:
        reasoning = reason_match.group(1)

    # 提取 suspension_question
    sq = ""
    sq_match = re.search(r'"suspension_question"\s*:\s*"([^"]*)', raw)
    if sq_match:
        sq = sq_match.group(1)

    if vote_match:
        # 成功从关键词提取到投票
        return {"vote": vote, "reasoning": reasoning, "suspension_question": sq}

    # 5. 全部失败 → 默认 approve（不惩罚玩家）
    return {
        "vote": "approve",
        "reasoning": "提交的决议文书格式不规范，裁判长判定该票作废，视为弃权赞成",
        "suspension_question": "",
    }


# ── 单个陪审员调用 ────────────────────────────────────────────────────────────

def _call_single_juror(
    juror_name: str,
    provider: str,
    model: str,
    question: str,
    answer: str,
    defense: str,
) -> JurorVote:
    """调用单个陪审员，返回投票结果。"""
    try:
        prompt = build_juror_prompt(juror_name, question, answer, defense)
        raw = call_provider(provider, prompt, model)
        parsed = _parse_juror_response(raw)

        vote = parsed.get("vote", "approve").lower().strip()
        if vote not in ("approve", "reject", "suspend"):
            vote = "approve"

        sq = parsed.get("suspension_question", "").strip() if vote == "suspend" else ""
        # 投了 suspend 但没给追问 → 视为 approve
        if vote == "suspend" and not sq:
            vote = "approve"

        return JurorVote(
            juror_name=juror_name,
            provider=provider,
            model=model,
            vote=vote,
            reasoning=parsed.get("reasoning", ""),
            suspension_question=sq,
        )
    except Exception as exc:
        traceback.print_exc()
        return JurorVote(
            juror_name=juror_name,
            provider=provider,
            model=model,
            vote="approve",  # API 调用失败时不惩罚玩家
            reasoning=f"{juror_name} 未能按时出庭，视为弃权赞成",
            error="缺席",
        )


# ── 主审判流程 ────────────────────────────────────────────────────────────────

def run_jury_trial(
    question: str,
    answer: str,
    defense: str = "",
) -> JuryVerdict:
    """
    并行调用 3 名陪审员，收集投票，产生判决。
    
    Returns:
        JuryVerdict with outcome:
          - "health_unchanged": < 2 reject votes
          - "health_minus_1":   >= 2 reject votes
          - "suspended":        at least 1 juror voted suspend
    """
    # 读取陪审员列表
    state = json.loads(JURY_STATE_FILE.read_text(encoding="utf-8"))
    jurors = state.get("jurors", [])

    if len(jurors) == 0:
        return JuryVerdict(
            outcome="health_unchanged",
            report="⚠️ 无陪审团成员，跳过审判。",
        )

    # 并行调用（线程池，最多 3 个线程）
    votes: list[JurorVote] = []
    with ThreadPoolExecutor(max_workers=3) as pool:
        futures = {}
        for i, name in enumerate(jurors):
            model_cfg = JUROR_MODELS[i % len(JUROR_MODELS)]
            fut = pool.submit(
                _call_single_juror,
                juror_name=name,
                provider=model_cfg["provider"],
                model=model_cfg["model"],
                question=question,
                answer=answer,
                defense=defense,
            )
            futures[fut] = name

        for fut in as_completed(futures):
            votes.append(fut.result())

    # 按 jurors 顺序排序（保持稳定展示）
    order = {name: i for i, name in enumerate(jurors)}
    votes.sort(key=lambda v: order.get(v.juror_name, 99))

    # 处理悬置（仅在悬置结果可能改变判决时才进入追问）
    reject_count = sum(1 for v in votes if v.vote == "reject")
    suspensions = [v for v in votes if v.vote == "suspend"]
    if suspensions and reject_count < 2:
        # 悬置可能改变结果 → 进入追问环节
        return JuryVerdict(
            outcome="suspended",
            votes=votes,
            suspension_queue=suspensions,
            report=_generate_report(votes, "suspended"),
        )
    # 如果已有≥2票反对，把 suspend 视为弃权（不追问）

    # 统计投票
    reject_count = sum(1 for v in votes if v.vote == "reject")
    approve_count = sum(1 for v in votes if v.vote == "approve")

    outcome = "health_minus_1" if reject_count >= 2 else "health_unchanged"
    report = _generate_report(votes, outcome)

    return JuryVerdict(
        outcome=outcome,
        votes=votes,
        reject_count=reject_count,
        approve_count=approve_count,
        report=report,
    )


# ── 悬置追问处理 ──────────────────────────────────────────────────────────────

def resolve_suspension(
    juror_name: str,
    original_question: str,
    original_answer: str,
    suspension_question: str,
    student_reply: str,
) -> JurorVote:
    """
    将学生对追问的回答发回给发起悬置的陪审员，获取最终投票。
    """
    # 找到该陪审员对应的 provider/model
    state = json.loads(JURY_STATE_FILE.read_text(encoding="utf-8"))
    jurors = state.get("jurors", [])

    idx = jurors.index(juror_name) if juror_name in jurors else 0
    model_cfg = JUROR_MODELS[idx % len(JUROR_MODELS)]

    try:
        prompt = build_suspension_followup_prompt(
            juror_name, original_question, original_answer,
            suspension_question, student_reply,
        )
        raw = call_provider(model_cfg["provider"], prompt, model_cfg["model"])
        parsed = _parse_juror_response(raw)

        vote = parsed.get("vote", "reject").lower().strip()
        if vote not in ("approve", "reject"):
            vote = "reject"  # 追问后不允许再次悬置

        return JurorVote(
            juror_name=juror_name,
            provider=model_cfg["provider"],
            model=model_cfg["model"],
            vote=vote,
            reasoning=parsed.get("reasoning", ""),
        )
    except Exception as exc:
        traceback.print_exc()
        return JurorVote(
            juror_name=juror_name,
            provider=model_cfg["provider"],
            model=model_cfg["model"],
            vote="approve",  # 失败不惩罚
            error=str(exc),
        )


# ── 最终判决计算 ──────────────────────────────────────────────────────────────

def finalize_verdict(all_votes: list[JurorVote]) -> JuryVerdict:
    """
    所有投票（含悬置解决后的）汇总，产生最终判决。
    """
    reject_count = sum(1 for v in all_votes if v.vote == "reject")
    approve_count = sum(1 for v in all_votes if v.vote == "approve")

    outcome = "health_minus_1" if reject_count >= 2 else "health_unchanged"
    report = _generate_report(all_votes, outcome)

    return JuryVerdict(
        outcome=outcome,
        votes=all_votes,
        reject_count=reject_count,
        approve_count=approve_count,
        report=report,
    )


# ── 报告生成 ──────────────────────────────────────────────────────────────────

def _vote_emoji(vote: str) -> str:
    return {"approve": "🟢", "reject": "🔴", "suspend": "🟡"}.get(vote, "⚪")


def _generate_report(votes: list[JurorVote], outcome: str) -> str:
    """生成可读的审议报告（纯文本）。"""
    lines = ["⚖️ 陪审团审议报告", "=" * 40, ""]

    for v in votes:
        emoji = _vote_emoji(v.vote)
        status = {"approve": "赞成", "reject": "反对", "suspend": "悬置"}.get(v.vote, v.vote)
        lines.append(f"{emoji} {v.juror_name}：{status}")
        if v.reasoning:
            lines.append(f"   理由：{v.reasoning}")
        if v.suspension_question:
            lines.append(f"   追问：{v.suspension_question}")
        if v.error:
            lines.append(f"   📌 {v.error}")
        lines.append("")

    lines.append("-" * 40)
    if outcome == "health_minus_1":
        lines.append("📍 判决：❌ 健康度 -1")
    elif outcome == "health_unchanged":
        lines.append("📍 判决：✅ 健康度不变")
    elif outcome == "suspended":
        lines.append("📍 判决：🟡 悬置中，等待追问回答")

    return "\n".join(lines)


# ── 状态持久化辅助 ────────────────────────────────────────────────────────────

def save_trial_to_history(
    question: str,
    answer: str,
    verdict: JuryVerdict,
) -> None:
    """将本次审判完整记录追加到 jury_state.json 的 history 中。"""
    state = json.loads(JURY_STATE_FILE.read_text(encoding="utf-8"))

    record = {
        "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "question": question,
        "answer": answer,
        "votes": [asdict(v) for v in verdict.votes],
        "outcome": verdict.outcome,
        "reject_count": verdict.reject_count,
        "approve_count": verdict.approve_count,
        "report": verdict.report,
    }

    if "history" not in state:
        state["history"] = []
    state["history"].append(record)
    state["status"] = "idle"  # 审判完毕，回到 idle
    state["votes"] = []
    state["suspension_queue"] = []
    state["suspension_index"] = 0

    JURY_STATE_FILE.write_text(
        json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def apply_health_penalty() -> int:
    """健康度 -1，返回新健康度值。"""
    try:
        current = int(HEALTH_FILE.read_text(encoding="utf-8").strip())
    except Exception:
        current = 9
    new_val = max(0, current - 1)
    HEALTH_FILE.write_text(str(new_val), encoding="utf-8")
    return new_val
