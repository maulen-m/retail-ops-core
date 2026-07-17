#!/usr/bin/env python3
"""Minute-level watcher that triggers closeout early once the board is truly ready."""

from __future__ import annotations

import os
import json
import subprocess
import sys
from datetime import date, timedelta
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.integrations.google_ops_board import (  # noqa: E402
    DEFAULT_CONTRACT_PATH,
    GoogleOpsBoardClient,
    extract_rows_with_positions_from_matrix,
    load_ops_board_contract,
    resolve_service_account_json,
    resolve_spreadsheet_id,
)
from core.ops.fitpack_coordination import load_storeb_packing_excluded  # noqa: E402
from core.ops.waybill_shipping_obligations import normalize_store_code  # noqa: E402
from core.stores.roster import load_sync_enabled_kaspi_store_codes  # noqa: E402
from core.utils.sku_normalize import normalize_size  # noqa: E402
from scripts.google_ops_board_automation_common import (  # noqa: E402
    DEFAULT_READY_DEBOUNCE_STATE_PATH,
    READY_DEBOUNCE_SECONDS,
    auto_probable_closeout_cutoff_reached,
    clear_ready_debounce_state,
    closeout_completion_state,
    evaluate_ready_debounce,
    ensure_kaspi_api_call_ledger_env,
    evaluate_closeout_halt_barrier,
    load_ready_debounce_state,
    now_almaty,
    run_guarded,
    save_json_file,
    save_ready_debounce_state,
    select_run_control_row,
    today_almaty,
    within_early_closeout_watch_window,
)
from scripts.run_google_ops_board_closeout import build_readiness_report  # noqa: E402
from scripts.sync_google_ops_board_sizes_to_db import _load_db_rows as load_db_rows_for_writeback  # noqa: E402

SCRIPT_PATH = PROJECT_ROOT / "scripts" / "run_google_ops_board_closeout_scheduler.py"
DB_PATH = PROJECT_ROOT / "db" / "app.db"
READY_DEBOUNCE_STATE_PATH = DEFAULT_READY_DEBOUNCE_STATE_PATH
AUTO_PROBABLE_AUDIT_ROOT = PROJECT_ROOT / "exports" / "google_ops_board" / "auto_probable_fill"
IDENTITY_SYNC_WRITE_ENV_GATE = "ENABLE_KASPI_WORKBOOK_MAP_SYNC"
AUTO_READY_SET_BY = "AUTO_CLOSEOUT_1857"
AUTO_PROBABLE_FILL_ENV = "AB_GOOGLE_OPS_BOARD_ALLOW_AUTO_PROBABLE_FILL"
WATCH_READY_SET_BY = "READY_WATCHER"


def _in_watch_window() -> bool:
    return within_early_closeout_watch_window(now_almaty())


def _auto_probable_fill_enabled(env: dict[str, str]) -> bool:
    return str(env.get(AUTO_PROBABLE_FILL_ENV) or "").strip() == "1"


def _clean(value: object) -> str:
    text = str(value or "").strip()
    if text.endswith(".0") and text[:-2].isdigit():
        return text[:-2]
    return text


def _append_note(existing_note: object, extra_note: str) -> str:
    current = _clean(existing_note)
    if not current:
        return extra_note
    if extra_note in current:
        return current
    return f"{current} | {extra_note}"


def _auto_fill_row_is_in_scope(
    row: dict[str, object],
    *,
    target_date: date,
    enabled_store_codes: set[str],
) -> bool:
    if normalize_store_code(row.get("STORE_NAME")) not in enabled_store_codes:
        return False
    if _clean(row.get("Status")).upper() not in {"TODAY", "OVERDUE"}:
        return False
    try:
        row_date = date.fromisoformat(_clean(row.get("Date")))
    except ValueError:
        return False
    return row_date <= target_date


def _blocker_order_ids(rows: list[dict[str, object]]) -> list[str]:
    order_ids: list[str] = []
    seen: set[str] = set()
    for row in rows:
        order_id = _clean(row.get("OrderID") or row.get("order_id"))
        if not order_id or order_id in seen:
            continue
        seen.add(order_id)
        order_ids.append(order_id)
    return order_ids


