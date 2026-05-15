#!/usr/bin/env python3
"""Materialize C3 PO/inbound line-grain references from source PO rows.

Dry-run is the default. Apply requires ENABLE_C3_PO_INBOUND_WRITE=1.
Production DB apply also requires ALLOW_PRODUCTION_C3_PO_INBOUND_WRITE=1.
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

ENV_GATE = "ENABLE_C3_PO_INBOUND_WRITE"
PRODUCTION_ENV_GATE = "ALLOW_PRODUCTION_C3_PO_INBOUND_WRITE"
OPEN_PO_IDS = {"New-CLO_PO-2.1"}
RECEIVED_STATUSES = {"RECEIVED", "ARRIVED", "CLOSED", "DONE"}
OPEN_STATUSES = {"PENDING", "PARTIAL", "IN_TRANSIT", "CONFIRMED", "SHIPPED", "PAID_NOT_SHIPPED"}


@dataclass(frozen=True)
class POInboundPlan:
    summary: dict[str, Any]
    po_headers: list[dict[str, Any]]
    po_parts: list[dict[str, Any]]
    po_lines: list[dict[str, Any]]
    ledger_updates: list[dict[str, Any]]
    blocked_rows: list[dict[str, Any]]

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


def _columns(conn: sqlite3.Connection, table: str) -> set[str]:
    if not _table_exists(conn, table):
        return set()
    return {str(row[1]) for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}


def _upper(value: Any) -> str:
    return str(value or "").strip().upper()


def _as_int(value: Any) -> int:
    try:
        return int(round(float(value or 0)))
    except (TypeError, ValueError):
        return 0


def _as_float(value: Any) -> float:
    try:
        return float(value or 0.0)
    except (TypeError, ValueError):
        return 0.0


def _status_from_source(status: Any, *, received_qty: int, order_qty: int) -> str:
    upper = _upper(status)
    if upper in RECEIVED_STATUSES or (received_qty > 0 and received_qty >= order_qty):
        return "RECEIVED"
    if upper in OPEN_STATUSES:
        return upper
    if received_qty > 0:
        return "RECEIVED"
    return "PENDING"


def _source_line_from_fact(row: sqlite3.Row, *, po_part_id: str) -> dict[str, Any]:
    order_qty = _as_int(row["order_quantity"])
    received_qty = _as_int(row["received_qty"])
    return {
        "source_table": "fact_po_lines",
        "source_row_id": row["id"],
        "po_id": str(row["po_id"] or "").strip(),
        "po_part_id": po_part_id,
        "store_code": str(row["store_code"] or "UNIVERSAL").strip().upper(),
        "sku_key": str(row["sku_key"] or "").strip(),
        "sku_id": str(row["sku_id"] or "").strip(),
        "my_size": str(row["my_size"] or "").strip().upper(),
        "order_qty": order_qty,
        "received_qty": received_qty,
        "status": _status_from_source(row["status"], received_qty=received_qty, order_qty=order_qty),
        "unit_cost_kzt": _as_float(row["unit_cost_kzt"]),
        "unit_cost_cny": 0.0,
        "po_date": row["po_date"],
        "est_arrival_date": row["est_arrival_date"],
        "actual_arrival_date": row["actual_arrival_date"],
    }


def _single_existing_part(conn: sqlite3.Connection, po_id: str) -> str | None:
    if not _table_exists(conn, "po_line") or "po_part_id" not in _columns(conn, "po_line"):
        return None
    rows = conn.execute(
        """
        SELECT DISTINCT po_part_id
        FROM po_line
        WHERE po_id = ?
          AND COALESCE(TRIM(po_part_id), '') <> ''
        """,
        (po_id,),
    ).fetchall()
    parts = [str(row["po_part_id"]) for row in rows if str(row["po_part_id"] or "").strip()]
    return parts[0] if len(parts) == 1 else None


def _coarse_ledger_rows(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    return conn.execute(
        """
        SELECT
            ledger_id,
            event_date,
            sku_key,
            sku_id,
            my_size,
            store_code,
            qty_change,
            reference_id,
            reference_type
        FROM stock_ledger
        WHERE UPPER(COALESCE(event_type, '')) = 'INBOUND'
          AND COALESCE(qty_change, 0) > 0
          AND UPPER(COALESCE(reference_type, '')) = 'PO'
        ORDER BY ledger_id
        """
    ).fetchall()


def _fact_po_match(conn: sqlite3.Connection, ledger: sqlite3.Row) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    rows = conn.execute(
        """
        SELECT *
        FROM fact_po_lines
        WHERE po_id = ?
          AND sku_id = ?
        """,
        (ledger["reference_id"], ledger["sku_id"]),
    ).fetchall()
    if len(rows) != 1:
        return None, {
            "ledger_id": ledger["ledger_id"],
            "reference_id": ledger["reference_id"],
            "sku_id": ledger["sku_id"],
            "reason": "SOURCE_MATCH_NOT_ONE_TO_ONE",
            "match_count": len(rows),
        }
    row = rows[0]
    if _as_int(row["received_qty"]) != _as_int(ledger["qty_change"]):
        return None, {
            "ledger_id": ledger["ledger_id"],
            "reference_id": ledger["reference_id"],
            "sku_id": ledger["sku_id"],
            "reason": "LEDGER_QTY_DIFFERS_FROM_SOURCE_RECEIVED_QTY",
            "ledger_qty": ledger["qty_change"],
            "source_received_qty": row["received_qty"],
        }
    target_part = _single_existing_part(conn, str(row["po_id"] or "")) or str(row["po_id"] or "").strip()
    return _source_line_from_fact(row, po_part_id=target_part), None


def _open_source_lines(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    if not _table_exists(conn, "fact_po_lines"):
        return []
    placeholders = ",".join("?" for _ in OPEN_PO_IDS)
    rows = conn.execute(
        f"""
        SELECT *
        FROM fact_po_lines
        WHERE po_id IN ({placeholders})
        ORDER BY po_id, sku_id
        """,
        tuple(sorted(OPEN_PO_IDS)),
    ).fetchall()
    return [_source_line_from_fact(row, po_part_id=str(row["po_id"] or "").strip()) for row in rows]


def _dedupe_lines(lines: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out: dict[tuple[str, str, str, str], dict[str, Any]] = {}
    for row in lines:
        key = (row["po_id"], row["po_part_id"], row["sku_key"], row["my_size"])
        out[key] = row
    return [out[key] for key in sorted(out)]


def _po_line_exists(conn: sqlite3.Connection, row: dict[str, Any]) -> bool:
    if not _table_exists(conn, "po_line"):
        return False
    found = conn.execute(
        """
        SELECT 1
        FROM po_line
        WHERE po_id = ?
          AND COALESCE(po_part_id, '') = COALESCE(?, '')
          AND sku_key = ?
          AND my_size = ?
        LIMIT 1
        """,
        (row["po_id"], row["po_part_id"], row["sku_key"], row["my_size"]),
    ).fetchone()
    return found is not None


def build_po_inbound_line_grain_plan(conn: sqlite3.Connection) -> POInboundPlan:
    required = {"fact_po_lines", "stock_ledger", "po_header", "po_part", "po_line"}
    missing = sorted(table for table in required if not _table_exists(conn, table))
    if missing:
        return POInboundPlan(
            summary={"missing_tables": missing, "is_safe_to_apply": False},
            po_headers=[],
            po_parts=[],
            po_lines=[],
            ledger_updates=[],
            blocked_rows=[{"reason": "MISSING_TABLES", "missing_tables": missing}],
        )

    blocked_rows: list[dict[str, Any]] = []
    source_lines: list[dict[str, Any]] = []
    ledger_updates: list[dict[str, Any]] = []
    coarse_rows = _coarse_ledger_rows(conn)
    for ledger in coarse_rows:
        source_line, blocked = _fact_po_match(conn, ledger)
        if blocked is not None:
            blocked_rows.append(blocked)
            continue
        assert source_line is not None
        source_lines.append(source_line)
        ledger_updates.append(
            {
                "ledger_id": ledger["ledger_id"],
                "old_reference_type": ledger["reference_type"],
                "old_reference_id": ledger["reference_id"],
                "target_reference_type": "PO_PART",
                "target_reference_id": source_line["po_part_id"],
                "sku_id": ledger["sku_id"],
                "qty_change": ledger["qty_change"],
                "source_table": source_line["source_table"],
                "source_row_id": source_line["source_row_id"],
            }
        )

    source_lines.extend(_open_source_lines(conn))
    source_lines = _dedupe_lines(source_lines)
    po_lines = [row for row in source_lines if not _po_line_exists(conn, row)]

    part_totals: dict[str, dict[str, Any]] = {}
    header_totals: dict[str, dict[str, Any]] = {}
    for row in source_lines:
        part = part_totals.setdefault(
            row["po_part_id"],
            {
                "po_part_id": row["po_part_id"],
                "po_id": row["po_id"],
                "status": row["status"],
                "total_units": 0,
            },
        )
        part["total_units"] += row["order_qty"]
        if row["status"] != "RECEIVED":
            part["status"] = row["status"]
        header = header_totals.setdefault(
            row["po_id"],
            {
                "po_id": row["po_id"],
                "supplier_code": "LEGACY_FACT_PO_LINES",
                "status": row["status"],
                "units_total": 0,
                "units_received": 0,
            },
        )
        header["units_total"] += row["order_qty"]
        header["units_received"] += row["received_qty"]
        if row["status"] != "RECEIVED":
            header["status"] = row["status"]

    po_parts = [
        row
        for row in part_totals.values()
        if conn.execute("SELECT 1 FROM po_part WHERE po_part_id = ? LIMIT 1", (row["po_part_id"],)).fetchone()
        is None
    ]
    po_headers = [
        row
        for row in header_totals.values()
        if conn.execute("SELECT 1 FROM po_header WHERE po_id = ? LIMIT 1", (row["po_id"],)).fetchone()
        is None
    ]
    summary = {
        "coarse_inbound_count": len(coarse_rows),
        "unmatched_or_ambiguous_count": len(blocked_rows),
        "po_header_insert_count": len(po_headers),
        "po_part_insert_count": len(po_parts),
        "po_line_insert_count": len(po_lines),
        "ledger_update_count": len(ledger_updates),
        "is_safe_to_apply": not blocked_rows,
    }
    return POInboundPlan(
        summary=summary,
        po_headers=sorted(po_headers, key=lambda row: row["po_id"]),
        po_parts=sorted(po_parts, key=lambda row: row["po_part_id"]),
        po_lines=sorted(po_lines, key=lambda row: (row["po_id"], row["po_part_id"], row["sku_id"])),
        ledger_updates=ledger_updates,
        blocked_rows=blocked_rows,
    )


def _insert_dynamic(conn: sqlite3.Connection, table: str, payload: dict[str, Any]) -> None:
    cols = _columns(conn, table)
    usable = {key: value for key, value in payload.items() if key in cols}
    fields = ", ".join(usable)
    placeholders = ", ".join("?" for _ in usable)
    conn.execute(f"INSERT INTO {table} ({fields}) VALUES ({placeholders})", list(usable.values()))


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")


def _write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = sorted({key for row in rows for key in row.keys()})
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def _assert_apply_allowed(db_path: Path, *, env_gate_value: str | None) -> None:
    value = env_gate_value if env_gate_value is not None else os.environ.get(ENV_GATE)
    if value != "1":
        raise RuntimeError(f"{ENV_GATE}=1 is required for apply")
    if db_path.resolve() == DEFAULT_DB_PATH.resolve() and os.environ.get(PRODUCTION_ENV_GATE) != "1":
        raise RuntimeError(f"{PRODUCTION_ENV_GATE}=1 is required for production DB apply")


def materialize_po_inbound_line_grain(
    *,
    db_path: Path,
    output_root: Path,
    apply: bool = False,
    env_gate_value: str | None = None,
) -> dict[str, Any]:
    backup_path: Path | None = None
    if apply:
        _assert_apply_allowed(db_path, env_gate_value=env_gate_value)
        backup_path = backup_database(db_path, output_root / "backups", compress=False)

    with _connect(db_path) as conn:
        plan = build_po_inbound_line_grain_plan(conn)
        if apply and not plan.is_safe_to_apply:
            raise RuntimeError("PO inbound plan is not safe to apply; see blocked ledger")
        applied = {
            "po_header": 0,
            "po_part": 0,
            "po_line": 0,
            "stock_ledger": 0,
        }
        if apply:
            for row in plan.po_headers:
                _insert_dynamic(conn, "po_header", row)
                applied["po_header"] += 1
            for row in plan.po_parts:
                _insert_dynamic(conn, "po_part", row)
                applied["po_part"] += 1
            for row in plan.po_lines:
                _insert_dynamic(conn, "po_line", row)
                applied["po_line"] += 1
            for row in plan.ledger_updates:
                cursor = conn.execute(
                    """
                    UPDATE stock_ledger
                    SET reference_type = ?,
                        reference_id = ?
                    WHERE ledger_id = ?
                    """,
                    (row["target_reference_type"], row["target_reference_id"], row["ledger_id"]),
                )
                applied["stock_ledger"] += max(cursor.rowcount, 0)
            conn.commit()

    summary = {**plan.summary, "applied": apply, "applied_counts": applied}
    payload = {
        "summary": summary,
        "db_path": str(db_path),
        "backup_path": str(backup_path) if backup_path else None,
        "outputs": {
            "po_headers_csv": str(output_root / "po_headers_to_insert.csv"),
            "po_parts_csv": str(output_root / "po_parts_to_insert.csv"),
            "po_lines_csv": str(output_root / "po_lines_to_insert.csv"),
            "ledger_updates_csv": str(output_root / "stock_ledger_reference_updates.csv"),
            "blocked_csv": str(output_root / "po_inbound_blocked.csv"),
        },
    }
    output_root.mkdir(parents=True, exist_ok=True)
    _write_json(output_root / "po_inbound_line_grain_summary.json", payload)
    _write_csv(output_root / "po_headers_to_insert.csv", plan.po_headers)
    _write_csv(output_root / "po_parts_to_insert.csv", plan.po_parts)
    _write_csv(output_root / "po_lines_to_insert.csv", plan.po_lines)
    _write_csv(output_root / "stock_ledger_reference_updates.csv", plan.ledger_updates)
    _write_csv(output_root / "po_inbound_blocked.csv", plan.blocked_rows)
    return payload


def main() -> int:
    parser = argparse.ArgumentParser(description="Materialize C3 PO inbound line-grain references")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB_PATH)
    parser.add_argument("--xlsx", type=Path, default=None, help="Accepted for command compatibility; not mutated")
    parser.add_argument("--as-of", default=None, help="Accepted for command compatibility")
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    try:
        result = materialize_po_inbound_line_grain(
            db_path=args.db,
            output_root=args.output_root,
            apply=args.apply,
        )
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(result["summary"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
