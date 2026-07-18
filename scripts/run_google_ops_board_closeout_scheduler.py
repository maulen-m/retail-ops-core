#!/usr/bin/env python3
"""LaunchAgent entrypoint for the 18:30 Google Ops Board closeout run."""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from datetime import date
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.integrations.google_ops_board import (  # noqa: E402
    DEFAULT_CONTRACT_PATH,
    GoogleOpsBoardClient,
    OWNERSHIP_MODE_PARTIAL,
    OWNERSHIP_MODE_SPLIT_V1,
    detect_board_ownership_layout,
    extract_rows_from_matrix,
    load_ops_board_contract,
    resolve_effective_board_state,
    resolve_service_account_json,
    resolve_spreadsheet_id,
)
from scripts.google_ops_board_automation_common import (  # noqa: E402
    AUTOMATION_LOCK_HELD_ENV,
    GoogleOpsBoardAutomationLock,
    closeout_completion_state,
    ensure_kaspi_api_call_ledger_env,
    evaluate_closeout_halt_barrier,
    record_lock_contention,
    reset_lock_contention,
    run_guarded,
    today_almaty,
)
SCRIPT_PATH = PROJECT_ROOT / "scripts" / "run_google_ops_board_closeout.py"
DB_CHECK_PATH = PROJECT_ROOT / "scripts" / "check_local_app_db.py"
IDENTITY_SYNC_WRITE_ENV_GATE = "ENABLE_KASPI_WORKBOOK_MAP_SYNC"
_LAST_CLOSEOUT_STATE: dict[str, object] = {}


def _clean(value: object) -> str:
    return str(value or "").strip()


def _current_ready_identity(
    *,
    service_account_json: str,
    spreadsheet_id_override: str | None,
    target_date,
) -> dict[str, str]:
    contract = load_ops_board_contract(DEFAULT_CONTRACT_PATH)
    spreadsheet_id = resolve_spreadsheet_id(spreadsheet_id_override, contract=contract)
    client = GoogleOpsBoardClient.from_service_account_file(
        spreadsheet_id,
        Path(service_account_json),
    )
    run_matrix = client.get_tab_values("Run_Control")
    sales_matrix = client.get_tab_values("SalesRaw_Today")
    layout = detect_board_ownership_layout(
        {
            "Run_Control": list(run_matrix[0]) if run_matrix else [],
            "SalesRaw_Today": list(sales_matrix[0]) if sales_matrix else [],
        }
    )
    rows = extract_rows_from_matrix(
        contract.tabs["Run_Control"].headers,
        run_matrix,
    )
    row = next(
        (
            item
            for item in rows
            if _clean(item.get("target_date")) == target_date.isoformat()
        ),
        {},
    )
    if layout["ownership_mode"] == OWNERSHIP_MODE_PARTIAL:
        return {
            "target_date": _clean(row.get("target_date")),
            "ready_source": "",
            "ready_set_at": "",
            "ready_for_closeout": "PARTIAL_LAYOUT",
        }
    if layout["ownership_mode"] == OWNERSHIP_MODE_SPLIT_V1:
        resolution = resolve_effective_board_state(
            salesraw_rows=extract_rows_from_matrix(
                contract.tabs["SalesRaw_Today"].headers, sales_matrix
            ),
            run_control_row=row,
            target_date=target_date.isoformat(),
        )
        effective = dict(resolution["effective_run_control_row"])
        return {
            "target_date": _clean(effective.get("target_date")),
            "ready_source": _clean(effective.get("ready_source")),
            "ready_set_at": _clean(effective.get("ready_set_at")),
            "ready_for_closeout": _clean(
                effective.get("ready_for_closeout")
            ).upper(),
        }
    return {
        "target_date": _clean(row.get("target_date")),
        "ready_set_at": _clean(row.get("ready_set_at")),
        "ready_for_closeout": _clean(row.get("ready_for_closeout")).upper(),
    }


def _closeout_already_completed(
    *,
    service_account_json: str,
    spreadsheet_id_override: str | None,
) -> bool:
    global _LAST_CLOSEOUT_STATE
    contract = load_ops_board_contract(DEFAULT_CONTRACT_PATH)
    spreadsheet_id = resolve_spreadsheet_id(spreadsheet_id_override, contract=contract)
    client = GoogleOpsBoardClient.from_service_account_file(spreadsheet_id, Path(service_account_json))
    state = closeout_completion_state(client=client, contract=contract, target_date=today_almaty())
    _LAST_CLOSEOUT_STATE = dict(state)
    if state["completed"]:
        run_id = state["run_id"] or "unknown"
        print(
            f"Google Ops Board closeout already completed for {state['target_date']} "
            f"(run_id={run_id}); skipping.",
            file=sys.stderr,
        )
    elif state["status"] == "OK":
        print(
            "Google Ops Board closeout has OK Run_Control status but delivery is incomplete "
            f"(delivery_status={state.get('delivery_status')}, "
            f"confirmed={state.get('delivery_confirmed_count')}/{state.get('delivery_manifest_count')}); resuming.",
            file=sys.stderr,
        )
    return bool(state["completed"])


