#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENV="${VENV_PATH:-$ROOT/.venv}"
PY="$VENV/bin/python"

if [[ ! -x "$PY" ]]; then
  PY="$(command -v python3)"
fi

cd "$ROOT"
# shellcheck disable=SC1091
source "$ROOT/scripts/load_dotenv.sh"
load_dotenv "$ROOT/.env"
"$PY" "$ROOT/scripts/gmail_watch_setup.py"
