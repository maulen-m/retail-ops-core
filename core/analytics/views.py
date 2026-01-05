"""SQLite views for analytics queries."""
from __future__ import annotations

import sqlite3
from typing import Iterable


SALES_ENRICHED_VIEW = """
CREATE VIEW v_sales_enriched AS
WITH day_units AS (
    SELECT date(order_date) AS order_date,
           sku_key,
           SUM(quantity) AS units_day
    FROM sales_fact_v2
    GROUP BY date(order_date), sku_key
)
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
    base.ads_daily_spend_kzt,
    CASE
        WHEN base.units_day > 0 THEN base.ads_daily_spend_kzt / base.units_day
        ELSE 0
    END AS ads_cost_unit,
    ((base.sell_price_kzt * (1 - base.commission_rate) - base.delivery_fee_unit) * (1 - base.vat_rate)
        - CASE
            WHEN base.units_day > 0 THEN base.ads_daily_spend_kzt / base.units_day
            ELSE 0
          END
    ) AS net_rev_unit,
    ((base.sell_price_kzt * (1 - base.commission_rate) - base.delivery_fee_unit) * (1 - base.vat_rate)
        - CASE
            WHEN base.units_day > 0 THEN base.ads_daily_spend_kzt / base.units_day
            ELSE 0
          END
    ) * base.quantity AS line_net_rev,
    (base.base_cost_cny * base.fx_cny_kzt + base.weight_kg * base.fx_usd_kzt * base.fx_dlv_rate_usd_kg) AS cogs_unit,
    (base.base_cost_cny * base.fx_cny_kzt + base.weight_kg * base.fx_usd_kzt * base.fx_dlv_rate_usd_kg) * base.quantity AS cogs_line,
    (((base.sell_price_kzt * (1 - base.commission_rate) - base.delivery_fee_unit) * (1 - base.vat_rate)
        - CASE
            WHEN base.units_day > 0 THEN base.ads_daily_spend_kzt / base.units_day
            ELSE 0
          END
        ) - (base.base_cost_cny * base.fx_cny_kzt + base.weight_kg * base.fx_usd_kzt * base.fx_dlv_rate_usd_kg)
    ) AS profit_unit,
    (((base.sell_price_kzt * (1 - base.commission_rate) - base.delivery_fee_unit) * (1 - base.vat_rate)
        - CASE
            WHEN base.units_day > 0 THEN base.ads_daily_spend_kzt / base.units_day
            ELSE 0
          END
        ) - (base.base_cost_cny * base.fx_cny_kzt + base.weight_kg * base.fx_usd_kzt * base.fx_dlv_rate_usd_kg)
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
        day_units.units_day,
        COALESCE(ads.daily_spend_kzt, 0) AS ads_daily_spend_kzt,
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
            (
                SELECT fee_blend
                FROM dim_ksp_dlv_fee
                WHERE sf.sell_price_kzt BETWEEN order_value_min AND order_value_max
                  AND COALESCE(sku.weight_kg, 0) BETWEEN weight_min_kg AND weight_max_kg
                ORDER BY weight_max_kg ASC
                LIMIT 1
            ),
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
    LEFT JOIN day_units
        ON day_units.order_date = date(sf.order_date)
       AND day_units.sku_key = sf.sku_key
    LEFT JOIN dim_ads_spend ads
        ON ads.sku_key = sf.sku_key
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


ABC_VIEW = """
CREATE VIEW v_abc_view AS
WITH latest_metrics AS (
    SELECT *
    FROM fact_sku_metrics
    WHERE computed_at = (SELECT MAX(computed_at) FROM fact_sku_metrics)
),
params AS (
    SELECT
        COALESCE((SELECT param_value FROM dim_params WHERE param_key = 'R_days' ORDER BY updated_at DESC LIMIT 1), 10) AS R,
        COALESCE((SELECT param_value FROM dim_params WHERE param_key = 'L_days' ORDER BY updated_at DESC LIMIT 1), 21) AS L,
        COALESCE((SELECT param_value FROM dim_params WHERE param_key = 'B_days' ORDER BY updated_at DESC LIMIT 1), 14) AS B,
        COALESCE((SELECT param_value FROM dim_params WHERE param_key = 'z_factor' ORDER BY updated_at DESC LIMIT 1), 1.65) AS z,
        COALESCE((SELECT param_value FROM dim_params WHERE param_key = 'TV_mix_floor' ORDER BY updated_at DESC LIMIT 1), 0.23) AS TV,
        COALESCE((SELECT param_value FROM dim_params WHERE param_key = 'cargo_rate_cl' ORDER BY updated_at DESC LIMIT 1), 2.66) AS cargo_rate
),
fx AS (
    SELECT cny_kzt, usd_kzt, dlv_rate_usd_kg
    FROM dim_fx_rates
    ORDER BY effective_date DESC
    LIMIT 1
)
SELECT
    m.sku_key AS SKU_key,
    sku.product_type AS Product_Type,
    m.current_stock AS Current_stock,
    m.inbound_stock AS Inbound_units,
    m.total_stock AS Total_stock,
    (sku.base_cost_cny * fx.cny_kzt) AS Base_cost_kzt,
    (sku.base_cost_cny * fx.cny_kzt + sku.weight_kg * fx.usd_kzt * fx.dlv_rate_usd_kg) AS COGS_unit,
    m.current_stock * (sku.base_cost_cny * fx.cny_kzt + sku.weight_kg * fx.usd_kzt * fx.dlv_rate_usd_kg) AS Stock_COGS,
    m.inbound_stock * (sku.base_cost_cny * fx.cny_kzt + sku.weight_kg * fx.usd_kzt * fx.dlv_rate_usd_kg) AS Inbound_COGS,
    m.total_stock * (sku.base_cost_cny * fx.cny_kzt + sku.weight_kg * fx.usd_kzt * fx.dlv_rate_usd_kg) AS Total_stock_COGS,
    m.d30 AS D_30,
    m.sigma AS Sigma_MAD,
    params.R AS R,
    params.L AS L,
    params.B AS B,
    params.z AS z,
    params.TV AS TV,
    m.ss_demand AS SS_demand,
    m.ss_floor AS SS_floor,
    m.ss_mix AS SS_mix,
    m.ss_total AS SS_total,
    m.rop AS ROP,
    m.target_stock AS T_post,
    m.avg_price AS Price,
    (m.avg_cogs + (
        m.avg_profit - CASE
            WHEN m.d30 > 0 THEN COALESCE(ads.daily_spend_kzt, 0) / m.d30
            ELSE 0
        END
    )) AS NetRev_unit,
    (m.avg_profit - CASE
        WHEN m.d30 > 0 THEN COALESCE(ads.daily_spend_kzt, 0) / m.d30
        ELSE 0
    END) AS Profit_unit,
    ((m.avg_profit - CASE
        WHEN m.d30 > 0 THEN COALESCE(ads.daily_spend_kzt, 0) / m.d30
        ELSE 0
    END) * m.d30 * 30) AS Monthly_Profit,
    m.k_avg AS K_avg,
    CASE
        WHEN m.k_avg > 0 THEN ((m.avg_profit - CASE
            WHEN m.d30 > 0 THEN COALESCE(ads.daily_spend_kzt, 0) / m.d30
            ELSE 0
        END) * m.d30 * 30) / m.k_avg
        ELSE NULL
    END AS ROIC_pct,
    m.suggested_order_qty AS Suggested_Order_Qty,
    m.days_with_sales AS Days_with_sales,
    m.total_units_30d AS Units_30d,
    m.status AS Status,
    life.lifecycle_status AS Lifecycle_flag,
    life.status_reason AS Notes,
    NULL AS OPEX_total,
    ads.daily_spend_kzt AS Ads_cost_day
