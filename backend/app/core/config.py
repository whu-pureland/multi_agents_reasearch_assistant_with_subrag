from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


REPO_ROOT = Path(__file__).resolve().parents[3]


def _clean_optional_str(value: str | None) -> str | None:
    if value is None:
        return None
    value = str(value).strip()
    return value or None


@dataclass(frozen=True)
class ResolvedModelProvider:
    provider: str
    api_key: str | None
    base_url: str | None
    model: str


@dataclass(frozen=True)
class ResolvedEmbeddingProvider:
    provider: str
    api_key: str | None
    base_url: str | None
    model: str


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=REPO_ROOT / ".env", extra="ignore")

    app_name: str = "Multi-Agent Research Assistant"
    api_prefix: str = "/api"
    cors_allow_origins: list[str] = ["http://localhost:5173"]

    data_dir: Path = REPO_ROOT / "data"

    llm_provider: str = "openai"  # openai | moonshot | deepseek | (other OpenAI-compatible)
    llm_api_key: str | None = None
    llm_base_url: str | None = None
    llm_model: str | None = None

    moonshot_api_key: str | None = None
    moonshot_base_url: str = "https://api.moonshot.cn/v1"

    deepseek_api_key: str | None = None
    deepseek_base_url: str = "https://api.deepseek.com/v1"

    embedding_provider: str | None = None  # openai | moonshot | deepseek | local
    embedding_api_key: str | None = None
    embedding_base_url: str | None = None
    embedding_model: str | None = None
    embedding_device: str = "cpu"  # used when embedding_provider=local

    # Backward-compatible OpenAI-style envs
    openai_api_key: str | None = None
    openai_base_url: str | None = None
    openai_model: str = "gpt-4o-mini"
    openai_embedding_model: str = "text-embedding-3-small"

    web_search_provider: str = "tavily"  # duckduckgo | tavily | disabled
    tavily_api_key: str | None = None
    tavily_base_url: str = "https://api.tavily.com"
    tavily_search_depth: str = "basic"  # basic | advanced | fast | ultra-fast
    tavily_include_answer: bool | str = False
    tavily_include_raw_content: bool | str = False

    mcp_config_path: Path = REPO_ROOT / "mcp_servers.json"

    def resolve_llm(self) -> ResolvedModelProvider:
        provider = (self.llm_provider or "openai").strip().lower()

        api_key = _clean_optional_str(self.llm_api_key)
        if not api_key:
            if provider == "moonshot":
                api_key = _clean_optional_str(self.moonshot_api_key)
            elif provider == "deepseek":
                api_key = _clean_optional_str(self.deepseek_api_key)
        if not api_key:
            api_key = _clean_optional_str(self.openai_api_key)

        base_url = _clean_optional_str(self.llm_base_url) or _clean_optional_str(self.openai_base_url)
        if not base_url:
            if provider == "moonshot":
                base_url = _clean_optional_str(self.moonshot_base_url)
            elif provider == "deepseek":
                base_url = _clean_optional_str(self.deepseek_base_url)

        model = _clean_optional_str(self.llm_model) or self.openai_model
        return ResolvedModelProvider(provider=provider, api_key=api_key, base_url=base_url, model=model)

    def resolve_embedding(self) -> ResolvedEmbeddingProvider:
        llm = self.resolve_llm()
        provider = (self.embedding_provider or llm.provider or "openai").strip().lower()

        api_key = _clean_optional_str(self.embedding_api_key)
        if not api_key and provider == llm.provider:
            api_key = llm.api_key
        if not api_key:
            if provider == "moonshot":
                api_key = _clean_optional_str(self.moonshot_api_key)
            elif provider == "deepseek":
                api_key = _clean_optional_str(self.deepseek_api_key)
        if not api_key:
            api_key = _clean_optional_str(self.openai_api_key)

        base_url = _clean_optional_str(self.embedding_base_url)
        if not base_url and provider == llm.provider:
            base_url = llm.base_url
        if not base_url:
            base_url = _clean_optional_str(self.openai_base_url)
        if not base_url:
            if provider == "moonshot":
                base_url = _clean_optional_str(self.moonshot_base_url)
            elif provider == "deepseek":
                base_url = _clean_optional_str(self.deepseek_base_url)

        model = _clean_optional_str(self.embedding_model) or self.openai_embedding_model
        return ResolvedEmbeddingProvider(provider=provider, api_key=api_key, base_url=base_url, model=model)


@lru_cache
def get_settings() -> Settings:
    return Settings()
