from __future__ import annotations

import sqlite3
from pathlib import Path

import pandas as pd

from scripts.classify_webui_db_absence import classify_webui_db_absence


def _seed_db(db_path: Path) -> None:
    conn = sqlite3.connect(db_path)
    conn.executescript(
        """
        CREATE TABLE fact_orders_kaspi (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            order_id TEXT,
            store_code TEXT,
            created_at TEXT,
            planned_shipment_date TEXT,
            actual_shipment_date TEXT,
            courier_transmission_date TEXT,
            internal_status TEXT,
            kaspi_status TEXT,
            updated_at TEXT,
            imported_at TEXT
        );
        CREATE TABLE fact_order_entries_kaspi (
            entry_id TEXT,
            order_id TEXT,
            store_code TEXT,
            offer_id TEXT,
            quantity REAL,
            total_price_kzt REAL
        );
        CREATE TABLE sales_fact_v2 (
            order_id TEXT,
            sku_id TEXT,
            store_code TEXT,
            kaspi_offer_name TEXT,
            order_date TEXT,
            source_file TEXT
        );
        CREATE TABLE fact_sales (
            order_id TEXT,
            order_date TEXT,
            store_code TEXT,
            sku_id TEXT,
            sku_key TEXT,
            quantity REAL,
            line_net_rev REAL
        );
        """
    )
    conn.executemany(
        """
        INSERT INTO fact_orders_kaspi (
            order_id, store_code, created_at, planned_shipment_date, actual_shipment_date,
            courier_transmission_date, internal_status, kaspi_status, updated_at, imported_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        [
            ("2001", "ACMEWEAR", "2026-01-10 09:00:00", "2026-01-11", "2026-01-11 18:00:00", "2026-01-11 18:00:00", "COMPLETED", "ARCHIVE", "2026-01-11 19:00:00", "2026-01-11 19:00:00"),
            ("2002", "ACMEWEAR", "2026-01-12 09:00:00", "2026-01-13", "2026-01-13 18:00:00", "2026-01-13 18:00:00", "COMPLETED", "ARCHIVE", "2026-01-13 19:00:00", "2026-01-13 19:00:00"),
        ],
    )
    conn.execute(
        """
        INSERT INTO fact_order_entries_kaspi (entry_id, order_id, store_code, offer_id, quantity, total_price_kzt)
        VALUES ('entry-1', '2001', 'ACMEWEAR', 'SKU-1', 1, 1000)
        """
    )
    conn.execute(
        """
        INSERT INTO fact_sales (order_id, order_date, store_code, sku_id, sku_key, quantity, line_net_rev)
        VALUES ('2001', '2026-01-11', 'ACMEWEAR', 'SKU-1', 'SKU-1', 1, 900)
        """
    )
    conn.commit()
    conn.close()


def test_classify_webui_db_absence_splits_backfill_and_quarantine_candidates(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "app.db"
    _seed_db(db_path)

    missing_csv = tmp_path / "db_missing_order_candidates.csv"
    pd.DataFrame(
        [
            {
                "order_id": "2001",
                "store_code": "ACMEWEAR",
                "webui_sale_date": "2026-01-11",
                "created_at": "2026-01-10",
                "planned_courier_at": "2026-01-11",
                "delivered_at": "2026-01-14",
                "status_set": "DELIVERED",
                "root_bucket": "DB_MISSING_IN_DB_ABSENT",
            },
            {
                "order_id": "2002",
                "store_code": "ACMEWEAR",
                "webui_sale_date": "2026-01-13",
                "created_at": "2026-01-12",
                "planned_courier_at": "2026-01-13",
                "delivered_at": "2026-01-15",
                "status_set": "DELIVERED",
                "root_bucket": "DB_MISSING_IN_DB_ABSENT",
            },
        ]
    ).to_csv(missing_csv, index=False, encoding="utf-8")

    db_only_csv = tmp_path / "db_only_order_explanations.csv"
    pd.DataFrame(
        [
            {
                "order_id": "3001",
                "store_code": "",
                "db_sale_date_min": "2026-02-23",
                "db_sale_date_max": "2026-02-23",
                "returned_at": "",
                "status_set": "",
                "root_bucket": "DB_ONLY_NO_WEBUI_LINEAGE",
                "resolution_detail": "db-only order id is absent from the frozen webui pack",
            }
        ]
    ).to_csv(db_only_csv, index=False, encoding="utf-8")

    report = classify_webui_db_absence(
        db_path=db_path,
        missing_orders_csv=missing_csv,
        db_only_orders_csv=db_only_csv,
        output_dir=tmp_path / "out",
        strict=True,
    )

    assert report["status"] == "PASS"

    backfill = pd.read_csv(tmp_path / "out" / "db_backfill_candidates.csv", dtype=object)
    quarantine = pd.read_csv(tmp_path / "out" / "db_quarantine_candidates.csv", dtype=object)
    root_causes = pd.read_csv(tmp_path / "out" / "db_absence_root_causes.csv", dtype=object)

    assert set(backfill["order_id"]) == {"2001"}
    assert set(quarantine["order_id"]) == {"2002", "3001"}
    assert set(root_causes["root_bucket"]) >= {
        "DB_BACKFILL_FROM_FACT_ORDER_ENTRIES",
        "DB_QUARANTINE_NO_FACT_ORDER_ENTRIES",
        "DB_ONLY_NO_WEBUI_LINEAGE",
    }
