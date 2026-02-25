from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from scripts.build_portfolio_completeness_report import build_portfolio_completeness_report


def _seed_db(db_path: Path) -> None:
    conn = sqlite3.connect(str(db_path))
    conn.executescript(
        """
        CREATE TABLE dim_sku (
            sku_key TEXT PRIMARY KEY,
            active_flag INTEGER,
            cogs_kzt REAL,
            base_cost_cny REAL,
            weight_kg REAL
        );
        CREATE TABLE fact_inventory_snapshot_size (
            snapshot_date TEXT,
            sku_key TEXT,
            current_stock INTEGER,
            inbound_stock INTEGER
        );
        CREATE TABLE fact_demand_estimates (
            cutoff_date TEXT,
            sku_key TEXT
        );
        CREATE TABLE fact_sales (
            order_date TEXT,
            sku_key TEXT,
            quantity INTEGER
        );
        """
    )
    conn.executemany(
        "INSERT INTO dim_sku (sku_key, active_flag, cogs_kzt, base_cost_cny, weight_kg) VALUES (?, ?, ?, ?, ?)",
        [
            ("SKU_A", 1, 1000.0, 0.0, 0.0),
            ("SKU_B", 1, 0.0, 10.0, 1.5),
            ("SKU_C", 1, 0.0, 0.0, 0.0),
            ("SKU_INACTIVE", 0, 0.0, 0.0, 0.0),
        ],
    )
    conn.executemany(
        "INSERT INTO fact_inventory_snapshot_size (snapshot_date, sku_key, current_stock, inbound_stock) VALUES (?, ?, ?, ?)",
        [
            ("2026-02-26", "SKU_A", 10, 0),
            ("2026-02-26", "SKU_B", 10, 0),
            ("2026-02-26", "SKU_C", 10, 0),
        ],
    )
    conn.executemany(
        "INSERT INTO fact_demand_estimates (cutoff_date, sku_key) VALUES (?, ?)",
        [
            ("2026-02-26", "SKU_A"),
            ("2026-02-26", "SKU_B"),
            ("2026-02-26", "SKU_C"),
        ],
    )
    conn.commit()
    conn.close()


def test_portfolio_completeness_passes_when_all_signals_exist(tmp_path: Path) -> None:
    db_path = tmp_path / "app.db"
    _seed_db(db_path)

    # Make SKU_C economically covered for green state.
    conn = sqlite3.connect(str(db_path))
    conn.execute("UPDATE dim_sku SET cogs_kzt = 1200 WHERE sku_key = 'SKU_C'")
    conn.commit()
    conn.close()

    report = build_portfolio_completeness_report(
        db_path=db_path,
        as_of="2026-02-26",
        output_root=tmp_path,
        strict=True,
    )
    assert report["ok"] is True
    assert report["exit_code"] == 0
    payload = json.loads((tmp_path / "2026-02-26" / "portfolio_completeness_report.json").read_text(encoding="utf-8"))
    assert payload["status"] == "GREEN"
    assert payload["missing_stock_count"] == 0
    assert payload["missing_demand_count"] == 0
    assert payload["missing_unit_econ_count"] == 0
    assert payload["demand_required_skus"] == 3
    assert payload["pending_launch_count"] == 0


def test_portfolio_completeness_fails_closed_when_unit_econ_missing(tmp_path: Path) -> None:
    db_path = tmp_path / "app.db"
    _seed_db(db_path)

    report = build_portfolio_completeness_report(
        db_path=db_path,
        as_of="2026-02-26",
        output_root=tmp_path,
        strict=True,
    )
    assert report["ok"] is False
    assert report["exit_code"] == 1
    payload = report["payload"]
    assert payload["status"] == "RED"
    assert payload["missing_unit_econ_count"] == 1
    assert payload["missing_unit_econ"] == ["SKU_C"]


def test_portfolio_completeness_allows_pending_launch_without_demand(tmp_path: Path) -> None:
    db_path = tmp_path / "app.db"
    _seed_db(db_path)

    conn = sqlite3.connect(str(db_path))
    conn.execute("DELETE FROM fact_demand_estimates WHERE sku_key = 'SKU_C'")
    conn.execute(
        "UPDATE fact_inventory_snapshot_size SET current_stock = 0, inbound_stock = 50 WHERE sku_key = 'SKU_C'"
    )
    conn.execute("UPDATE dim_sku SET cogs_kzt = 1200 WHERE sku_key = 'SKU_C'")
    conn.commit()
    conn.close()

    report = build_portfolio_completeness_report(
        db_path=db_path,
        as_of="2026-02-26",
        output_root=tmp_path,
        strict=True,
    )
    assert report["ok"] is True
    payload = report["payload"]
    assert payload["missing_demand_count"] == 0
    assert payload["demand_required_skus"] == 2
    assert payload["pending_launch_count"] == 1
    assert payload["pending_launch"] == ["SKU_C"]
