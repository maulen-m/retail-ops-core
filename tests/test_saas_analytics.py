import sqlite3
from pathlib import Path

from core.analytics.api import handle_request
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
    assert delivery_fee_unit == 856

    # VAT schedule should apply 4% from 2026-01-01
    expected_net_rev_unit = (12000 * (1 - 0.125) - 856) * 0.96
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
        "CREATE TABLE abc_view_cache (SKU_key TEXT, Status TEXT, D_30 REAL, ROP REAL, ROIC_pct REAL)"
    )
    conn.execute(
        "INSERT INTO abc_view_cache (SKU_key, Status, D_30, ROP, ROIC_pct) VALUES (?,?,?,?,?)",
        ("LINE52", "ACTIVE", 12.0, 30.0, 0.22),
    )
    conn.commit()
    conn.close()

    status, payload = handle_request("/kpis/sku_share", "metric=revenue&end_date=2026-01-15", db_path=str(db_path))
    assert status == 200
    assert payload["items"]

    status, payload = handle_request("/health/summary", "end_date=2026-01-15", db_path=str(db_path))
    assert status == 200
    assert "top_profit" in payload

    status, payload = handle_request("/catalog", "query=PRINT&limit=10&offset=0", db_path=str(db_path))
    assert status == 200
    assert payload["total"] == 1
    assert payload["items"][0]["SKU_key"] == "LINE52"
