#!/usr/bin/env python3
"""Apply owner/staff return-QC facts into return_qc_event.

Dry-run by default. Production writes require --apply and
ENABLE_RETURN_QC_EVENT_WRITE=1. This script records physical QC facts only; it
does not infer QC outcomes from Kaspi statuses or pickup flags.
"""

from __future__ import annotations

import argparse
import csv
from datetime import datetime
import hashlib
import json
import os
from pathlib import Path
import shutil
import sqlite3
import sys
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

DEFAULT_DB_PATH = PROJECT_ROOT / "db" / "app.db"
DEFAULT_OUTPUT_ROOT = PROJECT_ROOT / "exports" / "validation" / "return_qc_events"
ENV_GATE = "ENABLE_RETURN_QC_EVENT_WRITE"

PASS_STATUSES = {"PASS", "PASSED", "SELLABLE", "ACCEPTED", "OK"}
FAIL_STATUSES = {"FAIL", "FAILED", "DEFECT", "DEFECTIVE", "WRITEOFF", "WRITE_OFF", "SCRAP"}
QUARANTINE_STATUSES = {"QUARANTINE", "PENDING", "HOLD"}
PARTIAL_STATUSES = {"PARTIAL", "MIXED"}
RETURNED_STATUSES = {"RETURNED", "RETURN", "ВОЗВРАЩЕН"}


class ReturnQcApplyError(RuntimeError):
    """Raised when return QC input is unsafe to apply."""


def _norm(value: Any) -> str:
    return str(value or "").strip()


def _upper(value: Any) -> str:
    return _norm(value).upper()


def _int(value: Any, *, default: int = 0) -> int:
    if value is None or _norm(value) == "":
        return default
    try:
        return int(round(float(value)))
    except (TypeError, ValueError) as exc:
        raise ReturnQcApplyError(f"invalid integer value: {value!r}") from exc


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _now_stamp() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def _load_rows(csv_path: Path) -> list[dict[str, str]]:
    if not csv_path.exists():
        raise ReturnQcApplyError(f"input CSV not found: {csv_path}")
    with csv_path.open("r", encoding="utf-8-sig", newline="") as fh:
        reader = csv.DictReader(fh)
        if not reader.fieldnames:
            raise ReturnQcApplyError("input CSV has no header")
        rows = [{str(k or "").strip(): _norm(v) for k, v in row.items()} for row in reader]
    return [row for row in rows if any(_norm(v) for v in row.values())]


def _derive_buckets(row: dict[str, str]) -> tuple[int, int, int, int]:
    quantity = _int(row.get("quantity"))
    if quantity <= 0:
        raise ReturnQcApplyError("quantity must be positive")
    explicit = {
        "accepted_active_qty": _norm(row.get("accepted_active_qty")),
        "quarantine_qty": _norm(row.get("quarantine_qty")),
        "rejected_qty": _norm(row.get("rejected_qty")),
        "writeoff_qty": _norm(row.get("writeoff_qty")),
    }
    has_explicit = any(value != "" for value in explicit.values())
    status = _upper(row.get("qc_status"))
    if status in PASS_STATUSES and not has_explicit:
        return quantity, 0, 0, 0
    if status in FAIL_STATUSES and not has_explicit:
        return 0, 0, 0, quantity
    if status in QUARANTINE_STATUSES and not has_explicit:
        return 0, quantity, 0, 0
    if status in PARTIAL_STATUSES and not has_explicit:
        raise ReturnQcApplyError("PARTIAL/MIXED QC rows require explicit quantity buckets")
    if status not in PASS_STATUSES | FAIL_STATUSES | QUARANTINE_STATUSES | PARTIAL_STATUSES:
        raise ReturnQcApplyError(f"unsupported qc_status: {status or '<blank>'}")
    accepted = _int(row.get("accepted_active_qty"))
    quarantine = _int(row.get("quarantine_qty"))
    rejected = _int(row.get("rejected_qty"))
    writeoff = _int(row.get("writeoff_qty"))
    if min(accepted, quarantine, rejected, writeoff) < 0:
        raise ReturnQcApplyError("QC quantity buckets cannot be negative")
    if accepted + quarantine + rejected + writeoff != quantity:
        raise ReturnQcApplyError(
            "QC quantity buckets must sum to quantity "
            f"({accepted}+{quarantine}+{rejected}+{writeoff}!={quantity})"
        )
    return accepted, quarantine, rejected, writeoff


def _idempotency_key(event: dict[str, Any]) -> str:
    parts = [
        "return_qc_event_v1",
        str(event["store_code"]),
        str(event["order_id"]),
        str(event.get("order_entry_id") or ""),
        str(event["sku_id"]),
        str(event["quantity"]),
        str(event["qc_status"]),
        str(event["accepted_active_qty"]),
        str(event["quarantine_qty"]),
        str(event["rejected_qty"]),
        str(event["writeoff_qty"]),
        str(event.get("qc_ts") or ""),
        str(event["source"]),
    ]
    return hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()


