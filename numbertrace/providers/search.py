"""Official, documented web-search API adapters plus a no-key manual-link fallback.

Status checked 2026-11:
* Brave Search API - documented, key-based, active. Primary live adapter.
* Google Programmable Search JSON API - closed to new customers; Google states it stops
  working on 2027-01-01. Kept as an opt-in legacy adapter for existing customers only.
* Bing Search APIs - retired by Microsoft (Aug 2025). Not implemented.
We never scrape search-engine result pages.
"""

from __future__ import annotations

import html
import re
from typing import Any
from urllib.parse import quote_plus

from numbertrace.config import Settings
from numbertrace.models import ManualLink, NormalizedNumber
from numbertrace.net.safe_http import SafeHTTPClient
from numbertrace.providers.base import ProviderResponseError, RawHit, SearchProvider

_TAG = re.compile(r"<[^>]+>")
MAX_SNIPPET = 300


def clean_text(value: Any, limit: int = MAX_SNIPPET) -> str:
    if not isinstance(value, str):
        return ""
    text = html.unescape(_TAG.sub("", value)).strip()
    return text[:limit]


def _domain_clause(settings: Settings) -> str:
    parts: list[str] = []
    if settings.include_domains:
        parts.append("(" + " OR ".join(f"site:{d}" for d in settings.include_domains[:5]) + ")")
    parts.extend(f"-site:{d}" for d in settings.exclude_domains[:5])
    return (" " + " ".join(parts)) if parts else ""


def build_queries(number: NormalizedNumber, settings: Settings) -> list[tuple[str, str]]:
    """Return (variant, query) pairs, bounded by settings.max_queries.

    Queries are narrow: exact quoted number variants plus spam-report and business
    contexts. We never add names, addresses or other personal-data keywords.
    """
    suffix = _domain_clause(settings)
    e164 = number.e164
    national = number.national
    pairs: list[tuple[str, str]] = [(e164, f'"{e164}"{suffix}')]
    pairs.append((e164, f'"{e164}" (spam OR scam OR complaint OR "who called"){suffix}'))
    pairs.append((national, f'"{national}" (company OR business OR "customer service"){suffix}'))
    for variant in number.variants:
        if variant != e164:
            pairs.append((variant, f'"{variant}"{suffix}'))
    seen: set[str] = set()
    unique: list[tuple[str, str]] = []
    for variant, query in pairs:
        if query not in seen:
            seen.add(query)
            unique.append((variant, query))
    return unique[: settings.max_queries]


def manual_search_links(number: NormalizedNumber, settings: Settings) -> list[ManualLink]:
    """Clickable, URL-encoded links the user opens themselves. No network calls."""
    engines = {
        "DuckDuckGo": "https://duckduckgo.com/?q={q}",
        "Google": "https://www.google.com/search?q={q}",
        "Bing": "https://www.bing.com/search?q={q}",
        "Brave Search": "https://search.brave.com/search?q={q}",
    }
    links: list[ManualLink] = []
    for _variant, query in build_queries(number, settings)[:3]:
        for engine, template in engines.items():
            links.append(ManualLink(engine=engine, query=query, url=template.format(q=quote_plus(query))))
    return links


class BraveSearchProvider(SearchProvider):
    name = "brave_search"
    requires = ("NUMBERTRACE_BRAVE_API_KEY",)
    allowed_hosts = ("api.search.brave.com",)
    notes = "Brave Search API (documented). Requires your own API key and internet."
    endpoint = "https://api.search.brave.com/res/v1/web/search"

    def __init__(self, api_key: str | None) -> None:
        self._key = api_key

    def is_configured(self) -> bool:
        return bool(self._key)

    async def search(self, query: str, http: SafeHTTPClient) -> list[RawHit]:
        data = await http.get_json(
            self.endpoint,
            allowed_hosts=self.allowed_hosts,
            params={"q": query, "count": 10, "safesearch": "strict"},
            headers={"Accept": "application/json", "X-Subscription-Token": self._key or ""},
        )
        if not isinstance(data, dict):
            raise ProviderResponseError("unexpected response shape")
        web = data.get("web") or {}
        results = web.get("results", []) if isinstance(web, dict) else None
        if not isinstance(results, list):
            raise ProviderResponseError("missing web.results list")
        return _to_hits(results, title_key="title", url_key="url", snippet_key="description")


class GoogleCSEProvider(SearchProvider):
    name = "google_cse_legacy"
    requires = ("NUMBERTRACE_GOOGLE_CSE_KEY", "NUMBERTRACE_GOOGLE_CSE_CX")
    allowed_hosts = ("www.googleapis.com",)
    notes = (
        "LEGACY: Google Custom Search JSON API is closed to new customers and Google states "
        "it stops working on 2027-01-01. Existing customers only."
    )
    endpoint = "https://www.googleapis.com/customsearch/v1"

    def __init__(self, key: str | None, cx: str | None) -> None:
        self._key = key
        self._cx = cx

    def is_configured(self) -> bool:
        return bool(self._key and self._cx)

    async def search(self, query: str, http: SafeHTTPClient) -> list[RawHit]:
        data = await http.get_json(
            self.endpoint,
            allowed_hosts=self.allowed_hosts,
            params={"key": self._key, "cx": self._cx, "q": query, "num": 10, "safe": "active"},
        )
        if not isinstance(data, dict):
            raise ProviderResponseError("unexpected response shape")
        items = data.get("items", [])
        if not isinstance(items, list):
            raise ProviderResponseError("items is not a list")
        return _to_hits(items, title_key="title", url_key="link", snippet_key="snippet")


def _to_hits(items: list[Any], *, title_key: str, url_key: str, snippet_key: str) -> list[RawHit]:
    hits: list[RawHit] = []
    for item in items[:20]:
        if not isinstance(item, dict):
            continue
        url = item.get(url_key)
        if not isinstance(url, str) or not url.startswith(("https://", "http://")):
            continue
        hits.append(
            RawHit(
                title=clean_text(item.get(title_key), 200) or url,
                url=url[:2000],
                snippet=clean_text(item.get(snippet_key)),
            )
        )
    return hits


class DemoSearchProvider(SearchProvider):
    """Returns clearly SYNTHETIC hits on reserved example domains. Demo mode only."""

    name = "demo_synthetic_search"
    kind = "web_search_demo"
    online = False
    notes = "Synthetic results on example.com/example.org. Never real evidence."
    DEMO_NUMBERS = frozenset({"+14155550100", "+14155550123"})

    def is_configured(self) -> bool:
        return True

    async def search(self, query: str, http: SafeHTTPClient) -> list[RawHit]:
        if not any(n in query for n in self.DEMO_NUMBERS):
            return []
        return [
            RawHit(
                title="[SYNTHETIC DEMO] Example Pizza Co. - contact page",
                url="https://www.example.com/contact?utm_source=demo",
                snippet="[SYNTHETIC] Call our customer service line ...",
            ),
            RawHit(
                title="[SYNTHETIC DEMO] Example Pizza Co. - contact page",
                url="https://example.com/contact/",
                snippet="[SYNTHETIC] duplicate URL used to demonstrate de-duplication",
            ),
            RawHit(
                title="[SYNTHETIC DEMO] Who called me? spam complaint thread",
                url="https://forum.example.org/t/unknown-caller-complaint",
                snippet="[SYNTHETIC] Someone reports repeated scam calls from this number.",
            ),
            RawHit(
                title="[SYNTHETIC DEMO] Public post mentioning the number",
                url="https://example.net/social/post/123",
                snippet="[SYNTHETIC] A public post that includes the number in its text.",
            ),
        ]
