#!/usr/bin/env python3
"""Materialize source-backed governed stock repair events.

Dry-run is the default. Apply requires ENABLE_GOVERNED_STOCK_REPAIR_WRITE=1.
Production DB apply also requires ALLOW_PRODUCTION_GOVERNED_STOCK_REPAIR_WRITE=1.
"""

from __future__ import annotations

import argparse
import csv
from dataclasses import dataclass
import json
import os
from pathlib import Path
import sqlite3
import sys
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from core.db import DEFAULT_DB_PATH
from scripts.backup_db import backup_database


ENV_GATE = "ENABLE_GOVERNED_STOCK_REPAIR_WRITE"
PRODUCTION_ENV_GATE = "ALLOW_PRODUCTION_GOVERNED_STOCK_REPAIR_WRITE"
DEFAULT_MANIFEST = PROJECT_ROOT / "config" / "governed_stock_repair_events_20260613.json"
RECEIVED_STATUSES = {"RECEIVED", "ARRIVED", "CLOSED", "DONE"}
OWNER_APPROVAL_REPAIR_TYPES = {
    "owner_parent_child_allocation_delta",
    "owner_manual_stock_fact_delta",
}


@dataclass(frozen=True)
class RepairPlan:
    summary: dict[str, Any]
    events: list[dict[str, Any]]
    blocked_rows: list[dict[str, Any]]
    existing_rows: list[dict[str, Any]]

    @property
    def is_safe_to_apply(self) -> bool:
        return not self.blocked_rows


def _connect(db_path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    return conn


def _table_exists(conn: sqlite3.Connection, table: str) -> bool:
    return (
        conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
            (table,),
        ).fetchone()
        is not None
    )


def _resolve_path(path_text: str) -> Path:
    path = Path(path_text).expanduser()
    if not path.is_absolute():
        path = PROJECT_ROOT / path
    return path


