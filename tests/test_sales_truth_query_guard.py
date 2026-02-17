from __future__ import annotations

import sqlite3

import pytest

from core.db.sales_truth_query_guard import (
    install_sales_truth_query_guard,
    remove_sales_truth_query_guard,
)


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
