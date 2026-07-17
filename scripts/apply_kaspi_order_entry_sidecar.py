#!/usr/bin/env python3
"""Apply a hash-pinned Kaspi order-entry sidecar without more API calls.

The exporter already downloads order-entry payloads while building the daily
ActiveOrders workbook.  This writer reuses that exact, PII-free payload instead
of fetching every order a second time.  It is dry-run by default.  Apply
requires ``ENABLE_KASPI_ENRICHMENT=1`` and ``--apply``.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sqlite3
import sys
from datetime import date, datetime
from pathlib import Path
from typing import Any, Iterable


PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.stores.roster import load_sync_enabled_kaspi_store_codes  # noqa: E402
from core.sync.kaspi_order_enrichment import (  # noqa: E402
    _normalize_entry_updated_at,
    _parse_entry,
)
from scripts.backup_db import backup_database, verify_backup  # noqa: E402


SCHEMA_VERSION = "kaspi_order_entry_sidecar_v1"
WRITE_ENV_GATE = "ENABLE_KASPI_ENRICHMENT"
DEFAULT_DB = PROJECT_ROOT / "db" / "app.db"
DEFAULT_BACKUP_ROOT = PROJECT_ROOT / "backups" / "kaspi_order_entry_sidecar"
FORBIDDEN_RAW_KEYS = {
    "authorization",
    "cellphone",
    "customer",
    "customerphone",
    "email",
    "password",
    "phone",
    "token",
}
ENTRY_COLUMNS = (
    "entry_id",
    "order_id",
    "store_code",
    "product_id",
    "offer_id",
    "quantity",
    "unit_price_kzt",
    "total_price_kzt",
    "unit_type",
    "min_allowed_weight",
    "weight_kg",
    "entry_number",
    "category_code",
    "category_title",
    "delivery_cost_kzt",
    "base_price_kzt",
    "point_of_service_id",
    "delivery_point_of_service_id",
    "raw_json",
    "updated_at",
)
SEMANTIC_COLUMNS = (
    "entry_id",
    "order_id",
    "store_code",
    "product_id",
    "offer_id",
    "quantity",
    "unit_price_kzt",
    "total_price_kzt",
    "point_of_service_id",
)


class OrderEntrySidecarError(RuntimeError):
    """Raised when the sidecar or target DB cannot be proven safe."""


def canonical_json_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def payload_sha256(payload: dict[str, Any]) -> str:
    return hashlib.sha256(canonical_json_bytes(payload)).hexdigest()


def _table_columns(conn: sqlite3.Connection, table: str) -> list[str]:
    rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    return [str(row[1]) for row in rows]


def _integrity_check(conn: sqlite3.Connection) -> str:
    row = conn.execute("PRAGMA integrity_check").fetchone()
    return str(row[0]) if row else "missing"


def _walk_keys(value: Any) -> Iterable[str]:
    if isinstance(value, dict):
        for key, item in value.items():
            yield str(key).strip().lower()
            yield from _walk_keys(item)
    elif isinstance(value, list):
        for item in value:
            yield from _walk_keys(item)


def _validate_date(value: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise OrderEntrySidecarError(f"invalid target_date: {value}") from exc


def load_validated_sidecar(
    path: Path,
    *,
    expected_payload_sha256: str,
    expected_target_date: str,
    expected_store_roster: Iterable[str] | None = None,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    if not path.exists():
        raise OrderEntrySidecarError(f"entry sidecar not found: {path}")
    try:
        envelope = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise OrderEntrySidecarError(f"entry sidecar is not valid JSON: {path}") from exc
    if not isinstance(envelope, dict) or envelope.get("schema_version") != SCHEMA_VERSION:
        raise OrderEntrySidecarError("entry sidecar schema_version mismatch")
    payload = envelope.get("payload")
    if not isinstance(payload, dict):
        raise OrderEntrySidecarError("entry sidecar payload must be an object")
    observed_hash = payload_sha256(payload)
    embedded_hash = str(envelope.get("payload_sha256") or "").lower()
    expected_hash = str(expected_payload_sha256 or "").lower()
    if len(expected_hash) != 64:
        raise OrderEntrySidecarError("expected payload SHA-256 must be exactly 64 hex characters")
    if observed_hash != embedded_hash or observed_hash != expected_hash:
        raise OrderEntrySidecarError(
            "entry sidecar payload hash mismatch: "
            f"expected={expected_hash} embedded={embedded_hash} observed={observed_hash}"
        )

    target_date = str(payload.get("target_date") or "")
    target_day = _validate_date(target_date)
    if target_date != expected_target_date:
        raise OrderEntrySidecarError(
            f"entry sidecar target_date mismatch: expected={expected_target_date} observed={target_date}"
        )

    stores_value = payload.get("stores")
    if not isinstance(stores_value, list):
        raise OrderEntrySidecarError("entry sidecar stores must be a list")
    stores = [str(item or "").strip().upper() for item in stores_value]
    if any(not item for item in stores) or stores != sorted(set(stores)):
        raise OrderEntrySidecarError("entry sidecar stores must be sorted, unique, and nonblank")
    expected_stores = sorted(
        {
            str(item or "").strip().upper()
            for item in (
                expected_store_roster
                if expected_store_roster is not None
                else load_sync_enabled_kaspi_store_codes()
            )
            if str(item or "").strip()
        }
    )
    if stores != expected_stores:
        raise OrderEntrySidecarError(
            f"entry sidecar store roster mismatch: expected={expected_stores} observed={stores}"
        )

    orders = payload.get("orders")
    if not isinstance(orders, list):
        raise OrderEntrySidecarError("entry sidecar orders must be a list")
    parsed_entries: list[dict[str, Any]] = []
    seen_orders: set[tuple[str, str]] = set()
    seen_entries: dict[str, tuple[str, str]] = {}
    for record in orders:
        if not isinstance(record, dict):
            raise OrderEntrySidecarError("entry sidecar order record must be an object")
        order_id = str(record.get("order_id") or "").strip()
        store_code = str(record.get("store_code") or "").strip().upper()
        planned_date = str(record.get("planned_date") or "").strip()
        if not order_id or store_code not in stores:
            raise OrderEntrySidecarError(
                f"entry sidecar order identity is incomplete: {order_id!r}/{store_code!r}"
            )
        key = (order_id, store_code)
        if key in seen_orders:
            raise OrderEntrySidecarError(f"duplicate order in entry sidecar: {order_id}/{store_code}")
        seen_orders.add(key)
        try:
            planned_day = datetime.strptime(planned_date, "%d.%m.%Y").date()
        except ValueError as exc:
            raise OrderEntrySidecarError(
                f"invalid planned_date for {order_id}/{store_code}: {planned_date}"
            ) from exc
        if planned_day > target_day:
            raise OrderEntrySidecarError(
                f"future order in entry sidecar: {order_id}/{store_code} planned={planned_date}"
            )
        entries = record.get("entries")
        if not isinstance(entries, list) or not entries:
            raise OrderEntrySidecarError(
                f"entry sidecar order has zero entries: {order_id}/{store_code}"
            )
        for raw_entry in entries:
            if not isinstance(raw_entry, dict):
                raise OrderEntrySidecarError(
                    f"entry payload is not an object: {order_id}/{store_code}"
                )
            forbidden = sorted(set(_walk_keys(raw_entry)) & FORBIDDEN_RAW_KEYS)
            if forbidden:
                raise OrderEntrySidecarError(
                    f"entry sidecar contains forbidden keys for {order_id}/{store_code}: {forbidden}"
                )
            parsed = _parse_entry(raw_entry, order_id, store_code)
            entry_id = str(parsed.get("entry_id") or "").strip()
            parsed_order_id = str(parsed.get("order_id") or "").strip()
            if not entry_id:
                raise OrderEntrySidecarError(f"entry id missing for {order_id}/{store_code}")
            if parsed_order_id != order_id:
                raise OrderEntrySidecarError(
                    f"entry/order identity mismatch for {entry_id}: expected={order_id} observed={parsed_order_id}"
                )
            previous = seen_entries.get(entry_id)
            if previous is not None:
                raise OrderEntrySidecarError(
                    f"duplicate entry id {entry_id}: first={previous} second={key}"
                )
            seen_entries[entry_id] = key
            parsed["raw_json"] = json.dumps(
                raw_entry,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            )
            parsed_entries.append(parsed)

    if int(payload.get("order_count", -1)) != len(orders):
        raise OrderEntrySidecarError("entry sidecar order_count mismatch")
    if int(payload.get("entry_count", -1)) != len(parsed_entries):
        raise OrderEntrySidecarError("entry sidecar entry_count mismatch")
    return payload, parsed_entries


def _semantic_value(column: str, value: Any) -> Any:
    if column in {"quantity", "unit_price_kzt", "total_price_kzt"}:
        return float(value or 0.0)
    return "" if value is None else str(value)


def _non_target_hash(
    conn: sqlite3.Connection,
    *,
    excluded_entry_ids: set[str],
) -> str:
    columns = _table_columns(conn, "fact_order_entries_kaspi")
    if "entry_id" not in columns:
        raise OrderEntrySidecarError("fact_order_entries_kaspi.entry_id is missing")
    digest = hashlib.sha256()
    select_sql = ", ".join(f'"{column}"' for column in columns)
    for row in conn.execute(
        f"SELECT {select_sql} FROM fact_order_entries_kaspi ORDER BY entry_id"
    ):
        if str(row[columns.index("entry_id")]) in excluded_entry_ids:
            continue
        digest.update(canonical_json_bytes(list(row)))
        digest.update(b"\n")
    return digest.hexdigest()


def _header_updated_at(
    conn: sqlite3.Connection,
    *,
    order_id: str,
    store_code: str,
    target_date: str,
) -> str:
    rows = conn.execute(
        """
        SELECT status_updated_at, actual_shipment_date, planned_shipment_date, created_at
        FROM fact_orders_kaspi
        WHERE CAST(order_id AS TEXT)=? AND UPPER(COALESCE(store_code, ''))=?
        ORDER BY COALESCE(status_updated_at, actual_shipment_date, planned_shipment_date, created_at) DESC
        """,
        (order_id, store_code),
    ).fetchall()
    if not rows:
        raise OrderEntrySidecarError(f"order header missing: {order_id}/{store_code}")
    return _normalize_entry_updated_at(rows[0], max_date=target_date)


def _validate_existing_row(existing: sqlite3.Row, expected: dict[str, Any]) -> None:
    for column in SEMANTIC_COLUMNS:
        if _semantic_value(column, existing[column]) != _semantic_value(column, expected.get(column)):
            raise OrderEntrySidecarError(
                f"existing entry conflict for {expected['entry_id']} column={column}: "
                f"expected={expected.get(column)!r} observed={existing[column]!r}"
            )
    try:
        existing_raw = json.loads(str(existing["raw_json"] or "{}"))
        expected_raw = json.loads(str(expected["raw_json"] or "{}"))
    except json.JSONDecodeError as exc:
        raise OrderEntrySidecarError(
            f"existing raw_json is invalid for entry {expected['entry_id']}"
        ) from exc
    if existing_raw != expected_raw:
        raise OrderEntrySidecarError(
            f"existing raw_json conflict for entry {expected['entry_id']}"
        )


def apply_order_entry_sidecar(
    *,
    sidecar_path: Path,
    expected_payload_sha256: str,
    target_date: str,
    db_path: Path = DEFAULT_DB,
    backup_root: Path = DEFAULT_BACKUP_ROOT,
    prewrite_backup_path: Path | None = None,
    report_path: Path | None = None,
    expected_store_roster: Iterable[str] | None = None,
    apply: bool = False,
) -> dict[str, Any]:
    payload, parsed_entries = load_validated_sidecar(
        sidecar_path,
        expected_payload_sha256=expected_payload_sha256,
        expected_target_date=target_date,
        expected_store_roster=expected_store_roster,
    )
    if not db_path.exists():
        raise OrderEntrySidecarError(f"DB not found: {db_path}")
    if apply and os.environ.get(WRITE_ENV_GATE) != "1":
        raise OrderEntrySidecarError(f"{WRITE_ENV_GATE}=1 is required for --apply")

    backup_path: Path | None = None
    inserted = 0
    with sqlite3.connect(str(db_path)) as conn:
        conn.row_factory = sqlite3.Row
        required_header_columns = {
            "order_id",
            "store_code",
            "status_updated_at",
            "actual_shipment_date",
            "planned_shipment_date",
            "created_at",
        }
        header_columns = set(_table_columns(conn, "fact_orders_kaspi"))
        entry_columns = set(_table_columns(conn, "fact_order_entries_kaspi"))
        if missing := sorted(required_header_columns - header_columns):
            raise OrderEntrySidecarError(f"fact_orders_kaspi missing columns: {missing}")
        if missing := sorted(set(ENTRY_COLUMNS) - entry_columns):
            raise OrderEntrySidecarError(f"fact_order_entries_kaspi missing columns: {missing}")
        integrity_before = _integrity_check(conn)
        if integrity_before != "ok":
            raise OrderEntrySidecarError(f"DB integrity check failed before apply: {integrity_before}")

        order_entries: dict[tuple[str, str], list[dict[str, Any]]] = {}
        for entry in parsed_entries:
            key = (str(entry["order_id"]), str(entry["store_code"]).upper())
            order_entries.setdefault(key, []).append(entry)
        for (order_id, store_code), entries in order_entries.items():
            updated_at = _header_updated_at(
                conn,
                order_id=order_id,
                store_code=store_code,
                target_date=target_date,
            )
            for entry in entries:
                entry["updated_at"] = updated_at

        expected_by_id = {str(entry["entry_id"]): entry for entry in parsed_entries}
        expected_ids = set(expected_by_id)
        for (order_id, store_code), entries in order_entries.items():
            existing_ids = {
                str(row[0])
                for row in conn.execute(
                    """
                    SELECT entry_id FROM fact_order_entries_kaspi
                    WHERE CAST(order_id AS TEXT)=? AND UPPER(COALESCE(store_code, ''))=?
                    """,
                    (order_id, store_code),
                ).fetchall()
            }
            expected_for_order = {str(entry["entry_id"]) for entry in entries}
            extras = sorted(existing_ids - expected_for_order)
            if extras:
                raise OrderEntrySidecarError(
                    f"existing non-sidecar entries for {order_id}/{store_code}: {extras}"
                )

        missing_entries: list[dict[str, Any]] = []
        for entry_id, entry in expected_by_id.items():
            existing = conn.execute(
                "SELECT * FROM fact_order_entries_kaspi WHERE entry_id=?",
                (entry_id,),
            ).fetchone()
            if existing is None:
                missing_entries.append(entry)
            else:
                _validate_existing_row(existing, entry)

        non_target_before = _non_target_hash(conn, excluded_entry_ids=expected_ids)
        if apply and missing_entries:
            if db_path.resolve() == DEFAULT_DB.resolve():
                if prewrite_backup_path is not None:
                    backup_path = prewrite_backup_path
                    if not backup_path.exists():
                        raise OrderEntrySidecarError(
                            f"prewrite DB backup does not exist: {backup_path}"
                        )
                else:
                    day_backup_root = backup_root / target_date
                    backup_path = backup_database(db_path, day_backup_root, compress=False)
                if not verify_backup(backup_path):
                    raise OrderEntrySidecarError(f"DB backup verification failed: {backup_path}")
        transaction_started = False
        try:
            if apply and missing_entries:
                # Re-read and re-validate immediately before the write lock so
                # a replaced sidecar cannot pass the earlier preflight.
                load_validated_sidecar(
                    sidecar_path,
                    expected_payload_sha256=expected_payload_sha256,
                    expected_target_date=target_date,
                    expected_store_roster=expected_store_roster,
                )
                conn.execute("BEGIN IMMEDIATE")
                transaction_started = True
                insert_columns = [column for column in ENTRY_COLUMNS if column in entry_columns]
                placeholders = ",".join("?" for _ in insert_columns)
                column_sql = ",".join(insert_columns)
                for entry in missing_entries:
                    conn.execute(
                        f"INSERT INTO fact_order_entries_kaspi ({column_sql}) VALUES ({placeholders})",
                        [entry.get(column) for column in insert_columns],
                    )
                    inserted += 1

            for (order_id, store_code), entries in order_entries.items():
                observed_ids = {
                    str(row[0])
                    for row in conn.execute(
                        """
                        SELECT entry_id FROM fact_order_entries_kaspi
                        WHERE CAST(order_id AS TEXT)=? AND UPPER(COALESCE(store_code, ''))=?
                        """,
                        (order_id, store_code),
                    ).fetchall()
                }
                expected_for_order = {str(entry["entry_id"]) for entry in entries}
                if apply and observed_ids != expected_for_order:
                    raise OrderEntrySidecarError(
                        f"entry readback mismatch for {order_id}/{store_code}: "
                        f"expected={sorted(expected_for_order)} observed={sorted(observed_ids)}"
                    )
            non_target_after = _non_target_hash(conn, excluded_entry_ids=expected_ids)
            if non_target_after != non_target_before:
                raise OrderEntrySidecarError("non-target fact_order_entries_kaspi diff detected")
            integrity_after = _integrity_check(conn)
            if integrity_after != "ok":
                raise OrderEntrySidecarError(f"DB integrity check failed after apply: {integrity_after}")
            if transaction_started:
                conn.commit()
        except Exception:
            if transaction_started:
                conn.rollback()
            raise

    report = {
        "schema_version": SCHEMA_VERSION,
        "target_date": target_date,
        "sidecar_path": str(sidecar_path),
        "payload_sha256": expected_payload_sha256,
        "store_count": len(payload["stores"]),
        "order_count": len(payload["orders"]),
        "entry_count": len(parsed_entries),
        "preexisting_entry_count": len(parsed_entries) - len(missing_entries),
        "missing_entry_count": len(missing_entries),
        "applied": bool(apply and missing_entries),
        "inserted_entry_count": inserted,
        "backup_path": str(backup_path) if backup_path else "",
        "integrity_before": integrity_before,
        "integrity_after": integrity_after,
        "non_target_hash_before": non_target_before,
        "non_target_hash_after": non_target_after,
        "readback_complete": bool(apply or not missing_entries),
    }
    if report_path is not None:
        report_path.parent.mkdir(parents=True, exist_ok=True)
        temp_report = report_path.with_name(f".{report_path.name}.{os.getpid()}.tmp")
        temp_report.write_text(
            json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        temp_report.replace(report_path)
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sidecar", type=Path, required=True)
    parser.add_argument("--expected-payload-sha256", required=True)
    parser.add_argument("--target-date", required=True)
    parser.add_argument("--db-path", type=Path, default=DEFAULT_DB)
    parser.add_argument("--backup-root", type=Path, default=DEFAULT_BACKUP_ROOT)
    parser.add_argument("--prewrite-backup", type=Path)
    parser.add_argument("--report", type=Path)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args(argv)
    try:
        report = apply_order_entry_sidecar(
            sidecar_path=args.sidecar,
            expected_payload_sha256=args.expected_payload_sha256,
            target_date=args.target_date,
            db_path=args.db_path,
            backup_root=args.backup_root,
            prewrite_backup_path=args.prewrite_backup,
            report_path=args.report,
            apply=args.apply,
        )
    except (OrderEntrySidecarError, sqlite3.Error, OSError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
