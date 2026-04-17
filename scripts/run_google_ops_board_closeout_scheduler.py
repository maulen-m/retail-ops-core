#!/usr/bin/env python3
"""LaunchAgent entrypoint for the 18:30 Google Ops Board closeout run."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path("~/Docs/Autonomous_business")
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.integrations.google_ops_board import (  # noqa: E402
    DEFAULT_CONTRACT_PATH,
    GoogleOpsBoardClient,
    load_ops_board_contract,
    resolve_service_account_json,
    resolve_spreadsheet_id,
)
from scripts.google_ops_board_automation_common import (  # noqa: E402
    GoogleOpsBoardAutomationLock,
    closeout_completion_state,
    today_almaty,
)
SCRIPT_PATH = PROJECT_ROOT / "scripts" / "run_google_ops_board_closeout.py"
DB_CHECK_PATH = PROJECT_ROOT / "scripts" / "check_local_app_db.py"
IDENTITY_SYNC_WRITE_ENV_GATE = "ENABLE_KASPI_WORKBOOK_MAP_SYNC"


def _closeout_already_completed(*, service_account_json: str, spreadsheet_id_override: str | None) -> bool:
    contract = load_ops_board_contract(DEFAULT_CONTRACT_PATH)
    spreadsheet_id = resolve_spreadsheet_id(spreadsheet_id_override, contract=contract)
    client = GoogleOpsBoardClient.from_service_account_file(spreadsheet_id, Path(service_account_json))
    state = closeout_completion_state(client=client, contract=contract, target_date=today_almaty())
    if state["completed"]:
        run_id = state["run_id"] or "unknown"
        print(
            f"Google Ops Board closeout already completed for {state['target_date']} "
            f"(run_id={run_id}); skipping.",
            file=sys.stderr,
        )
    return bool(state["completed"])


def main() -> int:
    if not SCRIPT_PATH.exists():
        print(f"ERROR: missing Google Ops Board closeout script: {SCRIPT_PATH}", file=sys.stderr)
        return 78
    if not DB_CHECK_PATH.exists():
        print(f"ERROR: missing DB preflight script: {DB_CHECK_PATH}", file=sys.stderr)
        return 78

    env = os.environ.copy()
    env.setdefault("TERM", "dumb")
    env.setdefault("PYTHONUNBUFFERED", "1")
    env.setdefault(IDENTITY_SYNC_WRITE_ENV_GATE, "1")
    os.environ.setdefault(IDENTITY_SYNC_WRITE_ENV_GATE, env[IDENTITY_SYNC_WRITE_ENV_GATE])

    contract = load_ops_board_contract(DEFAULT_CONTRACT_PATH)
    service_account_json = str(resolve_service_account_json(contract=contract)).strip()
    if not service_account_json or not Path(service_account_json).exists():
        print("ERROR: AB_GOOGLE_SERVICE_ACCOUNT_JSON is missing or does not exist.", file=sys.stderr)
        return 78
    spreadsheet_id_override = resolve_spreadsheet_id(
        str(env.get("AB_GOOGLE_OPS_BOARD_SPREADSHEET_ID") or "").strip() or None,
        contract=contract,
    )

    try:
        if _closeout_already_completed(
            service_account_json=service_account_json,
            spreadsheet_id_override=spreadsheet_id_override,
        ):
            return 0
    except Exception as exc:
        print(f"WARNING: unable to inspect Run_Control before closeout: {exc}", file=sys.stderr)

    try:
        with GoogleOpsBoardAutomationLock():
            check_cmd = [
                sys.executable,
                str(DB_CHECK_PATH),
                "--db-path",
                str(PROJECT_ROOT / "db" / "app.db"),
            ]
            check = subprocess.run(check_cmd, cwd=str(PROJECT_ROOT), env=env)
            if check.returncode != 0:
                print("ERROR: local DB preflight failed; skipping Google Ops Board closeout.", file=sys.stderr)
                return int(check.returncode)

            cmd = [sys.executable, str(SCRIPT_PATH), "--apply", "--resume"]
            if spreadsheet_id_override:
                cmd.extend(["--spreadsheet-id", spreadsheet_id_override])
            cmd.extend(["--service-account-json", service_account_json])
            result = subprocess.run(cmd, cwd=str(PROJECT_ROOT), env=env)
            return int(result.returncode)
    except RuntimeError as exc:
        print(str(exc), file=sys.stderr)
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
