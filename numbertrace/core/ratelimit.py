"""Simple in-memory sliding-window rate limiter (per client key)."""

from __future__ import annotations

import threading
import time
from collections import deque


class RateLimiter:
    def __init__(self, limit: int, window_seconds: float = 60.0, max_keys: int = 1000) -> None:
        self.limit = limit
        self.window = window_seconds
        self.max_keys = max_keys
        self._hits: dict[str, deque[float]] = {}
        self._lock = threading.Lock()

    def allow(self, key: str, now: float | None = None) -> bool:
        now = time.monotonic() if now is None else now
        with self._lock:
            if key not in self._hits and len(self._hits) >= self.max_keys:
                self._hits.clear()  # bounded memory; fail closed would block local users
            q = self._hits.setdefault(key, deque())
            while q and now - q[0] >= self.window:
                q.popleft()
            if len(q) >= self.limit:
                return False
            q.append(now)
            return True

    def retry_after(self, key: str, now: float | None = None) -> int:
        now = time.monotonic() if now is None else now
        q = self._hits.get(key)
        if not q:
            return 0
        return max(1, int(self.window - (now - q[0])) + 1)
