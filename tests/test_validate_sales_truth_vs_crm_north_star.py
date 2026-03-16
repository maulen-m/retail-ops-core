from __future__ import annotations

import sqlite3
from pathlib import Path

import pandas as pd
import pytest

from scripts.validate_sales_truth_vs_crm_north_star import (
    SalesTruthVsCRMError,
    validate_sales_truth_vs_crm_north_star,
)


def _write_workbooks(
    tmp_path: Path,
    *,
    crm_net_rev: float = 1000.0,
    status_change_date: str | None = "01.01.2026",
    status_value: str = "Выдан",
) -> tuple[Path, Path]:
    crm = tmp_path / "crm.xlsx"
    rec = tmp_path / "rec.xlsx"
    crm_df = pd.DataFrame(
        [
            {
                "Return": None,
                "Date": "01.01.2026",
                "STORE_NAME": "Universal",
                "HEIGHT": None,
                "WEIGHT": None,
                "Quantity": 1,
                "Kaspi_name_core": "A",
                "OrderID": 111,
                "Phone": None,
                "MY_SIZE": "L",
                "PROBABLE_SIZE": None,
                "KASPI_OFFER_NAME": "Offer",
                "SKU_key": "SKU_A",
                "SKU_ID": "SKU_A_L",
                "Sell_price_kzt": 1500,
                "Total_price": 1500,
                "Total_net_rev": crm_net_rev,
                "MODEL": "M",
                "PLANNED_SHIPPING_DATE": None,
                "Product_Type": "CL",
            }
        ]
    )
    rec_df = pd.DataFrame(
        [
            {
                "№ заказа": 111,
                "Дата изменения статуса": status_change_date,
                "Статус": status_value,
            }
        ]
    )
    with pd.ExcelWriter(crm, engine="openpyxl") as w:
        crm_df.to_excel(w, sheet_name="Archive_sales", index=False)
    with pd.ExcelWriter(rec, engine="openpyxl") as w:
        rec_df.to_excel(w, sheet_name="sales_daily_sku_size_2024-06-06", index=False)
    return crm, rec


def _write_db(db_path: Path, *, db_net_rev: float = 900.0) -> None:
    conn = sqlite3.connect(db_path)
    try:
        conn.execute(
            """
            CREATE TABLE view_sales_line_truth (
                order_id TEXT,
                sale_date TEXT,
                store_code TEXT,
                sku_key TEXT,
                sku_id TEXT,
                my_size TEXT,
                units REAL,
                net_rev_kzt REAL,
                cogs_kzt REAL,
                profit_kzt REAL,
                cogs_source TEXT
            )
            """
        )
        conn.execute(
            """
            INSERT INTO view_sales_line_truth
            (order_id, sale_date, store_code, sku_key, sku_id, my_size, units, net_rev_kzt, cogs_kzt, profit_kzt, cogs_source)
            VALUES ('111', '2026-01-01', 'UNIVERSAL', 'SKU_A', 'SKU_A_L', 'L', 1, ?, 400, 500, 'formula_full')
            """,
            (db_net_rev,),
        )
        conn.commit()
    finally:
        conn.close()


def test_validate_sales_truth_vs_crm_north_star_pass(tmp_path: Path) -> None:
    db = tmp_path / "app.db"
    _write_db(db_path=db, db_net_rev=1000.0)
    crm, rec = _write_workbooks(tmp_path, crm_net_rev=1000.0)
    out_dir = tmp_path / "out"
    payload = validate_sales_truth_vs_crm_north_star(
        start="2026-01-01",
        end="2026-01-31",
        strict=True,
        crm_workbook=crm,
        reconciled_workbook=rec,
        db_path=db,
        net_rev_tolerance_kzt=1.0,
        units_tolerance=0.0,
        output_dir=out_dir,
        min_verified_date_ratio=0.95,
    )
    assert payload["status"] == "PASS"
    assert (out_dir / "sales_truth_vs_crm_by_day_store.csv").exists()
    assert (out_dir / "sales_truth_vs_crm_floor_gaps.csv").exists()


def test_validate_sales_truth_vs_crm_north_star_strict_fail_over_ceiling(tmp_path: Path) -> None:
    db = tmp_path / "app.db"
    _write_db(db_path=db, db_net_rev=1200.0)
    crm, rec = _write_workbooks(tmp_path, crm_net_rev=1000.0)
    with pytest.raises(SalesTruthVsCRMError):
        validate_sales_truth_vs_crm_north_star(
            start="2026-01-01",
            end="2026-01-31",
            strict=True,
            crm_workbook=crm,
            reconciled_workbook=rec,
            db_path=db,
            net_rev_tolerance_kzt=1.0,
            units_tolerance=0.0,
            output_dir=tmp_path / "out",
            min_verified_date_ratio=0.95,
        )


