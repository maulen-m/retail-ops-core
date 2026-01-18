#!/bin/bash
set -euo pipefail

load_env() {
  local env_path="${1:-.env}"
  if [ ! -f "$env_path" ]; then
    return 0
  fi
  python3 - "$env_path" <<'PY'
import shlex
import sys
from pathlib import Path

path = Path(sys.argv[1])
for raw_line in path.read_text(encoding="utf-8").splitlines():
    line = raw_line.strip()
    if not line or line.startswith("#"):
        continue
    if "=" not in line:
        continue
    key, value = line.split("=", 1)
    key = key.strip()
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
        value = value[1:-1]
    print(f"export {key}={shlex.quote(value)}")
PY
}

eval "$(load_env "${1:-.env}")"
