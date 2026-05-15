from __future__ import annotations

import sqlite3
from datetime import date
from pathlib import Path

from scripts.rebuild_snapshot import rebuild_snapshot
from scripts.translate_orders_to_cashflow_events import translate_orders


def _create_snapshot_db(path: Path) -> None:
    conn = sqlite3.connect(path)
    conn.execute(
        """
        CREATE TABLE dim_sku (
            sku_key TEXT PRIMARY KEY,
            active_flag INTEGER
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE dim_sku_size (
            sku_id TEXT PRIMARY KEY,
            sku_key TEXT,
            my_size TEXT,
            active_flag INTEGER
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE stock_ledger (
            ledger_id INTEGER PRIMARY KEY AUTOINCREMENT,
            event_date DATE NOT NULL,
            event_time DATETIME DEFAULT CURRENT_TIMESTAMP,
            event_type TEXT NOT NULL,
            sku_key TEXT NOT NULL,
            sku_id TEXT NOT NULL,
            my_size TEXT NOT NULL,
            store_code TEXT DEFAULT 'UNIVERSAL',
            qty_change INTEGER NOT NULL,
            running_balance INTEGER,
            reference_id TEXT,
            reference_type TEXT,
            kaspi_offer_name TEXT,
            notes TEXT,
            input_source TEXT DEFAULT 'SYSTEM',
            created_by TEXT DEFAULT 'system',
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            idempotency_key TEXT
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE fact_inventory_snapshot_size (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            snapshot_date TEXT NOT NULL,
            sku_id TEXT NOT NULL,
            sku_key TEXT NOT NULL,
            my_size TEXT NOT NULL,
            current_stock INTEGER NOT NULL DEFAULT 0,
            inbound_stock INTEGER NOT NULL DEFAULT 0,
            created_at TEXT DEFAULT (datetime('now')),
            UNIQUE(snapshot_date, sku_id)
        )
        """
    )
    conn.execute("INSERT INTO dim_sku VALUES ('SKU_A', 1)")
    conn.execute("INSERT INTO dim_sku_size VALUES ('SKU_A_M', 'SKU_A', 'M', 1)")
    conn.execute(
        """
        INSERT INTO stock_ledger (
            event_date, event_type, sku_key, sku_id, my_size, store_code,
            qty_change, running_balance
        ) VALUES ('2026-05-03', 'INITIAL', 'SKU_A', 'SKU_A_M', 'M', 'UNIVERSAL', 7, 7)
        """
    )
    conn.commit()
    conn.close()


def test_rebuild_snapshot_supports_db_path_and_dry_run_compare(tmp_path: Path) -> None:
    db_path = tmp_path / "app.db"
    _create_snapshot_db(db_path)

    dry = rebuild_snapshot(
        snapshot_date=date(2026, 5, 4),
        store_code="UNIVERSAL",
        mode="ledger",
        compare=True,
        apply=False,
        db_path=db_path,
    )
    assert dry["apply_status"] == "DRY_RUN"
    assert dry["rows_created"] == 1
    with sqlite3.connect(db_path) as conn:
        assert (
            conn.execute(
                "SELECT COUNT(*) FROM fact_inventory_snapshot_size WHERE snapshot_date='2026-05-04'"
            ).fetchone()[0]
            == 0
        )

    applied = rebuild_snapshot(
        snapshot_date=date(2026, 5, 4),
        store_code="UNIVERSAL",
        mode="ledger",
        compare=True,
        apply=True,
        db_path=db_path,
    )
    assert applied["apply_status"] == "APPLIED"
    with sqlite3.connect(db_path) as conn:
        assert (
            conn.execute(
                "SELECT current_stock FROM fact_inventory_snapshot_size WHERE snapshot_date='2026-05-04'"
            ).fetchone()[0]
            == 7
        )


def test_translate_orders_writes_report_to_output_path(tmp_path: Path) -> None:
    db_path = tmp_path / "app.db"
    conn = sqlite3.connect(db_path)
    conn.execute(
        """
        CREATE TABLE fact_orders_kaspi (
            order_id TEXT,
            store_code TEXT,
            created_at TEXT,
            status_updated_at TEXT,
            actual_shipment_date TEXT,
            planned_shipment_date TEXT,
            internal_status TEXT,
            kaspi_status TEXT,
            sku_key TEXT,
            sku_id TEXT,
            quantity INTEGER,
            unit_price_kzt REAL
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE fact_cashflow_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            event_date TEXT NOT NULL,
            event_type TEXT NOT NULL,
            account TEXT NOT NULL,
            amount_kzt REAL NOT NULL,
            store_code TEXT,
            sku_key TEXT,
            sku_id TEXT,
            ref_type TEXT,
            ref_id TEXT,
            notes TEXT,
            source TEXT NOT NULL DEFAULT 'SYSTEM',
            run_id TEXT,
            event_hash TEXT NOT NULL
        )
        """
    )
    conn.commit()
    conn.close()

    output_path = tmp_path / "evidence" / "orders_to_cashflow_report.txt"
    translate_orders(
        db_path,
        since=date(2026, 4, 16),
        until=date(2026, 5, 4),
        apply=False,
        run_id="agent22-test",
        allow_missing=True,
        output_path=output_path,
    )

    assert output_path.exists()
    assert "Orders scanned: 0" in output_path.read_text()
