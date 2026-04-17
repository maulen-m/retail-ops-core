#!/usr/bin/env python3
"""Minute-level watcher that triggers closeout early once the board is truly ready."""

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
    DEFAULT_READY_DEBOUNCE_STATE_PATH,
    READY_DEBOUNCE_SECONDS,
    clear_ready_debounce_state,
    closeout_completion_state,
    evaluate_ready_debounce,
    load_ready_debounce_state,
    now_almaty,
    save_ready_debounce_state,
    today_almaty,
    within_early_closeout_watch_window,
)
from scripts.run_google_ops_board_closeout import build_readiness_report  # noqa: E402
SCRIPT_PATH = PROJECT_ROOT / "scripts" / "run_google_ops_board_closeout_scheduler.py"
DB_PATH = PROJECT_ROOT / "db" / "app.db"
READY_DEBOUNCE_STATE_PATH = DEFAULT_READY_DEBOUNCE_STATE_PATH
IDENTITY_SYNC_WRITE_ENV_GATE = "ENABLE_KASPI_WORKBOOK_MAP_SYNC"


def _in_watch_window() -> bool:
    return within_early_closeout_watch_window(now_almaty())


def main() -> int:
    if not SCRIPT_PATH.exists():
        print(f"ERROR: missing closeout scheduler script: {SCRIPT_PATH}", file=sys.stderr)
        return 78

    if not _in_watch_window():
        print("Google Ops Board early-closeout watch: outside watch window; skipping.")
        return 0

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

    spreadsheet_id = resolve_spreadsheet_id(
        str(env.get("AB_GOOGLE_OPS_BOARD_SPREADSHEET_ID") or "").strip() or None,
        contract=contract,
    )
    client = GoogleOpsBoardClient.from_service_account_file(spreadsheet_id, Path(service_account_json))
    target_date = today_almaty()

    completion = closeout_completion_state(client=client, contract=contract, target_date=target_date)
    if completion["completed"]:
        clear_ready_debounce_state(READY_DEBOUNCE_STATE_PATH)
        run_id = completion["run_id"] or "unknown"
        print(
            f"Google Ops Board early-closeout watch: closeout already completed for {completion['target_date']} "
            f"(run_id={run_id}); skipping.",
        )
        return 0

    readiness = build_readiness_report(
        client=client,
        contract=contract,
        db_path=DB_PATH,
        target_date=target_date,
        lookback_days=5,
    )
    if not readiness["ready"]:
        clear_ready_debounce_state(READY_DEBOUNCE_STATE_PATH)
        print(
            "Google Ops Board early-closeout watch: not ready yet "
            f"(ready_toggle={readiness['run_control_ready_ok']}, "
            f"blank_sizes={readiness['blank_size_count']}, "
            f"invalid_sizes={readiness['invalid_size_count']})."
        )
        return 0

    debounce = evaluate_ready_debounce(
        state=load_ready_debounce_state(READY_DEBOUNCE_STATE_PATH),
        target_date=target_date,
        now=now_almaty(),
        ready=True,
        debounce_seconds=READY_DEBOUNCE_SECONDS,
    )
    action = str(debounce["action"])
    if action == "arm":
        save_ready_debounce_state(debounce["state"], READY_DEBOUNCE_STATE_PATH)
        print(
            "Google Ops Board early-closeout watch: READY detected; "
            f"arming {READY_DEBOUNCE_SECONDS}s debounce."
        )
        return 0
    if action == "wait":
        save_ready_debounce_state(debounce["state"], READY_DEBOUNCE_STATE_PATH)
        print(
            "Google Ops Board early-closeout watch: READY still stable, "
            f"waiting {debounce['remaining_seconds']}s more before closeout."
        )
        return 0

    print("Google Ops Board early-closeout watch: board is READY; triggering closeout immediately.")
    result = subprocess.run([sys.executable, str(SCRIPT_PATH), "--resume"], cwd=str(PROJECT_ROOT), env=env)
    clear_ready_debounce_state(READY_DEBOUNCE_STATE_PATH)
    return int(result.returncode)


if __name__ == "__main__":
    raise SystemExit(main())
