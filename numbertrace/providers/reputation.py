"""Reputation sources.

Only a local, user-maintained dataset is implemented. We did not find a free spam-report
API with documented terms that clearly allow this use, so instead of guessing we ship an
interface (ReputationProvider) that maintainers can implement for a licensed source.
"""

from __future__ import annotations

import json
from importlib import resources
from pathlib import Path
from typing import Any

from numbertrace.models import NormalizedNumber, ReputationReport
from numbertrace.net.safe_http import SafeHTTPClient
from numbertrace.providers.base import ProviderResponseError, ReputationProvider

MAX_DATASET_BYTES = 5_000_000


def bundled_sample_path() -> Path:
    return Path(str(resources.files("numbertrace") / "data" / "community_reports.sample.json"))


class LocalDatasetReputationProvider(ReputationProvider):
    name = "local_community_dataset"
    requires = ("NUMBERTRACE_COMMUNITY_DATASET (path to a JSON file)",)
    notes = "Offline JSON file of community reports that you maintain. See docs/PROVIDERS.md."

    def __init__(self, path: Path | None) -> None:
        self._path = path
        self._cache: dict[str, Any] | None = None

    def is_configured(self) -> bool:
        return self._path is not None

    def _load(self) -> dict[str, Any]:
        if self._cache is not None:
            return self._cache
        if self._path is None:
            raise ProviderResponseError("dataset not configured")
        if not self._path.is_file():
            raise ProviderResponseError("dataset file not found")
        if self._path.stat().st_size > MAX_DATASET_BYTES:
            raise ProviderResponseError("dataset file too large")
        try:
            data = json.loads(self._path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            raise ProviderResponseError("dataset is not valid JSON") from exc
        if not isinstance(data, dict) or not isinstance(data.get("reports"), list):
            raise ProviderResponseError("dataset must be an object with a 'reports' list")
        self._cache = data
        return data

    async def lookup(self, number: NormalizedNumber, http: SafeHTTPClient | None) -> list[ReputationReport]:
        data = self._load()
        synthetic = bool(data.get("synthetic", False))
        lic = data.get("license") if isinstance(data.get("license"), str) else None
        out: list[ReputationReport] = []
        for row in data["reports"]:
            if not isinstance(row, dict) or row.get("e164") != number.e164:
                continue
            try:
                count = int(row.get("report_count", 1))
            except (TypeError, ValueError):
                count = 1
            out.append(
                ReputationReport(
                    source=str(row.get("source", "unknown"))[:120],
                    category=str(row.get("category", "unspecified"))[:60],
                    summary=str(row.get("summary", ""))[:500],
                    reported_at=str(row["reported_at"])[:40] if row.get("reported_at") else None,
                    report_count=max(1, min(count, 10_000)),
                    synthetic=synthetic or bool(row.get("synthetic", False)),
                    license=lic,
                )
            )
        return out
