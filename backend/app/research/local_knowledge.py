from __future__ import annotations

import json
import math
import re
from dataclasses import dataclass
from pathlib import Path

from rank_bm25 import BM25Okapi

from app.core.config import get_settings


def _tokenize(text: str) -> list[str]:
    text = text.lower()
    return re.findall(r"[a-z0-9\u4e00-\u9fff]+", text)


def _chunk_text(text: str, chunk_size: int = 800, overlap: int = 120) -> list[str]:
    text = re.sub(r"\s+", " ", text).strip()
    if not text:
        return []
    chunks: list[str] = []
    start = 0
    while start < len(text):
        end = min(len(text), start + chunk_size)
        chunks.append(text[start:end])
        if end == len(text):
            break
        start = max(0, end - overlap)
    return chunks


@dataclass
class KnowledgeChunk:
    chunk_id: str
    filename: str
    text: str


class LocalKnowledgeBase:
    def __init__(self, index_path: Path) -> None:
        self.index_path = index_path
        self.chunks: list[KnowledgeChunk] = []
        self._bm25: BM25Okapi | None = None
        self._load()

    @staticmethod
    def for_job(job_id: str) -> "LocalKnowledgeBase":
        settings = get_settings()
        index_path = settings.data_dir / "kb" / f"{job_id}.jsonl"
        index_path.parent.mkdir(parents=True, exist_ok=True)
        return LocalKnowledgeBase(index_path=index_path)

    def _load(self) -> None:
        if not self.index_path.exists():
            return
        chunks: list[KnowledgeChunk] = []
        for line in self.index_path.read_text(encoding="utf-8").splitlines():
            raw = json.loads(line)
            chunks.append(KnowledgeChunk(**raw))
        self.chunks = chunks
        self._rebuild()

    def _persist_append(self, chunk: KnowledgeChunk) -> None:
        line = json.dumps(
            {"chunk_id": chunk.chunk_id, "filename": chunk.filename, "text": chunk.text},
            ensure_ascii=False,
        )
        with self.index_path.open("a", encoding="utf-8") as f:
            f.write(line + "\n")

    def _rebuild(self) -> None:
        if not self.chunks:
            self._bm25 = None
            return
        corpus = [_tokenize(c.text) for c in self.chunks]
        self._bm25 = BM25Okapi(corpus)

    def ingest_document(self, filename: str, text: str) -> None:
        for i, chunk in enumerate(_chunk_text(text)):
            chunk_id = f"{filename}::chunk-{i}"
            kc = KnowledgeChunk(chunk_id=chunk_id, filename=filename, text=chunk)
            self.chunks.append(kc)
            self._persist_append(kc)
        self._rebuild()

    def search(self, query: str, k: int = 5) -> list[tuple[KnowledgeChunk, float]]:
        if self._bm25 is None or not self.chunks:
            return []
        tokens = _tokenize(query)
        scores = self._bm25.get_scores(tokens)
        ranked = sorted(enumerate(scores), key=lambda x: x[1], reverse=True)[:k]
        results: list[tuple[KnowledgeChunk, float]] = []
        for idx, score in ranked:
            if score <= 0:
                continue
            normalized = 1.0 - math.exp(-float(score))
            results.append((self.chunks[idx], normalized))
        return results

