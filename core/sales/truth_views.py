"""Build canonical sales truth views from staging sales tables."""

from __future__ import annotations

import sqlite3


def _table_exists(conn: sqlite3.Connection, name: str) -> bool:
    row = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
        (name,),
    ).fetchone()
    return row is not None


def _column_exists(conn: sqlite3.Connection, table: str, column: str) -> bool:
    rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    return any(row[1] == column for row in rows)


def ensure_sales_truth_views(conn: sqlite3.Connection) -> None:
    """
    Create canonical line/daily sales truth views.

    - sales_fact_v2 and fact_sales remain staging.
    - consumers must read only `view_sales_line_truth` and `view_sales_daily_truth`.
    """
    has_sales_v2 = _table_exists(conn, "sales_fact_v2")
    has_fact_sales = _table_exists(conn, "fact_sales")
    if not has_sales_v2 and not has_fact_sales:
        raise RuntimeError("Missing staging sales tables: sales_fact_v2 and fact_sales")

    conn.execute("DROP VIEW IF EXISTS view_sales_daily_truth")
    conn.execute("DROP VIEW IF EXISTS view_sales_line_truth")

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
        base_lines AS (
            SELECT * FROM sales_v2
            UNION ALL
            SELECT sf.*
            FROM sales_fact sf
            WHERE NOT EXISTS (
                SELECT 1
                FROM sales_v2 s2
                WHERE COALESCE(s2.order_id, '') = COALESCE(sf.order_id, '')
                  AND COALESCE(s2.store_code, '') = COALESCE(sf.store_code, '')
                  AND COALESCE(s2.sku_id, '') = COALESCE(sf.sku_id, '')
            )
        )
        """
    )

    if has_fact_sales:
        ctes.append(
            """
            fact_sales_lookup AS (
                SELECT
                    CAST(order_id AS TEXT) AS order_id,
                    CAST(COALESCE(store_code, 'UNIVERSAL') AS TEXT) AS store_code,
                    CAST(sku_id AS TEXT) AS sku_id,
                    MAX(CAST(COALESCE(cogs_line, 0) AS REAL)) AS cogs_line
                FROM fact_sales
                GROUP BY order_id, store_code, sku_id
            )
            """
        )
    else:
        ctes.append(
            """
            fact_sales_lookup AS (
                SELECT NULL AS order_id, NULL AS store_code, NULL AS sku_id, 0.0 AS cogs_line
                WHERE 0
            )
            """
        )

    has_dim_sku = _table_exists(conn, "dim_sku") and _column_exists(conn, "dim_sku", "cogs_kzt")
    if has_dim_sku:
        dim_join = "LEFT JOIN dim_sku ds ON ds.sku_key = b.sku_key"
        dim_expr = "CAST(COALESCE(ds.cogs_kzt, 0) AS REAL)"
    else:
        dim_join = ""
        dim_expr = "0.0"

    cte_sql = ",\n".join(ctes)
    line_view_sql = f"""
        CREATE VIEW view_sales_line_truth AS
        WITH {cte_sql}
        SELECT
            b.order_id,
            b.sale_date,
            b.store_code,
            b.sku_key,
            b.sku_id,
            b.my_size,
            b.units,
            b.net_rev_kzt,
            CASE
                WHEN b.cogs_kzt > 0 THEN b.cogs_kzt
                WHEN fsl.cogs_line > 0 THEN fsl.cogs_line
                WHEN {dim_expr} > 0 AND b.units > 0 THEN ROUND({dim_expr} * b.units, 2)
                ELSE 0.0
            END AS cogs_kzt,
            ROUND(
                b.net_rev_kzt - CASE
                    WHEN b.cogs_kzt > 0 THEN b.cogs_kzt
                    WHEN fsl.cogs_line > 0 THEN fsl.cogs_line
                    WHEN {dim_expr} > 0 AND b.units > 0 THEN ROUND({dim_expr} * b.units, 2)
                    ELSE 0.0
                END,
                2
            ) AS profit_kzt,
            CASE
                WHEN b.cogs_kzt > 0 THEN 'line_cogs'
                WHEN fsl.cogs_line > 0 THEN 'fact_sales_fallback'
                WHEN {dim_expr} > 0 AND b.units > 0 THEN 'dim_sku_fallback'
                ELSE 'unresolved'
            END AS cogs_source,
            b.source_table
        FROM base_lines b
        LEFT JOIN fact_sales_lookup fsl
          ON COALESCE(fsl.order_id, '') = COALESCE(b.order_id, '')
         AND COALESCE(fsl.store_code, '') = COALESCE(b.store_code, '')
         AND COALESCE(fsl.sku_id, '') = COALESCE(b.sku_id, '')
        {dim_join}
    """
    conn.execute(line_view_sql)

    daily_view_sql = """
        CREATE VIEW view_sales_daily_truth AS
        SELECT
            sale_date,
            store_code,
            sku_key,
            SUM(units) AS units,
            SUM(net_rev_kzt) AS revenue_kzt,
            SUM(cogs_kzt) AS cogs_kzt,
            SUM(profit_kzt) AS profit_kzt,
            COUNT(*) AS line_count
        FROM view_sales_line_truth
        GROUP BY sale_date, store_code, sku_key
    """
    conn.execute(daily_view_sql)
