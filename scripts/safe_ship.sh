#!/usr/bin/env bash
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LOG_DIR="$REPO_DIR/logs"
mkdir -p "$LOG_DIR"

usage() {
  cat <<'USAGE'
Usage: scripts/safe_ship.sh [--slug <slug>] [--prompt "..."] [--pack-file <path>]...

Runs required gates, lightweight secrets scan, generates an offline oracle pack,
then pushes the current branch (sets upstream if missing).

Environment overrides:
  SKIP_DOCS_LINT=1    Skip docs lint gate
  SKIP_TESTS=1        Skip pytest gate
USAGE
}

SLUG="safe-ship"
PROMPT=""
PACK_FILES=()

while [[ $# -gt 0 ]]; do
  case "$1" in
    --slug)
      SLUG="$2"; shift 2;;
    --prompt)
      PROMPT="$2"; shift 2;;
    --pack-file)
      PACK_FILES+=("$2"); shift 2;;
    -h|--help)
      usage; exit 0;;
    *)
      echo "Unknown arg: $1" >&2
      usage; exit 1;;
  esac
done

cd "$REPO_DIR"

if [[ -n "$(git status --porcelain)" ]]; then
  echo "Working tree is dirty. Commit or stash before safe_ship." >&2
  exit 1
fi

STAMP=$(date +"%Y%m%d_%H%M%S")
LOG_FILE="$LOG_DIR/safe_ship_${STAMP}.log"

run_gate() {
  echo "> $*" | tee -a "$LOG_FILE"
  "$@" 2>&1 | tee -a "$LOG_FILE"
}

# Required gates (per AGENTS.md)
run_gate python3 scripts/validate_params.py --strict
run_gate python3 scripts/run_end_of_day.py --verbose
if [[ -z "${SKIP_TESTS:-}" ]]; then
  run_gate pytest -q
else
  echo "> pytest -q (skipped: SKIP_TESTS=1)" | tee -a "$LOG_FILE"
fi

if [[ -x scripts/lint_docs.sh && -z "${SKIP_DOCS_LINT:-}" ]]; then
  run_gate scripts/lint_docs.sh
elif [[ -x scripts/lint_docs.sh ]]; then
  echo "> scripts/lint_docs.sh (skipped: SKIP_DOCS_LINT=1)" | tee -a "$LOG_FILE"
fi

if [[ -x scripts/check_no_db_tracked.sh ]]; then
  run_gate scripts/check_no_db_tracked.sh
fi

# Lightweight secrets scan on last commit
changed_files=()
if git rev-parse HEAD~1 >/dev/null 2>&1; then
  while IFS= read -r line; do
    [[ -n "$line" ]] && changed_files+=("$line")
  done < <(git diff --name-only HEAD~1..HEAD)
else
  while IFS= read -r line; do
    [[ -n "$line" ]] && changed_files+=("$line")
  done < <(git ls-files)
fi

patterns=(
  "BEGIN PRIVATE KEY"
  "AWS_SECRET_ACCESS_KEY"
  "OPENAI_API_KEY"
  "API_KEY="
  "TOKEN="
  "PASSWORD="
  "SECRET="
)

if command -v rg >/dev/null 2>&1; then
  for pat in "${patterns[@]}"; do
    if rg -n --fixed-strings "$pat" "${changed_files[@]}" >/dev/null 2>&1; then
      echo "Secret scan failed: pattern '$pat' found." >&2
      rg -n --fixed-strings "$pat" "${changed_files[@]}" >&2 || true
      exit 1
    fi
  done
else
  for pat in "${patterns[@]}"; do
    if grep -n --fixed-strings "$pat" "${changed_files[@]}" >/dev/null 2>&1; then
      echo "Secret scan failed: pattern '$pat' found." >&2
      grep -n --fixed-strings "$pat" "${changed_files[@]}" >&2 || true
      exit 1
    fi
  done
fi

# Build offline oracle pack evidence
if [[ -z "$PROMPT" ]]; then
  branch=$(git rev-parse --abbrev-ref HEAD || true)
  PROMPT="Review git health and ship evidence for ${branch}."
fi

if [[ ${#PACK_FILES[@]} -eq 0 ]]; then
  PACK_FILES=(
    "AGENTS.md"
    ".gitignore"
    "scripts/safe_ship.sh"
    "scripts/oracle_pack.sh"
    "scripts/oracle_run.sh"
    ".claude/ISSUES.md"
    ".claude/DECISIONS.md"
    ".claude/PROGRESS.md"
    ".claude/SESSION_LOG.md"
  )
fi

PACK_ARGS=("--slug" "$SLUG" "--prompt" "$PROMPT")
for f in "${PACK_FILES[@]}"; do
  if [[ -e "$f" ]]; then
    PACK_ARGS+=("--file" "$f")
  fi
done

scripts/oracle_pack.sh "${PACK_ARGS[@]}"

# Push (set upstream if missing)
if git rev-parse --abbrev-ref --symbolic-full-name @{u} >/dev/null 2>&1; then
  git push
else
  git push -u origin HEAD
fi

# Ensure clean state after
if [[ -n "$(git status --porcelain)" ]]; then
  echo "Working tree not clean after safe_ship." >&2
  exit 1
fi

echo "safe_ship complete: gates passed, pack generated, pushed."
