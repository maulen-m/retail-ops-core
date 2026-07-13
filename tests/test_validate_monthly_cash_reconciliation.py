from __future__ import annotations

import hashlib
import sqlite3
from datetime import date
from pathlib import Path

import pytest

from core.sales import ensure_sales_truth_views
import scripts.validate_monthly_cash_reconciliation as reconciliation
from scripts.validate_monthly_cash_reconciliation import (
    CashReconciliationError,
    validate_monthly_cash_reconciliation,
)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _init_db(
    path: Path,
    *,
    sale_amount: float = 1000.0,
    cash_amount: float = 1000.0,
    prepare_views: bool = True,
) -> None:
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
            quantity INTEGER,
            cogs REAL,
            net_rev REAL,
            profit REAL,
            status TEXT,
            return_flag INTEGER
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
    conn.execute("INSERT INTO dim_sku (sku_key, base_cost_cny, weight_kg) VALUES ('SKU_A', 10, 0.5)")
    conn.execute(
        """
        INSERT INTO sales_fact_v2
        (order_id, order_date, sku_key, sku_id, my_size, store_code, quantity, cogs, net_rev, profit, status, return_flag)
        VALUES ('O1', '2026-02-15', 'SKU_A', 'SKU_A_M', 'M', 'UNIVERSAL', 1, 400, ?, 600, 'DELIVERED', 0)
        """,
        (sale_amount,),
    )
    conn.execute(
        "INSERT INTO fact_cashflow_events (event_date, event_type, amount_kzt, store_code) VALUES ('2026-02-15', 'SALE_ACCRUED', ?, 'UNIVERSAL')",
        (cash_amount,),
    )
    if prepare_views:
        ensure_sales_truth_views(conn)
    conn.commit()
    conn.close()


def test_validate_monthly_cash_reconciliation_pass(tmp_path: Path) -> None:
    db_path = tmp_path / "app.db"
    _init_db(db_path, sale_amount=1000.0, cash_amount=980.0)
    db_sha_before = _sha256(db_path)

    report = validate_monthly_cash_reconciliation(
        db_path=db_path,
        since=date(2026, 2, 1),
        until=date(2026, 3, 20),
        output_root=tmp_path / "out",
        tolerance_pct=0.05,
        statusdate_cutover=date(2026, 1, 1),
        require_covered_pairs=True,
        strict=True,
    )
    assert report["status"] == "PASS"
    assert report["covered_pairs"] >= 1
    assert _sha256(db_path) == db_sha_before


def test_validate_monthly_cash_reconciliation_fails_on_large_diff(tmp_path: Path) -> None:
    db_path = tmp_path / "app.db"
    _init_db(db_path, sale_amount=1000.0, cash_amount=200.0)
    db_sha_before = _sha256(db_path)

    with pytest.raises(CashReconciliationError):
        validate_monthly_cash_reconciliation(
            db_path=db_path,
            since=date(2026, 2, 1),
            until=date(2026, 3, 20),
            output_root=tmp_path / "out",
            tolerance_pct=0.05,
            statusdate_cutover=date(2026, 1, 1),
            require_covered_pairs=True,
            strict=True,
        )
    assert _sha256(db_path) == db_sha_before


def test_validate_monthly_cash_reconciliation_requires_prepared_view_without_mutation(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "app.db"
    _init_db(db_path, prepare_views=False)
    db_sha_before = _sha256(db_path)

    with pytest.raises(CashReconciliationError, match="required view missing"):
        validate_monthly_cash_reconciliation(
            db_path=db_path,
            since=date(2026, 2, 1),
            until=date(2026, 3, 20),
            output_root=tmp_path / "out",
            tolerance_pct=0.05,
            statusdate_cutover=date(2026, 1, 1),
            require_covered_pairs=True,
            strict=True,
        )
    assert _sha256(db_path) == db_sha_before


def test_nonproduction_db_cannot_use_canonical_output_root(tmp_path: Path, monkeypatch) -> None:
    db_path = tmp_path / "app.db"
    _init_db(db_path)
    db_sha_before = _sha256(db_path)
    canonical_output_root = tmp_path / "canonical_cash_reconciliation"
    monkeypatch.setattr(reconciliation, "DEFAULT_OUTPUT_ROOT", canonical_output_root)

    with pytest.raises(CashReconciliationError, match="explicit noncanonical output_root"):
        validate_monthly_cash_reconciliation(
            db_path=db_path,
            since=date(2026, 2, 1),
            until=date(2026, 3, 20),
            output_root=canonical_output_root,
            tolerance_pct=0.05,
            statusdate_cutover=date(2026, 1, 1),
            require_covered_pairs=True,
            strict=True,
        )
    assert not canonical_output_root.exists()
    assert _sha256(db_path) == db_sha_before
