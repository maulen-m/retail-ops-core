"""Build canonical sales truth views from staging sales tables."""

from __future__ import annotations

import sqlite3
from datetime import date

from core.config.business_params import get_supplier_fx_rates_from_conn
from core.sales.publication_binding import publication_binding_schema_ready


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
    rates = get_supplier_fx_rates_from_conn(conn, date.today())
    return (
        float(rates.cny_kzt),
        float(rates.usd_kzt),
        float(rates.dlv_rate_usd_kg),
    )


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
    has_sales_v2 = _table_exists(conn, "sales_fact_v2")
    has_fact_sales = _table_exists(conn, "fact_sales")
    has_sales_ref = _table_exists(conn, "fact_sales_external_ref")
    has_workbook_anchor = _table_exists(conn, "fact_sales_workbook_anchor")
    has_workbook_anchor_quarantine = _table_exists(conn, "fact_sales_workbook_anchor_quarantine")
    has_product_identity_quarantine = _table_exists(
        conn,
        "fact_order_entry_product_identity_quarantine",
    )
    has_header_only_source_gap_quarantine = _table_exists(
        conn,
        "fact_order_entry_header_only_source_gap_quarantine",
    )
    has_owner_cogs_override = _table_exists(conn, "fact_sales_owner_cogs_override")
    binding_source_columns = {
        "sale_id",
        "order_id",
        "order_date",
        "store_code",
        "sku_key",
        "sku_id",
        "my_size",
        "quantity",
        "sell_price_kzt",
        "delivery_fee",
        "cogs",
        "net_rev",
        "profit",
        "status",
        "return_flag",
        "source_file",
        "source_entry_id",
        "kaspi_article",
        "line_identity_key",
    }
    has_publication_binding = bool(
        has_sales_v2
        and has_workbook_anchor
        and publication_binding_schema_ready(conn)
        and binding_source_columns.issubset(
            {str(row[1]) for row in conn.execute("PRAGMA table_info(sales_fact_v2)")}
        )
    )
    if not has_sales_v2 and not has_fact_sales:
        raise RuntimeError(
            "Missing internal staging sales tables: sales_fact_v2, fact_sales"
        )

    conn.execute("DROP VIEW IF EXISTS view_sales_daily_reference")
    conn.execute("DROP VIEW IF EXISTS view_sales_line_reference")
    conn.execute("DROP VIEW IF EXISTS view_sales_daily_truth")
    conn.execute("DROP VIEW IF EXISTS view_sales_line_truth")
    conn.execute("DROP VIEW IF EXISTS view_sales_publication_binding_validation")
    conn.execute("DROP VIEW IF EXISTS view_sales_line_truth_unbound")

    cny_kzt, usd_kzt, dlv_rate_usd_kg = _resolve_fx_rates(conn)

    ref_select = None
    if has_sales_ref:
        ref_store = "store_code" if _column_exists(conn, "fact_sales_external_ref", "store_code") else "'UNKNOWN'"
        ref_size = "my_size" if _column_exists(conn, "fact_sales_external_ref", "my_size") else "''"
        ref_status = "status" if _column_exists(conn, "fact_sales_external_ref", "status") else "'DELIVERED'"
        ref_return = "return_flag" if _column_exists(conn, "fact_sales_external_ref", "return_flag") else "0"
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
                'fact_sales_external_ref' AS source_table,
                CAST(rowid AS TEXT) AS source_row_id,
                NULL AS source_entry_id,
                NULL AS source_line_identity_key
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
        v2_row_id = "sale_id" if _column_exists(conn, "sales_fact_v2", "sale_id") else "rowid"
        v2_entry_id = (
            "source_entry_id"
            if _column_exists(conn, "sales_fact_v2", "source_entry_id")
            else "NULL"
        )
        v2_line_key = (
            "line_identity_key"
            if _column_exists(conn, "sales_fact_v2", "line_identity_key")
            else "NULL"
        )
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
                'sales_fact_v2' AS source_table,
                CAST({v2_row_id} AS TEXT) AS source_row_id,
                CAST({v2_entry_id} AS TEXT) AS source_entry_id,
                CAST({v2_line_key} AS TEXT) AS source_line_identity_key
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
        fs_row_id = "id" if _column_exists(conn, "fact_sales", "id") else "rowid"
        fs_entry_id = (
            "source_entry_id"
            if _column_exists(conn, "fact_sales", "source_entry_id")
            else "NULL"
        )
        fs_line_key = (
            "line_identity_key"
            if _column_exists(conn, "fact_sales", "line_identity_key")
            else "NULL"
        )
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
                'fact_sales' AS source_table,
                CAST({fs_row_id} AS TEXT) AS source_row_id,
                CAST({fs_entry_id} AS TEXT) AS source_entry_id,
                CAST({fs_line_key} AS TEXT) AS source_line_identity_key
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
            fs_row_id=fs_row_id,
            fs_entry_id=fs_entry_id,
            fs_line_key=fs_line_key,
        )

    ctes: list[str] = []
    if v2_select:
        ctes.append(f"sales_v2 AS ({v2_select})")
    else:
        ctes.append(
            "sales_v2 AS (SELECT NULL AS order_id, NULL AS sale_date, NULL AS store_code, NULL AS sku_key, "
            "NULL AS sku_id, NULL AS my_size, 0.0 AS units, 0.0 AS net_rev_kzt, 0.0 AS cogs_kzt, 0.0 AS profit_kzt, "
            "NULL AS status, 0 AS return_flag, NULL AS source_table, NULL AS source_row_id, "
            "NULL AS source_entry_id, NULL AS source_line_identity_key WHERE 0)"
        )
    if fact_select:
        ctes.append(f"sales_fact AS ({fact_select})")
    else:
        ctes.append(
            "sales_fact AS (SELECT NULL AS order_id, NULL AS sale_date, NULL AS store_code, NULL AS sku_key, "
            "NULL AS sku_id, NULL AS my_size, 0.0 AS units, 0.0 AS net_rev_kzt, 0.0 AS cogs_kzt, 0.0 AS profit_kzt, "
            "NULL AS status, 0 AS return_flag, NULL AS source_table, NULL AS source_row_id, "
            "NULL AS source_entry_id, NULL AS source_line_identity_key WHERE 0)"
        )
    if has_sales_v2:
        v2_bounds_order_date = "order_date" if _column_exists(conn, "sales_fact_v2", "order_date") else "sale_date"
        ctes.append(
            f"""
            v2_bounds AS (
                SELECT MIN(date({v2_bounds_order_date})) AS v2_min_sale_date
                FROM sales_fact_v2
            )
            """
        )
    else:
        ctes.append(
            """
            v2_bounds AS (
                SELECT NULL AS v2_min_sale_date
            )
            """
        )
    ctes.append(
        """
        v2_order_keys AS (
            SELECT DISTINCT
                CAST(order_id AS TEXT) AS order_id,
                UPPER(TRIM(COALESCE(store_code, 'UNIVERSAL'))) AS store_code
            FROM sales_v2
        )
        """
    )
    if has_sales_v2:
        any_v2_store = "store_code" if _column_exists(conn, "sales_fact_v2", "store_code") else "'UNIVERSAL'"
        ctes.append(
            f"""
            v2_any_order_keys AS (
                SELECT DISTINCT
                    CAST(order_id AS TEXT) AS order_id,
                    UPPER(TRIM(COALESCE({any_v2_store}, 'UNIVERSAL'))) AS store_code
                FROM sales_fact_v2
            )
            """
        )
    else:
        ctes.append(
            """
            v2_any_order_keys AS (
                SELECT NULL AS order_id, NULL AS store_code WHERE 0
            )
            """
        )
    if has_workbook_anchor:
        wa_keys_store = (
            "store_code"
            if _column_exists(conn, "fact_sales_workbook_anchor", "store_code")
            else "'UNKNOWN'"
        )
        ctes.append(
            f"""
            workbook_anchor_keys AS (
                SELECT DISTINCT
                    CAST(order_id AS TEXT) AS order_id,
                    UPPER(TRIM(COALESCE({wa_keys_store}, 'UNKNOWN'))) AS store_code
                FROM fact_sales_workbook_anchor
            )
            """
        )
    else:
        ctes.append(
            """
            workbook_anchor_keys AS (
                SELECT NULL AS order_id, NULL AS store_code WHERE 0
            )
            """
        )
    ctes.append(
        """
        internal_order_totals AS (
            SELECT
                order_id,
                UPPER(COALESCE(store_code, '')) AS store_code,
                SUM(COALESCE(units, 0)) AS order_units_total
            FROM base_lines
            GROUP BY 1, 2
        )
        """
    )
    if has_workbook_anchor:
        wa_store = (
            "store_code"
            if _column_exists(conn, "fact_sales_workbook_anchor", "store_code")
            else "'UNKNOWN'"
        )
        wa_sale_date = (
            "sale_date"
            if _column_exists(conn, "fact_sales_workbook_anchor", "sale_date")
            else ("order_date" if _column_exists(conn, "fact_sales_workbook_anchor", "order_date") else "NULL")
        )
        wa_qty = (
            "quantity"
            if _column_exists(conn, "fact_sales_workbook_anchor", "quantity")
            else ("units" if _column_exists(conn, "fact_sales_workbook_anchor", "units") else "0")
        )
        wa_net = (
            "net_rev_kzt"
            if _column_exists(conn, "fact_sales_workbook_anchor", "net_rev_kzt")
            else ("gross_rev_kzt" if _column_exists(conn, "fact_sales_workbook_anchor", "gross_rev_kzt") else "0")
        )
        ctes.append(
            f"""
            workbook_anchor AS (
                SELECT
                    CAST(order_id AS TEXT) AS order_id,
                    UPPER(COALESCE({wa_store}, 'UNKNOWN')) AS store_code,
                    MAX(date({wa_sale_date})) AS anchor_sale_date,
                    SUM(COALESCE({wa_qty}, 0)) AS anchor_units,
                    SUM(COALESCE({wa_net}, 0)) AS anchor_net_rev_kzt
                FROM fact_sales_workbook_anchor
                GROUP BY 1, 2
            )
            """
        )
    else:
        ctes.append(
            """
            workbook_anchor AS (
                SELECT
                    NULL AS order_id,
                    NULL AS store_code,
                    NULL AS anchor_sale_date,
                    0.0 AS anchor_units,
                    0.0 AS anchor_net_rev_kzt
                WHERE 0
            )
            """
        )
    if has_workbook_anchor_quarantine:
        waq_store = (
            "store_code"
            if _column_exists(conn, "fact_sales_workbook_anchor_quarantine", "store_code")
            else "'UNKNOWN'"
        )
        ctes.append(
            f"""
            workbook_anchor_quarantine AS (
                SELECT DISTINCT
                    CAST(order_id AS TEXT) AS order_id,
                    UPPER(COALESCE({waq_store}, 'UNKNOWN')) AS store_code
                FROM fact_sales_workbook_anchor_quarantine
            )
            """
        )
    else:
        ctes.append(
            """
            workbook_anchor_quarantine AS (
                SELECT
                    NULL AS order_id,
                    NULL AS store_code
                WHERE 0
            )
            """
        )
    if has_product_identity_quarantine:
        piq_store = (
            "store_code"
            if _column_exists(conn, "fact_order_entry_product_identity_quarantine", "store_code")
            else "'UNKNOWN'"
        )
        piq_active_clause = (
            "COALESCE(active_flag, 1) = 1"
            if _column_exists(conn, "fact_order_entry_product_identity_quarantine", "active_flag")
            else "1 = 1"
        )
        piq_publication_clause = (
            "COALESCE(publication_exclusion_required, 1) = 1"
            if _column_exists(
                conn,
                "fact_order_entry_product_identity_quarantine",
                "publication_exclusion_required",
            )
            else "1 = 1"
        )
        ctes.append(
            f"""
            product_identity_quarantine AS (
                SELECT DISTINCT
                    CAST(order_id AS TEXT) AS order_id,
                    UPPER(COALESCE({piq_store}, 'UNKNOWN')) AS store_code
                FROM fact_order_entry_product_identity_quarantine
                WHERE {piq_active_clause}
                  AND {piq_publication_clause}
            )
            """
        )
    else:
        ctes.append(
            """
            product_identity_quarantine AS (
                SELECT
                    NULL AS order_id,
                    NULL AS store_code
                WHERE 0
            )
            """
        )
    if has_header_only_source_gap_quarantine:
        hosg_store = (
            "store_code"
            if _column_exists(
                conn,
                "fact_order_entry_header_only_source_gap_quarantine",
                "store_code",
            )
            else "'UNKNOWN'"
        )
        hosg_active_clause = (
            "COALESCE(active_flag, 1) = 1"
            if _column_exists(
                conn,
                "fact_order_entry_header_only_source_gap_quarantine",
                "active_flag",
            )
            else "1 = 1"
        )
        hosg_publication_clause = (
            "COALESCE(publication_exclusion_required, 1) = 1"
            if _column_exists(
                conn,
                "fact_order_entry_header_only_source_gap_quarantine",
                "publication_exclusion_required",
            )
            else "1 = 1"
        )
        ctes.append(
            f"""
            header_only_source_gap_quarantine AS (
                SELECT DISTINCT
                    CAST(order_id AS TEXT) AS order_id,
                    UPPER(COALESCE({hosg_store}, 'UNKNOWN')) AS store_code
                FROM fact_order_entry_header_only_source_gap_quarantine
                WHERE {hosg_active_clause}
                  AND {hosg_publication_clause}
            )
            """
        )
    else:
        ctes.append(
            """
            header_only_source_gap_quarantine AS (
                SELECT
                    NULL AS order_id,
                    NULL AS store_code
                WHERE 0
            )
            """
        )
    lifecycle_exclusion_selects: list[str] = []
    if _table_exists(conn, "fact_orders_kaspi") and _column_exists(conn, "fact_orders_kaspi", "internal_status"):
        lifecycle_store = (
            "store_code"
            if _column_exists(conn, "fact_orders_kaspi", "store_code")
            else "'UNIVERSAL'"
        )
        lifecycle_exclusion_selects.append(
            f"""
            SELECT DISTINCT
                CAST(order_id AS TEXT) AS order_id,
                UPPER(TRIM(COALESCE({lifecycle_store}, 'UNIVERSAL'))) AS store_code
            FROM fact_orders_kaspi
            WHERE UPPER(TRIM(COALESCE(internal_status, ''))) IN ('CANCELLED', 'RETURNED')
            """
        )
    if (
        _table_exists(conn, "order_status_event")
        and _column_exists(conn, "order_status_event", "order_id")
        and _column_exists(conn, "order_status_event", "stage_code")
    ):
        lifecycle_event_store = (
            "store_code"
            if _column_exists(conn, "order_status_event", "store_code")
            else "'UNIVERSAL'"
        )
        lifecycle_exclusion_selects.append(
            f"""
            SELECT DISTINCT
                CAST(order_id AS TEXT) AS order_id,
                UPPER(TRIM(COALESCE({lifecycle_event_store}, 'UNIVERSAL'))) AS store_code
            FROM order_status_event
            WHERE UPPER(TRIM(COALESCE(stage_code, ''))) IN ('CANCELLED', 'RETURNED')
            """
        )
    lifecycle_exclusion_sql = (
        "\nUNION\n".join(lifecycle_exclusion_selects)
        if lifecycle_exclusion_selects
        else "SELECT NULL AS order_id, NULL AS store_code WHERE 0"
    )
    ctes.append(
        f"""
        lifecycle_excluded_order_keys AS (
            {lifecycle_exclusion_sql}
        )
        """
    )
    ctes.append(
        """
        base_lines AS (
            SELECT sv.*
            FROM sales_v2 sv
            LEFT JOIN lifecycle_excluded_order_keys lex
              ON lex.order_id = sv.order_id
             AND lex.store_code = UPPER(TRIM(COALESCE(sv.store_code, 'UNIVERSAL')))
            LEFT JOIN product_identity_quarantine piq
              ON piq.order_id = sv.order_id
             AND piq.store_code = UPPER(TRIM(COALESCE(sv.store_code, 'UNIVERSAL')))
            LEFT JOIN header_only_source_gap_quarantine hosg
              ON hosg.order_id = sv.order_id
             AND hosg.store_code = UPPER(TRIM(COALESCE(sv.store_code, 'UNIVERSAL')))
            WHERE lex.order_id IS NULL
              AND piq.order_id IS NULL
              AND hosg.order_id IS NULL
            UNION ALL
            SELECT sf.*
            FROM sales_fact sf
            LEFT JOIN v2_any_order_keys v2a
              ON v2a.order_id = sf.order_id
             AND v2a.store_code = UPPER(TRIM(COALESCE(sf.store_code, 'UNIVERSAL')))
            LEFT JOIN workbook_anchor_keys wak
              ON wak.order_id = sf.order_id
             AND wak.store_code = UPPER(TRIM(COALESCE(sf.store_code, 'UNIVERSAL')))
            LEFT JOIN lifecycle_excluded_order_keys lex
              ON lex.order_id = sf.order_id
             AND lex.store_code = UPPER(TRIM(COALESCE(sf.store_code, 'UNIVERSAL')))
            LEFT JOIN product_identity_quarantine piq
              ON piq.order_id = sf.order_id
             AND piq.store_code = UPPER(TRIM(COALESCE(sf.store_code, 'UNIVERSAL')))
            LEFT JOIN header_only_source_gap_quarantine hosg
              ON hosg.order_id = sf.order_id
             AND hosg.store_code = UPPER(TRIM(COALESCE(sf.store_code, 'UNIVERSAL')))
            WHERE (
                (SELECT v2_min_sale_date FROM v2_bounds) IS NULL
                OR date(sf.sale_date) < date((SELECT v2_min_sale_date FROM v2_bounds))
                OR (wak.order_id IS NOT NULL AND v2a.order_id IS NULL)
            )
              AND lex.order_id IS NULL
              AND piq.order_id IS NULL
              AND hosg.order_id IS NULL
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
                COALESCE(wa.anchor_sale_date, b.sale_date) AS sale_date,
                b.sale_date AS source_sale_date,
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
                CASE
                    WHEN COALESCE(wa.anchor_units, 0) > 0
                     AND COALESCE(iot.order_units_total, 0) > 0
                        THEN CAST(wa.anchor_units AS REAL) * CAST(COALESCE(b.units, 0) AS REAL) / CAST(iot.order_units_total AS REAL)
                    ELSE b.units
                END AS units,
                CASE
                    WHEN COALESCE(wa.anchor_net_rev_kzt, 0) > 0
                     AND COALESCE(iot.order_units_total, 0) > 0
                        THEN CAST(wa.anchor_net_rev_kzt AS REAL) * CAST(COALESCE(b.units, 0) AS REAL) / CAST(iot.order_units_total AS REAL)
                    ELSE b.net_rev_kzt
                END AS net_rev_kzt,
                b.cogs_kzt AS source_cogs_kzt,
                b.profit_kzt AS source_profit_kzt,
                b.source_table,
                b.source_row_id,
                b.source_entry_id,
                b.source_line_identity_key,
                b.sku_key AS source_sku_key,
                b.sku_id AS source_sku_id,
                b.units AS source_units,
                b.net_rev_kzt AS source_net_rev_kzt
            FROM base_lines b
            LEFT JOIN internal_order_totals iot
              ON iot.order_id = b.order_id
             AND iot.store_code = UPPER(TRIM(COALESCE(b.store_code, '')))
            LEFT JOIN workbook_anchor wa
              ON wa.order_id = b.order_id
             AND wa.store_code = UPPER(TRIM(COALESCE(b.store_code, '')))
            LEFT JOIN workbook_anchor_quarantine waq
              ON waq.order_id = b.order_id
             AND waq.store_code = UPPER(TRIM(COALESCE(b.store_code, '')))
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
            WHERE waq.order_id IS NULL
        )
        """
    )

    if has_owner_cogs_override:
        owner_cogs_cols = {
            row[1] for row in conn.execute("PRAGMA table_info(fact_sales_owner_cogs_override)").fetchall()
        }
        required_owner_cogs_cols = {"order_id", "store_code", "sku_key", "sku_id", "unit_cogs_kzt"}
        if required_owner_cogs_cols.issubset(owner_cogs_cols):
            owner_cogs_source_expr = (
                "COALESCE(cogs_source, 'owner_row_override')"
                if "cogs_source" in owner_cogs_cols
                else "'owner_row_override'"
            )
            owner_cogs_active_clause = (
                "COALESCE(active_flag, 1) = 1"
                if "active_flag" in owner_cogs_cols
                else "1 = 1"
            )
            ctes.append(
                f"""
                owner_cogs_override AS (
                    SELECT
                        CAST(order_id AS TEXT) AS order_id,
                        UPPER(TRIM(COALESCE(store_code, 'UNIVERSAL'))) AS store_code,
                        CAST(COALESCE(sku_key, '') AS TEXT) AS sku_key,
                        CAST(COALESCE(sku_id, '') AS TEXT) AS sku_id,
                        CAST(unit_cogs_kzt AS REAL) AS unit_cogs_kzt,
                        CAST({owner_cogs_source_expr} AS TEXT) AS cogs_source
                    FROM fact_sales_owner_cogs_override
                    WHERE {owner_cogs_active_clause}
                      AND CAST(unit_cogs_kzt AS REAL) > 0
                )
                """
            )
        else:
            ctes.append(
                """
                owner_cogs_override AS (
                    SELECT
                        NULL AS order_id,
                        NULL AS store_code,
                        NULL AS sku_key,
                        NULL AS sku_id,
                        NULL AS unit_cogs_kzt,
                        NULL AS cogs_source
                    WHERE 0
                )
                """
            )
    else:
        ctes.append(
            """
            owner_cogs_override AS (
                SELECT
                    NULL AS order_id,
                    NULL AS store_code,
                    NULL AS sku_key,
                    NULL AS sku_id,
                    NULL AS unit_cogs_kzt,
                    NULL AS cogs_source
                WHERE 0
            )
            """
        )

    has_dim_sku = _table_exists(conn, "dim_sku")
    has_base_cost = has_dim_sku and _column_exists(conn, "dim_sku", "base_cost_cny")
    has_weight = has_dim_sku and _column_exists(conn, "dim_sku", "weight_kg")
    has_stored_cogs = has_dim_sku and _column_exists(conn, "dim_sku", "cogs_kzt")

    if has_dim_sku and (has_base_cost or has_weight or has_stored_cogs):
        dim_join = "LEFT JOIN dim_sku ds ON ds.sku_key = rl.canonical_sku_key"
        base_expr = "CAST(ds.base_cost_cny AS REAL)" if has_base_cost else "NULL"
        weight_expr = "CAST(ds.weight_kg AS REAL)" if has_weight else "NULL"
        stored_cogs_expr = "CAST(ds.cogs_kzt AS REAL)" if has_stored_cogs else "NULL"
    else:
        dim_join = ""
        base_expr = "NULL"
        weight_expr = "NULL"
        stored_cogs_expr = "NULL"

    formula_unit_expr = (
        f"(({base_expr}) * {cny_kzt:.8f}) + "
        f"(({weight_expr}) * {usd_kzt:.8f} * {dlv_rate_usd_kg:.8f})"
    )
    formula_ready_expr = f"(({base_expr}) IS NOT NULL AND ({base_expr}) > 0 AND ({weight_expr}) IS NOT NULL AND ({weight_expr}) > 0 AND COALESCE(rl.units, 0) > 0)"
    stored_cogs_ready_expr = f"(({stored_cogs_expr}) IS NOT NULL AND ({stored_cogs_expr}) > 0 AND COALESCE(rl.units, 0) > 0)"
    owner_cogs_ready_expr = "(oco.unit_cogs_kzt IS NOT NULL AND oco.unit_cogs_kzt > 0 AND COALESCE(rl.units, 0) > 0)"

    cte_sql = ",\n".join(ctes)
    line_view_sql = f"""
        CREATE VIEW view_sales_line_truth_unbound AS
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
                WHEN {stored_cogs_ready_expr}
                    THEN ROUND(({stored_cogs_expr}) * rl.units, 2)
                WHEN {owner_cogs_ready_expr}
                    THEN ROUND(oco.unit_cogs_kzt * rl.units, 2)
                ELSE NULL
            END AS cogs_kzt,
            CASE
                WHEN {formula_ready_expr}
                    THEN ROUND(rl.net_rev_kzt - ROUND(({formula_unit_expr}) * rl.units, 2), 2)
                WHEN {stored_cogs_ready_expr}
                    THEN ROUND(rl.net_rev_kzt - ROUND(({stored_cogs_expr}) * rl.units, 2), 2)
                WHEN {owner_cogs_ready_expr}
                    THEN ROUND(rl.net_rev_kzt - ROUND(oco.unit_cogs_kzt * rl.units, 2), 2)
                ELSE NULL
            END AS profit_kzt,
            CASE
                WHEN {formula_ready_expr} THEN 'formula_full'
                WHEN {stored_cogs_ready_expr} THEN 'dim_sku_fallback'
                WHEN {owner_cogs_ready_expr} THEN COALESCE(oco.cogs_source, 'owner_row_override')
                ELSE 'unresolved'
            END AS cogs_source,
            rl.source_table,
            rl.source_sku_key,
            rl.source_sku_id,
            rl.source_units,
            rl.source_net_rev_kzt,
            rl.source_cogs_kzt,
            rl.source_profit_kzt,
            rl.source_sale_date,
            rl.source_row_id,
            rl.source_entry_id,
            rl.source_line_identity_key,
            'UNBOUND' AS publication_binding_status,
            0 AS publication_provisional_flag
        FROM resolved_lines rl
        {dim_join}
        LEFT JOIN owner_cogs_override oco
          ON oco.order_id = rl.order_id
         AND oco.store_code = UPPER(TRIM(COALESCE(rl.store_code, 'UNIVERSAL')))
         AND oco.sku_key = rl.canonical_sku_key
         AND oco.sku_id = rl.canonical_sku_id
    """
    conn.execute(line_view_sql)

    if has_publication_binding:
        binding_validation_sql = """
            CREATE VIEW view_sales_publication_binding_validation AS
            WITH active_counts AS (
                SELECT
                    CAST(order_id AS TEXT) AS order_id,
                    UPPER(TRIM(store_code)) AS store_code,
                    COUNT(*) AS active_header_count
                FROM fact_sales_publication_binding_header
                WHERE active_flag = 1
                GROUP BY 1, 2
            ),
            binding_checks AS (
                SELECT
                    h.*,
                    COALESCE(ac.active_header_count, 0) AS active_header_count,
                    (
                        SELECT COUNT(*)
                        FROM fact_sales_workbook_anchor a
                        WHERE CAST(a.order_id AS TEXT) = CAST(h.order_id AS TEXT)
                          AND UPPER(TRIM(a.store_code)) = UPPER(TRIM(h.store_code))
                    ) AS anchor_row_count,
                    (
                        SELECT COUNT(*)
                        FROM fact_sales_workbook_anchor a
                        WHERE CAST(a.order_id AS TEXT) = CAST(h.order_id AS TEXT)
                          AND UPPER(TRIM(a.store_code)) = UPPER(TRIM(h.store_code))
                          AND date(a.sale_date) = date(h.anchor_sale_date)
                          AND ABS(CAST(a.quantity AS REAL) - CAST(h.anchor_quantity AS REAL)) <= 0.0001
                          AND ABS(CAST(a.net_rev_kzt AS REAL) - CAST(h.anchor_net_rev_kzt AS REAL)) <= 0.01
                          AND ABS(CAST(a.total_price_kzt AS REAL) - CAST(h.anchor_total_price_kzt AS REAL)) <= 0.01
                          AND COALESCE(a.source_file, '') = COALESCE(h.anchor_source_file, '')
                          AND COALESCE(a.updated_at, '') = COALESCE(h.anchor_updated_at, '')
                    ) AS matching_anchor_row_count,
                    (
                        SELECT COUNT(*)
                        FROM fact_sales_publication_binding_line l
                        WHERE l.binding_id = h.binding_id
                    ) AS binding_line_count,
                    (
                        SELECT COUNT(*)
                        FROM fact_sales_publication_binding_line l
                        JOIN sales_fact_v2 s ON s.sale_id = l.source_sale_id
                        WHERE l.binding_id = h.binding_id
                          AND l.source_table = 'sales_fact_v2'
                          AND CAST(s.order_id AS TEXT) = l.source_order_id
                          AND UPPER(TRIM(COALESCE(s.store_code, 'UNIVERSAL'))) = UPPER(TRIM(l.source_store_code))
                          AND date(s.order_date) = date(l.source_order_date)
                          AND COALESCE(s.sku_key, '') = l.source_sku_key
                          AND COALESCE(s.sku_id, '') = l.source_sku_id
                          AND COALESCE(s.my_size, '') = l.source_my_size
                          AND ABS(CAST(s.quantity AS REAL) - CAST(l.source_quantity AS REAL)) <= 0.0001
                          AND ABS(CAST(s.sell_price_kzt AS REAL) - CAST(l.source_sell_price_kzt AS REAL)) <= 0.01
                          AND ABS(CAST(s.delivery_fee AS REAL) - CAST(l.source_delivery_fee AS REAL)) <= 0.01
                          AND ((s.cogs IS NULL AND l.source_cogs_kzt IS NULL)
                               OR ABS(CAST(s.cogs AS REAL) - CAST(l.source_cogs_kzt AS REAL)) <= 0.01)
                          AND ABS(CAST(s.net_rev AS REAL) - CAST(l.source_net_rev_kzt AS REAL)) <= 0.01
                          AND ((s.profit IS NULL AND l.source_profit_kzt IS NULL)
                               OR ABS(CAST(s.profit AS REAL) - CAST(l.source_profit_kzt AS REAL)) <= 0.01)
                          AND UPPER(TRIM(COALESCE(s.status, ''))) = UPPER(TRIM(l.source_status))
                          AND COALESCE(s.return_flag, 0) = l.source_return_flag
                          AND COALESCE(s.source_file, '') = COALESCE(l.source_file, '')
                          AND COALESCE(s.source_entry_id, '') = l.source_entry_id
                          AND COALESCE(s.kaspi_article, '') = COALESCE(l.source_kaspi_article, '')
                          AND COALESCE(s.line_identity_key, '') = l.line_identity_key
                    ) AS matching_source_line_count,
                    (
                        SELECT COUNT(*)
                        FROM fact_sales_publication_binding_line l
                        JOIN view_sales_line_truth_unbound u
                          ON u.source_table = l.source_table
                         AND CAST(u.source_row_id AS TEXT) = CAST(l.source_sale_id AS TEXT)
                        WHERE l.binding_id = h.binding_id
                          AND CAST(u.order_id AS TEXT) = l.source_order_id
                          AND UPPER(TRIM(COALESCE(u.store_code, 'UNIVERSAL'))) = UPPER(TRIM(l.source_store_code))
                          AND date(u.source_sale_date) = date(l.source_order_date)
                          AND COALESCE(u.source_entry_id, '') = l.source_entry_id
                          AND COALESCE(u.source_line_identity_key, '') = l.line_identity_key
                          AND COALESCE(u.source_sku_key, '') = l.source_sku_key
                          AND COALESCE(u.source_sku_id, '') = l.source_sku_id
                          AND COALESCE(u.my_size, '') = l.source_my_size
                          AND ABS(CAST(u.source_units AS REAL) - CAST(l.source_quantity AS REAL)) <= 0.0001
                          AND ABS(CAST(u.source_net_rev_kzt AS REAL) - CAST(l.source_net_rev_kzt AS REAL)) <= 0.01
                          AND date(u.sale_date) = date(l.unbound_sale_date)
                          AND ABS(CAST(u.units AS REAL) - CAST(l.unbound_units AS REAL)) <= 0.0001
                          AND ABS(CAST(u.net_rev_kzt AS REAL) - CAST(l.unbound_net_rev_kzt AS REAL)) <= 0.01
                          AND date(l.publication_sale_date) = date(h.publication_effective_date)
                          AND ABS(CAST(l.publication_units AS REAL) - CAST(l.source_quantity AS REAL)) <= 0.0001
                          AND ABS(CAST(l.publication_net_rev_kzt AS REAL) - CAST(l.source_net_rev_kzt AS REAL)) <= 0.01
                    ) AS matching_unbound_line_count
                FROM fact_sales_publication_binding_header h
                LEFT JOIN active_counts ac
                  ON ac.order_id = CAST(h.order_id AS TEXT)
                 AND ac.store_code = UPPER(TRIM(h.store_code))
                WHERE h.active_flag = 1
            )
            SELECT
                binding_id,
                CAST(order_id AS TEXT) AS order_id,
                UPPER(TRIM(store_code)) AS store_code,
                active_flag,
                provisional_flag,
                publication_effective_date,
                expected_line_count,
                active_header_count,
                anchor_row_count,
                matching_anchor_row_count,
                binding_line_count,
                matching_source_line_count,
                matching_unbound_line_count,
                CASE
                    WHEN binding_status <> 'VALID' THEN 'HEADER_NOT_VALID'
                    WHEN active_header_count <> 1 THEN 'ACTIVE_HEADER_COUNT_MISMATCH'
                    WHEN provisional_flag <> 0 THEN 'PROVISIONAL_BINDING_FORBIDDEN'
                    WHEN terminal_date_semantics <> 'STATUS_CHANGE_TIMESTAMP_PROVEN' THEN 'TERMINAL_DATE_NOT_PROVEN'
                    WHEN external_evidence_validated <> 1 THEN 'EXTERNAL_EVIDENCE_NOT_VALIDATED'
                    WHEN anchor_row_count <> 1 OR matching_anchor_row_count <> 1 THEN 'ANCHOR_PREIMAGE_MISMATCH'
                    WHEN binding_line_count <> expected_line_count THEN 'BINDING_LINE_COUNT_MISMATCH'
                    WHEN matching_source_line_count <> expected_line_count THEN 'SOURCE_PREIMAGE_MISMATCH'
                    WHEN matching_unbound_line_count <> expected_line_count THEN 'UNBOUND_PREIMAGE_MISMATCH'
                    ELSE 'VALID_ACTIVE'
                END AS validation_status,
                CASE
                    WHEN binding_status = 'VALID'
                     AND active_header_count = 1
                     AND provisional_flag = 0
                     AND terminal_date_semantics = 'STATUS_CHANGE_TIMESTAMP_PROVEN'
                     AND external_evidence_validated = 1
                     AND anchor_row_count = 1
                     AND matching_anchor_row_count = 1
                     AND binding_line_count = expected_line_count
                     AND matching_source_line_count = expected_line_count
                     AND matching_unbound_line_count = expected_line_count
                    THEN 1 ELSE 0
                END AS publication_binding_usable
            FROM binding_checks
        """
    else:
        binding_validation_sql = """
            CREATE VIEW view_sales_publication_binding_validation AS
            SELECT
                NULL AS binding_id,
                NULL AS order_id,
                NULL AS store_code,
                0 AS active_flag,
                0 AS provisional_flag,
                NULL AS publication_effective_date,
                0 AS expected_line_count,
                0 AS active_header_count,
                0 AS anchor_row_count,
                0 AS matching_anchor_row_count,
                0 AS binding_line_count,
                0 AS matching_source_line_count,
                0 AS matching_unbound_line_count,
                NULL AS validation_status,
                0 AS publication_binding_usable
            WHERE 0
        """
    conn.execute(binding_validation_sql)

    if has_publication_binding:
        bound_line_join = """
            LEFT JOIN fact_sales_publication_binding_line pbl
              ON pbl.binding_id = pbv.binding_id
             AND pbl.source_table = u.source_table
             AND CAST(pbl.source_sale_id AS TEXT) = CAST(u.source_row_id AS TEXT)
        """
    else:
        bound_line_join = """
            LEFT JOIN (
                SELECT NULL AS binding_id, NULL AS source_table, NULL AS source_sale_id,
                       NULL AS publication_sale_date, NULL AS publication_units,
                       NULL AS publication_net_rev_kzt
                WHERE 0
            ) pbl ON 1 = 0
        """

    canonical_line_sql = f"""
        CREATE VIEW view_sales_line_truth AS
        SELECT
            u.order_id,
            CASE WHEN pbv.publication_binding_usable = 1
                 THEN date(pbl.publication_sale_date) ELSE u.sale_date END AS sale_date,
            u.store_code,
            u.sku_key,
            u.sku_id,
            u.my_size,
            CASE WHEN pbv.publication_binding_usable = 1
                 THEN CAST(pbl.publication_units AS REAL) ELSE u.units END AS units,
            CASE WHEN pbv.publication_binding_usable = 1
                 THEN CAST(pbl.publication_net_rev_kzt AS REAL) ELSE u.net_rev_kzt END AS net_rev_kzt,
            u.cogs_kzt,
            CASE
                WHEN u.cogs_kzt IS NULL THEN NULL
                WHEN pbv.publication_binding_usable = 1
                    THEN ROUND(CAST(pbl.publication_net_rev_kzt AS REAL) - u.cogs_kzt, 2)
                ELSE u.profit_kzt
            END AS profit_kzt,
            u.cogs_source,
            u.source_table,
            u.source_sku_key,
            u.source_sku_id,
            u.source_units,
            u.source_net_rev_kzt,
            u.source_cogs_kzt,
            u.source_profit_kzt,
            u.source_sale_date,
            u.source_row_id,
            u.source_entry_id,
            u.source_line_identity_key,
            CASE
                WHEN pbv.binding_id IS NULL THEN 'UNBOUND'
                WHEN pbv.publication_binding_usable = 1 THEN 'VALID_ACTIVE'
                ELSE 'INVALID_ACTIVE:' || COALESCE(pbv.validation_status, 'UNKNOWN')
            END AS publication_binding_status,
            COALESCE(pbv.provisional_flag, 0) AS publication_provisional_flag
        FROM view_sales_line_truth_unbound u
        LEFT JOIN view_sales_publication_binding_validation pbv
          ON pbv.order_id = CAST(u.order_id AS TEXT)
         AND pbv.store_code = UPPER(TRIM(COALESCE(u.store_code, 'UNIVERSAL')))
        {bound_line_join}
    """
    conn.execute(canonical_line_sql)

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
            COUNT(*) AS line_count,
            CASE WHEN COUNT(DISTINCT publication_binding_status) = 1
                 THEN MAX(publication_binding_status) ELSE 'MIXED' END AS publication_binding_status,
            MAX(COALESCE(publication_provisional_flag, 0)) AS publication_provisional_flag
        FROM view_sales_line_truth
        GROUP BY sale_date, store_code, sku_key
    """
    conn.execute(daily_view_sql)

    if ref_select:
        ref_ctes: list[str] = [f"sales_ref AS ({ref_select})"]
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
            ref_ctes.append(
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
            ref_ctes.append(
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
            ref_ctes.append(
                """
                article_store_map AS (
                    SELECT '' AS article_norm, '' AS store_norm, '' AS sku_key, '' AS sku_id WHERE 0
                )
                """
            )
            ref_ctes.append(
                """
                article_any_map AS (
                    SELECT '' AS article_norm, '' AS sku_key, '' AS sku_id WHERE 0
                )
                """
            )
        ref_ctes.append(
            """
            resolved_ref_lines AS (
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
                FROM sales_ref b
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
        ref_cte_sql = ",\n".join(ref_ctes)
        line_ref_sql = f"""
            CREATE VIEW view_sales_line_reference AS
            WITH {ref_cte_sql}
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
                    WHEN {stored_cogs_ready_expr}
                        THEN ROUND(({stored_cogs_expr}) * rl.units, 2)
                    ELSE NULL
                END AS cogs_kzt,
                CASE
                    WHEN {formula_ready_expr}
                        THEN ROUND(rl.net_rev_kzt - ROUND(({formula_unit_expr}) * rl.units, 2), 2)
                    WHEN {stored_cogs_ready_expr}
                        THEN ROUND(rl.net_rev_kzt - ROUND(({stored_cogs_expr}) * rl.units, 2), 2)
                    ELSE NULL
                END AS profit_kzt,
                CASE
                    WHEN {formula_ready_expr} THEN 'formula_full'
                    WHEN {stored_cogs_ready_expr} THEN 'dim_sku_fallback'
                    ELSE 'unresolved'
                END AS cogs_source,
                rl.source_table,
                rl.source_sku_key,
                rl.source_sku_id,
                rl.source_units,
                rl.source_net_rev_kzt,
                rl.source_cogs_kzt,
                rl.source_profit_kzt
            FROM resolved_ref_lines rl
            {dim_join}
        """
        conn.execute(line_ref_sql)
    else:
        conn.execute(
            """
            CREATE VIEW view_sales_line_reference AS
            SELECT
                CAST(NULL AS TEXT) AS order_id,
                CAST(NULL AS TEXT) AS sale_date,
                CAST(NULL AS TEXT) AS store_code,
                CAST(NULL AS TEXT) AS sku_key,
                CAST(NULL AS TEXT) AS sku_id,
                CAST(NULL AS TEXT) AS my_size,
                CAST(NULL AS REAL) AS units,
                CAST(NULL AS REAL) AS net_rev_kzt,
                CAST(NULL AS REAL) AS cogs_kzt,
                CAST(NULL AS REAL) AS profit_kzt,
                CAST(NULL AS TEXT) AS cogs_source,
                CAST(NULL AS TEXT) AS source_table,
                CAST(NULL AS TEXT) AS source_sku_key,
                CAST(NULL AS TEXT) AS source_sku_id,
                CAST(NULL AS REAL) AS source_units,
                CAST(NULL AS REAL) AS source_net_rev_kzt,
                CAST(NULL AS REAL) AS source_cogs_kzt,
                CAST(NULL AS REAL) AS source_profit_kzt
            WHERE 0
            """
        )

    daily_ref_sql = """
        CREATE VIEW view_sales_daily_reference AS
        SELECT
            sale_date,
            store_code,
            sku_key,
            SUM(COALESCE(units, 0)) AS units,
            SUM(COALESCE(net_rev_kzt, 0)) AS revenue_kzt,
            SUM(COALESCE(cogs_kzt, 0)) AS cogs_kzt,
            SUM(COALESCE(profit_kzt, 0)) AS profit_kzt,
            COUNT(*) AS line_count
        FROM view_sales_line_reference
        GROUP BY sale_date, store_code, sku_key
    """
    conn.execute(daily_ref_sql)
