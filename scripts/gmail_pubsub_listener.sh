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

if [[ -z "${GOOGLE_APPLICATION_CREDENTIALS:-}" ]]; then
  if [[ -n "${GMAIL_PUSH_SERVICE_ACCOUNT_JSON:-}" ]]; then
    export GOOGLE_APPLICATION_CREDENTIALS="$GMAIL_PUSH_SERVICE_ACCOUNT_JSON"
  elif [[ -n "${GCP_SERVICE_ACCOUNT_JSON:-}" ]]; then
    export GOOGLE_APPLICATION_CREDENTIALS="$GCP_SERVICE_ACCOUNT_JSON"
  elif [[ -f "$ROOT/config/gmail/service_account.json" ]]; then
    export GOOGLE_APPLICATION_CREDENTIALS="$ROOT/config/gmail/service_account.json"
  fi
fi
"$PY" "$ROOT/scripts/gmail_pubsub_listener.py"
