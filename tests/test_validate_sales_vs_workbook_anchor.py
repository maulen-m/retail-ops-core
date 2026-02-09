import sqlite3
from pathlib import Path

import openpyxl

from scripts.validate_sales_vs_workbook_anchor import validate_sales_vs_workbook_anchor


def _seed_v2(db_path: Path, rows: list[tuple[str, str, float, float]]) -> None:
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
    conn.executemany(
        """
        INSERT INTO sales_fact_v2
        (order_id, order_date, sku_key, sku_id, quantity, net_rev, cogs, status, return_flag)
        VALUES (?, ?, 'SKU_A', 'SKU_A_M', ?, ?, 0, 'DELIVERED', 0)
        """,
        rows,
    )
    conn.commit()
    conn.close()


def _write_workbook(path: Path, rows: list[tuple[str, float, float]]) -> None:
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "SALES_KSP_CRM_1"
    ws.append(["Date", "Quantity", "Total_net_rev"])
    for day, units, net_rev in rows:
        ws.append([day, units, net_rev])
    wb.save(path)


def test_validator_allows_db_below_workbook_by_more_than_5pct(tmp_path: Path) -> None:
    db = tmp_path / "app.db"
    wb = tmp_path / "crm.xlsx"
    _seed_v2(db, [("O1", "2026-02-08", 80.0, 80000.0)])
    _write_workbook(wb, [("2026-02-08", 100.0, 100000.0)])

    report = validate_sales_vs_workbook_anchor(
        db_path=db,
        workbook_path=wb,
        days=14,
        tol_pct=5.0,
        as_of="2026-02-08",
        min_overlap_days=1,
    )
    assert report["ok"] is True


def test_validator_fails_when_db_exceeds_workbook_by_gt_5pct(tmp_path: Path) -> None:
    db = tmp_path / "app.db"
    wb = tmp_path / "crm.xlsx"
    _seed_v2(db, [("O1", "2026-02-08", 106.0, 106000.0)])
    _write_workbook(wb, [("2026-02-08", 100.0, 100000.0)])

    report = validate_sales_vs_workbook_anchor(
        db_path=db,
        workbook_path=wb,
        days=14,
        tol_pct=5.0,
        as_of="2026-02-08",
        min_overlap_days=1,
    )
    assert report["ok"] is False
    assert any("published exceeds workbook" in err for err in report["errors"])
