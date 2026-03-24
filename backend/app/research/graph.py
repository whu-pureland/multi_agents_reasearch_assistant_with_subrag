from __future__ import annotations

from time import perf_counter
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, TypedDict

from langgraph.graph import END, StateGraph

from app.core.storage import JobStore
from app.research.llm import LlmClient, LlmMessage
from app.research.rag_sub_agent import RagSubAgent
from app.research.source_quality import aggregate_quality, score_source
from app.research.tool_aware_agent import ToolAwareSimpleAgent, ToolCallMeta, ToolCallObserver
from app.tools.registry import ToolRegistry


class ResearchState(TypedDict, total=False):
    job_id: str
    query: str
    settings: dict[str, Any]
    todos: list[dict[str, Any]]
    current_todo_id: str | None
    sources: list[dict[str, Any]]
    notes: list[dict[str, Any]]
    report: str | None


@dataclass
class GraphContext:
    job_id: str
    emit: Callable[[dict[str, Any]], None]
    persist: Callable[[dict[str, Any]], None]


def _fallback_plan(query: str, max_todos: int) -> list[dict[str, Any]]:
    _ = query
    seed = [
        "澄清问题与范围（定义关键术语、边界条件）",
        "收集权威背景（官方/学术/标准定义）",
        "梳理关键机制与方法（对比不同路线）",
        "整理最新进展与代表性案例",
        "总结风险、局限与未解问题",
        "形成结构化大纲与结论",
    ]
    items = seed[: max(3, min(max_todos, len(seed)))]
    return [{"id": str(i + 1), "title": t, "status": "pending", "note_id": None} for i, t in enumerate(items)]


async def plan_node(state: ResearchState, ctx: GraphContext) -> dict[str, Any]:
    ctx.emit({"type": "node_started", "node": "plan"})
    max_todos = int(state.get("settings", {}).get("max_todos", 8))
    llm = LlmClient()
    existing_todos = list(state.get("todos", []) or [])
    already_progressed = bool(state.get("notes")) or bool(state.get("report")) or any(
        (t.get("status") not in {None, "", "pending"}) or bool(t.get("note_id")) for t in existing_todos
    )
    if already_progressed and existing_todos:
        ctx.emit({"type": "plan_skipped", "reason": "existing_progress", "count": len(existing_todos)})
        ctx.emit({"type": "node_completed", "node": "plan"})
        return {"todos": existing_todos}

    planned = _fallback_plan(state["query"], max_todos=max_todos)

    if llm.available():
        prompt = (
            "你是研究助理。将用户问题拆解为可执行 TODO 列表（3-10 条），每条一句话。"
            "输出 JSON 数组，每项包含 id(从1开始的字符串) 与 title。只输出 JSON。"
        )
        observer = ToolCallObserver(ctx.emit)
        meta = ToolCallMeta(job_id=state["job_id"], node="plan", todo_id=None)
        observer.on_start("llm.chat", {"purpose": "plan_todos"}, meta)
        t0 = perf_counter()
        try:
            text = await llm.complete(
                [LlmMessage(role="system", content=prompt), LlmMessage(role="user", content=state["query"])],
                temperature=0.2,
            )
            observer.on_success("llm.chat", {"chars": len(text)}, meta, int((perf_counter() - t0) * 1000))
        except Exception as e:
            observer.on_error("llm.chat", str(e), meta, int((perf_counter() - t0) * 1000))
            text = ""
        try:
            import json

            parsed = json.loads(text)
            if isinstance(parsed, list) and parsed:
                planned = [
                    {
                        "id": str(item.get("id")),
                        "title": str(item.get("title")),
                        "status": "pending",
                        "note_id": None,
                    }
                    for item in parsed[:max_todos]
                    if item.get("id") and item.get("title")
                ] or planned
        except Exception:
            pass

    merged_items: list[dict[str, Any]] = []
    seen_titles: set[str] = set()
    for item in [*planned, *existing_todos]:
        title = str((item or {}).get("title") or "").strip()
        if not title or title in seen_titles:
            continue
        seen_titles.add(title)
        merged_items.append({"title": title})
    merged_items = merged_items[:max_todos] or [{"title": t.get("title")} for t in planned[:max_todos]]

    todos = [
        {"id": str(i + 1), "title": str(it.get("title") or ""), "status": "pending", "note_id": None}
        for i, it in enumerate(merged_items)
        if str(it.get("title") or "").strip()
    ]

    ctx.emit({"type": "plan_created", "todos": todos})
    ctx.persist({"todos": todos})
    ctx.emit({"type": "node_completed", "node": "plan"})
    return {"todos": todos}


