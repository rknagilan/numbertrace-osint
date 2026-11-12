#!/usr/bin/env bash
# NumberTrace OSINT installer for Kali Linux / Debian / Ubuntu (x86_64 and ARM64).
# - Never uses sudo pip, never uses --break-system-packages.
# - Installs into a project-local virtual environment (.venv).
# Usage:  bash scripts/install_kali.sh            (light: CLI only)
#         bash scripts/install_kali.sh --web      (adds the local dashboard)
#         bash scripts/install_kali.sh --dev      (adds tests/lint tools)
set -euo pipefail

EXTRA=""
case "${1:-}" in
  --web) EXTRA="[web]" ;;
  --dev) EXTRA="[dev]" ;;
  "" ) ;;
  *) echo "Unknown option: $1 (use --web or --dev)"; exit 2 ;;
esac

cd "$(dirname "$0")/.."
echo "==> NumberTrace installer (arch: $(uname -m))"

if [ "$(id -u)" -eq 0 ]; then
  echo "!! You are running as root. This is not needed. Run as your normal user instead."
fi

if ! command -v python3 >/dev/null 2>&1; then
  echo "!! python3 not found. Install it with:"
  echo "   sudo apt update && sudo apt install -y python3 python3-venv python3-pip"
  exit 1
fi

PYV=$(python3 -c 'import sys; print("%d.%d" % sys.version_info[:2])')
if ! python3 -c 'import sys; sys.exit(0 if sys.version_info >= (3,12) else 1)'; then
  echo "!! Python $PYV found, but 3.12+ is required."
  echo "   sudo apt update && sudo apt full-upgrade -y   (Kali rolling ships 3.12+)"
  exit 1
fi
echo "==> Python $PYV OK"

if ! python3 -c 'import venv, ensurepip' >/dev/null 2>&1; then
  echo "!! The venv module is missing. Install it with (needs your password once):"
  echo "   sudo apt install -y python3-venv"
  exit 1
fi

FREE_MB=$(df -Pm . | awk 'NR==2 {print $4}')
if [ "${FREE_MB:-0}" -lt 300 ]; then
  echo "!! Only ${FREE_MB} MB free. Need ~300 MB. Try: sudo apt clean; rm -rf ~/.cache/pip"
  exit 1
fi

if [ ! -d .venv ]; then
  echo "==> Creating virtual environment in .venv"
  python3 -m venv .venv
fi
# shellcheck disable=SC1091
source .venv/bin/activate
python -m pip install --upgrade pip --quiet
echo "==> Installing NumberTrace ${EXTRA:-(light)}"
pip install --quiet -e ".${EXTRA}"

if [ ! -f .env ] && [ -f .env.example ]; then
  cp .env.example .env
  chmod 600 .env
  echo "==> Created .env from .env.example (edit it to add optional API keys)"
fi

echo
echo "==> Done. Next steps:"
echo "   source .venv/bin/activate"
echo "   numbertrace doctor"
echo "   numbertrace demo"