def _event_from_row(row: dict[str, str], *, default_source: str) -> dict[str, Any]:
    store_code = _upper(row.get("store_code"))
    order_id = _norm(row.get("order_id"))
    sku_id = _norm(row.get("sku_id"))
    qc_status = _upper(row.get("qc_status"))
    if not store_code or not order_id or not sku_id:
        raise ReturnQcApplyError("store_code, order_id, and sku_id are required")
    accepted, quarantine, rejected, writeoff = _derive_buckets(row)
    quantity = accepted + quarantine + rejected + writeoff
    event = {
        "store_code": store_code,
        "order_id": order_id,
        "order_entry_id": _norm(row.get("order_entry_id")),
        "sku_id": sku_id,
        "quantity": quantity,
        "return_stage": _upper(row.get("return_stage")) or "RETURNED_TO_WAREHOUSE",
        "qc_status": qc_status,
        "qc_ts": _norm(row.get("qc_ts")) or datetime.now().replace(microsecond=0).isoformat(),
        "accepted_active_qty": accepted,
        "quarantine_qty": quarantine,
        "rejected_qty": rejected,
        "writeoff_qty": writeoff,
        "source": _norm(row.get("source")) or default_source,
    }
    key = _idempotency_key(event)
    event["idempotency_key"] = key
    event["qc_event_id"] = "RETQC-" + key[:24]
    return event


def _order_rows(conn: sqlite3.Connection, event: dict[str, Any]) -> list[sqlite3.Row]:
    return conn.execute(
        """
        SELECT order_id, store_code, sku_id, quantity, internal_status,
               kaspi_status_detail, returned_to_warehouse
        FROM fact_orders_kaspi
        WHERE UPPER(TRIM(COALESCE(store_code, ''))) = ?
          AND TRIM(CAST(order_id AS TEXT)) = ?
          AND COALESCE(TRIM(CAST(sku_id AS TEXT)), '') = ?
        """,
        (event["store_code"], event["order_id"], event["sku_id"]),
    ).fetchall()


def _validate_against_db(conn: sqlite3.Connection, events: list[dict[str, Any]]) -> dict[str, Any]:
    existing_keys = {
        str(row[0])
        for row in conn.execute("SELECT idempotency_key FROM return_qc_event").fetchall()
        if row[0]
    }
    planned: list[dict[str, Any]] = []
    skipped_existing = 0
    errors: list[str] = []
    for event in events:
        if event["idempotency_key"] in existing_keys:
            skipped_existing += 1
            continue
        rows = _order_rows(conn, event)
        if not rows:
            errors.append(
                f"{event['store_code']} {event['order_id']} {event['sku_id']}: no matching fact_orders_kaspi row"
            )
            continue
        returned_qty = 0
        returned_flags = 0
        for row in rows:
            status_values = {_upper(row["internal_status"]), _upper(row["kaspi_status_detail"])}
            if status_values & RETURNED_STATUSES:
                returned_qty += max(0, _int(row["quantity"], default=1))
            if _norm(row["returned_to_warehouse"]).lower() in {"1", "true", "yes"}:
                returned_flags += 1
        if returned_qty <= 0:
            errors.append(f"{event['store_code']} {event['order_id']} {event['sku_id']}: order is not RETURNED")
            continue
        if returned_flags <= 0:
            errors.append(
                f"{event['store_code']} {event['order_id']} {event['sku_id']}: returned_to_warehouse is not confirmed"
            )
            continue
        existing_qty = conn.execute(
            """
            SELECT COALESCE(SUM(quantity), 0)
            FROM return_qc_event
            WHERE UPPER(TRIM(COALESCE(store_code, ''))) = ?
              AND TRIM(CAST(order_id AS TEXT)) = ?
              AND COALESCE(TRIM(CAST(sku_id AS TEXT)), '') = ?
            """,
            (event["store_code"], event["order_id"], event["sku_id"]),
        ).fetchone()[0]
        if _int(existing_qty) + int(event["quantity"]) > returned_qty:
            errors.append(
                f"{event['store_code']} {event['order_id']} {event['sku_id']}: "
                f"QC quantity exceeds returned quantity ({_int(existing_qty)}+{event['quantity']}>{returned_qty})"
            )
            continue
        event["returned_quantity"] = returned_qty
        planned.append(event)
    return {
        "planned": planned,
        "skipped_existing": skipped_existing,
        "errors": errors,
    }