FROM latest_metrics m
LEFT JOIN dim_sku sku ON sku.sku_key = m.sku_key
LEFT JOIN dim_sku_lifecycle life ON life.sku_key = m.sku_key
LEFT JOIN dim_ads_spend ads ON ads.sku_key = m.sku_key
CROSS JOIN params
CROSS JOIN fx;
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
        """
        CREATE TABLE IF NOT EXISTS dim_ads_spend (
            sku_key TEXT PRIMARY KEY,
            daily_spend_kzt REAL NOT NULL DEFAULT 0,
            updated_at TEXT DEFAULT (datetime('now')),
            updated_by TEXT DEFAULT 'SYSTEM'
        );

        CREATE TABLE IF NOT EXISTS dim_ksp_dlv_fee (
            order_value_min REAL NOT NULL,
            order_value_max REAL NOT NULL,
            weight_min_kg REAL NOT NULL,
            weight_max_kg REAL NOT NULL,
            fee_city REAL,
            fee_kazakhstan REAL,
            fee_express REAL,
            fee_blend REAL NOT NULL,
            updated_at TEXT DEFAULT (datetime('now'))
        );
        """
    )

    conn.executescript(
        "\n".join(
            [
                "DROP VIEW IF EXISTS v_sales_monthly;",
                "DROP VIEW IF EXISTS v_sales_daily;",
                "DROP VIEW IF EXISTS v_sales_enriched;",
                "DROP VIEW IF EXISTS v_abc_view;",
                SALES_ENRICHED_VIEW,
                SALES_DAILY_VIEW,
                SALES_MONTHLY_VIEW,
                ABC_VIEW,
            ]
        )
    )
    conn.commit()
