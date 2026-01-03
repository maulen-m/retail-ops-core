"""SQLite views for analytics queries."""
from __future__ import annotations

import sqlite3
from typing import Iterable


SALES_ENRICHED_VIEW = """
CREATE VIEW v_sales_enriched AS
SELECT
    base.sale_id,
    base.order_id,
    base.order_date,
    base.sku_key,
    base.sku_id,
    base.my_size,
    base.kaspi_offer_name,
    base.store_code,
    base.quantity,
    base.sell_price_kzt,
    base.status,
    base.return_flag,
    base.product_type,
    base.base_cost_cny,
    base.weight_kg,
    base.fx_cny_kzt,
    base.fx_usd_kzt,
    base.fx_dlv_rate_usd_kg,
    base.fx_effective_date,
    base.commission_rate,
    base.vat_rate,
    base.delivery_fee_unit,
    ((base.sell_price_kzt * (1 - base.commission_rate) - base.delivery_fee_unit) * (1 - base.vat_rate)) AS net_rev_unit,
    ((base.sell_price_kzt * (1 - base.commission_rate) - base.delivery_fee_unit) * (1 - base.vat_rate)) * base.quantity AS line_net_rev,
    (base.base_cost_cny * base.fx_cny_kzt + base.weight_kg * base.fx_usd_kzt * base.fx_dlv_rate_usd_kg) AS cogs_unit,
    (base.base_cost_cny * base.fx_cny_kzt + base.weight_kg * base.fx_usd_kzt * base.fx_dlv_rate_usd_kg) * base.quantity AS cogs_line,
    (((base.sell_price_kzt * (1 - base.commission_rate) - base.delivery_fee_unit) * (1 - base.vat_rate))
        - (base.base_cost_cny * base.fx_cny_kzt + base.weight_kg * base.fx_usd_kzt * base.fx_dlv_rate_usd_kg)
    ) AS profit_unit,
    (((base.sell_price_kzt * (1 - base.commission_rate) - base.delivery_fee_unit) * (1 - base.vat_rate))
        - (base.base_cost_cny * base.fx_cny_kzt + base.weight_kg * base.fx_usd_kzt * base.fx_dlv_rate_usd_kg)
    ) * base.quantity AS profit_line
FROM (
    SELECT
        sf.sale_id,
        sf.order_id,
        date(sf.order_date) AS order_date,
        sf.sku_key,
        sf.sku_id,
        sf.my_size,
        sf.kaspi_offer_name,
        sf.store_code,
        sf.quantity,
        sf.sell_price_kzt,
        sf.status,
        sf.return_flag,
        sku.product_type,
        sku.base_cost_cny,
        sku.weight_kg,
        (
            SELECT cny_kzt
            FROM dim_fx_rates
            WHERE effective_date <= date(sf.order_date)
            ORDER BY effective_date DESC
            LIMIT 1
        ) AS fx_cny_kzt,
        (
            SELECT usd_kzt
            FROM dim_fx_rates
            WHERE effective_date <= date(sf.order_date)
            ORDER BY effective_date DESC
            LIMIT 1
        ) AS fx_usd_kzt,
        (
            SELECT dlv_rate_usd_kg
            FROM dim_fx_rates
            WHERE effective_date <= date(sf.order_date)
            ORDER BY effective_date DESC
            LIMIT 1
        ) AS fx_dlv_rate_usd_kg,
        (
            SELECT effective_date
            FROM dim_fx_rates
            WHERE effective_date <= date(sf.order_date)
            ORDER BY effective_date DESC
            LIMIT 1
        ) AS fx_effective_date,
        COALESCE(
            (
                SELECT param_value
                FROM dim_params
                WHERE param_key = 'commission'
                  AND (product_type IS NULL OR product_type = '')
                ORDER BY updated_at DESC
                LIMIT 1
            ),
            0.125
        ) AS commission_rate,
        CASE
            WHEN date(sf.order_date) >= '2026-01-01' THEN 0.04
            ELSE COALESCE(
                (
                    SELECT param_value
                    FROM dim_params
                    WHERE param_key = 'VAT_rate'
                      AND (product_type IS NULL OR product_type = '')
                    ORDER BY updated_at DESC
                    LIMIT 1
                ),
                0.03
            )
        END AS vat_rate,
        COALESCE(
            sf.delivery_fee,
            CASE
                WHEN sf.sell_price_kzt <= 4999 THEN 0
                WHEN sf.sell_price_kzt <= 14999 THEN 856
                ELSE 1259
            END
        ) AS delivery_fee_unit
    FROM sales_fact_v2 sf
    LEFT JOIN dim_sku sku
        ON sku.sku_key = sf.sku_key
) base;
"""


SALES_DAILY_VIEW = """
CREATE VIEW v_sales_daily AS
SELECT
    order_date AS sale_date,
    store_code,
    sku_key,
    SUM(quantity) AS units,
    SUM(line_net_rev) AS revenue,
    SUM(cogs_line) AS cogs,
    SUM(profit_line) AS profit
FROM v_sales_enriched
GROUP BY order_date, store_code, sku_key;
"""


SALES_MONTHLY_VIEW = """
CREATE VIEW v_sales_monthly AS
SELECT
    strftime('%Y-%m-01', order_date) AS month_start,
    store_code,
    sku_key,
    SUM(quantity) AS units,
    SUM(line_net_rev) AS revenue,
    SUM(cogs_line) AS cogs,
    SUM(profit_line) AS profit
FROM v_sales_enriched
GROUP BY strftime('%Y-%m-01', order_date), store_code, sku_key;
"""


REQUIRED_TABLES = (
    "sales_fact_v2",
    "dim_sku",
    "dim_fx_rates",
    "dim_params",
)


def _table_exists(conn: sqlite3.Connection, table_name: str) -> bool:
    row = conn.execute(
        "SELECT name FROM sqlite_master WHERE type IN ('table', 'view') AND name = ?",
        (table_name,),
    ).fetchone()
    return row is not None


def _missing_tables(conn: sqlite3.Connection, tables: Iterable[str]) -> list[str]:
    return [name for name in tables if not _table_exists(conn, name)]


def ensure_sales_views(conn: sqlite3.Connection) -> None:
    """Ensure analytics views exist and are up to date."""
    missing = _missing_tables(conn, REQUIRED_TABLES)
    if missing:
        raise RuntimeError(
            "Missing required tables for analytics views: " + ", ".join(missing)
        )

    conn.executescript(
        "\n".join(
            [
                "DROP VIEW IF EXISTS v_sales_monthly;",
                "DROP VIEW IF EXISTS v_sales_daily;",
                "DROP VIEW IF EXISTS v_sales_enriched;",
                SALES_ENRICHED_VIEW,
                SALES_DAILY_VIEW,
                SALES_MONTHLY_VIEW,
            ]
        )
    )
    conn.commit()
