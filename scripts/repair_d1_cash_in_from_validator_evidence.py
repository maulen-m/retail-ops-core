#!/usr/bin/env python3
"""Repair D1 CASH_IN rows for focused missing order-entry candidates.

Default: dry run. Apply requires ENABLE_D1_CASH_IN_REPAIR_WRITE=1.
Production db/app.db apply additionally requires
ENABLE_D1_CASH_IN_REPAIR_PROD_WRITE=1, --expected-pre-sha256, and --backup-dir.

By default this remains limited to recovered CRM entry rows. Passing
--allow-fact-order-entries also permits complete real fact_order_entries_kaspi
ORDER_ENTRY candidates from the validator evidence.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sqlite3
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

DEFAULT_DB = PROJECT_ROOT / "db" / "app.db"
DEFAULT_OUTPUT_ROOT = PROJECT_ROOT / "exports" / "validation" / "d1_cash_in_repair"
WRITE_ENV_GATE = "ENABLE_D1_CASH_IN_REPAIR_WRITE"
PROD_WRITE_ENV_GATE = "ENABLE_D1_CASH_IN_REPAIR_PROD_WRITE"

from core.cashflow.order_cashflow_validation import (  # noqa: E402
    _build_d1_candidates,
    _candidate_cash_rows,
    _cash_rows,
    _matching_positive_cash,
    _positive_cash_index,
    evaluate_order_cashflow_coverage_conn,
)
from scripts.backup_db import backup_database  # noqa: E402
from scripts.translate_orders_to_cashflow_events import (  # noqa: E402
    _allocate_seller_delivery_fee,
    _event_hash,
    _load_dim_sku_weights,
    _load_order_seller_delivery_fees,
    _net_cash_amount_for_line,
)


class D1CashInRepairError(RuntimeError):
    """Raised when the focused D1 cash-in repair cannot prove safety."""


def _json_default(value: Any) -> Any:
    if isinstance(value, Path):
        return str(value)
    return str(value)


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True, default=_json_default) + "\n",
        encoding="utf-8",
    )


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "".join(json.dumps(row, ensure_ascii=False, sort_keys=True, default=_json_default) + "\n" for row in rows),
        encoding="utf-8",
    )


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _sqlite_integrity_check(path: Path) -> str:
    conn = sqlite3.connect(str(path))
    try:
        row = conn.execute("PRAGMA integrity_check").fetchone()
        return str(row[0]) if row else "missing"
    finally:
        conn.close()


def _sidecar_paths(db_path: Path) -> list[Path]:
    return [db_path.with_name(db_path.name + suffix) for suffix in ("-wal", "-shm", "-journal")]


def _fail_on_sqlite_sidecars(db_path: Path) -> None:
    existing = [path for path in _sidecar_paths(db_path) if path.exists()]
    if existing:
        joined = ", ".join(str(path) for path in existing)
        raise D1CashInRepairError(f"refusing production D1 cash-in repair while SQLite sidecars exist: {joined}")


def _is_production_db(db_path: Path) -> bool:
    return db_path.resolve() == DEFAULT_DB.resolve()


def _prepare_apply_guard(
    db_path: Path,
    *,
    expected_pre_sha256: str | None,
    backup_dir: Path | None,
) -> dict[str, Any]:
    if os.environ.get(WRITE_ENV_GATE) != "1":
        raise D1CashInRepairError(f"{WRITE_ENV_GATE}=1 is required to apply D1 cash-in repair.")

    production_apply = _is_production_db(db_path)
    metadata: dict[str, Any] = {
        "production_apply": production_apply,
        "pre_sha256": _sha256_file(db_path),
    }
    if not production_apply:
        return metadata

    if os.environ.get(PROD_WRITE_ENV_GATE) != "1":
        raise D1CashInRepairError(f"{PROD_WRITE_ENV_GATE}=1 is required for production D1 cash-in repair.")
    if not expected_pre_sha256:
        raise D1CashInRepairError("--expected-pre-sha256 is required for production D1 cash-in repair.")
    if backup_dir is None:
        raise D1CashInRepairError("--backup-dir is required for production D1 cash-in repair.")

    _fail_on_sqlite_sidecars(db_path)
    pre_integrity = _sqlite_integrity_check(db_path)
    if pre_integrity.lower() != "ok":
        raise D1CashInRepairError(f"production DB integrity_check failed before D1 cash-in repair: {pre_integrity}")
    pre_sha256 = str(metadata["pre_sha256"])
    if pre_sha256 != expected_pre_sha256:
        raise D1CashInRepairError(
            "production DB SHA mismatch before D1 cash-in repair: "
            f"expected {expected_pre_sha256}, observed {pre_sha256}"
        )

    backup_path = backup_database(db_path, backup_dir, compress=False)
    backup_integrity = _sqlite_integrity_check(backup_path)
    if backup_integrity.lower() != "ok":
        raise D1CashInRepairError(f"D1 cash-in backup integrity_check failed: {backup_integrity}")
    metadata.update(
        {
            "expected_pre_sha256": expected_pre_sha256,
            "backup_path": str(backup_path),
            "backup_sha256": _sha256_file(backup_path),
            "pre_integrity_check": pre_integrity,
            "backup_integrity_check": backup_integrity,
        }
    )
    return metadata


def _missing_cash_candidates(conn: sqlite3.Connection, *, as_of: str) -> list[dict[str, Any]]:
    candidates = _build_d1_candidates(conn, as_of=as_of)
    cash_index = _positive_cash_index(_cash_rows(conn))
    line_counts = Counter((candidate["order_id"], candidate["store_code"]) for candidate in candidates)
    missing: list[dict[str, Any]] = []
    for candidate in candidates:
        key = (candidate["order_id"], candidate["store_code"])
        matches = _matching_positive_cash(
            candidate,
            _candidate_cash_rows(candidate, cash_index),
            line_counts.get(key, 1),
        )
        if not matches:
            missing.append(candidate)
    return missing


def _is_allowed_recovered_entry(candidate: dict[str, Any]) -> bool:
    ref_id = str(candidate.get("ref_id") or "")
    return (
        str(candidate.get("ref_type") or "").strip().upper() == "ORDER_ENTRY"
        and ref_id.startswith(("RECOV-CURRENT_CRM-", "RECOV-WORKBOOK-"))
        and bool(str(candidate.get("order_id") or "").strip())
        and bool(str(candidate.get("store_code") or "").strip())
        and bool(str(candidate.get("delivered_date") or "").strip())
        and float(candidate.get("quantity") or 0.0) > 0
        and float(candidate.get("amount_basis_kzt") or 0.0) > 0
    )


def _is_allowed_fact_order_entry(candidate: dict[str, Any]) -> bool:
    ref_id = str(candidate.get("ref_id") or "")
    return (
        str(candidate.get("ref_type") or "").strip().upper() == "ORDER_ENTRY"
        and str(candidate.get("source") or "").strip() == "fact_order_entries_kaspi"
        and not ref_id.startswith(("RECOV-CURRENT_CRM-", "RECOV-WORKBOOK-"))
        and bool(ref_id.strip())
        and bool(str(candidate.get("order_id") or "").strip())
        and bool(str(candidate.get("store_code") or "").strip())
        and bool(str(candidate.get("delivered_date") or "").strip())
        and float(candidate.get("quantity") or 0.0) > 0
        and float(candidate.get("amount_basis_kzt") or 0.0) > 0
    )


def _seller_delivery_cost_allocations(
    conn: sqlite3.Connection,
    target_candidates: list[dict[str, Any]],
    *,
    allocation_universe: list[dict[str, Any]],
) -> dict[str, float | None]:
    seller_fees, ambiguous_order_keys = _load_order_seller_delivery_fees(conn)
    target_grouped: dict[tuple[str, str], list[dict[str, Any]]] = {}
    universe_grouped: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for candidate in target_candidates:
        order_key = (
            str(candidate.get("order_id") or "").strip(),
            str(candidate.get("store_code") or "").strip().upper(),
        )
        target_grouped.setdefault(order_key, []).append(candidate)
    for candidate in allocation_universe:
        order_key = (
            str(candidate.get("order_id") or "").strip(),
            str(candidate.get("store_code") or "").strip().upper(),
        )
        universe_grouped.setdefault(order_key, []).append(candidate)

    allocations: dict[str, float | None] = {}
    for order_key, targets in target_grouped.items():
        if order_key in ambiguous_order_keys:
            raise D1CashInRepairError(
                f"ambiguous seller delivery fee for {order_key[0]}:{order_key[1]}"
            )
        order_candidates = universe_grouped.get(order_key, [])
        if not order_candidates or any(
            str(candidate.get("ref_type") or "").strip().upper() != "ORDER_ENTRY"
            for candidate in order_candidates
        ):
            raise D1CashInRepairError(
                f"complete ORDER_ENTRY allocation universe unavailable for {order_key[0]}:{order_key[1]}"
            )
        allocation_lines = [
            {
                "quantity": float(candidate.get("quantity") or 0.0),
                "total_price_kzt": float(candidate.get("amount_basis_kzt") or 0.0),
            }
            for candidate in order_candidates
        ]
        _allocate_seller_delivery_fee(allocation_lines, seller_fees.get(order_key))
        by_ref_id: dict[str, float | None] = {}
        for candidate, line in zip(order_candidates, allocation_lines):
            ref_id = str(candidate.get("ref_id") or "").strip()
            if not ref_id or ref_id in by_ref_id:
                raise D1CashInRepairError(
                    f"duplicate or blank ORDER_ENTRY identity in allocation universe for {order_key[0]}:{order_key[1]}"
                )
            by_ref_id[ref_id] = line.get("seller_delivery_cost_total_kzt")
        for target in targets:
            ref_id = str(target.get("ref_id") or "").strip()
            if ref_id not in by_ref_id:
                raise D1CashInRepairError(
                    f"target entry missing from allocation universe: {order_key[0]}:{ref_id}"
                )
            allocations[ref_id] = by_ref_id[ref_id]
    return allocations


def _cash_account(store_code: str) -> str:
    return f"KASPI_PAY_{store_code.strip().upper() or 'UNKNOWN'}"


def _event_from_candidate(
    candidate: dict[str, Any],
    *,
    weights: dict[str, float],
    seller_delivery_costs: dict[str, float | None],
    run_id: str,
) -> dict[str, Any]:
    quantity = float(candidate.get("quantity") or 0.0)
    total = float(candidate.get("amount_basis_kzt") or 0.0)
    unit = round(total / quantity, 4) if quantity else total
    ref_id = str(candidate.get("ref_id") or "").strip()
    line = {
        "quantity": quantity,
        "unit_price_kzt": unit,
        "total_price_kzt": total,
        "sku_key": str(candidate.get("sku_key") or "").strip(),
        "sku_id": str(candidate.get("sku_id") or "").strip(),
        "seller_delivery_cost_total_kzt": seller_delivery_costs.get(ref_id),
    }
    amount = _net_cash_amount_for_line(line, str(candidate["delivered_date"]), weights)
    if amount <= 0:
        raise D1CashInRepairError(
            f"refusing non-positive D1 cash-in amount for {candidate.get('order_id')}:{ref_id}: {amount}"
        )
    event = {
        "event_date": str(candidate["delivered_date"]),
        "event_type": "CASH_IN",
        "account": _cash_account(str(candidate.get("store_code") or "")),
        "amount_kzt": amount,
        "store_code": str(candidate.get("store_code") or "").strip().upper(),
        "sku_key": line["sku_key"],
        "sku_id": line["sku_id"],
        "ref_type": "ORDER_ENTRY",
        "ref_id": ref_id,
        "source": "ORDER_MODELLED",
        "run_id": run_id,
        "notes": f"D1 cash-in from focused validator-evidence repair; order_id={candidate['order_id']}",
    }
    event["event_hash"] = _event_hash(event)
    return event


def repair_d1_cash_in_from_validator_evidence(
    *,
    db_path: Path,
    as_of: str,
    output_root: Path = DEFAULT_OUTPUT_ROOT,
    run_id: str | None = None,
    apply: bool = False,
    expected_missing_count: int | None = None,
    expected_pre_sha256: str | None = None,
    backup_dir: Path | None = None,
    allow_fact_order_entries: bool = False,
) -> dict[str, Any]:
    db_path = db_path.resolve()
    output_root = output_root.resolve()
    run_id = run_id or datetime.now().strftime("%Y%m%d_%H%M%S")
    if not db_path.exists():
        raise FileNotFoundError(f"DB not found: {db_path}")

    apply_metadata: dict[str, Any] = {}
    if apply:
        apply_metadata = _prepare_apply_guard(
            db_path,
            expected_pre_sha256=expected_pre_sha256,
            backup_dir=backup_dir,
        )

    inserted = 0
    with sqlite3.connect(str(db_path)) as conn:
        conn.row_factory = sqlite3.Row
        coverage_before = evaluate_order_cashflow_coverage_conn(conn, as_of=as_of)
        allocation_universe = _build_d1_candidates(conn, as_of=as_of)
        missing = _missing_cash_candidates(conn, as_of=as_of)
        allowed_recovered = [candidate for candidate in missing if _is_allowed_recovered_entry(candidate)]
        allowed_fact_entries = [
            candidate
            for candidate in missing
            if allow_fact_order_entries and _is_allowed_fact_order_entry(candidate)
        ]
        allowed = allowed_recovered + allowed_fact_entries
        allowed_keys = {(candidate.get("ref_type"), candidate.get("ref_id")) for candidate in allowed}
        blocked = [
            candidate
            for candidate in missing
            if (candidate.get("ref_type"), candidate.get("ref_id")) not in allowed_keys
        ]
        if expected_missing_count is not None and len(missing) != expected_missing_count:
            raise D1CashInRepairError(
                f"expected {expected_missing_count} missing D1 cash-in candidates, observed {len(missing)}"
            )
        if blocked:
            if apply:
                raise D1CashInRepairError(
                    f"refusing apply with {len(blocked)} non-recovered-entry missing D1 candidates"
                )
        seller_delivery_costs = _seller_delivery_cost_allocations(
            conn,
            allowed,
            allocation_universe=allocation_universe,
        )
        weights = _load_dim_sku_weights(conn)
        events = [
            _event_from_candidate(
                candidate,
                weights=weights,
                seller_delivery_costs=seller_delivery_costs,
                run_id=run_id,
            )
            for candidate in allowed
        ]
        if events:
            placeholders = ",".join("?" * len(events))
            existing_hashes = {
                str(row[0])
                for row in conn.execute(
                    f"SELECT event_hash FROM fact_cashflow_events WHERE event_hash IN ({placeholders})",
                    [event["event_hash"] for event in events],
                ).fetchall()
            }
        else:
            existing_hashes = set()
        insert_events = [event for event in events if event["event_hash"] not in existing_hashes]

        if apply and insert_events:
            for event in insert_events:
                conn.execute(
                    """
                    INSERT OR IGNORE INTO fact_cashflow_events (
                        event_date, event_type, account, amount_kzt, store_code, sku_key, sku_id,
                        ref_type, ref_id, notes, source, run_id, event_hash
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        event["event_date"],
                        event["event_type"],
                        event["account"],
                        float(event["amount_kzt"]),
                        event.get("store_code"),
                        event.get("sku_key"),
                        event.get("sku_id"),
                        event.get("ref_type"),
                        event.get("ref_id"),
                        event.get("notes"),
                        event.get("source"),
                        event.get("run_id"),
                        event.get("event_hash"),
                    ),
                )
                inserted += 1
            conn.commit()
        coverage_after = evaluate_order_cashflow_coverage_conn(conn, as_of=as_of) if apply else coverage_before

    if apply_metadata.get("production_apply"):
        post_integrity = _sqlite_integrity_check(db_path)
        if post_integrity.lower() != "ok":
            raise D1CashInRepairError(f"production DB integrity_check failed after D1 cash-in repair: {post_integrity}")
        apply_metadata["post_sha256"] = _sha256_file(db_path)
        apply_metadata["post_integrity_check"] = post_integrity

    summary = {
        "status": "PASS" if not blocked else "FAIL",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "db_path": str(db_path),
        "as_of": as_of,
        "run_id": run_id,
        "apply": {
            "applied": bool(apply),
            "inserted_event_rows": inserted if apply else 0,
            "would_insert_event_rows": len(insert_events),
            **apply_metadata,
        },
        "coverage_before": {
            "status": coverage_before.get("status"),
            "cash_in_missing_count": coverage_before.get("cash_in_missing_count"),
            "duplicate_cash_in_count": coverage_before.get("duplicate_cash_in_count"),
            "missing_line_evidence_count": coverage_before.get("missing_line_evidence_count"),
            "modeled_receivables_count": coverage_before.get("modeled_receivables_count"),
        },
        "coverage_after": {
            "status": coverage_after.get("status"),
            "cash_in_missing_count": coverage_after.get("cash_in_missing_count"),
            "duplicate_cash_in_count": coverage_after.get("duplicate_cash_in_count"),
            "missing_line_evidence_count": coverage_after.get("missing_line_evidence_count"),
            "modeled_receivables_count": coverage_after.get("modeled_receivables_count"),
        },
        "missing_candidate_count": len(missing),
        "allowed_recovered_entry_count": len(allowed_recovered),
        "allowed_fact_order_entry_count": len(allowed_fact_entries),
        "blocked_candidate_count": len(blocked),
        "already_present_event_rows": len(events) - len(insert_events),
    }
    _write_json(output_root / "summary.json", summary)
    _write_jsonl(output_root / "candidate_events.jsonl", events)
    _write_jsonl(output_root / "blocked_candidates.jsonl", blocked)
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description="Repair D1 CASH_IN rows for recovered order entries only")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument("--as-of", required=True)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--run-id", default=None)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--expected-missing-count", type=int, default=None)
    parser.add_argument("--expected-pre-sha256", default=None)
    parser.add_argument("--backup-dir", type=Path, default=None)
    parser.add_argument(
        "--allow-fact-order-entries",
        action="store_true",
        help="Permit complete fact_order_entries_kaspi ORDER_ENTRY candidates in addition to recovered CRM rows.",
    )
    args = parser.parse_args()

    summary = repair_d1_cash_in_from_validator_evidence(
        db_path=args.db,
        as_of=args.as_of,
        output_root=args.output_root,
        run_id=args.run_id,
        apply=args.apply,
        expected_missing_count=args.expected_missing_count,
        expected_pre_sha256=args.expected_pre_sha256,
        backup_dir=args.backup_dir,
        allow_fact_order_entries=bool(args.allow_fact_order_entries),
    )
    print(f"status={summary['status']}")
    print(f"missing_candidate_count={summary['missing_candidate_count']}")
    print(f"allowed_recovered_entry_count={summary['allowed_recovered_entry_count']}")
    print(f"allowed_fact_order_entry_count={summary['allowed_fact_order_entry_count']}")
    print(f"blocked_candidate_count={summary['blocked_candidate_count']}")
    print(f"would_insert_event_rows={summary['apply']['would_insert_event_rows']}")
    print(f"inserted_event_rows={summary['apply']['inserted_event_rows']}")
    print(f"coverage_after_cash_in_missing={summary['coverage_after']['cash_in_missing_count']}")
    print(f"summary_json={args.output_root / 'summary.json'}")
    return 0 if summary["status"] == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
