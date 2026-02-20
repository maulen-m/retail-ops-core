"""Tests for production readiness validation."""

import sqlite3
from pathlib import Path

from core.validation.production_readiness import evaluate_production_readiness


def _make_output(sku_level, stock_date="2026-01-02", cutoff_date="2026-01-02"):
    return {
        "summary": {
            "total_skus": len(sku_level),
            "skus_with_orders": sum(1 for sku in sku_level if sku.get("po_qty_total", 0) > 0),
            "total_units": sum(int(sku.get("po_qty_total", 0)) for sku in sku_level),
            "no_demand_estimate": 0,
        },
        "sku_level": sku_level,
        "stock_date": stock_date,
        "cutoff_date": cutoff_date,
    }


def test_readiness_blocks_missing_stock_for_ordered_sku():
    output = _make_output(
        [
            {"sku_key": "SKU1", "po_qty_total": 5, "notes": "NO_STOCK_SNAPSHOT"},
            {"sku_key": "SKU2", "po_qty_total": 0, "notes": ""},
        ]
    )
    report = evaluate_production_readiness(output, db_path=None)

    assert not report.ok
    assert any("Missing stock snapshot" in b for b in report.blockers)


def test_readiness_blocks_stale_stock_date():
    output = _make_output(
        [{"sku_key": "SKU1", "po_qty_total": 0, "notes": ""}],
        stock_date="2026-01-01",
        cutoff_date="2026-01-03",
    )
    report = evaluate_production_readiness(output, db_path=None)

    assert not report.ok
    assert any("Stock snapshot stale" in b for b in report.blockers)


def test_readiness_ok_when_clean():
    output = _make_output(
        [{"sku_key": "SKU1", "po_qty_total": 0, "notes": ""}],
        stock_date="2026-01-02",
        cutoff_date="2026-01-02",
    )
    report = evaluate_production_readiness(output, db_path=None)

    assert report.ok


def _make_readiness_db(db_path: Path, *, latest_missing_size: bool) -> None:
    conn = sqlite3.connect(str(db_path))
    conn.execute(
        """
        CREATE TABLE dim_sku (
            sku_key TEXT PRIMARY KEY,
            active_flag INTEGER
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE fact_sales (
            order_date TEXT,
            sku_id TEXT,
            sku_key TEXT,
            my_size TEXT
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE fact_inventory_snapshot_size (
            snapshot_date TEXT,
            sku_id TEXT,
            sku_key TEXT,
            my_size TEXT
        )
        """
    )
    conn.execute("INSERT INTO dim_sku (sku_key, active_flag) VALUES ('SKU1', 1)")
    conn.execute(
        """
        INSERT INTO fact_inventory_snapshot_size
            (snapshot_date, sku_id, sku_key, my_size)
        VALUES (?, ?, ?, ?)
        """,
        ("2025-12-15", "SKU1_M", "SKU1", None),
    )
    latest_size = None if latest_missing_size else "M"
    conn.execute(
        """
        INSERT INTO fact_inventory_snapshot_size
            (snapshot_date, sku_id, sku_key, my_size)
        VALUES (?, ?, ?, ?)
        """,
        ("2026-01-01", "SKU1_M", "SKU1", latest_size),
    )
    conn.commit()
    conn.close()


def test_missing_size_ignores_historical_snapshot(tmp_path: Path):
    db_path = tmp_path / "app.db"
    _make_readiness_db(db_path, latest_missing_size=False)
    output = _make_output(
        [{"sku_key": "SKU1", "po_qty_total": 0, "notes": ""}],
        stock_date="2026-01-01",
        cutoff_date="2026-01-02",
    )
    report = evaluate_production_readiness(output, db_path=db_path)

    assert report.ok


def test_missing_size_blocks_latest_snapshot(tmp_path: Path):
    db_path = tmp_path / "app.db"
    _make_readiness_db(db_path, latest_missing_size=True)
    output = _make_output(
        [{"sku_key": "SKU1", "po_qty_total": 0, "notes": ""}],
        stock_date="2026-01-01",
        cutoff_date="2026-01-02",
    )
    report = evaluate_production_readiness(output, db_path=db_path)

    assert not report.ok
    assert any("Missing MY_SIZE rows detected" in b for b in report.blockers)
