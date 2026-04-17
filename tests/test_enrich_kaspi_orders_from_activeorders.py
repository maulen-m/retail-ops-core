from __future__ import annotations

import sqlite3
from pathlib import Path

from scripts.enrich_kaspi_orders_from_activeorders import (
    _apply_updates,
    _canonicalize_parsed_orders,
    _ensure_dim_sku,
    _ensure_dim_sku_size,
    _filter_parsed_orders,
    _insert_from_template,
    _load_article_identity_map,
    plan_activeorders_enrichment,
)


def _make_db(db_path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.executescript(
        """
        CREATE TABLE fact_orders_kaspi (
            id INTEGER PRIMARY KEY,
            order_id TEXT,
            store_code TEXT,
            channel_code TEXT,
            kaspi_offer_name TEXT,
            sku_key TEXT,
            sku_id TEXT,
            my_size TEXT,
            quantity INTEGER,
            unit_price_kzt REAL,
            created_at TEXT,
            planned_shipment_date TEXT,
            actual_shipment_date TEXT,
            kaspi_status TEXT,
            internal_status TEXT,
            status_updated_at TEXT,
            waybill_url TEXT,
            waybill_number TEXT,
            waybill_downloaded INTEGER,
            source TEXT,
            source_file TEXT,
            assigned_size TEXT,
            size_source TEXT,
            size_confidence TEXT,
            customer_height_cm INTEGER,
            customer_weight_kg INTEGER,
            kaspi_status_detail TEXT,
            planned_delivery_date TEXT,
            courier_transmission_planning_date TEXT,
            courier_transmission_date TEXT,
            delivery_mode TEXT,
            payment_mode TEXT,
            signature_required INTEGER,
            credit_term INTEGER,
            pre_order INTEGER,
            approved_by_bank_date TEXT,
            reservation_date TEXT,
            delivery_cost REAL,
            delivery_cost_for_seller REAL,
            delivery_address TEXT,
            is_imei_required INTEGER,
            express INTEGER,
            returned_to_warehouse INTEGER,
            category TEXT,
            customer_first_name TEXT,
            customer_last_name TEXT,
            customer_phone TEXT,
            updated_at TEXT
        );
        CREATE TABLE dim_sku (
            sku_key TEXT PRIMARY KEY,
            model TEXT NOT NULL,
            color TEXT,
            product_type TEXT NOT NULL,
            base_cost_cny REAL NOT NULL,
            weight_kg REAL NOT NULL,
            category TEXT,
            gender TEXT,
            active_flag INTEGER DEFAULT 1,
            created_at TEXT DEFAULT (datetime('now')),
            updated_at TEXT DEFAULT (datetime('now'))
        );
        CREATE TABLE dim_sku_size (
            sku_id TEXT PRIMARY KEY,
            sku_key TEXT NOT NULL,
            my_size TEXT NOT NULL,
            barcode TEXT,
            size_order INTEGER,
            active_flag INTEGER DEFAULT 1,
            created_at TEXT DEFAULT (datetime('now'))
        );
        CREATE TABLE dim_kaspi_article_map (
            id INTEGER PRIMARY KEY,
            store_code TEXT NOT NULL,
            kaspi_article TEXT NOT NULL,
            kaspi_offer_name TEXT,
            kaspi_name_core TEXT,
            sku_key TEXT,
            sku_id TEXT,
            source TEXT,
            updated_at TEXT DEFAULT (datetime('now'))
        );
        """
    )
    return conn


def test_filter_parsed_orders_keeps_ready_rows_up_to_target():
    orders = [
        {"order_id": "1", "internal_status": "READY", "planned_shipment_date": "2026-04-15"},
        {"order_id": "2", "internal_status": "READY", "planned_shipment_date": "2026-04-14"},
        {"order_id": "3", "internal_status": "NEW", "planned_shipment_date": "2026-04-15"},
        {"order_id": "4", "internal_status": "READY", "planned_shipment_date": "2026-04-16"},
    ]

    filtered = _filter_parsed_orders(orders, target_date=__import__("datetime").date(2026, 4, 15))

    assert [row["order_id"] for row in filtered] == ["1", "2"]


def test_plan_activeorders_enrichment_matches_blank_identity_then_inserts_extra_line():
    parsed_orders = [
        {
            "order_id": "889224556",
            "store_code": "STOREB",
            "planned_shipment_date": "2026-04-15",
            "kaspi_offer_name": "Offer A",
            "sku_key": "SKU-A",
            "sku_id": "SKU-A_L",
            "my_size": "L",
            "quantity": 1,
            "unit_price_kzt": 1000,
        },
        {
            "order_id": "889224556",
            "store_code": "STOREB",
            "planned_shipment_date": "2026-04-15",
            "kaspi_offer_name": "Offer B",
            "sku_key": "SKU-B",
            "sku_id": "SKU-B_XL",
            "my_size": "XL",
            "quantity": 1,
            "unit_price_kzt": 1200,
        },
    ]
    candidate_rows = [
        {
            "id": 33074,
            "order_id": "889224556",
            "store_code": "STOREB",
            "planned_shipment_date": "2026-04-15",
            "kaspi_offer_name": "",
            "sku_key": "",
            "sku_id": "",
            "quantity": 1,
            "internal_status": "ACCEPTED",
        }
    ]

    plan = plan_activeorders_enrichment(parsed_orders=parsed_orders, candidate_rows=candidate_rows)

    assert len(plan["updates"]) == 1
    assert len(plan["inserts"]) == 1
    assert plan["updates"][0]["candidate"]["id"] == 33074
    assert plan["updates"][0]["order"]["sku_id"] == "SKU-A_L"
    assert plan["inserts"][0]["order"]["sku_id"] == "SKU-B_XL"


def test_plan_activeorders_enrichment_handles_blank_parsed_identity_without_crashing():
    parsed_orders = [
        {
            "order_id": "1002",
            "store_code": "UNIVERSAL",
            "planned_shipment_date": "2026-04-15",
            "kaspi_offer_name": "",
            "sku_key": "",
            "sku_id": "",
            "my_size": "",
            "quantity": 1,
            "unit_price_kzt": 1990,
        }
    ]
    candidate_rows = [
        {
            "id": 44,
            "order_id": "1002",
            "store_code": "UNIVERSAL",
            "planned_shipment_date": "2026-04-15",
            "kaspi_offer_name": "",
            "sku_key": "",
            "sku_id": "",
            "quantity": 1,
            "internal_status": "ACCEPTED",
        }
    ]

    plan = plan_activeorders_enrichment(parsed_orders=parsed_orders, candidate_rows=candidate_rows)

    assert len(plan["updates"]) == 1
    assert plan["updates"][0]["candidate"]["id"] == 44
    assert plan["inserts"] == []


def test_canonicalize_parsed_orders_uses_article_map_for_acmewear_line51_alias(tmp_path: Path):
    db_path = tmp_path / "app.db"
    conn = _make_db(db_path)
    try:
        conn.execute(
            """
            INSERT INTO dim_kaspi_article_map (
                store_code, kaspi_article, kaspi_offer_name, kaspi_name_core, sku_key, sku_id, source
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "ACMEWEAR",
                "CL_OC_MEN_LINE51_WHITE_K-O_ST_4XL_2_159720193",
                "Спортивный костюм ACMEWEAR OF_SUIT-61_BLK_K-O_4XL_58 черный, белый 4XL",
                "Line51",
                "CL_OC_MEN_LINE51_WHITE",
                None,
                "crm_historical_patch",
            ),
        )
        orders = [
            {
                "order_id": "890181585",
                "store_code": "ACMEWEAR",
                "kaspi_article": "CL_OC_MEN_LINE51_WHITE_K-O_ST_4XL_2_159720193",
                "kaspi_offer_name": "Спортивный костюм ACMEWEAR OF_SUIT-61_BLK_K-O_4XL_58 черный, белый 4XL",
                "sku_key": "CL_OC_MEN_LINE51_WHITE_K-O_ST_4XL_2",
                "sku_id": "CL_OC_MEN_LINE51_WHITE_K-O_ST_4XL_2_4XL",
                "my_size": "4XL",
                "quantity": 1,
                "unit_price_kzt": 13990,
                "planned_shipment_date": "2026-04-15",
                "internal_status": "READY",
            }
        ]

        article_map = _load_article_identity_map(conn, orders)
        canonicalized, overrides = _canonicalize_parsed_orders(orders, article_map)
    finally:
        conn.close()

    assert article_map[("ACMEWEAR", "CL_OC_MEN_LINE51_WHITE_K-O_ST_4XL_2")]["sku_key"] == "CL_OC_MEN_LINE51_WHITE"
    assert overrides == 1
    assert canonicalized[0]["sku_key"] == "CL_OC_MEN_LINE51_WHITE"
    assert canonicalized[0]["sku_id"] == "CL_OC_MEN_LINE51_WHITE_4XL"
    assert canonicalized[0]["my_size"] == "4XL"


def test_canonicalize_parsed_orders_prefers_exact_article_before_ambiguous_normalized_family(tmp_path: Path):
    db_path = tmp_path / "app.db"
    conn = _make_db(db_path)
    try:
        conn.executemany(
            """
            INSERT INTO dim_kaspi_article_map (
                store_code, kaspi_article, kaspi_offer_name, kaspi_name_core, sku_key, sku_id, source
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    "UNIVERSAL",
                    "132822924_328581041",
                    "Леггинсы PRO COMBAT 2010 белый XL",
                    "Леггинсы_PRO_COMBAT_2010_белый",
                    "CL_NEW-CLO_MEN_LEG_WHITE",
                    "CL_NEW-CLO_MEN_LEG_WHITE_2XL",
                    "crm_historical_patch",
                ),
                (
                    "UNIVERSAL",
                    "132822924_884186730",
                    "Леггинсы PRO COMBAT 2010 белый M",
                    "Леггинсы_PRO_COMBAT_2010_белый",
                    "CL_NEW-CLO_MEN_LEG_WHITE",
                    "CL_NEW-CLO_MEN_LEG_WHITE_M",
                    "crm_historical_patch",
                ),
            ],
        )
        orders = [
            {
                "order_id": "891902371",
                "store_code": "UNIVERSAL",
                "kaspi_article": "132822924_328581041",
                "kaspi_offer_name": "Леггинсы PRO COMBAT 2010 белый XL",
                "sku_key": "",
                "sku_id": "",
                "my_size": "",
                "quantity": 1,
                "unit_price_kzt": 1500,
                "planned_shipment_date": "2026-04-17",
                "internal_status": "READY",
            }
        ]

        article_map = _load_article_identity_map(conn, orders)
        canonicalized, overrides = _canonicalize_parsed_orders(orders, article_map)
    finally:
        conn.close()

    assert article_map[("UNIVERSAL", "132822924_328581041")]["sku_id"] == "CL_NEW-CLO_MEN_LEG_WHITE_2XL"
    assert overrides == 1
    assert canonicalized[0]["sku_key"] == "CL_NEW-CLO_MEN_LEG_WHITE"
    assert canonicalized[0]["sku_id"] == "CL_NEW-CLO_MEN_LEG_WHITE_2XL"
    assert canonicalized[0]["my_size"] == "2XL"


