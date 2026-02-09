import sqlite3
from pathlib import Path

import pandas as pd

from core.sales.truth_views import ensure_sales_truth_views
from scripts.validate_cogs_integrity import validate_cogs_integrity
from scripts.validate_dim_sku_master_alignment import validate_dim_sku_master_alignment


def _seed_sales_schema(conn: sqlite3.Connection) -> None:
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
        CREATE TABLE dim_kaspi_article_map (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            store_code TEXT,
            kaspi_article TEXT,
            sku_key TEXT,
            sku_id TEXT,
            active_flag INTEGER DEFAULT 1
        );
        """
    )


def _write_master_workbook(path: Path, rows: list[dict]) -> None:
    df = pd.DataFrame(rows)
    with pd.ExcelWriter(path, engine="openpyxl") as writer:
        df.to_excel(writer, sheet_name="Dim_SKU", index=False)


def test_validator_fails_on_unresolved_cogs_rows(tmp_path: Path) -> None:
    db_path = tmp_path / "app.db"
    conn = sqlite3.connect(str(db_path))
    _seed_sales_schema(conn)
    conn.execute("INSERT INTO dim_sku (sku_key, base_cost_cny, weight_kg, cogs_kzt) VALUES ('SKU_BAD', 50, NULL, 0)")
    conn.execute(
        """
        INSERT INTO sales_fact_v2
        (order_id, order_date, sku_key, sku_id, my_size, store_code, quantity, net_rev, cogs, profit, status, return_flag)
        VALUES ('ORD-1', '2026-02-08', 'SKU_BAD', 'SKU_BAD_XL', 'XL', 'ACMEWEAR', 1, 10000, 0, 0, 'DELIVERED', 0)
        """
    )
    conn.commit()
    ensure_sales_truth_views(conn)
    conn.close()

    report = validate_cogs_integrity(db_path=db_path, as_of="2026-02-08", days=7)
    assert report["ok"] is False
    assert any("unresolved" in err.lower() for err in report["errors"])


def test_validator_fails_when_dim_sku_weight_mismatch_exceeds_tolerance(tmp_path: Path) -> None:
    db_path = tmp_path / "app.db"
    conn = sqlite3.connect(str(db_path))
    conn.execute(
        """
        CREATE TABLE dim_sku (
            sku_key TEXT PRIMARY KEY,
            base_cost_cny REAL,
            weight_kg REAL,
            active_flag INTEGER DEFAULT 1
        )
        """
    )
    conn.execute(
        "INSERT INTO dim_sku (sku_key, base_cost_cny, weight_kg, active_flag) VALUES ('SKU_A', 60, 0.90, 1)"
    )
    conn.commit()
    conn.close()

    workbook = tmp_path / "master.xlsx"
    _write_master_workbook(
        workbook,
        [
            {
                "SKU_key": "SKU_A",
                "BaseCost_CNY": 60,
                "Weight_kg": 1.20,
                "Is_Active": 1,
            }
        ],
    )

    report = validate_dim_sku_master_alignment(
        db_path=db_path,
        workbook_path=workbook,
        sheet_name="Dim_SKU",
        weight_tol_kg=0.01,
    )
    assert report["ok"] is False
    assert report["mismatch_count"] == 1


def test_validator_passes_after_alignment(tmp_path: Path) -> None:
    db_path = tmp_path / "app.db"
    conn = sqlite3.connect(str(db_path))
    conn.execute(
        """
        CREATE TABLE dim_sku (
            sku_key TEXT PRIMARY KEY,
            base_cost_cny REAL,
            weight_kg REAL,
            active_flag INTEGER DEFAULT 1
        )
        """
    )
    conn.execute(
        "INSERT INTO dim_sku (sku_key, base_cost_cny, weight_kg, active_flag) VALUES ('SKU_A', 60, 1.20, 1)"
    )
    conn.commit()
    conn.close()

    workbook = tmp_path / "master.xlsx"
    _write_master_workbook(
        workbook,
        [
            {
                "SKU_key": "SKU_A",
                "BaseCost_CNY": 60,
                "Weight_kg": 1.20,
                "Is_Active": 1,
            }
        ],
    )

    report = validate_dim_sku_master_alignment(
        db_path=db_path,
        workbook_path=workbook,
        sheet_name="Dim_SKU",
        weight_tol_kg=0.01,
    )
    assert report["ok"] is True
    assert report["mismatch_count"] == 0
