#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'USAGE'
Usage: scripts/oracle_run.sh --confirm --prompt "..." [--slug "..."] --file <path|glob> [--file <path|glob> ...]

Runs Oracle in browser mode (network + browser automation) using GPT-5.2 Pro.
Requires --confirm to proceed.
USAGE
}

if [[ "${1:-}" != "--confirm" ]]; then
  echo "Refusing to run: this uses network + browser automation. Re-run with --confirm." >&2
  usage
  exit 1
fi
shift

PROMPT=""
PROMPT_FILE=""
SLUG=""
FILES=()

while [[ $# -gt 0 ]]; do
  case "$1" in
    --prompt)
      PROMPT="$2"; shift 2;;
    --prompt-file)
      PROMPT_FILE="$2"; shift 2;;
    --slug)
      SLUG="$2"; shift 2;;
    --file)
      FILES+=("$2"); shift 2;;
    -h|--help)
      usage; exit 0;;
    *)
      echo "Unknown arg: $1"; usage; exit 1;;
  esac
done

if [[ -z "$PROMPT" && -z "$PROMPT_FILE" ]]; then
  echo "Missing --prompt or --prompt-file." >&2
  usage
  exit 1
fi

if [[ ${#FILES[@]} -eq 0 ]]; then
  echo "At least one --file is required." >&2
  usage
  exit 1
fi

if [[ -n "$PROMPT_FILE" ]]; then
  PROMPT=$(cat "$PROMPT_FILE")
fi

trimmed="$(printf '%s' "$PROMPT" | sed -e 's/^[[:space:]]*//')"
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

CMD=("npx" "-y" "@steipete/oracle" "--engine" "browser" "--model" "gpt-5.2-pro" "-p" "$PROMPT")
if [[ -n "$SLUG" ]]; then
  CMD+=("--slug" "$SLUG")
fi
for f in "${FILES[@]}"; do
  CMD+=("--file" "$f")
done

"${CMD[@]}"