def _load_manifest(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _normalize_path(path: Path) -> Path:
    return path.expanduser().resolve()


def _normalize_evidence_paths(paths: list[Path] | None) -> list[Path]:
    return [_normalize_path(_resolve_path(str(path))) for path in paths or []]


def _is_forbidden_approval_evidence_path(path: Path) -> bool:
    parts = path.parts
    return any(
        parts[index : index + 2] == ("docs", "agent_handoffs")
        for index in range(max(len(parts) - 1, 0))
    )


def _approval_definitions(manifest: dict[str, Any]) -> dict[str, dict[str, Any]]:
    approvals = manifest.get("approvals") or {}
    if isinstance(approvals, dict):
        return {str(key): dict(value or {}) for key, value in approvals.items()}
    if isinstance(approvals, list):
        out: dict[str, dict[str, Any]] = {}
        for item in approvals:
            if isinstance(item, dict) and item.get("approval_id"):
                out[str(item["approval_id"])] = dict(item)
        return out
    return {}


def _read_manual_count_csv(path: Path) -> dict[str, dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        rows = [dict(row) for row in csv.DictReader(handle)]
    return {str(row.get("stock_pool_id") or "").strip(): row for row in rows}


def _as_int(value: Any) -> int:
    try:
        return int(round(float(value or 0)))
    except (TypeError, ValueError):
        return 0


def _upper(value: Any) -> str:
    return str(value or "").strip().upper()


def _current_balances(conn: sqlite3.Connection) -> dict[tuple[str, str], int]:
    rows = conn.execute(
        """
        SELECT sku_id, UPPER(COALESCE(store_code, 'UNIVERSAL')) AS store_code,
               COALESCE(SUM(qty_change), 0) AS balance
        FROM stock_ledger
        GROUP BY sku_id, UPPER(COALESCE(store_code, 'UNIVERSAL'))
        """
    ).fetchall()
    return {(str(row["sku_id"]), str(row["store_code"])): int(row["balance"] or 0) for row in rows}


def _existing_idempotency_keys(conn: sqlite3.Connection, keys: list[str]) -> set[str]:
    if not keys:
        return set()
    placeholders = ",".join("?" for _ in keys)
    rows = conn.execute(
        f"SELECT idempotency_key FROM stock_ledger WHERE idempotency_key IN ({placeholders})",
        keys,
    ).fetchall()
    return {str(row["idempotency_key"]) for row in rows}


def _validate_manual_count_repair(
    repair: dict[str, Any],
    *,
    manual_cache: dict[Path, dict[str, dict[str, str]]],
    allocation_totals: dict[tuple[Path, str], int],
) -> list[str]:
    errors: list[str] = []
    source_path = _resolve_path(str(repair.get("source_artifact_path") or ""))
    if not source_path.exists():
        return [f"MANUAL_COUNT_SOURCE_MISSING:{source_path}"]
    if source_path not in manual_cache:
        manual_cache[source_path] = _read_manual_count_csv(source_path)
    stock_pool_id = str(repair.get("source_stock_pool_id") or "").strip()
    source_row = manual_cache[source_path].get(stock_pool_id)
    if source_row is None:
        return [f"MANUAL_COUNT_STOCK_POOL_MISSING:{stock_pool_id}"]
    expected_status = str(repair.get("source_status") or "").strip()
    if expected_status and str(source_row.get("status") or "").strip() != expected_status:
        errors.append(
            f"MANUAL_COUNT_STATUS_MISMATCH:{stock_pool_id}:{source_row.get('status')}!={expected_status}"
        )
    quantity = _as_int(source_row.get("quantity"))
    min_quantity = _as_int(repair.get("source_min_quantity"))
    if min_quantity and quantity < min_quantity:
        errors.append(f"MANUAL_COUNT_QUANTITY_BELOW_MIN:{stock_pool_id}:{quantity}<{min_quantity}")
    allocated = allocation_totals.get((source_path, stock_pool_id), 0)
    if allocated > quantity:
        errors.append(f"MANUAL_COUNT_ALLOCATION_EXCEEDS_SOURCE:{stock_pool_id}:{allocated}>{quantity}")
    return errors


def _validate_po_line_repair(conn: sqlite3.Connection, repair: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if not _table_exists(conn, "po_line") or not _table_exists(conn, "po_part"):
        return ["PO_LINE_TABLES_MISSING"]
    row = conn.execute(
        """
        SELECT pl.*, pp.actual_arrival_date AS part_actual_arrival_date,
               pp.status AS part_status
        FROM po_line pl
        LEFT JOIN po_part pp ON pp.po_part_id = pl.po_part_id
        WHERE pl.po_line_id = ?
        """,
        (repair.get("source_po_line_id"),),
    ).fetchone()
    if row is None:
        return [f"PO_LINE_SOURCE_MISSING:{repair.get('source_po_line_id')}"]
    if str(row["sku_id"] or "").strip() != str(repair.get("sku_id") or "").strip():
        errors.append(f"PO_LINE_SKU_ID_MISMATCH:{row['sku_id']}!={repair.get('sku_id')}")
    if str(row["po_part_id"] or "").strip() != str(repair.get("source_po_part_id") or "").strip():
        errors.append(f"PO_LINE_PART_MISMATCH:{row['po_part_id']}!={repair.get('source_po_part_id')}")
    received_qty = _as_int(row["received_qty"])
    if received_qty < _as_int(repair.get("source_min_received_qty")):
        errors.append(
            f"PO_LINE_RECEIVED_QTY_BELOW_MIN:{repair.get('source_po_line_id')}:{received_qty}<{repair.get('source_min_received_qty')}"
        )
    if _as_int(repair.get("qty_change")) > received_qty:
        errors.append(
            f"PO_LINE_REPAIR_QTY_EXCEEDS_RECEIVED:{repair.get('source_po_line_id')}:{repair.get('qty_change')}>{received_qty}"
        )
    if _upper(row["status"]) not in RECEIVED_STATUSES and received_qty <= 0:
        errors.append(f"PO_LINE_NOT_RECEIVED:{repair.get('source_po_line_id')}:{row['status']}")
    actual_arrival = str(row["part_actual_arrival_date"] or "").strip()
    if actual_arrival and actual_arrival[:10] != str(repair.get("event_date") or "")[:10]:
        errors.append(
            f"PO_LINE_EVENT_DATE_MISMATCH:{repair.get('source_po_line_id')}:{actual_arrival}!={repair.get('event_date')}"
        )
    return errors


def _validate_owner_approval_repair(
    repair: dict[str, Any],
    *,
    manifest: dict[str, Any],
    manifest_path: Path,
    approval_evidence_paths: list[Path],
) -> list[str]:
    errors: list[str] = []
    approval_id = str(repair.get("approval_id") or "").strip()
    if not approval_id:
        return ["APPROVAL_ID_MISSING"]
    approval = _approval_definitions(manifest).get(approval_id)
    if approval is None:
        return [f"APPROVAL_DEFINITION_MISSING:{approval_id}"]
    required_phrase = str(approval.get("required_phrase") or "").strip()
    if not required_phrase:
        return [f"APPROVAL_REQUIRED_PHRASE_MISSING:{approval_id}"]
    if not approval_evidence_paths:
        return [f"APPROVAL_EVIDENCE_MISSING:{approval_id}"]

    valid_texts: list[str] = []
    manifest_resolved = _normalize_path(manifest_path)
    for evidence_path in approval_evidence_paths:
        if evidence_path == manifest_resolved:
            errors.append(f"APPROVAL_EVIDENCE_MUST_BE_SEPARATE_FROM_MANIFEST:{approval_id}")
            continue
        if _is_forbidden_approval_evidence_path(evidence_path):
            errors.append(f"APPROVAL_EVIDENCE_HANDOFF_PATH_FORBIDDEN:{approval_id}:{evidence_path}")
            continue
        if not evidence_path.exists() or not evidence_path.is_file():
            errors.append(f"APPROVAL_EVIDENCE_FILE_MISSING:{approval_id}:{evidence_path}")
            continue
        valid_texts.append(evidence_path.read_text(encoding="utf-8"))
    if not valid_texts:
        return errors or [f"APPROVAL_EVIDENCE_MISSING:{approval_id}"]
    if not any(required_phrase in text for text in valid_texts):
        errors.append(f"APPROVAL_EXACT_PHRASE_NOT_FOUND:{approval_id}")
    return errors


def _build_event(
    repair: dict[str, Any],
    *,
    manifest_run_id: str,
    current_balance: int,
) -> dict[str, Any]:
    repair_id = str(repair["repair_id"])
    qty_change = _as_int(repair["qty_change"])
    return {
        "repair_id": repair_id,
        "event_date": str(repair["event_date"]),
        "event_type": str(repair["event_type"]),
        "sku_key": str(repair["sku_key"]),
        "sku_id": str(repair["sku_id"]),
        "my_size": str(repair["my_size"]),
        "store_code": _upper(repair.get("store_code") or "UNIVERSAL") or "UNIVERSAL",
        "qty_change": qty_change,
        "current_balance_before": current_balance,
        "reference_id": str(repair["reference_id"]),
        "reference_type": str(repair["reference_type"]),
        "kaspi_offer_name": "",
        "notes": str(repair.get("notes") or repair.get("source_basis") or ""),
        "input_source": str(repair.get("input_source") or "GOVERNED_STOCK_REPAIR_SOURCE_BACKED"),
        "created_by": str(repair.get("created_by") or "orchestrator_greenpath_20260613"),
        "idempotency_key": str(
            repair.get("idempotency_key")
            or f"GOVERNED_STOCK_REPAIR:{manifest_run_id}:{repair_id}"
        ),
        "source_basis": str(repair.get("source_basis") or ""),
    }


def build_governed_stock_repair_plan(
    conn: sqlite3.Connection,
    *,
    manifest_path: Path,
    approval_evidence_paths: list[Path] | None = None,
) -> RepairPlan:
    required = {"stock_ledger"}
    missing = sorted(table for table in required if not _table_exists(conn, table))
    if missing:
        return RepairPlan(
            summary={"missing_tables": missing, "is_safe_to_apply": False},
            events=[],
            blocked_rows=[{"reason": "MISSING_TABLES", "missing_tables": missing}],
            existing_rows=[],
        )

    manifest = _load_manifest(manifest_path)
    manifest_run_id = str(manifest.get("run_id") or manifest_path.stem)
    repairs = list(manifest.get("repairs") or [])
    normalized_approval_paths = _normalize_evidence_paths(approval_evidence_paths)
    keys = [
        str(repair.get("idempotency_key") or f"GOVERNED_STOCK_REPAIR:{manifest_run_id}:{repair.get('repair_id')}")
        for repair in repairs
    ]
    existing_keys = _existing_idempotency_keys(conn, keys)
    balances = _current_balances(conn)
    manual_cache: dict[Path, dict[str, dict[str, str]]] = {}
    allocation_totals: dict[tuple[Path, str], int] = {}
    for repair in repairs:
        if repair.get("repair_type") == "manual_count_size_alias_delta":
            source_path = _resolve_path(str(repair.get("source_artifact_path") or ""))
            stock_pool_id = str(repair.get("source_stock_pool_id") or "").strip()
            allocation_totals[(source_path, stock_pool_id)] = allocation_totals.get(
                (source_path, stock_pool_id),
                0,
            ) + _as_int(repair.get("qty_change"))

    events: list[dict[str, Any]] = []
    blocked_rows: list[dict[str, Any]] = []
    existing_rows: list[dict[str, Any]] = []
    for repair in repairs:
        repair_id = str(repair.get("repair_id") or "")
        key = str(
            repair.get("idempotency_key")
            or f"GOVERNED_STOCK_REPAIR:{manifest_run_id}:{repair_id}"
        )
        if key in existing_keys:
            existing_rows.append({"repair_id": repair_id, "idempotency_key": key})
            continue
        errors: list[str] = []
        qty_change = _as_int(repair.get("qty_change"))
        if not repair_id:
            errors.append("REPAIR_ID_MISSING")
        if qty_change <= 0:
            errors.append(f"QTY_CHANGE_NOT_POSITIVE:{qty_change}")
        balance_key = (
            str(repair.get("sku_id") or ""),
            _upper(repair.get("store_code") or "UNIVERSAL") or "UNIVERSAL",
        )
        current_balance = balances.get(balance_key, 0)
        if "expected_current_balance" in repair:
            expected = _as_int(repair.get("expected_current_balance"))
            if current_balance != expected:
                errors.append(f"CURRENT_BALANCE_MISMATCH:{current_balance}!={expected}")
        if current_balance >= 0:
            errors.append(f"CURRENT_BALANCE_NOT_NEGATIVE:{current_balance}")
        if current_balance + qty_change < 0:
            errors.append(f"REPAIR_DOES_NOT_CLEAR_NEGATIVE:{current_balance}+{qty_change}<0")

        repair_type = str(repair.get("repair_type") or "")
        if repair_type == "manual_count_size_alias_delta":
            errors.extend(
                _validate_manual_count_repair(
                    repair,
                    manual_cache=manual_cache,
                    allocation_totals=allocation_totals,
                )
            )
        elif repair_type == "po_line_received_delta":
            errors.extend(_validate_po_line_repair(conn, repair))
        elif repair_type in OWNER_APPROVAL_REPAIR_TYPES:
            errors.extend(
                _validate_owner_approval_repair(
                    repair,
                    manifest=manifest,
                    manifest_path=manifest_path,
                    approval_evidence_paths=normalized_approval_paths,
                )
            )
        else:
            errors.append(f"UNKNOWN_REPAIR_TYPE:{repair_type}")

        if errors:
            blocked_rows.append(
                {
                    "repair_id": repair_id,
                    "sku_id": repair.get("sku_id"),
                    "store_code": balance_key[1],
                    "current_balance": current_balance,
                    "qty_change": qty_change,
                    "errors": ";".join(errors),
                }
            )
            continue
        events.append(
            _build_event(repair, manifest_run_id=manifest_run_id, current_balance=current_balance)
        )

    summary = {
        "manifest_path": str(manifest_path),
        "manifest_run_id": manifest_run_id,
        "approval_evidence_paths": [str(path) for path in normalized_approval_paths],
        "approval_ids_required": sorted(
            {
                str(repair.get("approval_id"))
                for repair in repairs
                if repair.get("repair_type") in OWNER_APPROVAL_REPAIR_TYPES
                and repair.get("approval_id")
            }
        ),
        "repair_count": len(repairs),
        "candidate_event_count": len(events),
        "blocked_count": len(blocked_rows),
        "existing_count": len(existing_rows),
        "is_safe_to_apply": not blocked_rows,
    }
    return RepairPlan(
        summary=summary,
        events=events,
        blocked_rows=blocked_rows,
        existing_rows=existing_rows,
    )


def _apply_events(conn: sqlite3.Connection, events: list[dict[str, Any]]) -> int:
    balances = _current_balances(conn)
    inserted = 0
    for event in events:
        balance_key = (str(event["sku_id"]), str(event["store_code"]))
        running_balance = balances.get(balance_key, 0) + int(event["qty_change"])
        cursor = conn.execute(
            """
            INSERT OR IGNORE INTO stock_ledger (
                event_date, event_type, sku_key, sku_id, my_size, store_code,
                qty_change, running_balance, reference_id, reference_type,
                kaspi_offer_name, notes, input_source, created_by, idempotency_key
            ) VALUES (
                :event_date, :event_type, :sku_key, :sku_id, :my_size, :store_code,
                :qty_change, :running_balance, :reference_id, :reference_type,
                :kaspi_offer_name, :notes, :input_source, :created_by, :idempotency_key
            )
            """,
            {**event, "running_balance": running_balance},
        )
        if cursor.rowcount:
            balances[balance_key] = running_balance
            inserted += 1
    return inserted


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = sorted({key for row in rows for key in row.keys()})
    with path.open("w", newline="", encoding="utf-8") as handle:
        if not fields:
            handle.write("\n")
            return
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def _assert_apply_allowed(db_path: Path) -> None:
    if os.environ.get(ENV_GATE) != "1":
        raise RuntimeError(f"{ENV_GATE}=1 is required for --apply")
    if db_path.resolve() == DEFAULT_DB_PATH.resolve() and os.environ.get(PRODUCTION_ENV_GATE) != "1":
        raise RuntimeError(f"{PRODUCTION_ENV_GATE}=1 is required for production DB apply")


def materialize_governed_stock_repairs(
    *,
    db_path: Path,
    manifest_path: Path,
    output_root: Path,
    apply: bool = False,
    approval_evidence_paths: list[Path] | None = None,
) -> dict[str, Any]:
    if not db_path.exists():
        raise FileNotFoundError(f"DB not found: {db_path}")
    if not manifest_path.exists():
        raise FileNotFoundError(f"manifest not found: {manifest_path}")

    backup_path: Path | None = None
    if apply:
        _assert_apply_allowed(db_path)
        backup_path = backup_database(db_path, output_root / "backups", compress=False)

    with _connect(db_path) as conn:
        plan = build_governed_stock_repair_plan(
            conn,
            manifest_path=manifest_path,
            approval_evidence_paths=approval_evidence_paths,
        )
        if apply and not plan.is_safe_to_apply:
            raise RuntimeError("Governed stock repair plan is not safe to apply; see blocked rows")
        applied_rows = 0
        if apply:
            applied_rows = _apply_events(conn, plan.events)
            conn.commit()

    summary = {
        **plan.summary,
        "applied": apply,
        "applied_rows": applied_rows,
        "db_path": str(db_path),
        "backup_path": str(backup_path) if backup_path else None,
    }
    payload = {
        "summary": summary,
        "outputs": {
            "summary_json": str(output_root / "governed_stock_repair_summary.json"),
            "events_csv": str(output_root / "governed_stock_repair_events.csv"),
            "blocked_csv": str(output_root / "governed_stock_repair_blocked.csv"),
            "existing_csv": str(output_root / "governed_stock_repair_existing.csv"),
        },
    }
    output_root.mkdir(parents=True, exist_ok=True)
    _write_json(output_root / "governed_stock_repair_summary.json", payload)
    _write_csv(output_root / "governed_stock_repair_events.csv", plan.events)
    _write_csv(output_root / "governed_stock_repair_blocked.csv", plan.blocked_rows)
    _write_csv(output_root / "governed_stock_repair_existing.csv", plan.existing_rows)
    return payload


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, default=DEFAULT_DB_PATH)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument(
        "--approval-evidence",
        type=Path,
        action="append",
        default=[],
        help="Path to owner approval evidence text. May be repeated.",
    )
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    try:
        result = materialize_governed_stock_repairs(
            db_path=args.db,
            manifest_path=args.manifest,
            output_root=args.output_root,
            apply=args.apply,
            approval_evidence_paths=args.approval_evidence,
        )
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        summary = result["summary"]
        print(f"applied={summary['applied']}")
        print(f"candidate_event_count={summary['candidate_event_count']}")
        print(f"blocked_count={summary['blocked_count']}")
        print(f"applied_rows={summary['applied_rows']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
