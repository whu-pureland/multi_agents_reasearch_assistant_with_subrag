from __future__ import annotations

import os
import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from app.core.config import get_settings


def _is_local_provider(provider: str) -> bool:
    provider = str(provider or "").strip().lower()
    return provider in {"local", "hf", "huggingface", "sentence-transformers", "sentence_transformers"}


@lru_cache(maxsize=4)
def _load_sentence_transformer(model: str, device: str) -> "SentenceTransformer":
    from sentence_transformers import SentenceTransformer  # type: ignore

    return SentenceTransformer(model, device=device)


def _chunk_text(text: str, chunk_size: int = 900, overlap: int = 140) -> list[str]:
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


@dataclass(frozen=True)
class VectorHit:
    chunk_id: str
    filename: str
    text: str
    score: float


class EmbeddingClient:
    def __init__(self) -> None:
        self.settings = get_settings()

    def available(self) -> bool:
        cfg = self.settings.resolve_embedding()
        if _is_local_provider(cfg.provider):
            if not cfg.model:
                return False
            try:
                import sentence_transformers  # type: ignore # noqa: F401
            except Exception:
                return False
            return True
        return bool(cfg.api_key) and bool(cfg.model)

    def _set_openai_compat_env(self, api_key: str | None, base_url: str | None) -> None:
        if api_key:
            os.environ["OPENAI_API_KEY"] = api_key
        if base_url:
            os.environ["OPENAI_BASE_URL"] = base_url
            os.environ["OPENAI_API_BASE"] = base_url

    def _openai_embeddings(self):
        cfg = self.settings.resolve_embedding()
        self._set_openai_compat_env(api_key=cfg.api_key, base_url=cfg.base_url)
        from langchain_openai import OpenAIEmbeddings  # type: ignore

        candidates = [
            {"model": cfg.model, "api_key": cfg.api_key, "base_url": cfg.base_url},
            {"model": cfg.model, "openai_api_key": cfg.api_key, "base_url": cfg.base_url},
            {"model": cfg.model, "openai_api_key": cfg.api_key, "openai_api_base": cfg.base_url},
            {"model": cfg.model},
        ]
        for kwargs in candidates:
            kwargs = {k: v for k, v in kwargs.items() if v is not None and v != ""}
            try:
                return OpenAIEmbeddings(**kwargs)
            except TypeError:
                continue
        return OpenAIEmbeddings(model=cfg.model)

    def _local_embed_documents(self, texts: list[str]) -> list[list[float]]:
        cfg = self.settings.resolve_embedding()
        device = str(getattr(self.settings, "embedding_device", "cpu") or "cpu")
        model = _load_sentence_transformer(cfg.model, device=device)
        vectors = model.encode(
            texts,
            normalize_embeddings=True,
            convert_to_numpy=True,
        )
        return [[float(x) for x in vec] for vec in vectors]

    def _local_embed_query(self, text: str) -> list[float]:
        cfg = self.settings.resolve_embedding()
        device = str(getattr(self.settings, "embedding_device", "cpu") or "cpu")
        model = _load_sentence_transformer(cfg.model, device=device)
        vectors = model.encode(
            [text],
            normalize_embeddings=True,
            convert_to_numpy=True,
        )
        return [float(x) for x in vectors[0]]

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        if not self.available():
            return []
        cfg = self.settings.resolve_embedding()
        if _is_local_provider(cfg.provider):
            return self._local_embed_documents(texts)
        return self._openai_embeddings().embed_documents(texts)

    def embed_query(self, text: str) -> list[float]:
        if not self.available():
            return []
        cfg = self.settings.resolve_embedding()
        if _is_local_provider(cfg.provider):
            return self._local_embed_query(text)
        return self._openai_embeddings().embed_query(text)


class VectorKnowledgeBase:
    def __init__(self, persist_dir: Path) -> None:
        self.persist_dir = persist_dir
        self.persist_dir.mkdir(parents=True, exist_ok=True)
        self._collection = None

    @staticmethod
    def for_job(job_id: str) -> "VectorKnowledgeBase":
        settings = get_settings()
        return VectorKnowledgeBase(persist_dir=settings.data_dir / "chroma" / job_id)

    def _get_collection(self):
        if self._collection is not None:
            return self._collection
        import chromadb  # type: ignore

        client = chromadb.PersistentClient(path=str(self.persist_dir))
        self._collection = client.get_or_create_collection(
            name="documents",
            metadata={"hnsw:space": "cosine"},
        )
        return self._collection

    def ingest_document(self, filename: str, text: str) -> None:
        embedder = EmbeddingClient()
        if not embedder.available():
            return
        chunks = _chunk_text(text)
        if not chunks:
            return

        embeddings = embedder.embed_documents(chunks)
        if not embeddings:
            return

        ids = [f"{filename}::vchunk-{i}" for i in range(len(chunks))]
        metadatas = [{"filename": filename, "chunk_index": i} for i in range(len(chunks))]
        collection = self._get_collection()
        collection.upsert(ids=ids, documents=chunks, metadatas=metadatas, embeddings=embeddings)

    def search(self, query: str, k: int = 5) -> list[VectorHit]:
        embedder = EmbeddingClient()
        if not embedder.available():
            return []
        q_emb = embedder.embed_query(query)
        if not q_emb:
            return []

        collection = self._get_collection()
        res = collection.query(
            query_embeddings=[q_emb],
            n_results=int(k),
            include=["documents", "metadatas", "distances"],
        )

        hits: list[VectorHit] = []
        ids = (res.get("ids") or [[]])[0]
        docs = (res.get("documents") or [[]])[0]
        metas = (res.get("metadatas") or [[]])[0]
        dists = (res.get("distances") or [[]])[0]

        for chunk_id, doc, meta, dist in zip(ids, docs, metas, dists):
            filename = str((meta or {}).get("filename") or "")
            distance = float(dist) if dist is not None else 1.0
            score = max(0.0, min(1.0, 1.0 - distance))
            hits.append(VectorHit(chunk_id=str(chunk_id), filename=filename, text=str(doc), score=score))
        return hits