async def next_todo_node(state: ResearchState, ctx: GraphContext) -> dict[str, Any]:
    ctx.emit({"type": "node_started", "node": "next_todo"})
    todos: list[dict[str, Any]] = list(state.get("todos", []) or [])
    try:
        job = JobStore.default().get_job(str(state.get("job_id") or ""))
    except Exception:
        job = None
    if job is not None and job.todos:
        todos = [t.model_dump() for t in job.todos]
    for todo in todos:
        if todo.get("status") == "pending":
            todo["status"] = "in_progress"
            ctx.emit({"type": "todo_started", "todo": todo})
            ctx.persist({"todos": todos})
            ctx.emit({"type": "node_completed", "node": "next_todo", "todo_id": todo.get("id")})
            return {"todos": todos, "current_todo_id": todo.get("id")}
    ctx.emit({"type": "node_completed", "node": "next_todo", "todo_id": None})
    return {"current_todo_id": None}


def _select_current_todo(state: ResearchState) -> dict[str, Any] | None:
    todo_id = state.get("current_todo_id")
    if not todo_id:
        return None
    for todo in state.get("todos", []):
        if todo.get("id") == todo_id:
            return todo
    return None


async def retrieve_node(state: ResearchState, ctx: GraphContext) -> dict[str, Any]:
    ctx.emit({"type": "node_started", "node": "retrieve", "todo_id": state.get("current_todo_id")})
    todo = _select_current_todo(state)
    if todo is None:
        return {}

    settings = state.get("settings", {})
    web_k = int(settings.get("web_results_per_todo", 5))
    include_private = bool(settings.get("include_private_knowledge", True))
    semantic_k = int(settings.get("private_semantic_top_k", 5))
    enable_mcp = bool(settings.get("enable_mcp_tools", False))

    query = f"{state['query']}\n子任务：{todo.get('title')}"
    observer = ToolCallObserver(ctx.emit)
    agent = ToolAwareSimpleAgent(registry=ToolRegistry.default(), observer=observer)
    meta = ToolCallMeta(job_id=state["job_id"], node="retrieve", todo_id=str(todo.get("id") or ""))

    web_items = agent.call_tool("web.search", {"query": query, "max_results": web_k}, meta=meta)
    if not isinstance(web_items, list):
        web_items = []

    sources: list[dict[str, Any]] = [*state.get("sources", [])]
    for i, item in enumerate(web_items):
        title = str((item or {}).get("title") or "")
        url = str((item or {}).get("url") or "")
        snippet = (item or {}).get("snippet")
        signals = score_source(url=url, title=title, snippet=str(snippet) if snippet is not None else None)
        sources.append(
            {
                "id": f"web:{todo['id']}:{i}",
                "title": title,
                "url": url,
                "snippet": snippet,
                "provider": "web",
                "quality_score": aggregate_quality(signals),
                "metadata": {"signals": [s.__dict__ for s in signals]},
            }
        )

    if include_private:
        rag = RagSubAgent(job_id=state["job_id"], observer=observer)
        sources.extend(
            rag.retrieve_private_sources(
                query=query,
                todo_id=str(todo["id"]),
                bm25_k=5,
                semantic_k=semantic_k,
                meta=meta,
            )
        )

    if enable_mcp:
        try:
            import json
            result = agent.call_tool("demo.sql_query", {"query": query}, meta=meta)
            sources.append(
                {
                    "id": f"mcp:{todo['id']}:demo.sql_query",
                    "title": "企业数据库（MCP Demo）",
                    "url": "mcp://demo/sql_query",
                    "snippet": json.dumps(result, ensure_ascii=False)[:280],
                    "provider": "mcp",
                    "quality_score": 0.7,
                    "metadata": {"tool": "demo.sql_query"},
                }
            )
        except Exception as e:
            ctx.emit({"type": "mcp_tool_failed", "tool": "demo.sql_query", "error": str(e), "todo_id": todo["id"]})

    ctx.emit({"type": "sources_collected", "todo_id": todo["id"], "count": len(web_items)})
    ctx.persist({"sources": sources})
    ctx.emit({"type": "node_completed", "node": "retrieve", "todo_id": todo["id"]})
    return {"sources": sources}


