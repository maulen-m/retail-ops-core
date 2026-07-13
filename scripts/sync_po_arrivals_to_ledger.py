#!/usr/bin/env python3
"""Sync delivered PO arrivals into the stock ledger without replaying receipts.

Dry-run is the default. A write is permitted only when a real source shortfall
exists, the explicit write gate is open, and a database backup has succeeded.
Existing physical receipts are recognized across both legacy ``PO`` and
line-grain ``PO_PART`` references.
"""

from __future__ import annotations

import argparse
import csv
from datetime import date, datetime
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import sys
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from core.db import DEFAULT_DB_PATH, get_db
from scripts.backup_db import backup_database


ENV_GATE = "ENABLE_PO_ARRIVAL_LEDGER_WRITE"
PRODUCTION_ENV_GATE = "ALLOW_PRODUCTION_PO_ARRIVAL_LEDGER_WRITE"
DEFAULT_OUTPUT_ROOT = PROJECT_ROOT / "exports" / "validation" / "po_arrival_ledger_sync"
INVENTORY_POOL_STORE = "UNIVERSAL"


def _upper_store(value: Any) -> str:
    return str(value or "UNIVERSAL").strip().upper() or "UNIVERSAL"


def _parse_date(value: str | None) -> str:
    if value:
        return datetime.strptime(value, "%Y-%m-%d").date().isoformat()
    return date.today().isoformat()


def _table_exists(conn: sqlite3.Connection, table: str) -> bool:
    return conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
        (table,),
    ).fetchone() is not None


def _columns(conn: sqlite3.Connection, table: str) -> set[str]:
    if not _table_exists(conn, table):
        return set()
    return {str(row[1]) for row in conn.execute(f"PRAGMA table_info({table})")}


def _part_refs(
    conn: sqlite3.Connection,
    *,
    po_id: str,
    sku_id: str,
    my_size: str,
) -> list[str]:
    if not _table_exists(conn, "po_line"):
        return []
    cols = _columns(conn, "po_line")
    if not {"po_id", "po_part_id", "sku_id", "my_size"}.issubset(cols):
        return []
    rows = conn.execute(
        """
        SELECT DISTINCT TRIM(po_part_id) AS po_part_id
        FROM po_line
        WHERE po_id = ?
          AND sku_id = ?
          AND UPPER(TRIM(my_size)) = UPPER(TRIM(?))
          AND COALESCE(TRIM(po_part_id), '') <> ''
        ORDER BY po_part_id
        """,
        (po_id, sku_id, my_size),
    ).fetchall()
    return [str(row[0]) for row in rows]


def _existing_receipt_units(
    conn: sqlite3.Connection,
    *,
    po_id: str,
    part_refs: list[str],
    sku_id: str,
    my_size: str,
) -> int:
    po_part_refs = sorted({po_id, *part_refs})
    placeholders = ",".join("?" for _ in po_part_refs)
    params: list[Any] = [sku_id, my_size, po_id, *po_part_refs]
    row = conn.execute(
        f"""
        SELECT COALESCE(SUM(qty_change), 0)
        FROM stock_ledger
        WHERE UPPER(COALESCE(event_type, '')) = 'INBOUND'
          AND sku_id = ?
          AND UPPER(TRIM(my_size)) = UPPER(TRIM(?))
          AND (
                (UPPER(COALESCE(reference_type, '')) = 'PO' AND reference_id = ?)
             OR (UPPER(COALESCE(reference_type, '')) = 'PO_PART'
                 AND reference_id IN ({placeholders}))
          )
        """,
        params,
    ).fetchone()
    return int(row[0] or 0)


def _idempotency_key(row: dict[str, Any]) -> str:
    identity = "|".join(
        [
            "po-arrival-ledger-v2",
            str(row["source_po_id"]),
            str(row["reference_type"]),
            str(row["reference_id"]),
            str(row["sku_id"]),
            str(row["my_size"]),
            str(row["event_date"]),
            str(row["source_received_qty"]),
        ]
    )
    return hashlib.sha256(identity.encode("utf-8")).hexdigest()


