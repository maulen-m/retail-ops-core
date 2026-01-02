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
            assigned_size TEXT,
            size_source TEXT,
            size_confidence TEXT
        )
        """
    )
    conn.execute(
        "INSERT INTO fact_orders_kaspi (order_id) VALUES (?)",
        ("ORDER-1",),
    )
    conn.commit()
    conn.close()


def test_sync_crm_sizes_updates_assigned_size(tmp_path: Path) -> None:
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

    stats = sync.sync_crm_sizes(
        db_path=db_path,
        crm_path=crm_path,
        sheet_name=sync.DEFAULT_SHEET,
        as_of=date.today(),
        dry_run=False,
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
    conn.close()

    assert row == ("XL", "CRM_MANUAL", "HIGH")
    assert stats.updated_orders == 1
