from __future__ import annotations

import asyncio
from typing import Any

from app.core.storage import JobStore
from app.research.graph import GraphContext, build_graph


def _emit_factory(store: JobStore, job_id: str):
    def emit(event: dict[str, Any]) -> None:
        store.append_event(job_id, event)

    return emit


def _persist_factory(store: JobStore, job_id: str):
    def persist(patch: dict[str, Any]) -> None:
        try:
            store.update_job(job_id, patch)
        except Exception:
            return

    return persist


async def _run(job_id: str) -> None:
    store = JobStore.default()
    job = store.get_job(job_id)
    if job is None:
        return
    store.update_job(job_id, {"status": "running", "error": None})

    emit = _emit_factory(store, job_id)
    persist = _persist_factory(store, job_id)
    ctx = GraphContext(job_id=job_id, emit=emit, persist=persist)
    graph = build_graph(ctx)
    store.append_event(job_id, {"type": "job_started"})

    state = {
        "job_id": job.id,
        "query": job.query,
        "settings": job.settings.model_dump(),
        "todos": [t.model_dump() for t in job.todos],
        "sources": [s.model_dump() for s in job.sources],
        "notes": [n.model_dump() for n in job.notes],
        "report": job.report,
        "current_todo_id": None,
    }

    try:
        result = await graph.ainvoke(state)
        store.update_job(
            job_id,
            {
                "status": "succeeded",
                "todos": result.get("todos", []),
                "sources": result.get("sources", []),
                "notes": result.get("notes", []),
                "report": result.get("report"),
                "error": None,
            },
        )
    except Exception as e:
        store.update_job(job_id, {"status": "failed", "error": str(e)})
        store.append_event(job_id, {"type": "job_failed", "error": str(e)})


def run_job(job_id: str) -> None:
    asyncio.run(_run(job_id))
