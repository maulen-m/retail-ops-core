#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo


PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.integrations.google_ops_board import (  # noqa: E402
    DEFAULT_CONTRACT_PATH,
    GoogleOpsBoardClient,
    dump_json,
    extract_rows_from_matrix,
    extract_rows_with_positions_from_matrix,
    load_ops_board_contract,
    resolve_service_account_json,
    resolve_spreadsheet_id,
)
from core.integrations.kaspi_api_client import (  # noqa: E402
    KaspiAPIClient,
    KaspiAuthError,
    STORE_TOKEN_MAP,
)
from core.paths import data_path  # noqa: E402
from scripts.sync_google_ops_board_sizes_to_db import (  # noqa: E402
    _load_db_rows as load_db_rows_for_writeback,
    plan_size_writeback,
)


ALMATY_TZ = ZoneInfo("Asia/Almaty")
DEFAULT_RUN_ROOT = data_path("exports", "google_ops_board", "workflow_runs")
DEFAULT_TODAY_FOLDER = data_path("excel_ui", "Kaspi_orders", "Today")
STORE_NAME_TO_API_CODE = {
    "AcmeWear": "ACMEWEAR",
    "Universal": "UNIVERSAL",
    "11KZ": "11KZ",
    "STORE-B": "STOREB",
    "Store-C": "MELVIS",
}


def _require_apply_gate(apply: bool, env_name: str) -> None:
    if apply and str(os.environ.get(env_name) or "").strip() != "1":
        raise RuntimeError(f"{env_name}=1 is required with --apply")


def _resolve_target_date(value: str) -> date:
    text = str(value or "").strip().lower()
    today = datetime.now(ALMATY_TZ).date()
    if text in ("", "today"):
        return today
    if text == "tomorrow":
        return today + timedelta(days=1)
    return date.fromisoformat(text)


def _clean(value: Any) -> str:
    text = str(value or "").strip()
    if text.endswith(".0") and text[:-2].isdigit():
        return text[:-2]
    return text


def _build_run_id(target_date: date) -> str:
    stamp = datetime.now(ALMATY_TZ).strftime("%Y%m%d_%H%M%S")
    return f"{stamp}_{target_date.isoformat()}_closeout"


def _select_run_control_row(rows: list[dict[str, Any]], target_date: date) -> dict[str, Any] | None:
    target_iso = target_date.isoformat()
    for row in rows:
        if _clean(row.get("target_date")) == target_iso:
            return row
    return rows[0] if rows else None


def _update_run_control_status(
    *,
    client: GoogleOpsBoardClient,
    contract,
    target_date: date,
    run_id: str,
    status: str,
) -> None:
    headers = contract.tabs["Run_Control"].headers
    matrix = client.get_tab_values("Run_Control")
    rows_with_positions = extract_rows_with_positions_from_matrix(headers, matrix)
    target_iso = target_date.isoformat()
    selected = None
    for row_info in rows_with_positions:
        if _clean(row_info["row"].get("target_date")) == target_iso:
            selected = row_info
            break
    if selected is None and rows_with_positions:
        selected = rows_with_positions[0]
    if selected is None:
        return
    updated = dict(selected["row"])
    if str(status or "").strip().upper().startswith("FAILED_"):
        updated["ready_for_closeout"] = "HOLD"
    updated["last_verified_ready_at"] = datetime.now(ALMATY_TZ).isoformat()
    updated["last_orchestrator_run_id"] = run_id
    updated["last_orchestrator_status"] = status
    client.update_tab_rows(
        "Run_Control",
        headers,
        [{"sheet_row": int(selected["sheet_row"]), "row": updated}],
    )


