from __future__ import annotations

from datetime import date
from pathlib import Path
import sqlite3

from scripts.validate_recent_identity_coverage import validate_recent_identity_coverage


def _init_db(path: Path) -> None:
    conn = sqlite3.connect(path)
    try:
        conn.execute(
            """
            CREATE TABLE fact_orders_kaspi (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                order_id TEXT,
                store_code TEXT,
                sku_key TEXT,
                sku_id TEXT,
                my_size TEXT,
                kaspi_offer_name TEXT,
                kaspi_status_detail TEXT,
                internal_status TEXT,
                kaspi_status TEXT,
                created_at TEXT
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE fact_order_status_observations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                order_id TEXT,
                store_code TEXT,
                status_internal TEXT,
                observed_at TEXT,
                source TEXT
            )
            """
        )
        conn.commit()
    finally:
        conn.close()


def test_recent_identity_uses_latest_pending_observation(tmp_path: Path) -> None:
    db = tmp_path / "app.db"
    _init_db(db)
    conn = sqlite3.connect(db)
    try:
        conn.executemany(
            """
            INSERT INTO fact_orders_kaspi(
                order_id, store_code, sku_key, sku_id, my_size, kaspi_offer_name,
                kaspi_status_detail, internal_status, kaspi_status, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    "1",
                    "UNIVERSAL",
                    "",
                    "",
                    "",
                    "",
                    "COMPLETED",
                    "COMPLETED",
                    "ARCHIVE",
                    "2026-03-09 09:00:00",
                ),
                (
                    "2",
                    "UNIVERSAL",
                    "SKU2",
                    "SKU2",
                    "L",
                    "Offer 2",
                    "COMPLETED",
                    "COMPLETED",
                    "ARCHIVE",
                    "2026-03-09 08:00:00",
                ),
            ],
        )
        conn.execute(
            """
            INSERT INTO fact_order_status_observations(
                order_id, store_code, status_internal, observed_at, source
            )
            VALUES (?, ?, ?, ?, ?)
            """,
            ("1", "UNIVERSAL", "READY", "2026-03-09 10:00:00", "API"),
        )
        conn.commit()
    finally:
        conn.close()

    report = validate_recent_identity_coverage(
        db_path=db,
        as_of=date(2026, 3, 9),
        lookback_days=15,
        stores=("UNIVERSAL",),
        output_root=tmp_path / "out",
        strict=True,
        max_missing_all=0,
        max_missing_any_pct=0.5,
        max_missing_any_per_day=1.0,
    )

    assert report["status"] == "PASS"
    assert report["per_store"][0]["total_orders"] == 1
    assert report["per_store"][0]["missing_all_identity_core"] == 0


def test_recent_identity_skips_rows_after_store_observation_watermark(tmp_path: Path) -> None:
    db = tmp_path / "app.db"
    _init_db(db)
    conn = sqlite3.connect(db)
    try:
        conn.executemany(
            """
            INSERT INTO fact_orders_kaspi(
                order_id, store_code, sku_key, sku_id, my_size, kaspi_offer_name,
                kaspi_status_detail, internal_status, kaspi_status, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    "1",
                    "UNIVERSAL",
                    "SKU1",
                    "SKU1",
                    "L",
                    "Offer 1",
                    "COMPLETED",
                    "COMPLETED",
                    "ARCHIVE",
                    "2026-03-09 08:00:00",
                ),
                (
                    "2",
                    "UNIVERSAL",
                    "",
                    "",
                    "",
                    "",
                    "COMPLETED",
                    "COMPLETED",
                    "ARCHIVE",
                    "2026-03-09 14:00:00",
                ),
            ],
        )
        conn.execute(
            """
            INSERT INTO fact_order_status_observations(
                order_id, store_code, status_internal, observed_at, source
            )
            VALUES (?, ?, ?, ?, ?)
            """,
            ("anchor", "UNIVERSAL", "READY", "2026-03-09 13:30:00", "API"),
        )
        conn.commit()
    finally:
        conn.close()

    report = validate_recent_identity_coverage(
        db_path=db,
        as_of=date(2026, 3, 9),
        lookback_days=15,
        stores=("UNIVERSAL",),
        output_root=tmp_path / "out",
        strict=True,
        max_missing_all=0,
        max_missing_any_pct=0.5,
        max_missing_any_per_day=1.0,
    )

    assert report["status"] == "PASS"
    assert report["per_store"][0]["total_orders"] == 1
    assert report["per_store"][0]["missing_all_identity_core"] == 0
