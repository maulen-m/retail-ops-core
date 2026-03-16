from __future__ import annotations

import sqlite3
from pathlib import Path

import openpyxl

from scripts.sync_sales_workbook_anchor import build_workbook_anchor_rows, sync_sales_workbook_anchor


def _write_workbook(path: Path, rows: list[tuple]) -> None:
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
            "Статус",
        ]
    )
    for row in rows:
        order_id, day, qty, net_rev, store = row[:5]
        status = row[5] if len(row) > 5 else "ЗАВЕРШЕН"
        ws.append([order_id, day, f"OFFER-{order_id}", qty, net_rev, net_rev, store, status])
    wb.save(path)


def test_build_workbook_anchor_rows_groups_order_level_and_quarantines_multi_date(tmp_path: Path) -> None:
    workbook = tmp_path / "crm.xlsx"
    _write_workbook(
        workbook,
        [
            ("ORD-1", "2026-02-05", 1.0, 80.0, "ACMEWEAR"),
            ("ORD-1", "2026-02-05", 2.0, 160.0, "ACMEWEAR"),
            ("ORD-2", "2026-02-05", 1.0, 50.0, "ACMEWEAR"),
            ("ORD-2", "2026-02-06", 1.0, 50.0, "ACMEWEAR"),
        ],
    )

    rows, quarantine, summary = build_workbook_anchor_rows(workbook_path=workbook)

    assert rows == [
        {
            "order_id": "ORD-1",
            "store_code": "ACMEWEAR",
            "sale_date": "2026-02-05",
            "quantity": 3.0,
            "net_rev_kzt": 240.0,
            "total_price_kzt": 240.0,
            "source_file": str(workbook.resolve()),
        }
    ]
    assert len(quarantine) == 1
    assert quarantine[0]["order_id"] == "ORD-2"
    assert quarantine[0]["sale_dates"] == "2026-02-05|2026-02-06"
    assert summary["accepted_orders"] == 1
    assert summary["quarantined_orders"] == 1


def test_sync_sales_workbook_anchor_is_idempotent(tmp_path: Path) -> None:
    workbook = tmp_path / "crm.xlsx"
    db = tmp_path / "app.db"
    _write_workbook(
        workbook,
        [
            ("ORD-1", "2026-02-05", 1.0, 80.0, "ACMEWEAR"),
            ("ORD-2", "2026-02-06", 2.0, 140.0, "ACMEWEAR"),
        ],
    )

    first = sync_sales_workbook_anchor(db_path=db, workbook_path=workbook, apply=True)
    second = sync_sales_workbook_anchor(db_path=db, workbook_path=workbook, apply=True)

    conn = sqlite3.connect(db)
    rows = conn.execute(
        """
        SELECT order_id, store_code, sale_date, quantity, net_rev_kzt, total_price_kzt
        FROM fact_sales_workbook_anchor
        ORDER BY order_id
        """
    ).fetchall()
    conn.close()

    assert first["applied_rows"] == 2
    assert second["applied_rows"] == 2
    assert rows == [
        ("ORD-1", "ACMEWEAR", "2026-02-05", 1.0, 80.0, 80.0),
        ("ORD-2", "ACMEWEAR", "2026-02-06", 2.0, 140.0, 140.0),
    ]
