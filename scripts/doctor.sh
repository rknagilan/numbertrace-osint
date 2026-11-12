#!/usr/bin/env bash
# Runs `numbertrace doctor` from the project venv, with hints if the venv is missing.
set -uo pipefail
cd "$(dirname "$0")/.."
if [ ! -x .venv/bin/numbertrace ]; then
  echo "NumberTrace is not installed in .venv yet."
  echo "Fix: bash scripts/install_kali.sh"
  exit 1
fi
exec .venv/bin/numbertrace doctor "$@"
