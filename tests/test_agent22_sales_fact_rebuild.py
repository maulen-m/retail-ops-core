from __future__ import annotations

import json
import sqlite3
from datetime import date
from pathlib import Path

import pytest

from scripts.rebuild_sales_fact_v2_from_kaspi_entries import (
    RebuildError,
    build_sales_fact_v2_rows_from_entries,
    run_rebuild,
)


def _create_sales_rebuild_db(path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(path)
    conn.execute(
        """
        CREATE TABLE fact_orders_kaspi (
            order_id TEXT NOT NULL,
            store_code TEXT NOT NULL,
            kaspi_offer_name TEXT,
            sku_key TEXT,
            sku_id TEXT,
            my_size TEXT,
            quantity INTEGER,
            unit_price_kzt REAL,
            delivery_cost REAL,
            delivery_cost_for_seller REAL,
            status_updated_at TEXT,
            actual_shipment_date TEXT,
            planned_shipment_date TEXT,
            created_at TEXT,
            internal_status TEXT,
            kaspi_status TEXT
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE fact_order_entries_kaspi (
            entry_id TEXT PRIMARY KEY,
            order_id TEXT,
            store_code TEXT,
            offer_id TEXT,
            raw_json TEXT,
            quantity REAL,
            total_price_kzt REAL
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE sales_fact_v2 (
            sale_id INTEGER PRIMARY KEY AUTOINCREMENT,
            order_id TEXT NOT NULL,
            order_date DATE NOT NULL,
            sku_key TEXT NOT NULL,
            sku_id TEXT NOT NULL,
            my_size TEXT NOT NULL,
            kaspi_offer_name TEXT NOT NULL,
            store_code TEXT DEFAULT 'UNIVERSAL',
            quantity INTEGER NOT NULL,
            sell_price_kzt REAL,
            delivery_fee REAL,
            cogs REAL,
            net_rev REAL,
            profit REAL,
            status TEXT DEFAULT 'DELIVERED',
            return_flag INTEGER DEFAULT 0,
            return_date DATE,
            ingested_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            source_file TEXT,
            api_updated_at DATETIME,
            UNIQUE(order_id, sku_id, store_code, kaspi_offer_name)
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE dim_kaspi_article_map (
            store_code TEXT,
            kaspi_article TEXT,
            kaspi_offer_name TEXT,
            sku_key TEXT,
            sku_id TEXT,
            active_flag INTEGER
        )
        """
    )
    return conn


def test_rebuild_prefers_entry_lines_and_falls_back_to_completed_headers(tmp_path: Path) -> None:
    db_path = tmp_path / "app.db"
    conn = _create_sales_rebuild_db(db_path)
    conn.execute(
        """
        INSERT INTO dim_kaspi_article_map
            (store_code, kaspi_article, kaspi_offer_name, sku_key, sku_id, active_flag)
        VALUES ('UNIVERSAL', 'ENTRY-OFFER', '', 'SKU_ENTRY', 'SKU_ENTRY_L', 1)
        """
    )
    conn.execute(
        """
        INSERT INTO fact_orders_kaspi (
            order_id, store_code, kaspi_offer_name, sku_key, sku_id, my_size,
            quantity, unit_price_kzt, delivery_cost, status_updated_at, internal_status
        ) VALUES
            ('ENTRY-1', 'UNIVERSAL', 'Header offer', 'SKU_HEADER', 'SKU_HEADER_M', 'M',
             1, 9999, 0, '2026-04-20T12:00:00', 'COMPLETED'),
            ('HEADER-1', 'UNIVERSAL', 'Header fallback', 'SKU_HEADER', 'SKU_HEADER_M', 'M',
             2, 15000, 1000, '2026-04-21T12:00:00', 'COMPLETED')
        """
    )
    conn.execute(
        """
        INSERT INTO fact_order_entries_kaspi
            (entry_id, order_id, store_code, offer_id, quantity, total_price_kzt)
        VALUES ('entry-1', 'ENTRY-1', 'UNIVERSAL', 'ENTRY-OFFER', 3, 36000)
        """
    )

    rows, summary = build_sales_fact_v2_rows_from_entries(
        conn,
        as_of=date(2026, 5, 4),
        start_date=date(2026, 4, 16),
        strict=True,
    )

    by_order = {row["order_id"]: row for row in rows}
    assert by_order["ENTRY-1"]["sku_key"] == "SKU_ENTRY"
    assert by_order["ENTRY-1"]["sku_id"] == "SKU_ENTRY_L"
    assert by_order["ENTRY-1"]["quantity"] == 3
    assert by_order["HEADER-1"]["sku_key"] == "SKU_HEADER"
    assert by_order["HEADER-1"]["sku_id"] == "SKU_HEADER_M"
    assert by_order["HEADER-1"]["quantity"] == 2
    assert summary["rows_built_from_entries"] == 1
    assert summary["rows_built_from_headers"] == 1


def test_rebuild_uses_suffix_article_patch_and_assigned_size(tmp_path: Path) -> None:
    db_path = tmp_path / "app.db"
    conn = _create_sales_rebuild_db(db_path)
    conn.execute(
        """
        INSERT INTO dim_kaspi_article_map
            (store_code, kaspi_article, kaspi_offer_name, sku_key, sku_id, active_flag)
        VALUES ('UNIVERSAL', '_687453750', 'Леггинсы PRO COMBAT 2010 белый 2XL',
                'CL_NEW-CLO_MEN_LEG_WHITE', '', 1)
        """
    )
    conn.execute(
        """
        INSERT INTO fact_orders_kaspi (
            order_id, store_code, kaspi_offer_name, sku_key, sku_id, my_size,
            quantity, unit_price_kzt, delivery_cost, status_updated_at, internal_status
        ) VALUES (
            'SUFFIX-1', 'UNIVERSAL', 'Леггинсы PRO COMBAT 2010 белый 2XL',
            'CL_NEW-CLO_MEN_LEG_WHITE', 'CL_NEW-CLO_MEN_LEG_WHITE_2XL', '2XL',
            1, 1500, 0, '2026-06-14T12:00:00', 'COMPLETED'
        )
        """
    )
    conn.execute(
        """
        INSERT INTO fact_order_entries_kaspi
            (entry_id, order_id, store_code, offer_id, quantity, total_price_kzt)
        VALUES ('entry-suffix-1', 'SUFFIX-1', 'UNIVERSAL', '132822924_687453750', 1, 1500)
        """
    )

    rows, summary = build_sales_fact_v2_rows_from_entries(
        conn,
        as_of=date(2026, 6, 15),
        start_date=date(2026, 6, 14),
        strict=True,
    )
    conn.close()

    assert len(rows) == 1
    assert rows[0]["sku_key"] == "CL_NEW-CLO_MEN_LEG_WHITE"
    assert rows[0]["sku_id"] == "CL_NEW-CLO_MEN_LEG_WHITE_2XL"
    assert rows[0]["my_size"] == "2XL"
    assert summary["errors_count"] == 0


def test_rebuild_delete_scope_stays_inside_requested_window(tmp_path: Path) -> None:
    db_path = tmp_path / "app.db"
    conn = _create_sales_rebuild_db(db_path)
    conn.execute(
        """
        INSERT INTO fact_orders_kaspi (
            order_id, store_code, kaspi_offer_name, sku_key, sku_id, my_size,
            quantity, unit_price_kzt, delivery_cost, status_updated_at, internal_status
        ) VALUES ('HEADER-2', 'UNIVERSAL', 'Header fallback', 'SKU_HEADER', 'SKU_HEADER_M', 'M',
                  1, 15000, 0, '2026-04-21T12:00:00', 'COMPLETED')
        """
    )
    conn.execute(
        """
        INSERT INTO sales_fact_v2 (
            order_id, order_date, sku_key, sku_id, my_size, kaspi_offer_name, store_code,
            quantity, sell_price_kzt, delivery_fee, cogs, net_rev, profit,
            status, return_flag, return_date, source_file, api_updated_at
        ) VALUES (
            'OLD-1', '2025-12-20', 'OLD_SKU', 'OLD_SKU_M', 'M', 'Old rebuild', 'UNIVERSAL',
            1, 10000, 0, NULL, 10000, NULL, 'DELIVERED', 0, NULL, 'KASPI_API_ENTRIES_REBUILD', NULL
        )
        """
    )
    conn.commit()
    conn.close()

    run_rebuild(
        db_path=db_path,
        as_of=date(2026, 5, 4),
        start_date=date(2026, 4, 16),
        output_root=tmp_path / "out",
        backup_root=tmp_path / "backups",
        strict=True,
        apply=False,
    )
    plan = json.loads((tmp_path / "out" / "2026-05-04" / "rebuild_plan.json").read_text())

    assert plan["delete_count"] == 0
    assert plan["rows_delete_keys"] == []


def test_strict_rebuild_skips_identityless_duplicate_archive_header(tmp_path: Path) -> None:
    db_path = tmp_path / "app.db"
    conn = _create_sales_rebuild_db(db_path)
    conn.executemany(
        """
        INSERT INTO fact_orders_kaspi (
            order_id, store_code, kaspi_offer_name, sku_key, sku_id, my_size,
            quantity, unit_price_kzt, delivery_cost, status_updated_at, internal_status, kaspi_status
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        [
            (
                "DUP-ARCHIVE-1",
                "STOREB",
                "nan",
                "",
                "",
                "",
                1,
                2800,
                0,
                "2026-05-10T02:02:11",
                "COMPLETED",
                "ARCHIVE",
            ),
            (
                "DUP-ARCHIVE-1",
                "STOREB",
                "Рашгард 30203092_627506878 черный 46",
                "CL_NEW-CLO_MEN_NIKE-SHIRT_BLACK",
                "CL_NEW-CLO_MEN_NIKE-SHIRT_BLACK_L",
                "L",
                1,
                2800,
                0,
                "",
                "ACCEPTED",
                "KASPI_DELIVERY",
            ),
        ],
    )

    rows, summary = build_sales_fact_v2_rows_from_entries(
        conn,
        as_of=date(2026, 5, 31),
        start_date=date(2026, 5, 5),
        strict=True,
    )

    assert summary["skipped_identityless_duplicate_headers"] == 1
    assert len(rows) == 1
    assert rows[0]["order_id"] == "DUP-ARCHIVE-1"
    assert rows[0]["sku_id"] == "CL_NEW-CLO_MEN_NIKE-SHIRT_BLACK_L"


def test_entry_rebuild_upgrades_weak_article_map_with_entry_size_identity(tmp_path: Path) -> None:
    db_path = tmp_path / "app.db"
    conn = _create_sales_rebuild_db(db_path)
    conn.execute(
        """
        INSERT INTO dim_kaspi_article_map
            (store_code, kaspi_article, kaspi_offer_name, sku_key, sku_id, active_flag)
        VALUES ('UNIVERSAL', 'CL_TEST_WEAK_L_123', '', 'CL_TEST_WEAK', 'CL_TEST_WEAK', 1)
        """
    )
    conn.execute(
        """
        INSERT INTO fact_orders_kaspi (
            order_id, store_code, kaspi_offer_name, sku_key, sku_id, my_size,
            quantity, unit_price_kzt, delivery_cost, status_updated_at, internal_status
        ) VALUES ('WEAK-1', 'UNIVERSAL', 'Weak mapped offer', 'CL_TEST_WEAK', 'CL_TEST_WEAK_L', 'L',
                  1, 15000, 0, '2026-04-21T12:00:00', 'COMPLETED')
        """
    )
    conn.execute(
        """
        INSERT INTO fact_order_entries_kaspi
            (entry_id, order_id, store_code, offer_id, quantity, total_price_kzt)
        VALUES ('entry-weak', 'WEAK-1', 'UNIVERSAL', 'CL_TEST_WEAK_L_123', 1, 15000)
        """
    )

    rows, _summary = build_sales_fact_v2_rows_from_entries(
        conn,
        as_of=date(2026, 5, 4),
        start_date=date(2026, 4, 16),
        strict=True,
    )

    assert rows[0]["sku_id"] == "CL_TEST_WEAK_L"
    assert rows[0]["my_size"] == "L"


def test_entry_rebuild_uses_raw_json_offer_code_when_flat_offer_id_blank(tmp_path: Path) -> None:
    db_path = tmp_path / "app.db"
    conn = _create_sales_rebuild_db(db_path)
    conn.execute(
        """
        INSERT INTO dim_kaspi_article_map
            (store_code, kaspi_article, kaspi_offer_name, sku_key, sku_id, active_flag)
        VALUES ('ACMEWEAR', 'CL_RAW_TEST_BLACK_L_123456', '', 'CL_RAW_TEST_BLACK', 'CL_RAW_TEST_BLACK_L', 1)
        """
    )
    conn.execute(
        """
        INSERT INTO fact_orders_kaspi (
            order_id, store_code, kaspi_offer_name, sku_key, sku_id, my_size,
            quantity, unit_price_kzt, delivery_cost, status_updated_at, internal_status
        ) VALUES ('RAW-1', 'ACMEWEAR', '', '', '', '',
                  1, 15000, 0, '2026-06-10T12:00:00', 'COMPLETED')
        """
    )
    conn.execute(
        """
        INSERT INTO fact_order_entries_kaspi
            (entry_id, order_id, store_code, offer_id, raw_json, quantity, total_price_kzt)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            "entry-raw",
            "RAW-1",
            "ACMEWEAR",
            "",
            json.dumps({"attributes": {"offer": {"code": "CL_RAW_TEST_BLACK_L_123456", "name": "Raw Test L"}}}),
            1,
            15000,
        ),
    )

    rows, summary = build_sales_fact_v2_rows_from_entries(
        conn,
        as_of=date(2026, 6, 13),
        start_date=date(2026, 6, 1),
        strict=True,
    )

    assert summary["errors_count"] == 0
    assert len(rows) == 1
    assert rows[0]["sku_key"] == "CL_RAW_TEST_BLACK"
    assert rows[0]["sku_id"] == "CL_RAW_TEST_BLACK_L"
    assert rows[0]["kaspi_offer_name"] == "CL_RAW_TEST_BLACK_L_123456"


