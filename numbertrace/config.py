"""Configuration loaded from environment variables and an optional `.env` file.

We parse `.env` ourselves (tiny, no extra dependency) and never log values.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field, field_validator

HARD_MAX_VARIANTS = 12
HARD_MAX_QUERIES = 20


def load_dotenv(path: Path) -> dict[str, str]:
    """Parse a simple KEY=VALUE `.env` file. Unknown/invalid lines are ignored."""
    values: dict[str, str] = {}
    if not path.is_file():
        return values
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        value = value.strip().strip('"').strip("'")
        values[key.strip()] = value
    return values


def _split(value: str | None) -> list[str]:
    if not value:
        return []
    return [part.strip().lower() for part in value.split(",") if part.strip()]


class Settings(BaseModel):
    default_region: str = "LK"
    brave_api_key: str | None = None
    google_cse_key: str | None = None
    google_cse_cx: str | None = None
    max_variants: int = Field(default=4, ge=1, le=HARD_MAX_VARIANTS)
    max_queries: int = Field(default=6, ge=1, le=HARD_MAX_QUERIES)
    http_timeout: float = Field(default=8.0, gt=0, le=30)
    provider_timeout: float = Field(default=15.0, gt=0, le=60)
    max_concurrency: int = Field(default=2, ge=1, le=4)
    api_rate_limit_per_minute: int = Field(default=10, ge=1, le=120)
    include_domains: list[str] = Field(default_factory=list)
    exclude_domains: list[str] = Field(default_factory=list)
    community_dataset: Path | None = None
    history_enabled: bool = False
    demo: bool = False

    @field_validator("default_region")
    @classmethod
    def _region_upper(cls, v: str) -> str:
        return v.strip().upper() or "LK"

    @property
    def has_live_search(self) -> bool:
        return bool(self.brave_api_key) or bool(self.google_cse_key and self.google_cse_cx)


def get_settings(env_file: Path | None = None, **overrides: Any) -> Settings:
    """Build settings: `.env` file < real environment < explicit overrides."""
    env: dict[str, str] = {}
    env.update(load_dotenv(env_file or Path.cwd() / ".env"))
    env.update({k: v for k, v in os.environ.items() if k.startswith("NUMBERTRACE_")})

    def get(name: str) -> str | None:
        val = env.get(f"NUMBERTRACE_{name}")
        return val if val not in (None, "") else None

    data: dict[str, object] = {}
    simple = {
        "default_region": "DEFAULT_REGION",
        "brave_api_key": "BRAVE_API_KEY",
        "google_cse_key": "GOOGLE_CSE_KEY",
        "google_cse_cx": "GOOGLE_CSE_CX",
        "max_variants": "MAX_VARIANTS",
        "max_queries": "MAX_QUERIES",
        "http_timeout": "HTTP_TIMEOUT",
        "provider_timeout": "PROVIDER_TIMEOUT",
        "max_concurrency": "MAX_CONCURRENCY",
        "api_rate_limit_per_minute": "API_RATE_LIMIT_PER_MINUTE",
        "community_dataset": "COMMUNITY_DATASET",
    }
    for field, key in simple.items():
        val = get(key)
        if val is not None:
            data[field] = val
    data["include_domains"] = _split(get("INCLUDE_DOMAINS"))
    data["exclude_domains"] = _split(get("EXCLUDE_DOMAINS"))
    data["history_enabled"] = (get("HISTORY") or "0").lower() in {"1", "true", "yes"}
    data["demo"] = (get("DEMO") or "0").lower() in {"1", "true", "yes"}
    data.update({k: v for k, v in overrides.items() if v is not None})
    return Settings.model_validate(data)
