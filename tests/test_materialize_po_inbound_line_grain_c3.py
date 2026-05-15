from __future__ import annotations

import sqlite3
from pathlib import Path

from scripts.materialize_po_inbound_line_grain_c3 import (
    build_po_inbound_line_grain_plan,
    materialize_po_inbound_line_grain,
)


def _connect(path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    conn.executescript(
        """
        CREATE TABLE fact_po_lines (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            po_id TEXT NOT NULL,
            store_code TEXT NOT NULL,
            sku_key TEXT NOT NULL,
            sku_id TEXT NOT NULL,
            my_size TEXT NOT NULL,
            order_quantity INTEGER NOT NULL,
            unit_cost_kzt REAL,
            po_date TEXT,
            est_arrival_date TEXT,
            actual_arrival_date TEXT,
            status TEXT,
            received_qty INTEGER
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
            reference_id TEXT,
            reference_type TEXT
        );
        CREATE TABLE po_header (
            po_id TEXT PRIMARY KEY,
            supplier_code TEXT,
            status TEXT,
            units_total INTEGER,
            units_received INTEGER
        );
        CREATE TABLE po_part (
            po_part_id TEXT PRIMARY KEY,
            po_id TEXT NOT NULL,
            status TEXT,
            total_units INTEGER
        );
        CREATE TABLE po_line (
            po_line_id INTEGER PRIMARY KEY AUTOINCREMENT,
            po_id TEXT NOT NULL,
            sku_key TEXT NOT NULL,
            sku_id TEXT NOT NULL,
            my_size TEXT NOT NULL,
            order_qty INTEGER NOT NULL,
            received_qty INTEGER DEFAULT 0,
            unit_cost_cny REAL NOT NULL DEFAULT 0,
            status TEXT DEFAULT 'PENDING',
            po_part_id TEXT
        );
        """
    )
    return conn


def test_po_line_grain_plan_maps_coarse_inbound_to_po_part(tmp_path: Path) -> None:
    db_path = tmp_path / "app.db"
    conn = _connect(db_path)
    conn.execute(
        """
        INSERT INTO fact_po_lines (
            po_id, store_code, sku_key, sku_id, my_size, order_quantity,
            status, received_qty
        ) VALUES ('LEGACY_PO-1', 'UNIVERSAL', 'SKU_A', 'SKU_A_M', 'M', 5,
                  'RECEIVED', 5)
        """
    )
    conn.execute(
        """
        INSERT INTO stock_ledger (
            event_date, event_type, sku_key, sku_id, my_size, store_code,
            qty_change, reference_id, reference_type
        ) VALUES ('2026-05-03', 'INBOUND', 'SKU_A', 'SKU_A_M', 'M', 'UNIVERSAL',
                  5, 'LEGACY_PO-1', 'PO')
        """
    )
    conn.commit()

    plan = build_po_inbound_line_grain_plan(conn)

    assert plan.summary["coarse_inbound_count"] == 1
    assert plan.summary["ledger_update_count"] == 1
    assert plan.summary["po_line_insert_count"] == 1
    assert plan.ledger_updates[0]["target_reference_type"] == "PO_PART"
    assert plan.ledger_updates[0]["target_reference_id"] == "LEGACY_PO-1"


def test_po_line_grain_apply_materializes_open_pending_rows_without_ledger(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "app.db"
    conn = _connect(db_path)
    conn.execute(
        """
        INSERT INTO fact_po_lines (
            po_id, store_code, sku_key, sku_id, my_size, order_quantity,
            status, received_qty
        ) VALUES ('New-CLO_PO-2.1', 'UNIVERSAL', 'SKU_B', 'SKU_B_L', 'L', 7,
                  'PENDING', 0)
        """
    )
    conn.commit()
    conn.close()

    result = materialize_po_inbound_line_grain(
        db_path=db_path,
        output_root=tmp_path / "evidence",
        apply=True,
        env_gate_value="1",
    )

    conn = sqlite3.connect(str(db_path))
    po_line = conn.execute(
        "SELECT po_id, po_part_id, order_qty, received_qty, status FROM po_line"
    ).fetchone()
    ledger_count = conn.execute("SELECT COUNT(*) FROM stock_ledger").fetchone()[0]

    assert result["summary"]["po_line_insert_count"] == 1
    assert po_line == ("New-CLO_PO-2.1", "New-CLO_PO-2.1", 7, 0, "PENDING")
    assert ledger_count == 0


def test_po_line_grain_plan_fails_closed_on_non_unique_source_match(tmp_path: Path) -> None:
    db_path = tmp_path / "app.db"
    conn = _connect(db_path)
    for _ in range(2):
        conn.execute(
            """
            INSERT INTO fact_po_lines (
                po_id, store_code, sku_key, sku_id, my_size, order_quantity,
                status, received_qty
            ) VALUES ('LEGACY_PO-1', 'UNIVERSAL', 'SKU_A', 'SKU_A_M', 'M', 5,
                      'RECEIVED', 5)
            """
        )
    conn.execute(
        """
        INSERT INTO stock_ledger (
            event_date, event_type, sku_key, sku_id, my_size, store_code,
            qty_change, reference_id, reference_type
        ) VALUES ('2026-05-03', 'INBOUND', 'SKU_A', 'SKU_A_M', 'M', 'UNIVERSAL',
                  5, 'LEGACY_PO-1', 'PO')
        """
    )
    conn.commit()

    plan = build_po_inbound_line_grain_plan(conn)

    assert plan.summary["unmatched_or_ambiguous_count"] == 1
    assert plan.is_safe_to_apply is False
