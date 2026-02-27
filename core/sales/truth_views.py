"""Build canonical sales truth views from staging sales tables."""

from __future__ import annotations

import sqlite3
from datetime import date

from core.config.business_params import DEFAULT_FX_RATES


def _table_exists(conn: sqlite3.Connection, name: str) -> bool:
    row = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
        (name,),
    ).fetchone()
    return row is not None


def _column_exists(conn: sqlite3.Connection, table: str, column: str) -> bool:
    rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    return any(row[1] == column for row in rows)


def _resolve_fx_rates(conn: sqlite3.Connection) -> tuple[float, float, float]:
    cny_kzt = float(DEFAULT_FX_RATES["cny_kzt"])
    usd_kzt = float(DEFAULT_FX_RATES["usd_kzt"])
    dlv_rate_usd_kg = float(DEFAULT_FX_RATES["dlv_rate_usd_kg"])

    if not _table_exists(conn, "dim_fx_rates"):
        return cny_kzt, usd_kzt, dlv_rate_usd_kg

    cols = {row[1] for row in conn.execute("PRAGMA table_info(dim_fx_rates)").fetchall()}
    required = {"effective_date", "cny_kzt", "usd_kzt", "dlv_rate_usd_kg"}
    if not required.issubset(cols):
        return cny_kzt, usd_kzt, dlv_rate_usd_kg

    today = date.today().isoformat()
    row = conn.execute(
        """
        SELECT cny_kzt, usd_kzt, dlv_rate_usd_kg
        FROM dim_fx_rates
        WHERE effective_date <= ?
        ORDER BY effective_date DESC
        LIMIT 1
        """,
        (today,),
    ).fetchone()
    if row is None:
        return cny_kzt, usd_kzt, dlv_rate_usd_kg

    return float(row[0]), float(row[1]), float(row[2])


def get_article_aliases_for_sku(
    conn: sqlite3.Connection,
    *,
    sku_key: str,
    store_code: str | None = None,
) -> list[str]:
    """Return known article aliases for a canonical SKU key."""
    if not _table_exists(conn, "dim_kaspi_article_map"):
        return []

    cols = {row[1] for row in conn.execute("PRAGMA table_info(dim_kaspi_article_map)").fetchall()}
    if "kaspi_article" not in cols or "sku_key" not in cols:
        return []

    where = ["COALESCE(active_flag, 1) = 1", "sku_key = ?"] if "active_flag" in cols else ["sku_key = ?"]
    params: list[object] = [sku_key]
    if store_code and "store_code" in cols:
        where.append("store_code = ?")
        params.append(store_code)

    rows = conn.execute(
        f"""
        SELECT DISTINCT kaspi_article
        FROM dim_kaspi_article_map
        WHERE {' AND '.join(where)}
        ORDER BY kaspi_article
        """,
        tuple(params),
    ).fetchall()
    return [str(row[0]) for row in rows if row[0]]


