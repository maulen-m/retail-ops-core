from __future__ import annotations

import sqlite3
import sys
from datetime import date
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import scripts.sync_crm_sizes_to_db as sync


def _create_db(path: Path) -> None:
    conn = sqlite3.connect(path)
    conn.execute(
        """
        CREATE TABLE fact_orders_kaspi (
            order_id TEXT PRIMARY KEY,
            store_code TEXT NOT NULL,
            planned_shipment_date TEXT,
            assigned_size TEXT,
            size_source TEXT,
            size_confidence TEXT,
            source TEXT,
            source_file TEXT
        )
        """
    )
    conn.execute(
        "INSERT INTO fact_orders_kaspi (order_id, store_code) VALUES (?, ?)",
        ("ORDER-1", "UNIVERSAL"),
    )
    conn.commit()
    conn.close()


def test_sync_crm_sizes_updates_assigned_size(tmp_path: Path) -> None:
    db_path = tmp_path / "app.db"
    _create_db(db_path)

    crm_path = tmp_path / "crm.xlsx"
    df = pd.DataFrame(
        {
            "OrderID": ["ORDER-1", "ORDER-2"],
            "MY_SIZE": ["XL", "L"],
            "PLANNED_SHIPPING_DATE": [date.today().isoformat(), date.today().isoformat()],
            "STORE_NAME": ["Universal", "AcmeWear"],
        }
    )
    df.to_excel(crm_path, index=False, sheet_name=sync.DEFAULT_SHEET)

    stats = sync.sync_crm_sizes(
        db_path=db_path,
        crm_path=crm_path,
        sheet_name=sync.DEFAULT_SHEET,
        as_of=date.today(),
        dry_run=False,
        upsert_missing=True,
    )

    conn = sqlite3.connect(db_path)
    row = conn.execute(
        """
        SELECT assigned_size, size_source, size_confidence
        FROM fact_orders_kaspi
        WHERE order_id = ?
        """,
        ("ORDER-1",),
    ).fetchone()
    row_missing = conn.execute(
        """
        SELECT assigned_size, size_source, size_confidence, store_code
        FROM fact_orders_kaspi
        WHERE order_id = ?
        """,
        ("ORDER-2",),
    ).fetchone()
    conn.close()

    assert row == ("XL", "CRM_MANUAL", "HIGH")
    assert row_missing == ("L", "CRM_MANUAL", "HIGH", "ACMEWEAR")
    assert stats.updated_orders == 2
    assert stats.inserted_orders == 1


def test_sync_crm_sizes_idempotent(tmp_path: Path) -> None:
    db_path = tmp_path / "app.db"
    _create_db(db_path)

    crm_path = tmp_path / "crm.xlsx"
    df = pd.DataFrame(
        {
            "OrderID": ["ORDER-1"],
            "MY_SIZE": ["XL"],
            "PLANNED_SHIPPING_DATE": [date.today().isoformat()],
        }
    )
    df.to_excel(crm_path, index=False, sheet_name=sync.DEFAULT_SHEET)

    sync.sync_crm_sizes(
        db_path=db_path,
        crm_path=crm_path,
        sheet_name=sync.DEFAULT_SHEET,
        as_of=date.today(),
        dry_run=False,
        upsert_missing=True,
    )

    stats = sync.sync_crm_sizes(
        db_path=db_path,
        crm_path=crm_path,
        sheet_name=sync.DEFAULT_SHEET,
        as_of=date.today(),
        dry_run=False,
        upsert_missing=True,
    )

    assert stats.updated_orders == 0