def main(argv: list[str] | None = None) -> int:
    global _LAST_CLOSEOUT_STATE
    _LAST_CLOSEOUT_STATE = {}
    parser = argparse.ArgumentParser(description="Identity-bound Google Ops Board closeout launcher")
    parser.add_argument("--expected-target-date", default="")
    parser.add_argument("--expected-ready-source", default="")
    parser.add_argument("--expected-ready-set-at", default="")
    args = parser.parse_args(argv)

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
    env.setdefault(AUTOMATION_LOCK_HELD_ENV, "1")
    target_date = today_almaty()
    if _clean(args.expected_target_date):
        try:
            target_date = date.fromisoformat(_clean(args.expected_target_date))
        except ValueError:
            print("ERROR: invalid --expected-target-date", file=sys.stderr)
            return 78
    if target_date != today_almaty():
        print("ERROR: closeout scheduler refuses a non-today target date", file=sys.stderr)
        return 78
    expected_ready_set_at = _clean(args.expected_ready_set_at)
    expected_ready_source = _clean(args.expected_ready_source)

    ensure_kaspi_api_call_ledger_env(env, target_date=target_date, project_root=PROJECT_ROOT)
    os.environ.setdefault(IDENTITY_SYNC_WRITE_ENV_GATE, env[IDENTITY_SYNC_WRITE_ENV_GATE])
    if env.get("KASPI_API_CALL_LEDGER_PATH"):
        os.environ.setdefault("KASPI_API_CALL_LEDGER_PATH", env["KASPI_API_CALL_LEDGER_PATH"])

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
        print(f"ERROR: unable to inspect Run_Control before closeout: {exc}", file=sys.stderr)
        return 78

    if not expected_ready_set_at:
        state = dict(_LAST_CLOSEOUT_STATE)
        delivery_state = dict(state.get("delivery_state") or {})
        request_identity = dict(state.get("request_identity") or {})
        delivery_status = _clean(delivery_state.get("status")).upper()
        if (
            _clean(state.get("status")).upper() == "OK"
            and _clean(delivery_state.get("manifest_path"))
            and bool(state.get("delivery_resume_safe", True))
            and not delivery_status.startswith(("CHECKPOINT_", "PINNED_"))
            and _clean(request_identity.get("target_date")) == target_date.isoformat()
            and _clean(request_identity.get("ready_set_at"))
        ):
            expected_ready_set_at = _clean(request_identity.get("ready_set_at"))
            expected_ready_source = _clean(request_identity.get("ready_source"))
            print(
                "Google Ops Board closeout scheduler: resuming checkpoint-pinned "
                "incomplete delivery.",
                file=sys.stderr,
            )
        else:
            print(
                "Google Ops Board closeout scheduler: fresh execution is owned by the "
                "60-second READY watcher; no identity-bound request was supplied.",
                file=sys.stderr,
            )
            return 0

    lock_acquired = False
    try:
        with GoogleOpsBoardAutomationLock():
            lock_acquired = True
            try:
                reset_lock_contention("run_google_ops_board_closeout_scheduler")
            except Exception as exc:
                print(f"WARNING: unable to reset lock-contention counter: {exc}", file=sys.stderr)
            current_identity = _current_ready_identity(
                service_account_json=service_account_json,
                spreadsheet_id_override=spreadsheet_id_override,
                target_date=target_date,
            )
            halt_gate = evaluate_closeout_halt_barrier(
                target_date=target_date,
                run_control_row=current_identity,
                request_ready_set_at=expected_ready_set_at,
                request_ready_source=expected_ready_source,
            )
            if halt_gate["blocked"]:
                print(
                    "Google Ops Board closeout scheduler: local halt barrier blocks "
                    f"launch ({halt_gate['reason']}).",
                    file=sys.stderr,
                )
                return 0
            expected_identity = {
                "target_date": target_date.isoformat(),
                "ready_set_at": expected_ready_set_at,
                "ready_for_closeout": "READY",
            }
            if "ready_source" in current_identity:
                expected_identity = {
                    "target_date": target_date.isoformat(),
                    "ready_source": expected_ready_source,
                    "ready_set_at": expected_ready_set_at,
                    "ready_for_closeout": "READY",
                }
                if not expected_ready_source:
                    print(
                        "ERROR: split-v1 scheduler launch requires --expected-ready-source",
                        file=sys.stderr,
                    )
                    return 78
            if current_identity != expected_identity:
                print(
                    f"ERROR: READY identity changed before scheduler launch: {current_identity}",
                    file=sys.stderr,
                )
                return 78
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

            cmd = [
                sys.executable,
                str(SCRIPT_PATH),
                "--apply",
                "--resume",
                "--target-date",
                target_date.isoformat(),
                "--expected-ready-set-at",
                expected_ready_set_at,
            ]
            if expected_ready_source:
                cmd.extend(["--expected-ready-source", expected_ready_source])
            if spreadsheet_id_override:
                cmd.extend(["--spreadsheet-id", spreadsheet_id_override])
            cmd.extend(["--service-account-json", service_account_json])
            result = subprocess.run(cmd, cwd=str(PROJECT_ROOT), env=env)
            return int(result.returncode)
    except RuntimeError as exc:
        print(str(exc), file=sys.stderr)
        if not lock_acquired:
            try:
                record_lock_contention("run_google_ops_board_closeout_scheduler")
            except Exception as counter_exc:
                print(f"WARNING: unable to record lock contention: {counter_exc}", file=sys.stderr)
        return 0


if __name__ == "__main__":
    raise SystemExit(run_guarded("run_google_ops_board_closeout_scheduler", main))
