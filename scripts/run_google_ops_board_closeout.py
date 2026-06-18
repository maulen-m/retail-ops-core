#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from dotenv import load_dotenv


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
from core.alerts.google_ops_board_alerts import send_owner_ops_alert  # noqa: E402
from scripts.google_ops_board_automation_common import (  # noqa: E402
    AUTOMATION_LOCK_HELD_ENV,
    GoogleOpsBoardAutomationLock,
    ensure_kaspi_api_call_ledger_env,
    load_json_file,
    resolve_closeout_checkpoint_path,
    salesraw_writeback_fingerprint,
)
from scripts.run_google_ops_board_prewindow_health import ensure_prewindow_health  # noqa: E402
from scripts.sync_google_ops_board_sizes_to_db import (  # noqa: E402
    _load_db_rows as load_db_rows_for_writeback,
    plan_size_writeback,
)
from scripts.validate_google_closeout_expected_orders import (  # noqa: E402
    build_expected_orders_from_db,
    fetch_api_active_order_ids_by_store,
    find_latest_send_manifest,
    validate_manifest_against_expected,
    write_expected_orders_report,
)
from scripts.waybill_delivery_completion import delivery_completion_state  # noqa: E402


ALMATY_TZ = ZoneInfo("Asia/Almaty")
DEFAULT_DOTENV_PATH = PROJECT_ROOT / ".env"
DEFAULT_RUN_ROOT = data_path("exports", "google_ops_board", "workflow_runs")
DEFAULT_TODAY_FOLDER = data_path("excel_ui", "Kaspi_orders", "Today")
STAGE_ORDER = [
    "size_writeback",
    "shipping",
    "download_waybills",
    "build_waybills",
    "delivery_send",
    "shipped_truth_sync",
]
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


def _load_repo_dotenv() -> None:
    load_dotenv(DEFAULT_DOTENV_PATH, override=False)


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
    hold_on_failure: bool = True,
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
    if hold_on_failure and str(status or "").strip().upper().startswith("FAILED_"):
        updated["ready_for_closeout"] = "HOLD"
    updated["last_verified_ready_at"] = datetime.now(ALMATY_TZ).isoformat()
    updated["last_orchestrator_run_id"] = run_id
    updated["last_orchestrator_status"] = status
    if str(status or "").strip().upper() == "OK":
        updated["ready_for_closeout"] = "HOLD"
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
    started_dt = datetime.now(ALMATY_TZ)
    started_at = started_dt.isoformat()
    proc = subprocess.run(
        command,
        cwd=str(PROJECT_ROOT),
        env=env,
        text=True,
        capture_output=True,
    )
    finished_dt = datetime.now(ALMATY_TZ)
    finished_at = finished_dt.isoformat()
    report = {
        "name": name,
        "command": command,
        "returncode": int(proc.returncode),
        "stdout": proc.stdout,
        "stderr": proc.stderr,
        "started_at": started_at,
        "completed_at": finished_at,
        "finished_at": finished_at,
        "duration_sec": round(max(0.0, (finished_dt - started_dt).total_seconds()), 3),
        "ok": proc.returncode == 0,
    }
    dump_json(report_path, report)
    return report


