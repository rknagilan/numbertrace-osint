"""Provider interfaces. Providers are injected into the Investigator."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass

from numbertrace.models import NormalizedNumber, ProviderInfo, ReputationReport
from numbertrace.net.safe_http import SafeHTTPClient


class ProviderResponseError(RuntimeError):
    """The provider answered with something we could not safely parse."""


@dataclass(frozen=True)
class RawHit:
    title: str
    url: str
    snippet: str


class SearchProvider(ABC):
    name: str = "search"
    kind: str = "web_search"
    requires: tuple[str, ...] = ()
    allowed_hosts: tuple[str, ...] = ()
    online: bool = True
    notes: str = ""

    @abstractmethod
    def is_configured(self) -> bool: ...

    @abstractmethod
    async def search(self, query: str, http: SafeHTTPClient) -> list[RawHit]: ...

    def info(self) -> ProviderInfo:
        return ProviderInfo(
            name=self.name,
            kind=self.kind,
            configured=self.is_configured(),
            requires=list(self.requires),
            online=self.online,
            notes=self.notes,
        )


class ReputationProvider(ABC):
    name: str = "reputation"
    kind: str = "reputation"
    requires: tuple[str, ...] = ()
    online: bool = False
    notes: str = ""

    @abstractmethod
    def is_configured(self) -> bool: ...

    @abstractmethod
    async def lookup(self, number: NormalizedNumber, http: SafeHTTPClient | None) -> list[ReputationReport]: ...

    def info(self) -> ProviderInfo:
        return ProviderInfo(
            name=self.name,
            kind=self.kind,
            configured=self.is_configured(),
            requires=list(self.requires),
            online=self.online,
            notes=self.notes,
        )
