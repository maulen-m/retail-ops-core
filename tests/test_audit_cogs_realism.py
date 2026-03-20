from __future__ import annotations

import sqlite3
from datetime import date
from pathlib import Path

import pytest

from scripts.audit_cogs_realism import CogsAuditError, audit_cogs_realism


def _init_db(path: Path, *, with_dim_inputs: bool) -> None:
    conn = sqlite3.connect(path)
    conn.executescript(
        """
        CREATE TABLE sales_fact_v2 (
            order_id TEXT,
            order_date DATE,
            sku_key TEXT,
            sku_id TEXT,
            my_size TEXT,
            store_code TEXT,
            quantity INTEGER,
            cogs REAL,
            net_rev REAL,
            profit REAL,
            status TEXT,
            return_flag INTEGER
        );
        CREATE TABLE dim_sku (
            sku_key TEXT PRIMARY KEY,
            cogs_kzt REAL,
            base_cost_cny REAL,
            weight_kg REAL
        );
        CREATE TABLE dim_sku_size (
            sku_id TEXT PRIMARY KEY,
            sku_key TEXT,
            my_size TEXT
        );
        """
    )
    if with_dim_inputs:
        conn.execute(
            "INSERT INTO dim_sku (sku_key, cogs_kzt, base_cost_cny, weight_kg) VALUES ('SKU_A', 2500, 25, 0.9)"
        )
    else:
        conn.execute(
            "INSERT INTO dim_sku (sku_key, cogs_kzt, base_cost_cny, weight_kg) VALUES ('SKU_A', 2500, NULL, NULL)"
        )
    conn.execute("INSERT INTO dim_sku_size (sku_id, sku_key, my_size) VALUES ('SKU_A_M', 'SKU_A', 'M')")
    conn.execute(
        """
        INSERT INTO sales_fact_v2
        (order_id, order_date, sku_key, sku_id, my_size, store_code, quantity, cogs, net_rev, profit, status, return_flag)
        VALUES ('O1', '2026-02-20', 'SKU_A', 'SKU_A_M', 'M', 'UNIVERSAL', 2, 5000, 12000, 7000, 'DELIVERED', 0)
        """
    )
    conn.commit()
    conn.close()


def test_audit_cogs_realism_pass(tmp_path: Path) -> None:
    db_path = tmp_path / "app.db"
    _init_db(db_path, with_dim_inputs=True)

    report = audit_cogs_realism(
        db_path=db_path,
        as_of=date(2026, 3, 2),
        days=30,
        top_n=10,
        output_root=tmp_path / "out",
        min_formula_input_coverage_pct=50.0,
        strict=True,
    )
    assert report["status"] == "PASS"
    assert report["coverage"]["formula_input_coverage_pct"] >= 50.0
    scenario_names = {row["scenario"] for row in report["sensitivity"]}
    assert {"BASE", "USD_PLUS_10", "DLV_PLUS_20"} <= scenario_names


def test_audit_cogs_realism_fails_on_missing_formula_inputs(tmp_path: Path) -> None:
    db_path = tmp_path / "app.db"
    _init_db(db_path, with_dim_inputs=False)

    with pytest.raises(CogsAuditError):
        audit_cogs_realism(
            db_path=db_path,
            as_of=date(2026, 3, 2),
            days=30,
            top_n=10,
            output_root=tmp_path / "out",
            min_formula_input_coverage_pct=90.0,
            strict=True,
        )
