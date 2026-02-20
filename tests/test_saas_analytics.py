import sqlite3
from pathlib import Path

import pytest

from core.analytics.api import handle_request
from core.analytics.queries import get_health_summary
from core.analytics.views import ensure_sales_views


def _create_db(tmp_path: Path) -> Path:
    db_path = tmp_path / "test.db"
    conn = sqlite3.connect(db_path)
    conn.executescript(
        """
        CREATE TABLE sales_fact_v2 (
            sale_id INTEGER PRIMARY KEY AUTOINCREMENT,
            order_id TEXT NOT NULL,
            order_date TEXT NOT NULL,
            sku_key TEXT NOT NULL,
            sku_id TEXT NOT NULL,
            my_size TEXT,
            kaspi_offer_name TEXT,
            store_code TEXT,
            quantity INTEGER NOT NULL,
            sell_price_kzt REAL,
            delivery_fee REAL,
            status TEXT,
            return_flag INTEGER
        );

        CREATE TABLE dim_sku (
            sku_key TEXT PRIMARY KEY,
            product_type TEXT,
            base_cost_cny REAL,
            weight_kg REAL
        );

        CREATE TABLE dim_fx_rates (
            effective_date TEXT PRIMARY KEY,
            cny_kzt REAL NOT NULL,
            usd_kzt REAL NOT NULL,
            dlv_rate_usd_kg REAL NOT NULL
        );

        CREATE TABLE dim_params (
            param_key TEXT PRIMARY KEY,
            product_type TEXT,
            param_value REAL NOT NULL,
            updated_at TEXT DEFAULT (datetime('now'))
        );

        CREATE TABLE fact_sku_metrics (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            computed_at TEXT NOT NULL,
            sku_key TEXT NOT NULL,
            store_code TEXT NOT NULL,
            d30 REAL NOT NULL,
            sigma REAL NOT NULL,
            ss_demand REAL NOT NULL,
            ss_floor REAL NOT NULL,
            ss_mix REAL NOT NULL,
            ss_total REAL NOT NULL,
            rop REAL NOT NULL,
            target_stock REAL NOT NULL,
            avg_price REAL,
            avg_cogs REAL,
            avg_profit REAL,
            k_avg REAL,
            roic_monthly REAL,
            current_stock INTEGER,
            inbound_stock INTEGER,
            total_stock INTEGER,
            status TEXT NOT NULL,
            suggested_order_qty INTEGER,
            days_with_sales INTEGER,
            total_units_30d INTEGER
        );

        CREATE TABLE dim_sku_lifecycle (
            sku_key TEXT PRIMARY KEY,
            lifecycle_status TEXT NOT NULL DEFAULT 'GROW',
            status_reason TEXT
        );

        CREATE TABLE fact_inventory_snapshot_size (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            snapshot_date TEXT NOT NULL,
            sku_id TEXT NOT NULL,
            sku_key TEXT NOT NULL,
            my_size TEXT NOT NULL,
            current_stock INTEGER NOT NULL DEFAULT 0,
            inbound_stock INTEGER NOT NULL DEFAULT 0
        );

        CREATE TABLE stock_ledger (
            event_date TEXT NOT NULL,
            event_type TEXT NOT NULL,
            sku_key TEXT NOT NULL,
            sku_id TEXT NOT NULL,
            my_size TEXT,
            store_code TEXT DEFAULT 'UNIVERSAL',
            qty_change INTEGER NOT NULL
        );

        CREATE TABLE po_header (
            po_id TEXT PRIMARY KEY,
            status TEXT DEFAULT 'DRAFT'
        );

        CREATE TABLE po_line (
            po_line_id INTEGER PRIMARY KEY AUTOINCREMENT,
            po_id TEXT NOT NULL,
            sku_key TEXT NOT NULL,
            order_qty INTEGER NOT NULL,
            received_qty INTEGER DEFAULT 0,
            status TEXT DEFAULT 'PENDING'
        );
        """
    )

    conn.execute(
        "INSERT INTO dim_fx_rates (effective_date, cny_kzt, usd_kzt, dlv_rate_usd_kg) VALUES (?,?,?,?)",
        ("2026-01-01", 78.0, 530.0, 2.66),
    )
    conn.execute(
        "INSERT INTO dim_params (param_key, product_type, param_value) VALUES (?,?,?)",
        ("commission", None, 0.125),
    )
    conn.execute(
        "INSERT INTO dim_params (param_key, product_type, param_value) VALUES (?,?,?)",
        ("VAT_rate", None, 0.03),
    )
    conn.execute(
        "INSERT INTO dim_sku (sku_key, product_type, base_cost_cny, weight_kg) VALUES (?,?,?,?)",
        ("LINE52", "CL", 47.0, 0.95),
    )
    conn.execute(
        """
        INSERT INTO sales_fact_v2 (
            order_id, order_date, sku_key, sku_id, my_size, kaspi_offer_name,
            store_code, quantity, sell_price_kzt, delivery_fee, status, return_flag
        ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
        """,
        (
            "ORD-1",
            "2026-01-02",
            "LINE52",
            "LINE52_XL",
            "XL",
            "LINE52 BLACK XL",
            "UNIVERSAL",
            2,
            12000.0,
            None,
            "DELIVERED",
            0,
        ),
    )
    conn.commit()
    conn.close()
    return db_path


