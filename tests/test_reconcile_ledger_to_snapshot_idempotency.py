from __future__ import annotations

import os
import sqlite3
import subprocess
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _seed_reconcile_db(db_path: Path) -> None:
    conn = sqlite3.connect(str(db_path))
    conn.executescript(
        """
        CREATE TABLE fact_inventory_snapshot_size (
            snapshot_date TEXT NOT NULL,
            sku_id TEXT NOT NULL,
            sku_key TEXT NOT NULL,
            my_size TEXT NOT NULL,
            current_stock INTEGER NOT NULL
        );
        CREATE TABLE stock_ledger (
            ledger_id INTEGER PRIMARY KEY AUTOINCREMENT,
            event_date TEXT NOT NULL,
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
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE dim_sku_size (
            sku_id TEXT PRIMARY KEY,
            sku_key TEXT NOT NULL,
            my_size TEXT NOT NULL
        );
        INSERT INTO fact_inventory_snapshot_size
            (snapshot_date, sku_id, sku_key, my_size, current_stock)
        VALUES
            ('2026-04-15', 'SKU1_M', 'SKU1', 'M', 5);
        INSERT INTO dim_sku_size (sku_id, sku_key, my_size)
        VALUES ('SKU1_M', 'SKU1', 'M');
        INSERT INTO stock_ledger (
            event_date, event_type, sku_key, sku_id, my_size, store_code,
            qty_change, reference_id, reference_type, notes, input_source, created_by
        ) VALUES (
            '2026-04-14', 'ADJUSTMENT', 'SKU1', 'SKU1_M', 'M', 'UNIVERSAL',
            5, 'SNAPSHOT_RECON_2026-04-15', 'ADJUSTMENT',
            'Existing reconcile row on morning adjustment date', 'SYSTEM', 'system'
        );
        INSERT INTO stock_ledger (
            event_date, event_type, sku_key, sku_id, my_size, store_code,
            qty_change, reference_id, reference_type, notes, input_source, created_by
        ) VALUES (
            '2026-04-14', 'SALE', 'SKU1', 'SKU1_M', 'M', 'UNIVERSAL',
            -2, 'ORDER1', 'SALE', 'Backfilled movement after reconcile', 'TEST', 'test'
        );
        """
    )
    conn.commit()
    conn.close()


def test_reconcile_apply_is_idempotent_when_prior_adjustment_is_on_adjust_date(tmp_path: Path) -> None:
    db_path = tmp_path / "app.db"
    _seed_reconcile_db(db_path)

    env = os.environ.copy()
    env["PYTHONPATH"] = str(PROJECT_ROOT)
    env["ENABLE_STOCK_RECONCILE_WRITE"] = "1"
    result = subprocess.run(
        [
            sys.executable,
            str(PROJECT_ROOT / "scripts" / "reconcile_ledger_to_snapshot.py"),
            "--snapshot-date",
            "2026-04-15",
            "--db",
            str(db_path),
            "--apply",
        ],
        cwd=PROJECT_ROOT,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr or result.stdout

    conn = sqlite3.connect(str(db_path))
    count = conn.execute(
        """
        SELECT COUNT(*)
        FROM stock_ledger
        WHERE event_type = 'ADJUSTMENT'
          AND reference_id = 'SNAPSHOT_RECON_2026-04-15'
          AND sku_id = 'SKU1_M'
        """
    ).fetchone()[0]
    conn.close()

    assert count == 1
