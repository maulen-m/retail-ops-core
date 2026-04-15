from __future__ import annotations

import sqlite3
from datetime import date
from pathlib import Path

import pytest

from scripts.validate_returns_economics_audit import (
    ReturnsEconomicsError,
    validate_returns_economics_audit,
)


def _init_db(path: Path) -> None:
    conn = sqlite3.connect(path)
    conn.executescript(
        """
        CREATE TABLE fact_orders_kaspi (
            order_id TEXT,
            store_code TEXT,
            internal_status TEXT,
            status_updated_at TEXT,
            updated_at TEXT,
            created_at TEXT
        );
        CREATE TABLE sales_fact_v2 (
            order_id TEXT,
            order_date TEXT,
            store_code TEXT,
            quantity REAL,
            net_rev REAL,
            cogs REAL,
            profit REAL,
            status TEXT,
            return_flag INTEGER,
            sku_key TEXT,
            sku_id TEXT,
            my_size TEXT
        );
        CREATE TABLE fact_cashflow_events (
            event_date TEXT,
            event_type TEXT,
            amount_kzt REAL,
            store_code TEXT
        );
        CREATE TABLE dim_sku (
            sku_key TEXT PRIMARY KEY,
            base_cost_cny REAL,
            weight_kg REAL
        );
        """
    )
    conn.execute("INSERT INTO dim_sku (sku_key, base_cost_cny, weight_kg) VALUES ('SKU', 10, 0.5)")
    conn.execute(
        """
        INSERT INTO fact_orders_kaspi (order_id, store_code, internal_status, status_updated_at, updated_at, created_at)
        VALUES ('R1', 'UNIVERSAL', 'RETURNED', '2026-03-03', '2026-03-03', '2026-02-20')
        """
    )
    conn.execute(
        """
        INSERT INTO fact_cashflow_events (event_date, event_type, amount_kzt, store_code)
        VALUES ('2026-02-10', 'REFUND', -2000, 'UNIVERSAL')
        """
    )
    conn.commit()
    conn.close()


def test_validate_returns_economics_pass_within_volatility(tmp_path: Path) -> None:
    db_path = tmp_path / "app.db"
    _init_db(db_path)

    report = validate_returns_economics_audit(
        db_path=db_path,
        as_of=date(2026, 3, 4),
        since=date(2026, 2, 1),
        output_root=tmp_path / "out",
        volatility_days=14,
        strict=True,
    )
    assert report["status"] == "PASS"
    assert report["stale_leaked_orders"] == 0


def test_validate_returns_economics_fails_stale_leak(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    db_path = tmp_path / "app.db"
    _init_db(db_path)

    conn = sqlite3.connect(db_path)
    conn.execute(
        """
        INSERT INTO sales_fact_v2 (
            order_id, order_date, store_code, quantity, net_rev, cogs, profit, status,
            return_flag, sku_key, sku_id, my_size
        ) VALUES ('R1', '2026-02-10', 'UNIVERSAL', 1, 3000, 1000, 2000, 'DELIVERED', 0, 'SKU', 'SKU_1', 'L')
        """
    )
    conn.execute(
        """
        CREATE VIEW view_sales_line_truth AS
        SELECT
            order_id,
            order_date AS sale_date,
            store_code,
            sku_key,
            sku_id,
            my_size,
            quantity AS units,
            net_rev AS net_rev_kzt,
            cogs AS cogs_kzt,
            profit AS profit_kzt,
            'sales_fact_v2' AS source_table
        FROM sales_fact_v2
        """
    )
    conn.commit()
    conn.close()

    monkeypatch.setattr("scripts.validate_returns_economics_audit.ensure_sales_truth_views", lambda _conn: None)
    with pytest.raises(ReturnsEconomicsError):
        validate_returns_economics_audit(
            db_path=db_path,
            as_of=date(2026, 3, 25),
            since=date(2026, 2, 1),
            output_root=tmp_path / "out",
            volatility_days=14,
            strict=True,
        )


def test_validate_returns_economics_ignores_returns_before_window(tmp_path: Path) -> None:
    db_path = tmp_path / "app.db"
    _init_db(db_path)

    conn = sqlite3.connect(db_path)
    conn.execute(
        """
        INSERT INTO fact_orders_kaspi (order_id, store_code, internal_status, status_updated_at, updated_at, created_at)
        VALUES ('OLD', 'UNIVERSAL', 'RETURNED', '2025-01-10', '2025-01-10', '2024-12-20')
        """
    )
    conn.execute(
        """
        INSERT INTO sales_fact_v2 (
            order_id, order_date, store_code, quantity, net_rev, cogs, profit, status,
            return_flag, sku_key, sku_id, my_size
        ) VALUES ('OLD', '2024-12-28', 'UNIVERSAL', 1, 3000, 1000, 2000, 'DELIVERED', 0, 'SKU', 'SKU_1', 'L')
        """
    )
    conn.commit()
    conn.close()

    report = validate_returns_economics_audit(
        db_path=db_path,
        as_of=date(2026, 3, 25),
        since=date(2026, 2, 1),
        output_root=tmp_path / "out",
        volatility_days=14,
        strict=True,
    )

    assert report["status"] == "PASS"
    assert report["stale_leaked_orders"] == 0


def test_validate_returns_economics_accepts_legacy_negative_cash_in_as_refund(tmp_path: Path) -> None:
    db_path = tmp_path / "app.db"
    _init_db(db_path)

    conn = sqlite3.connect(db_path)
    conn.execute("DELETE FROM fact_cashflow_events")
    conn.execute(
        """
        INSERT INTO fact_orders_kaspi (order_id, store_code, internal_status, status_updated_at, updated_at, created_at)
        VALUES ('R2', 'UNIVERSAL', 'RETURNED', '2026-02-20', '2026-02-20', '2026-02-10')
        """
    )
    conn.execute(
        """
        INSERT INTO fact_cashflow_events (event_date, event_type, amount_kzt, store_code)
        VALUES ('2026-02-21', 'CASH_IN', -2000, 'UNIVERSAL')
        """
    )
    conn.commit()
    conn.close()

    report = validate_returns_economics_audit(
        db_path=db_path,
        as_of=date(2026, 3, 25),
        since=date(2026, 2, 1),
        output_root=tmp_path / "out",
        volatility_days=14,
        strict=True,
    )

    assert report["status"] == "PASS"
    assert report["months_missing_refunds"] == []