def _hash_run_control_row(row: dict[str, Any]) -> str:
    payload = json.dumps(row, ensure_ascii=False, sort_keys=True).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def run_control_resume_fingerprint(row: dict[str, Any]) -> str:
    payload = json.dumps(
        {
            "target_date": _clean(row.get("target_date")),
            "ready_for_closeout": _clean(row.get("ready_for_closeout")).upper(),
        },
        ensure_ascii=False,
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _load_checkpoint(path: Path) -> dict[str, Any]:
    payload = load_json_file(path)
    return payload if isinstance(payload, dict) else {}


def _write_checkpoint(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    dump_json(path, payload)


def _build_checkpoint_base(
    *,
    target_date: date,
    db_path: Path,
    spreadsheet_id: str,
    service_account_json: Path,
    run_control_row: dict[str, Any],
    salesraw_rows: list[dict[str, Any]],
) -> dict[str, Any]:
    return {
        "target_date": target_date.isoformat(),
        "db_path": str(db_path.resolve()),
        "spreadsheet_id": spreadsheet_id,
        "service_account_json": str(service_account_json.resolve()),
        "salesraw_writeback_fingerprint": salesraw_writeback_fingerprint(salesraw_rows),
        "run_control_row_hash": _hash_run_control_row(run_control_row),
        "run_control_resume_fingerprint": run_control_resume_fingerprint(run_control_row),
        "stages": {},
    }


def _validate_checkpoint(
    *,
    checkpoint: dict[str, Any],
    target_date: date,
    db_path: Path,
    spreadsheet_id: str,
    service_account_json: Path,
) -> tuple[bool, str]:
    expected = {
        "target_date": target_date.isoformat(),
        "db_path": str(db_path.resolve()),
        "spreadsheet_id": spreadsheet_id,
        "service_account_json": str(service_account_json.resolve()),
    }
    for key, value in expected.items():
        if str(checkpoint.get(key) or "") != value:
            return False, f"checkpoint_{key}_mismatch"
    return True, ""


def _checkpoint_stage_report(
    *,
    checkpoint: dict[str, Any],
    stage: str,
    step_report: dict[str, Any],
    run_id: str,
    run_dir: Path,
    artifact_paths: list[str] | None = None,
) -> None:
    checkpoint.setdefault("stages", {})
    checkpoint["stages"][stage] = {
        "status": "ok" if step_report.get("returncode") == 0 else "failed",
        "run_id": run_id,
        "run_dir": str(run_dir),
        "step_report_path": str(run_dir / f"step_{stage}.json"),
        "artifact_paths": list(artifact_paths or []),
        "summary": (
            str(step_report.get("stdout") or step_report.get("stderr") or "").strip().splitlines()[-1]
            if str(step_report.get("stdout") or step_report.get("stderr") or "").strip().splitlines()
            else ""
        ),
        "updated_at": datetime.now(ALMATY_TZ).isoformat(),
    }


def _contiguous_successful_stages(
    checkpoint: dict[str, Any],
    *,
    salesraw_rows: list[dict[str, Any]],
    run_control_row: dict[str, Any],
    today_folder: Path | None = None,
    target_date: date | None = None,
    run_root: Path = DEFAULT_RUN_ROOT,
) -> list[str]:
    stages = checkpoint.get("stages") or {}
    if str(checkpoint.get("salesraw_writeback_fingerprint") or "") != salesraw_writeback_fingerprint(salesraw_rows):
        return []
    checkpoint_resume_fingerprint = str(checkpoint.get("run_control_resume_fingerprint") or "")
    if checkpoint_resume_fingerprint:
        if checkpoint_resume_fingerprint != run_control_resume_fingerprint(run_control_row):
            return []
    elif str(checkpoint.get("run_control_row_hash") or "") != _hash_run_control_row(run_control_row):
        return []
    successful: list[str] = []
    for stage in STAGE_ORDER:
        state = stages.get(stage) or {}
        if state.get("status") != "ok":
            break
        step_report_path = Path(str(state.get("step_report_path") or "")).expanduser()
        if not step_report_path.exists():
            break
        if stage == "delivery_send" and today_folder is not None and target_date is not None:
            delivery_state = delivery_completion_state(
                today_folder=Path(today_folder),
                target_date=target_date,
                run_root=Path(run_root),
                run_id=str(state.get("run_id") or ""),
            )
            if not delivery_state.get("completed"):
                break
        successful.append(stage)
    return successful


def _checkpoint_has_successful_external_stage(checkpoint: dict[str, Any]) -> bool:
    stages = checkpoint.get("stages") or {}
    for stage in ("shipping", "download_waybills", "build_waybills", "delivery_send"):
        if (stages.get(stage) or {}).get("status") == "ok":
            return True
    return False


def _append_checkpoint_stage(
    *,
    report: dict[str, Any],
    checkpoint: dict[str, Any],
    stage: str,
) -> None:
    stage_state = (checkpoint.get("stages") or {}).get(stage) or {}
    step_report_path = Path(str(stage_state.get("step_report_path") or "")).expanduser()
    step_report = load_json_file(step_report_path)
    if not step_report:
        return
    step_report["from_checkpoint"] = True
    report.setdefault("steps", []).append(step_report)
    artifact_paths = list(stage_state.get("artifact_paths") or [])
    if stage == "size_writeback" and artifact_paths:
        report["size_writeback_report_path"] = artifact_paths[0]


def _send_closeout_alert(
    *,
    title: str,
    run_id: str,
    target_date: date,
    report_path: Path,
    stage: str | None = None,
    resumed: bool = False,
    detail: str | None = None,
) -> None:
    lines = [
        f"Target date: {target_date.isoformat()}",
        f"Run ID: {run_id}",
    ]
    if resumed:
        lines.append("Mode: resumed from checkpoint")
    if stage:
        lines.append(f"Stage: {stage}")
    if detail:
        lines.append(detail)
    lines.append(f"Report: {report_path}")
    send_owner_ops_alert(title=title, lines=lines)


def _write_daily_index_best_effort(*, target_date: date, run_root: Path) -> None:
    try:
        from scripts.google_ops_board_daily_index import write_daily_index

        write_daily_index(target_date=target_date, workflow_root=Path(run_root))
    except Exception as exc:
        print(f"WARNING: unable to update Google Ops Board daily index: {exc}", file=sys.stderr)


def _run_closeout(args: argparse.Namespace) -> int:
    contract = load_ops_board_contract(args.contract)
    _require_apply_gate(args.apply, contract.closeout_write_env_gate)

    target_date = _resolve_target_date(args.target_date)
    db_path = Path(args.db_path).expanduser() if args.db_path else data_path("db", "app.db")
    service_account_json = resolve_service_account_json(args.service_account_json, contract=contract)
    spreadsheet_id = resolve_spreadsheet_id(args.spreadsheet_id, contract=contract)
    client = GoogleOpsBoardClient.from_service_account_file(spreadsheet_id, service_account_json)
    checkpoint_path = Path(args.checkpoint_path).expanduser() if args.checkpoint_path else resolve_closeout_checkpoint_path(
        target_date,
        root=Path(args.run_root).expanduser(),
    )

    run_id = _build_run_id(target_date)
    run_dir = Path(args.run_root).expanduser() / target_date.isoformat() / run_id
    run_dir.mkdir(parents=True, exist_ok=True)

    env = os.environ.copy()
    env.setdefault("PYTHONUNBUFFERED", "1")
    env.setdefault("TERM", "dumb")
    ensure_kaspi_api_call_ledger_env(env, target_date=target_date, project_root=PROJECT_ROOT)
    if env.get("KASPI_API_CALL_LEDGER_PATH"):
        os.environ.setdefault("KASPI_API_CALL_LEDGER_PATH", env["KASPI_API_CALL_LEDGER_PATH"])

    report: dict[str, Any] = {
        "run_id": run_id,
        "mode": "apply" if args.apply else "dry_run",
        "target_date": target_date.isoformat(),
        "db_path": str(db_path),
        "spreadsheet_id": spreadsheet_id,
        "service_account_json": str(service_account_json),
        "run_dir": str(run_dir),
        "checkpoint_path": str(checkpoint_path),
        "steps": [],
        "started_at": datetime.now(ALMATY_TZ).isoformat(),
        "ready": False,
        "resume_requested": bool(args.resume),
        "resumed_from_checkpoint": False,
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
    run_control_row = _select_run_control_row(
        extract_rows_from_matrix(contract.tabs["Run_Control"].headers, run_control_matrix),
        target_date,
    ) or {}
    checkpoint = _build_checkpoint_base(
        target_date=target_date,
        db_path=db_path,
        spreadsheet_id=spreadsheet_id,
        service_account_json=service_account_json,
        run_control_row=run_control_row,
        salesraw_rows=salesraw_rows,
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
            hold_on_failure=False,
        )

    if not readiness["ready"]:
        report["failure_stage"] = "readiness"
        report["failure_reason"] = "Closeout gate failed"
        report["readiness_report_path"] = str(run_dir / "readiness_report.json")
        output_path = args.json_out or (run_dir / "closeout_report.json")
        dump_json(output_path, report)
        _write_daily_index_best_effort(target_date=target_date, run_root=Path(args.run_root).expanduser())
        print(f"Closeout blocked. Readiness report: {run_dir / 'readiness_report.json'}")
        return 1

    if args.apply:
        health = ensure_prewindow_health(
            target_date=target_date,
            db_path=db_path,
            contract_path=args.contract,
            service_account_json=service_account_json,
            spreadsheet_id=spreadsheet_id,
            apply=True,
            reason="closeout_apply",
            profile="closeout",
        )
        report["prewindow_health_report_path"] = str(health.get("report_path") or "")
        if not health.get("ok"):
            _update_run_control_status(
                client=client,
                contract=contract,
                target_date=target_date,
                run_id=run_id,
                status="FAILED_HEALTH_GATE",
                hold_on_failure=False,
            )
            report["failure_stage"] = "prewindow_health"
            report["failure_reason"] = "Prewindow health gate failed"
            output_path = args.json_out or (run_dir / "closeout_report.json")
            dump_json(output_path, report)
            _write_daily_index_best_effort(target_date=target_date, run_root=Path(args.run_root).expanduser())
            _send_closeout_alert(
                title="Google Ops Board Closeout Failed",
                run_id=run_id,
                target_date=target_date,
                report_path=output_path,
                stage="prewindow_health",
                detail="Prewindow health gate is red.",
            )
            return 1

    completed_stages: list[str] = []
    if args.resume and checkpoint_path.exists():
        saved_checkpoint = _load_checkpoint(checkpoint_path)
        valid_checkpoint, checkpoint_reason = _validate_checkpoint(
            checkpoint=saved_checkpoint,
            target_date=target_date,
            db_path=db_path,
            spreadsheet_id=spreadsheet_id,
            service_account_json=service_account_json,
        )
        if not valid_checkpoint:
            report["failure_stage"] = "checkpoint"
            report["failure_reason"] = checkpoint_reason
            output_path = args.json_out or (run_dir / "closeout_report.json")
            dump_json(output_path, report)
            _write_daily_index_best_effort(target_date=target_date, run_root=Path(args.run_root).expanduser())
            if args.apply:
                _update_run_control_status(
                    client=client,
                    contract=contract,
                    target_date=target_date,
                    run_id=run_id,
                    status="FAILED_CHECKPOINT",
                    hold_on_failure=False,
                )
                _send_closeout_alert(
                    title="Google Ops Board Closeout Failed",
                    run_id=run_id,
                    target_date=target_date,
                    report_path=output_path,
                    stage="checkpoint",
                    detail=checkpoint_reason,
                )
            return 1
        checkpoint = saved_checkpoint
        if (
            str(checkpoint.get("salesraw_writeback_fingerprint") or "")
            != salesraw_writeback_fingerprint(salesraw_rows)
            and _checkpoint_has_successful_external_stage(checkpoint)
        ):
            report["failure_stage"] = "checkpoint"
            report["failure_reason"] = "checkpoint_salesraw_mismatch_after_external_stage"
            output_path = args.json_out or (run_dir / "closeout_report.json")
            dump_json(output_path, report)
            _write_daily_index_best_effort(target_date=target_date, run_root=Path(args.run_root).expanduser())
            if args.apply:
                _update_run_control_status(
                    client=client,
                    contract=contract,
                    target_date=target_date,
                    run_id=run_id,
                    status="FAILED_CHECKPOINT",
                    hold_on_failure=False,
                )
                _send_closeout_alert(
                    title="Google Ops Board Closeout Failed",
                    run_id=run_id,
                    target_date=target_date,
                    report_path=output_path,
                    stage="checkpoint",
                    detail=report["failure_reason"],
                )
            return 1
        completed_stages = _contiguous_successful_stages(
            checkpoint,
            salesraw_rows=salesraw_rows,
            run_control_row=run_control_row,
            today_folder=Path(args.today_folder).expanduser(),
            target_date=target_date,
            run_root=Path(args.run_root).expanduser(),
        )
        report["resumed_stages"] = completed_stages
        report["resumed_from_checkpoint"] = bool(completed_stages)
        for stage in completed_stages:
            _append_checkpoint_stage(report=report, checkpoint=checkpoint, stage=stage)

    output_path = args.json_out or (run_dir / "closeout_report.json")
    if args.apply:
        _send_closeout_alert(
            title="Google Ops Board Closeout Resumed" if completed_stages else "Google Ops Board Closeout Started",
            run_id=run_id,
            target_date=target_date,
            report_path=output_path,
            resumed=bool(completed_stages),
            detail=f"Completed stages: {', '.join(completed_stages)}" if completed_stages else None,
        )

    selected_python = str(PROJECT_ROOT / ".venv" / "bin" / "python")
    if not Path(selected_python).exists():
        selected_python = sys.executable

    def _record_failure(stage: str, reason: str, step_report: dict[str, Any] | None = None) -> int:
        if step_report is not None:
            _checkpoint_stage_report(
                checkpoint=checkpoint,
                stage=stage,
                step_report=step_report,
                run_id=run_id,
                run_dir=run_dir,
            )
            _write_checkpoint(checkpoint_path, checkpoint)
        if args.apply:
            _update_run_control_status(
                client=client,
                contract=contract,
                target_date=target_date,
                run_id=run_id,
                status=f"FAILED_{stage.upper()}",
                hold_on_failure=False,
            )
        report["failure_stage"] = stage
        report["failure_reason"] = reason
        dump_json(output_path, report)
        _write_daily_index_best_effort(target_date=target_date, run_root=Path(args.run_root).expanduser())
        if args.apply:
            _send_closeout_alert(
                title="Google Ops Board Closeout Failed",
                run_id=run_id,
                target_date=target_date,
                report_path=output_path,
                stage=stage,
                resumed=bool(completed_stages),
                detail=reason,
            )
        return 1

    if "size_writeback" not in completed_stages:
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
            return _record_failure("size_writeback", "Final size writeback failed", step_report)
        artifact_paths = [str(size_writeback_json)] if size_writeback_json.exists() else []
        _checkpoint_stage_report(
            checkpoint=checkpoint,
            stage="size_writeback",
            step_report=step_report,
            run_id=run_id,
            run_dir=run_dir,
            artifact_paths=artifact_paths,
        )
        checkpoint["salesraw_writeback_fingerprint"] = salesraw_writeback_fingerprint(salesraw_rows)
        checkpoint["run_control_row_hash"] = _hash_run_control_row(run_control_row)
        checkpoint["run_control_resume_fingerprint"] = run_control_resume_fingerprint(run_control_row)
        _write_checkpoint(checkpoint_path, checkpoint)
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
        return _record_failure("store_context", "Store token / merchant UID context failed preflight")

    expected_orders_path = run_dir / "expected_closeout_orders.json"
    if args.apply:
        active_order_ids_by_store = fetch_api_active_order_ids_by_store(
            target_date=target_date,
            lookback_days=args.lookback_days,
            store_codes=store_context.get("active_store_codes") or None,
            api_since_days=14,
            verbose=False,
        )
        dump_json(
            run_dir / "api_active_order_ids_by_store.json",
            {
                "target_date": target_date.isoformat(),
                "lookback_days": args.lookback_days,
                "api_since_days": 14,
                "counts_by_store": {
                    store: len(order_ids)
                    for store, order_ids in sorted(active_order_ids_by_store.items())
                },
                "stores": {
                    store: sorted(order_ids)
                    for store, order_ids in sorted(active_order_ids_by_store.items())
                },
            },
        )
        report["api_active_order_ids_by_store_path"] = str(run_dir / "api_active_order_ids_by_store.json")
        expected_orders = build_expected_orders_from_db(
            db_path=db_path,
            target_date=target_date,
            lookback_days=args.lookback_days,
            active_order_ids_by_store=active_order_ids_by_store,
        )
        write_expected_orders_report(expected_orders, expected_orders_path)
        report["expected_closeout_orders_path"] = str(expected_orders_path)
        report["expected_closeout_order_count"] = expected_orders["counts"]["orders"]
        report["expected_closeout_overdue_order_count"] = expected_orders["counts"]["overdue_orders"]

    if "shipping" not in completed_stages:
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
            return _record_failure("shipping", "DB-first shipping failed", ship_step)
        _checkpoint_stage_report(
            checkpoint=checkpoint,
            stage="shipping",
            step_report=ship_step,
            run_id=run_id,
            run_dir=run_dir,
            artifact_paths=[str(run_dir / "shipping_report.json")],
        )
        _write_checkpoint(checkpoint_path, checkpoint)

    if "download_waybills" not in completed_stages:
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
            return _record_failure("download_waybills", "Waybill download failed", download_step)
        _checkpoint_stage_report(
            checkpoint=checkpoint,
            stage="download_waybills",
            step_report=download_step,
            run_id=run_id,
            run_dir=run_dir,
        )
        _write_checkpoint(checkpoint_path, checkpoint)

    if "build_waybills" not in completed_stages:
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
            return _record_failure("build_waybills", "Waybill bundle build failed", build_step)
        _checkpoint_stage_report(
            checkpoint=checkpoint,
            stage="build_waybills",
            step_report=build_step,
            run_id=run_id,
            run_dir=run_dir,
        )
        _write_checkpoint(checkpoint_path, checkpoint)

    if args.apply:
        if "delivery_send" not in completed_stages:
            manifest_path = find_latest_send_manifest(Path(args.today_folder).expanduser())
            if manifest_path is None:
                gate_report = {
                    "ok": False,
                    "issue_codes": ["send_manifest_missing"],
                    "expected_path": str(expected_orders_path),
                    "today_folder": str(Path(args.today_folder).expanduser()),
                }
                gate_path = run_dir / "expected_order_manifest_gate.json"
                dump_json(gate_path, gate_report)
                report["expected_order_manifest_gate_path"] = str(gate_path)
                return _record_failure("expected_order_gate", "No MERGED/SEND send_batch_manifest.json found")

            gate_report = validate_manifest_against_expected(
                expected_path=expected_orders_path,
                manifest_path=manifest_path,
            )
            gate_path = run_dir / "expected_order_manifest_gate.json"
            dump_json(gate_path, gate_report)
            report["expected_order_manifest_gate_path"] = str(gate_path)
            report["expected_order_manifest_gate_ok"] = bool(gate_report.get("ok"))
            if not gate_report.get("ok"):
                reason_bits = [
                    f"issues={','.join(gate_report.get('issue_codes') or [])}",
                    f"expected={gate_report.get('expected_count')}",
                    f"manifest={gate_report.get('manifest_count')}",
                ]
                missing = gate_report.get("missing_order_ids") or []
                extra = gate_report.get("extra_order_ids") or []
                if missing:
                    reason_bits.append(f"missing={','.join(missing)}")
                if extra:
                    reason_bits.append(f"extra={','.join(extra)}")
                return _record_failure("expected_order_gate", "Expected order manifest gate failed: " + "; ".join(reason_bits))

        if "delivery_send" not in completed_stages:
            delivery_cmd = [
                selected_python,
                str(PROJECT_ROOT / "scripts" / "send_waybills_delivery.py"),
                "--today-folder",
                str(Path(args.today_folder).expanduser()),
                "--bundle-source",
                "merged",
                "--expected-target-date",
                target_date.isoformat(),
                "--whatsapp-fallback-policy",
                "auto-zero-fail",
                "--json-out",
                str(run_dir / "delivery_send_report.json"),
            ]
            delivery_step = _run_command(
                name="delivery_send",
                command=delivery_cmd,
                env=env,
                report_path=run_dir / "step_delivery_send.json",
            )
            report["steps"].append(delivery_step)
            if delivery_step["returncode"] != 0:
                return _record_failure("delivery_send", "Delivery step failed", delivery_step)
            _checkpoint_stage_report(
                checkpoint=checkpoint,
                stage="delivery_send",
                step_report=delivery_step,
                run_id=run_id,
                run_dir=run_dir,
                artifact_paths=[str(run_dir / "delivery_send_report.json")],
            )
            _write_checkpoint(checkpoint_path, checkpoint)

        if "shipped_truth_sync" not in completed_stages:
            shipped_sync_env = dict(env)
            shipped_sync_env["ENABLE_KASPI_SHIPPED_TRUTH_SYNC"] = "1"
            shipped_sync_cmd = [
                selected_python,
                str(PROJECT_ROOT / "scripts" / "run_kaspi_shipped_truth_sync_scheduler.py"),
                "--target-date",
                target_date.isoformat(),
                "--lookback-days",
                str(args.lookback_days),
                "--db-path",
                str(db_path),
                "--json-out",
                str(run_dir / "shipped_truth_sync_report.json"),
                "--reason",
                "post_closeout_delivery",
            ]
            shipped_sync_step = _run_command(
                name="shipped_truth_sync",
                command=shipped_sync_cmd,
                env=shipped_sync_env,
                report_path=run_dir / "step_shipped_truth_sync.json",
            )
            report["steps"].append(shipped_sync_step)
            if shipped_sync_step["returncode"] != 0:
                return _record_failure(
                    "shipped_truth_sync",
                    "Post-delivery Kaspi shipped-truth sync failed; delivery checkpoint is preserved, rerun closeout with --resume.",
                    shipped_sync_step,
                )
            _checkpoint_stage_report(
                checkpoint=checkpoint,
                stage="shipped_truth_sync",
                step_report=shipped_sync_step,
                run_id=run_id,
                run_dir=run_dir,
                artifact_paths=[str(run_dir / "shipped_truth_sync_report.json")],
            )
            _write_checkpoint(checkpoint_path, checkpoint)
    else:
        delivery_step = {
            "name": "delivery_preflight",
            "command": [],
            "returncode": 0,
            "stdout": "",
            "stderr": "",
            "ok": True,
            "skipped": True,
            "note": "Dry-run closeout skips delivery preflight because no live manifest is created by a dry-run build.",
        }
        dump_json(run_dir / "step_delivery_preflight.json", delivery_step)
        report["steps"].append(delivery_step)

    report["ok"] = True
    report["completed_at"] = datetime.now(ALMATY_TZ).isoformat()
    if args.apply:
        _update_run_control_status(
            client=client,
            contract=contract,
            target_date=target_date,
            run_id=run_id,
            status="OK",
            hold_on_failure=False,
        )
    _write_checkpoint(checkpoint_path, checkpoint)
    dump_json(output_path, report)
    _write_daily_index_best_effort(target_date=target_date, run_root=Path(args.run_root).expanduser())
    if args.apply:
        _send_closeout_alert(
            title="Google Ops Board Closeout Complete",
            run_id=run_id,
            target_date=target_date,
            report_path=output_path,
            resumed=bool(completed_stages),
        )
    print(f"Closeout report: {output_path}")
    return 0


def main(argv: list[str] | None = None) -> int:
    _load_repo_dotenv()

    parser = argparse.ArgumentParser(description="Run fail-closed Google Ops Board daily closeout.")
    parser.add_argument("--contract", type=Path, default=DEFAULT_CONTRACT_PATH, help="Contract YAML path")
    parser.add_argument("--db-path", type=Path, default=None, help="Optional DB path (default: db/app.db)")
    parser.add_argument("--service-account-json", type=Path, default=None, help="Path to service-account JSON")
    parser.add_argument("--spreadsheet-id", type=str, default=None, help="Override spreadsheet ID")
    parser.add_argument("--target-date", type=str, default="today", help="Target date (default: today)")
    parser.add_argument("--lookback-days", type=int, default=5, help="Operational lookback window (default: 5)")
    parser.add_argument("--today-folder", type=Path, default=DEFAULT_TODAY_FOLDER, help="Today folder for send step")
    parser.add_argument("--run-root", type=Path, default=DEFAULT_RUN_ROOT, help="Workflow run output root")
    parser.add_argument("--checkpoint-path", type=Path, default=None, help="Optional day-level checkpoint path")
    parser.add_argument("--resume", action="store_true", help="Reuse prior successful safe stages when possible")
    parser.add_argument("--apply", action="store_true", help="Run live closeout (default: dry-run)")
    parser.add_argument("--json-out", type=Path, default=None, help="Optional top-level JSON report path")
    args = parser.parse_args(argv)

    if args.apply and str(os.environ.get(AUTOMATION_LOCK_HELD_ENV) or "").strip() != "1":
        previous = os.environ.get(AUTOMATION_LOCK_HELD_ENV)
        try:
            with GoogleOpsBoardAutomationLock():
                os.environ[AUTOMATION_LOCK_HELD_ENV] = "1"
                return _run_closeout(args)
        finally:
            if previous is None:
                os.environ.pop(AUTOMATION_LOCK_HELD_ENV, None)
            else:
                os.environ[AUTOMATION_LOCK_HELD_ENV] = previous

    return _run_closeout(args)


if __name__ == "__main__":
    raise SystemExit(main())
