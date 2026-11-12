"""Bounded single-number investigation orchestrator (async, dependency-injected)."""

from __future__ import annotations

import asyncio
import contextlib
import logging
import time
from collections.abc import AsyncIterator, Awaitable, Callable
from typing import Any

import httpx

from numbertrace import __version__
from numbertrace.config import Settings
from numbertrace.core.evidence import assess_risk, build_summary, dedupe_and_group, make_finding
from numbertrace.core.phone import normalize
from numbertrace.models import (
    Finding,
    Investigation,
    NormalizedNumber,
    ProviderInfo,
    ProviderState,
    ProviderStatus,
    ReputationReport,
)
from numbertrace.net.safe_http import SafeHTTPClient, UnsafeURLError
from numbertrace.providers.base import ProviderResponseError, ReputationProvider, SearchProvider
from numbertrace.providers.reputation import LocalDatasetReputationProvider, bundled_sample_path
from numbertrace.providers.search import (
    BraveSearchProvider,
    DemoSearchProvider,
    GoogleCSEProvider,
    build_queries,
    manual_search_links,
)

log = logging.getLogger("numbertrace.investigate")
Event = dict[str, Any]
EventCallback = Callable[[Event], Awaitable[None]]

NOTICES = [
    "Every web result is a PUBLIC REFERENCE (UNVERIFIED). It is not confirmed identity.",
    "Social-platform mentions never establish account ownership.",
    "Carrier/region metadata can be stale (number portability) and is not live location.",
    "Community complaints are allegations, not proof. Do not label a person based on them.",
]


def default_search_providers(settings: Settings) -> list[SearchProvider]:
    if settings.demo:
        return [DemoSearchProvider()]
    return [
        BraveSearchProvider(settings.brave_api_key),
        GoogleCSEProvider(settings.google_cse_key, settings.google_cse_cx),
    ]


def default_reputation_providers(settings: Settings) -> list[ReputationProvider]:
    path = settings.community_dataset
    if settings.demo and path is None:
        path = bundled_sample_path()
    return [LocalDatasetReputationProvider(path)]


def _error_message(exc: BaseException) -> str:
    """Human-readable, PII-free error text."""
    if isinstance(exc, httpx.HTTPStatusError):
        code = exc.response.status_code
        if code in (401, 403):
            return f"provider rejected the API key (HTTP {code})"
        if code == 429:
            return "provider rate limit or quota reached (HTTP 429)"
        return f"provider returned HTTP {code}"
    if isinstance(exc, UnsafeURLError):
        return f"blocked by outbound safety policy: {exc}"
    if isinstance(exc, ProviderResponseError):
        return f"malformed provider response: {exc}"
    if isinstance(exc, httpx.TransportError):
        return "network error (check internet/DNS/proxy)"
    return type(exc).__name__


