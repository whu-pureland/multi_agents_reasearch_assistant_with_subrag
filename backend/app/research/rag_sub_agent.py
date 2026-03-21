from __future__ import annotations

from dataclasses import dataclass
from time import perf_counter

from app.research.local_knowledge import LocalKnowledgeBase
from app.research.tool_aware_agent import ToolCallMeta, ToolCallObserver
from app.research.vector_knowledge import VectorKnowledgeBase, VectorHit


@dataclass(frozen=True)
class RagSource:
    id: str
    title: str
    url: str
    snippet: str
    provider: str
    quality_score: float
    metadata: dict


class RagSubAgent:
    def __init__(self, job_id: str, observer: ToolCallObserver | None = None) -> None:
        self.job_id = job_id
        self._bm25 = LocalKnowledgeBase.for_job(job_id)
        self._vector = VectorKnowledgeBase.for_job(job_id)
        self._observer = observer

    def retrieve_private_sources(
        self,
        query: str,
        todo_id: str,
        bm25_k: int = 5,
        semantic_k: int = 5,
        meta: ToolCallMeta | None = None,
    ) -> list[dict]:
        sources: list[dict] = []

        if self._observer and meta:
            self._observer.on_start("kb.bm25_search", {"query": query, "k": int(bm25_k)}, meta)
        t0 = perf_counter()
        bm25_hits = self._bm25.search(query, k=int(bm25_k))
        if self._observer and meta:
            self._observer.on_success(
                "kb.bm25_search",
                {"count": len(bm25_hits)},
                meta,
                int((perf_counter() - t0) * 1000),
            )
        for i, (chunk, score) in enumerate(bm25_hits):
            sources.append(
                RagSource(
                    id=f"local:{todo_id}:{i}",
                    title=f"{chunk.filename}（私有资料）",
                    url=f"local://{chunk.chunk_id}",
                    snippet=chunk.text[:280],
                    provider="local",
                    quality_score=max(0.6, float(score)),
                    metadata={"filename": chunk.filename, "chunk_id": chunk.chunk_id},
                ).__dict__
            )

        if int(semantic_k) > 0:
            if self._observer and meta:
                self._observer.on_start("kb.vector_search", {"query": query, "k": int(semantic_k)}, meta)
            t1 = perf_counter()
            vector_hits = self._vector.search(query, k=int(semantic_k))
            if self._observer and meta:
                self._observer.on_success(
                    "kb.vector_search",
                    {"count": len(vector_hits)},
                    meta,
                    int((perf_counter() - t1) * 1000),
                )
            for i, hit in enumerate(vector_hits):
                sources.append(self._vector_hit_to_source(hit=hit, todo_id=todo_id, idx=i))

        return sources

    @staticmethod
    def _vector_hit_to_source(hit: VectorHit, todo_id: str, idx: int) -> dict:
        return RagSource(
            id=f"vector:{todo_id}:{idx}",
            title=f"{hit.filename}（语义检索）",
            url=f"local+vector://{hit.chunk_id}",
            snippet=hit.text[:280],
            provider="local_vector",
            quality_score=max(0.65, float(hit.score)),
            metadata={"filename": hit.filename, "chunk_id": hit.chunk_id},
        ).__dict__
