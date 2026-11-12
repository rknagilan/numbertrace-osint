"""Environment self-check with actionable fixes (Kali/Linux/macOS/Windows)."""

from __future__ import annotations

import importlib.util
import platform
import shutil
import socket
import sys
from dataclasses import dataclass
from pathlib import Path

from numbertrace.config import Settings


@dataclass
class Check:
    name: str
    status: str  # ok | warn | fail | info
    detail: str
    fix: str = ""


def run_checks(settings: Settings, offline: bool = False) -> list[Check]:
    checks: list[Check] = []
    v = sys.version_info
    if v >= (3, 12):
        checks.append(Check("Python version", "ok", platform.python_version()))
    else:
        checks.append(
            Check(
                "Python version",
                "fail",
                platform.python_version(),
                "Install Python 3.12+: sudo apt update && sudo apt install python3 python3-venv",
            )
        )

    in_venv = sys.prefix != getattr(sys, "base_prefix", sys.prefix)
    checks.append(
        Check(
            "Virtual environment",
            "ok" if in_venv else "warn",
            sys.prefix if in_venv else "not inside a venv",
            "" if in_venv else "Run: python3 -m venv .venv && source .venv/bin/activate",
        )
    )

    machine = platform.machine() or "unknown"
    checks.append(Check("CPU architecture", "info", f"{machine} on {platform.system()} {platform.release()}"))

    for mod, pkg, required in (
        ("phonenumbers", "phonenumbers", True),
        ("pydantic", "pydantic", True),
        ("typer", "typer", True),
        ("rich", "rich", True),
        ("httpx", "httpx", True),
        ("fastapi", "fastapi (web extra)", False),
        ("uvicorn", "uvicorn (web extra)", False),
    ):
        found = importlib.util.find_spec(mod) is not None
        if found:
            checks.append(Check(f"Package {pkg}", "ok", "installed"))
        elif required:
            checks.append(Check(f"Package {pkg}", "fail", "missing", "Run: pip install -e ."))
        else:
            checks.append(
                Check(
                    f"Package {pkg}",
                    "info",
                    "not installed (optional)",
                    "For the web dashboard run: pip install -e '.[web]'",
                )
            )

    try:
        usage = shutil.disk_usage(Path.cwd())
        free_mb = usage.free // (1024 * 1024)
        checks.append(
            Check(
                "Free disk space",
                "ok" if free_mb > 300 else "warn",
                f"{free_mb} MB free",
                "" if free_mb > 300 else "Free space: sudo apt clean; pip cache purge; remove old files",
            )
        )
    except OSError:
        checks.append(Check("Free disk space", "warn", "could not read disk usage"))

    if offline:
        checks.append(Check("Network/DNS", "info", "skipped (--offline)"))
    else:
        old = socket.getdefaulttimeout()
        socket.setdefaulttimeout(3)
        try:
            socket.getaddrinfo("api.search.brave.com", 443)
            checks.append(Check("Network/DNS", "ok", "api.search.brave.com resolves"))
        except OSError:
            checks.append(
                Check(
                    "Network/DNS",
                    "warn",
                    "cannot resolve api.search.brave.com",
                    "Offline mode still works. Check Wi-Fi, /etc/resolv.conf, or proxy settings.",
                )
            )
        finally:
            socket.setdefaulttimeout(old)

    if settings.brave_api_key:
        checks.append(Check("Brave Search API key", "ok", "configured (value hidden)"))
    else:
        checks.append(
            Check(
                "Brave Search API key",
                "info",
                "not set: manual search links will be used",
                "Optional: add NUMBERTRACE_BRAVE_API_KEY to .env",
            )
        )
    if settings.google_cse_key and settings.google_cse_cx:
        checks.append(Check("Google CSE (legacy)", "warn", "configured; Google says it stops 2027-01-01"))
    if settings.community_dataset:
        p = settings.community_dataset
        checks.append(
            Check(
                "Community dataset",
                "ok" if p.is_file() else "fail",
                str(p),
                "" if p.is_file() else "Fix NUMBERTRACE_COMMUNITY_DATASET path in .env",
            )
        )
    checks.append(Check("Local history", "info", "enabled" if settings.history_enabled else "disabled (default)"))
    return checks
