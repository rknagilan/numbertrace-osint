"""Safe outbound HTTP: HTTPS only, host allowlist, private-IP (SSRF) blocking,
no redirects, short timeouts, bounded retries and a global concurrency cap."""

from __future__ import annotations

import asyncio
import ipaddress
import logging
import socket
from collections.abc import Callable, Iterable
from typing import Any
from urllib.parse import urlsplit

import httpx

log = logging.getLogger("numbertrace.http")

Resolver = Callable[[str], list[str]]


class UnsafeURLError(ValueError):
    """Raised when a URL fails the outbound safety policy."""


def system_resolver(host: str) -> list[str]:
    infos = socket.getaddrinfo(host, 443, proto=socket.IPPROTO_TCP)
    return sorted({str(info[4][0]) for info in infos})


def _is_public_ip(addr: str) -> bool:
    ip = ipaddress.ip_address(addr)
    return not (
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_multicast
        or ip.is_reserved
        or ip.is_unspecified
        or (
            isinstance(ip, ipaddress.IPv6Address)
            and ip.ipv4_mapped is not None
            and not _is_public_ip(str(ip.ipv4_mapped))
        )
    )


def check_url(url: str, allowed_hosts: Iterable[str], resolver: Resolver | None) -> str:
    """Validate a URL against the policy. Returns the hostname on success."""
    parts = urlsplit(url)
    if parts.scheme != "https":
        raise UnsafeURLError("only https:// URLs are allowed")
    if parts.username or parts.password:
        raise UnsafeURLError("credentials in URL are not allowed")
    host = (parts.hostname or "").lower().rstrip(".")
    if not host:
        raise UnsafeURLError("URL has no host")
    if parts.port not in (None, 443):
        raise UnsafeURLError("non-standard ports are not allowed")
    try:
        ipaddress.ip_address(host)
    except ValueError:
        pass
    else:
        raise UnsafeURLError("literal IP addresses are not allowed")
    allowed = {h.lower() for h in allowed_hosts}
    if host not in allowed:
        raise UnsafeURLError(f"host '{host}' is not on the provider allowlist")
    if resolver is not None:
        try:
            addrs = resolver(host)
        except OSError as exc:
            raise UnsafeURLError(f"DNS lookup failed for '{host}'") from exc
        if not addrs or not all(_is_public_ip(a) for a in addrs):
            raise UnsafeURLError(f"host '{host}' resolves to a non-public address")
    return host


class SafeHTTPClient:
    """Thin wrapper around httpx.AsyncClient enforcing the outbound policy."""

    def __init__(
        self,
        *,
        timeout: float = 8.0,
        retries: int = 1,
        max_concurrency: int = 2,
        transport: httpx.AsyncBaseTransport | None = None,
        resolver: Resolver | None = system_resolver,
        max_response_bytes: int = 2_000_000,
    ) -> None:
        self._timeout = timeout
        self._retries = max(0, min(retries, 3))
        self._sem = asyncio.Semaphore(max_concurrency)
        self._resolver = resolver
        self._max_bytes = max_response_bytes
        self._client = httpx.AsyncClient(
            timeout=httpx.Timeout(timeout),
            follow_redirects=False,
            transport=transport,
            headers={"User-Agent": "NumberTrace-OSINT/0.1 (+open-source caller verification)"},
        )

    async def aclose(self) -> None:
        await self._client.aclose()

    async def get_json(
        self,
        url: str,
        *,
        allowed_hosts: Iterable[str],
        params: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> Any:
        allowed = list(allowed_hosts)
        if self._resolver is not None:
            await asyncio.to_thread(check_url, url, allowed, self._resolver)
        else:
            check_url(url, allowed, None)
        last_exc: Exception | None = None
        for attempt in range(self._retries + 1):
            try:
                async with self._sem:
                    resp = await self._client.get(url, params=params, headers=headers)
                if resp.status_code in (429, 502, 503, 504) and attempt < self._retries:
                    await asyncio.sleep(0.5 * (attempt + 1))
                    continue
                if resp.is_redirect:
                    raise UnsafeURLError("redirects are not followed")
                resp.raise_for_status()
                if len(resp.content) > self._max_bytes:
                    raise ValueError("provider response too large")
                return resp.json()
            except httpx.TransportError as exc:
                last_exc = exc
                if attempt < self._retries:
                    await asyncio.sleep(0.5 * (attempt + 1))
                    continue
                raise
        assert last_exc is not None
        raise last_exc
