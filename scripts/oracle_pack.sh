#!/usr/bin/env bash
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ORCH_HOME="${ORCH_HOME:-$HOME/Docs/Oracle/agent-scripts-main}"
PACK_SCRIPT="$ORCH_HOME/scripts/oracle_pack_local.py"

usage() {
  cat <<'USAGE'
Usage: scripts/oracle_pack.sh --slug <slug> [--task-id TASK-###] [--prompt "..."] [--prompt-file path] [--out-dir path] --file <path|glob> [--file <path|glob> ...]

Offline pack generator (no network, no browser automation).
If --task-id is omitted, it is inferred from the current git branch (TASK-###), or TASK-000.
USAGE
}

TASK_ID=""
SLUG=""
PROMPT=""
PROMPT_FILE=""
OUT_DIR=""
FILES=()

while [[ $# -gt 0 ]]; do
  case "$1" in
    --task|--task-id)
      TASK_ID="$2"; shift 2;;
    --slug)
      SLUG="$2"; shift 2;;
    --prompt)
      PROMPT="$2"; shift 2;;
    --prompt-file)
      PROMPT_FILE="$2"; shift 2;;
    --out-dir)
      OUT_DIR="$2"; shift 2;;
    --file)
      FILES+=("$2"); shift 2;;
    -h|--help)
      usage; exit 0;;
    *)
      echo "Unknown arg: $1"; usage; exit 1;;
  esac
done

if [[ -z "$SLUG" ]]; then
  echo "Missing --slug"; usage; exit 1
fi

if [[ -z "$PROMPT" && -z "$PROMPT_FILE" ]]; then
  echo "Missing --prompt or --prompt-file"; usage; exit 1
fi

if [[ ! -f "$PACK_SCRIPT" ]]; then
  echo "Missing pack script: $PACK_SCRIPT" >&2
  echo "Set ORCH_HOME to your control plane repo (default: \$HOME/Docs/Oracle/agent-scripts-main)." >&2
  exit 1
fi

if [[ -z "$TASK_ID" ]]; then
  BRANCH=$(git -C "$REPO_DIR" rev-parse --abbrev-ref HEAD 2>/dev/null || true)
  if [[ "$BRANCH" =~ (TASK-[0-9]+) ]]; then
    TASK_ID="${BASH_REMATCH[1]}"
  else
    TASK_ID="TASK-000"
  fi
fi

if [[ ${#FILES[@]} -eq 0 ]]; then
  echo "At least one --file is required."; usage; exit 1
fi

ARGS=("--repo" "$REPO_DIR" "--slug" "$SLUG" "--task-id" "$TASK_ID")
if [[ -n "$PROMPT" ]]; then
  ARGS+=("--prompt" "$PROMPT")
fi
if [[ -n "$PROMPT_FILE" ]]; then
  ARGS+=("--prompt-file" "$PROMPT_FILE")
fi
if [[ -n "$OUT_DIR" ]]; then
  ARGS+=("--out-dir" "$OUT_DIR")
fi
for f in "${FILES[@]}"; do
  ARGS+=("--file" "$f")
done

prompt_text="$PROMPT"
if [[ -n "$PROMPT_FILE" ]]; then
  prompt_text="$(cat "$PROMPT_FILE")"
fi
trimmed="$(printf '%s' "$prompt_text" | sed -e 's/^[[:space:]]*//')"
lowered="$(printf '%s' "$trimmed" | tr '[:upper:]' '[:lower:]')"
if [[ -z "$trimmed" ]]; then
  echo "Prompt is empty." >&2
  exit 1
fi
if [[ "$lowered" == "[system]"* || "$lowered" == "[user]"* || "$lowered" == "[assistant]"* ]]; then
  echo "Prompt must not start with role headers like [SYSTEM]/[USER]." >&2
  exit 1
fi
if [[ "$lowered" == "system:"* || "$lowered" == "user:"* || "$lowered" == "assistant:"* ]]; then
  echo "Prompt must not start with role headers like SYSTEM:/USER:." >&2
  exit 1
fi
if [[ "$lowered" == "you are oracle"* ]]; then
  echo "Prompt must not start with 'You are Oracle'." >&2
  exit 1
fi

python3 "$PACK_SCRIPT" "${ARGS[@]}"
