from __future__ import annotations

from datetime import date
from pathlib import Path
import sqlite3

import pytest

from scripts.identity_stabilization_common import StatusError
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
                created_at TEXT
            )
            """
        )
        conn.commit()
    finally:
        conn.close()


def test_validate_recent_identity_coverage_pass(tmp_path: Path) -> None:
    db = tmp_path / "app.db"
    _init_db(db)
    conn = sqlite3.connect(db)
    try:
        conn.executemany(
            """
            INSERT INTO fact_orders_kaspi
            (order_id, store_code, sku_key, sku_id, my_size, kaspi_offer_name, kaspi_status_detail, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                ("1", "UNIVERSAL", "SKU1", "SKU1", "L", "Offer 1", "COMPLETED", "2026-03-04 10:00:00"),
                ("2", "STOREB", "SKU2", "SKU2", "XL", "Offer 2", "COMPLETED", "2026-03-04 11:00:00"),
            ],
        )
        conn.commit()
    finally:
        conn.close()

    report = validate_recent_identity_coverage(
        db_path=db,
        as_of=date(2026, 3, 4),
        lookback_days=15,
        stores=("UNIVERSAL", "STOREB"),
        output_root=tmp_path / "out",
        strict=True,
        max_missing_all=0,
        max_missing_any_pct=0.5,
        max_missing_any_per_day=1.0,
    )
    assert report["status"] == "PASS"


def test_validate_recent_identity_coverage_fails_when_missing_all_identity(tmp_path: Path) -> None:
    db = tmp_path / "app.db"
    _init_db(db)
    conn = sqlite3.connect(db)
    try:
        conn.executemany(
            """
            INSERT INTO fact_orders_kaspi
            (order_id, store_code, sku_key, sku_id, my_size, kaspi_offer_name, kaspi_status_detail, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                ("1", "UNIVERSAL", "", "", "", "", "COMPLETED", "2026-03-04 10:00:00"),
                ("2", "UNIVERSAL", "SKU2", "SKU2", "XL", "Offer 2", "COMPLETED", "2026-03-04 11:00:00"),
            ],
        )
        conn.commit()
    finally:
        conn.close()

    with pytest.raises(StatusError, match="IDENTITY_COVERAGE_FAIL"):
        validate_recent_identity_coverage(
            db_path=db,
            as_of=date(2026, 3, 4),
            lookback_days=15,
            stores=("UNIVERSAL",),
            output_root=tmp_path / "out",
            strict=True,
            max_missing_all=0,
            max_missing_any_pct=0.5,
            max_missing_any_per_day=1.0,
        )


def test_validate_recent_identity_coverage_excludes_cancelled_rows(tmp_path: Path) -> None:
    db = tmp_path / "app.db"
    _init_db(db)
    conn = sqlite3.connect(db)
    try:
        conn.executemany(
            """
            INSERT INTO fact_orders_kaspi
            (order_id, store_code, sku_key, sku_id, my_size, kaspi_offer_name, kaspi_status_detail, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                ("1", "UNIVERSAL", "", "", "", "", "CANCELLED", "2026-03-04 10:00:00"),
                ("2", "UNIVERSAL", "SKU2", "SKU2", "XL", "Offer 2", "COMPLETED", "2026-03-04 11:00:00"),
            ],
        )
        conn.commit()
    finally:
        conn.close()

    report = validate_recent_identity_coverage(
        db_path=db,
        as_of=date(2026, 3, 4),
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


def test_validate_recent_identity_coverage_excludes_fresh_pending_rows(tmp_path: Path) -> None:
    db = tmp_path / "app.db"
    _init_db(db)
    conn = sqlite3.connect(db)
    try:
        conn.executemany(
            """
            INSERT INTO fact_orders_kaspi
            (order_id, store_code, sku_key, sku_id, my_size, kaspi_offer_name, kaspi_status_detail, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                ("1", "UNIVERSAL", "", "", "", "", "ACCEPTED_BY_MERCHANT", "2026-03-04 10:00:00"),
                ("2", "UNIVERSAL", "SKU2", "SKU2", "XL", "Offer 2", "COMPLETED", "2026-03-04 11:00:00"),
            ],
        )
        conn.commit()
    finally:
        conn.close()

    report = validate_recent_identity_coverage(
        db_path=db,
        as_of=date(2026, 3, 4),
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