def test_apply_activeorders_enrichment_updates_identity_without_writing_customer_size(tmp_path: Path):
    db_path = tmp_path / "app.db"
    conn = _make_db(db_path)
    try:
        conn.execute(
            """
            INSERT INTO fact_orders_kaspi (
                id, order_id, store_code, channel_code, kaspi_offer_name, sku_key, sku_id, my_size,
                quantity, unit_price_kzt, created_at, planned_shipment_date, actual_shipment_date,
                kaspi_status, internal_status, status_updated_at, source, source_file, assigned_size
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                1,
                "1001",
                "UNIVERSAL",
                "KSP",
                None,
                None,
                None,
                None,
                1,
                1799,
                "2026-04-14T10:00:00",
                "2026-04-15",
                None,
                "KASPI_DELIVERY",
                "ACCEPTED",
                None,
                "API",
                None,
                None,
            ),
        )
        order = {
            "order_id": "1001",
            "store_code": "UNIVERSAL",
            "planned_shipment_date": "2026-04-15",
            "kaspi_offer_name": "Offer Name",
            "sku_key": "CL_NEW-CLO_MEN_TEST_BLACK",
            "sku_id": "CL_NEW-CLO_MEN_TEST_BLACK_XL",
            "my_size": "XL",
            "product_type": "CL",
            "quantity": 2,
            "unit_price_kzt": 1990,
        }
        _ensure_dim_sku(conn, order["sku_key"], product_type="CL")
        _ensure_dim_sku_size(conn, order["sku_id"], order["sku_key"], order["my_size"])
        applied = _apply_updates(
            conn,
            [{"id": 1, "order": order, "candidate": {"id": 1}}],
            source_file="excel_ui/ActiveOrders/ActiveOrders.xlsx",
        )
        conn.commit()
        row = conn.execute(
            "SELECT kaspi_offer_name, sku_key, sku_id, my_size, assigned_size, quantity FROM fact_orders_kaspi WHERE id = 1"
        ).fetchone()
        dim_row = conn.execute("SELECT sku_key, product_type FROM dim_sku WHERE sku_key = ?", (order["sku_key"],)).fetchone()
        size_row = conn.execute("SELECT sku_id, my_size FROM dim_sku_size WHERE sku_id = ?", (order["sku_id"],)).fetchone()
    finally:
        conn.close()

    assert applied == 1
    assert tuple(row) == (
        "Offer Name",
        "CL_NEW-CLO_MEN_TEST_BLACK",
        "CL_NEW-CLO_MEN_TEST_BLACK_XL",
        None,
        None,
        2,
    )
    assert tuple(dim_row) == ("CL_NEW-CLO_MEN_TEST_BLACK", "CL")
    assert tuple(size_row) == ("CL_NEW-CLO_MEN_TEST_BLACK_XL", "XL")


def test_insert_from_template_copies_order_level_fields_but_leaves_manual_size_blank(tmp_path: Path):
    db_path = tmp_path / "app.db"
    conn = _make_db(db_path)
    try:
        inserted = _insert_from_template(
            conn,
            [
                {
                    "order": {
                        "order_id": "2001",
                        "store_code": "STOREB",
                        "planned_shipment_date": "2026-04-15",
                        "kaspi_offer_name": "Offer B",
                        "sku_key": "SKU-B",
                        "sku_id": "SKU-B_XL",
                        "quantity": 1,
                        "unit_price_kzt": 1200,
                    },
                    "template": {
                        "store_code": "STOREB",
                        "channel_code": "KSP",
                        "kaspi_status": "KASPI_DELIVERY",
                        "internal_status": "ACCEPTED",
                        "delivery_mode": "DELIVERY_PICKUP",
                        "payment_mode": "PREPAID",
                        "customer_phone": "+0(000)-000-00-00",
                    },
                }
            ],
            source_file="excel_ui/ActiveOrders/ActiveOrders.xlsx",
        )
        conn.commit()
        row = conn.execute(
            "SELECT order_id, store_code, kaspi_offer_name, sku_key, sku_id, my_size, assigned_size, delivery_mode, payment_mode FROM fact_orders_kaspi"
        ).fetchone()
    finally:
        conn.close()

    assert inserted == 1
    assert tuple(row) == (
        "2001",
        "STOREB",
        "Offer B",
        "SKU-B",
        "SKU-B_XL",
        None,
        None,
        "DELIVERY_PICKUP",
        "PREPAID",
    )
