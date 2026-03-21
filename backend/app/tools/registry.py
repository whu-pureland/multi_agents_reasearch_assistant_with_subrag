from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from typing import Any, Callable

from app.mcp.manager import McpManager
from app.research.vector_knowledge import VectorKnowledgeBase
from app.research.web_search import web_search


@dataclass(frozen=True)
class ToolSpec:
    name: str
    description: str
    input_schema: dict[str, Any]
    origin: str
    handler: Callable[[dict[str, Any]], Any] | None = None


class ToolRegistry:
    def __init__(self, mcp: McpManager) -> None:
        self._mcp = mcp
        self._builtins: dict[str, ToolSpec] = {
            "web.search": ToolSpec(
                name="web.search",
                description="Web search returning title/url/snippet results (provider via WEB_SEARCH_PROVIDER).",
                origin="builtin",
                input_schema={
                    "type": "object",
                    "properties": {
                        "query": {"type": "string"},
                        "max_results": {"type": "integer"},
                        "search_depth": {"type": "string"},
                        "include_answer": {"type": "boolean"},
                        "include_raw_content": {"type": "boolean"},
                    },
                    "required": ["query"],
                },
                handler=self._web_search,
            ),
            "kb.vector_search": ToolSpec(
                name="kb.vector_search",
                description="Private semantic search over uploaded documents (ChromaDB).",
                origin="builtin",
                input_schema={
                    "type": "object",
                    "properties": {
                        "job_id": {"type": "string"},
                        "query": {"type": "string"},
                        "k": {"type": "integer"},
                    },
                    "required": ["job_id", "query"],
                },
                handler=self._vector_search,
            ),
        }

    @staticmethod
    @lru_cache
    def default() -> "ToolRegistry":
        return ToolRegistry(mcp=McpManager.default())

    def reload(self) -> None:
        self._mcp.reload()

    def list_tools(self) -> list[dict[str, Any]]:
        tools = [
            {
                "name": t.name,
                "description": t.description,
                "input_schema": t.input_schema,
                "origin": t.origin,
            }
            for t in self._builtins.values()
        ]
        tools.extend(self._mcp.list_tools())
        return sorted(tools, key=lambda x: x["name"])

    def call(self, name: str, arguments: dict[str, Any]) -> Any:
        if name in self._builtins:
            spec = self._builtins[name]
            if spec.handler is None:
                raise ValueError("Tool handler missing")
            return spec.handler(arguments)
        return self._mcp.call(name, arguments)

    @staticmethod
    def _web_search(args: dict[str, Any]) -> list[dict[str, Any]]:
        query = str(args.get("query") or "")
        max_results = int(args.get("max_results") or 5)
        options = {k: v for k, v in args.items() if k not in {"query", "max_results"}}
        results = web_search(query, max_results=max_results, options=options)
        return [{"title": r.title, "url": r.url, "snippet": r.snippet} for r in results]

    @staticmethod
    def _vector_search(args: dict[str, Any]) -> list[dict[str, Any]]:
        job_id = str(args.get("job_id") or "")
        query = str(args.get("query") or "")
        k = int(args.get("k") or 5)
        hits = VectorKnowledgeBase.for_job(job_id).search(query, k=k)
        return [{"chunk_id": h.chunk_id, "filename": h.filename, "text": h.text, "score": h.score} for h in hits]