def _recoverable_block_status(readiness: dict[str, object]) -> tuple[str, str]:
    if not bool(readiness.get("run_control_ready_ok")):
        return "", ""
    blank_rows = list(readiness.get("blank_size_rows") or [])
    invalid_rows = list(readiness.get("invalid_size_rows") or [])
    if int(readiness.get("blank_size_count") or 0) > 0:
        order_ids = _blocker_order_ids(blank_rows)
        detail = ", ".join(order_ids[:20])
        if len(order_ids) > 20:
            detail += f", +{len(order_ids) - 20} more"
        return "BLOCKED_MISSING_SIZES", f"BLOCKED_MISSING_SIZES: fill MY_SIZE for orders {detail}"
    if int(readiness.get("invalid_size_count") or 0) > 0:
        order_ids = _blocker_order_ids(invalid_rows)
        detail = ", ".join(order_ids[:20])
        if len(order_ids) > 20:
            detail += f", +{len(order_ids) - 20} more"
        return "BLOCKED_INVALID_SIZES", f"BLOCKED_INVALID_SIZES: fix MY_SIZE for orders {detail}"
    return "BLOCKED_READY_GATE", "BLOCKED_READY_GATE: Run_Control READY is set but closeout gate is not green"


def _revalidate_watch_mutation(
    *,
    client: GoogleOpsBoardClient,
    contract,
    target_date: date,
    now,
    allow_fresh_blank_ready: bool = False,
) -> tuple[bool, dict[str, object], dict[str, object]]:
    """Re-read the local halt barrier immediately before a watcher side effect."""
    headers = contract.tabs["Run_Control"].headers
    rows = extract_rows_with_positions_from_matrix(
        headers,
        client.get_tab_values("Run_Control"),
    )
    selected = next(
        (
            item
            for item in rows
            if _clean(item["row"].get("target_date")) == target_date.isoformat()
        ),
        None,
    )
    if selected is None:
        return False, {}, {"blocked": True, "reason": "RUN_CONTROL_TARGET_MISSING"}
    row = dict(selected["row"])
    gate = evaluate_closeout_halt_barrier(
        target_date=target_date,
        run_control_row=row,
        request_ready_set_at=_clean(row.get("ready_set_at")),
        now=now,
    )
    allowed = not bool(gate.get("blocked"))
    if allow_fresh_blank_ready and gate.get("allow_fresh_blank_ready"):
        allowed = True
    return allowed, {**selected, "row": row}, gate


def _mark_recoverable_ready_block(
    *,
    client: GoogleOpsBoardClient,
    contract,
    target_date,
    readiness: dict[str, object],
    now,
) -> None:
    status, note = _recoverable_block_status(readiness)
    if not status:
        return

    headers = contract.tabs["Run_Control"].headers
    rows_with_positions = extract_rows_with_positions_from_matrix(headers, client.get_tab_values("Run_Control"))
    target_iso = target_date.isoformat()
    selected = None
    for row_info in rows_with_positions:
        if _clean(row_info["row"].get("target_date")) == target_iso:
            selected = row_info
            break
    if selected is None:
        return

    allowed, selected, gate = _revalidate_watch_mutation(
        client=client,
        contract=contract,
        target_date=target_date,
        now=now,
    )
    if not allowed:
        return
    row = dict(selected["row"])
    updated_notes = _append_note(row.get("notes"), note)
    if _clean(row.get("last_orchestrator_status")) == status and _clean(row.get("notes")) == updated_notes:
        return
    row["last_verified_ready_at"] = now.isoformat()
    row["last_orchestrator_status"] = status
    row["notes"] = updated_notes
    client.update_tab_rows(
        "Run_Control",
        headers,
        [{"sheet_row": int(selected["sheet_row"]), "row": row}],
    )


