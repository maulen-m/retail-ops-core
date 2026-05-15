import sqlite3
from datetime import date
from pathlib import Path

from core.ops.waybill_overdue_carryforward import get_overdue_waybill_ready_order_ids_from_db


def _init_db(path: Path) -> None:
    conn = sqlite3.connect(path)
    conn.execute(
        """
        CREATE TABLE fact_orders_kaspi (
            order_id TEXT,
            store_code TEXT,
            assigned_size TEXT,
            my_size TEXT,
            planned_shipment_date TEXT,
            kaspi_status TEXT,
            kaspi_status_detail TEXT,
            internal_status TEXT,
            signature_required INTEGER,
            courier_transmission_date TEXT,
            waybill_url TEXT,
            waybill_downloaded INTEGER,
            returned_to_warehouse TEXT
        )
        """
    )
    conn.commit()
    conn.close()


def _insert_rows(path: Path, rows: list[tuple]) -> None:
    conn = sqlite3.connect(path)
    conn.executemany(
        """
        INSERT INTO fact_orders_kaspi (
            order_id, store_code, assigned_size, my_size, planned_shipment_date,
            kaspi_status, kaspi_status_detail, internal_status, signature_required,
            courier_transmission_date, waybill_url, waybill_downloaded, returned_to_warehouse
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        rows,
    )
    conn.commit()
    conn.close()


def test_overdue_carryforward_merges_duplicate_rows_for_size_and_waybill(tmp_path: Path) -> None:
    db_path = tmp_path / "app.db"
    _init_db(db_path)
    _insert_rows(
        db_path,
        [
            (
                "914313118",
                "STOREB",
                "",
                "",
                "2026-05-07",
                "KASPI_DELIVERY",
                "ACCEPTED_BY_MERCHANT",
                "READY",
                0,
                None,
                "https://kaspi.kz/shop/api/waybill/914313118",
                0,
                None,
            ),
            (
                "914313118",
                "STOREB",
                "2XL",
                "",
                "2026-05-07",
                "KASPI_DELIVERY",
                "ACCEPTED_BY_MERCHANT",
                "ACCEPTED",
                0,
                None,
                None,
                0,
                None,
            ),
        ],
    )

    result = get_overdue_waybill_ready_order_ids_from_db(
        db_path,
        target_date=date(2026, 5, 8),
        lookback_days=7,
    )

    assert result == {"STOREB": {"914313118"}}


def test_overdue_carryforward_excludes_duplicate_order_if_any_row_is_handed_over(tmp_path: Path) -> None:
    db_path = tmp_path / "app.db"
    _init_db(db_path)
    _insert_rows(
        db_path,
        [
            (
                "913356798",
                "STOREB",
                "3XL",
                "",
                "2026-05-07",
                "KASPI_DELIVERY",
                "ACCEPTED_BY_MERCHANT",
                "SHIPPED",
                0,
                "2026-05-07 18:56:25",
                "https://kaspi.kz/shop/api/waybill/current",
                0,
                None,
            ),
            (
                "913356798",
                "STOREB",
                "3XL",
                "",
                "2026-05-06",
                "KASPI_DELIVERY",
                "ACCEPTED_BY_MERCHANT",
                "READY",
                0,
                None,
                "https://kaspi.kz/shop/api/waybill/stale",
                0,
                None,
            ),
        ],
    )

    result = get_overdue_waybill_ready_order_ids_from_db(
        db_path,
        target_date=date(2026, 5, 8),
        lookback_days=7,
    )

    assert result == {}
