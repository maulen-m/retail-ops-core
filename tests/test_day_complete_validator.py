from __future__ import annotations

import sqlite3
from datetime import date
from pathlib import Path

from core.validation.day_complete import evaluate_day_complete


def _make_db(path: Path) -> None:
    conn = sqlite3.connect(path)
    conn.execute(
        """
        CREATE TABLE fact_orders_kaspi (
            order_id TEXT,
            sku_id TEXT,
            store_code TEXT,
            planned_shipment_date TEXT,
            internal_status TEXT,
            kaspi_status TEXT,
            assigned_size TEXT,
            my_size TEXT
        )
        """
    )
    conn.commit()
    conn.close()


def _insert(
    conn,
    order_id: str,
    planned: str,
    internal: str,
    assigned: str = "",
    my_size: str = "",
    kaspi_status: str = "KASPI_DELIVERY",
    sku_id: str = "SKU-1",
) -> None:
    conn.execute(
        """
        INSERT INTO fact_orders_kaspi (
            order_id, sku_id, store_code, planned_shipment_date,
            internal_status, kaspi_status, assigned_size, my_size
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (order_id, sku_id, "UNIVERSAL", planned, internal, kaspi_status, assigned, my_size),
    )


def test_day_complete_passes_with_sizes(tmp_path: Path) -> None:
    db_path = tmp_path / "app.db"
    _make_db(db_path)
    conn = sqlite3.connect(db_path)
    _insert(conn, "1001", "2026-01-08", "READY", assigned="L")
    conn.commit()
    conn.close()

    report = evaluate_day_complete(db_path, date(2026, 1, 8))
    assert report.ok
    assert report.details["violations"] == 0


def test_day_complete_flags_missing_size(tmp_path: Path) -> None:
    db_path = tmp_path / "app.db"
    _make_db(db_path)
    conn = sqlite3.connect(db_path)
    _insert(conn, "1002", "2026-01-08", "READY")
    conn.commit()
    conn.close()

    report = evaluate_day_complete(db_path, date(2026, 1, 8))
    assert not report.ok
    assert report.details["violations"] == 1
    assert report.violations[0].order_id == "1002"


def test_day_complete_ignores_future_and_non_ready(tmp_path: Path) -> None:
    db_path = tmp_path / "app.db"
    _make_db(db_path)
    conn = sqlite3.connect(db_path)
    _insert(conn, "1003", "2026-01-10", "READY")
    _insert(conn, "1004", "2026-01-08", "CANCELLED", kaspi_status="CANCELLED")
    conn.commit()
    conn.close()

    report = evaluate_day_complete(db_path, date(2026, 1, 8))
    assert report.ok
    assert report.details["violations"] == 0


def test_day_complete_skips_missing_line_items(tmp_path: Path) -> None:
    db_path = tmp_path / "app.db"
    _make_db(db_path)
    conn = sqlite3.connect(db_path)
    _insert(conn, "1005", "2026-01-08", "READY", sku_id="")
    conn.commit()
    conn.close()

    report = evaluate_day_complete(db_path, date(2026, 1, 8))
    assert report.ok
    assert report.details["violations"] == 0
