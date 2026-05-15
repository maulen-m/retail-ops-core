import sqlite3
from pathlib import Path

import pandas as pd
import pytest

from scripts import sync_truth_workbook_to_db


def _init_db(db_path: Path) -> None:
    conn = sqlite3.connect(str(db_path))
    conn.executescript(
        """
        CREATE TABLE fact_sales (
            order_date TEXT,
            sku_key TEXT,
            quantity REAL,
            sell_price_kzt REAL
        );

        CREATE TABLE dim_sku (
            sku_key TEXT PRIMARY KEY,
            model TEXT,
            color TEXT,
            product_type TEXT,
            base_cost_cny REAL,
            weight_kg REAL,
            active_flag INTEGER,
            cogs_kzt REAL,
            avg_sell_price_kzt_used REAL,
            avg_sell_price_source TEXT,
            price_missing_flag INTEGER
        );

        CREATE TABLE dim_fx_rates (
            effective_date TEXT PRIMARY KEY,
            cny_kzt REAL,
            usd_kzt REAL,
            dlv_rate_usd_kg REAL,
            usdt_kzt REAL,
            usdt_cny REAL,
            source TEXT,
            provider TEXT
        );
        """
    )
    conn.execute(
        """
        INSERT INTO dim_fx_rates (
            effective_date, cny_kzt, usd_kzt, dlv_rate_usd_kg,
            usdt_kzt, usdt_cny, source, provider
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        ("2026-02-01", 78.0, 514.0, 2.66, 502.008, 6.9187, "DERIVED", "FX_ROUTE"),
    )
    conn.commit()
    conn.close()


def _write_workbook(path: Path) -> None:
    df = pd.DataFrame(
        [
            {
                "SKU_key": "CL_OC_MEN_LINE52_BLACK",
                "Product_Type": "CL",
                "Weight_kg": 0.95,
                "BaseCost_CNY": 47.0,
                "Current_stock": 10,
                "Avg_price_90D": 9000.0,
                "Is_Active": "YES",
            }
        ]
    )
    with pd.ExcelWriter(path, engine="openpyxl") as writer:
        df.to_excel(writer, sheet_name="Dim_SKU", index=False)


def test_sync_dim_sku_computes_landed_cogs_with_routed_supplier_fx(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    db_path = tmp_path / "app.db"
    workbook_path = tmp_path / "truth.xlsx"
    _init_db(db_path)
    _write_workbook(workbook_path)
    monkeypatch.setattr(sync_truth_workbook_to_db, "DB_PATH", db_path)

    conn = sqlite3.connect(str(db_path))
    try:
        xl = pd.ExcelFile(workbook_path)
        summary = sync_truth_workbook_to_db.sync_dim_sku(conn, xl)
        row = conn.execute(
            "SELECT cogs_kzt, avg_sell_price_source FROM dim_sku WHERE sku_key='CL_OC_MEN_LINE52_BLACK'"
        ).fetchone()
    finally:
        conn.close()

    expected_cny_kzt = 502.008 / 6.9187
    expected_cogs = 47.0 * expected_cny_kzt + 0.95 * 2.66 * 514.0

    assert summary["rows_updated"] == 1
    assert row is not None
    assert row[0] == pytest.approx(expected_cogs)
    assert row[1] == "DIM_SKU"
