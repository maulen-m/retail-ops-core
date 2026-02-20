#!/usr/bin/env bash
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SESSION_LOG="$REPO_DIR/.claude/SESSION_LOG.md"

usage() {
  cat <<'USAGE'
Usage: scripts/backup_push.sh --note "<why this backup push>"

Push current branch to origin without running gates.
Requires a clean working tree and a note for the session log.
USAGE
}

NOTE=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --note)
      NOTE="$2"; shift 2;;
    -h|--help)
      usage; exit 0;;
    *)
      echo "Unknown arg: $1" >&2
      usage; exit 1;;
  esac
done

if [[ -z "$NOTE" ]]; then
  echo "Missing required --note." >&2
  usage
  exit 1
fi

cd "$REPO_DIR"

if [[ -n "$(git status --porcelain)" ]]; then
  echo "Working tree is dirty. Commit or stash before backup_push." >&2
  exit 1
fi

branch=$(git rev-parse --abbrev-ref HEAD 2>/dev/null || echo "(unknown)")
head=$(git rev-parse HEAD 2>/dev/null || echo "(unknown)")
timestamp=$(date -Iseconds)

printf 'backup_push note: %s\n' "$NOTE"

printf -- "- %s backup_push: branch=%s head=%s note=%s\n" \
  "$timestamp" "$branch" "$head" "$NOTE" >> "$SESSION_LOG"

if git rev-parse --abbrev-ref --symbolic-full-name @{u} >/dev/null 2>&1; then
  git push
else
  git push -u origin HEAD
fi
