from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from core.sales.truth_views import ensure_sales_truth_views
from scripts.apply_owner_approved_beli_child_cogs_rows import run


def _seed_db(path: Path) -> None:
    conn = sqlite3.connect(path)
    conn.executescript(
        """
        CREATE TABLE sales_fact_v2 (
            order_id TEXT,
            order_date TEXT,
            sku_key TEXT,
            sku_id TEXT,
            my_size TEXT,
            store_code TEXT,
            quantity REAL,
            net_rev REAL,
            cogs REAL,
            profit REAL,
            status TEXT,
            return_flag INTEGER
        );
        CREATE TABLE dim_sku (
            sku_key TEXT PRIMARY KEY,
            base_cost_cny REAL,
            weight_kg REAL,
            cogs_kzt REAL
        );
        INSERT INTO dim_sku (sku_key, base_cost_cny, weight_kg, cogs_kzt)
        VALUES ('LINE-31-LS', 0, 0, NULL), ('LINE-21-TS', 0, 0, NULL);
        INSERT INTO sales_fact_v2
        (order_id, order_date, sku_key, sku_id, my_size, store_code, quantity, net_rev, cogs, profit, status, return_flag)
        VALUES
        ('929183530', '2026-05-23', 'LINE-31-LS', 'LINE-31-LS_2XL', '2XL', 'ACMEWEAR', 1, 8563, NULL, NULL, 'DELIVERED', 0),
        ('934547752', '2026-05-27', 'LINE-21-TS', 'LINE-21-TS_3XL', '3XL', 'ACMEWEAR', 1, 6563, NULL, NULL, 'DELIVERED', 0),
        ('953395459', '2026-06-11', 'LINE-31-LS', 'LINE-31-LS_XL', 'XL', 'ACMEWEAR', 1, 9215, NULL, NULL, 'DELIVERED', 0),
        ('956748585', '2026-06-16', 'LINE-21-TS', 'LINE-21-TS_3XL', '3XL', 'ACMEWEAR', 1, 7563, NULL, NULL, 'DELIVERED', 0);
        """
    )
    conn.commit()
    conn.close()


def test_truth_view_uses_exact_owner_row_cogs_override(tmp_path: Path) -> None:
    db_path = tmp_path / "app.db"
    _seed_db(db_path)
    conn = sqlite3.connect(db_path)
    conn.execute(
        """
        CREATE TABLE fact_sales_owner_cogs_override (
            order_id TEXT,
            store_code TEXT,
            sku_key TEXT,
            sku_id TEXT,
            unit_cogs_kzt REAL,
            cogs_source TEXT,
            active_flag INTEGER
        )
        """
    )
    conn.execute(
        """
        INSERT INTO fact_sales_owner_cogs_override
        (order_id, store_code, sku_key, sku_id, unit_cogs_kzt, cogs_source, active_flag)
        VALUES ('929183530', 'ACMEWEAR', 'LINE-31-LS', 'LINE-31-LS_2XL', 6006.76, 'OWNER_TEST', 1)
        """
    )
    conn.commit()

    ensure_sales_truth_views(conn)
    rows = conn.execute(
        """
        SELECT order_id, cogs_kzt, profit_kzt, cogs_source
        FROM view_sales_line_truth
        ORDER BY order_id
        """
    ).fetchall()
    conn.close()

    assert rows == [
        ("929183530", 6006.76, 2556.24, "OWNER_TEST"),
        ("934547752", None, None, "unresolved"),
        ("953395459", None, None, "unresolved"),
        ("956748585", None, None, "unresolved"),
    ]


def test_beli_child_cogs_dry_run_does_not_mutate(tmp_path: Path) -> None:
    db_path = tmp_path / "app.db"
    _seed_db(db_path)

    summary = run(db_path=db_path, output_root=tmp_path / "out", apply=False)

    conn = sqlite3.connect(db_path)
    table_exists = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='fact_sales_owner_cogs_override'"
    ).fetchone()
    conn.close()

    assert summary["apply_status"] == "DRY_RUN"
    assert summary["before"]["unresolved_window_count"] == 4
    assert summary["simulated_after"]["unresolved_window_count"] == 0
    assert summary["after"]["unresolved_window_count"] == 4
    assert table_exists is None


def test_beli_child_cogs_apply_requires_env_gate(tmp_path: Path) -> None:
    db_path = tmp_path / "app.db"
    _seed_db(db_path)

    with pytest.raises(RuntimeError, match="ENABLE_OWNER_APPROVED_LINE_CHILD_COGS_ROW_WRITE=1"):
        run(db_path=db_path, output_root=tmp_path / "out", apply=True)


def test_beli_child_cogs_apply_writes_exact_overrides(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db_path = tmp_path / "app.db"
    _seed_db(db_path)
    monkeypatch.setenv("ENABLE_OWNER_APPROVED_LINE_CHILD_COGS_ROW_WRITE", "1")

    summary = run(db_path=db_path, output_root=tmp_path / "out", apply=True)

    conn = sqlite3.connect(db_path)
    rows = conn.execute(
        """
        SELECT order_id, sku_id, unit_cogs_kzt, cogs_source, active_flag
        FROM fact_sales_owner_cogs_override
        ORDER BY order_id
        """
    ).fetchall()
    truth_rows = conn.execute(
        """
        SELECT order_id, cogs_kzt, profit_kzt, cogs_source
        FROM view_sales_line_truth
        ORDER BY order_id
        """
    ).fetchall()
    conn.close()

    assert summary["apply_status"] == "APPLIED"
    assert Path(summary["backup_path"]).exists()
    assert rows == [
        ("929183530", "LINE-31-LS_2XL", 6006.76, "OWNER_APPROVED_LINE51_PARENT_UNIT_COGS_20260601", 1),
        ("934547752", "LINE-21-TS_3XL", 6006.76, "OWNER_APPROVED_LINE51_PARENT_UNIT_COGS_20260601", 1),
        ("953395459", "LINE-31-LS_XL", 6006.76, "OWNER_APPROVED_LINE51_PARENT_UNIT_COGS_20260601", 1),
        ("956748585", "LINE-21-TS_3XL", 6006.76, "OWNER_APPROVED_LINE51_PARENT_UNIT_COGS_20260601", 1),
    ]
    assert truth_rows == [
        ("929183530", 6006.76, 2556.24, "OWNER_APPROVED_LINE51_PARENT_UNIT_COGS_20260601"),
        ("934547752", 6006.76, 556.24, "OWNER_APPROVED_LINE51_PARENT_UNIT_COGS_20260601"),
        ("953395459", 6006.76, 3208.24, "OWNER_APPROVED_LINE51_PARENT_UNIT_COGS_20260601"),
        ("956748585", 6006.76, 1556.24, "OWNER_APPROVED_LINE51_PARENT_UNIT_COGS_20260601"),
    ]
