from __future__ import annotations

import sqlite3

import pytest

from core.db.sales_truth_query_guard import (
    install_sales_truth_query_guard,
    remove_sales_truth_query_guard,
)
from core.sales.truth_views import ensure_sales_truth_views


def test_runtime_guard_blocks_raw_sales_tables() -> None:
    conn = sqlite3.connect(":memory:")
    conn.execute("CREATE TABLE fact_sales (order_id TEXT)")
    conn.execute("INSERT INTO fact_sales(order_id) VALUES ('1')")

    install_sales_truth_query_guard(conn)

    with pytest.raises(sqlite3.DatabaseError):
        conn.execute("SELECT * FROM fact_sales").fetchall()


@pytest.mark.parametrize(
    "table_name",
    ["fact_sales", "sales_fact_v2", "fact_sales_daily", "fact_sales_daily_size"],
)
def test_runtime_guard_blocks_all_disallowed_tables(table_name: str) -> None:
    conn = sqlite3.connect(":memory:")
    conn.execute(f"CREATE TABLE {table_name} (id INTEGER)")
    conn.execute(f"INSERT INTO {table_name}(id) VALUES (1)")

    install_sales_truth_query_guard(conn)

    with pytest.raises(sqlite3.DatabaseError):
        conn.execute(f"SELECT * FROM {table_name}").fetchall()


def test_runtime_guard_allows_published_truth_views() -> None:
    conn = sqlite3.connect(":memory:")
    conn.execute("CREATE TABLE view_sales_line_truth (order_id TEXT)")
    conn.execute("INSERT INTO view_sales_line_truth(order_id) VALUES ('1')")
    conn.execute("CREATE TABLE view_sales_daily_truth (sale_date TEXT)")
    conn.execute("INSERT INTO view_sales_daily_truth(sale_date) VALUES ('2026-02-17')")

    install_sales_truth_query_guard(conn)

    rows_line = conn.execute("SELECT * FROM view_sales_line_truth").fetchall()
    rows_daily = conn.execute("SELECT * FROM view_sales_daily_truth").fetchall()

    assert rows_line == [("1",)]
    assert rows_daily == [("2026-02-17",)]


def test_runtime_guard_allows_generated_truth_view_internals() -> None:
    conn = sqlite3.connect(":memory:")
    conn.execute(
        """
        CREATE TABLE sales_fact_v2 (
            order_id TEXT,
            order_date TEXT,
            store_code TEXT,
            sku_key TEXT,
            sku_id TEXT,
            my_size TEXT,
            quantity REAL,
            net_rev REAL,
            cogs REAL,
            profit REAL,
            status TEXT,
            return_flag INTEGER
        )
        """
    )
    conn.execute(
        """
        INSERT INTO sales_fact_v2 (
            order_id, order_date, store_code, sku_key, sku_id, my_size,
            quantity, net_rev, cogs, profit, status, return_flag
        ) VALUES ('1', '2026-02-17', 'UNIVERSAL', 'SKU_A', 'SKU_A_L', 'L', 1, 1000, 400, 600, 'DELIVERED', 0)
        """
    )
    ensure_sales_truth_views(conn)
    install_sales_truth_query_guard(conn)

    rows = conn.execute(
        "SELECT order_id, sku_key FROM view_sales_line_truth"
    ).fetchall()
    assert rows == [("1", "SKU_A")]

    with pytest.raises(sqlite3.DatabaseError):
        conn.execute("SELECT order_id FROM sales_fact_v2").fetchall()


def test_guard_can_be_removed() -> None:
    conn = sqlite3.connect(":memory:")
    conn.execute("CREATE TABLE fact_sales (order_id TEXT)")
    conn.execute("INSERT INTO fact_sales(order_id) VALUES ('1')")

    install_sales_truth_query_guard(conn)
    with pytest.raises(sqlite3.DatabaseError):
        conn.execute("SELECT * FROM fact_sales").fetchall()

    remove_sales_truth_query_guard(conn)
    rows = conn.execute("SELECT * FROM fact_sales").fetchall()
    assert rows == [("1",)]
