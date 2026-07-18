#!/usr/bin/env python3
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import math
import os
import subprocess
import sys
import time
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Mapping, MutableMapping
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
from core.alerts.ops_alert_outbox import enqueue_alert, flush_held  # noqa: E402
from core.ops.waybill_send_batch import (  # noqa: E402
    SEND_LEDGER_FILE,
    compute_manifest_batch_hash,
)
from core.ops.waybill_prepacked_exclusions import (  # noqa: E402
    apply_prepacked_exclusion,
    load_prepacked_exclusion_expectation,
    load_validated_prepacked_exclusion,
)
from core.ops.google_board_day_state import (  # noqa: E402
    effective_store_states,
    load_store_day_states,
    set_store_day_state,
)
from core.ops.waybill_shipping_obligations import (  # noqa: E402
    active_obligation_ids_by_store,
    load_required_orders_file,
    load_shipping_obligation_ledger,
    normalize_store_code,
    obligation_key,
    open_obligation_keys_needing_detail,
    reconcile_shipping_obligations,
    save_shipping_obligation_ledger,
)
from core.stores.roster import load_sync_enabled_kaspi_store_codes  # noqa: E402
from scripts.google_ops_board_automation_common import (  # noqa: E402
    AUTOMATION_LOCK_HELD_ENV,
    GoogleOpsBoardAutomationLock,
    ensure_kaspi_api_call_ledger_env,
    evaluate_closeout_halt_barrier,
    load_json_file,
    resolve_closeout_checkpoint_path,
    run_guarded,
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
    validate_required_orders_against_db,
    validate_manifest_against_expected,
    write_expected_orders_report,
)
from scripts.waybill_delivery_completion import delivery_completion_state  # noqa: E402
from core.ops.fitpack_coordination import (  # noqa: E402
    EXCLUSION_LOG_LINE,
    filter_storeb_store_codes,
    is_storeb_store,
    load_storeb_packing_excluded,
)


ALMATY_TZ = ZoneInfo("Asia/Almaty")
DEFAULT_DOTENV_PATH = PROJECT_ROOT / ".env"
DEFAULT_RUN_ROOT = data_path("exports", "google_ops_board", "workflow_runs")
DEFAULT_TODAY_FOLDER = data_path("excel_ui", "Kaspi_orders", "Today")
DEFAULT_SHIPPING_OBLIGATION_LEDGER_PATH = data_path(
    "runtime", "state", "waybill_shipping_obligations.json"
)
OBLIGATION_DETAIL_MAX_OPEN = 100
OBLIGATION_DETAIL_MAX_EXACT_READS = 60
OBLIGATION_DETAIL_MAX_PAGES_PER_STATE = 10
OBLIGATION_DETAIL_MAX_SECONDS = 120.0
OBLIGATION_DETAIL_BULK_THRESHOLD = 5
OBLIGATION_DETAIL_MAX_OPEN_ENV = "OBLIGATION_DETAIL_MAX_OPEN"
OBLIGATION_DETAIL_MAX_PAGES_PER_STATE_ENV = (
    "OBLIGATION_DETAIL_MAX_PAGES_PER_STATE"
)
OBLIGATION_DETAIL_BULK_THRESHOLD_ENV = (
    "OBLIGATION_DETAIL_BULK_THRESHOLD"
)
OBLIGATION_DETAIL_MAX_EXACT_READS_ENV = "OBLIGATION_DETAIL_MAX_EXACT_READS"
OBLIGATION_DETAIL_MAX_SECONDS_ENV = "OBLIGATION_DETAIL_MAX_SECONDS"
OBLIGATION_BUDGET_WARNING_FRACTION = 0.8
OBLIGATION_BUDGET_ALERT_DEDUP_WINDOW = timedelta(days=370)
_INVALID_ENV_WARNINGS_EMITTED: set[tuple[str, str]] = set()
STAGE_ORDER = [
    "size_writeback",
    "shipping",
    "download_waybills",
    "build_waybills",
    "delivery_send",
    "shipped_truth_sync",
]
STAGE_TIMEOUT_SECONDS = {
    "size_writeback": 600,
    "shipping": 1200,
    "download_waybills": 1200,
    "build_waybills": 600,
    "delivery_send": 1200,
    "shipped_truth_sync": 600,
    "telegram_delivery": 1200,
}
ENV_TUNABLE_STAGE_TIMEOUTS = frozenset(
    {
        "size_writeback",
        "shipping",
        "download_waybills",
        "build_waybills",
        "delivery_send",
        "shipped_truth_sync",
    }
)
STORE_NAME_TO_API_CODE = {
    "AcmeWear": "ACMEWEAR",
    "Universal": "UNIVERSAL",
    "11KZ": "11KZ",
    "STORE-B": "STOREB",
    "Store-C": "MELVIS",
}


class _PreservedBoardClient:
    """Read-only Google Board adapter backed by a completed run's snapshots."""

    def __init__(self, matrices: dict[str, list[Any]]) -> None:
        self._matrices = copy.deepcopy(matrices)

    def get_tab_values(self, tab_name: str) -> list[Any]:
        if tab_name not in self._matrices:
            raise KeyError(f"preserved board snapshot has no tab: {tab_name}")
        return copy.deepcopy(self._matrices[tab_name])

    def update_tab_rows(self, *_args: Any, **_kwargs: Any) -> None:
        raise RuntimeError("preserved board client is read-only")


def _read_json_object(path: Path, *, label: str) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"{label} is missing or invalid JSON") from exc
    if not isinstance(payload, dict):
        raise ValueError(f"{label} must be a JSON object")
    return payload


def _load_preserved_board_client(
    run_dir: Path,
    *,
    target_date: date,
) -> tuple[_PreservedBoardClient, dict[str, Any]]:
    """Load an offline Board view from one successful apply closeout."""

    source = Path(run_dir).expanduser().resolve()
    if not source.is_dir():
        raise ValueError("preserved board run directory is missing")
    report = _read_json_object(
        source / "closeout_report.json", label="preserved closeout report"
    )
    target_iso = target_date.isoformat()
    if report.get("ok") is not True or str(report.get("mode") or "") != "apply":
        raise ValueError("preserved board source must be a successful apply closeout")
    if str(report.get("target_date") or "") != target_iso:
        raise ValueError("preserved closeout target date does not match replay target date")

    matrices: dict[str, list[Any]] = {}
    for tab_name, filename in (
        ("Run_Control", "run_control_snapshot.json"),
        ("SalesRaw_Today", "salesraw_snapshot.json"),
    ):
        snapshot = _read_json_object(
            source / filename, label=f"preserved {tab_name} snapshot"
        )
        if str(snapshot.get("target_date") or "") != target_iso:
            raise ValueError(f"preserved {tab_name} snapshot target date does not match")
        matrix = snapshot.get("matrix")
        if not isinstance(matrix, list) or not all(
            isinstance(row, list) for row in matrix
        ):
            raise ValueError(f"preserved {tab_name} snapshot matrix must be a list")
        matrices[tab_name] = matrix

    return _PreservedBoardClient(matrices), {
        "board_source_mode": "preserved_snapshot",
        "board_source_path": str(source),
        "source_apply_run_id": str(report.get("run_id") or ""),
    }


def _filter_storeb_salesraw_rows(
    rows: list[dict[str, Any]],
    *,
    enabled: bool,
    context: str,
) -> tuple[list[dict[str, Any]], int]:
    if not enabled:
        return rows, 0
    kept = [row for row in rows if not is_storeb_store(row.get("STORE_NAME"))]
    skipped = len(rows) - len(kept)
    if skipped:
        print(f"{EXCLUSION_LOG_LINE}: skipped {skipped} STORE-B SalesRaw rows in {context}.")
    return kept, skipped


def _filter_salesraw_to_sync_enabled_stores(
    rows: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], int]:
    enabled = {
        normalize_store_code(value) for value in load_sync_enabled_kaspi_store_codes()
    }
    kept = [
        row
        for row in rows
        if normalize_store_code(row.get("STORE_NAME")) in enabled
    ]
    return kept, len(rows) - len(kept)


def _require_apply_gate(apply: bool, env_name: str) -> None:
    if apply and str(os.environ.get(env_name) or "").strip() != "1":
        raise RuntimeError(f"{env_name}=1 is required with --apply")


def _load_repo_dotenv() -> None:
    load_dotenv(DEFAULT_DOTENV_PATH, override=False)


def _strip_shadow_write_gates(
    environment: MutableMapping[str, str] | None = None,
) -> list[str]:
    """Remove every local write enable before a receiver shadow can run."""

    target = os.environ if environment is None else environment
    removed = sorted(
        key
        for key in target
        if key.startswith("ENABLE_") or key == AUTOMATION_LOCK_HELD_ENV
    )
    for key in removed:
        target.pop(key, None)
    return removed


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


def _prepacked_exclusion_expectation_error(
    expectation: Mapping[str, Any] | None,
    decision: Mapping[str, Any] | None,
) -> str:
    if expectation is None:
        return ""
    if decision is None:
        return "expected prepacked-exclusion decision is missing or targets another date"
    expected_id = _clean(expectation.get("decision_id"))
    observed_id = _clean(decision.get("decision_id"))
    if observed_id != expected_id:
        return (
            "prepacked-exclusion decision_id mismatch: "
            f"expected={expected_id} observed={observed_id or 'missing'}"
        )
    expected_sha = _clean(expectation.get("decision_sha256")).lower()
    observed_sha = _clean(decision.get("decision_sha256")).lower()
    if observed_sha != expected_sha:
        return (
            "prepacked-exclusion file SHA-256 mismatch: "
            f"expected={expected_sha} observed={observed_sha or 'missing'}"
        )
    return ""


def _enforce_prepacked_exclusion_expectation(
    *,
    target_date: date,
    expectation: Mapping[str, Any] | None,
    decision: Mapping[str, Any] | None,
) -> str:
    error = _prepacked_exclusion_expectation_error(expectation, decision)
    if error:
        enqueue_alert(
            title="Prepacked exclusion arm expectation failed closed",
            lines=[
                f"Target date: {target_date.isoformat()}",
                error,
                "Closeout stopped before obligation reconciliation or shipping.",
            ],
            severity="CRITICAL",
            dedup_key=(
                "prepacked_exclusion_expectation_failed:"
                f"{target_date.isoformat()}"
            ),
        )
    return error


def _build_run_id(target_date: date) -> str:
    stamp = datetime.now(ALMATY_TZ).strftime("%Y%m%d_%H%M%S")
    return f"{stamp}_{target_date.isoformat()}_closeout"


def _select_run_control_row(rows: list[dict[str, Any]], target_date: date) -> dict[str, Any] | None:
    target_iso = target_date.isoformat()
    for row in rows:
        if _clean(row.get("target_date")) == target_iso:
            return row
    return None


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
    storeb_excluded: bool | None = None,
) -> dict[str, Any]:
    if storeb_excluded is None:
        storeb_excluded = load_storeb_packing_excluded(warn=lambda msg: print(msg, file=sys.stderr))
    run_control_headers = contract.tabs["Run_Control"].headers
    salesraw_headers = contract.tabs["SalesRaw_Today"].headers

    run_control_matrix = client.get_tab_values("Run_Control")
    salesraw_matrix = client.get_tab_values("SalesRaw_Today")
    run_control_rows = extract_rows_from_matrix(run_control_headers, run_control_matrix)
    salesraw_rows = extract_rows_from_matrix(salesraw_headers, salesraw_matrix)
    salesraw_rows, sync_disabled_skipped = _filter_salesraw_to_sync_enabled_stores(
        salesraw_rows
    )
    salesraw_rows, fitpack_skipped = _filter_storeb_salesraw_rows(
        salesraw_rows,
        enabled=bool(storeb_excluded),
        context="closeout readiness",
    )
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

    writeback_key = contract.writeback["size_assignments"]["key_column"]
    visible_db_row_ids = {
        _clean(row.get(writeback_key))
        for row in salesraw_rows
        if _clean(row.get(writeback_key))
    }
    db_rows = load_db_rows_for_writeback(db_path, visible_db_row_ids)
    writeback_plan = plan_size_writeback(
        salesraw_rows,
        db_rows,
        key_column=writeback_key,
        source_column=contract.writeback["size_assignments"]["source_column"],
        require_visible_identity=True,
    )

    target_match = bool(run_control_row) and _clean(run_control_row.get("target_date")) == target_date.isoformat()
    ready_value = _clean((run_control_row or {}).get("ready_for_closeout")).upper()
    ready_toggle_ok = ready_value == "READY"
    ready_set_at = _clean((run_control_row or {}).get("ready_set_at"))
    request_identity_ok = bool(ready_set_at)
    no_blank_sizes = len(blank_size_rows) == 0
    no_invalid_sizes = len(writeback_plan["invalid_rows"]) == 0

    report = {
        "target_date": target_date.isoformat(),
        "run_control_row": run_control_row or {},
        "run_control_target_match": target_match,
        "run_control_ready_value": ready_value,
        "run_control_ready_ok": ready_toggle_ok,
        "ready_set_at": ready_set_at,
        "request_identity_ok": request_identity_ok,
        "salesraw_row_count": len(salesraw_rows),
        "blank_size_rows": blank_size_rows,
        "blank_size_count": len(blank_size_rows),
        "invalid_size_rows": writeback_plan["invalid_rows"],
        "invalid_size_count": len(writeback_plan["invalid_rows"]),
        "pending_db_writeback_updates": writeback_plan["updates"],
        "pending_db_writeback_count": len(writeback_plan["updates"]),
        "ready": bool(
            target_match
            and ready_toggle_ok
            and request_identity_ok
            and no_blank_sizes
            and no_invalid_sizes
        ),
    }
    if storeb_excluded:
        report["fitpack_storeb_excluded"] = True
        report["fitpack_storeb_skipped_rows"] = fitpack_skipped
    if sync_disabled_skipped:
        report["sync_disabled_store_rows_skipped"] = sync_disabled_skipped
    return report


