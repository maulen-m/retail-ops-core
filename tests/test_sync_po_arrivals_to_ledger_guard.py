from __future__ import annotations

import sqlite3
from pathlib import Path

from scripts.sync_po_arrivals_to_ledger import build_po_arrival_sync_plan


def _connect(path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.executescript(
        """
        CREATE TABLE fact_po_lines (
            id INTEGER PRIMARY KEY,
            po_id TEXT NOT NULL,
            store_code TEXT NOT NULL,
            sku_key TEXT NOT NULL,
            sku_id TEXT NOT NULL,
            my_size TEXT NOT NULL,
            received_qty INTEGER,
            actual_arrival_date TEXT,
            status TEXT
        );
        CREATE TABLE po_line (
            po_id TEXT NOT NULL,
            po_part_id TEXT,
            sku_id TEXT NOT NULL,
            my_size TEXT NOT NULL
        );
        CREATE TABLE stock_ledger (
            ledger_id INTEGER PRIMARY KEY AUTOINCREMENT,
            event_date TEXT,
            event_type TEXT,
            sku_key TEXT,
            sku_id TEXT,
            my_size TEXT,
            store_code TEXT,
            qty_change INTEGER,
            running_balance INTEGER,
            reference_id TEXT,
            reference_type TEXT,
            notes TEXT,
            input_source TEXT,
            created_by TEXT,
            idempotency_key TEXT
        );
        """
    )
    return conn


def _seed_source(conn: sqlite3.Connection, *, received_qty: int = 5) -> None:
    conn.execute(
        """
        INSERT INTO fact_po_lines (
            po_id, store_code, sku_key, sku_id, my_size,
            received_qty, actual_arrival_date, status
        ) VALUES ('PO-1', 'UNIVERSAL', 'SKU_A', 'SKU_A_M', 'M', ?,
                  '2026-01-14', 'DELIVERED')
        """,
        (received_qty,),
    )
    conn.execute(
        "INSERT INTO po_line (po_id, po_part_id, sku_id, my_size) "
        "VALUES ('PO-1', 'PO-1.0', 'SKU_A_M', 'M')"
    )
    conn.commit()


def test_po_part_receipt_counts_as_existing_and_prevents_replay(tmp_path: Path) -> None:
    conn = _connect(tmp_path / "app.db")
    _seed_source(conn)
    conn.execute(
        """
        INSERT INTO stock_ledger (
            event_date, event_type, sku_key, sku_id, my_size, store_code,
            qty_change, reference_id, reference_type
        ) VALUES ('2026-01-14', 'INBOUND', 'SKU_A', 'SKU_A_M', 'M',
                  'UNIVERSAL', 5, 'PO-1.0', 'PO_PART')
        """
    )
    conn.commit()

    plan = build_po_arrival_sync_plan(conn, snapshot_date="2026-07-12")

    assert plan["summary"]["source_line_count"] == 1
    assert plan["summary"]["insert_count"] == 0
    assert plan["summary"]["insert_units"] == 0
    assert plan["blocked_rows"] == []


def test_partial_po_part_receipt_only_plans_source_shortfall(tmp_path: Path) -> None:
    conn = _connect(tmp_path / "app.db")
    _seed_source(conn)
    conn.execute(
        """
        INSERT INTO stock_ledger (
            event_date, event_type, sku_key, sku_id, my_size, store_code,
            qty_change, reference_id, reference_type
        ) VALUES ('2026-01-14', 'INBOUND', 'SKU_A', 'SKU_A_M', 'M',
                  'UNIVERSAL', 3, 'PO-1.0', 'PO_PART')
        """
    )
    conn.commit()

    plan = build_po_arrival_sync_plan(conn, snapshot_date="2026-07-12")

    assert plan["summary"]["insert_count"] == 1
    assert plan["summary"]["insert_units"] == 2
    assert plan["insert_rows"][0]["reference_type"] == "PO_PART"
    assert plan["insert_rows"][0]["reference_id"] == "PO-1.0"
    assert plan["insert_rows"][0]["qty_change"] == 2
    assert plan["insert_rows"][0]["idempotency_key"]


def test_ambiguous_po_part_mapping_fails_closed(tmp_path: Path) -> None:
    conn = _connect(tmp_path / "app.db")
    _seed_source(conn)
    conn.execute(
        "INSERT INTO po_line (po_id, po_part_id, sku_id, my_size) "
        "VALUES ('PO-1', 'PO-1.1', 'SKU_A_M', 'M')"
    )
    conn.commit()

    plan = build_po_arrival_sync_plan(conn, snapshot_date="2026-07-12")

    assert plan["summary"]["insert_count"] == 0
    assert plan["summary"]["blocked_count"] == 1
    assert plan["blocked_rows"][0]["reason"] == "AMBIGUOUS_PO_PART_MAPPING"


def test_missing_po_part_mapping_fails_closed_instead_of_emitting_coarse_po(
    tmp_path: Path,
) -> None:
    conn = _connect(tmp_path / "app.db")
    conn.execute(
        """
        INSERT INTO fact_po_lines (
            po_id, store_code, sku_key, sku_id, my_size,
            received_qty, actual_arrival_date, status
        ) VALUES ('PO-1', 'UNIVERSAL', 'SKU_A', 'SKU_A_M', 'M', 5,
                  '2026-01-14', 'DELIVERED')
        """
    )
    conn.commit()

    plan = build_po_arrival_sync_plan(conn, snapshot_date="2026-07-12")

    assert plan["summary"]["insert_count"] == 0
    assert plan["blocked_rows"][0]["reason"] == "PO_PART_MAPPING_MISSING"


def test_receipt_overage_is_a_blocker_not_a_silent_noop(tmp_path: Path) -> None:
    conn = _connect(tmp_path / "app.db")
    _seed_source(conn)
    conn.execute(
        """
        INSERT INTO stock_ledger (
            event_date, event_type, sku_key, sku_id, my_size, store_code,
            qty_change, reference_id, reference_type
        ) VALUES ('2026-01-14', 'INBOUND', 'SKU_A', 'SKU_A_M', 'M',
                  'UNIVERSAL', 10, 'PO-1.0', 'PO_PART')
        """
    )
    conn.commit()

    plan = build_po_arrival_sync_plan(conn, snapshot_date="2026-07-12")

    assert plan["summary"]["insert_count"] == 0
    assert plan["blocked_rows"][0]["reason"] == "RECEIPT_OVERAGE"
    assert plan["blocked_rows"][0]["overage_units"] == 5