def build_po_arrival_sync_plan(
    conn: sqlite3.Connection,
    *,
    snapshot_date: str,
) -> dict[str, Any]:
    """Return a source-to-ledger shortfall plan without writing."""

    raw_source_rows = conn.execute(
        """
        SELECT
            po_id,
            store_code,
            sku_id,
            sku_key,
            UPPER(TRIM(my_size)) AS my_size,
            COALESCE(received_qty, 0) AS received_qty,
            actual_arrival_date
        FROM fact_po_lines
        WHERE UPPER(COALESCE(status, '')) = 'DELIVERED'
          AND actual_arrival_date IS NOT NULL
          AND actual_arrival_date <= ?
          AND COALESCE(received_qty, 0) > 0
        ORDER BY po_id, sku_id, my_size, store_code
        """,
        (snapshot_date,),
    ).fetchall()

    grouped_sources: dict[tuple[str, str, str], list[sqlite3.Row]] = {}
    for source in raw_source_rows:
        key = (
            str(source["po_id"] or "").strip(),
            str(source["sku_id"] or "").strip(),
            str(source["my_size"] or "").strip().upper(),
        )
        grouped_sources.setdefault(key, []).append(source)

    insert_rows: list[dict[str, Any]] = []
    blocked_rows: list[dict[str, Any]] = []
    source_rows: list[sqlite3.Row] = []
    for (po_id, sku_id, my_size), matches in sorted(grouped_sources.items()):
        if len(matches) != 1:
            blocked_rows.append(
                {
                    "reason": "SOURCE_LINE_NOT_ONE_TO_ONE",
                    "po_id": po_id,
                    "sku_id": sku_id,
                    "my_size": my_size,
                    "source_row_count": len(matches),
                    "store_codes": sorted({_upper_store(row["store_code"]) for row in matches}),
                    "sku_keys": sorted({str(row["sku_key"] or "").strip() for row in matches}),
                    "arrival_dates": sorted({str(row["actual_arrival_date"] or "").strip() for row in matches}),
                }
            )
            continue
        source_rows.append(matches[0])

    for source in source_rows:
        po_id = str(source["po_id"] or "").strip()
        sku_id = str(source["sku_id"] or "").strip()
        my_size = str(source["my_size"] or "").strip().upper()
        received_qty = int(source["received_qty"] or 0)
        min_arrival = str(source["actual_arrival_date"] or "").strip()
        max_arrival = min_arrival
        if not po_id or not sku_id or not my_size or received_qty <= 0:
            blocked_rows.append(
                {
                    "reason": "SOURCE_IDENTITY_INCOMPLETE",
                    "po_id": po_id,
                    "sku_id": sku_id,
                    "my_size": my_size,
                    "received_qty": received_qty,
                }
            )
            continue
        if not min_arrival or min_arrival != max_arrival:
            blocked_rows.append(
                {
                    "reason": "AMBIGUOUS_ARRIVAL_DATE",
                    "po_id": po_id,
                    "sku_id": sku_id,
                    "my_size": my_size,
                    "min_arrival_date": min_arrival,
                    "max_arrival_date": max_arrival,
                }
            )
            continue

        part_refs = _part_refs(
            conn,
            po_id=po_id,
            sku_id=sku_id,
            my_size=my_size,
        )
        if len(part_refs) > 1:
            blocked_rows.append(
                {
                    "reason": "AMBIGUOUS_PO_PART_MAPPING",
                    "po_id": po_id,
                    "sku_id": sku_id,
                    "my_size": my_size,
                    "po_part_ids": part_refs,
                }
            )
            continue
        if not part_refs:
            blocked_rows.append(
                {
                    "reason": "PO_PART_MAPPING_MISSING",
                    "po_id": po_id,
                    "sku_id": sku_id,
                    "my_size": my_size,
                }
            )
            continue

        existing_units = _existing_receipt_units(
            conn,
            po_id=po_id,
            part_refs=part_refs,
            sku_id=sku_id,
            my_size=my_size,
        )
        to_add = received_qty - existing_units
        if existing_units > received_qty:
            blocked_rows.append(
                {
                    "reason": "RECEIPT_OVERAGE",
                    "po_id": po_id,
                    "sku_id": sku_id,
                    "my_size": my_size,
                    "source_received_qty": received_qty,
                    "existing_receipt_units": existing_units,
                    "overage_units": existing_units - received_qty,
                }
            )
            continue
        if to_add <= 0:
            continue

        target_reference_type = "PO_PART"
        target_reference_id = part_refs[0]
        planned = {
            "event_date": min_arrival,
            "event_type": "INBOUND",
            "sku_key": str(source["sku_key"] or "").strip(),
            "sku_id": sku_id,
            "my_size": my_size,
            "store_code": INVENTORY_POOL_STORE,
            "qty_change": to_add,
            "reference_id": target_reference_id,
            "reference_type": target_reference_type,
            "notes": "Source-backed PO arrival shortfall from fact_po_lines",
            "input_source": "SYSTEM",
            "created_by": "sync_po_arrivals_to_ledger_v2",
            "source_po_id": po_id,
            "source_received_qty": received_qty,
            "existing_receipt_units": existing_units,
        }
        planned["idempotency_key"] = _idempotency_key(planned)
        insert_rows.append(planned)

    return {
        "summary": {
            "snapshot_date": snapshot_date,
            "source_line_count": len(raw_source_rows),
            "insert_count": len(insert_rows),
            "insert_units": sum(int(row["qty_change"]) for row in insert_rows),
            "blocked_count": len(blocked_rows),
        },
        "insert_rows": insert_rows,
        "blocked_rows": blocked_rows,
    }


