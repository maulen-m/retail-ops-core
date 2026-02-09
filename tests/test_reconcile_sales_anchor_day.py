from __future__ import annotations

import os
import sqlite3
from pathlib import Path

import pandas as pd
import pytest

from scripts.reconcile_sales_anchor_day import reconcile_sales_anchor_day


def _init_sales_v2(db_path: Path) -> None:
    conn = sqlite3.connect(db_path)
    try:
        conn.executescript(
            """
            CREATE TABLE sales_fact_v2 (
                sale_id INTEGER PRIMARY KEY AUTOINCREMENT,
                order_id TEXT NOT NULL,
                order_date TEXT NOT NULL,
                sku_key TEXT NOT NULL,
                sku_id TEXT NOT NULL,
                my_size TEXT NOT NULL,
                kaspi_offer_name TEXT NOT NULL,
                store_code TEXT DEFAULT 'UNIVERSAL',
                quantity INTEGER NOT NULL,
                sell_price_kzt REAL,
                delivery_fee REAL,
                cogs REAL,
                net_rev REAL,
                profit REAL,
                status TEXT DEFAULT 'DELIVERED',
                return_flag INTEGER DEFAULT 0,
                source_file TEXT
            );
            """
        )
        conn.execute(
            """
            INSERT INTO sales_fact_v2 (
                order_id, order_date, sku_key, sku_id, my_size, kaspi_offer_name, store_code,
                quantity, sell_price_kzt, delivery_fee, net_rev, status, return_flag, source_file
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "811866861",
                "2026-02-07",
                "CL_OC_MEN_LINE52_BLACK",
                "CL_OC_MEN_LINE52_BLACK_XL",
                "XL",
                "LINE52 XL",
                "UNIVERSAL",
                1,
                9427.0,
                699.0,
                8001.16625,
                "DELIVERED",
                0,
                "seed.xlsx",
            ),
        )
        conn.commit()
    finally:
        conn.close()


def _write_anchor_workbook(path: Path) -> None:
    df = pd.DataFrame(
        [
            {
                "OrderID": 811866861,
                "Date": "2026-02-07",
                "KASPI_OFFER_NAME": "LINE52 XL",
                "SKU_key": "CL_OC_MEN_LINE52_BLACK",
                "SKU_ID": "CL_OC_MEN_LINE52_BLACK_XL",
                "MY_SIZE": "XL",
                "Quantity": 1,
                "Sell_price_kzt": 9427,
                "STORE_NAME": "UNIVERSAL",
                "Return": 0,
                "Total_net_rev": 7133.01625,
                "Delivery_fee_kzt": 1599,
            }
        ]
    )
    with pd.ExcelWriter(path, engine="openpyxl") as writer:
        df.to_excel(writer, sheet_name="SALES_KSP_CRM_1", index=False)


def _fetch_net_and_fee(db_path: Path) -> tuple[float, float]:
    conn = sqlite3.connect(db_path)
    try:
        row = conn.execute(
            "SELECT net_rev, delivery_fee FROM sales_fact_v2 WHERE order_id = '811866861'"
        ).fetchone()
        assert row is not None
        return float(row[0] or 0.0), float(row[1] or 0.0)
    finally:
        conn.close()


def test_reconcile_sales_anchor_day_dry_run_no_writes(tmp_path: Path) -> None:
    db_path = tmp_path / "app.db"
    workbook_path = tmp_path / "sales.xlsx"
    _init_sales_v2(db_path)
    _write_anchor_workbook(workbook_path)

    before = _fetch_net_and_fee(db_path)
    result = reconcile_sales_anchor_day(
        db_path=db_path,
        workbook_path=workbook_path,
        since="2026-02-07",
        until="2026-02-07",
        apply=False,
    )
    after = _fetch_net_and_fee(db_path)

    assert result["candidates"] == 1
    assert result["would_update"] == 1
    assert result["updated"] == 0
    assert before == after


def test_reconcile_sales_anchor_day_apply_requires_env_gate(tmp_path: Path) -> None:
    db_path = tmp_path / "app.db"
    workbook_path = tmp_path / "sales.xlsx"
    _init_sales_v2(db_path)
    _write_anchor_workbook(workbook_path)

    with pytest.raises(RuntimeError, match="ENABLE_CASHFLOW_WRITE=1"):
        reconcile_sales_anchor_day(
            db_path=db_path,
            workbook_path=workbook_path,
            since="2026-02-07",
            until="2026-02-07",
            apply=True,
        )


def test_reconcile_sales_anchor_day_apply_updates_and_is_idempotent(tmp_path: Path) -> None:
    db_path = tmp_path / "app.db"
    workbook_path = tmp_path / "sales.xlsx"
    _init_sales_v2(db_path)
    _write_anchor_workbook(workbook_path)

    old_env = os.environ.get("ENABLE_CASHFLOW_WRITE")
    os.environ["ENABLE_CASHFLOW_WRITE"] = "1"
    try:
        first = reconcile_sales_anchor_day(
            db_path=db_path,
            workbook_path=workbook_path,
            since="2026-02-07",
            until="2026-02-07",
            apply=True,
        )
        second = reconcile_sales_anchor_day(
            db_path=db_path,
            workbook_path=workbook_path,
            since="2026-02-07",
            until="2026-02-07",
            apply=True,
        )
    finally:
        if old_env is None:
            os.environ.pop("ENABLE_CASHFLOW_WRITE", None)
        else:
            os.environ["ENABLE_CASHFLOW_WRITE"] = old_env

    net_rev, delivery_fee = _fetch_net_and_fee(db_path)
    assert first["would_update"] == 1
    assert first["updated"] == 1
    assert second["would_update"] == 0
    assert second["updated"] == 0
    assert round(net_rev, 5) == round(7133.01625, 5)
    assert round(delivery_fee, 2) == 1599.0
