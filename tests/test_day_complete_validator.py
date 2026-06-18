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
            my_size TEXT,
            kaspi_offer_name TEXT
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
    offer_name: str = "",
) -> None:
    conn.execute(
        """
        INSERT INTO fact_orders_kaspi (
            order_id, sku_id, store_code, planned_shipment_date,
            internal_status, kaspi_status, assigned_size, my_size, kaspi_offer_name
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (order_id, sku_id, "UNIVERSAL", planned, internal, kaspi_status, assigned, my_size, offer_name),
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


def test_day_complete_excludes_cancelled_returned_archive(tmp_path: Path) -> None:
    db_path = tmp_path / "app.db"
    _make_db(db_path)
    conn = sqlite3.connect(db_path)
    _insert(conn, "1006", "2026-01-08", "CANCELLED", kaspi_status="ARCHIVE")
    _insert(conn, "1007", "2026-01-08", "RETURNED", kaspi_status="ARCHIVE")
    conn.commit()
    conn.close()

    report = evaluate_day_complete(db_path, date(2026, 1, 8))
    assert report.ok
    assert report.details["eligible_orders"] == 0
    assert report.details["skipped_cancelled_returned_archive"] == 2


def test_day_complete_treats_blank_sku_nan_offer_as_missing_line_item(tmp_path: Path) -> None:
    db_path = tmp_path / "app.db"
    _make_db(db_path)
    conn = sqlite3.connect(db_path)
    _insert(conn, "1008", "2026-01-08", "READY", sku_id="", offer_name="nan")
    conn.commit()
    conn.close()

    report = evaluate_day_complete(db_path, date(2026, 1, 8))
    assert report.ok
    assert report.details["eligible_orders"] == 0
    assert report.details["skipped_missing_line_items"] == 1


def test_day_complete_accepts_owner_approved_manual_offer_text(tmp_path: Path) -> None:
    db_path = tmp_path / "app.db"
    _make_db(db_path)
    conn = sqlite3.connect(db_path)
    _insert(
        conn,
        "861147900",
        "2026-03-19",
        "COMPLETED",
        kaspi_status="ARCHIVE",
        sku_id="CL",
        offer_name="Комплект Antec RASH-921 Рашгард 5 в 1 черный 46, 48",
    )
    conn.commit()
    conn.close()

    report = evaluate_day_complete(db_path, date(2026, 3, 19))
    assert report.ok
    assert report.details["eligible_orders"] == 1
    assert report.details["manual_offer_text_classifications"] == 1
    assert report.details["violations"] == 0


def test_day_complete_accepts_size_encoded_in_sku_id(tmp_path: Path) -> None:
    db_path = tmp_path / "app.db"
    _make_db(db_path)
    conn = sqlite3.connect(db_path)
    _insert(
        conn,
        "844362551",
        "2026-03-04",
        "COMPLETED",
        kaspi_status="ARCHIVE",
        sku_id="CL_NEW-CLO2_MEN_SUIT-61_BLACK_3XL",
        offer_name="OF_SUIT-61_BLK_3XL",
    )
    conn.commit()
    conn.close()

    report = evaluate_day_complete(db_path, date(2026, 3, 4))
    assert report.ok
    assert report.details["eligible_orders"] == 1
    assert report.details["violations"] == 0


def test_day_complete_accepts_owner_approved_kids_offer_text(tmp_path: Path) -> None:
    db_path = tmp_path / "app.db"
    _make_db(db_path)
    conn = sqlite3.connect(db_path)
    _insert(
        conn,
        "861137901",
        "2026-03-19",
        "COMPLETED",
        kaspi_status="ARCHIVE",
        sku_id="CL_NEW-CLO_KIDS_KID-31_BLACK",
        offer_name="Рашгард 218596 черный 146-152",
    )
    conn.commit()
    conn.close()

    report = evaluate_day_complete(db_path, date(2026, 3, 19))
    assert report.ok
    assert report.details["eligible_orders"] == 1
    assert report.details["manual_offer_text_classifications"] == 1
    assert report.details["violations"] == 0
