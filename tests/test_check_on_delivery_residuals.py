from __future__ import annotations

import sqlite3
from pathlib import Path

from scripts.check_on_delivery_residuals import run_residual_check


def _init_db(db_path: Path) -> None:
    conn = sqlite3.connect(str(db_path))
    conn.executescript(
        """
        CREATE TABLE fact_orders_kaspi (
            order_id TEXT,
            store_code TEXT,
            internal_status TEXT,
            status_updated_at TEXT,
            sku_key TEXT,
            sku_id TEXT
        );
        CREATE TABLE fact_cashflow_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            event_date TEXT,
            event_type TEXT,
            account TEXT,
            amount_kzt REAL,
            store_code TEXT,
            sku_key TEXT,
            sku_id TEXT,
            ref_type TEXT,
            ref_id TEXT,
            notes TEXT,
            source TEXT,
            run_id TEXT,
            event_hash TEXT UNIQUE
        );
        """
    )
    conn.commit()
    conn.close()


def _seed_residual(db_path: Path) -> None:
    conn = sqlite3.connect(str(db_path))
    conn.execute(
        """
        INSERT INTO fact_orders_kaspi
        (order_id, store_code, internal_status, status_updated_at, sku_key, sku_id)
        VALUES ('ORD-R1', 'ACMEWEAR', 'COMPLETED', '2026-02-08', 'SKU_A', 'SKU_A_M')
        """
    )
    conn.execute(
        """
        INSERT INTO fact_cashflow_events
        (event_date, event_type, account, amount_kzt, store_code, sku_key, sku_id, ref_type, ref_id, source, event_hash)
        VALUES ('2026-02-08', 'INVENTORY_MOVE', 'INVENTORY_ON_DELIVERY_COST', 1200, 'ACMEWEAR', 'SKU_A', 'SKU_A_M', 'ORDER', 'ORD-R1', 'ORDER_MODELLED', 'hash-r1')
        """
    )
    conn.commit()
    conn.close()


def test_report_written_and_nonzero_exit_when_residuals_exist(tmp_path: Path) -> None:
    db_path = tmp_path / "app.db"
    output_dir = tmp_path / "reports"
    _init_db(db_path)
    _seed_residual(db_path)

    result = run_residual_check(
        db_path=db_path,
        output_dir=output_dir,
        since="2026-02-01",
        until="2026-02-08",
        send_alert=False,
    )

    assert result["exit_code"] != 0
    assert result["residual_count"] == 1
    assert Path(result["report_path"]).exists()


def test_zero_exit_and_report_when_no_residuals(tmp_path: Path) -> None:
    db_path = tmp_path / "app.db"
    output_dir = tmp_path / "reports"
    _init_db(db_path)

    result = run_residual_check(
        db_path=db_path,
        output_dir=output_dir,
        since="2026-02-01",
        until="2026-02-08",
        send_alert=False,
    )

    assert result["exit_code"] == 0
    assert result["residual_count"] == 0
    assert Path(result["report_path"]).exists()
