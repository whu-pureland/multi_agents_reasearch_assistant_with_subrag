from __future__ import annotations

import json
import secrets
import threading
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, ClassVar

from app.core.cache import cache_get_json, cache_set_json
from app.core.config import get_settings
from app.research.models import Job, JobCreateRequest


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(frozen=True)
class JobStore:
    root_dir: Path

    _locks_guard: ClassVar[threading.Lock] = threading.Lock()
    _locks: ClassVar[dict[str, threading.RLock]] = {}

    @staticmethod
    def default() -> "JobStore":
        settings = get_settings()
        return JobStore(root_dir=settings.data_dir / "jobs")

    def _job_path(self, job_id: str) -> Path:
        return self.root_dir / f"{job_id}.json"

    @staticmethod
    def _cache_name(job_id: str) -> str:
        return f"job:{job_id}"

    @classmethod
    def _lock_for(cls, job_id: str) -> threading.RLock:
        with cls._locks_guard:
            lock = cls._locks.get(job_id)
            if lock is None:
                lock = threading.RLock()
                cls._locks[job_id] = lock
            return lock

    def ensure_dirs(self) -> None:
        self.root_dir.mkdir(parents=True, exist_ok=True)

    def create_job(self, request: JobCreateRequest) -> Job:
        self.ensure_dirs()
        job_id = secrets.token_urlsafe(10)
        job = Job(
            id=job_id,
            query=request.query.strip(),
            status="created",
            created_at=_utc_now_iso(),
            updated_at=_utc_now_iso(),
            settings=request.settings,
            todos=[],
            notes=[],
            sources=[],
            report=None,
            error=None,
            uploads=[],
            events=[],
        )
        with self._lock_for(job_id):
            payload = job.model_dump()
            self._job_path(job_id).write_text(job.model_dump_json(indent=2), encoding="utf-8")
            settings = get_settings()
            cache_set_json(self._cache_name(job_id), payload, ttl_seconds=int(settings.redis_job_ttl_seconds or 0))
        return job

    def get_job(self, job_id: str) -> Job | None:
        path = self._job_path(job_id)
        with self._lock_for(job_id):
            cached = cache_get_json(self._cache_name(job_id))
            if cached is not None:
                try:
                    return Job.model_validate(cached)
                except Exception:
                    pass
            if not path.exists():
                return None
            data = json.loads(path.read_text(encoding="utf-8"))
            settings = get_settings()
            cache_set_json(self._cache_name(job_id), data, ttl_seconds=int(settings.redis_job_ttl_seconds or 0))
            return Job.model_validate(data)

    def update_job(self, job_id: str, patch: dict[str, Any]) -> Job:
        with self._lock_for(job_id):
            job = self.get_job(job_id)
            if job is None:
                raise KeyError(f"Job not found: {job_id}")
            data = job.model_dump()
            data.update(patch)
            data["updated_at"] = _utc_now_iso()
            updated = Job.model_validate(data)
            self._job_path(job_id).write_text(updated.model_dump_json(indent=2), encoding="utf-8")
            settings = get_settings()
            cache_set_json(
                self._cache_name(job_id),
                updated.model_dump(),
                ttl_seconds=int(settings.redis_job_ttl_seconds or 0),
            )
            return updated

    def append_event(self, job_id: str, event: dict[str, Any], limit: int = 2000) -> None:
        with self._lock_for(job_id):
            job = self.get_job(job_id)
            if job is None:
                return
            events = [*job.events, {**event, "ts": _utc_now_iso()}]
            if len(events) > limit:
                events = events[-limit:]
            self.update_job(job_id, {"events": events})
