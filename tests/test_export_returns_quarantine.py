from __future__ import annotations

import sqlite3
from pathlib import Path

from scripts.export_returns_quarantine import build_return_cancel_exports


def _init_db(path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(path)
    conn.execute(
        """
        CREATE TABLE fact_orders_kaspi (
            id INTEGER PRIMARY KEY,
            order_id TEXT,
            store_code TEXT,
            kaspi_offer_name TEXT,
            sku_key TEXT,
            sku_id TEXT,
            my_size TEXT,
            assigned_size TEXT,
            quantity INTEGER,
            unit_price_kzt REAL,
            created_at TEXT,
            actual_shipment_date TEXT,
            kaspi_status TEXT,
            kaspi_status_detail TEXT,
            internal_status TEXT,
            status_updated_at TEXT,
            waybill_number TEXT,
            source TEXT,
            source_file TEXT,
            courier_transmission_date TEXT,
            delivery_mode TEXT,
            delivery_cost REAL,
            delivery_cost_for_seller REAL,
            returned_to_warehouse INTEGER
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE fact_order_entries_kaspi (
            entry_id TEXT PRIMARY KEY,
            order_id TEXT,
            store_code TEXT,
            product_id TEXT,
            offer_id TEXT,
            quantity REAL,
            unit_price_kzt REAL,
            total_price_kzt REAL,
            delivery_cost_kzt REAL,
            category_title TEXT,
            entry_number INTEGER
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE dim_kaspi_article_map (
            store_code TEXT,
            kaspi_article TEXT,
            sku_key TEXT,
            sku_id TEXT,
            kaspi_offer_name TEXT,
            kaspi_name_core TEXT,
            active_flag INTEGER
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE dim_sku_size (
            sku_id TEXT PRIMARY KEY,
            sku_key TEXT,
            my_size TEXT,
            active_flag INTEGER
        )
        """
    )
    conn.execute(
        """
        INSERT INTO dim_kaspi_article_map
        VALUES ('UNIVERSAL', 'ART-1', 'SKU_RETURNED', 'SKU_RETURNED_M', 'Returned offer', 'Returned core', 1)
        """
    )
    conn.execute(
        """
        INSERT INTO dim_sku_size
        VALUES ('SKU_RETURNED_M', 'SKU_RETURNED', 'M', 1)
        """
    )
    return conn


def _insert_order(
    conn: sqlite3.Connection,
    *,
    order_id: str,
    state: str,
    status: str,
    internal_status: str,
    returned_to_warehouse: int = 0,
    courier_transmission_date: str | None = None,
    actual_shipment_date: str | None = None,
    sku_key: str = "",
    sku_id: str = "",
    my_size: str = "",
) -> None:
    conn.execute(
        """
        INSERT INTO fact_orders_kaspi (
            order_id, store_code, kaspi_offer_name, sku_key, sku_id, my_size,
            assigned_size, quantity, unit_price_kzt, created_at, actual_shipment_date,
            kaspi_status, kaspi_status_detail, internal_status, status_updated_at,
            waybill_number, source, source_file, courier_transmission_date,
            delivery_mode, delivery_cost, delivery_cost_for_seller, returned_to_warehouse
        )
        VALUES (?, 'UNIVERSAL', 'Header offer', ?, ?, ?, ?, 1, 10000, '2026-03-01',
                ?, ?, ?, ?, '2026-03-02', 'WB1', 'TEST', 'fixture.csv', ?,
                'DELIVERY', 0, 500, ?)
        """,
        (
            order_id,
            sku_key,
            sku_id,
            my_size,
            my_size,
            actual_shipment_date,
            state,
            status,
            internal_status,
            courier_transmission_date,
            returned_to_warehouse,
        ),
    )


def _insert_entry(conn: sqlite3.Connection, order_id: str, entry_id: str = "entry-1") -> None:
    conn.execute(
        """
        INSERT INTO fact_order_entries_kaspi (
            entry_id, order_id, store_code, product_id, offer_id, quantity,
            unit_price_kzt, total_price_kzt, delivery_cost_kzt, category_title, entry_number
        )
        VALUES (?, ?, 'UNIVERSAL', 'PROD-1', 'ART-1', 1, 10000, 10000, 500, 'cat', 1)
        """,
        (entry_id, order_id),
    )


def test_returned_order_goes_to_quarantine_and_pending_qc(tmp_path: Path) -> None:
    conn = _init_db(tmp_path / "app.db")
    _insert_order(
        conn,
        order_id="1001",
        state="ARCHIVE",
        status="RETURNED",
        internal_status="RETURNED",
        returned_to_warehouse=1,
        courier_transmission_date="2026-03-02",
    )
    _insert_entry(conn, "1001")
    conn.commit()
    conn.close()

    result = build_return_cancel_exports(db_path=tmp_path / "app.db", since="2026-02-01", as_of="2026-04-23")

    assert len(result.backlog_rows) == 1
    row = result.backlog_rows[0]
    assert row["stage_code"] == "RETURNED"
    assert row["active_stock_effect"] == "0"
    assert row["quarantine_effect"] == "+1"
    assert row["sku_key"] == "SKU_RETURNED"
    assert row["mapped_size"] == "M"
    assert len(result.qc_rows) == 1
    assert result.qc_rows[0]["qc_status"] == "PENDING_QC"


def test_cancelled_before_stock_moved_has_no_quarantine_queue(tmp_path: Path) -> None:
    conn = _init_db(tmp_path / "app.db")
    _insert_order(
        conn,
        order_id="1002",
        state="ARCHIVE",
        status="CANCELLED",
        internal_status="CANCELLED",
        sku_key="SKU_CANCEL",
        sku_id="SKU_CANCEL_L",
        my_size="L",
    )
    conn.commit()
    conn.close()

    result = build_return_cancel_exports(db_path=tmp_path / "app.db", since="2026-02-01", as_of="2026-04-23")

    assert result.backlog_rows[0]["event_type"] == "CANCELLED_BEFORE_STOCK_MOVED"
    assert result.backlog_rows[0]["quarantine_effect"] == "0"
    assert result.qc_rows == []


def test_cancelling_order_is_expected_return_pending_qc(tmp_path: Path) -> None:
    conn = _init_db(tmp_path / "app.db")
    _insert_order(
        conn,
        order_id="1003",
        state="KASPI_DELIVERY",
        status="CANCELLING",
        internal_status="CANCELLED",
        sku_key="SKU_PENDING",
        sku_id="SKU_PENDING_XL",
        my_size="XL",
        courier_transmission_date="2026-03-03",
    )
    conn.commit()
    conn.close()

    result = build_return_cancel_exports(db_path=tmp_path / "app.db", since="2026-02-01", as_of="2026-04-23")

    assert result.backlog_rows[0]["stage_code"] == "CANCELLING"
    assert result.backlog_rows[0]["event_type"] == "EXPECTED_RETURN"
    assert result.backlog_rows[0]["quarantine_effect"] == "+1"
    assert result.qc_rows[0]["physical_bucket"] == "EXPECTED_RETURN"
    assert result.qc_rows[0]["qc_status"] == "PENDING_QC"


def test_missing_line_identity_is_exception_and_never_restocked(tmp_path: Path) -> None:
    conn = _init_db(tmp_path / "app.db")
    _insert_order(
        conn,
        order_id="1004",
        state="ARCHIVE",
        status="RETURNED",
        internal_status="RETURNED",
        returned_to_warehouse=1,
    )
    conn.commit()
    conn.close()

    result = build_return_cancel_exports(db_path=tmp_path / "app.db", since="2026-02-01", as_of="2026-04-23")

    row = result.backlog_rows[0]
    assert row["active_stock_effect"] == "0"
    assert row["quarantine_effect"] == "0"
    assert "MISSING_SKU_KEY" in row["exception_reason"]
    assert "MISSING_SIZE" in row["exception_reason"]
    assert len(result.exception_rows) == 1
    assert result.qc_rows[0]["qc_status"] == "PENDING_QC"
