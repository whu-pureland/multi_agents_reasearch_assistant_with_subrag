from __future__ import annotations

import json
from functools import lru_cache
from typing import Any

from app.core.config import get_settings

try:
    import redis  # type: ignore
except Exception:  # pragma: no cover
    redis = None  # type: ignore


@lru_cache
def _redis_client():
    settings = get_settings()
    url = str(getattr(settings, "redis_url", "") or "").strip()
    if not url or url.lower() in {"disabled", "none"}:
        return None
    if redis is None:
        return None
    try:
        return redis.Redis.from_url(url, decode_responses=True)
    except Exception:
        return None


def _key(name: str) -> str:
    settings = get_settings()
    prefix = str(getattr(settings, "redis_prefix", "multi_codex") or "multi_codex").strip()
    return f"{prefix}:{name}"


def cache_get_json(name: str) -> dict[str, Any] | None:
    client = _redis_client()
    if client is None:
        return None
    try:
        raw = client.get(_key(name))
    except Exception:
        return None
    if not raw:
        return None
    try:
        obj = json.loads(raw)
    except Exception:
        return None
    if not isinstance(obj, dict):
        return None
    return obj


def cache_set_json(name: str, value: dict[str, Any], ttl_seconds: int | None = None) -> None:
    client = _redis_client()
    if client is None:
        return
    payload = json.dumps(value, ensure_ascii=False)
    try:
        if ttl_seconds is not None and int(ttl_seconds) > 0:
            client.setex(_key(name), int(ttl_seconds), payload)
        else:
            client.set(_key(name), payload)
    except Exception:
        return

