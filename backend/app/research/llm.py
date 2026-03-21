from __future__ import annotations

import os
import threading
from dataclasses import dataclass

from app.core.config import get_settings


@dataclass(frozen=True)
class LlmMessage:
    role: str
    content: str


class LlmClient:
    def __init__(self) -> None:
        self.settings = get_settings()

    _temperature_one_models_guard = threading.Lock()
    _temperature_one_models: set[str] = set()

    def available(self) -> bool:
        cfg = self.settings.resolve_llm()
        return bool(cfg.api_key) and bool(cfg.model)

    @staticmethod
    def _set_openai_compat_env(api_key: str | None, base_url: str | None) -> None:
        if api_key:
            os.environ["OPENAI_API_KEY"] = api_key
        if base_url:
            os.environ["OPENAI_BASE_URL"] = base_url
            os.environ["OPENAI_API_BASE"] = base_url

    @classmethod
    def _model_key(cls, model: str, base_url: str | None) -> str:
        return f"{(base_url or '').strip()}::{model.strip()}"

    @classmethod
    def _force_temperature_one(cls, key: str) -> bool:
        with cls._temperature_one_models_guard:
            return key in cls._temperature_one_models

    @classmethod
    def _mark_force_temperature_one(cls, key: str) -> None:
        with cls._temperature_one_models_guard:
            cls._temperature_one_models.add(key)

    @staticmethod
    def _looks_like_temperature_one_error(exc: Exception) -> bool:
        message = str(exc).lower()
        if "temperature" not in message:
            return False
        return ("only 1 is allowed" in message) or ("must be 1" in message)

    @staticmethod
    def _create_chat_openai(ChatOpenAI, cfg, temperature: float):  # type: ignore[no-untyped-def]
        candidates = [
            {"model": cfg.model, "temperature": temperature, "api_key": cfg.api_key, "base_url": cfg.base_url},
            {"model": cfg.model, "temperature": temperature, "openai_api_key": cfg.api_key, "base_url": cfg.base_url},
            {
                "model": cfg.model,
                "temperature": temperature,
                "openai_api_key": cfg.api_key,
                "openai_api_base": cfg.base_url,
            },
            {"model": cfg.model, "temperature": temperature},
        ]

        for kwargs in candidates:
            kwargs = {k: v for k, v in kwargs.items() if v is not None and v != ""}
            try:
                return ChatOpenAI(**kwargs)
            except TypeError:
                continue
        return ChatOpenAI(model=cfg.model, temperature=temperature)

    async def complete(self, messages: list[LlmMessage], temperature: float = 0.2) -> str:
        if not self.available():
            return ""
        try:
            from langchain_openai import ChatOpenAI  # type: ignore
        except Exception:
            return ""

        cfg = self.settings.resolve_llm()
        self._set_openai_compat_env(api_key=cfg.api_key, base_url=cfg.base_url)

        model_key = self._model_key(cfg.model, cfg.base_url)
        effective_temperature = 1.0 if self._force_temperature_one(model_key) else float(temperature)

        llm = self._create_chat_openai(ChatOpenAI, cfg, effective_temperature)
        try:
            response = await llm.ainvoke([{"role": m.role, "content": m.content} for m in messages])
        except Exception as exc:
            if (not self._force_temperature_one(model_key)) and self._looks_like_temperature_one_error(exc):
                self._mark_force_temperature_one(model_key)
                llm = self._create_chat_openai(ChatOpenAI, cfg, 1.0)
                response = await llm.ainvoke([{"role": m.role, "content": m.content} for m in messages])
            else:
                raise
        return str(getattr(response, "content", "") or "")