def _write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = [
        "qc_event_id",
        "store_code",
        "order_id",
        "order_entry_id",
        "sku_id",
        "quantity",
        "return_stage",
        "qc_status",
        "qc_ts",
        "accepted_active_qty",
        "quarantine_qty",
        "rejected_qty",
        "writeoff_qty",
        "source",
        "idempotency_key",
        "returned_quantity",
    ]
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def _insert_events(conn: sqlite3.Connection, events: list[dict[str, Any]]) -> int:
    if not events:
        return 0
    conn.executemany(
        """
        INSERT INTO return_qc_event (
            qc_event_id, store_code, order_id, order_entry_id, sku_id, quantity,
            return_stage, qc_status, qc_ts, accepted_active_qty, quarantine_qty,
            rejected_qty, writeoff_qty, source, idempotency_key
        ) VALUES (
            :qc_event_id, :store_code, :order_id, :order_entry_id, :sku_id, :quantity,
            :return_stage, :qc_status, :qc_ts, :accepted_active_qty, :quarantine_qty,
            :rejected_qty, :writeoff_qty, :source, :idempotency_key
        )
        """,
        events,
    )
    return len(events)


def apply_return_qc_events(
    *,
    db_path: Path,
    input_csv: Path,
    output_root: Path,
    apply: bool = False,
    backup_dir: Path | None = None,
    expected_pre_sha256: str | None = None,
    default_source: str = "OWNER_STAFF_RETURN_QC_CSV",
) -> dict[str, Any]:
    if not db_path.exists():
        raise ReturnQcApplyError(f"db not found: {db_path}")
    pre_sha = _sha256(db_path)
    if expected_pre_sha256 and pre_sha != expected_pre_sha256:
        raise ReturnQcApplyError(f"pre-sha mismatch: expected {expected_pre_sha256}, got {pre_sha}")

    events = [_event_from_row(row, default_source=default_source) for row in _load_rows(input_csv)]
    output_root.mkdir(parents=True, exist_ok=True)
    backup_path = None
    applied_count = 0
    with sqlite3.connect(str(db_path)) as conn:
        conn.row_factory = sqlite3.Row
        validation = _validate_against_db(conn, events)
        planned = validation["planned"]
        errors = validation["errors"]
        if errors:
            _write_csv(output_root / "planned_rows.csv", planned)
            summary = {
                "status": "ERROR",
                "apply": bool(apply),
                "db_path": str(db_path),
                "input_csv": str(input_csv),
                "pre_sha256": pre_sha,
                "errors": errors,
                "input_row_count": len(events),
                "planned_row_count": len(planned),
                "skipped_existing_count": validation["skipped_existing"],
                "env_gate": ENV_GATE,
            }
            (output_root / "summary.json").write_text(
                json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
            raise ReturnQcApplyError("; ".join(errors))
        if apply:
            if os.environ.get(ENV_GATE) != "1":
                raise ReturnQcApplyError(f"{ENV_GATE}=1 is required with --apply")
            target_backup_dir = backup_dir or (output_root / "backups")
            target_backup_dir.mkdir(parents=True, exist_ok=True)
            backup_path = target_backup_dir / f"app_before_return_qc_events_{_now_stamp()}.db"
            shutil.copy2(db_path, backup_path)
            applied_count = _insert_events(conn, planned)
            conn.commit()
            integrity = conn.execute("PRAGMA integrity_check").fetchone()[0]
        else:
            integrity = conn.execute("PRAGMA integrity_check").fetchone()[0]

    post_sha = _sha256(db_path)
    _write_csv(output_root / "planned_rows.csv", planned)
    summary = {
        "status": "APPLIED" if apply else "DRY_RUN",
        "apply": bool(apply),
        "db_path": str(db_path),
        "input_csv": str(input_csv),
        "pre_sha256": pre_sha,
        "post_sha256": post_sha,
        "backup_path": str(backup_path) if backup_path else None,
        "sqlite_integrity_check": integrity,
        "input_row_count": len(events),
        "planned_row_count": len(planned),
        "applied_row_count": applied_count,
        "skipped_existing_count": validation["skipped_existing"],
        "accepted_active_qty": sum(int(row["accepted_active_qty"]) for row in planned),
        "quarantine_qty": sum(int(row["quarantine_qty"]) for row in planned),
        "rejected_qty": sum(int(row["rejected_qty"]) for row in planned),
        "writeoff_qty": sum(int(row["writeoff_qty"]) for row in planned),
        "planned_rows_csv": str(output_root / "planned_rows.csv"),
        "env_gate": ENV_GATE,
    }
    (output_root / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return summary


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, default=DEFAULT_DB_PATH)
    parser.add_argument("--input-csv", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--expected-pre-sha256", default="")
    parser.add_argument("--backup-dir", type=Path, default=None)
    parser.add_argument("--source", default="OWNER_STAFF_RETURN_QC_CSV")
    parser.add_argument("--json", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    try:
        summary = apply_return_qc_events(
            db_path=args.db,
            input_csv=args.input_csv,
            output_root=args.output_root,
            apply=bool(args.apply),
            backup_dir=args.backup_dir,
            expected_pre_sha256=args.expected_pre_sha256 or None,
            default_source=args.source,
        )
    except ReturnQcApplyError as exc:
        print(f"ERROR: {exc}")
        return 1
    if args.json:
        print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(
            "return_qc_events "
            f"status={summary['status']} "
            f"planned_rows={summary['planned_row_count']} "
            f"applied_rows={summary['applied_row_count']}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
