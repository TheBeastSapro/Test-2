"""Web search and page fetching for the research stage.

Same shape as every other capability here: an abstract provider, real adapters, and a
mock that lets the whole research flow run offline. Search vendors are interchangeable
and their free tiers come and go, so nothing above this layer knows which one is in use.

Extraction is a small hand-rolled HTML-to-text pass rather than a readability
dependency. It is not as good as a real article extractor, and it says so in the
`extraction` field so a downstream claim can be discounted when the text looks thin.
"""

from __future__ import annotations

import html
import logging
import re
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from html.parser import HTMLParser
from typing import ClassVar
from urllib.parse import urlparse

import httpx

from ..config import get_settings
from .base import ProviderError, ProviderTimeout

log = logging.getLogger("forgecast.providers.search")

_TIMEOUT = httpx.Timeout(connect=10.0, read=45.0, write=15.0, pool=10.0)
MAX_PAGE_BYTES = 3_000_000
MIN_USEFUL_CHARS = 400


@dataclass
class SearchResult:
    title: str
    url: str
    snippet: str = ""
    published: str | None = None
    rank: int = 0

    @property
    def domain(self) -> str:
        return urlparse(self.url).netloc.lower().removeprefix("www.")

    def as_dict(self) -> dict:
        return {
            "title": self.title,
            "url": self.url,
            "domain": self.domain,
            "snippet": self.snippet,
            "published": self.published,
            "rank": self.rank,
        }


@dataclass
class FetchedPage:
    url: str
    title: str
    text: str
    status: int = 200
    extraction: str = "heuristic"
    error: str | None = None

    @property
    def domain(self) -> str:
        return urlparse(self.url).netloc.lower().removeprefix("www.")

    @property
    def usable(self) -> bool:
        return self.error is None and len(self.text) >= MIN_USEFUL_CHARS

    def as_dict(self) -> dict:
        return {
            "url": self.url,
            "domain": self.domain,
            "title": self.title,
            "characters": len(self.text),
            "status": self.status,
            "extraction": self.extraction,
            "usable": self.usable,
            "error": self.error,
        }


class SearchProvider(ABC):
    name = "search"

    def __init__(self, api_key: str = "") -> None:
        self.api_key = api_key

    @abstractmethod
    async def search(self, query: str, *, limit: int = 8) -> list[SearchResult]: ...


class BraveSearch(SearchProvider):
    name = "brave"
    base_url = "https://api.search.brave.com/res/v1/web/search"

    async def search(self, query: str, *, limit: int = 8) -> list[SearchResult]:
        if not self.api_key:
            raise ProviderError("no Brave Search API key configured", provider=self.name)
        try:
            async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
                response = await client.get(
                    self.base_url,
                    headers={
                        "X-Subscription-Token": self.api_key,
                        "Accept": "application/json",
                    },
                    params={"q": query, "count": min(limit, 20)},
                )
        except httpx.TimeoutException as exc:
            raise ProviderTimeout(str(exc), provider=self.name) from exc

        if not response.is_success:
            raise ProviderError(
                f"brave returned {response.status_code}: {response.text[:200]}",
                provider=self.name,
                retryable=response.status_code == 429 or response.status_code >= 500,
            )

        results = ((response.json().get("web") or {}).get("results")) or []
        return [
            SearchResult(
                title=entry.get("title", ""),
                url=entry.get("url", ""),
                snippet=_strip_tags(entry.get("description", "")),
                published=entry.get("age"),
                rank=index,
            )
            for index, entry in enumerate(results[:limit])
            if entry.get("url")
        ]


class TavilySearch(SearchProvider):
    """Tavily returns extracted page content alongside results, which saves a fetch."""

    name = "tavily"
    base_url = "https://api.tavily.com/search"

    async def search(self, query: str, *, limit: int = 8) -> list[SearchResult]:
        if not self.api_key:
            raise ProviderError("no Tavily API key configured", provider=self.name)
        try:
            async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
                response = await client.post(
                    self.base_url,
                    json={
                        "api_key": self.api_key,
                        "query": query,
                        "max_results": min(limit, 20),
                        "search_depth": "advanced",
                    },
                )
        except httpx.TimeoutException as exc:
            raise ProviderTimeout(str(exc), provider=self.name) from exc

        if not response.is_success:
            raise ProviderError(
                f"tavily returned {response.status_code}: {response.text[:200]}",
                provider=self.name,
                retryable=response.status_code >= 500,
            )

        results = response.json().get("results") or []
        return [
            SearchResult(
                title=entry.get("title", ""),
                url=entry.get("url", ""),
                snippet=entry.get("content", "")[:600],
                rank=index,
            )
            for index, entry in enumerate(results[:limit])
            if entry.get("url")
        ]


