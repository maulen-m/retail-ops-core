from __future__ import annotations

from datetime import date
from pathlib import Path
import sqlite3

import pytest

from scripts.identity_stabilization_common import StatusError
from scripts.validate_order_entries_freshness import validate_order_entries_freshness


def _init_db(path: Path) -> None:
    conn = sqlite3.connect(path)
    try:
        conn.execute(
            """
            CREATE TABLE fact_orders_kaspi (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                order_id TEXT,
                store_code TEXT,
                kaspi_status_detail TEXT,
                internal_status TEXT,
                kaspi_status TEXT,
                created_at TEXT
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE fact_order_entries_kaspi (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                order_id TEXT,
                store_code TEXT,
                updated_at TEXT
            )
            """
        )
        conn.commit()
    finally:
        conn.close()


def test_validate_order_entries_freshness_pass(tmp_path: Path) -> None:
    db = tmp_path / "app.db"
    _init_db(db)
    conn = sqlite3.connect(db)
    try:
        conn.executemany(
            "INSERT INTO fact_orders_kaspi(order_id, store_code, created_at) VALUES (?, ?, ?)",
            [
                ("1", "UNIVERSAL", "2026-03-04 10:00:00"),
                ("2", "UNIVERSAL", "2026-03-04 11:00:00"),
            ],
        )
        conn.executemany(
            "INSERT INTO fact_order_entries_kaspi(order_id, store_code, updated_at) VALUES (?, ?, ?)",
            [
                ("1", "UNIVERSAL", "2026-03-04 10:01:00"),
                ("2", "UNIVERSAL", "2026-03-04 11:01:00"),
            ],
        )
        conn.commit()
    finally:
        conn.close()

    report = validate_order_entries_freshness(
        db_path=db,
        as_of=date(2026, 3, 4),
        lookback_days=7,
        stores=("UNIVERSAL",),
        min_entries_coverage_pct=95.0,
        output_root=tmp_path / "out",
        strict=True,
    )
    assert report["status"] == "PASS"


def test_validate_order_entries_freshness_fails_when_coverage_is_low(tmp_path: Path) -> None:
    db = tmp_path / "app.db"
    _init_db(db)
    conn = sqlite3.connect(db)
    try:
        conn.executemany(
            "INSERT INTO fact_orders_kaspi(order_id, store_code, created_at) VALUES (?, ?, ?)",
            [
                ("1", "UNIVERSAL", "2026-03-04 10:00:00"),
                ("2", "UNIVERSAL", "2026-03-04 11:00:00"),
            ],
        )
        conn.execute(
            "INSERT INTO fact_order_entries_kaspi(order_id, store_code, updated_at) VALUES (?, ?, ?)",
            ("1", "UNIVERSAL", "2026-03-04 10:01:00"),
        )
        conn.commit()
    finally:
        conn.close()

    with pytest.raises(StatusError, match="IDENTITY_COVERAGE_FAIL"):
        validate_order_entries_freshness(
            db_path=db,
            as_of=date(2026, 3, 4),
            lookback_days=7,
            stores=("UNIVERSAL",),
            min_entries_coverage_pct=95.0,
            output_root=tmp_path / "out",
            strict=True,
        )


def test_validate_order_entries_freshness_excludes_pending_rows(tmp_path: Path) -> None:
    db = tmp_path / "app.db"
    _init_db(db)
    conn = sqlite3.connect(db)
    try:
        conn.executemany(
            """
            INSERT INTO fact_orders_kaspi(order_id, store_code, kaspi_status_detail, internal_status, kaspi_status, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            [
                ("1", "UNIVERSAL", "ACCEPTED_BY_MERCHANT", "ACCEPTED", "NEW", "2026-03-03 10:00:00"),
                ("2", "UNIVERSAL", "DELIVERY", "SHIPPED", "KASPI_DELIVERY", "2026-03-04 11:00:00"),
            ],
        )
        conn.execute(
            "INSERT INTO fact_order_entries_kaspi(order_id, store_code, updated_at) VALUES (?, ?, ?)",
            ("2", "UNIVERSAL", "2026-03-04 11:01:00"),
        )
        conn.commit()
    finally:
        conn.close()

    report = validate_order_entries_freshness(
        db_path=db,
        as_of=date(2026, 3, 4),
        lookback_days=7,
        stores=("UNIVERSAL",),
        min_entries_coverage_pct=95.0,
        output_root=tmp_path / "out",
        strict=True,
    )
    assert report["status"] == "PASS"
    assert report["per_store"][0]["orders_total"] == 1