def ensure_sales_truth_views(conn: sqlite3.Connection) -> None:
    """
    Create canonical line/daily sales truth views.

    - sales_fact_v2 and fact_sales remain staging.
    - consumers must read only `view_sales_line_truth` and `view_sales_daily_truth`.
    - revenue/units policy: sales_fact_v2 is authoritative for dates >= MIN(v2.sale_date);
      fact_sales contributes only pre-v2 historical days.
    - COGS/profit policy: published COGS is valid only when full landed formula inputs
      (base_cost_cny + weight_kg + FX) are present.
    """
    has_sales_ref = _table_exists(conn, "fact_sales_external_ref")
    has_sales_v2 = _table_exists(conn, "sales_fact_v2")
    has_fact_sales = _table_exists(conn, "fact_sales")
    if not has_sales_ref and not has_sales_v2 and not has_fact_sales:
        raise RuntimeError(
            "Missing staging sales tables: fact_sales_external_ref, sales_fact_v2, fact_sales"
        )

    conn.execute("DROP VIEW IF EXISTS view_sales_daily_truth")
    conn.execute("DROP VIEW IF EXISTS view_sales_line_truth")

    cny_kzt, usd_kzt, dlv_rate_usd_kg = _resolve_fx_rates(conn)

    ref_select = None
    if has_sales_ref:
        ref_store = "store_code" if _column_exists(conn, "fact_sales_external_ref", "store_code") else "'UNKNOWN'"
        ref_size = "my_size" if _column_exists(conn, "fact_sales_external_ref", "my_size") else "''"
        ref_status = "status" if _column_exists(conn, "fact_sales_external_ref", "status") else "'DELIVERED'"
        ref_return = (
            "return_flag" if _column_exists(conn, "fact_sales_external_ref", "return_flag") else "0"
        )
        ref_net = (
            "net_rev_kzt"
            if _column_exists(conn, "fact_sales_external_ref", "net_rev_kzt")
            else ("gross_rev_kzt" if _column_exists(conn, "fact_sales_external_ref", "gross_rev_kzt") else "0")
        )
        ref_qty = (
            "quantity"
            if _column_exists(conn, "fact_sales_external_ref", "quantity")
            else ("units" if _column_exists(conn, "fact_sales_external_ref", "units") else "0")
        )
        ref_sale_date = (
            "sale_date"
            if _column_exists(conn, "fact_sales_external_ref", "sale_date")
            else ("order_date" if _column_exists(conn, "fact_sales_external_ref", "order_date") else "NULL")
        )
        ref_sku_key = "sku_key" if _column_exists(conn, "fact_sales_external_ref", "sku_key") else "''"
        ref_sku_id = "sku_id" if _column_exists(conn, "fact_sales_external_ref", "sku_id") else "''"
        ref_select = f"""
            SELECT
                CAST(order_id AS TEXT) AS order_id,
                date({ref_sale_date}) AS sale_date,
                CAST(COALESCE({ref_store}, 'UNKNOWN') AS TEXT) AS store_code,
                CAST(COALESCE({ref_sku_key}, '') AS TEXT) AS sku_key,
                CAST(COALESCE({ref_sku_id}, '') AS TEXT) AS sku_id,
                CAST(COALESCE({ref_size}, '') AS TEXT) AS my_size,
                CAST(COALESCE({ref_qty}, 0) AS REAL) AS units,
                CAST(COALESCE({ref_net}, 0) AS REAL) AS net_rev_kzt,
                NULL AS cogs_kzt,
                NULL AS profit_kzt,
                CAST(COALESCE({ref_status}, 'DELIVERED') AS TEXT) AS status,
                CAST(COALESCE({ref_return}, 0) AS INTEGER) AS return_flag,
                'fact_sales_external_ref' AS source_table
            FROM fact_sales_external_ref
            WHERE UPPER(COALESCE({ref_status}, 'DELIVERED')) IN ('DELIVERED', 'COMPLETED', 'ВЫДАН')
              AND COALESCE({ref_return}, 0) = 0
        """

    v2_select = None
    if has_sales_v2:
        v2_store = "store_code" if _column_exists(conn, "sales_fact_v2", "store_code") else "'UNIVERSAL'"
        v2_size = "my_size" if _column_exists(conn, "sales_fact_v2", "my_size") else "''"
        v2_status = "status" if _column_exists(conn, "sales_fact_v2", "status") else "NULL"
        v2_return = "return_flag" if _column_exists(conn, "sales_fact_v2", "return_flag") else "0"
        v2_profit = "profit" if _column_exists(conn, "sales_fact_v2", "profit") else "NULL"
        v2_net = "net_rev" if _column_exists(conn, "sales_fact_v2", "net_rev") else "0"
        v2_cogs = "cogs" if _column_exists(conn, "sales_fact_v2", "cogs") else "0"
        v2_qty = "quantity" if _column_exists(conn, "sales_fact_v2", "quantity") else "0"
        v2_order_date = "order_date" if _column_exists(conn, "sales_fact_v2", "order_date") else "NULL"
        v2_sku_id = "sku_id" if _column_exists(conn, "sales_fact_v2", "sku_id") else "''"
        v2_select = f"""
            SELECT
                CAST(order_id AS TEXT) AS order_id,
                date({v2_order_date}) AS sale_date,
                CAST(COALESCE({v2_store}, 'UNIVERSAL') AS TEXT) AS store_code,
                CAST(sku_key AS TEXT) AS sku_key,
                CAST({v2_sku_id} AS TEXT) AS sku_id,
                CAST(COALESCE({v2_size}, '') AS TEXT) AS my_size,
                CAST(COALESCE({v2_qty}, 0) AS REAL) AS units,
                CAST(COALESCE({v2_net}, 0) AS REAL) AS net_rev_kzt,
                CAST(COALESCE({v2_cogs}, 0) AS REAL) AS cogs_kzt,
                CAST(COALESCE({v2_profit}, COALESCE({v2_net}, 0) - COALESCE({v2_cogs}, 0)) AS REAL) AS profit_kzt,
                CAST(COALESCE({v2_status}, '') AS TEXT) AS status,
                CAST(COALESCE({v2_return}, 0) AS INTEGER) AS return_flag,
                'sales_fact_v2' AS source_table
            FROM sales_fact_v2
            WHERE UPPER(COALESCE({v2_status}, 'DELIVERED')) = 'DELIVERED'
              AND COALESCE({v2_return}, 0) = 0
        """

    fact_select = None
    if has_fact_sales:
        fs_store = "store_code" if _column_exists(conn, "fact_sales", "store_code") else "'UNIVERSAL'"
        fs_size = "my_size" if _column_exists(conn, "fact_sales", "my_size") else "''"
        fs_net = "line_net_rev" if _column_exists(conn, "fact_sales", "line_net_rev") else "0"
        fs_cogs = "cogs_line" if _column_exists(conn, "fact_sales", "cogs_line") else "0"
        fs_profit = "profit_line" if _column_exists(conn, "fact_sales", "profit_line") else "NULL"
        fs_qty = "quantity" if _column_exists(conn, "fact_sales", "quantity") else "0"
        fs_order_date = "order_date" if _column_exists(conn, "fact_sales", "order_date") else "NULL"
        fs_sku_id = "sku_id" if _column_exists(conn, "fact_sales", "sku_id") else "''"
        fact_select = """
            SELECT
                CAST(order_id AS TEXT) AS order_id,
                date({fs_order_date}) AS sale_date,
                CAST(COALESCE({fs_store}, 'UNIVERSAL') AS TEXT) AS store_code,
                CAST(sku_key AS TEXT) AS sku_key,
                CAST({fs_sku_id} AS TEXT) AS sku_id,
                CAST(COALESCE({fs_size}, '') AS TEXT) AS my_size,
                CAST(COALESCE({fs_qty}, 0) AS REAL) AS units,
                CAST(COALESCE({fs_net}, 0) AS REAL) AS net_rev_kzt,
                CAST(COALESCE({fs_cogs}, 0) AS REAL) AS cogs_kzt,
                CAST(COALESCE({fs_profit}, COALESCE({fs_net}, 0) - COALESCE({fs_cogs}, 0)) AS REAL) AS profit_kzt,
                'DELIVERED' AS status,
                0 AS return_flag,
                'fact_sales' AS source_table
            FROM fact_sales
        """.format(
            fs_order_date=fs_order_date,
            fs_store=fs_store,
            fs_sku_id=fs_sku_id,
            fs_size=fs_size,
            fs_qty=fs_qty,
            fs_net=fs_net,
            fs_cogs=fs_cogs,
            fs_profit=fs_profit,
        )

    ctes: list[str] = []
    if ref_select:
        ctes.append(f"sales_ref AS ({ref_select})")
    else:
        ctes.append(
            "sales_ref AS (SELECT NULL AS order_id, NULL AS sale_date, NULL AS store_code, NULL AS sku_key, "
            "NULL AS sku_id, NULL AS my_size, 0.0 AS units, 0.0 AS net_rev_kzt, NULL AS cogs_kzt, NULL AS profit_kzt, "
            "NULL AS status, 0 AS return_flag, NULL AS source_table WHERE 0)"
        )
    if v2_select:
        ctes.append(f"sales_v2 AS ({v2_select})")
    else:
        ctes.append(
            "sales_v2 AS (SELECT NULL AS order_id, NULL AS sale_date, NULL AS store_code, NULL AS sku_key, "
            "NULL AS sku_id, NULL AS my_size, 0.0 AS units, 0.0 AS net_rev_kzt, 0.0 AS cogs_kzt, 0.0 AS profit_kzt, "
            "NULL AS status, 0 AS return_flag, NULL AS source_table WHERE 0)"
        )
    if fact_select:
        ctes.append(f"sales_fact AS ({fact_select})")
    else:
        ctes.append(
            "sales_fact AS (SELECT NULL AS order_id, NULL AS sale_date, NULL AS store_code, NULL AS sku_key, "
            "NULL AS sku_id, NULL AS my_size, 0.0 AS units, 0.0 AS net_rev_kzt, 0.0 AS cogs_kzt, 0.0 AS profit_kzt, "
            "NULL AS status, 0 AS return_flag, NULL AS source_table WHERE 0)"
        )
    ctes.append(
        """
        ref_day_store AS (
            SELECT DISTINCT date(sale_date) AS sale_date, UPPER(COALESCE(store_code, '')) AS store_code
            FROM sales_ref
        )
        """
    )
    ctes.append(
        """
        v2_bounds AS (
            SELECT MIN(date(sale_date)) AS v2_min_sale_date
            FROM sales_v2
        )
        """
    )
    ctes.append(
        """
        base_lines AS (
            SELECT * FROM sales_ref
            UNION ALL
            SELECT sv2.*
            FROM sales_v2 sv2
            WHERE NOT EXISTS (
                SELECT 1
                FROM ref_day_store r
                WHERE date(r.sale_date) = date(sv2.sale_date)
                  AND UPPER(COALESCE(sv2.store_code, '')) = r.store_code
            )
            UNION ALL
            SELECT sf.*
            FROM sales_fact sf
            WHERE (
                (SELECT v2_min_sale_date FROM v2_bounds) IS NULL
                OR date(sf.sale_date) < date((SELECT v2_min_sale_date FROM v2_bounds))
            )
              AND NOT EXISTS (
                SELECT 1
                FROM ref_day_store r
                WHERE date(r.sale_date) = date(sf.sale_date)
                  AND UPPER(COALESCE(sf.store_code, '')) = r.store_code
            )
        )
        """
    )

    if _table_exists(conn, "dim_kaspi_article_map"):
        has_active_flag = _column_exists(conn, "dim_kaspi_article_map", "active_flag")
        if has_active_flag:
            sku_key_expr = (
                "COALESCE("
                "MAX(CASE WHEN COALESCE(active_flag, 1) = 1 THEN COALESCE(sku_key, '') END), "
                "MAX(COALESCE(sku_key, ''))"
                ") AS sku_key"
            )
            sku_id_expr = (
                "COALESCE("
                "MAX(CASE WHEN COALESCE(active_flag, 1) = 1 THEN COALESCE(sku_id, '') END), "
                "MAX(COALESCE(sku_id, ''))"
                ") AS sku_id"
            )
        else:
            sku_key_expr = "MAX(COALESCE(sku_key, '')) AS sku_key"
            sku_id_expr = "MAX(COALESCE(sku_id, '')) AS sku_id"
        ctes.append(
            f"""
            article_store_map AS (
                SELECT
                    UPPER(TRIM(COALESCE(kaspi_article, ''))) AS article_norm,
                    UPPER(TRIM(COALESCE(store_code, ''))) AS store_norm,
                    {sku_key_expr},
                    {sku_id_expr}
                FROM dim_kaspi_article_map
                GROUP BY 1, 2
            )
            """
        )
        ctes.append(
            """
            article_any_map AS (
                SELECT
                    article_norm,
                    MAX(COALESCE(sku_key, '')) AS sku_key,
                    MAX(COALESCE(sku_id, '')) AS sku_id
                FROM article_store_map
                GROUP BY 1
            )
            """
        )
    else:
        ctes.append(
            """
            article_store_map AS (
                SELECT '' AS article_norm, '' AS store_norm, '' AS sku_key, '' AS sku_id WHERE 0
            )
            """
        )
        ctes.append(
            """
            article_any_map AS (
                SELECT '' AS article_norm, '' AS sku_key, '' AS sku_id WHERE 0
            )
            """
        )

    ctes.append(
        """
        resolved_lines AS (
            SELECT
                b.order_id,
                b.sale_date,
                b.store_code,
                COALESCE(
                    NULLIF(am_key_store.sku_key, ''),
                    NULLIF(am_id_store.sku_key, ''),
                    NULLIF(am_key_any.sku_key, ''),
                    NULLIF(am_id_any.sku_key, ''),
                    b.sku_key
                ) AS canonical_sku_key,
                COALESCE(
                    NULLIF(am_key_store.sku_id, ''),
                    NULLIF(am_id_store.sku_id, ''),
                    NULLIF(am_key_any.sku_id, ''),
                    NULLIF(am_id_any.sku_id, ''),
                    b.sku_id
                ) AS canonical_sku_id,
                b.my_size,
                b.units,
                b.net_rev_kzt,
                b.cogs_kzt AS source_cogs_kzt,
                b.profit_kzt AS source_profit_kzt,
                b.source_table,
                b.sku_key AS source_sku_key,
                b.sku_id AS source_sku_id,
                b.units AS source_units,
                b.net_rev_kzt AS source_net_rev_kzt
            FROM base_lines b
            LEFT JOIN article_store_map am_key_store
              ON am_key_store.article_norm = UPPER(TRIM(COALESCE(b.sku_key, '')))
             AND am_key_store.store_norm = UPPER(TRIM(COALESCE(b.store_code, '')))
            LEFT JOIN article_store_map am_id_store
              ON am_id_store.article_norm = UPPER(TRIM(COALESCE(b.sku_id, '')))
             AND am_id_store.store_norm = UPPER(TRIM(COALESCE(b.store_code, '')))
            LEFT JOIN article_any_map am_key_any
              ON am_key_any.article_norm = UPPER(TRIM(COALESCE(b.sku_key, '')))
            LEFT JOIN article_any_map am_id_any
              ON am_id_any.article_norm = UPPER(TRIM(COALESCE(b.sku_id, '')))
        )
        """
    )

    has_dim_sku = _table_exists(conn, "dim_sku")
    has_base_cost = has_dim_sku and _column_exists(conn, "dim_sku", "base_cost_cny")
    has_weight = has_dim_sku and _column_exists(conn, "dim_sku", "weight_kg")

    if has_dim_sku and has_base_cost and has_weight:
        dim_join = "LEFT JOIN dim_sku ds ON ds.sku_key = rl.canonical_sku_key"
        base_expr = "CAST(ds.base_cost_cny AS REAL)"
        weight_expr = "CAST(ds.weight_kg AS REAL)"
    else:
        dim_join = ""
        base_expr = "NULL"
        weight_expr = "NULL"

    formula_unit_expr = (
        f"(({base_expr}) * {cny_kzt:.8f}) + "
        f"(({weight_expr}) * {usd_kzt:.8f} * {dlv_rate_usd_kg:.8f})"
    )
    formula_ready_expr = f"(({base_expr}) IS NOT NULL AND ({base_expr}) > 0 AND ({weight_expr}) IS NOT NULL AND ({weight_expr}) > 0 AND COALESCE(rl.units, 0) > 0)"

    cte_sql = ",\n".join(ctes)
    line_view_sql = f"""
        CREATE VIEW view_sales_line_truth AS
        WITH {cte_sql}
        SELECT
            rl.order_id,
            rl.sale_date,
            rl.store_code,
            rl.canonical_sku_key AS sku_key,
            rl.canonical_sku_id AS sku_id,
            rl.my_size,
            rl.units,
            rl.net_rev_kzt,
            CASE
                WHEN {formula_ready_expr}
                    THEN ROUND(({formula_unit_expr}) * rl.units, 2)
                ELSE NULL
            END AS cogs_kzt,
            CASE
                WHEN {formula_ready_expr}
                    THEN ROUND(rl.net_rev_kzt - ROUND(({formula_unit_expr}) * rl.units, 2), 2)
                ELSE NULL
            END AS profit_kzt,
            CASE
                WHEN {formula_ready_expr} THEN 'formula_full'
                ELSE 'unresolved'
            END AS cogs_source,
            rl.source_table,
            rl.source_sku_key,
            rl.source_sku_id,
            rl.source_units,
            rl.source_net_rev_kzt,
            rl.source_cogs_kzt,
            rl.source_profit_kzt
        FROM resolved_lines rl
        {dim_join}
    """
    conn.execute(line_view_sql)

    daily_view_sql = """
        CREATE VIEW view_sales_daily_truth AS
        SELECT
            sale_date,
            store_code,
            sku_key,
            SUM(COALESCE(units, 0)) AS units,
            SUM(COALESCE(net_rev_kzt, 0)) AS revenue_kzt,
            SUM(COALESCE(cogs_kzt, 0)) AS cogs_kzt,
            SUM(COALESCE(profit_kzt, 0)) AS profit_kzt,
            COUNT(*) AS line_count
        FROM view_sales_line_truth
        GROUP BY sale_date, store_code, sku_key
    """
    conn.execute(daily_view_sql)
