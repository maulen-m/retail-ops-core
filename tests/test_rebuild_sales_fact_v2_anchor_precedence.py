from __future__ import annotations

import sqlite3

from scripts.rebuild_sales_fact_v2_from_kaspi_entries import build_rebuild_plan


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
        """
    )


def _insert_sales_fact(
    conn: sqlite3.Connection,
    *,
    order_id: str,
    sku_id: str,
    store_code: str,
    offer: str,
    source_file: str,
) -> None:
    conn.execute(
        """
        INSERT INTO sales_fact_v2 (
            order_id, order_date, sku_key, sku_id, my_size, kaspi_offer_name, store_code,
            quantity, sell_price_kzt, delivery_fee, cogs, net_rev, profit,
            status, return_flag, return_date, source_file, api_updated_at
        ) VALUES (
            ?, '2026-02-01', 'SKU', ?, 'L', ?, ?,
            1, 1000, 50, 500, 950, 450,
            'DELIVERED', 0, NULL, ?, NULL
        )
        """,
        (order_id, sku_id, offer, store_code, source_file),
    )


def test_build_rebuild_plan_removes_kaspi_overlap_when_anchor_exists() -> None:
    conn = sqlite3.connect(":memory:")
    _seed_schema(conn)

    # Anchor row is the preferred truth for this order/store.
    _insert_sales_fact(
        conn,
        order_id="ORD-1",
        sku_id="SKU-ANCHOR",
        store_code="ACMEWEAR",
        offer="OFFER-1",
        source_file="OCEAN_DROP_ANCHOR",
    )
    # Historical kaspi rebuild row for same order/store should be deleted.
    _insert_sales_fact(
        conn,
        order_id="ORD-1",
        sku_id="SKU-KASPI-OLD",
        store_code="ACMEWEAR",
        offer="OFFER-1",
        source_file="KASPI_API_ENTRIES_REBUILD",
    )
    conn.commit()

    rows = [
        {
            "order_id": "ORD-1",
            "order_date": "2026-02-05",
            "sku_key": "SKU-KASPI-NEW",
            "sku_id": "SKU-KASPI-NEW",
            "my_size": "XL",
            "kaspi_offer_name": "OFFER-1",
            "store_code": "ACMEWEAR",
            "quantity": 1,
            "sell_price_kzt": 1200.0,
            "delivery_fee": 50.0,
            "cogs": None,
            "net_rev": 1150.0,
            "profit": None,
            "status": "DELIVERED",
            "return_flag": 0,
            "return_date": None,
            "source_file": "KASPI_API_ENTRIES_REBUILD",
            "api_updated_at": None,
        },
        {
            "order_id": "ORD-2",
            "order_date": "2026-02-05",
            "sku_key": "SKU-2",
            "sku_id": "SKU-2",
            "my_size": "M",
            "kaspi_offer_name": "OFFER-2",
            "store_code": "ACMEWEAR",
            "quantity": 1,
            "sell_price_kzt": 1000.0,
            "delivery_fee": 50.0,
            "cogs": None,
            "net_rev": 950.0,
            "profit": None,
            "status": "DELIVERED",
            "return_flag": 0,
            "return_date": None,
            "source_file": "KASPI_API_ENTRIES_REBUILD",
            "api_updated_at": None,
        },
    ]

    plan = build_rebuild_plan(rows=rows, conn=conn)
    conn.close()

    assert plan["insert_count"] == 1
    assert plan["rows_insert"][0]["order_id"] == "ORD-2"
    assert plan["delete_count"] == 1
    assert ("ORD-1", "SKU-KASPI-OLD", "ACMEWEAR", "OFFER-1") in plan["rows_delete_keys"]
