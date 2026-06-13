#!/usr/bin/env python3
"""Materialize SALE/RETURN stock-ledger events from sales_fact_v2.

Default: dry run. Apply requires ENABLE_STOCK_LEDGER_SALES_REPLAY_WRITE=1 and
--apply. The script only inserts idempotent SALE/RETURN rows and never updates or
deletes existing stock_ledger rows.
"""

from __future__ import annotations

import argparse
from datetime import date, datetime
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

DEFAULT_DB = PROJECT_ROOT / "db" / "app.db"
DEFAULT_OUTPUT_ROOT = PROJECT_ROOT / "exports" / "validation" / "stock_ledger_sales_replay"
INVENTORY_POOL_STORE_CODE = "UNIVERSAL"


def _table_exists(conn: sqlite3.Connection, name: str) -> bool:
    return conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
        (name,),
    ).fetchone() is not None


def _table_columns(conn: sqlite3.Connection, name: str) -> set[str]:
    if not _table_exists(conn, name):
        return set()
    return {row[1] for row in conn.execute(f"PRAGMA table_info({name})").fetchall()}


def _idempotency_key(event: dict[str, Any]) -> str:
    parts = [
        "sales_fact_v2_stock_replay_v1",
        str(event.get("event_type") or ""),
        str(event.get("reference_id") or ""),
        str(event.get("source_store_code") or ""),
        str(event.get("sku_id") or ""),
        str(event.get("event_date") or ""),
    ]
    return hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()


def _normalize_status(value: Any) -> str:
    raw = str(value or "").strip().upper()
    if raw in {"RETURNED", "RETURN"}:
        return "RETURNED"
    if raw in {"DELIVERED", "COMPLETED"}:
        return "DELIVERED"
    if raw in {"CANCELLED", "CANCELED"}:
        return "CANCELLED"
    return raw or "UNKNOWN"


def _parse_event_date(value: Any) -> str | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return date.fromisoformat(text[:10]).isoformat()
    except ValueError:
        return None


def _accepted_return_qty_by_order_sku(
    conn: sqlite3.Connection,
) -> dict[tuple[str, str, str], int]:
    if not _table_exists(conn, "return_qc_event"):
        return {}
    cols = _table_columns(conn, "return_qc_event")
    required = {"order_id", "store_code", "sku_id", "accepted_active_qty"}
    if not required.issubset(cols):
        return {}
    rows = conn.execute(
        """
        SELECT
            UPPER(COALESCE(store_code, 'UNIVERSAL')) AS store_code,
            order_id,
            sku_id,
            COALESCE(SUM(accepted_active_qty), 0) AS accepted_active_qty
        FROM return_qc_event
        WHERE order_id IS NOT NULL
          AND trim(order_id) <> ''
          AND sku_id IS NOT NULL
          AND trim(sku_id) <> ''
        GROUP BY UPPER(COALESCE(store_code, 'UNIVERSAL')), order_id, sku_id
        """
    ).fetchall()
    return {
        (
            str(row["store_code"] or "UNIVERSAL").strip().upper(),
            str(row["order_id"] or "").strip(),
            str(row["sku_id"] or "").strip(),
        ): int(row["accepted_active_qty"] or 0)
        for row in rows
    }


def _active_product_identity_quarantine_pairs(
    conn: sqlite3.Connection,
) -> set[tuple[str, str]]:
    table = "fact_order_entry_product_identity_quarantine"
    if not _table_exists(conn, table):
        return set()
    cols = _table_columns(conn, table)
    if not {"store_code", "order_id"}.issubset(cols):
        return set()
    active_clause = "COALESCE(active_flag, 1) = 1" if "active_flag" in cols else "1 = 1"
    publication_clause = (
        "COALESCE(publication_exclusion_required, 1) = 1"
        if "publication_exclusion_required" in cols
        else "1 = 1"
    )
    rows = conn.execute(
        f"""
        SELECT UPPER(COALESCE(store_code, 'UNIVERSAL')) AS store_code,
               CAST(order_id AS TEXT) AS order_id
        FROM {table}
        WHERE {active_clause}
          AND {publication_clause}
        """
    ).fetchall()
    return {
        (
            str(row["store_code"] or "UNIVERSAL").strip().upper(),
            str(row["order_id"] or "").strip(),
        )
        for row in rows
        if str(row["order_id"] or "").strip()
    }


