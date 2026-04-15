#!/usr/bin/env python3
"""LaunchAgent entrypoint for Google Ops Board publish schedule."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


PROJECT_ROOT = Path("~/Docs/Autonomous_business")
SCRIPT_PATH = PROJECT_ROOT / "scripts" / "sync_google_ops_board.py"
DB_CHECK_PATH = PROJECT_ROOT / "scripts" / "check_local_app_db.py"


def main() -> int:
    if not SCRIPT_PATH.exists():
        print(f"ERROR: missing Google Ops Board publisher: {SCRIPT_PATH}", file=sys.stderr)
        return 78
    if not DB_CHECK_PATH.exists():
        print(f"ERROR: missing DB preflight script: {DB_CHECK_PATH}", file=sys.stderr)
        return 78

    env = os.environ.copy()
    env.setdefault("TERM", "dumb")
    env.setdefault("PYTHONUNBUFFERED", "1")

    service_account_json = str(env.get("AB_GOOGLE_SERVICE_ACCOUNT_JSON") or "").strip()
    if not service_account_json or not Path(service_account_json).exists():
        print("ERROR: AB_GOOGLE_SERVICE_ACCOUNT_JSON is missing or does not exist.", file=sys.stderr)
        return 78

    check_cmd = [
        sys.executable,
        str(DB_CHECK_PATH),
        "--db-path",
        str(PROJECT_ROOT / "db" / "app.db"),
    ]
    check = subprocess.run(check_cmd, cwd=str(PROJECT_ROOT), env=env)
    if check.returncode != 0:
        print("ERROR: local DB preflight failed; skipping Google Ops Board publish.", file=sys.stderr)
        return int(check.returncode)

    cmd = [sys.executable, str(SCRIPT_PATH), "--apply"]
    if str(env.get("AB_GOOGLE_OPS_BOARD_SPREADSHEET_ID") or "").strip():
        cmd.extend(["--spreadsheet-id", str(env["AB_GOOGLE_OPS_BOARD_SPREADSHEET_ID"]).strip()])
    cmd.extend(["--service-account-json", service_account_json])
    result = subprocess.run(cmd, cwd=str(PROJECT_ROOT), env=env)
    return int(result.returncode)


if __name__ == "__main__":
    raise SystemExit(main())
