"""Opt-in local history. OFF by default. Stores only masked numbers and summary fields."""

from __future__ import annotations

import contextlib
import json
import os
import sys
from pathlib import Path
from typing import Any

from numbertrace.models import Investigation


def data_dir() -> Path:
    if sys.platform.startswith("win"):
        base = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
    elif sys.platform == "darwin":
        base = Path.home() / "Library" / "Application Support"
    else:
        base = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share"))
    return base / "numbertrace"


def history_path() -> Path:
    override = os.environ.get("NUMBERTRACE_HISTORY_FILE")
    return Path(override) if override else data_dir() / "history.jsonl"


def record(inv: Investigation) -> None:
    path = history_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    entry = {
        "at": inv.generated_at.isoformat(),
        "number_masked": inv.number.input_masked,
        "country_code": inv.number.country_code,
        "mode": inv.mode,
        "risk_level": inv.risk.level,
    }
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(entry) + "\n")
    with contextlib.suppress(OSError):
        path.chmod(0o600)


def load() -> list[dict[str, Any]]:
    path = history_path()
    if not path.is_file():
        return []
    out = []
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return out


def clear() -> bool:
    path = history_path()
    if path.exists():
        path.unlink()
        return True
    return False