def build_readiness_report(
    *,
    client: GoogleOpsBoardClient,
    contract,
    db_path: Path,
    target_date: date,
    lookback_days: int,
) -> dict[str, Any]:
    run_control_headers = contract.tabs["Run_Control"].headers
    salesraw_headers = contract.tabs["SalesRaw_Today"].headers

    run_control_matrix = client.get_tab_values("Run_Control")
    salesraw_matrix = client.get_tab_values("SalesRaw_Today")
    run_control_rows = extract_rows_from_matrix(run_control_headers, run_control_matrix)
    salesraw_rows = extract_rows_from_matrix(salesraw_headers, salesraw_matrix)
    run_control_row = _select_run_control_row(run_control_rows, target_date)

    blank_size_rows: list[dict[str, Any]] = []
    for row in salesraw_rows:
        if _clean(row.get("MY_SIZE")):
            continue
        blank_size_rows.append(
            {
                "_db_row_id": _clean(row.get("_db_row_id")),
                "OrderID": _clean(row.get("OrderID")),
                "Status": _clean(row.get("Status")),
                "Date": _clean(row.get("Date")),
                "STORE_NAME": _clean(row.get("STORE_NAME")),
            }
        )

    start_date = target_date - timedelta(days=max(lookback_days - 1, 0))
    db_rows = load_db_rows_for_writeback(db_path, start_date, target_date)
    writeback_plan = plan_size_writeback(
        salesraw_rows,
        db_rows,
        key_column=contract.writeback["size_assignments"]["key_column"],
        source_column=contract.writeback["size_assignments"]["source_column"],
    )

    target_match = bool(run_control_row) and _clean(run_control_row.get("target_date")) == target_date.isoformat()
    ready_value = _clean((run_control_row or {}).get("ready_for_closeout")).upper()
    ready_toggle_ok = ready_value == "READY"
    no_blank_sizes = len(blank_size_rows) == 0
    no_invalid_sizes = len(writeback_plan["invalid_rows"]) == 0

    return {
        "target_date": target_date.isoformat(),
        "run_control_row": run_control_row or {},
        "run_control_target_match": target_match,
        "run_control_ready_value": ready_value,
        "run_control_ready_ok": ready_toggle_ok,
        "salesraw_row_count": len(salesraw_rows),
        "blank_size_rows": blank_size_rows,
        "blank_size_count": len(blank_size_rows),
        "invalid_size_rows": writeback_plan["invalid_rows"],
        "invalid_size_count": len(writeback_plan["invalid_rows"]),
        "pending_db_writeback_updates": writeback_plan["updates"],
        "pending_db_writeback_count": len(writeback_plan["updates"]),
        "ready": bool(target_match and ready_toggle_ok and no_blank_sizes and no_invalid_sizes),
    }


def build_store_context_report(*, salesraw_rows: list[dict[str, Any]]) -> dict[str, Any]:
    active_store_codes: list[str] = []
    seen: set[str] = set()
    for row in salesraw_rows:
        store_name = _clean(row.get("STORE_NAME"))
        api_code = STORE_NAME_TO_API_CODE.get(store_name, store_name.upper())
        if not api_code or api_code in seen:
            continue
        seen.add(api_code)
        active_store_codes.append(api_code)

    store_reports: list[dict[str, Any]] = []
    failures: list[dict[str, Any]] = []
    for store_code in active_store_codes:
        token_env = STORE_TOKEN_MAP.get(store_code)
        try:
            client = KaspiAPIClient(store_code=store_code)
            merchant_uid = _clean(getattr(client, "_merchant_uid", ""))
            ok = bool(merchant_uid)
            store_report = {
                "store_code": store_code,
                "token_env": token_env or "",
                "merchant_uid": merchant_uid,
                "ok": ok,
                "error": "" if ok else "merchant UID missing",
            }
        except KaspiAuthError as exc:
            store_report = {
                "store_code": store_code,
                "token_env": token_env or "",
                "merchant_uid": "",
                "ok": False,
                "error": str(exc),
            }
        except Exception as exc:
            store_report = {
                "store_code": store_code,
                "token_env": token_env or "",
                "merchant_uid": "",
                "ok": False,
                "error": str(exc),
            }
        store_reports.append(store_report)
        if not store_report["ok"]:
            failures.append(store_report)

    return {
        "ok": len(failures) == 0,
        "active_store_codes": active_store_codes,
        "stores": store_reports,
        "failure_count": len(failures),
        "failures": failures,
    }