def _stamp_blank_ready_identity(
    *,
    client: GoogleOpsBoardClient,
    contract,
    target_date,
    now,
) -> dict[str, object]:
    headers = contract.tabs["Run_Control"].headers
    rows = extract_rows_with_positions_from_matrix(headers, client.get_tab_values("Run_Control"))
    selected = next(
        (
            item
            for item in rows
            if _clean(item["row"].get("target_date")) == target_date.isoformat()
        ),
        None,
    )
    if selected is None:
        return {}
    row = dict(selected["row"])
    if _clean(row.get("ready_for_closeout")).upper() != "READY":
        return row
    if _clean(row.get("ready_set_at")):
        return row
    allowed, selected, gate = _revalidate_watch_mutation(
        client=client,
        contract=contract,
        target_date=target_date,
        now=now,
        allow_fresh_blank_ready=True,
    )
    if not allowed:
        row["_halt_barrier_blocked"] = _clean(gate.get("reason"))
        return row
    row = dict(selected["row"])
    if _clean(row.get("ready_for_closeout")).upper() != "READY":
        return row
    if _clean(row.get("ready_set_at")):
        return row
    row["ready_set_at"] = now.isoformat()
    if not _clean(row.get("ready_set_by")):
        row["ready_set_by"] = WATCH_READY_SET_BY
    client.update_tab_rows(
        "Run_Control",
        headers,
        [{"sheet_row": int(selected["sheet_row"]), "row": row}],
    )
    return row


def _derive_auto_fill_size(*, row: dict[str, object], db_row: dict[str, object], db_path: Path) -> tuple[str, str]:
    product_type = _clean((db_row or {}).get("product_type"))
    if not product_type:
        sku_key = _clean((db_row or {}).get("sku_key"))
        product_type = sku_key.split("_", 1)[0] if "_" in sku_key else "CL"

    raw_probable_size = _clean(row.get("PROBABLE_SIZE"))
    probable_size = normalize_size(raw_probable_size, product_type=product_type)
    if probable_size:
        probable_source = _clean(row.get("_probable_size_source")) or "SHEET_PROBABLE"
        return probable_size, probable_source
    if raw_probable_size:
        return "", "INVALID_PROBABLE_SIZE"
    return "", "MISSING_PROBABLE_SIZE"


def _write_auto_probable_audit(
    *,
    target_date,
    now,
    applied_rows: list[dict[str, str]],
    unresolved_rows: list[dict[str, object]],
) -> Path | None:
    if not applied_rows and not unresolved_rows:
        return None
    stamp = now.strftime("%Y%m%d_%H%M%S")
    audit_path = AUTO_PROBABLE_AUDIT_ROOT / target_date.isoformat() / f"auto_probable_closeout_{stamp}.json"
    save_json_file(
        audit_path,
        {
            "target_date": target_date.isoformat(),
            "generated_at": now.isoformat(),
            "policy": "18:57 copy-only autofill from visible PROBABLE_SIZE for unresolved MY_SIZE values",
            "applied_count": len(applied_rows),
            "unresolved_count": len(unresolved_rows),
            "applied_rows": applied_rows,
            "unresolved_rows": unresolved_rows,
        },
    )
    return audit_path


