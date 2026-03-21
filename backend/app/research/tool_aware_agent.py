from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from time import perf_counter
from typing import Any

from app.tools.registry import ToolRegistry


@dataclass(frozen=True)
class ToolCallMeta:
    job_id: str
    node: str
    todo_id: str | None = None


class ToolCallObserver:
    def __init__(self, emit: Callable[[dict[str, Any]], None]) -> None:
        self.emit = emit

    def on_start(self, tool: str, args: dict[str, Any], meta: ToolCallMeta) -> None:
        safe_args = dict(args)
        if "query" in safe_args and isinstance(safe_args["query"], str):
            safe_args["query"] = safe_args["query"][:240]
        self.emit(
            {
                "type": "tool_call_started",
                "tool": tool,
                "node": meta.node,
                "todo_id": meta.todo_id,
                "args": safe_args,
            }
        )

    def on_success(self, tool: str, result: Any, meta: ToolCallMeta, duration_ms: int) -> None:
        preview = str(result)
        if len(preview) > 500:
            preview = preview[:500] + "..."
        self.emit(
            {
                "type": "tool_call_completed",
                "tool": tool,
                "node": meta.node,
                "todo_id": meta.todo_id,
                "duration_ms": duration_ms,
                "preview": preview,
            }
        )

    def on_error(self, tool: str, error: str, meta: ToolCallMeta, duration_ms: int) -> None:
        self.emit(
            {
                "type": "tool_call_failed",
                "tool": tool,
                "node": meta.node,
                "todo_id": meta.todo_id,
                "duration_ms": duration_ms,
                "error": error,
            }
        )


@dataclass
class ToolAwareSimpleAgent:
    registry: ToolRegistry
    observer: ToolCallObserver

    def call_tool(self, tool: str, args: dict[str, Any], meta: ToolCallMeta) -> Any:
        start = perf_counter()
        self.observer.on_start(tool=tool, args=args, meta=meta)
        try:
            result = self.registry.call(tool, args)
            duration_ms = int((perf_counter() - start) * 1000)
            self.observer.on_success(tool=tool, result=result, meta=meta, duration_ms=duration_ms)
            return result
        except Exception as e:
            duration_ms = int((perf_counter() - start) * 1000)
            self.observer.on_error(tool=tool, error=str(e), meta=meta, duration_ms=duration_ms)
            raise

