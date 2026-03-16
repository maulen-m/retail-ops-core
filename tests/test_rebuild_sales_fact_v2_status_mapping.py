from __future__ import annotations

from datetime import date
from pathlib import Path
import sqlite3

from scripts.rebuild_sales_fact_v2_from_kaspi_entries import build_sales_fact_v2_rows_from_entries


def _seed_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE sales_fact_v2 (
            sale_id INTEGER PRIMARY KEY AUTOINCREMENT,
            order_id TEXT,
            order_date TEXT,
            sku_key TEXT,
            sku_id TEXT,
            my_size TEXT,
            kaspi_offer_name TEXT,
            store_code TEXT,
            quantity REAL,
            sell_price_kzt REAL,
            delivery_fee REAL,
            cogs REAL,
            net_rev REAL,
            profit REAL,
            status TEXT,
            return_flag INTEGER,
            return_date TEXT,
            source_file TEXT,
            api_updated_at TEXT,
            UNIQUE(order_id, sku_id, store_code, kaspi_offer_name)
        );
        CREATE TABLE fact_orders_kaspi (
            order_id TEXT,
            store_code TEXT,
            kaspi_offer_name TEXT,
            sku_key TEXT,
            sku_id TEXT,
            assigned_size TEXT,
            my_size TEXT,
            quantity INTEGER,
            internal_status TEXT,
            kaspi_status TEXT,
            status_updated_at TEXT,
            actual_shipment_date TEXT,
            planned_shipment_date TEXT,
            created_at TEXT,
            delivery_cost REAL,
            delivery_cost_for_seller REAL
        );
        CREATE TABLE fact_order_entries_kaspi (
            entry_id TEXT,
            order_id TEXT,
            store_code TEXT,
            offer_id TEXT,
            quantity REAL,
            total_price_kzt REAL
        );
        CREATE TABLE dim_kaspi_article_map (
            store_code TEXT,
            kaspi_article TEXT,
            kaspi_offer_name TEXT,
            sku_key TEXT,
            sku_id TEXT,
            active_flag INTEGER
        );
        """
    )


def test_shipped_internal_status_is_open_and_not_counted_as_delivered(tmp_path: Path) -> None:
    db = tmp_path / "app.db"
    conn = sqlite3.connect(db)
    _seed_schema(conn)

    conn.execute(
        """
        INSERT INTO fact_orders_kaspi (
            order_id, store_code, kaspi_offer_name, sku_key, sku_id, assigned_size, my_size,
            quantity, internal_status, kaspi_status, status_updated_at,
            actual_shipment_date, planned_shipment_date, created_at, delivery_cost_for_seller
        ) VALUES (
            'ORD-SHIPPED', 'ACMEWEAR', 'OFFER-X', '', '', '', '',
            1, 'SHIPPED', 'Передан', '2026-02-25T10:00:00',
            '2026-02-25', '2026-02-25', '2026-02-24', 50
        )
        """
    )
    conn.execute(
        """
        INSERT INTO fact_order_entries_kaspi (entry_id, order_id, store_code, offer_id, quantity, total_price_kzt)
        VALUES ('E-SH', 'ORD-SHIPPED', 'ACMEWEAR', 'OFFER-X', 1, 1000)
        """
    )
    conn.commit()

    rows, summary = build_sales_fact_v2_rows_from_entries(
        conn,
        as_of=date(2026, 2, 26),
        strict=True,
    )
    conn.close()

    assert rows == []
    assert summary["skipped_open"] == 1


def test_unknown_terminal_row_can_finalize_store_specific_archive_snapshot(tmp_path: Path) -> None:
    db = tmp_path / "app.db"
    conn = sqlite3.connect(db)
    _seed_schema(conn)

    conn.execute(
        """
        INSERT INTO fact_orders_kaspi (
            order_id, store_code, kaspi_offer_name, sku_key, sku_id, assigned_size, my_size,
            quantity, internal_status, kaspi_status, status_updated_at,
            actual_shipment_date, planned_shipment_date, created_at, delivery_cost_for_seller
        ) VALUES (
            'ORD-FALLBACK', 'ACMEWEAR', 'OFFER-Z', 'SKU_Z', 'SKU_Z_3XL', '3XL', '3XL',
            1, 'NEW', 'ARCHIVE', '2026-01-27T18:57:37',
            '2026-01-07T19:14:23', '2026-01-07', '2026-01-07T10:03:56', 927
        )
        """
    )
    conn.execute(
        """
        INSERT INTO fact_orders_kaspi (
            order_id, store_code, kaspi_offer_name, sku_key, sku_id, assigned_size, my_size,
            quantity, internal_status, kaspi_status, status_updated_at,
            actual_shipment_date, planned_shipment_date, created_at, delivery_cost_for_seller
        ) VALUES (
            'ORD-FALLBACK', 'UNKNOWN', 'OFFER-Z', 'SKU_Z', 'SKU_Z_3XL', '3XL', '3XL',
            1, 'COMPLETED', 'Завершен', '',
            '', '2026-01-07', '', 0
        )
        """
    )
    conn.execute(
        """
        INSERT INTO fact_order_entries_kaspi (entry_id, order_id, store_code, offer_id, quantity, total_price_kzt)
        VALUES ('E-FALLBACK', 'ORD-FALLBACK', 'ACMEWEAR', 'OFFER-Z', 1, 10000)
        """
    )
    conn.commit()

    rows, summary = build_sales_fact_v2_rows_from_entries(
        conn,
        as_of=date(2026, 1, 31),
        strict=True,
    )
    conn.close()

    assert summary["skipped_open"] == 0
    assert len(rows) == 1
    assert rows[0]["order_id"] == "ORD-FALLBACK"
    assert rows[0]["store_code"] == "ACMEWEAR"
    assert rows[0]["status"] == "DELIVERED"
    assert rows[0]["order_date"] == "2026-01-07"


def test_offer_id_can_resolve_from_dim_kaspi_article_map_kaspi_article(tmp_path: Path) -> None:
    db = tmp_path / "app.db"
    conn = sqlite3.connect(db)
    _seed_schema(conn)

    conn.execute(
        """
        INSERT INTO fact_orders_kaspi (
            order_id, store_code, kaspi_offer_name, sku_key, sku_id, assigned_size, my_size,
            quantity, internal_status, kaspi_status, status_updated_at,
            actual_shipment_date, planned_shipment_date, created_at, delivery_cost_for_seller
        ) VALUES (
            'ORD-ARTICLE-MAP', 'UNIVERSAL', '', '', '', '', '',
            1, 'COMPLETED', 'Выдан', '2026-03-07T12:00:00',
            '2026-03-07', '2026-03-07', '2026-03-06', 0
        )
        """
    )
    conn.execute(
        """
        INSERT INTO fact_order_entries_kaspi (entry_id, order_id, store_code, offer_id, quantity, total_price_kzt)
        VALUES (
            'ENTRY-ARTICLE-MAP',
            'ORD-ARTICLE-MAP',
            'UNIVERSAL',
            'CL_OC_MEN_LINE52_BLACK_103217238_48/XL_(XL)',
            1,
            10000
        )
        """
    )
    conn.execute(
        """
        INSERT INTO dim_kaspi_article_map (store_code, kaspi_article, kaspi_offer_name, sku_key, sku_id, active_flag)
        VALUES (
            'UNIVERSAL',
            'CL_OC_MEN_LINE52_BLACK_103217238_48/XL_(XL)',
            NULL,
            'CL_OC_MEN_LINE52_BLACK',
            'CL_OC_MEN_LINE52_BLACK_XL',
            1
        )
        """
    )
    conn.commit()

    rows, summary = build_sales_fact_v2_rows_from_entries(
        conn,
        as_of=date(2026, 3, 7),
        strict=True,
    )
    conn.close()

    assert summary["errors_count"] == 0
    assert len(rows) == 1
    assert rows[0]["sku_key"] == "CL_OC_MEN_LINE52_BLACK"
    assert rows[0]["sku_id"] == "CL_OC_MEN_LINE52_BLACK_XL"


def test_generic_header_sku_prefers_specific_offer_parse(tmp_path: Path) -> None:
    db = tmp_path / "app.db"
    conn = sqlite3.connect(db)
    _seed_schema(conn)

    conn.execute(
        """
        INSERT INTO fact_orders_kaspi (
            order_id, store_code, kaspi_offer_name, sku_key, sku_id, assigned_size, my_size,
            quantity, internal_status, kaspi_status, status_updated_at,
            actual_shipment_date, planned_shipment_date, created_at, delivery_cost_for_seller
        ) VALUES (
            'ORD-GENERIC-HEADER',
            'STOREB',
            'IMPERIAL black XL',
            'CL',
            'CL_XL',
            'XL',
            'XL',
            1,
            'COMPLETED',
            'ARCHIVE',
            '2026-03-03T06:02:00',
            '2026-02-28 18:41:54',
            '2026-02-28',
            '2026-02-27 15:43:14',
            0
        )
        """
    )
    conn.execute(
        """
        INSERT INTO fact_order_entries_kaspi (entry_id, order_id, store_code, offer_id, quantity, total_price_kzt)
        VALUES (
            'ENTRY-GENERIC-HEADER',
            'ORD-GENERIC-HEADER',
            'STOREB',
            'CL_OC_MEN_LINE52_BLACK_XL_112127011',
            1,
            9990
        )
        """
    )
    conn.commit()

    rows, summary = build_sales_fact_v2_rows_from_entries(
        conn,
        as_of=date(2026, 3, 7),
        strict=True,
    )
    conn.close()

    assert summary["errors_count"] == 0
    assert len(rows) == 1
    assert rows[0]["sku_key"] == "CL_OC_MEN_LINE52_BLACK"
    assert rows[0]["sku_id"] == "CL_OC_MEN_LINE52_BLACK_XL"
    assert rows[0]["my_size"] == "XL"
