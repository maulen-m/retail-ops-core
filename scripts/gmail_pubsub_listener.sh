#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENV="${VENV_PATH:-~/Docs/Autonomous_business/.venv}"
PY="$VENV/bin/python"

if [[ ! -x "$PY" ]]; then
  PY="$(command -v python3)"
fi

cd "$ROOT"
if [[ -z "${GOOGLE_APPLICATION_CREDENTIALS:-}" && -f "$ROOT/config/gmail/service_account.json" ]]; then
  export GOOGLE_APPLICATION_CREDENTIALS="$ROOT/config/gmail/service_account.json"
fi
"$PY" "$ROOT/scripts/gmail_pubsub_listener.py"
