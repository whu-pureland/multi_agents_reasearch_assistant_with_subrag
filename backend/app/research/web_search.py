from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.core.config import get_settings


@dataclass(frozen=True)
class WebResult:
    title: str
    url: str
    snippet: str | None = None


def web_search(query: str, max_results: int = 5, options: dict[str, Any] | None = None) -> list[WebResult]:
    settings = get_settings()
    options = options or {}
    provider = (settings.web_search_provider or "duckduckgo").lower()
    if provider == "disabled":
        return []

    if provider == "duckduckgo":
        try:
            from duckduckgo_search import DDGS  # type: ignore
        except Exception:
            return []

        results: list[WebResult] = []
        with DDGS() as ddgs:
            for item in ddgs.text(query, max_results=max_results):
                results.append(
                    WebResult(
                        title=str(item.get("title") or ""),
                        url=str(item.get("href") or ""),
                        snippet=item.get("body"),
                    )
                )
        return results

    if provider == "tavily":
        api_key = settings.tavily_api_key
        if not api_key:
            return []

        base_url = (settings.tavily_base_url or "https://api.tavily.com").rstrip("/")
        url = f"{base_url}/search"

        search_depth = str(options.get("search_depth") or settings.tavily_search_depth or "basic")
        include_answer = options.get("include_answer") if "include_answer" in options else settings.tavily_include_answer
        include_raw_content = (
            options.get("include_raw_content") if "include_raw_content" in options else settings.tavily_include_raw_content
        )

        payload = {
            "query": query,
            "max_results": int(max_results),
            "search_depth": search_depth,
            "include_answer": include_answer,
            "include_raw_content": include_raw_content,
        }
        for key in ["topic", "time_range", "days", "include_domains", "exclude_domains"]:
            if key in options:
                payload[key] = options[key]

        try:
            import httpx

            headers = {"Authorization": f"Bearer {api_key}"}
            resp = httpx.post(url, headers=headers, json=payload, timeout=25.0)
            resp.raise_for_status()
            data = resp.json()
        except Exception:
            return []

        items = data.get("results") if isinstance(data, dict) else None
        if not isinstance(items, list):
            return []

        results: list[WebResult] = []
        for item in items[: int(max_results)]:
            if not isinstance(item, dict):
                continue
            title = str(item.get("title") or "")
            href = str(item.get("url") or "")
            snippet = item.get("content") or item.get("snippet")
            if snippet is not None:
                snippet = str(snippet)
            results.append(WebResult(title=title, url=href, snippet=snippet))
        return results

    return []