class Investigator:
    def __init__(
        self,
        settings: Settings,
        *,
        search_providers: list[SearchProvider] | None = None,
        reputation_providers: list[ReputationProvider] | None = None,
        http: SafeHTTPClient | None = None,
    ) -> None:
        self.settings = settings
        self.search_providers = search_providers if search_providers is not None else default_search_providers(settings)
        self.reputation_providers = (
            reputation_providers if reputation_providers is not None else default_reputation_providers(settings)
        )
        self._http = http

    def provider_info(self) -> list[ProviderInfo]:
        infos = [p.info() for p in self.search_providers]
        infos += [p.info() for p in self.reputation_providers]
        infos.append(
            ProviderInfo(
                name="manual_search_links",
                kind="manual",
                configured=True,
                requires=[],
                online=False,
                notes="Always available. Generates links you open yourself.",
            )
        )
        return infos

    def normalize(self, raw: str, region: str | None = None) -> NormalizedNumber:
        return normalize(raw, region or self.settings.default_region, self.settings.max_variants)

    async def _run_search(
        self,
        provider: SearchProvider,
        queries: list[tuple[str, str]],
        http: SafeHTTPClient,
        sink: list[Finding],
        status: ProviderStatus,
    ) -> None:
        for variant, query in queries:
            hits = await provider.search(query, http)
            status.queries_used += 1
            for h in hits:
                sink.append(
                    make_finding(
                        title=h.title,
                        url=h.url,
                        snippet=h.snippet,
                        provider=provider.name,
                        variant=variant,
                    )
                )

    async def run(
        self,
        raw: str,
        *,
        region: str | None = None,
        online: bool = True,
        on_event: EventCallback | None = None,
        number: NormalizedNumber | None = None,
    ) -> Investigation:
        async def emit(event: Event) -> None:
            if on_event is not None:
                await on_event(event)

        number = number or self.normalize(raw, region)
        await emit({"type": "normalized", "number": number.model_dump(mode="json")})

        statuses: list[ProviderStatus] = []
        findings: list[Finding] = []
        reputation: list[ReputationReport] = []
        queries = build_queries(number, self.settings)
        configured = [p for p in self.search_providers if p.is_configured()]
        per_provider = max(1, self.settings.max_queries // max(1, len(configured)))

        owns_http = self._http is None
        http = self._http or SafeHTTPClient(
            timeout=self.settings.http_timeout, max_concurrency=self.settings.max_concurrency
        )
        try:
            tasks: list[tuple[ProviderStatus, Awaitable[None], list[Finding]]] = []
            for p in self.search_providers:
                st = ProviderStatus(name=p.name, kind=p.kind, state=ProviderState.SKIPPED)
                statuses.append(st)
                if not p.is_configured():
                    st.state = ProviderState.NOT_CONFIGURED
                    st.message = "needs " + ", ".join(p.requires)
                elif p.online and not online:
                    st.message = "offline mode: live search disabled"
                else:
                    sink: list[Finding] = []
                    tasks.append((st, self._run_search(p, queries[:per_provider], http, sink, st), sink))

            for rp in self.reputation_providers:
                st = ProviderStatus(name=rp.name, kind=rp.kind, state=ProviderState.SKIPPED)
                statuses.append(st)
                if not rp.is_configured():
                    st.state = ProviderState.NOT_CONFIGURED
                    st.message = "needs " + ", ".join(rp.requires)
                elif rp.online and not online:
                    st.message = "offline mode"
                else:
                    tasks.append((st, self._run_reputation(rp, number, http, reputation, st), []))

            for st in statuses:
                await emit({"type": "provider", "status": st.model_dump(mode="json")})

            async def guarded(st: ProviderStatus, coro: Awaitable[None], sink: list[Finding]) -> None:
                start = time.monotonic()
                await emit(
                    {
                        "type": "provider",
                        "status": {**st.model_dump(mode="json"), "state": "running"},
                    }
                )
                try:
                    await asyncio.wait_for(coro, timeout=self.settings.provider_timeout)
                    st.state = ProviderState.OK
                except TimeoutError:
                    st.state = ProviderState.TIMEOUT
                    st.message = f"timed out after {self.settings.provider_timeout:.0f}s (partial results kept)"
                except asyncio.CancelledError:
                    st.state = ProviderState.CANCELLED
                    st.message = "cancelled by user"
                    raise
                except Exception as exc:
                    st.state = ProviderState.ERROR
                    st.message = _error_message(exc)
                    log.warning("provider %s failed: %s", st.name, st.message)
                finally:
                    findings.extend(sink)
                    if st.kind.startswith("web"):
                        st.result_count = len(sink)
                    st.duration_ms = int((time.monotonic() - start) * 1000)
                    if st.state is ProviderState.OK and st.result_count == 0:
                        st.state = ProviderState.EMPTY
                    await emit({"type": "provider", "status": st.model_dump(mode="json")})

            await asyncio.gather(*(guarded(st, c, s) for st, c, s in tasks))
        finally:
            if owns_http:
                await http.aclose()

        groups, hidden = dedupe_and_group(findings, self.settings.exclude_domains)
        risk = assess_risk(number, groups, reputation, statuses)
        summary = build_summary(number, groups, reputation, statuses, hidden)
        live = any(st.state in (ProviderState.OK, ProviderState.EMPTY) and st.kind == "web_search" for st in statuses)
        mode = "demo" if self.settings.demo else ("online" if live else "offline")
        notices = list(NOTICES)
        if mode == "demo":
            notices.insert(0, "DEMO MODE: all search results and reports are SYNTHETIC.")
        inv = Investigation(
            tool_version=__version__,
            mode=mode,
            number=number,
            providers=statuses,
            findings=groups,
            reputation=reputation,
            manual_links=manual_search_links(number, self.settings),
            risk=risk,
            summary=summary,
            notices=notices,
        )
        await emit({"type": "result", "investigation": inv.model_dump(mode="json")})
        return inv

    async def _run_reputation(
        self,
        provider: ReputationProvider,
        number: NormalizedNumber,
        http: SafeHTTPClient,
        sink: list[ReputationReport],
        status: ProviderStatus,
    ) -> None:
        reports = await provider.lookup(number, http)
        sink.extend(reports)
        status.result_count = len(reports)

    async def stream(self, raw: str, *, region: str | None = None, online: bool = True) -> AsyncIterator[Event]:
        """Yield progress events; cancelling the consumer cancels running providers."""
        queue: asyncio.Queue[Event | None] = asyncio.Queue()

        async def put(e: Event) -> None:
            await queue.put(e)

        async def runner() -> None:
            try:
                await self.run(raw, region=region, online=online, on_event=put)
            except Exception as exc:
                await queue.put(
                    {
                        "type": "error",
                        "message": str(exc) if isinstance(exc, ValueError) else "investigation failed",
                    }
                )
            finally:
                await queue.put(None)

        task = asyncio.create_task(runner())
        try:
            while (item := await queue.get()) is not None:
                yield item
        finally:
            if not task.done():
                task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await task
