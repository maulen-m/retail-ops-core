#!/usr/bin/env bash
set -euo pipefail

ROOT="$(git rev-parse --show-toplevel)"
cd "$ROOT"

tracked_db="$(git ls-files '*.db' || true)"
staged_db="$(git diff --cached --name-only -- '*.db' || true)"

if [[ -n "$tracked_db" || -n "$staged_db" ]]; then
  echo "ERROR: .db files must not be tracked or staged." >&2
  [[ -n "$tracked_db" ]] && echo "Tracked:"$'\n'"$tracked_db" >&2
  [[ -n "$staged_db" ]] && echo "Staged:"$'\n'"$staged_db" >&2
  exit 1
fi

echo "DB guard OK (no tracked/staged .db files)."