def _run_command(
    *,
    name: str,
    command: list[str],
    env: dict[str, str],
    report_path: Path,
) -> dict[str, Any]:
    started_at = datetime.now(ALMATY_TZ).isoformat()
    proc = subprocess.run(
        command,
        cwd=str(PROJECT_ROOT),
        env=env,
        text=True,
        capture_output=True,
    )
    finished_at = datetime.now(ALMATY_TZ).isoformat()
    report = {
        "name": name,
        "command": command,
        "returncode": int(proc.returncode),
        "stdout": proc.stdout,
        "stderr": proc.stderr,
        "started_at": started_at,
        "finished_at": finished_at,
        "ok": proc.returncode == 0,
    }
    dump_json(report_path, report)
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run fail-closed Google Ops Board daily closeout.")
    parser.add_argument("--contract", type=Path, default=DEFAULT_CONTRACT_PATH, help="Contract YAML path")
    parser.add_argument("--db-path", type=Path, default=None, help="Optional DB path (default: db/app.db)")
    parser.add_argument("--service-account-json", type=Path, default=None, help="Path to service-account JSON")
    parser.add_argument("--spreadsheet-id", type=str, default=None, help="Override spreadsheet ID")
    parser.add_argument("--target-date", type=str, default="today", help="Target date (default: today)")
    parser.add_argument("--lookback-days", type=int, default=5, help="Operational lookback window (default: 5)")
    parser.add_argument("--today-folder", type=Path, default=DEFAULT_TODAY_FOLDER, help="Today folder for send step")
    parser.add_argument("--run-root", type=Path, default=DEFAULT_RUN_ROOT, help="Workflow run output root")
    parser.add_argument("--apply", action="store_true", help="Run live closeout (default: dry-run)")
    parser.add_argument("--json-out", type=Path, default=None, help="Optional top-level JSON report path")
    args = parser.parse_args(argv)

    contract = load_ops_board_contract(args.contract)
    _require_apply_gate(args.apply, contract.closeout_write_env_gate)

    target_date = _resolve_target_date(args.target_date)
    db_path = Path(args.db_path).expanduser() if args.db_path else data_path("db", "app.db")
    service_account_json = resolve_service_account_json(args.service_account_json, contract=contract)
    spreadsheet_id = resolve_spreadsheet_id(args.spreadsheet_id, contract=contract)
    client = GoogleOpsBoardClient.from_service_account_file(spreadsheet_id, service_account_json)

    run_id = _build_run_id(target_date)
    run_dir = Path(args.run_root).expanduser() / target_date.isoformat() / run_id
    run_dir.mkdir(parents=True, exist_ok=True)

    env = os.environ.copy()
    env.setdefault("PYTHONUNBUFFERED", "1")
    env.setdefault("TERM", "dumb")

    report: dict[str, Any] = {
        "run_id": run_id,
        "mode": "apply" if args.apply else "dry_run",
        "target_date": target_date.isoformat(),
        "db_path": str(db_path),
        "spreadsheet_id": spreadsheet_id,
        "service_account_json": str(service_account_json),
        "run_dir": str(run_dir),
        "steps": [],
        "ready": False,
        "ok": False,
    }

    run_control_matrix = client.get_tab_values("Run_Control")
    salesraw_matrix = client.get_tab_values("SalesRaw_Today")
    salesraw_rows = extract_rows_from_matrix(contract.tabs["SalesRaw_Today"].headers, salesraw_matrix)
    dump_json(
        run_dir / "run_control_snapshot.json",
        {
            "target_date": target_date.isoformat(),
            "headers": contract.tabs["Run_Control"].headers,
            "matrix": run_control_matrix,
            "rows": extract_rows_from_matrix(contract.tabs["Run_Control"].headers, run_control_matrix),
        },
    )
    dump_json(
        run_dir / "salesraw_snapshot.json",
        {
            "target_date": target_date.isoformat(),
            "headers": contract.tabs["SalesRaw_Today"].headers,
            "matrix": salesraw_matrix,
            "rows": salesraw_rows,
        },
    )

    readiness = build_readiness_report(
        client=client,
        contract=contract,
        db_path=db_path,
        target_date=target_date,
        lookback_days=args.lookback_days,
    )
    report["ready"] = bool(readiness["ready"])
    dump_json(run_dir / "readiness_report.json", readiness)

    if args.apply:
        _update_run_control_status(
            client=client,
            contract=contract,
            target_date=target_date,
            run_id=run_id,
            status="READY" if readiness["ready"] else "BLOCKED",
        )

    if not readiness["ready"]:
        report["failure_stage"] = "readiness"
        report["failure_reason"] = "Closeout gate failed"
        report["readiness_report_path"] = str(run_dir / "readiness_report.json")
        output_path = args.json_out or (run_dir / "closeout_report.json")
        dump_json(output_path, report)
        print(f"Closeout blocked. Readiness report: {run_dir / 'readiness_report.json'}")
        return 1

    selected_python = str(PROJECT_ROOT / ".venv" / "bin" / "python")
    if not Path(selected_python).exists():
        selected_python = sys.executable

    size_writeback_json = run_dir / "size_writeback_report.json"
    size_env = dict(env)
    if args.apply:
        size_env[contract.db_write_env_gate] = "1"
    size_cmd = [
        selected_python,
        str(PROJECT_ROOT / "scripts" / "sync_google_ops_board_sizes_to_db.py"),
        "--target-date",
        target_date.isoformat(),
        "--lookback-days",
        str(args.lookback_days),
        "--db",
        str(db_path),
        "--service-account-json",
        str(service_account_json),
        "--spreadsheet-id",
        spreadsheet_id,
        "--output-json",
        str(size_writeback_json),
    ]
    if args.apply:
        size_cmd.append("--apply")
    step_report = _run_command(
        name="size_writeback",
        command=size_cmd,
        env=size_env,
        report_path=run_dir / "step_size_writeback.json",
    )
    report["steps"].append(step_report)
    if step_report["returncode"] != 0:
        if args.apply:
            _update_run_control_status(
                client=client,
                contract=contract,
                target_date=target_date,
                run_id=run_id,
                status="FAILED_SIZE_WRITEBACK",
            )
        report["failure_stage"] = "size_writeback"
        report["failure_reason"] = "Final size writeback failed"
        output_path = args.json_out or (run_dir / "closeout_report.json")
        dump_json(output_path, report)
        return 1

    if size_writeback_json.exists():
        report["size_writeback_report_path"] = str(size_writeback_json)
        try:
            size_payload = json.loads(size_writeback_json.read_text(encoding="utf-8"))
        except Exception:
            size_payload = {}
        report["size_writeback_db_backup_path"] = size_payload.get("db_backup_path")
        report["size_writeback_updates_applied"] = size_payload.get("updates_applied")

    store_context = build_store_context_report(salesraw_rows=salesraw_rows)
    dump_json(run_dir / "store_context_report.json", store_context)
    report["store_context_report_path"] = str(run_dir / "store_context_report.json")
    if not store_context["ok"]:
        if args.apply:
            _update_run_control_status(
                client=client,
                contract=contract,
                target_date=target_date,
                run_id=run_id,
                status="FAILED_STORE_CONTEXT",
            )
        report["failure_stage"] = "store_context"
        report["failure_reason"] = "Store token / merchant UID context failed preflight"
        output_path = args.json_out or (run_dir / "closeout_report.json")
        dump_json(output_path, report)
        return 1

    ship_cmd = [
        selected_python,
        str(PROJECT_ROOT / "scripts" / "ship_orders_api.py"),
        "--selection-source",
        "db",
        "--db-path",
        str(db_path),
        "--date",
        target_date.isoformat(),
        "--since-days",
        str(args.lookback_days),
        "--json-out",
        str(run_dir / "shipping_report.json"),
        "--verbose",
    ]
    if not args.apply:
        ship_cmd.append("--dry-run")
    ship_step = _run_command(
        name="shipping",
        command=ship_cmd,
        env=env,
        report_path=run_dir / "step_shipping.json",
    )
    report["steps"].append(ship_step)
    if ship_step["returncode"] != 0:
        if args.apply:
            _update_run_control_status(
                client=client,
                contract=contract,
                target_date=target_date,
                run_id=run_id,
                status="FAILED_SHIPPING",
            )
        report["failure_stage"] = "shipping"
        report["failure_reason"] = "DB-first shipping failed"
        output_path = args.json_out or (run_dir / "closeout_report.json")
        dump_json(output_path, report)
        return 1

    download_cmd = [
        selected_python,
        str(PROJECT_ROOT / "scripts" / "download_waybills_api.py"),
        "--db-path",
        str(db_path),
        "--date",
        target_date.isoformat(),
        "--include-overdue",
        "--verbose",
    ]
    if not args.apply:
        download_cmd.append("--dry-run")
    download_step = _run_command(
        name="download_waybills",
        command=download_cmd,
        env=env,
        report_path=run_dir / "step_download_waybills.json",
    )
    report["steps"].append(download_step)
    if download_step["returncode"] != 0:
        if args.apply:
            _update_run_control_status(
                client=client,
                contract=contract,
                target_date=target_date,
                run_id=run_id,
                status="FAILED_DOWNLOAD",
            )
        report["failure_stage"] = "download_waybills"
        report["failure_reason"] = "Waybill download failed"
        output_path = args.json_out or (run_dir / "closeout_report.json")
        dump_json(output_path, report)
        return 1

    build_cmd = [
        selected_python,
        str(PROJECT_ROOT / "scripts" / "build_daily_waybills.py"),
        "--db-path",
        str(db_path),
        "--date",
        target_date.isoformat(),
        "--include-overdue",
        "--output-layout",
        "per-store-and-merged",
        "--verbose",
    ]
    if not args.apply:
        build_cmd.append("--dry-run")
    build_step = _run_command(
        name="build_waybills",
        command=build_cmd,
        env=env,
        report_path=run_dir / "step_build_waybills.json",
    )
    report["steps"].append(build_step)
    if build_step["returncode"] != 0:
        if args.apply:
            _update_run_control_status(
                client=client,
                contract=contract,
                target_date=target_date,
                run_id=run_id,
                status="FAILED_BUILD",
            )
        report["failure_stage"] = "build_waybills"
        report["failure_reason"] = "Waybill bundle build failed"
        output_path = args.json_out or (run_dir / "closeout_report.json")
        dump_json(output_path, report)
        return 1

    if args.apply:
        whatsapp_cmd = [
            selected_python,
            str(PROJECT_ROOT / "scripts" / "send_waybills_whatsapp.py"),
            "--today-folder",
            str(Path(args.today_folder).expanduser()),
            "--bundle-source",
            "merged",
            "--expected-target-date",
            target_date.isoformat(),
            "--browser-mode",
            "launch-temp",
            "--fail-fast",
            "--json-out",
            str(run_dir / "whatsapp_send_report.json"),
        ]
        whatsapp_step = _run_command(
            name="whatsapp_send",
            command=whatsapp_cmd,
            env=env,
            report_path=run_dir / "step_whatsapp_send.json",
        )
        report["steps"].append(whatsapp_step)
        if whatsapp_step["returncode"] != 0:
            if args.apply:
                _update_run_control_status(
                    client=client,
                    contract=contract,
                    target_date=target_date,
                    run_id=run_id,
                    status="FAILED_WHATSAPP",
                )
            report["failure_stage"] = "whatsapp_send"
            report["failure_reason"] = "WhatsApp step failed"
            output_path = args.json_out or (run_dir / "closeout_report.json")
            dump_json(output_path, report)
            return 1
    else:
        whatsapp_step = {
            "name": "whatsapp_preflight",
            "command": [],
            "returncode": 0,
            "stdout": "",
            "stderr": "",
            "ok": True,
            "skipped": True,
            "note": "Dry-run closeout skips WhatsApp preflight because no live manifest is created by a dry-run build.",
        }
        dump_json(run_dir / "step_whatsapp_preflight.json", whatsapp_step)
        report["steps"].append(whatsapp_step)

    report["ok"] = True
    report["completed_at"] = datetime.now(ALMATY_TZ).isoformat()
    if args.apply:
        _update_run_control_status(
            client=client,
            contract=contract,
            target_date=target_date,
            run_id=run_id,
            status="OK",
        )
    output_path = args.json_out or (run_dir / "closeout_report.json")
    dump_json(output_path, report)
    print(f"Closeout report: {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