def test_validate_sales_truth_vs_crm_north_star_strict_fail_floor_gap(tmp_path: Path) -> None:
    db = tmp_path / "app.db"
    _write_db(db_path=db, db_net_rev=900.0)
    crm, rec = _write_workbooks(tmp_path, crm_net_rev=1000.0)
    with pytest.raises(SalesTruthVsCRMError):
        validate_sales_truth_vs_crm_north_star(
            start="2026-01-01",
            end="2026-01-31",
            strict=True,
            crm_workbook=crm,
            reconciled_workbook=rec,
            db_path=db,
            net_rev_tolerance_kzt=1.0,
            units_tolerance=0.0,
            output_dir=tmp_path / "out",
            min_verified_date_ratio=0.95,
        )


def test_validate_sales_truth_vs_crm_north_star_strict_fail_date_mismatch(tmp_path: Path) -> None:
    db = tmp_path / "app.db"
    _write_db(db_path=db, db_net_rev=1000.0)
    crm, rec = _write_workbooks(
        tmp_path, crm_net_rev=1000.0, status_change_date="02.01.2026"
    )
    with pytest.raises(SalesTruthVsCRMError):
        validate_sales_truth_vs_crm_north_star(
            start="2026-01-01",
            end="2026-01-31",
            strict=True,
            crm_workbook=crm,
            reconciled_workbook=rec,
            db_path=db,
            net_rev_tolerance_kzt=1.0,
            units_tolerance=0.0,
            output_dir=tmp_path / "out",
            min_verified_date_ratio=0.95,
        )


def test_validate_sales_truth_vs_crm_north_star_unverified_date_not_strict_mismatch(
    tmp_path: Path,
) -> None:
    db = tmp_path / "app.db"
    _write_db(db_path=db, db_net_rev=1000.0)
    crm, rec = _write_workbooks(
        tmp_path,
        crm_net_rev=1000.0,
        status_change_date=None,
        status_value="Завершен",
    )
    payload = validate_sales_truth_vs_crm_north_star(
        start="2026-01-01",
        end="2026-01-31",
        strict=True,
        crm_workbook=crm,
        reconciled_workbook=rec,
        db_path=db,
        net_rev_tolerance_kzt=1.0,
        units_tolerance=0.0,
        output_dir=tmp_path / "out",
        min_verified_date_ratio=0.0,
    )
    assert payload["status"] == "PASS"
    assert payload["chronology_mismatch_orders"] == 0


def test_validate_sales_truth_vs_crm_north_star_excludes_unverified_out_of_window(
    tmp_path: Path,
) -> None:
    db = tmp_path / "app.db"
    conn = sqlite3.connect(db)
    try:
        conn.execute(
            """
            CREATE TABLE view_sales_line_truth (
                order_id TEXT,
                sale_date TEXT,
                store_code TEXT,
                sku_key TEXT,
                sku_id TEXT,
                my_size TEXT,
                units REAL,
                net_rev_kzt REAL,
                cogs_kzt REAL,
                profit_kzt REAL,
                cogs_source TEXT
            )
            """
        )
        conn.execute(
            """
            INSERT INTO view_sales_line_truth
            (order_id, sale_date, store_code, sku_key, sku_id, my_size, units, net_rev_kzt, cogs_kzt, profit_kzt, cogs_source)
            VALUES ('111', '2025-12-30', 'UNIVERSAL', 'SKU_A', 'SKU_A_L', 'L', 1, 1000, 400, 500, 'formula_full')
            """
        )
        conn.commit()
    finally:
        conn.close()
    crm, rec = _write_workbooks(
        tmp_path,
        crm_net_rev=1000.0,
        status_change_date=None,
        status_value="Завершен",
    )
    payload = validate_sales_truth_vs_crm_north_star(
        start="2026-01-01",
        end="2026-01-31",
        strict=True,
        crm_workbook=crm,
        reconciled_workbook=rec,
        db_path=db,
        net_rev_tolerance_kzt=1.0,
        units_tolerance=0.0,
        output_dir=tmp_path / "out",
        min_verified_date_ratio=0.0,
    )
    assert payload["status"] == "PASS"
    assert payload["bridge_unverified_db_outside_window_excluded"] == 1


def test_validate_sales_truth_vs_crm_north_star_strict_fail_low_verified_ratio(
    tmp_path: Path,
) -> None:
    db = tmp_path / "app.db"
    _write_db(db_path=db, db_net_rev=1000.0)
    crm, rec = _write_workbooks(
        tmp_path,
        crm_net_rev=1000.0,
        status_change_date=None,
        status_value="Завершен",
    )
    with pytest.raises(SalesTruthVsCRMError, match="verified_ratio"):
        validate_sales_truth_vs_crm_north_star(
            start="2026-01-01",
            end="2026-01-31",
            strict=True,
            crm_workbook=crm,
            reconciled_workbook=rec,
            db_path=db,
            net_rev_tolerance_kzt=1.0,
            units_tolerance=0.0,
            min_verified_date_ratio=0.95,
            output_dir=tmp_path / "out",
        )