def _maybe_auto_prepare_closeout(
    *,
    client: GoogleOpsBoardClient,
    contract,
    db_path: Path,
    target_date,
    lookback_days: int,
    now,
) -> dict[str, object]:
    if not auto_probable_closeout_cutoff_reached(now):
        return {
            "cutoff_reached": False,
            "salesraw_updates_applied": 0,
            "run_control_updated": False,
            "blank_rows_remaining": [],
        }

    salesraw_headers = contract.tabs["SalesRaw_Today"].headers
    run_control_headers = contract.tabs["Run_Control"].headers
    salesraw_rows_with_positions = extract_rows_with_positions_from_matrix(
        salesraw_headers,
        client.get_tab_values("SalesRaw_Today"),
    )
    run_control_rows_with_positions = extract_rows_with_positions_from_matrix(
        run_control_headers,
        client.get_tab_values("Run_Control"),
    )

    target_iso = target_date.isoformat()
    run_control_selected = next(
        (
            row_info
            for row_info in run_control_rows_with_positions
            if _clean(row_info["row"].get("target_date")) == target_iso
        ),
        None,
    )
    if run_control_selected is None:
        return {
            "cutoff_reached": True,
            "target_date_match": False,
            "salesraw_updates_applied": 0,
            "applied_rows": [],
            "audit_path": "",
            "run_control_updated": False,
            "blank_rows_remaining": [],
            "blocked_reason": "Run_Control has no exact target-date row; no Sheet write performed",
        }

    enabled_store_codes = {
        normalize_store_code(value) for value in load_sync_enabled_kaspi_store_codes()
    }
    if load_storeb_packing_excluded(warn=lambda _message: None):
        enabled_store_codes.discard("STOREB")
    scoped_salesraw_rows = [
        row_info
        for row_info in salesraw_rows_with_positions
        if _auto_fill_row_is_in_scope(
            dict(row_info["row"]),
            target_date=target_date,
            enabled_store_codes=enabled_store_codes,
        )
    ]
    out_of_scope_row_count = len(salesraw_rows_with_positions) - len(scoped_salesraw_rows)

    visible_db_row_ids = {
        _clean(row_info["row"].get("_db_row_id"))
        for row_info in scoped_salesraw_rows
        if _clean(row_info["row"].get("_db_row_id"))
    }
    db_rows = load_db_rows_for_writeback(db_path, visible_db_row_ids)

    salesraw_updates: list[dict[str, object]] = []
    unresolved_rows: list[dict[str, object]] = []
    applied_rows: list[dict[str, str]] = []
    for row_info in scoped_salesraw_rows:
        row = dict(row_info["row"])
        if _clean(row.get("MY_SIZE")):
            continue
        db_row = db_rows.get(_clean(row.get("_db_row_id"))) or {}
        resolved_size, resolved_source = _derive_auto_fill_size(row=row, db_row=db_row, db_path=db_path)
        if not resolved_size:
            unresolved_rows.append(
                {
                    "_db_row_id": _clean(row.get("_db_row_id")),
                    "OrderID": _clean(row.get("OrderID")),
                    "STORE_NAME": _clean(row.get("STORE_NAME")),
                    "KASPI_OFFER_NAME": _clean(row.get("KASPI_OFFER_NAME")),
                    "PROBABLE_SIZE": _clean(row.get("PROBABLE_SIZE")),
                    "reason": resolved_source,
                }
            )
            continue
        row["MY_SIZE"] = resolved_size
        salesraw_updates.append({"sheet_row": int(row_info["sheet_row"]), "row": row})
        applied_rows.append(
            {
                "_db_row_id": _clean(row.get("_db_row_id")),
                "OrderID": _clean(row.get("OrderID")),
                "MY_SIZE": resolved_size,
                "source": resolved_source,
            }
        )

    if salesraw_updates:
        allowed, _, gate = _revalidate_watch_mutation(
            client=client,
            contract=contract,
            target_date=target_date,
            now=now,
        )
        if not allowed:
            return {
                "cutoff_reached": True,
                "salesraw_updates_applied": 0,
                "applied_rows": [],
                "audit_path": "",
                "run_control_updated": False,
                "blank_rows_remaining": unresolved_rows,
                "out_of_scope_rows_skipped": out_of_scope_row_count,
                "blocked_reason": f"local_halt_barrier:{_clean(gate.get('reason'))}",
            }
        client.update_tab_rows("SalesRaw_Today", salesraw_headers, salesraw_updates)

    run_control_updated = False
    if not unresolved_rows:
        allowed, current_run_control, gate = _revalidate_watch_mutation(
            client=client,
            contract=contract,
            target_date=target_date,
            now=now,
        )
        if not allowed:
            audit_path = _write_auto_probable_audit(
                target_date=target_date,
                now=now,
                applied_rows=applied_rows if salesraw_updates else [],
                unresolved_rows=unresolved_rows,
            )
            return {
                "cutoff_reached": True,
                "salesraw_updates_applied": len(salesraw_updates),
                "applied_rows": applied_rows,
                "audit_path": str(audit_path) if audit_path else "",
                "run_control_updated": False,
                "blank_rows_remaining": unresolved_rows,
                "out_of_scope_rows_skipped": out_of_scope_row_count,
                "blocked_reason": f"local_halt_barrier:{_clean(gate.get('reason'))}",
            }
        run_control_selected = current_run_control
        run_control_row = dict(run_control_selected["row"])
        ready_value = _clean(run_control_row.get("ready_for_closeout")).upper()
        note_bits: list[str] = []
        if applied_rows:
            note_bits.append(f"AUTO_1857 probable backfill: {len(applied_rows)} row(s)")
        if ready_value != "READY":
            note_bits.append("AUTO_1857 closeout trigger")
        if note_bits:
            run_control_row["ready_for_closeout"] = "READY"
            run_control_row["ready_set_by"] = AUTO_READY_SET_BY
            run_control_row["ready_set_at"] = now.isoformat()
            run_control_row["notes"] = _append_note(run_control_row.get("notes"), "; ".join(note_bits))
            client.update_tab_rows(
                "Run_Control",
                run_control_headers,
                [{"sheet_row": int(run_control_selected["sheet_row"]), "row": run_control_row}],
            )
            run_control_updated = True

    audit_path = _write_auto_probable_audit(
        target_date=target_date,
        now=now,
        applied_rows=applied_rows,
        unresolved_rows=unresolved_rows,
    )
    return {
        "cutoff_reached": True,
        "salesraw_updates_applied": len(salesraw_updates),
        "applied_rows": applied_rows,
        "audit_path": str(audit_path) if audit_path else "",
        "run_control_updated": run_control_updated,
        "blank_rows_remaining": unresolved_rows,
        "out_of_scope_rows_skipped": out_of_scope_row_count,
    }


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
    auto_probable_fill_enabled = _auto_probable_fill_enabled(env)
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
    ensure_kaspi_api_call_ledger_env(env, target_date=target_date, project_root=PROJECT_ROOT)
    if env.get("KASPI_API_CALL_LEDGER_PATH"):
        os.environ.setdefault("KASPI_API_CALL_LEDGER_PATH", env["KASPI_API_CALL_LEDGER_PATH"])

    # HOLD is the dominant steady state. Keep it intentionally cheap: one
    # target-date Run_Control read and no SalesRaw, DB, manifest, ledger, or
    # subprocess work. The explicitly enabled 18:57 probable-size fallback is
    # the only reason to continue from HOLD into full readiness evaluation.
    fast_row = select_run_control_row(client=client, contract=contract, target_date=target_date)
    fast_ready_value = _clean((fast_row or {}).get("ready_for_closeout")).upper()
    fallback_due = bool(
        auto_probable_fill_enabled
        and auto_probable_closeout_cutoff_reached(now_almaty())
    )
    if fast_row is None:
        clear_ready_debounce_state(READY_DEBOUNCE_STATE_PATH)
        print(
            "ERROR: Google Ops Board early-closeout watch: target-date "
            "Run_Control row is missing; fail-closed lightweight poll stopped.",
            file=sys.stderr,
        )
        return 1
    if fast_row is not None and fast_ready_value != "READY" and not fallback_due:
        clear_ready_debounce_state(READY_DEBOUNCE_STATE_PATH)
        print("Google Ops Board early-closeout watch: Run_Control is HOLD; lightweight poll complete.")
        return 0

    completion = closeout_completion_state(client=client, contract=contract, target_date=target_date)
    completion_row = dict(completion.get("row") or {})
    barrier_now = now_almaty()
    halt_gate = evaluate_closeout_halt_barrier(
        target_date=target_date,
        run_control_row=completion_row,
        request_ready_set_at=_clean(completion_row.get("ready_set_at")),
        now=barrier_now,
    )
    if halt_gate.get("allow_fresh_blank_ready"):
        _stamp_blank_ready_identity(
            client=client,
            contract=contract,
            target_date=target_date,
            now=barrier_now,
        )
        completion = closeout_completion_state(
            client=client,
            contract=contract,
            target_date=target_date,
        )
        completion_row = dict(completion.get("row") or {})
        halt_gate = evaluate_closeout_halt_barrier(
            target_date=target_date,
            run_control_row=completion_row,
            request_ready_set_at=_clean(completion_row.get("ready_set_at")),
            now=barrier_now,
        )
    if halt_gate["blocked"]:
        clear_ready_debounce_state(READY_DEBOUNCE_STATE_PATH)
        print(
            "Google Ops Board early-closeout watch: local halt barrier blocks "
            f"READY processing ({halt_gate['reason']})."
        )
        return 0
    if (
        _clean(completion_row.get("ready_for_closeout")).upper() == "READY"
        and not _clean(completion_row.get("ready_set_at"))
    ):
        if (
            int(completion.get("delivery_manifest_count") or 0) > 0
            or _clean(completion.get("run_id"))
            or _clean(completion.get("status")).upper() == "OK"
        ):
            print(
                "ERROR: READY has no ready_set_at but prior closeout/delivery evidence exists; "
                "refusing to invent an ambiguous request identity.",
                file=sys.stderr,
            )
            return 1
        _stamp_blank_ready_identity(
            client=client,
            contract=contract,
            target_date=target_date,
            now=now_almaty(),
        )
        completion = closeout_completion_state(
            client=client,
            contract=contract,
            target_date=target_date,
        )
    if completion["completed"]:
        clear_ready_debounce_state(READY_DEBOUNCE_STATE_PATH)
        run_id = completion["run_id"] or "unknown"
        print(
            f"Google Ops Board early-closeout watch: exact Ready request already completed for "
            f"{completion['target_date']} (run_id={run_id}); skipping."
        )
        return 0
    if completion["status"] == "OK":
        print(
            "Google Ops Board early-closeout watch: Run_Control is OK but delivery is incomplete "
            f"(delivery_status={completion.get('delivery_status')}, "
            f"confirmed={completion.get('delivery_confirmed_count')}/{completion.get('delivery_manifest_count')}); "
            "continuing readiness checks."
        )

    local_now = now_almaty()
    readiness = build_readiness_report(
        client=client,
        contract=contract,
        db_path=DB_PATH,
        target_date=target_date,
        lookback_days=5,
    )
    cutoff_reached = auto_probable_closeout_cutoff_reached(local_now)
    auto_prepare = {
        "cutoff_reached": cutoff_reached,
        "salesraw_updates_applied": 0,
        "run_control_updated": False,
        "blank_rows_remaining": [],
    }
    if auto_probable_fill_enabled and cutoff_reached and (
        readiness["blank_size_count"] > 0 or not readiness["run_control_ready_ok"]
    ):
        auto_prepare = _maybe_auto_prepare_closeout(
            client=client,
            contract=contract,
            db_path=DB_PATH,
            target_date=target_date,
            lookback_days=5,
            now=local_now,
        )
        readiness = build_readiness_report(
            client=client,
            contract=contract,
            db_path=DB_PATH,
            target_date=target_date,
            lookback_days=5,
        )

    if not readiness["ready"]:
        clear_ready_debounce_state(READY_DEBOUNCE_STATE_PATH)
        _mark_recoverable_ready_block(
            client=client,
            contract=contract,
            target_date=target_date,
            readiness=readiness,
            now=local_now,
        )
        auto_bits = []
        if cutoff_reached:
            auto_bits.append(f"cutoff_reached=True")
            auto_bits.append(
                f"auto_probable_fill={'enabled' if auto_probable_fill_enabled else 'disabled'}"
            )
            auto_bits.append(f"auto_filled={auto_prepare['salesraw_updates_applied']}")
            auto_bits.append(f"auto_ready={auto_prepare['run_control_updated']}")
            auto_bits.append(f"blanks_remaining={len(auto_prepare['blank_rows_remaining'])}")
        print(
            "Google Ops Board early-closeout watch: not ready yet "
            f"(ready_toggle={readiness['run_control_ready_ok']}, "
            f"blank_sizes={readiness['blank_size_count']}, "
            f"invalid_sizes={readiness['invalid_size_count']}"
            + (", " + ", ".join(auto_bits) if auto_bits else "")
            + ")."
        )
        return 0

    auto_fallback_just_prepared = bool(
        auto_prepare["salesraw_updates_applied"] or auto_prepare["run_control_updated"]
    )
    if cutoff_reached and auto_fallback_just_prepared:
        clear_ready_debounce_state(READY_DEBOUNCE_STATE_PATH)
        print(
            "Google Ops Board early-closeout watch: 18:57 fallback is green; "
            "triggering closeout immediately."
        )
        fresh_readiness = build_readiness_report(
            client=client,
            contract=contract,
            db_path=DB_PATH,
            target_date=target_date,
            lookback_days=5,
        )
        if (
            not fresh_readiness["ready"]
            or _clean(fresh_readiness.get("ready_set_at"))
            != _clean(readiness.get("ready_set_at"))
        ):
            print(
                "Google Ops Board early-closeout watch: READY identity changed before launch; "
                "deferring to a fresh scheduler pass."
            )
            return 0
        launch_allowed, _, launch_gate = _revalidate_watch_mutation(
            client=client,
            contract=contract,
            target_date=target_date,
            now=now_almaty(),
        )
        if not launch_allowed:
            clear_ready_debounce_state(READY_DEBOUNCE_STATE_PATH)
            print(
                "Google Ops Board early-closeout watch: local halt barrier appeared "
                f"before launch ({_clean(launch_gate.get('reason'))}); skipping."
            )
            return 0
        result = subprocess.run(
            [
                sys.executable,
                str(SCRIPT_PATH),
                "--expected-target-date",
                target_date.isoformat(),
                "--expected-ready-set-at",
                _clean(fresh_readiness.get("ready_set_at")),
            ],
            cwd=str(PROJECT_ROOT),
            env=env,
        )
        return int(result.returncode)

    debounce = evaluate_ready_debounce(
        state=load_ready_debounce_state(READY_DEBOUNCE_STATE_PATH),
        target_date=target_date,
        now=local_now,
        ready=True,
        ready_set_at=_clean(readiness.get("ready_set_at")),
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

    fresh_readiness = build_readiness_report(
        client=client,
        contract=contract,
        db_path=DB_PATH,
        target_date=target_date,
        lookback_days=5,
    )
    if (
        not fresh_readiness["ready"]
        or _clean(fresh_readiness.get("ready_set_at"))
        != _clean(readiness.get("ready_set_at"))
    ):
        clear_ready_debounce_state(READY_DEBOUNCE_STATE_PATH)
        print(
            "Google Ops Board early-closeout watch: READY identity changed before launch; "
            "arming the fresh request on the next pass."
        )
        return 0
    print("Google Ops Board early-closeout watch: board is READY; triggering closeout immediately.")
    launch_allowed, _, launch_gate = _revalidate_watch_mutation(
        client=client,
        contract=contract,
        target_date=target_date,
        now=now_almaty(),
    )
    if not launch_allowed:
        clear_ready_debounce_state(READY_DEBOUNCE_STATE_PATH)
        print(
            "Google Ops Board early-closeout watch: local halt barrier appeared "
            f"before launch ({_clean(launch_gate.get('reason'))}); skipping."
        )
        return 0
    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT_PATH),
            "--expected-target-date",
            target_date.isoformat(),
            "--expected-ready-set-at",
            _clean(fresh_readiness.get("ready_set_at")),
        ],
        cwd=str(PROJECT_ROOT),
        env=env,
    )
    clear_ready_debounce_state(READY_DEBOUNCE_STATE_PATH)
    return int(result.returncode)


if __name__ == "__main__":
    raise SystemExit(run_guarded("run_google_ops_board_closeout_watch_scheduler", main))
