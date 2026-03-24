from __future__ import annotations

import re
from typing import Any


_ACTION_WORDS = (
    "分析",
    "总结",
    "调研",
    "研究",
    "对比",
    "比较",
    "评估",
    "设计",
    "实现",
    "方案",
    "原理",
    "优缺点",
    "落地",
    "怎么",
    "如何",
    "为什么",
    "是什么",
)


def query_needs_clarification(query: str) -> bool:
    q = (query or "").strip()
    if len(q) < 12:
        return True
    if len(q) < 32 and (not any(w in q for w in _ACTION_WORDS)) and (not re.search(r"[?？]", q)):
        return True
    if re.fullmatch(r"[a-zA-Z0-9_\\-]{2,12}", q):
        return True
    return False


def build_query_hint_event(query: str) -> dict[str, Any]:
    q = (query or "").strip()
    return {
        "type": "query_hint",
        "message": (
            "你的问题看起来偏泛/不够明确，建议补充：研究目标、范围边界、关注维度、时间范围、输出形式。\n"
            "可直接按这个模板重写：\n"
            "“请在【范围/时间】内，围绕【主题】从【维度1/维度2/维度3】做调研，并输出【报告结构/结论+证据】。”"
        ),
        "examples": [
            f"示例：请对“{q or '某主题'}”在 2024-2026 年的关键进展做总结，并给出 5 条可验证来源。",
            f"示例：请对“{q or '某主题'}”的主流方案做对比（成本/效果/风险/适用场景），最后给出建议。",
        ],
        "suggested_questions": [
            "你最关心的评价维度是什么？（成本/性能/安全/可维护性/合规…）",
            "需要覆盖的时间范围与地域范围？",
            "期望输出：长报告 / 要点清单 / 决策建议 / 代码实现？",
        ],
    }

