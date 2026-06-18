from __future__ import annotations

from datetime import date
import sqlite3
from pathlib import Path

from scripts.validate_data_completeness import validate


def _seed_db(db_path: Path, *, cogs_authority: bool = True) -> None:
    conn = sqlite3.connect(db_path)
    conn.executescript(
        """
        CREATE TABLE dim_sku (
            sku_key TEXT PRIMARY KEY,
            base_cost_cny REAL,
            weight_kg REAL,
            cogs_kzt REAL
        );
        CREATE TABLE fact_sales (
            order_id TEXT,
            order_date TEXT,
            sku_key TEXT,
            sku_id TEXT,
            quantity INTEGER,
            cogs_unit REAL,
            profit_line REAL
        );
        CREATE TABLE fact_sales_daily (
            sale_date TEXT,
            units INTEGER
        );
        """
    )
    conn.execute(
        """
        INSERT INTO dim_sku (sku_key, base_cost_cny, weight_kg, cogs_kzt)
        VALUES ('SKU_A', ?, ?, NULL)
        """,
        (10.0 if cogs_authority else 0.0, 0.5 if cogs_authority else 0.0),
    )
    conn.execute(
        """
        INSERT INTO fact_sales (
            order_id, order_date, sku_key, sku_id, quantity, cogs_unit, profit_line
        ) VALUES ('ORD-1', '2026-06-13', 'SKU_A', 'SKU_A_M', 1, 500.0, -10.0)
        """
    )
    conn.execute("INSERT INTO fact_sales_daily (sale_date, units) VALUES ('2026-06-13', 1)")
    conn.commit()
    conn.close()


def test_formula_inputs_are_valid_cogs_authority_and_negative_profit_warns(tmp_path: Path) -> None:
    db = tmp_path / "app.db"
    _seed_db(db, cogs_authority=True)

    assert validate(db_path=db, as_of=date(2026, 6, 14)) is True


def test_missing_all_cogs_authority_fails(tmp_path: Path) -> None:
    db = tmp_path / "app.db"
    _seed_db(db, cogs_authority=False)

    assert validate(db_path=db, as_of=date(2026, 6, 14)) is False
