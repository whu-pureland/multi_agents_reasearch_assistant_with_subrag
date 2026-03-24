from __future__ import annotations

import re
from dataclasses import dataclass
from time import perf_counter
from typing import Any

from app.core.storage import JobStore
from app.research.llm import LlmClient, LlmMessage
from app.research.models import Job
from app.research.rag_sub_agent import RagSubAgent


@dataclass(frozen=True)
class InteractionResult:
    added_todos: list[dict[str, Any]]
    assistant_answer: str | None
    intent: str


_TODO_KEYWORDS = (
    "增加",
    "新增",
    "添加",
    "加入",
    "补充",
    "追加",
    "扩展",
    "深入",
    "再研究",
    "再查",
    "todo",
    "TODO",
)

_QUESTION_HINTS = ("如何", "为什么", "怎么", "是否", "能否", "可否", "区别", "对比", "比较", "是什么")


def _looks_like_question(text: str) -> bool:
    t = text.strip()
    if not t:
        return False
    if ("?" in t) or ("？" in t):
        return True
    return any(t.startswith(x) for x in _QUESTION_HINTS)


def _wants_todo_update(text: str) -> bool:
    t = text.strip()
    if not t:
        return False
    return any(k in t for k in _TODO_KEYWORDS)


def _next_todo_id(existing: list[dict[str, Any]]) -> str:
    max_id = 0
    for t in existing:
        raw = str((t or {}).get("id") or "").strip()
        if raw.isdigit():
            max_id = max(max_id, int(raw))
    return str(max_id + 1)


def _extract_todo_title(text: str) -> str:
    t = text.strip()
    match = re.match(r"^(?:todo|TODO)\s*[:：]\s*(.+)$", t)
    if match:
        t = match.group(1).strip()
    t = re.sub(r"^\s*(请|麻烦|帮我|帮忙)\s*", "", t)
    return t[:120] if t else "补充研究点"


async def _draft_answer(job: Job, question: str) -> str:
    llm = LlmClient()
    if not llm.available():
        return "已收到你的问题。但当前未配置 LLM，无法生成回答；你可以继续补充 TODO 或上传私有资料。"

    report = (job.report or "").strip()
    notes = job.notes
    notes_text = "\n\n".join([f"### {n.title}\n{n.content_md}" for n in notes]) if notes else ""

    sources_sorted = sorted(job.sources, key=lambda s: float(s.quality_score or 0.0), reverse=True)
    top_sources = sources_sorted[:12]
    sources_text = "\n".join(
        [f"[{s.id}] {s.title} - {(s.snippet or '')[:240]} ({s.url})" for s in top_sources]
    )

    private_text = ""
    if bool(job.settings.include_private_knowledge):
        semantic_k = max(0, int(job.settings.private_semantic_top_k or 0))
        if semantic_k > 0:
            rag = RagSubAgent(job_id=job.id)
            hits = rag.retrieve_private_sources(
                query=question,
                todo_id="qa",
                bm25_k=3,
                semantic_k=min(3, semantic_k),
                meta=None,
            )
            private_text = "\n".join([f"[{h['id']}] {h['title']} - {h['snippet']}" for h in hits[:6]])

    system_prompt = (
        "你是研究助理。基于给定上下文回答用户问题。\n"
        "要求：\n"
        "1) 先给结论，再给依据；\n"
        "2) 能引用时用“(来源: <id>)”标注；\n"
        "3) 若上下文不足，明确缺口并建议新增 TODO。\n"
        "只输出 Markdown。"
    )

    context_parts = []
    if report:
        context_parts.append(f"【报告】\n{report[:8000]}")
    if notes_text:
        context_parts.append(f"【笔记】\n{notes_text[:8000]}")
    if sources_text:
        context_parts.append(f"【来源摘要】\n{sources_text}")
    if private_text:
        context_parts.append(f"【私有资料摘要】\n{private_text}")
    context = "\n\n".join(context_parts) or "（无可用上下文）"

    user_prompt = f"问题：{question}\n\n上下文：\n{context}"
    return (await llm.complete([LlmMessage(role="system", content=system_prompt), LlmMessage(role="user", content=user_prompt)], temperature=0.2)).strip()


def _append_todo(store: JobStore, job: Job, title: str) -> dict[str, Any]:
    todos = [t.model_dump() for t in job.todos]
    item = {"id": _next_todo_id(todos), "title": title, "status": "pending", "note_id": None}
    todos.append(item)
    store.update_job(job.id, {"todos": todos})
    store.append_event(job.id, {"type": "todos_updated", "op": "add", "todo": item})
    return item


def handle_user_interaction(store: JobStore, job_id: str, text: str) -> InteractionResult:
    job = store.get_job(job_id)
    if job is None:
        raise KeyError(f"Job not found: {job_id}")

    wants_todo = _wants_todo_update(text)
    wants_answer = _looks_like_question(text)

    intent = "other"
    if wants_todo and wants_answer:
        intent = "todo_and_question"
    elif wants_todo:
        intent = "todo_update"
    elif wants_answer:
        intent = "question"

    store.append_event(job_id, {"type": "user_interaction", "intent": intent, "text": text})

    added: list[dict[str, Any]] = []
    if wants_todo:
        title = _extract_todo_title(text)
        added.append(_append_todo(store=store, job=store.get_job(job_id) or job, title=title))

    answer: str | None = None
    if wants_answer:
        t0 = perf_counter()
        try:
            answer = asyncio_run(_draft_answer(job=store.get_job(job_id) or job, question=text))
        except Exception as e:
            answer = f"生成回答失败：{e}"
        store.append_event(
            job_id,
            {
                "type": "assistant_answer",
                "question": text,
                "answer_md": answer,
                "elapsed_ms": int((perf_counter() - t0) * 1000),
            },
        )

    return InteractionResult(added_todos=added, assistant_answer=answer, intent=intent)


def asyncio_run(coro):  # type: ignore[no-untyped-def]
    try:
        import asyncio

        return asyncio.run(coro)
    except RuntimeError:
        loop = None
        try:
            import asyncio

            loop = asyncio.get_event_loop()
        except Exception:
            loop = None
        if loop and loop.is_running():
            future = asyncio.run_coroutine_threadsafe(coro, loop)
            return future.result()
        raise