def _active_header_only_source_gap_quarantine_pairs(
    conn: sqlite3.Connection,
) -> set[tuple[str, str]]:
    table = "fact_order_entry_header_only_source_gap_quarantine"
    if not _table_exists(conn, table):
        return set()
    cols = _table_columns(conn, table)
    if not {"store_code", "order_id"}.issubset(cols):
        return set()
    active_clause = "COALESCE(active_flag, 1) = 1" if "active_flag" in cols else "1 = 1"
    rows = conn.execute(
        f"""
        SELECT UPPER(COALESCE(store_code, 'UNIVERSAL')) AS store_code,
               CAST(order_id AS TEXT) AS order_id
        FROM {table}
        WHERE {active_clause}
        """
    ).fetchall()
    return {
        (
            str(row["store_code"] or "UNIVERSAL").strip().upper(),
            str(row["order_id"] or "").strip(),
        )
        for row in rows
        if str(row["order_id"] or "").strip()
    }


def _candidate_events(
    conn: sqlite3.Connection,
    *,
    start_date: date,
    end_date: date,
) -> tuple[list[dict[str, Any]], list[str], dict[str, int]]:
    if not _table_exists(conn, "sales_fact_v2"):
        raise RuntimeError("sales_fact_v2 missing")
    if not _table_exists(conn, "stock_ledger"):
        raise RuntimeError("stock_ledger missing")

    rows = conn.execute(
        """
        SELECT
            order_id, order_date, sku_key, sku_id, my_size, kaspi_offer_name,
            UPPER(COALESCE(store_code, 'UNIVERSAL')) AS store_code,
            quantity, status, return_flag, return_date
        FROM sales_fact_v2
        WHERE order_date BETWEEN ? AND ?
        ORDER BY order_date, order_id, sku_id, kaspi_offer_name
        """,
        (start_date.isoformat(), end_date.isoformat()),
    ).fetchall()

    events: list[dict[str, Any]] = []
    errors: list[str] = []
    accepted_return_qty = _accepted_return_qty_by_order_sku(conn)
    product_identity_quarantined_pairs = _active_product_identity_quarantine_pairs(conn)
    header_only_quarantined_pairs = _active_header_only_source_gap_quarantine_pairs(conn)
    quarantine_counts = {
        "product_identity_quarantined_order_count": 0,
        "header_only_source_gap_quarantined_order_count": 0,
    }
    for row in rows:
        order_id = str(row["order_id"] or "").strip()
        sku_key = str(row["sku_key"] or "").strip()
        sku_id = str(row["sku_id"] or "").strip()
        my_size = str(row["my_size"] or "").strip()
        qty = int(round(float(row["quantity"] or 0)))
        order_date = _parse_event_date(row["order_date"])
        status = _normalize_status(row["status"])
        return_flag = int(row["return_flag"] or 0)
        source_store_code = str(row["store_code"] or "").strip().upper() or INVENTORY_POOL_STORE_CODE
        if (source_store_code, order_id) in product_identity_quarantined_pairs:
            quarantine_counts["product_identity_quarantined_order_count"] += 1
            continue
        if (source_store_code, order_id) in header_only_quarantined_pairs:
            quarantine_counts["header_only_source_gap_quarantined_order_count"] += 1
            continue
        emits_stock_event = status in {"DELIVERED", "RETURNED"} or bool(return_flag)
        if emits_stock_event and (
            not order_id or not sku_key or not sku_id or not my_size or qty <= 0 or not order_date
        ):
            errors.append(f"missing required sales evidence for order_id={order_id or '<blank>'} sku_id={sku_id or '<blank>'}")
            continue
        if emits_stock_event:
            events.append(
                {
                    "event_date": order_date,
                    "event_type": "SALE",
                    "sku_key": sku_key,
                    "sku_id": sku_id,
                    "my_size": my_size,
                    "store_code": INVENTORY_POOL_STORE_CODE,
                    "source_store_code": source_store_code,
                    "qty_change": -abs(qty),
                    "reference_id": order_id,
                    "reference_type": "SALE",
                    "kaspi_offer_name": row["kaspi_offer_name"],
                    "notes": "sales_fact_v2 stock replay SALE",
                    "input_source": "KASPI_API_SALES_FACT_V2_REPLAY",
                    "created_by": "agent22",
                }
            )
        if status == "RETURNED" or return_flag:
            return_date = _parse_event_date(row["return_date"]) or order_date
            accepted_qty = accepted_return_qty.get((source_store_code, order_id, sku_id), 0)
            active_qty = min(abs(qty), max(0, int(accepted_qty)))
            if active_qty > 0:
                events.append(
                    {
                        "event_date": return_date,
                        "event_type": "RETURN",
                        "sku_key": sku_key,
                        "sku_id": sku_id,
                        "my_size": my_size,
                        "store_code": INVENTORY_POOL_STORE_CODE,
                        "source_store_code": source_store_code,
                        "qty_change": active_qty,
                        "reference_id": order_id,
                        "reference_type": "SALE",
                        "kaspi_offer_name": row["kaspi_offer_name"],
                        "notes": "sales_fact_v2 stock replay RETURN after QC accepted_active_qty",
                        "input_source": "KASPI_API_SALES_FACT_V2_REPLAY",
                        "created_by": "agent22",
                    }
                )

    for event in events:
        event["idempotency_key"] = _idempotency_key(event)

    events.sort(
        key=lambda e: (
            str(e["event_date"]),
            str(e["reference_id"]),
            str(e["sku_id"]),
            0 if e["event_type"] == "SALE" else 1,
        )
    )
    return events, errors, quarantine_counts