def _assert_apply_allowed(db_path: Path) -> None:
    if os.environ.get(ENV_GATE) != "1":
        raise RuntimeError(f"{ENV_GATE}=1 is required for --apply")
    if db_path.resolve() == DEFAULT_DB_PATH.resolve() and os.environ.get(PRODUCTION_ENV_GATE) != "1":
        raise RuntimeError(f"{PRODUCTION_ENV_GATE}=1 is required for production DB apply")


def _integrity_check(db_path: Path) -> str:
    with sqlite3.connect(f"file:{db_path}?mode=ro", uri=True) as conn:
        row = conn.execute("PRAGMA integrity_check").fetchone()
    return str(row[0] if row else "")


def _sha256(db_path: Path) -> str:
    digest = hashlib.sha256()
    with db_path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _require_idempotency_contract(conn: sqlite3.Connection) -> None:
    if "idempotency_key" not in _columns(conn, "stock_ledger"):
        raise RuntimeError("stock_ledger.idempotency_key is required for apply")
    for index in conn.execute("PRAGMA index_list(stock_ledger)").fetchall():
        if not int(index[2] or 0):
            continue
        index_name = str(index[1])
        columns = [str(row[2]) for row in conn.execute(f"PRAGMA index_info('{index_name}')")]
        if columns == ["idempotency_key"]:
            return
    raise RuntimeError("a unique stock_ledger(idempotency_key) index is required for apply")


def _write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = sorted({key for row in rows for key in row})
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def _insert_rows(conn: sqlite3.Connection, rows: list[dict[str, Any]]) -> int:
    _require_idempotency_contract(conn)
    inserted = 0
    for row in rows:
        previous_balance = int(
            conn.execute(
                """
                SELECT COALESCE(SUM(qty_change), 0)
                FROM stock_ledger
                WHERE sku_id = ? AND UPPER(COALESCE(store_code, 'UNIVERSAL')) = ?
                """,
                (row["sku_id"], row["store_code"]),
            ).fetchone()[0]
            or 0
        )
        payload = {
            key: row[key]
            for key in (
                "event_date",
                "event_type",
                "sku_key",
                "sku_id",
                "my_size",
                "store_code",
                "qty_change",
                "reference_id",
                "reference_type",
                "notes",
                "input_source",
                "created_by",
            )
        }
        payload["running_balance"] = previous_balance + int(row["qty_change"])
        payload["idempotency_key"] = row["idempotency_key"]
        columns = list(payload)
        cursor = conn.execute(
            f"INSERT INTO stock_ledger ({', '.join(columns)}) "
            f"VALUES ({', '.join('?' for _ in columns)})",
            [payload[column] for column in columns],
        )
        inserted += max(int(cursor.rowcount or 0), 0)
    return inserted


