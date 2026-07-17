#!/usr/bin/env python3
"""LaunchAgent entrypoint for Google Ops Board pre-window health."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


PROJECT_ROOT = Path("~/Docs/Autonomous_business")
SCRIPT_PATH = PROJECT_ROOT / "scripts" / "run_google_ops_board_prewindow_health.py"
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.google_ops_board_automation_common import ensure_kaspi_api_call_ledger_env, today_almaty  # noqa: E402


def main() -> int:
    if not SCRIPT_PATH.exists():
        print(f"ERROR: missing Google Ops Board prewindow health script: {SCRIPT_PATH}", file=sys.stderr)
        return 78

    env = os.environ.copy()
    env.setdefault("TERM", "dumb")
    env.setdefault("PYTHONUNBUFFERED", "1")
    ensure_kaspi_api_call_ledger_env(env, target_date=today_almaty(), project_root=PROJECT_ROOT)
    if env.get("KASPI_API_CALL_LEDGER_PATH"):
        os.environ.setdefault("KASPI_API_CALL_LEDGER_PATH", env["KASPI_API_CALL_LEDGER_PATH"])

    service_account_json = str(env.get("AB_GOOGLE_SERVICE_ACCOUNT_JSON") or "").strip()
    if not service_account_json or not Path(service_account_json).exists():
        print("ERROR: AB_GOOGLE_SERVICE_ACCOUNT_JSON is missing or does not exist.", file=sys.stderr)
        return 78

    cmd = [
        sys.executable,
        str(SCRIPT_PATH),
        "--profile",
        "closeout",
        "--reason",
        "scheduled_prewindow",
    ]
    if str(env.get("AB_GOOGLE_OPS_BOARD_SPREADSHEET_ID") or "").strip():
        cmd.extend(["--spreadsheet-id", str(env["AB_GOOGLE_OPS_BOARD_SPREADSHEET_ID"]).strip()])
    cmd.extend(["--service-account-json", service_account_json])
    result = subprocess.run(cmd, cwd=str(PROJECT_ROOT), env=env)
    return int(result.returncode)


if __name__ == "__main__":
    raise SystemExit(main())