async def synthesize_node(state: ResearchState, ctx: GraphContext) -> dict[str, Any]:
    ctx.emit({"type": "node_started", "node": "synthesize", "todo_id": state.get("current_todo_id")})
    todo = _select_current_todo(state)
    if todo is None:
        return {}

    todo_id = str(todo["id"])
    sources = [
        s
        for s in state.get("sources", [])
        if str(s.get("id", "")).startswith(("web:" + todo_id, "local:" + todo_id))
    ]
    top = sorted(sources, key=lambda s: float(s.get("quality_score") or 0.0), reverse=True)[:8]

    llm = LlmClient()
    content = ""
    if llm.available() and top:
        prompt = (
            "你是研究助理。根据给定的来源摘要，写出该子任务的研究笔记（Markdown）。"
            "要求：1) 先给3-5条要点；2) 再给一段解释；3) 最后列出引用来源id列表。"
        )
        sources_text = "\n".join([f"[{s['id']}] {s['title']} - {s.get('snippet') or ''}" for s in top])
        observer = ToolCallObserver(ctx.emit)
        meta = ToolCallMeta(job_id=state["job_id"], node="synthesize", todo_id=todo_id)
        observer.on_start("llm.chat", {"purpose": "synthesize_note"}, meta)
        t0 = perf_counter()
        try:
            content = await llm.complete(
                [
                    LlmMessage(role="system", content=prompt),
                    LlmMessage(role="user", content=f"子任务：{todo.get('title')}\n\n来源：\n{sources_text}"),
                ],
                temperature=0.2,
            )
            observer.on_success("llm.chat", {"chars": len(content)}, meta, int((perf_counter() - t0) * 1000))
        except Exception as e:
            observer.on_error("llm.chat", str(e), meta, int((perf_counter() - t0) * 1000))
            content = ""

    if not content:
        bullets = "\n".join([f"- {s['title']}（{s['url']}）" for s in top[:5]]) or "-（无可用来源）"
        content = (
            "## 要点\n"
            f"{bullets}\n\n"
            "## 说明\n"
            "基于当前可检索信息生成占位笔记；配置 LLM 后可获得更高质量内容。\n"
        )

    note_id = f"note:{todo_id}"
    note = {
        "todo_id": todo_id,
        "title": str(todo.get("title") or ""),
        "content_md": content,
        "source_ids": [s["id"] for s in top],
    }

    notes = [n for n in state.get("notes", []) if n.get("todo_id") != todo_id]
    notes.append(note)

    todos = state.get("todos", [])
    for t in todos:
        if t.get("id") == todo_id:
            t["status"] = "done"
            t["note_id"] = note_id
            break

    ctx.emit({"type": "todo_completed", "todo_id": todo_id})
    ctx.persist({"notes": notes, "todos": todos})
    ctx.emit({"type": "node_completed", "node": "synthesize", "todo_id": todo_id})
    return {"notes": notes, "todos": todos}


async def report_node(state: ResearchState, ctx: GraphContext) -> dict[str, Any]:
    ctx.emit({"type": "node_started", "node": "report"})
    llm = LlmClient()
    notes = state.get("notes", [])
    sources = state.get("sources", [])

    outline = "\n".join([f"- {n.get('title')}" for n in notes]) or "-（无）"
    content = ""

    if llm.available() and notes:
        prompt = (
            "你是资深研究员。基于研究笔记生成结构化长报告（Markdown）。"
            "包含：摘要、背景、方法/现状、关键发现、证据表、风险与局限、结论与下一步。"
            "尽量引用来源（用来源id）。"
        )
        notes_text = "\n\n".join([f"### {n['title']}\n{n['content_md']}" for n in notes])
        observer = ToolCallObserver(ctx.emit)
        meta = ToolCallMeta(job_id=state["job_id"], node="report", todo_id=None)
        observer.on_start("llm.chat", {"purpose": "draft_report"}, meta)
        t0 = perf_counter()
        try:
            content = await llm.complete(
                [
                    LlmMessage(role="system", content=prompt),
                    LlmMessage(
                        role="user",
                        content=f"主题：{state['query']}\n\n大纲：\n{outline}\n\n笔记：\n{notes_text}",
                    ),
                ],
                temperature=0.2,
            )
            observer.on_success("llm.chat", {"chars": len(content)}, meta, int((perf_counter() - t0) * 1000))
        except Exception as e:
            observer.on_error("llm.chat", str(e), meta, int((perf_counter() - t0) * 1000))
            content = ""

    if not content:
        content = "# 研究报告（占位）\n\n"
        content += f"## 研究问题\n{state['query']}\n\n"
        content += "## 笔记汇总\n"
        for n in notes:
            content += f"\n### {n.get('title')}\n{n.get('content_md')}\n"
        content += "\n## 来源\n"
        for s in sorted(sources, key=lambda x: float(x.get("quality_score") or 0.0), reverse=True)[:20]:
            content += f"- [{s['id']}] {s['title']} - {s['url']}\n"

    ctx.emit({"type": "report_ready"})
    ctx.persist({"report": content})
    ctx.emit({"type": "node_completed", "node": "report"})
    return {"report": content}


