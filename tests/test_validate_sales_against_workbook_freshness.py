from __future__ import annotations

import sqlite3
from pathlib import Path

import openpyxl

from scripts.validate_sales_against_workbook import validate_sales_against_workbook


def _seed_v2(db_path: Path, *, order_date: str = "2026-02-06", units: float = 100.0, net_rev: float = 100000.0) -> None:
    conn = sqlite3.connect(str(db_path))
    conn.executescript(
        """
        CREATE TABLE sales_fact_v2 (
            order_id TEXT,
            order_date TEXT,
            sku_key TEXT,
            sku_id TEXT,
            quantity REAL,
            net_rev REAL,
            cogs REAL,
            status TEXT,
            return_flag INTEGER
        );
        CREATE TABLE fact_sales (
            order_id TEXT,
            order_date TEXT,
            sku_key TEXT,
            sku_id TEXT,
            quantity REAL,
            line_net_rev REAL,
            cogs_line REAL
        );
        """
    )
    conn.execute(
        """
        INSERT INTO sales_fact_v2
        (order_id, order_date, sku_key, sku_id, quantity, net_rev, cogs, status, return_flag)
        VALUES ('ORD-1', ?, 'SKU_A', 'SKU_A_M', ?, ?, 0, 'DELIVERED', 0)
        """,
        (order_date, units, net_rev),
    )
    conn.commit()
    conn.close()


def _write_workbook(path: Path, rows: list[tuple[str, float, float]]) -> None:
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "SALES_KSP_CRM_1"
    ws.append(["Date", "Quantity", "Total_net_rev"])
    for day, units, net in rows:
        ws.append([day, units, net])
    wb.save(path)


def test_validator_fails_when_workbook_content_lags_threshold(tmp_path: Path) -> None:
    db = tmp_path / "app.db"
    wb = tmp_path / "crm.xlsx"
    _seed_v2(db, order_date="2026-02-06")
    _write_workbook(wb, [("2026-02-06", 100.0, 100000.0)])

    report = validate_sales_against_workbook(
        db_path=db,
        workbook_path=wb,
        as_of="2026-02-08",
        days=14,
        tol_pct=5.0,
        min_overlap_days=1,
        max_lag_days=1,
    )

    assert report["ok"] is False
    assert any("workbook content lag exceeds threshold" in err for err in report["errors"])


def test_validator_passes_when_workbook_content_within_lag_threshold(tmp_path: Path) -> None:
    db = tmp_path / "app.db"
    wb = tmp_path / "crm.xlsx"
    _seed_v2(db, order_date="2026-02-07")
    _write_workbook(wb, [("2026-02-07", 100.0, 100000.0)])

    report = validate_sales_against_workbook(
        db_path=db,
        workbook_path=wb,
        as_of="2026-02-08",
        days=14,
        tol_pct=5.0,
        min_overlap_days=1,
        max_lag_days=1,
    )

    assert report["ok"] is True


def test_validator_fails_closed_on_workbook_parse_error(tmp_path: Path) -> None:
    db = tmp_path / "app.db"
    wb = tmp_path / "crm.xlsx"
    _seed_v2(db, order_date="2026-02-08")

    bad_wb = openpyxl.Workbook()
    ws = bad_wb.active
    ws.title = "SALES_KSP_CRM_1"
    ws.append(["WrongColumn", "Q"])
    ws.append(["2026-02-08", 1])
    bad_wb.save(wb)

    report = validate_sales_against_workbook(
        db_path=db,
        workbook_path=wb,
        as_of="2026-02-08",
        days=14,
        tol_pct=5.0,
        min_overlap_days=1,
        max_lag_days=1,
    )

    assert report["ok"] is False
    assert any("workbook parse error" in err for err in report["errors"])


def test_validator_supports_explicit_window_and_writes_report(tmp_path: Path) -> None:
    db = tmp_path / "app.db"
    wb = tmp_path / "crm.xlsx"
    _seed_v2(db, order_date="2026-02-07", units=10.0, net_rev=10000.0)
    conn = sqlite3.connect(str(db))
    conn.execute(
        """
        INSERT INTO sales_fact_v2
        (order_id, order_date, sku_key, sku_id, quantity, net_rev, cogs, status, return_flag)
        VALUES ('ORD-2', '2026-02-08', 'SKU_A', 'SKU_A_M', 11.0, 11000.0, 0, 'DELIVERED', 0)
        """
    )
    conn.commit()
    conn.close()
    _write_workbook(
        wb,
        [
            ("2026-02-07", 10.0, 10000.0),
            ("2026-02-08", 11.0, 11000.0),
        ],
    )

    out_dir = tmp_path / "validation"
    report = validate_sales_against_workbook(
        db_path=db,
        workbook_path=wb,
        start="2026-02-07",
        end="2026-02-08",
        output_dir=out_dir,
        min_overlap_days=2,
        max_lag_days=30,
    )

    assert report["ok"] is True
    assert report["window_start"] == "2026-02-07"
    assert report["window_end"] == "2026-02-08"
    assert Path(report["outputs"]["sales_against_workbook_report_json"]).exists()
    assert Path(report["outputs"]["sales_against_workbook_report_md"]).exists()


def test_validator_normalizes_invalid_month_end_input(tmp_path: Path) -> None:
    db = tmp_path / "app.db"
    wb = tmp_path / "crm.xlsx"
    _seed_v2(db, order_date="2026-02-28", units=10.0, net_rev=10000.0)
    _write_workbook(wb, [("2026-02-28", 10.0, 10000.0)])

    report = validate_sales_against_workbook(
        db_path=db,
        workbook_path=wb,
        start="2026-02-01",
        end="2026-02-29",
        min_overlap_days=1,
        max_lag_days=30,
    )

    assert report["ok"] is True
    assert report["window_end"] == "2026-02-28"