def test_sales_enriched_view_math(tmp_path):
    db_path = _create_db(tmp_path)
    conn = sqlite3.connect(db_path)
    ensure_sales_views(conn)
    row = conn.execute("SELECT delivery_fee_unit, net_rev_unit, cogs_unit, profit_unit FROM v_sales_enriched").fetchone()
    conn.close()

    delivery_fee_unit, net_rev_unit, cogs_unit, profit_unit = row
    assert delivery_fee_unit == pytest.approx(1099.14)

    # VAT schedule should apply 4% from 2026-01-01
    expected_net_rev_unit = (12000 * (1 - 0.125) - 1099.14) * 0.96
    expected_cogs_unit = 47 * 78 + 0.95 * 2.66 * 530
    expected_profit_unit = expected_net_rev_unit - expected_cogs_unit

    assert abs(net_rev_unit - expected_net_rev_unit) < 0.5
    assert abs(cogs_unit - expected_cogs_unit) < 0.5
    assert abs(profit_unit - expected_profit_unit) < 0.5


def test_endpoints_smoke(tmp_path):
    db_path = _create_db(tmp_path)

    status, payload = handle_request("/kpis/last30", "end_date=2026-01-15", db_path=str(db_path))
    assert status == 200
    assert "current" in payload
    assert payload["current"]["units"] == 2.0

    status, payload = handle_request("/filters/options", "", db_path=str(db_path))
    assert status == 200
    assert "LINE52" in payload["sku_keys"]

    conn = sqlite3.connect(db_path)
    conn.execute(
        """
        INSERT INTO fact_sku_metrics (
            computed_at, sku_key, store_code, d30, sigma, ss_demand, ss_floor, ss_mix, ss_total, rop,
            target_stock, avg_price, avg_cogs, avg_profit, k_avg, roic_monthly, current_stock, inbound_stock,
            total_stock, status, suggested_order_qty, days_with_sales, total_units_30d
        ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """,
        (
            "2026-01-02",
            "LINE52",
            "UNIVERSAL",
            1.0,
            0.4,
            2.0,
            3.0,
            1.0,
            6.0,
            10.0,
            12.0,
            12000.0,
            5000.0,
            3000.0,
            10000.0,
            0.2,
            5,
            2,
            7,
            "OK",
            0,
            12,
            60,
        ),
    )
    conn.commit()
    conn.close()

    status, payload = handle_request("/kpis/sku_share", "metric=revenue&end_date=2026-01-15", db_path=str(db_path))
    assert status == 200
    assert payload["items"]


def test_health_summary_inventory_from_ledger(tmp_path):
    db_path = _create_db(tmp_path)
    conn = sqlite3.connect(db_path)
    ensure_sales_views(conn)

    conn.execute(
        """
        INSERT INTO stock_ledger (event_date, event_type, sku_key, sku_id, my_size, store_code, qty_change)
        VALUES (?,?,?,?,?,?,?)
        """,
        ("2026-01-01", "INITIAL", "LINE52", "LINE52_XL", "XL", "UNIVERSAL", 10),
    )
    conn.execute(
        """
        INSERT INTO fact_inventory_snapshot_size (
            snapshot_date, sku_id, sku_key, my_size, current_stock, inbound_stock
        ) VALUES (?,?,?,?,?,?)
        """,
        ("2026-01-01", "LINE52_XL", "LINE52", "XL", 10, 4),
    )
    conn.execute("INSERT INTO po_header (po_id, status) VALUES (?, ?)", ("PO-1", "OPEN"))
    conn.execute(
        """
        INSERT INTO po_line (po_id, sku_key, order_qty, received_qty, status)
        VALUES (?,?,?,?,?)
        """,
        ("PO-1", "LINE52", 5, 1, "PENDING"),
    )
    conn.execute(
        """
        INSERT INTO sales_fact_v2 (
            order_id, order_date, sku_key, sku_id, my_size, kaspi_offer_name,
            store_code, quantity, sell_price_kzt, delivery_fee, status, return_flag
        ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
        """,
        (
            "ORD-MISSING",
            "2026-01-02",
            "MISSING",
            "MISSING_XL",
            "XL",
            "MISSING",
            "UNIVERSAL",
            1,
            12000.0,
            None,
            "DELIVERED",
            0,
        ),
    )
    conn.commit()

    summary = get_health_summary(conn, inventory_date="2026-01-02")
    conn.close()

    expected_unit = 47 * 78 + 0.95 * 2.66 * 530
    expected_total = expected_unit * 12
    assert summary["inventory_cogs"] is not None
    assert abs(summary["inventory_cogs"]["total"] - expected_total) < 1.0

    status, payload = handle_request("/health/summary", "end_date=2026-01-15", db_path=str(db_path))
    assert status == 200
    assert "top_profit" in payload
