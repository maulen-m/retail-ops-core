#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENV="${VENV_PATH:-~/Docs/Autonomous_business/.venv}"
PY="$VENV/bin/python"

if [[ ! -x "$PY" ]]; then
  PY="$(command -v python3)"
fi

cd "$ROOT"
"$PY" "$ROOT/scripts/gmail_pubsub_listener.py"
