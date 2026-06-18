#!/usr/bin/env python3
"""Apply exact owner-approved cost basis for shipped-freeze order 956748585.

This writer may insert only the two inventory-move events needed to establish
the on-delivery balance for one shipped order. It must not create SKU-wide
COGS inheritance or run the broad order translator.
"""

from __future__ import annotations

import argparse
import csv
from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import sys
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.validate_on_delivery_freeze import (  # noqa: E402
    DEFAULT_DB,
    validate_on_delivery_freeze,
)

ENV_GATE = "ENABLE_956748585_FREEZE_COST_BASIS_WRITE"
ORDER_ID = "956748585"
STORE_CODE = "ACMEWEAR"
SKU_KEY = "LINE-21-TS"
SKU_ID = "LINE-21-TS_3XL"
UNIT_COGS_KZT = 6006.76
EVENT_DATE = "2026-06-12"
RUN_ID = "owner_956748585_freeze_cost_basis_20260614"
SOURCE = "OWNER_APPROVED_LINE51_PARENT_UNIT_COGS_20260614"
OWNER_DECISION_REF = "OWNER_COGS_COST_BASIS_OVERRIDE_2026_06_14_956748585"
EXPECTED_FREEZE_ERROR = (
    f"{ORDER_ID}: status=SHIPPED has missing INVENTORY_ON_DELIVERY_COST balance (balance=0.00)"
)
TOL_KZT = 0.01


class FreezeCostBasisError(RuntimeError):
    """Raised when the exact-row freeze cost-basis repair is not safe."""


@dataclass(frozen=True)
class ApprovedEvent:
    event_date: str
    event_type: str
    account: str
    amount_kzt: float
    store_code: str
    sku_key: str
    sku_id: str
    ref_type: str
    ref_id: str
    notes: str
    source: str
    run_id: str

    def as_dict(self) -> dict[str, Any]:
        payload = {
            "event_date": self.event_date,
            "event_type": self.event_type,
            "account": self.account,
            "amount_kzt": self.amount_kzt,
            "store_code": self.store_code,
            "sku_key": self.sku_key,
            "sku_id": self.sku_id,
            "ref_type": self.ref_type,
            "ref_id": self.ref_id,
            "notes": self.notes,
            "source": self.source,
            "run_id": self.run_id,
        }
        payload["event_hash"] = _event_hash(payload)
        return payload


APPROVED_EVENTS = [
    ApprovedEvent(
        event_date=EVENT_DATE,
        event_type="INVENTORY_MOVE",
        account="INVENTORY_ON_HAND_COST",
        amount_kzt=-UNIT_COGS_KZT,
        store_code=STORE_CODE,
        sku_key=SKU_KEY,
        sku_id=SKU_ID,
        ref_type="ORDER",
        ref_id=ORDER_ID,
        notes=(
            "Owner-approved exact-row LINE51 parent-unit landed COGS cost basis; "
            "move to on-delivery inventory."
        ),
        source=SOURCE,
        run_id=RUN_ID,
    ),
    ApprovedEvent(
        event_date=EVENT_DATE,
        event_type="INVENTORY_MOVE",
        account="INVENTORY_ON_DELIVERY_COST",
        amount_kzt=UNIT_COGS_KZT,
        store_code=STORE_CODE,
        sku_key=SKU_KEY,
        sku_id=SKU_ID,
        ref_type="ORDER",
        ref_id=ORDER_ID,
        notes=(
            "Owner-approved exact-row LINE51 parent-unit landed COGS cost basis; "
            "on-delivery inventory."
        ),
        source=SOURCE,
        run_id=RUN_ID,
    ),
]


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _connect_readonly(path: Path) -> sqlite3.Connection:
    return sqlite3.connect(f"{path.resolve().as_uri()}?mode=ro", uri=True)


def _sqlite_integrity_check(path: Path) -> str:
    conn = _connect_readonly(path)
    try:
        row = conn.execute("PRAGMA integrity_check;").fetchone()
    finally:
        conn.close()
    return str(row[0] if row else "")


def _sqlite_backup(src_path: Path, dst_path: Path) -> Path:
    dst_path.parent.mkdir(parents=True, exist_ok=True)
    src = _connect_readonly(src_path)
    dst = sqlite3.connect(str(dst_path))
    try:
        src.backup(dst)
    finally:
        dst.close()
        src.close()
    integrity = _sqlite_integrity_check(dst_path)
    if integrity.lower() != "ok":
        raise FreezeCostBasisError(f"backup integrity_check failed for {dst_path}: {integrity}")
    return dst_path


