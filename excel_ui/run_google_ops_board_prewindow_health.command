#!/bin/bash

cd ~/Docs/Autonomous_business
source .venv/bin/activate 2>/dev/null || true

if [ -f ".env" ]; then
    ENV_EXPORTS=$(python3 - <<'PY'
import re
import shlex
from pathlib import Path

p = Path(".env")
if not p.exists():
    raise SystemExit(0)

shell_key_re = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")

for raw in p.read_text(encoding="utf-8").splitlines():
    line = raw.strip()
    if not line or line.startswith("#"):
        continue
    if "=" not in line:
        continue
    key, val = line.split("=", 1)
    key = key.strip()
    if not key or not shell_key_re.match(key):
        continue
    print(f"export {key}={shlex.quote(val.strip())}")
PY
)
    if [ -n "${ENV_EXPORTS}" ]; then
        eval "${ENV_EXPORTS}"
    fi
fi

export ENABLE_KASPI_WORKBOOK_MAP_SYNC=1
export PYTHONUNBUFFERED=1
exec python3 -u scripts/run_google_ops_board_prewindow_health.py --apply "$@"
