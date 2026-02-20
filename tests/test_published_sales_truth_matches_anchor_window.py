import sqlite3
from pathlib import Path

import openpyxl

from scripts.validate_sales_against_workbook import validate_sales_against_workbook


def _seed_db(db_path: Path, rows: list[tuple[str, str, str, str, float, float]]) -> None:
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
        VALUES (?, ?, ?, ?, ?, ?, 0, 'DELIVERED', 0)
        """,
        rows,
    )
    conn.commit()
    conn.close()


def _write_anchor(workbook: Path, rows: list[tuple[str, float, float]]) -> None:
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "SALES_KSP_CRM_1"
    ws.append(
        [
            "OrderID",
            "Date",
            "KASPI_OFFER_NAME",
            "Quantity",
            "Total_price",
            "Total_net_rev",
            "STORE_NAME",
        ]
    )
    idx = 1
    for day, units, net_rev in rows:
        ws.append([f"ORD-{idx}", day, f"SKU-{idx}", units, net_rev, net_rev, "ACMEWEAR"])
        idx += 1
    wb.save(workbook)


def test_validate_sales_against_workbook_passes_within_tolerance(tmp_path: Path) -> None:
    db = tmp_path / "app.db"
    workbook = tmp_path / "crm.xlsx"
    _seed_db(
        db,
        [
            ("O1", "2026-02-05", "SKU_A", "SKU_A_M", 10.0, 100000.0),
            ("O2", "2026-02-06", "SKU_A", "SKU_A_M", 9.6, 95000.0),
        ],
    )
    _write_anchor(
        workbook,
        [
            ("2026-02-05", 10.0, 100000.0),
            ("2026-02-06", 10.0, 100000.0),
        ],
    )

    report = validate_sales_against_workbook(
        db_path=db,
        workbook_path=workbook,
        days=14,
        tol_pct=5.0,
        as_of="2026-02-08",
        min_overlap_days=2,
        max_lag_days=7,
    )
    assert report["ok"] is True
    assert report["overlap_days"] == 2


def test_validate_sales_against_workbook_fails_when_published_exceeds_by_gt_5pct(tmp_path: Path) -> None:
    db = tmp_path / "app.db"
    workbook = tmp_path / "crm.xlsx"
    _seed_db(
        db,
        [
            ("O1", "2026-02-05", "SKU_A", "SKU_A_M", 12.0, 120000.0),
        ],
    )
    _write_anchor(workbook, [("2026-02-05", 10.0, 100000.0)])

    report = validate_sales_against_workbook(
        db_path=db,
        workbook_path=workbook,
        days=14,
        tol_pct=5.0,
        as_of="2026-02-08",
        min_overlap_days=1,
        max_lag_days=7,
    )
    assert report["ok"] is False
    assert any("published exceeds workbook" in err for err in report["errors"])


def test_validate_sales_against_workbook_uses_min_window_end(tmp_path: Path) -> None:
    db = tmp_path / "app.db"
    workbook = tmp_path / "crm.xlsx"
    _seed_db(
        db,
        [
            ("O1", "2026-02-05", "SKU_A", "SKU_A_M", 10.0, 100000.0),
            ("O2", "2026-02-07", "SKU_A", "SKU_A_M", 5.0, 50000.0),
        ],
    )
    _write_anchor(workbook, [("2026-02-05", 10.0, 100000.0), ("2026-02-06", 9.0, 90000.0)])

    report = validate_sales_against_workbook(
        db_path=db,
        workbook_path=workbook,
        days=14,
        tol_pct=5.0,
        as_of="2026-02-10",
        min_overlap_days=1,
        max_lag_days=7,
    )
    assert report["window_end"] == "2026-02-06"


def test_validate_sales_against_workbook_fails_when_overlap_below_min_required(tmp_path: Path) -> None:
    db = tmp_path / "app.db"
    workbook = tmp_path / "crm.xlsx"
    _seed_db(
        db,
        [
            ("O1", "2026-02-05", "SKU_A", "SKU_A_M", 10.0, 100000.0),
        ],
    )
    _write_anchor(workbook, [("2026-02-05", 10.0, 100000.0)])

    report = validate_sales_against_workbook(
        db_path=db,
        workbook_path=workbook,
        days=14,
        tol_pct=5.0,
        as_of="2026-02-08",
        min_overlap_days=3,
        max_lag_days=7,
    )
    assert report["ok"] is False
    assert any("overlap days below minimum" in err for err in report["errors"])
