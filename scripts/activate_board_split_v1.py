#!/usr/bin/env python3
"""Prepare or apply the exact Google Ops Board split-v1 header activation.

Dry-run is the default. Live mutation additionally requires ``--apply`` and
``ENABLE_BOARD_SPLIT_V1_ACTIVATION=1``. The shared Google Ops Board automation
lock serializes this operation against both publish and closeout owners.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.integrations.google_ops_board import (  # noqa: E402
    DEFAULT_CONTRACT_PATH,
    GoogleOpsBoardClient,
    OWNERSHIP_MODE_LEGACY_V3,
    OWNERSHIP_MODE_SPLIT_V1,
    REQUIRED_SPLIT_COLUMNS,
    contract_for_ownership_mode,
    detect_board_ownership_layout,
    load_ops_board_contract,
    resolve_service_account_json,
    resolve_spreadsheet_id,
    validate_ownership_contract,
)
from scripts.google_ops_board_automation_common import (  # noqa: E402
    DEFAULT_CLOSEOUT_LOCK_PATH,
    GoogleOpsBoardAutomationLock,
)


ACTIVATION_ENV_GATE = "ENABLE_BOARD_SPLIT_V1_ACTIVATION"
RUNTIME_VALIDATOR_PATH = PROJECT_ROOT / "scripts" / "validate_daily_shipping_runtime.py"
ACTIVATION_TABS = tuple(REQUIRED_SPLIT_COLUMNS)
ROLLBACK_SUMMARY = (
    "Under a separate owner-authorized Board-write lane, pause/serialize Board "
    "writers, snapshot and read back the headers, then delete only the trailing "
    "SalesRaw_Today AUTO_SIZE_SUGGESTION column and the four trailing Run_Control "
    "auto-ownership columns. Their complete absence restores legacy_v3 detection."
)


RuntimeValidator = Callable[[], dict[str, Any]]


def _column_letter(column_number: int) -> str:
    letters = ""
    value = int(column_number)
    while value:
        value, remainder = divmod(value - 1, 26)
        letters = chr(65 + remainder) + letters
    return letters


def _normalize_header_row(values: list[Any] | None) -> list[str]:
    headers = [str(value or "").strip() for value in (values or [])]
    while headers and not headers[-1]:
        headers.pop()
    return headers


def _run_runtime_validator() -> dict[str, Any]:
    command = [sys.executable, str(RUNTIME_VALIDATOR_PATH), "--json"]
    completed = subprocess.run(
        command,
        cwd=str(PROJECT_ROOT),
        capture_output=True,
        text=True,
        check=False,
    )
    try:
        payload = json.loads(completed.stdout)
    except (TypeError, json.JSONDecodeError):
        payload = {
            "ok": False,
            "gate": "RED",
            "errors": ["validate_daily_shipping_runtime.py did not emit valid JSON"],
            "warnings": [],
        }
    if not isinstance(payload, dict):
        payload = {
            "ok": False,
            "gate": "RED",
            "errors": ["validate_daily_shipping_runtime.py JSON must be an object"],
            "warnings": [],
        }
    report = dict(payload)
    report["returncode"] = int(completed.returncode)
    report["command"] = command
    if completed.stderr.strip():
        report["stderr"] = completed.stderr.strip()
    return report


def _rollback_report(contract) -> dict[str, Any]:
    legacy = contract_for_ownership_mode(contract, OWNERSHIP_MODE_LEGACY_V3)
    header_rows = {
        tab_name: list(legacy.tabs[tab_name].headers)
        for tab_name in ACTIVATION_TABS
    }
    layout = detect_board_ownership_layout(header_rows)
    return {
        "summary": ROLLBACK_SUMMARY,
        "separate_owner_authorization_required": True,
        "delete_only_trailing_columns": {
            "SalesRaw_Today": ["AUTO_SIZE_SUGGESTION"],
            "Run_Control": [
                "employee_ready_observed_at",
                "auto_ready_for_closeout",
                "auto_ready_set_by",
                "auto_ready_set_at",
            ],
        },
        "resulting_ownership_mode": layout["ownership_mode"],
        "absence_semantics_proven": bool(
            layout["ok"]
            and layout["ownership_mode"] == OWNERSHIP_MODE_LEGACY_V3
            and layout["present_appended_column_count"] == 0
        ),
    }


def _base_report(*, apply: bool, lock_path: Path, contract) -> dict[str, Any]:
    return {
        "ok": False,
        "mode": "apply" if apply else "dry_run",
        "apply_requested": bool(apply),
        "write_attempted": False,
        "write_applied": False,
        "required_env_gate": ACTIVATION_ENV_GATE,
        "lock_path": str(Path(lock_path)),
        "required_appended_columns": {
            tab_name: list(columns)
            for tab_name, columns in REQUIRED_SPLIT_COLUMNS.items()
        },
        "rollback": _rollback_report(contract),
    }


def _existing_v4_columns(header_rows: dict[str, list[Any]]) -> dict[str, list[str]]:
    existing: dict[str, list[str]] = {}
    for tab_name, required_columns in REQUIRED_SPLIT_COLUMNS.items():
        observed = _normalize_header_row(header_rows.get(tab_name))
        existing[tab_name] = [
            column for column in required_columns if column in observed
        ]
    return existing


def _plan_header_updates(contract, header_rows: dict[str, list[Any]]) -> list[dict[str, Any]]:
    updates: list[dict[str, Any]] = []
    legacy = contract_for_ownership_mode(contract, OWNERSHIP_MODE_LEGACY_V3)
    for tab_name, appended_columns in REQUIRED_SPLIT_COLUMNS.items():
        observed = _normalize_header_row(header_rows.get(tab_name))
        expected_legacy = list(legacy.tabs[tab_name].headers)
        if observed != expected_legacy:
            raise ValueError(
                f"{tab_name} is not the exact legacy_v3 trailing-header source"
            )
        for column_number, column in enumerate(
            appended_columns,
            start=len(observed) + 1,
        ):
            updates.append(
                {
                    "range": f"{tab_name}!{_column_letter(column_number)}1",
                    "value": column,
                    "field": column,
                }
            )
    return updates


def _runtime_is_green(report: dict[str, Any]) -> bool:
    return bool(
        report.get("ok") is True
        and str(report.get("gate") or "") == "GREEN"
        and int(report.get("returncode") or 0) == 0
    )


def _activate_while_locked(
    *,
    client,
    contract,
    apply: bool,
    report: dict[str, Any],
) -> dict[str, Any]:
    header_rows = client.get_header_rows(list(ACTIVATION_TABS))
    layout_before = detect_board_ownership_layout(header_rows)
    existing_columns = _existing_v4_columns(header_rows)
    report.update(
        {
            "ownership_layout_before": layout_before,
            "existing_v4_columns": existing_columns,
        }
    )

    if any(existing_columns.values()):
        report.update(
            {
                "failure_stage": "existing_v4_columns",
                "error": (
                    "Activation refused: at least one v4 header already exists; "
                    "a partial layout is an abort and a complete layout is not re-applied."
                ),
            }
        )
        return report

    try:
        updates = _plan_header_updates(contract, header_rows)
    except ValueError as exc:
        report.update(
            {
                "failure_stage": "legacy_header_source",
                "error": str(exc),
            }
        )
        return report

    if len(updates) != 5:
        report.update(
            {
                "failure_stage": "activation_plan",
                "error": f"Activation plan must contain exactly five updates, got {len(updates)}",
                "planned_header_updates": updates,
            }
        )
        return report

    planned_headers = {
        tab_name: list(contract.tabs[tab_name].headers)
        for tab_name in ACTIVATION_TABS
    }
    planned_layout = detect_board_ownership_layout(planned_headers)
    report.update(
        {
            "planned_header_updates": updates,
            "planned_ownership_layout_after": planned_layout,
        }
    )
    if planned_layout["ownership_mode"] != OWNERSHIP_MODE_SPLIT_V1:
        report.update(
            {
                "failure_stage": "planned_layout_detection",
                "error": "Planned headers do not detect as complete split_v1",
            }
        )
        return report

    if not apply:
        report["ok"] = True
        return report

    report["write_attempted"] = True
    client.update_cells(updates)
    report["write_applied"] = True
    header_rows_after = client.get_header_rows(list(ACTIVATION_TABS))
    layout_after = detect_board_ownership_layout(header_rows_after)
    exact_readback = all(
        _normalize_header_row(header_rows_after.get(tab_name))
        == list(contract.tabs[tab_name].headers)
        for tab_name in ACTIVATION_TABS
    )
    report.update(
        {
            "header_readback_exact": exact_readback,
            "ownership_layout_after": layout_after,
        }
    )
    if not exact_readback:
        report.update(
            {
                "failure_stage": "header_readback",
                "error": "Post-append live header readback does not exactly match contract v4",
            }
        )
        return report
    if not (
        layout_after.get("ok") is True
        and layout_after.get("ownership_mode") == OWNERSHIP_MODE_SPLIT_V1
        and int(layout_after.get("present_appended_column_count") or 0) == 5
    ):
        report.update(
            {
                "failure_stage": "layout_detection_after",
                "error": "Post-append layout detection is not complete split_v1",
            }
        )
        return report

    report["ok"] = True
    return report


def execute_activation(
    *,
    client,
    contract,
    apply: bool = False,
    environ: Mapping[str, str] | None = None,
    lock_path: Path = DEFAULT_CLOSEOUT_LOCK_PATH,
    runtime_validator: RuntimeValidator = _run_runtime_validator,
) -> dict[str, Any]:
    """Execute one serialized activation attempt and return a JSON-safe report."""
    environment = os.environ if environ is None else environ
    report = _base_report(apply=apply, lock_path=Path(lock_path), contract=contract)

    if apply and str(environment.get(ACTIVATION_ENV_GATE) or "").strip() != "1":
        report.update(
            {
                "failure_stage": "apply_gate",
                "error": (
                    f"--apply requires {ACTIVATION_ENV_GATE}=1; no Board read or write performed"
                ),
            }
        )
        return report

    contract_errors = validate_ownership_contract(contract)
    if contract_errors:
        report.update(
            {
                "failure_stage": "ownership_contract",
                "error": "Configured Board ownership contract is not valid v4",
                "contract_errors": contract_errors,
            }
        )
        return report

    runtime_report = runtime_validator()
    report["runtime_validation"] = runtime_report
    if not _runtime_is_green(runtime_report):
        report.update(
            {
                "failure_stage": "daily_shipping_runtime",
                "error": "validate_daily_shipping_runtime.py is not GREEN; no Board read or write performed",
            }
        )
        return report

    try:
        with GoogleOpsBoardAutomationLock(Path(lock_path)):
            try:
                return _activate_while_locked(
                    client=client,
                    contract=contract,
                    apply=apply,
                    report=report,
                )
            except Exception as exc:
                report.update(
                    {
                        "failure_stage": "board_activation",
                        "error": str(exc),
                    }
                )
                return report
    except RuntimeError as exc:
        report.update(
            {
                "failure_stage": "automation_lock",
                "error": (
                    "Activation refused because the shared closeout/publish lock "
                    f"is held: {exc}"
                ),
            }
        )
        return report


def _print_report(report: dict[str, Any]) -> None:
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Activate the exact five Google Ops Board split-v1 trailing headers.",
        epilog=(
            "Dry-run is the default. Rollback is not automated: "
            + ROLLBACK_SUMMARY
        ),
    )
    parser.add_argument(
        "--contract",
        type=Path,
        default=DEFAULT_CONTRACT_PATH,
        help="Google Ops Board v4 contract path",
    )
    parser.add_argument(
        "--service-account-json",
        type=Path,
        default=None,
        help="Path to the Google service-account JSON",
    )
    parser.add_argument(
        "--spreadsheet-id",
        type=str,
        default=None,
        help="Override the configured spreadsheet ID",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help=f"Append the five headers; requires {ACTIVATION_ENV_GATE}=1",
    )
    args = parser.parse_args(argv)

    try:
        contract = load_ops_board_contract(args.contract)
    except Exception as exc:
        report = {
            "ok": False,
            "mode": "apply" if args.apply else "dry_run",
            "apply_requested": bool(args.apply),
            "write_attempted": False,
            "write_applied": False,
            "failure_stage": "load_contract",
            "error": str(exc),
        }
        _print_report(report)
        return 1

    if args.apply and str(os.environ.get(ACTIVATION_ENV_GATE) or "").strip() != "1":
        report = _base_report(
            apply=True,
            lock_path=DEFAULT_CLOSEOUT_LOCK_PATH,
            contract=contract,
        )
        report.update(
            {
                "failure_stage": "apply_gate",
                "error": f"--apply requires {ACTIVATION_ENV_GATE}=1; no Board read or write performed",
            }
        )
        _print_report(report)
        return 1

    try:
        service_account_json = resolve_service_account_json(
            args.service_account_json,
            contract=contract,
        )
        spreadsheet_id = resolve_spreadsheet_id(
            args.spreadsheet_id,
            contract=contract,
        )
        client = GoogleOpsBoardClient.from_service_account_file(
            spreadsheet_id,
            service_account_json,
        )
    except Exception as exc:
        report = _base_report(
            apply=args.apply,
            lock_path=DEFAULT_CLOSEOUT_LOCK_PATH,
            contract=contract,
        )
        report.update(
            {
                "failure_stage": "google_client",
                "error": str(exc),
            }
        )
        _print_report(report)
        return 1

    report = execute_activation(
        client=client,
        contract=contract,
        apply=args.apply,
    )
    _print_report(report)
    return 0 if report.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