def build_store_context_report(
    *,
    salesraw_rows: list[dict[str, Any]],
    storeb_excluded: bool | None = None,
) -> dict[str, Any]:
    """Validate the configured shipping roster independently of Sheet contents.

    ``salesraw_rows`` remains in the signature for compatibility with existing
    callers and tests, but it is deliberately not the discovery authority.  A
    store omitted from the Sheet must still be queried so its active orders can
    be repaired into the next complete batch.
    """
    del salesraw_rows
    configured_codes = [
        normalize_store_code(code)
        for code in load_sync_enabled_kaspi_store_codes()
    ]
    duplicate_codes = sorted(
        {code for code in configured_codes if configured_codes.count(code) > 1}
    )
    if storeb_excluded is None:
        storeb_excluded = load_storeb_packing_excluded(
            warn=lambda msg: print(msg, file=sys.stderr)
        )
    active_store_codes = list(dict.fromkeys(configured_codes))
    active_store_codes = filter_storeb_store_codes(
        active_store_codes,
        enabled=storeb_excluded,
        warn=lambda msg: print(msg, file=sys.stderr),
        context="configured closeout store roster",
    )

    store_reports: list[dict[str, Any]] = []
    failures: list[dict[str, Any]] = []
    for duplicate_code in duplicate_codes:
        failures.append(
            {
                "store_code": duplicate_code,
                "token_env": "",
                "merchant_uid": "",
                "ok": False,
                "error": "duplicate normalized store code in configured shipping roster",
            }
        )
    for store_code in active_store_codes:
        token_env = STORE_TOKEN_MAP.get(store_code)
        if not token_env:
            store_report = {
                "store_code": store_code,
                "token_env": "",
                "merchant_uid": "",
                "ok": False,
                "error": "configured sync-enabled store is missing from STORE_TOKEN_MAP",
            }
            store_reports.append(store_report)
            failures.append(store_report)
            continue
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
        "ok": bool(active_store_codes) and len(failures) == 0,
        "active_store_codes": active_store_codes,
        "scope_source": "config/kaspi_stores.yaml:sync_enabled",
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
    timeout_seconds = _resolved_stage_timeout_seconds(name)
    timed_out = False
    try:
        proc = subprocess.run(
            command,
            cwd=str(PROJECT_ROOT),
            env=env,
            text=True,
            capture_output=True,
            timeout=timeout_seconds,
        )
        returncode = int(proc.returncode)
        stdout = proc.stdout
        stderr = proc.stderr
    except subprocess.TimeoutExpired as exc:
        timed_out = True
        returncode = 124
        stdout = (
            exc.stdout.decode(errors="replace")
            if isinstance(exc.stdout, bytes)
            else (exc.stdout or "")
        )
        stderr = (
            exc.stderr.decode(errors="replace")
            if isinstance(exc.stderr, bytes)
            else (exc.stderr or "")
        )
    finished_dt = datetime.now(ALMATY_TZ)
    finished_at = finished_dt.isoformat()
    report = {
        "name": name,
        "command": command,
        "returncode": returncode,
        "stdout": stdout,
        "stderr": stderr,
        "started_at": started_at,
        "completed_at": finished_at,
        "finished_at": finished_at,
        "duration_sec": round(max(0.0, (finished_dt - started_dt).total_seconds()), 3),
        "timeout_seconds": timeout_seconds,
        "timed_out": timed_out,
        "ok": returncode == 0,
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
            "ready_set_at": _clean(row.get("ready_set_at")),
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


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _is_sha256(value: Any) -> bool:
    text = _clean(value)
    return len(text) == 64 and all(char in "0123456789abcdefABCDEF" for char in text)


def _resolve_shipping_obligation_ledger_path(args: argparse.Namespace) -> Path:
    run_root = Path(args.run_root).expanduser()
    canonical_path = Path(DEFAULT_SHIPPING_OBLIGATION_LEDGER_PATH).expanduser()
    default_run_root = Path(DEFAULT_RUN_ROOT).expanduser()
    if args.obligation_ledger_path:
        explicit_path = Path(args.obligation_ledger_path).expanduser()
        if (
            args.apply
            and run_root.resolve() != default_run_root.resolve()
            and explicit_path.resolve() != canonical_path.resolve()
        ):
            raise ValueError(
                "--apply with a custom --run-root requires --obligation-ledger-path "
                "to resolve to the canonical shipping-obligation ledger"
            )
        return explicit_path
    if run_root.resolve() == default_run_root.resolve():
        return canonical_path
    if args.apply:
        raise ValueError(
            "--apply with a custom --run-root requires an explicit canonical "
            "--obligation-ledger-path"
        )
    # Custom/test run roots must not mutate the canonical runtime state.
    return run_root / "_state" / "waybill_shipping_obligations.json"


def _send_manifest_paths(today_folder: Path) -> set[Path]:
    root = Path(today_folder).expanduser() / "MERGED" / "SEND"
    if not root.exists():
        return set()
    return {path.resolve() for path in root.glob("*/send_batch_manifest.json") if path.is_file()}


def _pdf_scope_hash(entries: list[dict[str, Any]]) -> str:
    stable = [
        {
            "pdf_key": _clean(entry.get("pdf_key")),
            "sha256": _clean(entry.get("sha256")),
            "relative_output_path": _clean(entry.get("relative_output_path")),
            "order_ids": sorted(_clean(value) for value in entry.get("order_ids") or [] if _clean(value)),
        }
        for entry in entries
        if isinstance(entry, dict)
    ]
    stable.sort(key=lambda item: item["pdf_key"])
    return hashlib.sha256(
        json.dumps(stable, ensure_ascii=False, sort_keys=True).encode("utf-8")
    ).hexdigest()


def _order_scope_hash(orders_by_store: dict[str, set[str]]) -> str:
    stable = {
        store: sorted(order_ids)
        for store, order_ids in sorted(orders_by_store.items())
    }
    return hashlib.sha256(
        json.dumps(stable, ensure_ascii=False, sort_keys=True).encode("utf-8")
    ).hexdigest()


def _write_size_writeback_scope(
    path: Path,
    *,
    target_date: date,
    request_identity: dict[str, str],
    orders_by_store: dict[str, set[str]],
    salesraw_rows: list[dict[str, Any]],
) -> Path:
    orders = [
        {"store_code": normalize_store_code(store), "order_id": _clean(order_id)}
        for store, order_ids in sorted(orders_by_store.items())
        for order_id in sorted(order_ids)
        if normalize_store_code(store) and _clean(order_id)
    ]
    orders.sort(key=lambda item: (item["store_code"], item["order_id"]))
    allowed_pairs = {(item["store_code"], item["order_id"]) for item in orders}
    rows = [
        {
            "store_code": normalize_store_code(row.get("STORE_NAME")),
            "order_id": _clean(row.get("OrderID")),
            "db_row_id": _clean(row.get("_db_row_id")),
            "line_key": _clean(row.get("_line_key")),
            "my_size": _clean(row.get("MY_SIZE")),
        }
        for row in salesraw_rows
        if (
            normalize_store_code(row.get("STORE_NAME")),
            _clean(row.get("OrderID")),
        )
        in allowed_pairs
    ]
    rows.sort(
        key=lambda item: (
            item["store_code"],
            item["order_id"],
            item["db_row_id"],
            item["line_key"],
        )
    )
    if orders and (not rows or any(
        not all(
            (
                item["store_code"],
                item["order_id"],
                item["db_row_id"],
                item["line_key"],
                item["my_size"],
            )
        )
        for item in rows
    )):
        raise ValueError("size writeback scope has incomplete pinned SalesRaw rows")
    if len({item["db_row_id"] for item in rows}) != len(rows):
        raise ValueError("size writeback scope has duplicate SalesRaw DB row identities")
    scope_sha256 = hashlib.sha256(
        json.dumps(rows, ensure_ascii=False, sort_keys=True).encode("utf-8")
    ).hexdigest()
    dump_json(
        path,
        {
            "schema_version": 2,
            "target_date": target_date.isoformat(),
            "request_identity": dict(request_identity),
            "orders": orders,
            "rows": rows,
            "scope_sha256": scope_sha256,
        },
    )
    return path


def _pin_send_manifest(
    *,
    manifest_path: Path,
    today_folder: Path,
    expected_orders_path: Path,
) -> dict[str, Any]:
    manifest_path = Path(manifest_path).expanduser().resolve()
    today_root = Path(today_folder).expanduser().resolve()
    try:
        manifest_path.relative_to(today_root)
    except ValueError as exc:
        raise ValueError("send manifest is outside the configured Today folder") from exc
    if manifest_path.name != "send_batch_manifest.json" or not manifest_path.is_file():
        raise ValueError(f"send manifest is missing or misnamed: {manifest_path}")

    expected = load_required_orders_file(Path(expected_orders_path), target_date=date.fromisoformat(
        json.loads(Path(expected_orders_path).read_text(encoding="utf-8"))["target_date"]
    ))
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if not isinstance(manifest, dict):
        raise ValueError("send manifest must be a JSON object")
    if _clean(manifest.get("target_date")) != _clean(expected["payload"].get("target_date")):
        raise ValueError("send manifest target_date does not match required orders")
    if dict(manifest.get("request_identity") or {}) != dict(expected["request_identity"]):
        raise ValueError("send manifest request_identity does not match required orders")
    if _clean(manifest.get("expected_orders_sha256")) != expected["sha256"]:
        raise ValueError("send manifest expected_orders_sha256 does not match required orders")
    expected_scope_hash = _order_scope_hash(expected["orders_by_store"])
    if _clean(manifest.get("obligation_scope_hash")) != expected_scope_hash:
        raise ValueError("send manifest obligation_scope_hash does not match required orders")

    entries = manifest.get("entries") or []
    if not isinstance(entries, list):
        raise ValueError("send manifest entries must be a list")
    batch_hash = _clean(manifest.get("batch_hash"))
    if not _is_sha256(batch_hash):
        raise ValueError("send manifest batch_hash is missing or malformed")
    try:
        computed_batch_hash = compute_manifest_batch_hash(manifest)
    except Exception as exc:
        raise ValueError(f"send manifest batch hash input is malformed: {exc}") from exc
    if computed_batch_hash != batch_hash:
        raise ValueError("send manifest batch_hash does not match its immutable scope")
    pdf_keys = [_clean(entry.get("pdf_key")) for entry in entries if isinstance(entry, dict)]
    if not pdf_keys or any(not key for key in pdf_keys) or len(pdf_keys) != len(set(pdf_keys)):
        raise ValueError("send manifest pdf_key scope is empty or ambiguous")
    batch_root = manifest_path.parent.resolve()
    for entry in entries:
        if not isinstance(entry, dict):
            raise ValueError("send manifest entry is malformed")
        entry_hash = _clean(entry.get("sha256"))
        if not _is_sha256(entry_hash):
            raise ValueError(f"send manifest PDF hash is malformed: {_clean(entry.get('pdf_key'))}")
        relative_path = _clean(entry.get("relative_output_path"))
        pdf_path = (batch_root / relative_path).resolve()
        try:
            pdf_path.relative_to(batch_root)
        except ValueError as exc:
            raise ValueError("send manifest PDF path escapes the batch root") from exc
        if not pdf_path.is_file():
            raise ValueError(f"send manifest PDF is missing: {relative_path}")
        if _file_sha256(pdf_path) != entry_hash:
            raise ValueError(f"send manifest PDF hash mismatch: {relative_path}")
    ledger_path = manifest_path.parent / SEND_LEDGER_FILE
    if not ledger_path.is_file():
        raise ValueError(f"send ledger missing for pinned manifest: {ledger_path}")

    gate = validate_manifest_against_expected(
        expected_path=Path(expected_orders_path),
        manifest_path=manifest_path,
    )
    if not gate.get("ok"):
        issues = ",".join(gate.get("issue_codes") or ["unknown_mismatch"])
        missing = ",".join(gate.get("missing_order_ids") or []) or "-"
        extra = ",".join(gate.get("extra_order_ids") or []) or "-"
        raise ValueError(
            "send manifest does not match required orders: "
            f"issues={issues}; missing={missing}; extra={extra}"
        )
    return {
        "manifest_path": str(manifest_path),
        "manifest_sha256": _file_sha256(manifest_path),
        "batch_hash": batch_hash,
        "obligation_scope_hash": _clean(manifest.get("obligation_scope_hash")),
        "line_scope_hash": _clean(manifest.get("line_scope_hash")),
        "ledger_path": str(ledger_path.resolve()),
        "pdf_scope_hash": _pdf_scope_hash(entries),
        "request_identity": dict(expected["request_identity"]),
        "expected_orders_path": str(Path(expected_orders_path).resolve()),
        "expected_orders_sha256": expected["sha256"],
    }


def _validate_pinned_manifest(pin: dict[str, Any], *, today_folder: Path) -> tuple[bool, str]:
    manifest_path = Path(str(pin.get("manifest_path") or "")).expanduser()
    expected_path = Path(str(pin.get("expected_orders_path") or "")).expanduser()
    if not manifest_path.is_file() or not expected_path.is_file():
        return False, "pinned_manifest_or_expected_orders_missing"
    try:
        refreshed = _pin_send_manifest(
            manifest_path=manifest_path,
            today_folder=today_folder,
            expected_orders_path=expected_path,
        )
    except Exception as exc:
        return False, f"pinned_manifest_invalid:{exc}"
    for key in (
        "manifest_sha256",
        "batch_hash",
        "obligation_scope_hash",
        "line_scope_hash",
        "ledger_path",
        "pdf_scope_hash",
        "expected_orders_sha256",
    ):
        if _clean(pin.get(key)) != _clean(refreshed.get(key)):
            return False, f"pinned_manifest_{key}_mismatch"
    if dict(pin.get("request_identity") or {}) != dict(refreshed.get("request_identity") or {}):
        return False, "pinned_manifest_request_identity_mismatch"
    return True, ""


def _pinned_delivery_attempt_evidence(pin: dict[str, Any]) -> tuple[bool, str]:
    """Detect any state proving a pinned batch may already have been delivered."""
    manifest_path = Path(str(pin.get("manifest_path") or "")).expanduser()
    primary_ledger_text = _clean(pin.get("ledger_path"))
    primary_ledger = Path(primary_ledger_text).expanduser() if primary_ledger_text else None
    if manifest_path.is_file() and (
        primary_ledger is None or not primary_ledger.is_file()
    ):
        return True, f"delivery_ledger_missing:{primary_ledger_text or '-'}"
    candidates = [
        primary_ledger,
        manifest_path.parent / "telegram_send_ledger.json",
    ]
    for ledger_path in candidates:
        if ledger_path is None or not ledger_path.is_file():
            continue
        try:
            payload = json.loads(ledger_path.read_text(encoding="utf-8"))
        except Exception as exc:
            return True, f"delivery_ledger_unreadable:{ledger_path}:{exc}"
        if not isinstance(payload, dict) or not isinstance(payload.get("entries"), dict):
            return True, f"delivery_ledger_malformed:{ledger_path}"
        for pdf_key, raw_entry in payload["entries"].items():
            if not isinstance(raw_entry, dict):
                return True, f"delivery_ledger_entry_malformed:{ledger_path}:{pdf_key}"
            entry = dict(raw_entry)
            state = _clean(entry.get("state")) or "pending"
            if state != "pending" or list(entry.get("history") or []):
                return True, f"delivery_attempt_evidence:{ledger_path}:{pdf_key}:{state}"
    return False, ""


def _checkpoint_delivery_may_have_been_attempted(
    checkpoint: dict[str, Any],
) -> bool:
    return bool(
        dict(checkpoint.get("delivery_attempt") or {})
        or dict((checkpoint.get("stages") or {}).get("delivery_send") or {})
    )


def _telegram_attempt_ledger_issue(pin: dict[str, Any]) -> str:
    manifest_path = Path(str(pin.get("manifest_path") or "")).expanduser()
    if not manifest_path.is_file():
        return "pinned_manifest_missing_after_attempt"
    telegram_ledger_path = manifest_path.parent / "telegram_send_ledger.json"
    if not telegram_ledger_path.is_file():
        return "telegram_send_ledger_missing_after_attempt"
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        ledger = json.loads(telegram_ledger_path.read_text(encoding="utf-8"))
    except Exception as exc:
        return f"telegram_send_ledger_unreadable_after_attempt:{type(exc).__name__}"
    if not isinstance(manifest, dict) or not isinstance(ledger, dict):
        return "telegram_send_ledger_malformed_after_attempt"
    ledger_entries = ledger.get("entries")
    if not isinstance(ledger_entries, dict):
        return "telegram_send_ledger_entries_malformed_after_attempt"
    batch_hash = _clean(manifest.get("batch_hash"))
    if not batch_hash or _clean(ledger.get("batch_hash")) != batch_hash:
        return "telegram_send_ledger_batch_hash_mismatch_after_attempt"
    pinned_chat_id = _clean(ledger.get("telegram_chat_id"))
    if not pinned_chat_id:
        return "telegram_send_ledger_target_missing_after_attempt"
    manifest_keys = {
        _clean(entry.get("pdf_key"))
        for entry in manifest.get("entries") or []
        if isinstance(entry, dict) and _clean(entry.get("pdf_key"))
    }
    if manifest_keys != set(ledger_entries):
        return "telegram_send_ledger_pdf_scope_mismatch_after_attempt"
    for pdf_key, raw_entry in ledger_entries.items():
        if not isinstance(raw_entry, dict):
            return f"telegram_send_ledger_entry_malformed_after_attempt:{pdf_key}"
        state = _clean(raw_entry.get("state")) or "pending"
        if state not in {"pending", "api_started", "confirmed", "failed", "unsure"}:
            return f"telegram_send_ledger_state_invalid_after_attempt:{pdf_key}:{state}"
        if not isinstance(raw_entry.get("history") or [], list):
            return f"telegram_send_ledger_history_invalid_after_attempt:{pdf_key}"
        if state == "confirmed" and _clean(raw_entry.get("telegram_chat_id")) != pinned_chat_id:
            return f"telegram_send_ledger_target_mismatch_after_attempt:{pdf_key}"
    return ""


def _validate_attempted_delivery_resume(
    *,
    checkpoint: dict[str, Any],
    today_folder: Path,
    target_date: date,
    run_root: Path,
) -> tuple[bool, str, dict[str, Any]]:
    """Never infer or recreate Telegram ledger state after a possible attempt."""
    if not _checkpoint_delivery_may_have_been_attempted(checkpoint):
        return True, "", {}
    pin = dict(checkpoint.get("delivery_artifacts") or {})
    manifest_path = Path(str(pin.get("manifest_path") or "")).expanduser()
    telegram_ledger_path = manifest_path.parent / "telegram_send_ledger.json"
    if not telegram_ledger_path.is_file():
        return False, "telegram_send_ledger_missing_after_attempt", {
            "manifest_path": str(manifest_path),
            "telegram_ledger_path": str(telegram_ledger_path),
        }
    attempt = dict(checkpoint.get("delivery_attempt") or {})
    stage = dict((checkpoint.get("stages") or {}).get("delivery_send") or {})
    state = delivery_completion_state(
        today_folder=Path(today_folder),
        target_date=target_date,
        run_root=Path(run_root),
        run_id=_clean(attempt.get("run_id") or stage.get("run_id")),
        manifest_path=manifest_path,
        expected_manifest_sha256=_clean(pin.get("manifest_sha256")),
    )
    if _clean(state.get("status")) not in {
        "TELEGRAM_LEDGER_INCOMPLETE",
        "TELEGRAM_CONFIRMED",
    }:
        return False, f"telegram_send_ledger_invalid_after_attempt:{_clean(state.get('status'))}", state
    return True, "", state


def _request_delivery_attempt_evidence(
    *,
    today_folder: Path,
    request_identity: dict[str, str],
    checkpoint: dict[str, Any] | None = None,
) -> list[dict[str, str]]:
    """Find prior send attempts for the READY request's target date.

    This protects exact-once behavior if the day checkpoint is lost or a new
    READY identity is stamped after an earlier same-day attempt. A manifest
    alone is not proof of a send, but any non-pending ledger state or history
    means an API call may already have happened and rebuilding must stop unless
    the exact attempted manifest is still checkpoint-pinned and resumable.
    """
    expected_identity = {
        "target_date": _clean(request_identity.get("target_date")),
        "ready_set_at": _clean(request_identity.get("ready_set_at")),
    }
    if not all(expected_identity.values()):
        return []

    attempts: list[dict[str, str]] = []
    checkpoint_state = dict(checkpoint or {})
    checkpoint_attempt_paths: set[Path] = set()
    if _checkpoint_delivery_may_have_been_attempted(checkpoint_state):
        for raw_path in (
            (checkpoint_state.get("delivery_attempt") or {}).get("manifest_path"),
            (checkpoint_state.get("delivery_artifacts") or {}).get("manifest_path"),
        ):
            if _clean(raw_path):
                checkpoint_attempt_paths.add(Path(str(raw_path)).expanduser().resolve())
    send_root = Path(today_folder).expanduser() / "MERGED" / "SEND"
    batch_roots = sorted(
        (path for path in send_root.iterdir() if path.is_dir()),
        key=str,
    ) if send_root.is_dir() else []
    for batch_root in batch_roots:
        manifest_path = batch_root / "send_batch_manifest.json"
        checkpoint_marks_attempt = manifest_path.resolve() in checkpoint_attempt_paths
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            if not isinstance(manifest, dict):
                raise ValueError("manifest is not an object")
        except Exception as exc:
            attempted, reason = _pinned_delivery_attempt_evidence(
                {
                    "manifest_path": str(manifest_path),
                    "ledger_path": str(batch_root / SEND_LEDGER_FILE),
                }
            )
            if checkpoint_marks_attempt and not attempted:
                attempted = True
                reason = "checkpoint_delivery_attempt_marker_present"
            if attempted:
                attempts.append(
                    {
                        "manifest_path": str(manifest_path.resolve()),
                        "reason": f"orphan_or_unreadable_manifest:{exc}:{reason}",
                    }
                )
            continue
        observed_identity = {
            "target_date": _clean(
                (manifest.get("request_identity") or {}).get("target_date")
                or manifest.get("target_date")
            ),
            "ready_set_at": _clean(
                (manifest.get("request_identity") or {}).get("ready_set_at")
                or manifest.get("ready_set_at")
            ),
        }
        if observed_identity["target_date"] != expected_identity["target_date"]:
            continue
        candidate_pin = {
            "manifest_path": str(manifest_path),
            "ledger_path": str(manifest_path.parent / SEND_LEDGER_FILE),
        }
        if checkpoint_marks_attempt:
            attempted = True
            reason = _telegram_attempt_ledger_issue(candidate_pin) or (
                "checkpoint_delivery_attempt_marker_present"
            )
        else:
            attempted, reason = _pinned_delivery_attempt_evidence(candidate_pin)
        if attempted:
            attempts.append(
                {
                    "manifest_path": str(manifest_path.resolve()),
                    "reason": reason,
                    "target_date": observed_identity["target_date"],
                    "ready_set_at": observed_identity["ready_set_at"],
                    "request_identity_match": str(
                        observed_identity == expected_identity
                    ).lower(),
                }
            )
    return attempts


def _guard_request_delivery_attempt_binding(
    *,
    checkpoint: dict[str, Any],
    completed_stages: list[str],
    today_folder: Path,
    request_identity: dict[str, str],
) -> tuple[bool, str, list[dict[str, str]]]:
    attempts = _request_delivery_attempt_evidence(
        today_folder=today_folder,
        request_identity=request_identity,
        checkpoint=checkpoint,
    )
    if not attempts:
        return True, "", []
    if any(item.get("request_identity_match") != "true" for item in attempts):
        return False, "same_date_prior_attempt_different_request", attempts
    if len(attempts) != 1:
        return False, "multiple_attempted_manifests", attempts

    delivery_pin = dict(checkpoint.get("delivery_artifacts") or {})
    if not delivery_pin:
        return False, "delivery_pin_missing", attempts
    pin_ok, pin_reason = _validate_pinned_manifest(
        delivery_pin,
        today_folder=today_folder,
    )
    if not pin_ok:
        return False, f"delivery_pin_invalid:{pin_reason}", attempts
    pinned_path = Path(str(delivery_pin.get("manifest_path") or "")).expanduser().resolve()
    attempted_path = Path(attempts[0]["manifest_path"]).resolve()
    if pinned_path != attempted_path:
        return False, "attempted_manifest_not_pinned", attempts
    if "build_waybills" not in completed_stages:
        return False, "build_stage_not_resumable", attempts
    return True, "", attempts


def _fetch_prior_obligation_details(
    *,
    ledger: dict[str, Any],
    current_active_order_ids_by_store: dict[str, set[str]],
    target_date: date | None = None,
    stats_out: dict[str, Any] | None = None,
) -> dict[str, dict[str, Any]]:
    started = time.monotonic()
    limits = _resolved_obligation_detail_limits()
    max_open = int(limits["max_open"])
    max_exact_reads = int(limits["max_exact_reads"])
    max_pages_per_state = int(limits["max_pages_per_state"])
    max_seconds = float(limits["max_seconds"])
    bulk_threshold = int(limits["bulk_threshold"])
    results: dict[str, dict[str, Any]] = {}
    entries = dict(ledger.get("entries") or {})
    clients: dict[str, KaspiAPIClient] = {}
    keys = list(open_obligation_keys_needing_detail(ledger, current_active_order_ids_by_store))
    stats: dict[str, Any] = {
        "candidate_count": len(keys),
        "bulk_read_count": 0,
        "exact_read_count": 0,
        "resolved_count": 0,
        "budget_exhausted": False,
        "budget_exhausted_names": [],
        "max_open": max_open,
        "max_exact_reads": max_exact_reads,
        "max_pages_per_state": max_pages_per_state,
        "max_seconds": max_seconds,
        "bulk_threshold": bulk_threshold,
        "bulk_page_high_watermark": 0,
        "bulk_errors": [],
    }
    emitted_alert_levels: set[tuple[str, str]] = set()

    def _publish_stats() -> None:
        stats["resolved_count"] = sum(1 for value in results.values() if "order" in value)
        stats["elapsed_seconds"] = round(time.monotonic() - started, 3)
        _enqueue_obligation_budget_alerts(
            target_date=target_date,
            stats=stats,
            emitted_alert_levels=emitted_alert_levels,
        )
        if stats_out is not None:
            stats_out.clear()
            stats_out.update(stats)

    if len(keys) > max_open:
        stats["budget_exhausted"] = True
        stats["budget_exhausted_names"].append("max_open")
        for key in keys:
            results[str(key)] = {
                "error": (
                    "obligation detail open-set budget exhausted: "
                    f"{len(keys)} > {max_open}"
                )
            }
        _publish_stats()
        return results

    unresolved_by_store: dict[str, list[tuple[str, str]]] = {}
    for key in keys:
        entry = dict(entries.get(key) or {})
        store_code = _clean(entry.get("store_code")).upper().replace("STORE-B", "STOREB")
        order_id = _clean(entry.get("order_id"))
        canonical_key = obligation_key(store_code, order_id) if store_code and order_id else str(key)
        if not store_code or not order_id:
            results[canonical_key] = {"error": "obligation identity is incomplete"}
            continue
        unresolved_by_store.setdefault(store_code, []).append((canonical_key, order_id))

    if target_date is not None:
        since = (target_date - timedelta(days=13)).isoformat()
        until = target_date.isoformat()
        for store_code, identities in sorted(unresolved_by_store.items()):
            if len(identities) < bulk_threshold:
                continue
            try:
                client = clients.get(store_code)
                if client is None:
                    client = KaspiAPIClient(store_code=store_code)
                    clients[store_code] = client
                wanted = {order_id for _key, order_id in identities}
                for state in ("KASPI_DELIVERY", "ARCHIVE"):
                    if time.monotonic() - started >= max_seconds:
                        stats["budget_exhausted"] = True
                        if "max_seconds" not in stats["budget_exhausted_names"]:
                            stats["budget_exhausted_names"].append("max_seconds")
                        break
                    orders = client.list_all_orders(
                        state=state,
                        since=since,
                        until=until,
                        max_pages=max_pages_per_state,
                        raise_on_error=True,
                    )
                    stats["bulk_read_count"] += 1
                    pages_consumed = max(1, math.ceil(len(orders) / 100))
                    stats["bulk_page_high_watermark"] = max(
                        int(stats["bulk_page_high_watermark"]),
                        pages_consumed,
                    )
                    for order in orders:
                        if not isinstance(order, dict):
                            continue
                        attrs = order.get("attributes") if isinstance(order.get("attributes"), dict) else order
                        observed_id = _clean(attrs.get("code") or attrs.get("orderCode"))
                        if observed_id not in wanted:
                            continue
                        results[obligation_key(store_code, observed_id)] = {"order": order}
            except Exception as exc:
                error_text = f"{type(exc).__name__}: {exc}"
                if "exceeds safety limit" in str(exc) or "exceeded safety limit" in str(exc):
                    stats["budget_exhausted"] = True
                    if "max_pages_per_state" not in stats["budget_exhausted_names"]:
                        stats["budget_exhausted_names"].append("max_pages_per_state")
                    stats["bulk_page_high_watermark"] = max_pages_per_state
                stats["bulk_errors"].append(
                    {"store_code": store_code, "error": error_text}
                )

    for store_code, identities in sorted(unresolved_by_store.items()):
        for canonical_key, order_id in identities:
            if canonical_key in results:
                continue
            if (
                int(stats["exact_read_count"]) >= max_exact_reads
                or time.monotonic() - started >= max_seconds
            ):
                stats["budget_exhausted"] = True
                if int(stats["exact_read_count"]) >= max_exact_reads:
                    if "max_exact_reads" not in stats["budget_exhausted_names"]:
                        stats["budget_exhausted_names"].append("max_exact_reads")
                if time.monotonic() - started >= max_seconds:
                    if "max_seconds" not in stats["budget_exhausted_names"]:
                        stats["budget_exhausted_names"].append("max_seconds")
                results[canonical_key] = {
                    "error": "obligation detail exact-read budget exhausted"
                }
                continue
            try:
                client = clients.get(store_code)
                if client is None:
                    client = KaspiAPIClient(store_code=store_code)
                    clients[store_code] = client
                stats["exact_read_count"] += 1
                response = client.get_order(order_id)
                if not response.success:
                    results[canonical_key] = {"error": str(response.error or "exact API read failed")}
                elif not isinstance(response.data, dict):
                    results[canonical_key] = {"error": "exact API read returned a malformed payload"}
                else:
                    results[canonical_key] = {"order": response.data}
            except Exception as exc:
                results[canonical_key] = {"error": f"{type(exc).__name__}: {exc}"}
    _publish_stats()
    return results


def _seed_obligation_ledger(
    ledger: dict[str, Any],
    candidates_by_store: dict[str, set[str]],
    *,
    target_date: date,
) -> dict[str, Any]:
    entries = ledger.setdefault("entries", {})
    for store_code, order_ids in sorted(candidates_by_store.items()):
        for order_id in sorted(order_ids):
            key = obligation_key(store_code, order_id)
            if key in entries:
                continue
            entries[key] = {
                "store_code": store_code,
                "order_id": order_id,
                "status": "unresolved",
                "first_seen_target_date": target_date.isoformat(),
                "last_seen_target_date": target_date.isoformat(),
                "last_stage": "DB_BOOTSTRAP_REQUIRES_EXACT_READ",
            }
    return ledger


def _scope_obligation_ledger(
    ledger: dict[str, Any],
    allowed_store_codes: list[str],
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Return an in-scope copy plus preserved out-of-scope ledger entries."""
    allowed = {normalize_store_code(value) for value in allowed_store_codes}
    scoped = copy.deepcopy(ledger)
    scoped_entries: dict[str, Any] = {}
    preserved_entries: dict[str, Any] = {}
    for key, raw_entry in dict(ledger.get("entries") or {}).items():
        entry = dict(raw_entry or {})
        store_code = normalize_store_code(entry.get("store_code"))
        destination = scoped_entries if store_code in allowed else preserved_entries
        destination[str(key)] = copy.deepcopy(raw_entry)
    scoped["entries"] = scoped_entries
    return scoped, preserved_entries


def _merge_scoped_obligation_ledger(
    scoped_ledger: dict[str, Any],
    preserved_entries: dict[str, Any],
) -> dict[str, Any]:
    merged = copy.deepcopy(scoped_ledger)
    entries = copy.deepcopy(preserved_entries)
    entries.update(copy.deepcopy(dict(scoped_ledger.get("entries") or {})))
    merged["entries"] = dict(sorted(entries.items()))
    return merged


def _positive_int_env(name: str, default: int) -> int:
    raw = _clean(os.environ.get(name))
    if not raw:
        return default
    try:
        value = int(raw)
        if value <= 0:
            raise ValueError
    except ValueError:
        warning_key = (name, raw)
        if warning_key not in _INVALID_ENV_WARNINGS_EMITTED:
            print(
                f"WARN: invalid {name}; using default {default}.",
                file=sys.stderr,
            )
            _INVALID_ENV_WARNINGS_EMITTED.add(warning_key)
        return default
    return value


def _positive_float_env(name: str, default: float) -> float:
    raw = _clean(os.environ.get(name))
    if not raw:
        return default
    try:
        value = float(raw)
        if value <= 0:
            raise ValueError
    except ValueError:
        warning_key = (name, raw)
        if warning_key not in _INVALID_ENV_WARNINGS_EMITTED:
            print(
                f"WARN: invalid {name}; using default {default}.",
                file=sys.stderr,
            )
            _INVALID_ENV_WARNINGS_EMITTED.add(warning_key)
        return default
    return value


def _resolved_obligation_detail_limits() -> dict[str, int | float]:
    return {
        "max_open": _positive_int_env(
            OBLIGATION_DETAIL_MAX_OPEN_ENV,
            OBLIGATION_DETAIL_MAX_OPEN,
        ),
        "max_exact_reads": _positive_int_env(
            OBLIGATION_DETAIL_MAX_EXACT_READS_ENV,
            OBLIGATION_DETAIL_MAX_EXACT_READS,
        ),
        "max_pages_per_state": _positive_int_env(
            OBLIGATION_DETAIL_MAX_PAGES_PER_STATE_ENV,
            OBLIGATION_DETAIL_MAX_PAGES_PER_STATE,
        ),
        "max_seconds": _positive_float_env(
            OBLIGATION_DETAIL_MAX_SECONDS_ENV,
            OBLIGATION_DETAIL_MAX_SECONDS,
        ),
        "bulk_threshold": _positive_int_env(
            OBLIGATION_DETAIL_BULK_THRESHOLD_ENV,
            OBLIGATION_DETAIL_BULK_THRESHOLD,
        ),
    }


def _resolved_stage_timeout_seconds(name: str) -> int:
    default = int(STAGE_TIMEOUT_SECONDS.get(name, 10 * 60))
    if name not in ENV_TUNABLE_STAGE_TIMEOUTS:
        return default
    env_name = f"AB_CLOSEOUT_STAGE_TIMEOUT_{name.upper()}"
    return _positive_int_env(env_name, default)


def _enqueue_obligation_budget_alerts(
    *,
    target_date: date | None,
    stats: Mapping[str, Any],
    emitted_alert_levels: set[tuple[str, str]],
) -> None:
    if target_date is None:
        return
    exhausted_names = {
        str(value) for value in stats.get("budget_exhausted_names") or []
    }
    budgets = {
        "max_open": (
            float(stats.get("candidate_count") or 0),
            float(stats.get("max_open") or OBLIGATION_DETAIL_MAX_OPEN),
        ),
        "max_exact_reads": (
            float(stats.get("exact_read_count") or 0),
            float(stats.get("max_exact_reads") or OBLIGATION_DETAIL_MAX_EXACT_READS),
        ),
        "max_pages_per_state": (
            float(stats.get("bulk_page_high_watermark") or 0),
            float(
                stats.get("max_pages_per_state")
                or OBLIGATION_DETAIL_MAX_PAGES_PER_STATE
            ),
        ),
        "max_seconds": (
            float(stats.get("elapsed_seconds") or 0),
            float(stats.get("max_seconds") or OBLIGATION_DETAIL_MAX_SECONDS),
        ),
    }
    target_iso = target_date.isoformat()
    for budget_name, (consumed, limit) in budgets.items():
        if limit <= 0:
            continue
        percent = consumed / limit
        if percent >= OBLIGATION_BUDGET_WARNING_FRACTION:
            alert_key = ("WARN", budget_name)
            if alert_key not in emitted_alert_levels:
                enqueue_alert(
                    title="Google Ops Board obligation budget at 80%",
                    lines=[
                        f"Target date: {target_iso}",
                        f"Budget: {budget_name}",
                        f"Consumption: {consumed:g} / {limit:g} ({percent:.0%})",
                    ],
                    severity="WARN",
                    dedup_key=f"closeout_obligation_budget_warn:{target_iso}:{budget_name}",
                    dedup_window=OBLIGATION_BUDGET_ALERT_DEDUP_WINDOW,
                )
                emitted_alert_levels.add(alert_key)
        if budget_name in exhausted_names:
            alert_key = ("CRITICAL", budget_name)
            if alert_key not in emitted_alert_levels:
                enqueue_alert(
                    title="Google Ops Board obligation budget exhausted",
                    lines=[
                        f"Target date: {target_iso}",
                        f"Budget: {budget_name}",
                        f"Consumption: {consumed:g} / {limit:g}",
                        "Closeout retained unresolved obligations and failed closed.",
                    ],
                    severity="CRITICAL",
                    dedup_key=(
                        f"closeout_obligation_budget_critical:{target_iso}:{budget_name}"
                    ),
                    dedup_window=OBLIGATION_BUDGET_ALERT_DEDUP_WINDOW,
                )
                emitted_alert_levels.add(alert_key)


def _existing_open_orders_present_in_current(
    ledger: dict[str, Any],
    current_active_order_ids_by_store: dict[str, set[str]],
) -> dict[str, set[str]]:
    existing_open: dict[str, set[str]] = {}
    for raw_entry in dict(ledger.get("entries") or {}).values():
        entry = dict(raw_entry or {})
        if _clean(entry.get("status")) not in {"unresolved", "suspended"}:
            continue
        store_code = normalize_store_code(entry.get("store_code"))
        order_id = _clean(entry.get("order_id"))
        if store_code and order_id:
            existing_open.setdefault(store_code, set()).add(order_id)
    present: dict[str, set[str]] = {}
    for raw_store_code, raw_order_ids in current_active_order_ids_by_store.items():
        store_code = normalize_store_code(raw_store_code)
        order_ids = {_clean(order_id) for order_id in raw_order_ids if _clean(order_id)}
        matches = order_ids & existing_open.get(store_code, set())
        if matches:
            present[store_code] = matches
    return {store: set(order_ids) for store, order_ids in sorted(present.items())}


def _union_order_ids_by_store(
    *values: dict[str, set[str]],
) -> dict[str, set[str]]:
    result: dict[str, set[str]] = {}
    for value in values:
        for raw_store_code, raw_order_ids in value.items():
            store_code = normalize_store_code(raw_store_code)
            if not store_code:
                continue
            result.setdefault(store_code, set()).update(
                _clean(order_id) for order_id in raw_order_ids if _clean(order_id)
            )
    return {store: set(order_ids) for store, order_ids in sorted(result.items())}


def _apply_store_day_state_scope(
    required_ids_by_store: dict[str, set[str]],
    *,
    target_date: date,
    checkpoint_path: Path,
    report_path: Path,
) -> tuple[dict[str, set[str]], dict[str, Any]]:
    """Subtract stores explicitly fulfilled manually or postponed for this day."""
    raw_section = load_store_day_states(
        target_date,
        checkpoint_path=checkpoint_path,
    )
    effective_states = effective_store_states(
        target_date,
        checkpoint_path=checkpoint_path,
    )
    scoped = {
        store: set(order_ids)
        for store, order_ids in required_ids_by_store.items()
    }
    excluded_ids_by_store: dict[str, list[str]] = {}
    counts_before = {
        store: len(order_ids)
        for store, order_ids in sorted(scoped.items())
    }
    for store, order_ids in list(scoped.items()):
        normalized_store = normalize_store_code(store)
        state = str(
            (effective_states.get(normalized_store) or {}).get("state") or "PENDING"
        )
        if state not in {"MANUAL_FULFILLED", "POSTPONED"}:
            continue
        excluded_ids_by_store[normalized_store] = sorted(order_ids)
        scoped[store] = set()
        print(
            "STORE_DAY_STATE_SCOPE "
            f"store={normalized_store} state={state} "
            f"required_before={len(order_ids)} required_after=0"
        )
    if not excluded_ids_by_store:
        print(
            "STORE_DAY_STATE_SCOPE no-op "
            f"target_date={target_date.isoformat()} section_present={bool(raw_section)}"
        )
    report_payload = {
        "schema_version": 1,
        "target_date": target_date.isoformat(),
        "checkpoint_path": str(checkpoint_path),
        "section_present": bool(raw_section),
        "applied": bool(excluded_ids_by_store),
        "effective_store_states": effective_states,
        "excluded_states": ["MANUAL_FULFILLED", "POSTPONED"],
        "excluded_ids_by_store": excluded_ids_by_store,
        "counts_before": counts_before,
        "counts_after": {
            store: len(order_ids)
            for store, order_ids in sorted(scoped.items())
        },
    }
    dump_json(report_path, report_payload)
    return scoped, report_payload


def _manifest_store_codes(manifest_path: Path) -> list[str]:
    payload = json.loads(Path(manifest_path).read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("send manifest must be a JSON object")
    stores: set[str] = set()
    for raw_entry in payload.get("entries") or []:
        if not isinstance(raw_entry, dict):
            continue
        counts = raw_entry.get("order_counts_by_store")
        if isinstance(counts, dict) and counts:
            stores.update(
                normalize_store_code(raw_store)
                for raw_store in counts
                if normalize_store_code(raw_store)
            )
            continue
        for raw_line in raw_entry.get("source_lines") or []:
            if not isinstance(raw_line, dict):
                continue
            raw_store = (
                raw_line.get("store_code")
                or raw_line.get("store")
                or raw_line.get("store_name")
            )
            store = normalize_store_code(raw_store)
            if store:
                stores.add(store)
    return sorted(stores)


def _stamp_manifest_stores_auto_sent(
    *,
    manifest_path: Path,
    target_date: date,
    checkpoint_path: Path,
) -> dict[str, Any]:
    """Best-effort AUTO_SENT stamps after a confirmed delivery stage."""
    result: dict[str, Any] = {
        "manifest_path": str(manifest_path),
        "stores": [],
        "stamped": [],
        "errors": [],
    }
    try:
        result["stores"] = _manifest_store_codes(manifest_path)
    except Exception as exc:
        result["errors"].append(
            f"manifest_store_read_failed:{type(exc).__name__}:{exc}"
        )
        print(
            "WARNING: unable to stamp AUTO_SENT day states: "
            f"{result['errors'][-1]}",
            file=sys.stderr,
        )
        return result
    for store in result["stores"]:
        try:
            set_store_day_state(
                target_date,
                store,
                "AUTO_SENT",
                reason="delivery_send stage confirmed",
                set_by="run_google_ops_board_closeout",
                checkpoint_path=checkpoint_path,
            )
        except Exception as exc:
            result["errors"].append(
                f"{store}:{type(exc).__name__}:{exc}"
            )
            print(
                "WARNING: AUTO_SENT day-state stamp failed "
                f"store={store}: {type(exc).__name__}: {exc}",
                file=sys.stderr,
            )
            continue
        result["stamped"].append(store)
        print(f"STORE_DAY_STATE_AUTO_SENT store={store}")
    return result


def _register_current_obligations_after_success(
    ledger: dict[str, Any],
    current_active_order_ids_by_store: dict[str, set[str]],
    *,
    target_date: date,
    ready_set_at: str,
    now: datetime,
) -> dict[str, Any]:
    registered = copy.deepcopy(ledger)
    entries = registered.setdefault("entries", {})
    target_iso = target_date.isoformat()
    now_iso = now.isoformat()
    for raw_store_code, raw_order_ids in sorted(current_active_order_ids_by_store.items()):
        store_code = normalize_store_code(raw_store_code)
        for raw_order_id in sorted(raw_order_ids):
            order_id = _clean(raw_order_id)
            if not store_code or not order_id:
                continue
            key = obligation_key(store_code, order_id)
            entry = dict(entries.get(key) or {})
            entry.update(
                {
                    "store_code": store_code,
                    "order_id": order_id,
                    "status": "unresolved",
                    "first_seen_target_date": _clean(
                        entry.get("first_seen_target_date")
                    )
                    or target_iso,
                    "last_seen_target_date": target_iso,
                    "last_checked_at": now_iso,
                    "last_stage": "SHIPPING_STAGE_CONFIRMED",
                    "last_api_error": "",
                    "discharged_at": "",
                    "discharge_reason": "",
                }
            )
            entries[key] = entry
    registered.update(
        {
            "schema_version": 1,
            "updated_at": now_iso,
            "request_identity": {
                "target_date": target_iso,
                "ready_set_at": _clean(ready_set_at),
            },
            "entries": dict(sorted(entries.items())),
        }
    )
    return registered


def _resolve_db_bootstrap_hints(
    *,
    prior_ledger: dict[str, Any],
    candidates_by_store: dict[str, set[str]],
    current_active_order_ids_by_store: dict[str, set[str]],
    target_date: date,
    ready_set_at: str,
) -> dict[str, Any]:
    """Source-confirm legacy DB hints before they can become obligations.

    A raw historical DB row is not source authority. Failed or uncertain exact
    reads remain quarantined in evidence and block closeout so they cannot be
    silently omitted. Previously source-confirmed obligations remain in
    ``prior_ledger`` and retain the same fail-closed behavior.
    """
    prior_keys = set(dict(prior_ledger.get("entries") or {}))
    hint_candidates: dict[str, set[str]] = {}
    for store_code, order_ids in sorted(candidates_by_store.items()):
        for order_id in sorted(order_ids):
            key = obligation_key(store_code, order_id)
            if key in prior_keys or order_id in current_active_order_ids_by_store.get(
                normalize_store_code(store_code), set()
            ):
                continue
            hint_candidates.setdefault(normalize_store_code(store_code), set()).add(order_id)

    hint_ledger = {
        "schema_version": 1,
        "updated_at": None,
        "request_identity": {},
        "entries": {},
    }
    _seed_obligation_ledger(hint_ledger, hint_candidates, target_date=target_date)
    if not hint_candidates:
        return {
            "ok": True,
            "ledger": prior_ledger,
            "candidate_count": 0,
            "exact_detail_read_count": 0,
            "promoted_keys": [],
            "terminal_audit_keys": [],
            "quarantined": [],
        }

    detail_stats: dict[str, Any] = {}
    detail_results = _fetch_prior_obligation_details(
        ledger=hint_ledger,
        current_active_order_ids_by_store={},
        target_date=target_date,
        stats_out=detail_stats,
    )
    hint_result = reconcile_shipping_obligations(
        prior_ledger=hint_ledger,
        current_active_order_ids_by_store={},
        detail_results=detail_results,
        target_date=target_date,
        ready_set_at=ready_set_at,
        now=datetime.now(ALMATY_TZ),
    )
    issue_by_key = {
        str(issue.get("key") or ""): dict(issue)
        for issue in hint_result.get("issues") or []
    }
    merged = copy.deepcopy(prior_ledger)
    merged_entries = merged.setdefault("entries", {})
    promoted_keys: list[str] = []
    terminal_audit_keys: list[str] = []
    quarantined: list[dict[str, Any]] = []
    for key, raw_entry in sorted(dict(hint_result["ledger"].get("entries") or {}).items()):
        entry = dict(raw_entry or {})
        if key in issue_by_key or _clean(entry.get("last_api_error")):
            quarantined.append(
                {
                    "key": key,
                    "issue": issue_by_key.get(key) or {},
                    "last_api_error": _clean(entry.get("last_api_error")),
                }
            )
            continue
        status = _clean(entry.get("status"))
        if status in {"unresolved", "suspended"}:
            merged_entries[key] = entry
            promoted_keys.append(key)
        elif status == "discharged":
            merged_entries[key] = entry
            terminal_audit_keys.append(key)
    merged["entries"] = dict(sorted(merged_entries.items()))
    return {
        "ok": not quarantined,
        "ledger": merged,
        "candidate_count": sum(len(values) for values in hint_candidates.values()),
        "exact_detail_read_count": int(detail_stats.get("exact_read_count") or 0),
        "detail_resolution": detail_stats,
        "promoted_keys": promoted_keys,
        "terminal_audit_keys": terminal_audit_keys,
        "quarantined": quarantined,
    }


def _expected_orders_by_store(payload: dict[str, Any]) -> dict[str, set[str]]:
    result: dict[str, set[str]] = {}
    for row in payload.get("orders") or []:
        if not isinstance(row, dict):
            continue
        store = _clean(row.get("store_code")).upper().replace("STORE-B", "STOREB")
        order_id = _clean(row.get("order_id"))
        if store and order_id:
            result.setdefault(store, set()).add(order_id)
    return result


def _required_orders_checkpoint_valid(
    checkpoint: dict[str, Any],
    *,
    target_date: date,
) -> tuple[bool, str]:
    state = dict(checkpoint.get("required_orders") or {})
    path = Path(str(state.get("path") or "")).expanduser()
    if not path.is_file():
        return False, "checkpoint_required_orders_missing"
    try:
        loaded = load_required_orders_file(path, target_date=target_date)
    except Exception as exc:
        return False, f"checkpoint_required_orders_invalid:{exc}"
    if _clean(state.get("sha256")) != loaded["sha256"]:
        return False, "checkpoint_required_orders_sha256_mismatch"
    if dict(state.get("request_identity") or {}) != dict(loaded["request_identity"]):
        return False, "checkpoint_required_orders_request_identity_mismatch"
    if _clean(state.get("line_scope_hash")) != _clean(loaded.get("line_scope_hash")):
        return False, "checkpoint_required_orders_line_scope_hash_mismatch"
    return True, ""


def _required_orders_db_pin_valid(
    checkpoint: dict[str, Any],
    *,
    db_path: Path,
    target_date: date,
) -> tuple[bool, str]:
    """Re-read all pinned orders and prove exact DB line/size scope is unchanged."""
    state = dict(checkpoint.get("required_orders") or {})
    path = Path(str(state.get("path") or "")).expanduser()
    try:
        pinned = load_required_orders_file(path, target_date=target_date)
    except Exception as exc:
        return False, f"checkpoint_required_orders_invalid:{exc}"
    validation = validate_required_orders_against_db(
        required_orders=pinned,
        db_path=db_path,
        target_date=target_date,
    )
    if not validation.get("ok"):
        return False, "checkpoint_" + ",".join(validation.get("issues") or ["required_orders_db_invalid"])
    return True, ""


def _build_checkpoint_base(
    *,
    target_date: date,
    db_path: Path,
    spreadsheet_id: str,
    service_account_json: Path,
    run_control_row: dict[str, Any],
    salesraw_rows: list[dict[str, Any]],
    execution_mode: str,
) -> dict[str, Any]:
    return {
        "execution_mode": execution_mode,
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
    execution_mode: str,
) -> tuple[bool, str]:
    expected = {
        "execution_mode": execution_mode,
        "target_date": target_date.isoformat(),
        "db_path": str(db_path.resolve()),
        "spreadsheet_id": spreadsheet_id,
        "service_account_json": str(service_account_json.resolve()),
    }
    for key, value in expected.items():
        if str(checkpoint.get(key) or "") != value:
            return False, f"checkpoint_{key}_mismatch"
    return True, ""


def _rebase_checkpoint_for_ready_request(
    *,
    checkpoint: dict[str, Any],
    fresh_checkpoint: dict[str, Any],
    run_control_row: dict[str, Any],
) -> tuple[dict[str, Any], str, str]:
    """Reset stale stage state for a new READY request unless delivery was attempted."""
    saved_fingerprint = str(checkpoint.get("run_control_resume_fingerprint") or "")
    current_fingerprint = run_control_resume_fingerprint(run_control_row)
    if not saved_fingerprint or saved_fingerprint == current_fingerprint:
        return checkpoint, "", ""
    if _checkpoint_delivery_may_have_been_attempted(checkpoint):
        ledger_issue = _telegram_attempt_ledger_issue(
            dict(checkpoint.get("delivery_artifacts") or {})
        )
        return (
            checkpoint,
            "",
            "checkpoint_previous_request_delivery_attempt_present:"
            f"{ledger_issue or 'checkpoint_delivery_attempt_marker_present'}",
        )
    attempt_evidence, attempt_reason = _pinned_delivery_attempt_evidence(
        dict(checkpoint.get("delivery_artifacts") or {})
    )
    if attempt_evidence:
        return (
            checkpoint,
            "",
            "checkpoint_previous_request_delivery_attempt_present:"
            f"{attempt_reason}",
        )
    return copy.deepcopy(fresh_checkpoint), "new_ready_request_identity", ""


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
        "execution_mode": str(checkpoint.get("execution_mode") or ""),
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
    execution_mode: str,
) -> list[str]:
    if str(checkpoint.get("execution_mode") or "") != execution_mode:
        return []
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
        stage_mode = str(state.get("execution_mode") or "")
        if stage_mode and stage_mode != execution_mode:
            break
        step_report_path = Path(str(state.get("step_report_path") or "")).expanduser()
        if not step_report_path.exists():
            break
        if stage in {"shipping", "download_waybills", "build_waybills", "delivery_send"}:
            required_ok, _required_reason = _required_orders_checkpoint_valid(
                checkpoint,
                target_date=target_date or date.fromisoformat(str(checkpoint.get("target_date"))),
            )
            if not required_ok:
                break
        if stage in {"build_waybills", "delivery_send"}:
            manifest_ok, _manifest_reason = _validate_pinned_manifest(
                dict(checkpoint.get("delivery_artifacts") or {}),
                today_folder=Path(today_folder or DEFAULT_TODAY_FOLDER),
            )
            if not manifest_ok:
                break
        if stage == "delivery_send" and today_folder is not None and target_date is not None:
            manifest_path = Path(
                str((checkpoint.get("delivery_artifacts") or {}).get("manifest_path") or "")
            )
            delivery_state = delivery_completion_state(
                today_folder=Path(today_folder),
                target_date=target_date,
                run_root=Path(run_root),
                run_id=str(state.get("run_id") or ""),
                manifest_path=manifest_path,
                expected_manifest_sha256=_clean(
                    (checkpoint.get("delivery_artifacts") or {}).get("manifest_sha256")
                ),
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
    step_report["checkpoint_source"] = {
        "run_id": str(stage_state.get("run_id") or ""),
        "run_dir": str(stage_state.get("run_dir") or ""),
        "step_report_path": str(stage_state.get("step_report_path") or ""),
    }
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


def _enqueue_held_closeout_failure_alert(
    *,
    run_id: str,
    target_date: date,
    report_path: Path,
    stage: str,
    detail: str,
    barrier_reason: str,
) -> bool:
    return enqueue_alert(
        title="Google Ops Board Closeout Failed",
        lines=[
            f"Target date: {target_date.isoformat()}",
            f"Run ID: {run_id}",
            f"Stage: {stage}",
            f"Held by halt barrier: {barrier_reason}",
            detail,
            f"Report: {report_path}",
        ],
        severity="CRITICAL",
        dedup_key=f"closeout_failure:{run_id}:{stage}",
        held=True,
    )


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
    shadow_board_run_dir = getattr(args, "shadow_board_run_dir", None)
    if args.apply and shadow_board_run_dir:
        raise ValueError("--shadow-board-run-dir cannot be combined with --apply")
    db_path = Path(args.db_path).expanduser() if args.db_path else data_path("db", "app.db")
    service_account_json = resolve_service_account_json(args.service_account_json, contract=contract)
    spreadsheet_id = resolve_spreadsheet_id(args.spreadsheet_id, contract=contract)
    if shadow_board_run_dir:
        client, board_source = _load_preserved_board_client(
            Path(shadow_board_run_dir), target_date=target_date
        )
    else:
        client = GoogleOpsBoardClient.from_service_account_file(
            spreadsheet_id, service_account_json
        )
        board_source = {
            "board_source_mode": "live_google_board",
            "board_source_path": "",
            "source_apply_run_id": "",
        }
    execution_mode = "apply" if args.apply else "dry_run"
    if args.checkpoint_path:
        day_state_checkpoint_path = Path(args.checkpoint_path).expanduser()
    else:
        day_state_checkpoint_path = resolve_closeout_checkpoint_path(
            target_date,
            root=Path(args.run_root).expanduser(),
        )
    checkpoint_path = day_state_checkpoint_path
    if not args.checkpoint_path:
        if not args.apply:
            checkpoint_path = checkpoint_path.with_name("closeout_checkpoint_dry_run.json")

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
        "mode": execution_mode,
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
        **board_source,
    }

    run_control_matrix = client.get_tab_values("Run_Control")
    salesraw_matrix = client.get_tab_values("SalesRaw_Today")
    salesraw_rows = extract_rows_from_matrix(contract.tabs["SalesRaw_Today"].headers, salesraw_matrix)
    closeout_salesraw_rows, sync_disabled_skipped_rows = _filter_salesraw_to_sync_enabled_stores(
        salesraw_rows
    )
    storeb_excluded = load_storeb_packing_excluded(warn=lambda msg: print(msg, file=sys.stderr))
    closeout_salesraw_rows, fitpack_skipped_rows = _filter_storeb_salesraw_rows(
        closeout_salesraw_rows,
        enabled=storeb_excluded,
        context="closeout execution",
    )
    report_exclusion = {}
    if storeb_excluded:
        report_exclusion = {
            "fitpack_storeb_excluded": True,
            "fitpack_storeb_skipped_rows": fitpack_skipped_rows,
        }
    if sync_disabled_skipped_rows:
        report_exclusion["sync_disabled_store_rows_skipped"] = sync_disabled_skipped_rows
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
            "fitpack_filtered_rows": closeout_salesraw_rows,
            **report_exclusion,
        },
    )
    run_control_row = _select_run_control_row(
        extract_rows_from_matrix(contract.tabs["Run_Control"].headers, run_control_matrix),
        target_date,
    ) or {}
    fresh_checkpoint = _build_checkpoint_base(
        target_date=target_date,
        db_path=db_path,
        spreadsheet_id=spreadsheet_id,
        service_account_json=service_account_json,
        run_control_row=run_control_row,
        salesraw_rows=salesraw_rows,
        execution_mode=execution_mode,
    )
    recorded_day_states = load_store_day_states(
        target_date,
        checkpoint_path=day_state_checkpoint_path,
    )
    if recorded_day_states:
        fresh_checkpoint["store_day_states"] = recorded_day_states
    checkpoint = copy.deepcopy(fresh_checkpoint)

    expected_ready_set_at = _clean(getattr(args, "expected_ready_set_at", ""))
    observed_request_identity = {
        "target_date": _clean(run_control_row.get("target_date")),
        "ready_set_at": _clean(run_control_row.get("ready_set_at")),
    }

    def _fail_request_identity(reason: str) -> int:
        report["failure_stage"] = "request_identity"
        report["failure_reason"] = reason
        report["expected_ready_set_at"] = expected_ready_set_at
        report["observed_request_identity"] = observed_request_identity
        output_path = args.json_out or (run_dir / "closeout_report.json")
        dump_json(output_path, report)
        _write_daily_index_best_effort(
            target_date=target_date,
            run_root=Path(args.run_root).expanduser(),
        )
        print(f"Closeout blocked by READY request identity: {reason}")
        return 1

    def _read_live_request_identity() -> dict[str, str]:
        matrix = client.get_tab_values("Run_Control")
        row = _select_run_control_row(
            extract_rows_from_matrix(
                contract.tabs["Run_Control"].headers,
                matrix,
            ),
            target_date,
        ) or {}
        return {
            "target_date": _clean(row.get("target_date")),
            "ready_set_at": _clean(row.get("ready_set_at")),
            "ready_for_closeout": _clean(row.get("ready_for_closeout")).upper(),
        }

    def _halt_gate_for_row(row: dict[str, Any]) -> dict[str, Any]:
        return evaluate_closeout_halt_barrier(
            target_date=target_date,
            run_control_row=row,
            request_ready_set_at=expected_ready_set_at,
        )

    def _external_mutation_allowed(action: str) -> bool:
        """Re-read request and halt state immediately before an external mutation."""
        try:
            current = _read_live_request_identity()
        except Exception as exc:
            report.setdefault("halt_barrier_suppressed_mutations", []).append(
                {
                    "action": action,
                    "reason": f"RUN_CONTROL_READ_FAILED:{type(exc).__name__}",
                }
            )
            return False
        gate = _halt_gate_for_row(current)
        if not gate.get("blocked"):
            return True
        report.setdefault("halt_barrier_suppressed_mutations", []).append(
            {"action": action, "reason": _clean(gate.get("reason"))}
        )
        report["halt_barrier_stop"] = {
            "stage": action,
            "reason": _clean(gate.get("reason")),
            "external_failure_write_suppressed": True,
        }
        return False

    def _guarded_update_run_control_status(**kwargs: Any) -> bool:
        if not args.apply or not _external_mutation_allowed("run_control_status"):
            return False
        _update_run_control_status(**kwargs)
        return True

    def _guarded_send_closeout_alert(**kwargs: Any) -> bool:
        if not args.apply or not _external_mutation_allowed("closeout_alert"):
            return False
        _send_closeout_alert(**kwargs)
        return True

    if args.apply and not expected_ready_set_at:
        return _fail_request_identity("apply_requires_expected_ready_set_at")
    if expected_ready_set_at and (
        observed_request_identity["target_date"] != target_date.isoformat()
        or observed_request_identity["ready_set_at"] != expected_ready_set_at
        or _clean(run_control_row.get("ready_for_closeout")).upper() != "READY"
    ):
        return _fail_request_identity("run_control_request_identity_mismatch")
    if args.apply:
        initial_halt_gate = _halt_gate_for_row(run_control_row)
        report["halt_barrier_gate"] = {
            "blocked": bool(initial_halt_gate.get("blocked")),
            "reason": _clean(initial_halt_gate.get("reason")),
        }
        if initial_halt_gate["blocked"]:
            return _fail_request_identity(
                f"local_halt_barrier:{initial_halt_gate['reason']}"
            )

    readiness = build_readiness_report(
        client=client,
        contract=contract,
        db_path=db_path,
        target_date=target_date,
        lookback_days=args.lookback_days,
        storeb_excluded=storeb_excluded,
    )
    report.update(report_exclusion)
    report["ready"] = bool(readiness["ready"])
    dump_json(run_dir / "readiness_report.json", readiness)

    readiness_ready_set_at = _clean(readiness.get("ready_set_at"))
    if (
        readiness_ready_set_at != observed_request_identity["ready_set_at"]
        or (expected_ready_set_at and readiness_ready_set_at != expected_ready_set_at)
    ):
        return _fail_request_identity("ready_identity_changed_during_preflight")

    if args.apply:
        boundary_identity = _read_live_request_identity()
        boundary_halt_gate = _halt_gate_for_row(boundary_identity)
        if boundary_halt_gate["blocked"]:
            return _fail_request_identity(
                f"local_halt_barrier:{boundary_halt_gate['reason']}"
            )
        status_written = _guarded_update_run_control_status(
            client=client,
            contract=contract,
            target_date=target_date,
            run_id=run_id,
            status="READY" if readiness["ready"] else "BLOCKED",
            hold_on_failure=False,
        )
        if not status_written:
            reason = _clean(
                (report.get("halt_barrier_stop") or {}).get("reason")
            ) or "EXTERNAL_MUTATION_RECHECK_FAILED"
            return _fail_request_identity(f"local_halt_barrier:{reason}")

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
        if not _external_mutation_allowed("prewindow_health"):
            reason = _clean(
                (report.get("halt_barrier_stop") or {}).get("reason")
            ) or "EXTERNAL_MUTATION_RECHECK_FAILED"
            return _fail_request_identity(f"local_halt_barrier:{reason}")
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
            _guarded_update_run_control_status(
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
            _guarded_send_closeout_alert(
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
            execution_mode=execution_mode,
        )
        if not valid_checkpoint:
            report["failure_stage"] = "checkpoint"
            report["failure_reason"] = checkpoint_reason
            output_path = args.json_out or (run_dir / "closeout_report.json")
            dump_json(output_path, report)
            _write_daily_index_best_effort(target_date=target_date, run_root=Path(args.run_root).expanduser())
            if args.apply:
                _guarded_update_run_control_status(
                    client=client,
                    contract=contract,
                    target_date=target_date,
                    run_id=run_id,
                    status="FAILED_CHECKPOINT",
                    hold_on_failure=False,
                )
                _guarded_send_closeout_alert(
                    title="Google Ops Board Closeout Failed",
                    run_id=run_id,
                    target_date=target_date,
                    report_path=output_path,
                    stage="checkpoint",
                    detail=checkpoint_reason,
                )
            return 1
        checkpoint, reset_reason, request_change_block = _rebase_checkpoint_for_ready_request(
            checkpoint=saved_checkpoint,
            fresh_checkpoint=fresh_checkpoint,
            run_control_row=run_control_row,
        )
        if request_change_block:
            report["failure_stage"] = "checkpoint"
            report["failure_reason"] = request_change_block
            output_path = args.json_out or (run_dir / "closeout_report.json")
            dump_json(output_path, report)
            _write_daily_index_best_effort(
                target_date=target_date,
                run_root=Path(args.run_root).expanduser(),
            )
            if args.apply:
                _guarded_update_run_control_status(
                    client=client,
                    contract=contract,
                    target_date=target_date,
                    run_id=run_id,
                    status="FAILED_CHECKPOINT",
                    hold_on_failure=False,
                )
                _guarded_send_closeout_alert(
                    title="Google Ops Board Closeout Failed",
                    run_id=run_id,
                    target_date=target_date,
                    report_path=output_path,
                    stage="checkpoint",
                    detail=report["failure_reason"],
                )
            return 1
        if reset_reason:
            report["checkpoint_reset_reason"] = reset_reason
        delivery_pin = dict(checkpoint.get("delivery_artifacts") or {})
        if delivery_pin:
            delivery_pin_ok, delivery_pin_reason = _validate_pinned_manifest(
                delivery_pin,
                today_folder=Path(args.today_folder).expanduser(),
            )
            attempt_evidence, attempt_reason = _pinned_delivery_attempt_evidence(
                delivery_pin
            )
            if not delivery_pin_ok and attempt_evidence:
                report["failure_stage"] = "checkpoint"
                report["failure_reason"] = (
                    "checkpoint_delivery_pin_invalid_after_attempt:"
                    f"{delivery_pin_reason}:{attempt_reason}"
                )
                failure_output = args.json_out or (run_dir / "closeout_report.json")
                dump_json(failure_output, report)
                _write_daily_index_best_effort(
                    target_date=target_date,
                    run_root=Path(args.run_root).expanduser(),
                )
                if args.apply:
                    _guarded_update_run_control_status(
                        client=client,
                        contract=contract,
                        target_date=target_date,
                        run_id=run_id,
                        status="FAILED_CHECKPOINT",
                        hold_on_failure=False,
                    )
                    _guarded_send_closeout_alert(
                        title="Google Ops Board Closeout Failed",
                        run_id=run_id,
                        target_date=target_date,
                        report_path=failure_output,
                        stage="checkpoint",
                        detail=report["failure_reason"],
                    )
                return 1
        attempted_resume_ok, attempted_resume_reason, attempted_resume_state = (
            _validate_attempted_delivery_resume(
                checkpoint=checkpoint,
                today_folder=Path(args.today_folder).expanduser(),
                target_date=target_date,
                run_root=Path(args.run_root).expanduser(),
            )
        )
        report["attempted_delivery_resume_gate"] = {
            "ok": attempted_resume_ok,
            "reason": attempted_resume_reason,
            "delivery_status": _clean(attempted_resume_state.get("status")),
        }
        if not attempted_resume_ok:
            report["failure_stage"] = "checkpoint"
            report["failure_reason"] = attempted_resume_reason
            failure_output = args.json_out or (run_dir / "closeout_report.json")
            dump_json(failure_output, report)
            _write_daily_index_best_effort(
                target_date=target_date,
                run_root=Path(args.run_root).expanduser(),
            )
            return 1
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
                _guarded_update_run_control_status(
                    client=client,
                    contract=contract,
                    target_date=target_date,
                    run_id=run_id,
                    status="FAILED_CHECKPOINT",
                    hold_on_failure=False,
                )
                _guarded_send_closeout_alert(
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
            execution_mode=execution_mode,
        )
        report["resumed_stages"] = completed_stages
        report["resumed_from_checkpoint"] = bool(completed_stages)
        for stage in completed_stages:
            _append_checkpoint_stage(report=report, checkpoint=checkpoint, stage=stage)
        if completed_stages:
            delivery_artifacts = dict(checkpoint.get("delivery_artifacts") or {})
            if delivery_artifacts:
                report["pinned_delivery_artifacts"] = delivery_artifacts
            resumed_evidence_path = run_dir / "resumed_checkpoint_evidence.json"
            dump_json(
                resumed_evidence_path,
                {
                    "schema_version": 1,
                    "target_date": target_date.isoformat(),
                    "execution_mode": execution_mode,
                    "checkpoint_path": str(checkpoint_path.resolve()),
                    "checkpoint_sha256": _file_sha256(checkpoint_path),
                    "resumed_stages": completed_stages,
                    "stage_sources": {
                        stage: dict((checkpoint.get("stages") or {}).get(stage) or {})
                        for stage in completed_stages
                    },
                    "required_orders": dict(checkpoint.get("required_orders") or {}),
                    "delivery_artifacts": delivery_artifacts,
                    "run_control_resume_fingerprint": str(
                        checkpoint.get("run_control_resume_fingerprint") or ""
                    ),
                },
            )
            report["resumed_checkpoint_evidence_path"] = str(resumed_evidence_path)
            report["resumed_checkpoint_evidence_sha256"] = _file_sha256(
                resumed_evidence_path
            )

    output_path = args.json_out or (run_dir / "closeout_report.json")
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
        suppress_external_failure_write = False
        if args.apply:
            try:
                failure_row = _read_live_request_identity()
            except Exception:
                failure_row = {
                    "target_date": target_date.isoformat(),
                    "ready_set_at": expected_ready_set_at,
                    "ready_for_closeout": "READY",
                }
            failure_halt_gate = _halt_gate_for_row(failure_row)
            suppress_external_failure_write = bool(failure_halt_gate["blocked"])
            if suppress_external_failure_write:
                report["halt_barrier_stop"] = {
                    "stage": stage,
                    "reason": _clean(failure_halt_gate.get("reason")),
                    "external_failure_write_suppressed": True,
                }
        if args.apply and not suppress_external_failure_write:
            _guarded_update_run_control_status(
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
        if args.apply and not suppress_external_failure_write:
            _guarded_send_closeout_alert(
                title="Google Ops Board Closeout Failed",
                run_id=run_id,
                target_date=target_date,
                report_path=output_path,
                stage=stage,
                resumed=bool(completed_stages),
                detail=reason,
            )
        elif args.apply and suppress_external_failure_write:
            try:
                _enqueue_held_closeout_failure_alert(
                    run_id=run_id,
                    target_date=target_date,
                    report_path=output_path,
                    stage=stage,
                    detail=reason,
                    barrier_reason=_clean(failure_halt_gate.get("reason")),
                )
            except Exception as exc:
                print(f"ERROR: unable to enqueue held closeout alert: {exc}", file=sys.stderr)
        return 1

    def _record_halt_stop(stage: str, gate: dict[str, Any]) -> int:
        report["failure_stage"] = stage
        report["failure_reason"] = f"local_halt_barrier:{gate['reason']}"
        report["halt_barrier_stop"] = {
            "stage": stage,
            "reason": _clean(gate.get("reason")),
            "external_failure_write_suppressed": True,
        }
        dump_json(output_path, report)
        _write_daily_index_best_effort(
            target_date=target_date,
            run_root=Path(args.run_root).expanduser(),
        )
        return 1

    def _request_identity_still_current(stage: str) -> tuple[bool, int | None]:
        if not args.apply:
            return True, None
        current = _read_live_request_identity()
        halt_gate = _halt_gate_for_row(current)
        if halt_gate["blocked"]:
            return False, _record_halt_stop(stage, halt_gate)
        expected = {
            "target_date": target_date.isoformat(),
            "ready_set_at": expected_ready_set_at,
            "ready_for_closeout": "READY",
        }
        if current == expected:
            return True, None
        report.setdefault("request_identity_boundary_failures", []).append(
            {"stage": stage, "expected": expected, "observed": current}
        )
        return False, _record_failure(
            stage,
            f"READY request identity changed before {stage}: {current}",
        )

    try:
        obligation_ledger_path = _resolve_shipping_obligation_ledger_path(args)
    except ValueError as exc:
        return _record_failure("shipping_obligations", str(exc))
    report["shipping_obligation_ledger_path"] = str(obligation_ledger_path)

    if args.apply:
        identity_ok, identity_rc = _request_identity_still_current("closeout_start")
        if not identity_ok:
            return int(identity_rc or 1)
        binding_ok, binding_reason, prior_attempts = _guard_request_delivery_attempt_binding(
            checkpoint=checkpoint,
            completed_stages=completed_stages,
            today_folder=Path(args.today_folder).expanduser(),
            request_identity={
                "target_date": target_date.isoformat(),
                "ready_set_at": _clean(run_control_row.get("ready_set_at")),
            },
        )
        if not binding_ok:
            report["target_date_delivery_attempts"] = prior_attempts
            return _record_failure(
                "checkpoint",
                f"checkpoint_target_date_delivery_attempt_unbound:{binding_reason}",
            )

    if args.apply:
        start_alert_sent = _guarded_send_closeout_alert(
            title="Google Ops Board Closeout Resumed" if completed_stages else "Google Ops Board Closeout Started",
            run_id=run_id,
            target_date=target_date,
            report_path=output_path,
            resumed=bool(completed_stages),
            detail=f"Completed stages: {', '.join(completed_stages)}" if completed_stages else None,
        )
        if not start_alert_sent:
            reason = _clean(
                (report.get("halt_barrier_stop") or {}).get("reason")
            ) or "EXTERNAL_MUTATION_RECHECK_FAILED"
            return _record_halt_stop(
                "closeout_start_alert",
                {"reason": reason},
            )

    store_context = build_store_context_report(
        salesraw_rows=closeout_salesraw_rows,
        storeb_excluded=storeb_excluded,
    )
    if storeb_excluded:
        store_context["fitpack_storeb_excluded"] = True
        store_context["fitpack_storeb_skipped_rows"] = fitpack_skipped_rows
    dump_json(run_dir / "store_context_report.json", store_context)
    report["store_context_report_path"] = str(run_dir / "store_context_report.json")
    if not store_context["ok"]:
        return _record_failure("store_context", "Store token / merchant UID context failed preflight")
    shipping_store_codes = [
        normalize_store_code(value)
        for value in store_context.get("active_store_codes") or []
        if normalize_store_code(value) in STORE_TOKEN_MAP
    ]
    if not shipping_store_codes:
        return _record_failure("store_context", "Configured shipping store roster is empty")

    expected_orders_path = run_dir / "expected_closeout_orders.json"
    zero_order_noop = False
    # Both modes must exercise the exact obligation and pinned-order path.  Dry
    # run writes only run-dir evidence and never persists the canonical ledger.
    exact_preflight_enabled = True
    if exact_preflight_enabled:
        if args.apply:
            identity_ok, identity_rc = _request_identity_still_current(
                "shipping_obligations"
            )
            if not identity_ok:
                return int(identity_rc or 1)
        request_identity = {
            "target_date": target_date.isoformat(),
            "ready_set_at": _clean(run_control_row.get("ready_set_at")),
        }
        try:
            active_order_ids_by_store = fetch_api_active_order_ids_by_store(
                target_date=target_date,
                lookback_days=args.lookback_days,
                store_codes=shipping_store_codes,
                api_since_days=14,
                verbose=False,
            )
            prepacked_decision = load_validated_prepacked_exclusion(
                target_date=target_date,
            )
            prepacked_expectation = load_prepacked_exclusion_expectation(
                target_date=target_date,
            )
            expectation_error = _enforce_prepacked_exclusion_expectation(
                target_date=target_date,
                expectation=prepacked_expectation,
                decision=prepacked_decision,
            )
            if prepacked_expectation is not None:
                report["prepacked_exclusion_expectation"] = {
                    "path": _clean(prepacked_expectation.get("path")),
                    "target_date": target_date.isoformat(),
                    "decision_id": _clean(prepacked_expectation.get("decision_id")),
                    "decision_sha256": _clean(
                        prepacked_expectation.get("decision_sha256")
                    ),
                    "satisfied": not bool(expectation_error),
                }
            if expectation_error:
                return _record_failure(
                    "prepacked_exclusion_expectation",
                    expectation_error,
                )
            uncertainty_waiver_ids_by_store = dict(
                (prepacked_decision or {}).get("excluded_order_ids_by_store") or {}
            )
            # The exact current active selector plus the already-persisted
            # obligation ledger are sufficient for this owner-authorized,
            # date-bound request.  Never put the legacy all-history bootstrap
            # scan back into its latency-critical READY path.
            db_bootstrap_ids_by_store = {}
            full_prior_obligations = load_shipping_obligation_ledger(obligation_ledger_path)
            prior_obligations, preserved_out_of_scope_entries = _scope_obligation_ledger(
                full_prior_obligations,
                shipping_store_codes,
            )
            bootstrap_resolution = {
                "ok": True,
                "ledger": prior_obligations,
                "mode": "bounded_current_active_plus_persisted_obligations",
                "candidate_count": 0,
                "exact_detail_read_count": 0,
                "promoted_keys": [],
                "terminal_audit_keys": [],
                "quarantined": [],
            }
            prior_obligations = bootstrap_resolution["ledger"]
            reconciliation_active_order_ids_by_store = (
                _existing_open_orders_present_in_current(
                    prior_obligations,
                    active_order_ids_by_store,
                )
            )
            detail_stats: dict[str, Any] = {}
            detail_results = _fetch_prior_obligation_details(
                ledger=prior_obligations,
                current_active_order_ids_by_store=(
                    reconciliation_active_order_ids_by_store
                ),
                target_date=target_date,
                stats_out=detail_stats,
            )
            obligation_result = reconcile_shipping_obligations(
                prior_ledger=prior_obligations,
                current_active_order_ids_by_store=(
                    reconciliation_active_order_ids_by_store
                ),
                detail_results=detail_results,
                target_date=target_date,
                ready_set_at=request_identity["ready_set_at"],
                now=datetime.now(ALMATY_TZ),
                uncertainty_waiver_ids_by_store=uncertainty_waiver_ids_by_store,
                enqueue_uncertainty_warnings=bool(args.apply),
            )
            if not bootstrap_resolution.get("ok"):
                obligation_result["ok"] = False
                obligation_result.setdefault("issues", []).append(
                    {
                        "code": "db_bootstrap_hint_exact_read_uncertain",
                        "quarantined": bootstrap_resolution.get("quarantined") or [],
                    }
                )
        except Exception as exc:
            return _record_failure(
                "shipping_obligations",
                f"Shipping obligation reconciliation failed: {type(exc).__name__}: {exc}",
            )

        obligation_report_path = run_dir / "shipping_obligation_reconciliation.json"
        dump_json(
            obligation_report_path,
            {
                "ok": bool(obligation_result.get("ok")),
                "target_date": target_date.isoformat(),
                "request_identity": request_identity,
                "issues": obligation_result.get("issues") or [],
                "uncertainty_scope_counts": dict(
                    obligation_result.get("uncertainty_scope_counts")
                    or {"covered": 0, "uncovered": 0}
                ),
                "uncertainty_waiver_ids_by_store": {
                    store: sorted(order_ids)
                    for store, order_ids in sorted(
                        uncertainty_waiver_ids_by_store.items()
                    )
                },
                "active_order_ids_by_store": {
                    store: sorted(order_ids)
                    for store, order_ids in sorted(
                        dict(obligation_result.get("active_order_ids_by_store") or {}).items()
                    )
                },
                "db_bootstrap_counts_by_store": {
                    store: len(order_ids)
                    for store, order_ids in sorted(db_bootstrap_ids_by_store.items())
                },
                "exact_detail_read_count": int(detail_stats.get("exact_read_count") or 0),
                "detail_resolution": detail_stats,
                "db_bootstrap_hint_resolution": {
                    key: value
                    for key, value in bootstrap_resolution.items()
                    if key != "ledger"
                },
                "configured_shipping_store_codes": shipping_store_codes,
                "preserved_out_of_scope_ledger_entry_count": len(
                    preserved_out_of_scope_entries
                ),
                "current_active_registration_deferred_count": sum(
                    len(order_ids)
                    for order_ids in active_order_ids_by_store.values()
                ),
            },
        )
        report["shipping_obligation_ledger_written"] = False
        report["shipping_obligation_reconciliation_path"] = str(obligation_report_path)
        if not obligation_result.get("ok"):
            report["shipping_obligation_ledger_write_suppressed"] = True
            report["shipping_obligation_ledger_write_suppressed_reason"] = (
                "detail_budget_exhausted_non_sticky"
                if detail_stats.get("budget_exhausted")
                else "reconciliation_non_green"
            )
            return _record_failure(
                "shipping_obligations",
                "Shipping obligations are uncertain; retained locally and blocked without omission.",
            )

        reconciled_prior_ledger = obligation_result["ledger"]
        if args.apply:
            save_shipping_obligation_ledger(
                obligation_ledger_path,
                _merge_scoped_obligation_ledger(
                    reconciled_prior_ledger,
                    preserved_out_of_scope_entries,
                ),
            )
            report["shipping_obligation_ledger_written"] = True
            report["shipping_obligation_ledger_write_phase"] = (
                "successful_prior_reconciliation_only"
            )

        required_ids_by_store = _union_order_ids_by_store(
            active_order_ids_by_store,
            {
                store: set(order_ids)
                for store, order_ids in dict(
                    obligation_result.get("active_order_ids_by_store") or {}
                ).items()
            },
        )
        try:
            prepacked_result = apply_prepacked_exclusion(
                required_ids_by_store,
                prepacked_decision,
            )
        except Exception as exc:
            return _record_failure(
                "prepacked_exclusion",
                f"Prepacked carryover exclusion failed closed: {type(exc).__name__}: {exc}",
            )
        required_ids_by_store = {
            store: set(order_ids)
            for store, order_ids in dict(
                prepacked_result.get("required_ids_by_store") or {}
            ).items()
        }
        store_day_state_report_path = run_dir / "store_day_state_report.json"
        try:
            required_ids_by_store, store_day_state_report = (
                _apply_store_day_state_scope(
                    required_ids_by_store,
                    target_date=target_date,
                    checkpoint_path=day_state_checkpoint_path,
                    report_path=store_day_state_report_path,
                )
            )
        except Exception as exc:
            dump_json(
                store_day_state_report_path,
                {
                    "schema_version": 1,
                    "target_date": target_date.isoformat(),
                    "checkpoint_path": str(day_state_checkpoint_path),
                    "ok": False,
                    "error": f"{type(exc).__name__}: {exc}",
                },
            )
            return _record_failure(
                "store_day_state",
                "Store day-state scoping failed closed: "
                f"{type(exc).__name__}: {exc}",
            )
        report["store_day_state_report_path"] = str(store_day_state_report_path)
        report["store_day_state_scope_applied"] = bool(
            store_day_state_report.get("applied")
        )
        prepacked_report_path = run_dir / "prepacked_exclusion_report.json"
        dump_json(
            prepacked_report_path,
            {
                "target_date": target_date.isoformat(),
                "applied": bool(prepacked_result.get("applied")),
                "decision_id": _clean((prepacked_decision or {}).get("decision_id")),
                "decision_path": _clean((prepacked_decision or {}).get("path")),
                "preserve_physical_handover_obligation": bool(
                    (prepacked_decision or {}).get("preserve_physical_handover_obligation")
                ),
                "counts_before": prepacked_result.get("counts_before") or {},
                "counts_after": prepacked_result.get("counts_after") or {},
                "declared_exclusion_count": int(
                    prepacked_result.get("declared_exclusion_count") or 0
                ),
                "excluded_active_count": int(
                    prepacked_result.get("excluded_active_count") or 0
                ),
                "excluded_active_ids_by_store": {
                    store: sorted(order_ids)
                    for store, order_ids in sorted(
                        dict(prepacked_result.get("excluded_active_ids_by_store") or {}).items()
                    )
                },
                "inactive_declared_ids_by_store": {
                    store: sorted(order_ids)
                    for store, order_ids in sorted(
                        dict(prepacked_result.get("inactive_declared_ids_by_store") or {}).items()
                    )
                },
            },
        )
        report["prepacked_exclusion_report_path"] = str(prepacked_report_path)
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

        try:
            size_writeback_scope_path = _write_size_writeback_scope(
                run_dir / "size_writeback_order_scope.json",
                target_date=target_date,
                request_identity=request_identity,
                orders_by_store=required_ids_by_store,
                salesraw_rows=closeout_salesraw_rows,
            )
        except ValueError as exc:
            return _record_failure("size_writeback", str(exc))
        report["size_writeback_order_scope_path"] = str(size_writeback_scope_path)
        if "size_writeback" not in completed_stages:
            identity_ok, identity_rc = _request_identity_still_current("size_writeback")
            if not identity_ok:
                return int(identity_rc or 1)
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
                "--allowed-order-scope-file",
                str(size_writeback_scope_path),
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

        expected_orders = build_expected_orders_from_db(
            db_path=db_path,
            target_date=target_date,
            lookback_days=None,
            active_order_ids_by_store=required_ids_by_store,
            request_identity=request_identity,
        )
        candidate_expected_path = run_dir / "expected_closeout_orders_candidate.json"
        write_expected_orders_report(expected_orders, candidate_expected_path)
        if expected_orders.get("ok") is False:
            report["expected_closeout_orders_path"] = str(candidate_expected_path)
            report["active_order_blockers"] = expected_orders.get("active_order_blockers") or {}
            return _record_failure(
                "expected_orders",
                "One or more active shipping obligations lacks complete DB/size eligibility.",
            )

        checkpoint_required = dict(checkpoint.get("required_orders") or {})
        external_stage_resumed = any(
            stage in completed_stages
            for stage in ("shipping", "download_waybills", "build_waybills", "delivery_send")
        )
        if external_stage_resumed:
            required_ok, required_reason = _required_orders_checkpoint_valid(
                checkpoint,
                target_date=target_date,
            )
            if not required_ok:
                return _record_failure("checkpoint", required_reason)
            expected_orders_path = Path(str(checkpoint_required["path"]))
            try:
                pinned_required = load_required_orders_file(
                    expected_orders_path,
                    target_date=target_date,
                )
            except Exception as exc:
                return _record_failure(
                    "checkpoint",
                    f"Pinned required-order artifact became unreadable: {exc}",
                )
            if (
                dict(pinned_required["request_identity"]) != request_identity
                or pinned_required["orders_by_store"] != _expected_orders_by_store(expected_orders)
                or (
                    pinned_required.get("line_scope_required")
                    and _clean(pinned_required.get("line_scope_hash"))
                    != _clean(expected_orders.get("line_scope_hash"))
                )
            ):
                return _record_failure(
                    "checkpoint",
                    "Fresh shipping obligations differ from the pinned in-progress request.",
                )
        else:
            expected_orders_path = run_dir / "expected_closeout_orders.json"
            write_expected_orders_report(expected_orders, expected_orders_path)
            try:
                pinned_required = load_required_orders_file(
                    expected_orders_path,
                    target_date=target_date,
                )
            except Exception as exc:
                return _record_failure(
                    "expected_orders",
                    f"Generated required-order artifact failed identity validation: {exc}",
                )
            checkpoint["required_orders"] = {
                "path": pinned_required["path"],
                "sha256": pinned_required["sha256"],
                "request_identity": dict(pinned_required["request_identity"]),
                "line_scope_hash": pinned_required.get("line_scope_hash") or "",
            }
            _write_checkpoint(checkpoint_path, checkpoint)

        report["expected_closeout_orders_path"] = str(expected_orders_path)
        report["expected_closeout_order_count"] = expected_orders["counts"]["orders"]
        report["expected_closeout_overdue_order_count"] = expected_orders["counts"]["overdue_orders"]
        zero_order_noop = int(expected_orders["counts"]["orders"]) == 0
        report["zero_order_noop"] = zero_order_noop

    def _persist_current_active_registration(phase: str) -> int | None:
        if not args.apply:
            return None
        try:
            registered_ledger = _register_current_obligations_after_success(
                reconciled_prior_ledger,
                active_order_ids_by_store,
                target_date=target_date,
                ready_set_at=request_identity["ready_set_at"],
                now=datetime.now(ALMATY_TZ),
            )
            save_shipping_obligation_ledger(
                obligation_ledger_path,
                _merge_scoped_obligation_ledger(
                    registered_ledger,
                    preserved_out_of_scope_entries,
                ),
            )
        except Exception as exc:
            return _record_failure(
                "shipping_obligations",
                "Current-target obligation registration failed after successful "
                f"{phase}: {type(exc).__name__}: {exc}",
            )
        report["shipping_obligation_ledger_written"] = True
        report["shipping_obligation_ledger_write_phase"] = phase
        report["current_active_obligations_registered_count"] = sum(
            len(order_ids) for order_ids in active_order_ids_by_store.values()
        )
        return None

    if not zero_order_noop and "shipping" not in completed_stages:
        identity_ok, identity_rc = _request_identity_still_current("shipping")
        if not identity_ok:
            return int(identity_rc or 1)
        pin_ok, pin_reason = _required_orders_db_pin_valid(
            checkpoint,
            db_path=db_path,
            target_date=target_date,
        )
        if not pin_ok:
            return _record_failure("shipping", pin_reason)
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
            "--required-orders-file",
            str(expected_orders_path),
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

    if not zero_order_noop:
        registration_rc = _persist_current_active_registration(
            "shipping_stage_confirmed"
        )
        if registration_rc is not None:
            return registration_rc

    if not zero_order_noop and "download_waybills" not in completed_stages:
        identity_ok, identity_rc = _request_identity_still_current(
            "download_waybills"
        )
        if not identity_ok:
            return int(identity_rc or 1)
        pin_ok, pin_reason = _required_orders_db_pin_valid(
            checkpoint,
            db_path=db_path,
            target_date=target_date,
        )
        if not pin_ok:
            return _record_failure("download_waybills", pin_reason)
        download_cmd = [
            selected_python,
            str(PROJECT_ROOT / "scripts" / "download_waybills_api.py"),
            "--db-path",
            str(db_path),
            "--date",
            target_date.isoformat(),
            "--include-overdue",
            "--verbose",
            "--required-orders-file",
            str(expected_orders_path),
            "--require-complete-api-selection",
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

    if not zero_order_noop and "build_waybills" not in completed_stages:
        identity_ok, identity_rc = _request_identity_still_current("build_waybills")
        if not identity_ok:
            return int(identity_rc or 1)
        pin_ok, pin_reason = _required_orders_db_pin_valid(
            checkpoint,
            db_path=db_path,
            target_date=target_date,
        )
        if not pin_ok:
            return _record_failure("build_waybills", pin_reason)
        manifests_before_build = _send_manifest_paths(Path(args.today_folder).expanduser())
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
            "--required-orders-file",
            str(expected_orders_path),
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
        build_artifacts: list[str] = []
        if args.apply:
            new_manifests = sorted(
                _send_manifest_paths(Path(args.today_folder).expanduser()) - manifests_before_build,
                key=str,
            )
            if len(new_manifests) != 1:
                return _record_failure(
                    "build_waybills",
                    "Bundle build did not create exactly one new immutable send manifest "
                    f"(observed={len(new_manifests)}).",
                    build_step,
                )
            try:
                delivery_artifacts = _pin_send_manifest(
                    manifest_path=new_manifests[0],
                    today_folder=Path(args.today_folder).expanduser(),
                    expected_orders_path=expected_orders_path,
                )
            except Exception as exc:
                return _record_failure(
                    "build_waybills",
                    f"New send manifest could not be identity-pinned: {exc}",
                    build_step,
                )
            checkpoint["delivery_artifacts"] = delivery_artifacts
            build_artifacts = [
                delivery_artifacts["manifest_path"],
                delivery_artifacts["ledger_path"],
            ]
            report["pinned_delivery_artifacts"] = delivery_artifacts
        _checkpoint_stage_report(
            checkpoint=checkpoint,
            stage="build_waybills",
            step_report=build_step,
            run_id=run_id,
            run_dir=run_dir,
            artifact_paths=build_artifacts,
        )
        _write_checkpoint(checkpoint_path, checkpoint)

    if args.apply and not zero_order_noop:
        pin_ok, pin_reason = _required_orders_db_pin_valid(
            checkpoint,
            db_path=db_path,
            target_date=target_date,
        )
        if not pin_ok:
            return _record_failure("expected_order_gate", pin_reason)
        delivery_artifacts = dict(checkpoint.get("delivery_artifacts") or {})
        if _clean(delivery_artifacts.get("expected_orders_sha256")) != _clean(
            (checkpoint.get("required_orders") or {}).get("sha256")
        ):
            return _record_failure(
                "expected_order_gate",
                "pinned_manifest_checkpoint_required_orders_sha256_mismatch",
            )
        manifest_path = Path(str(delivery_artifacts.get("manifest_path") or ""))
        manifest_pin_ok, manifest_pin_reason = _validate_pinned_manifest(
            delivery_artifacts,
            today_folder=Path(args.today_folder).expanduser(),
        )
        if not manifest_pin_ok:
            return _record_failure("expected_order_gate", manifest_pin_reason)
        if "delivery_send" not in completed_stages:
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
            identity_ok, identity_rc = _request_identity_still_current("delivery_send")
            if not identity_ok:
                return int(identity_rc or 1)
            delivery_cmd = [
                selected_python,
                str(PROJECT_ROOT / "scripts" / "send_waybills_delivery.py"),
                "--today-folder",
                str(Path(args.today_folder).expanduser()),
                "--bundle-source",
                "merged",
                "--expected-target-date",
                target_date.isoformat(),
                "--manifest-path",
                str(manifest_path),
                "--manifest-sha256",
                _clean(delivery_artifacts.get("manifest_sha256")),
                "--whatsapp-fallback-policy",
                "disabled",
                "--json-out",
                str(run_dir / "delivery_send_report.json"),
            ]
            checkpoint["delivery_attempt"] = {
                "schema_version": 1,
                "status": "started",
                "started_at": datetime.now(ALMATY_TZ).isoformat(),
                "run_id": run_id,
                "manifest_path": str(manifest_path.resolve()),
                "manifest_sha256": _clean(delivery_artifacts.get("manifest_sha256")),
                "request_identity": {
                    "target_date": target_date.isoformat(),
                    "ready_set_at": expected_ready_set_at,
                },
            }
            _write_checkpoint(checkpoint_path, checkpoint)
            identity_ok, identity_rc = _request_identity_still_current(
                "delivery_send_launch"
            )
            if not identity_ok:
                return int(identity_rc or 1)
            delivery_step = _run_command(
                name="delivery_send",
                command=delivery_cmd,
                env=env,
                report_path=run_dir / "step_delivery_send.json",
            )
            checkpoint["delivery_attempt"] = {
                **dict(checkpoint.get("delivery_attempt") or {}),
                "status": "returned",
                "returncode": int(delivery_step["returncode"]),
                "completed_at": datetime.now(ALMATY_TZ).isoformat(),
            }
            _write_checkpoint(checkpoint_path, checkpoint)
            report["steps"].append(delivery_step)
            if delivery_step["returncode"] != 0:
                return _record_failure("delivery_send", "Delivery step failed", delivery_step)
            delivery_verification = delivery_completion_state(
                today_folder=Path(args.today_folder).expanduser(),
                target_date=target_date,
                run_root=Path(args.run_root).expanduser(),
                run_id=run_id,
                manifest_path=manifest_path,
                expected_manifest_sha256=_clean(
                    delivery_artifacts.get("manifest_sha256")
                ),
            )
            report["delivery_completion_verification"] = {
                "completed": bool(delivery_verification.get("completed")),
                "status": _clean(delivery_verification.get("status")),
                "confirmed_count": int(
                    delivery_verification.get("confirmed_count") or 0
                ),
                "manifest_count": int(
                    delivery_verification.get("manifest_count") or 0
                ),
            }
            if not delivery_verification.get("completed"):
                return _record_failure(
                    "delivery_send",
                    "Delivery subprocess returned success without a complete pinned "
                    f"Telegram ledger: {_clean(delivery_verification.get('status'))}",
                    delivery_step,
                )
            checkpoint["delivery_attempt"] = {
                **dict(checkpoint.get("delivery_attempt") or {}),
                "status": "confirmed",
                "verified_at": datetime.now(ALMATY_TZ).isoformat(),
            }
            _checkpoint_stage_report(
                checkpoint=checkpoint,
                stage="delivery_send",
                step_report=delivery_step,
                run_id=run_id,
                run_dir=run_dir,
                artifact_paths=[str(run_dir / "delivery_send_report.json")],
            )
            _write_checkpoint(checkpoint_path, checkpoint)
            auto_sent_result = _stamp_manifest_stores_auto_sent(
                manifest_path=manifest_path,
                target_date=target_date,
                checkpoint_path=day_state_checkpoint_path,
            )
            report["store_day_state_auto_sent"] = auto_sent_result
            try:
                refreshed_day_states = load_store_day_states(
                    target_date,
                    checkpoint_path=day_state_checkpoint_path,
                )
            except Exception as exc:
                print(
                    "WARNING: unable to reload AUTO_SENT day states into closeout "
                    f"checkpoint: {type(exc).__name__}: {exc}",
                    file=sys.stderr,
                )
            else:
                if refreshed_day_states:
                    checkpoint["store_day_states"] = refreshed_day_states

        if "shipped_truth_sync" not in completed_stages:
            identity_ok, identity_rc = _request_identity_still_current(
                "shipped_truth_sync"
            )
            if not identity_ok:
                return int(identity_rc or 1)
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
    elif zero_order_noop:
        zero_step = {
            "name": "zero_order_noop",
            "command": [],
            "returncode": 0,
            "stdout": "",
            "stderr": "",
            "ok": True,
            "skipped": True,
            "note": "No active shipping obligations; no assembly, PDF build, or delivery was attempted.",
        }
        dump_json(run_dir / "step_zero_order_noop.json", zero_step)
        report["steps"].append(zero_step)
        if args.apply:
            zero_completion_path = run_dir / "zero_order_completion.json"
            dump_json(
                zero_completion_path,
                {
                    "schema_version": 1,
                    "completed": True,
                    "mode": "apply",
                    "run_id": run_id,
                    "target_date": target_date.isoformat(),
                    "request_identity": request_identity,
                    "required_order_count": 0,
                    "required_orders_path": str(expected_orders_path.resolve()),
                    "required_orders_sha256": _file_sha256(expected_orders_path),
                    "completed_at": datetime.now(ALMATY_TZ).isoformat(),
                },
            )
            report["zero_order_completion_path"] = str(zero_completion_path)
            registration_rc = _persist_current_active_registration(
                "terminal_zero_order_closeout_confirmed"
            )
            if registration_rc is not None:
                return registration_rc
    elif not args.apply:
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
        identity_ok, identity_rc = _request_identity_still_current("finalize")
        if not identity_ok:
            return int(identity_rc or 1)
        final_status_written = _guarded_update_run_control_status(
            client=client,
            contract=contract,
            target_date=target_date,
            run_id=run_id,
            status="OK",
            hold_on_failure=False,
        )
        if not final_status_written:
            reason = _clean(
                (report.get("halt_barrier_stop") or {}).get("reason")
            ) or "EXTERNAL_MUTATION_RECHECK_FAILED"
            return _record_halt_stop("finalize_status", {"reason": reason})
    _write_checkpoint(checkpoint_path, checkpoint)
    dump_json(output_path, report)
    _write_daily_index_best_effort(target_date=target_date, run_root=Path(args.run_root).expanduser())
    if args.apply:
        try:
            flush_held(f"successful closeout run {run_id}")
        except Exception as exc:
            print(f"WARNING: unable to flush held closeout alerts: {exc}", file=sys.stderr)
        _guarded_send_closeout_alert(
            title="Google Ops Board Closeout Complete",
            run_id=run_id,
            target_date=target_date,
            report_path=output_path,
            resumed=bool(completed_stages),
        )
    print(f"Closeout report: {output_path}")
    return 0


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
    parser.add_argument("--checkpoint-path", type=Path, default=None, help="Optional day-level checkpoint path")
    parser.add_argument(
        "--obligation-ledger-path",
        type=Path,
        default=None,
        help="Persistent local unresolved-shipping ledger (defaults under runtime/state)",
    )
    parser.add_argument("--resume", action="store_true", help="Reuse prior successful safe stages when possible")
    parser.add_argument(
        "--expected-ready-set-at",
        type=str,
        default="",
        help="Immutable READY timestamp supplied by the debounced launcher; required for --apply",
    )
    parser.add_argument(
        "--shadow-board-run-dir",
        type=Path,
        default=None,
        help=(
            "Dry-run only: read Run_Control and SalesRaw_Today from a preserved "
            "successful apply closeout instead of Google"
        ),
    )
    parser.add_argument("--apply", action="store_true", help="Run live closeout (default: dry-run)")
    parser.add_argument("--json-out", type=Path, default=None, help="Optional top-level JSON report path")
    args = parser.parse_args(argv)

    if args.apply and args.shadow_board_run_dir:
        parser.error("--shadow-board-run-dir cannot be combined with --apply")

    _load_repo_dotenv()
    if args.shadow_board_run_dir:
        _strip_shadow_write_gates()

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
    raise SystemExit(run_guarded("run_google_ops_board_closeout", main))
