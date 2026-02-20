from __future__ import annotations

import csv
import sqlite3
from datetime import date
from pathlib import Path

from scripts.export_sizing_queue import export_sizing_queue
from scripts.import_sizing_queue import import_sizing_queue


def _make_db(db_path: Path) -> None:
    conn = sqlite3.connect(str(db_path))
    conn.execute(
        """
        CREATE TABLE fact_orders_kaspi (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            order_id TEXT NOT NULL,
            store_code TEXT NOT NULL,
            kaspi_offer_name TEXT,
            sku_id TEXT,
            my_size TEXT,
            assigned_size TEXT,
            planned_shipment_date TEXT,
            customer_height_cm INTEGER,
            customer_weight_kg INTEGER
        )
        """
    )
    conn.commit()
    conn.close()


def test_export_sizing_queue_filters(tmp_path: Path) -> None:
    db_path = tmp_path / "app.db"
    _make_db(db_path)

    conn = sqlite3.connect(str(db_path))
    conn.execute(
        """
        INSERT INTO fact_orders_kaspi (
            order_id, store_code, kaspi_offer_name, sku_id, my_size, assigned_size, planned_shipment_date
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        ("1001", "UNIVERSAL", "Test Offer", "CL_TEST_XL", None, None, "2026-01-04"),
    )
    conn.execute(
        """
        INSERT INTO fact_orders_kaspi (
            order_id, store_code, kaspi_offer_name, sku_id, my_size, assigned_size, planned_shipment_date
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        ("1002", "UNIVERSAL", "Sized", "CL_TEST_L", None, "L", "2026-01-04"),
    )
    conn.execute(
        """
        INSERT INTO fact_orders_kaspi (
            order_id, store_code, kaspi_offer_name, sku_id, my_size, assigned_size, planned_shipment_date
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        ("1003", "UNIVERSAL", "Future", "CL_TEST_M", None, None, "2026-01-10"),
    )
    conn.commit()
    conn.close()

    output_path = tmp_path / "queue.csv"
    count = export_sizing_queue(
        db_path,
        output_path,
        as_of_date=date(2026, 1, 4),
        crm_path=None,
        crm_sheet=None,
    )

    assert count == 1
    with open(output_path, newline="") as f:
        rows = list(csv.DictReader(f))
    assert len(rows) == 1
    assert rows[0]["order_id"] == "1001"
    assert rows[0]["offer_size"] == "XL"


def test_import_sizing_queue_updates(tmp_path: Path) -> None:
    db_path = tmp_path / "app.db"
    _make_db(db_path)

    conn = sqlite3.connect(str(db_path))
    conn.execute(
        """
        INSERT INTO fact_orders_kaspi (
            order_id, store_code, kaspi_offer_name, sku_id, my_size, assigned_size, planned_shipment_date
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        ("2001", "ACMEWEAR", "Offer", "CL_TEST_L", None, None, "2026-01-04"),
    )
    conn.commit()
    conn.close()

    input_path = tmp_path / "queue.csv"
    with open(input_path, "w", newline="") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "order_id",
                "my_size",
                "customer_height_cm",
                "customer_weight_kg",
                "decided_by",
                "method",
            ],
        )
        writer.writeheader()
        writer.writerow(
            {
                "order_id": "2001",
                "my_size": "L",
                "customer_height_cm": "180",
                "customer_weight_kg": "78",
                "decided_by": "ops",
                "method": "MANUAL_QUEUE",
            }
        )

    stats = import_sizing_queue(
        db_path,
        input_path,
        decided_by="ops",
        method="MANUAL_QUEUE",
        dry_run=False,
    )

    assert stats["updated_sizes"] == 1

    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    row = conn.execute(
        "SELECT assigned_size, size_source, size_decided_by, size_decision_method, customer_height_cm, customer_weight_kg FROM fact_orders_kaspi WHERE order_id = ?",
        ("2001",),
    ).fetchone()
    conn.close()

    assert row["assigned_size"] == "L"
    assert row["size_source"] == "QUEUE_MANUAL"
    assert row["size_decided_by"] == "ops"
    assert row["size_decision_method"] == "MANUAL_QUEUE"
    assert row["customer_height_cm"] == 180
    assert row["customer_weight_kg"] == 78