async def fact_check_node(state: ResearchState, ctx: GraphContext) -> dict[str, Any]:
    ctx.emit({"type": "node_started", "node": "fact_check"})
    settings = state.get("settings", {})
    if not bool(settings.get("enable_fact_check", True)):
        ctx.emit({"type": "fact_check_skipped", "reason": "disabled"})
        ctx.emit({"type": "node_completed", "node": "fact_check"})
        return {}

    report = str(state.get("report") or "")
    if not report.strip():
        return {}

    llm = LlmClient()
    if not llm.available():
        ctx.emit({"type": "fact_check_skipped", "reason": "llm_unavailable"})
        ctx.emit({"type": "node_completed", "node": "fact_check"})
        return {}

    sources_all = list(state.get("sources", []))
    if bool(settings.get("include_private_knowledge", True)) and int(settings.get("private_semantic_top_k", 5)) > 0:
        observer = ToolCallObserver(ctx.emit)
        meta = ToolCallMeta(job_id=state["job_id"], node="fact_check", todo_id=None)
        rag = RagSubAgent(job_id=state["job_id"], observer=observer)
        extras = rag.retrieve_private_sources(
            query=str(state.get("query") or ""),
            todo_id="report",
            bm25_k=0,
            semantic_k=min(8, int(settings.get("private_semantic_top_k", 5))),
            meta=meta,
        )
        known_ids = {str(s.get("id")) for s in sources_all}
        for s in extras:
            if str(s.get("id")) not in known_ids:
                sources_all.append(s)
        ctx.persist({"sources": sources_all})

    sources = sorted(sources_all, key=lambda x: float(x.get("quality_score") or 0.0), reverse=True)[:30]
    evidence = "\n".join(
        [f"[{s['id']}] {s.get('title') or ''} - {(s.get('snippet') or '')[:240]}" for s in sources]
    )

    prompt = (
        "你是事实核查与知识对齐智能体。给你：研究报告草稿 + 证据列表（来源id/标题/摘要）。\n"
        "任务：\n"
        "1) 识别关键事实表述中缺乏证据支撑或可能错误的内容；\n"
        "2) 改写为有证据支撑的表述并在关键句后标注来源id（例如：...（来源：web:1:0））；\n"
        "3) 对于无法证实的内容，改写为不确定/假设并明确标注；\n"
        "4) 追加一个“证据表”小节，列出最重要的 8-12 条证据（来源id + 一句话用途）。\n"
        "只输出修订后的 Markdown。"
    )

    observer = ToolCallObserver(ctx.emit)
    meta_llm = ToolCallMeta(job_id=state["job_id"], node="fact_check", todo_id=None)
    observer.on_start("llm.chat", {"purpose": "fact_check"}, meta_llm)
    t0 = perf_counter()
    try:
        checked = await llm.complete(
            [
                LlmMessage(role="system", content=prompt),
                LlmMessage(role="user", content=f"证据列表：\n{evidence}\n\n报告草稿：\n{report}"),
            ],
            temperature=0.0,
        )
        observer.on_success("llm.chat", {"chars": len(checked)}, meta_llm, int((perf_counter() - t0) * 1000))
    except Exception as e:
        observer.on_error("llm.chat", str(e), meta_llm, int((perf_counter() - t0) * 1000))
        checked = ""
    checked = checked.strip()
    if not checked:
        return {}

    ctx.emit({"type": "fact_check_completed"})
    ctx.persist({"report": checked})
    ctx.emit({"type": "node_completed", "node": "fact_check"})
    return {"report": checked, "sources": sources_all}


def build_graph(ctx: GraphContext):
    graph = StateGraph(ResearchState)

    async def plan(state: ResearchState) -> dict[str, Any]:
        return await plan_node(state, ctx)

    async def next_todo(state: ResearchState) -> dict[str, Any]:
        return await next_todo_node(state, ctx)

    async def retrieve(state: ResearchState) -> dict[str, Any]:
        return await retrieve_node(state, ctx)

    async def synthesize(state: ResearchState) -> dict[str, Any]:
        return await synthesize_node(state, ctx)

    async def report(state: ResearchState) -> dict[str, Any]:
        return await report_node(state, ctx)

    async def fact_check(state: ResearchState) -> dict[str, Any]:
        return await fact_check_node(state, ctx)

    graph.add_node("plan", plan)
    graph.add_node("next_todo", next_todo)
    graph.add_node("retrieve", retrieve)
    graph.add_node("synthesize", synthesize)
    graph.add_node("report", report)
    graph.add_node("fact_check", fact_check)

    graph.set_entry_point("plan")
    graph.add_edge("plan", "next_todo")

    def route_after_next(state: ResearchState) -> str:
        if not state.get("current_todo_id"):
            return "report"
        return "retrieve"

    graph.add_conditional_edges("next_todo", route_after_next, {"retrieve": "retrieve", "report": "report"})
    graph.add_edge("retrieve", "synthesize")
    graph.add_edge("synthesize", "next_todo")
    graph.add_edge("report", "fact_check")
    graph.add_edge("fact_check", END)

    return graph.compile()
