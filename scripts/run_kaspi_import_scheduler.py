#!/usr/bin/env python3
"""LaunchAgent entrypoint for Kaspi import schedule."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent
COMMAND_PATH = PROJECT_ROOT / "excel_ui" / "run_full_import.command"
DB_CHECK_PATH = PROJECT_ROOT / "scripts" / "check_local_app_db.py"
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.google_ops_board_automation_common import ensure_kaspi_api_call_ledger_env, today_almaty  # noqa: E402


def main() -> int:
    project_root = PROJECT_ROOT
    command_path = COMMAND_PATH

    if not command_path.exists():
        print(f"ERROR: missing scheduler command: {command_path}", file=sys.stderr)
        return 78
    if not DB_CHECK_PATH.exists():
        print(f"ERROR: missing DB preflight script: {DB_CHECK_PATH}", file=sys.stderr)
        return 78

    env = os.environ.copy()
    env.setdefault("TERM", "dumb")
    ensure_kaspi_api_call_ledger_env(env, target_date=today_almaty(), project_root=PROJECT_ROOT)
    if env.get("KASPI_API_CALL_LEDGER_PATH"):
        os.environ.setdefault("KASPI_API_CALL_LEDGER_PATH", env["KASPI_API_CALL_LEDGER_PATH"])

    check_cmd = [
        sys.executable,
        str(DB_CHECK_PATH),
        "--db-path",
        str(project_root / "db" / "app.db"),
    ]
    check = subprocess.run(check_cmd, cwd=str(project_root), env=env)
    if check.returncode != 0:
        print("ERROR: local DB preflight failed; skipping scheduled import.", file=sys.stderr)
        return int(check.returncode)

    result = subprocess.run(["/bin/bash", str(command_path)], cwd=str(project_root), env=env)
    return int(result.returncode)


if __name__ == "__main__":
    raise SystemExit(main())