def test_entry_rebuild_skips_cancelled_unmapped_entry_without_relaxing_sales(tmp_path: Path) -> None:
    db_path = tmp_path / "app.db"
    conn = _create_sales_rebuild_db(db_path)
    conn.execute(
        """
        INSERT INTO fact_orders_kaspi (
            order_id, store_code, kaspi_offer_name, sku_key, sku_id, my_size,
            quantity, unit_price_kzt, delivery_cost, status_updated_at, internal_status
        ) VALUES ('CANCEL-UNMAPPED-1', 'STOREB', '', '', '', '',
                  1, 9499, 0, '2026-06-10T12:00:00', 'CANCELLED')
        """
    )
    conn.execute(
        """
        INSERT INTO fact_order_entries_kaspi
            (entry_id, order_id, store_code, offer_id, raw_json, quantity, total_price_kzt)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            "entry-cancel-unmapped",
            "CANCEL-UNMAPPED-1",
            "STOREB",
            "",
            json.dumps({"attributes": {"offer": {"code": "116515378_626543467", "name": "Ambiguous"}}}),
            1,
            9499,
        ),
    )

    rows, summary = build_sales_fact_v2_rows_from_entries(
        conn,
        as_of=date(2026, 6, 13),
        start_date=date(2026, 6, 1),
        strict=True,
    )

    assert rows == []
    assert summary["errors_count"] == 0


def test_strict_rebuild_fails_when_completed_header_lacks_sku_identity(tmp_path: Path) -> None:
    db_path = tmp_path / "app.db"
    conn = _create_sales_rebuild_db(db_path)
    conn.execute(
        """
        INSERT INTO fact_orders_kaspi (
            order_id, store_code, kaspi_offer_name, sku_key, sku_id, my_size,
            quantity, unit_price_kzt, delivery_cost, status_updated_at, internal_status
        ) VALUES ('BAD-1', 'UNIVERSAL', 'Bad header', '', '', '',
                  1, 15000, 0, '2026-04-21T12:00:00', 'COMPLETED')
        """
    )

    with pytest.raises(RebuildError, match="missing required evidence"):
        build_sales_fact_v2_rows_from_entries(
            conn,
            as_of=date(2026, 5, 4),
            start_date=date(2026, 4, 16),
            strict=True,
        )
