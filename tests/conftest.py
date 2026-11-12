from __future__ import annotations

import os
from collections.abc import Callable, Iterator

import httpx
import pytest

from numbertrace.config import Settings
from numbertrace.net.safe_http import SafeHTTPClient

PUBLIC_IP = ["93.184.216.34"]


@pytest.fixture(autouse=True)
def _isolate_env(monkeypatch: pytest.MonkeyPatch, tmp_path) -> Iterator[None]:
    # Never read the developer's real .env or environment keys during tests.
    for key in list(os.environ):
        if key.startswith("NUMBERTRACE_"):
            monkeypatch.delenv(key, raising=False)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("NUMBERTRACE_HISTORY_FILE", str(tmp_path / "history.jsonl"))
    yield


@pytest.fixture
def settings() -> Settings:
    return Settings(provider_timeout=2, http_timeout=1)


@pytest.fixture
def make_http() -> Callable[..., SafeHTTPClient]:
    def _make(handler: Callable[[httpx.Request], httpx.Response], **kw: object) -> SafeHTTPClient:
        return SafeHTTPClient(
            transport=httpx.MockTransport(handler),
            resolver=lambda host: PUBLIC_IP,
            **kw,  # type: ignore[arg-type]
        )

    return _make