def _existing_idempotency_keys(conn: sqlite3.Connection, keys: list[str]) -> set[str]:
    if not keys:
        return set()
    if "idempotency_key" not in _table_columns(conn, "stock_ledger"):
        return set()
    placeholders = ",".join("?" for _ in keys)
    rows = conn.execute(
        f"SELECT idempotency_key FROM stock_ledger WHERE idempotency_key IN ({placeholders})",
        keys,
    ).fetchall()
    return {str(row[0]) for row in rows if row[0]}


def _current_balances(conn: sqlite3.Connection) -> dict[tuple[str, str], int]:
    rows = conn.execute(
        """
        SELECT sku_id, UPPER(COALESCE(store_code, 'UNIVERSAL')) AS store_code,
               COALESCE(SUM(qty_change), 0) AS balance
        FROM stock_ledger
        GROUP BY sku_id, UPPER(COALESCE(store_code, 'UNIVERSAL'))
        """
    ).fetchall()
    return {(str(row[0]), str(row[1])): int(row[2] or 0) for row in rows}


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


def run_materialization(
    *,
    db_path: Path,
    start_date: date,
    end_date: date,
    output_root: Path,
    apply: bool = False,
) -> dict[str, Any]:
    if not db_path.exists():
        raise FileNotFoundError(f"DB not found: {db_path}")
    if start_date > end_date:
        raise ValueError("start_date must be <= end_date")

    output_root.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    try:
        candidates, errors, quarantine_counts = _candidate_events(conn, start_date=start_date, end_date=end_date)
        existing_keys = _existing_idempotency_keys(
            conn,
            [str(event["idempotency_key"]) for event in candidates],
        )
        to_insert = [
            event for event in candidates if str(event["idempotency_key"]) not in existing_keys
        ]
        summary: dict[str, Any] = {
            "generated_at": datetime.now().strftime("%Y-%m-%dT%H:%M:%S%z"),
            "db_path": str(db_path),
            "start_date": start_date.isoformat(),
            "end_date": end_date.isoformat(),
            "apply_status": "DRY_RUN",
            "candidate_count": len(candidates),
            "insert_count": len(to_insert),
            "existing_count": len(candidates) - len(to_insert),
            "rows_applied": 0,
            "errors_count": len(errors),
            "errors_sample": errors[:50],
            "quarantined_order_count": sum(quarantine_counts.values()),
            **quarantine_counts,
            "active_return_units": sum(
                int(event["qty_change"])
                for event in candidates
                if event["event_type"] == "RETURN"
            ),
        }

        if apply:
            if os.environ.get("ENABLE_STOCK_LEDGER_SALES_REPLAY_WRITE") != "1":
                raise RuntimeError(
                    "ENABLE_STOCK_LEDGER_SALES_REPLAY_WRITE=1 is required for --apply"
                )
            rows_applied = _apply_events(conn, to_insert)
            conn.commit()
            summary["apply_status"] = "APPLIED"
            summary["rows_applied"] = rows_applied

        (output_root / "stock_ledger_sales_replay_summary.json").write_text(
            json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        (output_root / "stock_ledger_sales_replay_plan.json").write_text(
            json.dumps({"events_to_insert": to_insert}, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        return summary
    finally:
        conn.close()


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Materialize idempotent stock_ledger SALE/RETURN rows from sales_fact_v2"
    )
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument("--start-date", required=True)
    parser.add_argument("--end-date", required=True)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--apply", action="store_true")
    return parser


def main() -> int:
    args = _build_parser().parse_args()
    summary = run_materialization(
        db_path=args.db,
        start_date=date.fromisoformat(args.start_date),
        end_date=date.fromisoformat(args.end_date),
        output_root=args.output_root,
        apply=bool(args.apply),
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