def _event_hash(event: dict[str, Any]) -> str:
    parts = [
        str(event.get("event_date") or ""),
        str(event.get("event_type") or ""),
        str(event.get("account") or ""),
        f"{float(event.get('amount_kzt') or 0.0):.4f}",
        str(event.get("store_code") or ""),
        str(event.get("sku_key") or ""),
        str(event.get("sku_id") or ""),
        str(event.get("ref_type") or ""),
        str(event.get("ref_id") or ""),
        str(event.get("source") or ""),
    ]
    return hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "event_date",
        "event_type",
        "account",
        "amount_kzt",
        "store_code",
        "sku_key",
        "sku_id",
        "ref_type",
        "ref_id",
        "notes",
        "source",
        "run_id",
        "event_hash",
    ]
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({key: row.get(key, "") for key in fieldnames})


def _dict_rows(conn: sqlite3.Connection, sql: str, params: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
    return [dict(row) for row in conn.execute(sql, params).fetchall()]


def _order_row(conn: sqlite3.Connection) -> dict[str, Any]:
    rows = _dict_rows(
        conn,
        """
        SELECT order_id, store_code, kaspi_status, kaspi_status_detail,
               internal_status, created_at, planned_shipment_date,
               actual_shipment_date, status_updated_at, quantity,
               unit_price_kzt, sku_key, sku_id
        FROM fact_orders_kaspi
        WHERE CAST(order_id AS TEXT) = ?
        """,
        (ORDER_ID,),
    )
    if len(rows) != 1:
        raise FreezeCostBasisError(f"expected exactly one fact_orders_kaspi row for {ORDER_ID}, found {len(rows)}")
    row = rows[0]
    expected = {
        "store_code": STORE_CODE,
        "kaspi_status": "KASPI_DELIVERY",
        "kaspi_status_detail": "ACCEPTED_BY_MERCHANT",
        "internal_status": "SHIPPED",
        "sku_key": SKU_KEY,
        "sku_id": SKU_ID,
    }
    for key, value in expected.items():
        observed = str(row.get(key) or "").strip().upper()
        if observed != value:
            raise FreezeCostBasisError(f"{ORDER_ID} {key} mismatch: observed={observed} expected={value}")
    if float(row.get("quantity") or 0.0) != 1.0:
        raise FreezeCostBasisError(f"{ORDER_ID} quantity mismatch: {row.get('quantity')}")
    if str(row.get("status_updated_at") or "")[:10] != EVENT_DATE:
        raise FreezeCostBasisError(
            f"{ORDER_ID} status_updated_at date mismatch: {row.get('status_updated_at')} expected {EVENT_DATE}"
        )
    return row


def _existing_target_events(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    return _dict_rows(
        conn,
        """
        SELECT event_date, event_type, account, amount_kzt, store_code, sku_key,
               sku_id, ref_type, ref_id, notes, source, run_id, event_hash
        FROM fact_cashflow_events
        WHERE CAST(ref_id AS TEXT) = ?
          AND account IN ('INVENTORY_ON_HAND_COST', 'INVENTORY_ON_DELIVERY_COST')
        ORDER BY event_date, event_type, account
        """,
        (ORDER_ID,),
    )


def _validate_preconditions(db_path: Path) -> dict[str, Any]:
    conn = _connect_readonly(db_path)
    conn.row_factory = sqlite3.Row
    try:
        row = _order_row(conn)
        existing = _existing_target_events(conn)
    finally:
        conn.close()
    if existing:
        raise FreezeCostBasisError(f"{ORDER_ID} already has target inventory events: {len(existing)}")

    freeze_errors = validate_on_delivery_freeze(db_path=db_path, until=__import__("datetime").date(2026, 6, 14))
    if freeze_errors != [EXPECTED_FREEZE_ERROR]:
        raise FreezeCostBasisError(
            "freeze precondition mismatch: expected only "
            f"{EXPECTED_FREEZE_ERROR!r}, observed={freeze_errors!r}"
        )
    return {
        "order_row": row,
        "existing_target_events": existing,
        "freeze_errors": freeze_errors,
    }


def _insert_events(db_path: Path) -> int:
    events = [event.as_dict() for event in APPROVED_EVENTS]
    conn = sqlite3.connect(str(db_path))
    try:
        conn.execute("BEGIN IMMEDIATE")
        inserted = 0
        for event in events:
            conn.execute(
                """
                INSERT INTO fact_cashflow_events (
                    event_date, event_type, account, amount_kzt, store_code, sku_key,
                    sku_id, ref_type, ref_id, notes, source, run_id, event_hash
                ) VALUES (
                    :event_date, :event_type, :account, :amount_kzt, :store_code, :sku_key,
                    :sku_id, :ref_type, :ref_id, :notes, :source, :run_id, :event_hash
                )
                """,
                event,
            )
            inserted += 1
        conn.commit()
        return inserted
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def _validate_post(db_path: Path) -> dict[str, Any]:
    conn = _connect_readonly(db_path)
    conn.row_factory = sqlite3.Row
    try:
        events = _existing_target_events(conn)
    finally:
        conn.close()

    if len(events) != 2:
        raise FreezeCostBasisError(f"expected exactly two target events after apply, observed {len(events)}")
    by_account = {str(row["account"]): float(row["amount_kzt"]) for row in events}
    if abs(by_account.get("INVENTORY_ON_HAND_COST", 0.0) + UNIT_COGS_KZT) > TOL_KZT:
        raise FreezeCostBasisError(f"INVENTORY_ON_HAND_COST amount mismatch: {by_account}")
    if abs(by_account.get("INVENTORY_ON_DELIVERY_COST", 0.0) - UNIT_COGS_KZT) > TOL_KZT:
        raise FreezeCostBasisError(f"INVENTORY_ON_DELIVERY_COST amount mismatch: {by_account}")

    freeze_errors = validate_on_delivery_freeze(db_path=db_path, until=__import__("datetime").date(2026, 6, 14))
    if freeze_errors:
        raise FreezeCostBasisError(f"freeze post validation failed: {freeze_errors!r}")
    return {
        "target_events": events,
        "freeze_errors": freeze_errors,
    }


def run_repair(
    *,
    db_path: Path = DEFAULT_DB,
    output_dir: Path,
    apply: bool = False,
    backup_dir: Path | None = None,
    expected_pre_sha256: str | None = None,
) -> dict[str, Any]:
    db_path = Path(db_path)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    if not db_path.exists():
        raise FreezeCostBasisError(f"db not found: {db_path}")

    if apply:
        if os.environ.get(ENV_GATE) != "1":
            raise FreezeCostBasisError(f"{ENV_GATE}=1 is required for --apply")
        if backup_dir is None:
            raise FreezeCostBasisError("--backup-dir is required for --apply")

    pre_sha = _sha256_file(db_path)
    if expected_pre_sha256 and expected_pre_sha256 != pre_sha:
        raise FreezeCostBasisError(
            f"pre-SHA mismatch: expected={expected_pre_sha256} observed={pre_sha}"
        )

    preconditions = _validate_preconditions(db_path)
    _write_csv(output_dir / "approved_events.csv", [event.as_dict() for event in APPROVED_EVENTS])

    gate: dict[str, Any] = {
        "env_gate": ENV_GATE,
        "apply": bool(apply),
        "pre_sha256": pre_sha,
        "backup_path": None,
        "backup_sha256": None,
    }

    if apply:
        backup_path = _sqlite_backup(
            db_path,
            Path(backup_dir) / "app_db_before_956748585_freeze_cost_basis.sqlite",
        )
        gate["backup_path"] = str(backup_path)
        gate["backup_sha256"] = _sha256_file(backup_path)
        rows_inserted = _insert_events(db_path)
        post = _validate_post(db_path)
        status = "APPLIED"
    else:
        simulation_db = _sqlite_backup(db_path, output_dir / "simulation.db")
        rows_inserted = _insert_events(simulation_db)
        post = _validate_post(simulation_db)
        status = "DRY_RUN"
        gate["simulation_db"] = str(simulation_db)

    post_sha = _sha256_file(db_path)
    report = {
        "status": status,
        "order_id": ORDER_ID,
        "store_code": STORE_CODE,
        "sku_key": SKU_KEY,
        "sku_id": SKU_ID,
        "unit_cogs_kzt": UNIT_COGS_KZT,
        "source": SOURCE,
        "owner_decision_ref": OWNER_DECISION_REF,
        "rows_inserted": rows_inserted,
        "gate": gate,
        "preconditions": preconditions,
        "post": post,
        "pre_sha256": pre_sha,
        "post_sha256": post_sha,
        "db_sha256_changed": pre_sha != post_sha,
        "rollback": {
            "restore_from_backup": (
                f"sqlite3 {db_path} \".restore {gate['backup_path']}\""
                if gate.get("backup_path")
                else None
            )
        },
    }
    _write_json(output_dir / "report.json", report)
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description="Apply exact-row 956748585 freeze cost-basis repair")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--backup-dir", type=Path, default=None)
    parser.add_argument("--expected-pre-sha256", default=None)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()

    try:
        report = run_repair(
            db_path=args.db,
            output_dir=args.output_dir,
            backup_dir=args.backup_dir,
            expected_pre_sha256=args.expected_pre_sha256,
            apply=args.apply,
        )
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