def sync_po_arrivals_to_ledger(
    *,
    db_path: Path,
    snapshot_date: str,
    output_root: Path,
    apply: bool = False,
    expected_pre_sha256: str | None = None,
) -> dict[str, Any]:
    output_root.mkdir(parents=True, exist_ok=True)
    backup_path: Path | None = None
    integrity_before = _integrity_check(db_path)
    if integrity_before.lower() != "ok":
        raise RuntimeError(f"pre-write integrity_check failed: {integrity_before}")
    pre_sha256 = _sha256(db_path)
    with get_db(db_path) as conn:
        plan = build_po_arrival_sync_plan(conn, snapshot_date=snapshot_date)

    summary = {
        **plan["summary"],
        "mode": "DRY_RUN",
        "rows_applied": 0,
        "pre_sha256": pre_sha256,
        "post_sha256": pre_sha256,
        "backup_path": None,
        "integrity_check": {"before": integrity_before, "backup": None, "after": integrity_before},
    }
    (output_root / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    _write_csv(output_root / "insert_rows.csv", plan["insert_rows"])
    _write_csv(output_root / "blocked_rows.csv", plan["blocked_rows"])

    if apply and plan["summary"]["blocked_count"]:
        raise RuntimeError("PO arrival plan has ambiguous source rows; see blocked_rows.csv")
    if apply and plan["insert_rows"]:
        _assert_apply_allowed(db_path)
        if db_path.resolve() == DEFAULT_DB_PATH.resolve():
            if not expected_pre_sha256 or expected_pre_sha256 != pre_sha256:
                raise RuntimeError("production apply requires the exact current --expected-pre-sha256")
        with get_db(db_path) as conn:
            _require_idempotency_contract(conn)
        backup_path = backup_database(db_path, output_root / "backups", compress=False)
        backup_integrity = _integrity_check(backup_path)
        if backup_integrity.lower() != "ok":
            raise RuntimeError(f"backup integrity_check failed: {backup_integrity}")
        if _sha256(db_path) != pre_sha256:
            raise RuntimeError("database SHA changed during backup; refusing apply")
        with get_db(db_path) as conn:
            refreshed = build_po_arrival_sync_plan(conn, snapshot_date=snapshot_date)
            if refreshed["insert_rows"] != plan["insert_rows"]:
                raise RuntimeError("PO arrival plan changed after backup; refusing apply")
            inserted = _insert_rows(conn, plan["insert_rows"])
            if inserted != len(plan["insert_rows"]):
                raise RuntimeError(
                    f"insert count mismatch: expected {len(plan['insert_rows'])}, got {inserted}"
                )
    else:
        inserted = 0
        backup_integrity = None

    integrity_after = _integrity_check(db_path)
    summary = {
        **plan["summary"],
        "mode": "APPLIED" if apply and plan["insert_rows"] else ("NOOP" if apply else "DRY_RUN"),
        "rows_applied": inserted,
        "pre_sha256": pre_sha256,
        "post_sha256": _sha256(db_path),
        "backup_path": str(backup_path) if backup_path else None,
        "integrity_check": {
            "before": integrity_before,
            "backup": backup_integrity,
            "after": integrity_after,
        },
    }
    (output_root / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return {"summary": summary, **plan}


def main() -> int:
    parser = argparse.ArgumentParser(description="Sync delivered PO arrivals to stock ledger")
    parser.add_argument("--snapshot-date", help="Cutoff date YYYY-MM-DD (default: today)")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB_PATH, help="DB path")
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--expected-pre-sha256")
    parser.add_argument("--apply", action="store_true", help="Apply proven shortfalls (default: dry-run)")
    parser.add_argument(
        "--force",
        action="store_true",
        help="Deprecated unsafe replay bypass; always rejected",
    )
    args = parser.parse_args()
    if args.force:
        print("ERROR: --force is disabled; repair source lineage instead of replaying receipts", file=sys.stderr)
        return 2
    try:
        result = sync_po_arrivals_to_ledger(
            db_path=args.db,
            snapshot_date=_parse_date(args.snapshot_date),
            output_root=args.output_root,
            apply=bool(args.apply),
            expected_pre_sha256=args.expected_pre_sha256,
        )
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(result["summary"], ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