@dataclass
class MockSearch(SearchProvider):
    """Deterministic fake results so the research flow is testable offline.

    It returns plausible *shapes*, never plausible *facts*: every snippet is marked as
    mock text. That matters because the research stage's whole job is citation
    discipline, and a mock that produced convincing-looking statistics would let a bug
    in that discipline pass unnoticed.
    """

    name: str = "mock-search"
    api_key: str = ""
    pages: dict[str, str] = field(default_factory=dict)

    async def search(self, query: str, *, limit: int = 8) -> list[SearchResult]:
        stem = re.sub(r"[^a-z0-9]+", "-", query.lower()).strip("-")[:40] or "query"
        domains = ["example.org", "example.edu", "example-news.com", "example.gov"]
        return [
            SearchResult(
                title=f"[MOCK] Source {index + 1} about {query}",
                url=f"https://{domains[index % len(domains)]}/{stem}-{index + 1}",
                snippet=f"[MOCK SNIPPET] Placeholder text for {query}. Contains no real "
                        f"facts and must not be cited as evidence.",
                rank=index,
            )
            for index in range(min(limit, 6))
        ]


# ------------------------------------------------------------------- fetching


class _TextExtractor(HTMLParser):
    """Collect visible text, dropping script/style/nav furniture."""

    SKIP: ClassVar[frozenset[str]] = frozenset(
        {"script", "style", "noscript", "svg", "head", "nav", "footer", "form"}
    )
    BREAK: ClassVar[frozenset[str]] = frozenset(
        {"p", "div", "br", "li", "h1", "h2", "h3", "h4", "tr", "section"}
    )

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self.title = ""
        self._skip_depth = 0
        self._in_title = False

    def handle_starttag(self, tag, attrs):
        if tag in self.SKIP:
            self._skip_depth += 1
        elif tag == "title":
            self._in_title = True
        elif tag in self.BREAK:
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if tag in self.SKIP and self._skip_depth:
            self._skip_depth -= 1
        elif tag == "title":
            self._in_title = False

    def handle_data(self, data):
        # Title is checked before the skip guard on purpose: <title> lives inside
        # <head>, which is skipped, so guarding first silently discarded the title of
        # every real page and left sources labelled only by URL.
        if self._in_title:
            self.title += data.strip()
            return
        if self._skip_depth:
            return
        text = data.strip()
        if text:
            self.parts.append(text)

    def text(self) -> str:
        joined = " ".join(self.parts)
        joined = re.sub(r"[ \t]+", " ", joined)
        return re.sub(r"\n\s*\n+", "\n\n", joined).strip()


def _strip_tags(value: str) -> str:
    return html.unescape(re.sub(r"<[^>]+>", "", value or "")).strip()


async def fetch(url: str, *, timeout: float = 30.0) -> FetchedPage:
    """Fetch and extract one page. Never raises — failures come back as a page."""
    try:
        async with httpx.AsyncClient(
            timeout=httpx.Timeout(timeout), follow_redirects=True
        ) as client:
            response = await client.get(
                url,
                headers={
                    "User-Agent": "Mozilla/5.0 (compatible; Forgecast research bot)",
                    "Accept": "text/html,application/xhtml+xml",
                },
            )
    except httpx.HTTPError as exc:
        return FetchedPage(url=url, title="", text="", status=0, error=str(exc)[:200])

    if not response.is_success:
        return FetchedPage(
            url=url, title="", text="", status=response.status_code,
            error=f"HTTP {response.status_code}",
        )

    content_type = response.headers.get("content-type", "")
    if "html" not in content_type and "text" not in content_type:
        return FetchedPage(
            url=url, title="", text="", status=response.status_code,
            error=f"unsupported content type {content_type!r}",
        )

    body = response.text[:MAX_PAGE_BYTES]
    parser = _TextExtractor()
    try:
        parser.feed(body)
    except Exception as exc:
        return FetchedPage(
            url=url, title="", text="", status=response.status_code,
            error=f"parse failed: {exc}"[:200],
        )

    return FetchedPage(
        url=url,
        title=parser.title or url,
        text=parser.text(),
        status=response.status_code,
        extraction="heuristic-htmlparser",
    )


def provider_for(user_keys: dict[str, str] | None = None) -> SearchProvider:
    """Pick a search provider: user key, then platform key, then mock."""
    settings = get_settings()
    keys = user_keys or {}

    if settings.is_mock:
        return MockSearch()

    for name, cls in (("tavily", TavilySearch), ("brave", BraveSearch)):
        key = keys.get(name) or getattr(settings, f"{name}_api_key", "")
        if key:
            return cls(key)

    log.warning("no search provider key configured — falling back to mock search")
    return MockSearch()
