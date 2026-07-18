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


def test_anchor_dedupes_snapshot_rows_only_to_first_party_entry_quantity(
    tmp_path: Path,
) -> None:
    workbook = tmp_path / "crm.xlsx"
    db = tmp_path / "app.db"
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "SALES_KSP_CRM_1"
    ws.append(
        [
            "OrderID",
            "Date",
            "Quantity",
            "Total_price",
            "Total_net_rev",
            "STORE_NAME",
            "MY_SIZE",
            "SKU_ID_KSP",
        ]
    )
    ws.append(["D1", "2026-01-15", 1, 1000, 800, "ACMEWEAR", "XL", "ARTICLE-1"])
    ws.append(["D1", "2026-01-15", 1, 1000, 800, "ACMEWEAR", "", "ARTICLE-1"])
    ws.append(["D2", "2026-01-16", 2, 2000, 1600, "ACMEWEAR", "L", "ARTICLE-2"])
    ws.append(["D2", "2026-01-16", 2, 2000, 1600, "ACMEWEAR", "L", "ARTICLE-2"])
    ws.append(["D3", "2026-01-17", 1, 1000, 800, "ACMEWEAR", "L", "ARTICLE-3A"])
    ws.append(["D3", "2026-01-17", 1, 1200, 900, "ACMEWEAR", "XL", "ARTICLE-3B"])
    ws.append(["BAD", "2026-01-18", 1, 1000, 800, "ACMEWEAR", "L", "ARTICLE-B"])
    ws.append(["BAD", "2026-01-18", 1, 1000, 800, "ACMEWEAR", "", "ARTICLE-B"])
    wb.save(workbook)

    with sqlite3.connect(db) as conn:
        conn.execute(
            """
            CREATE TABLE fact_order_entries_kaspi (
                entry_id TEXT PRIMARY KEY,
                order_id TEXT,
                store_code TEXT,
                quantity REAL,
                raw_json TEXT
            )
            """
        )
        conn.executemany(
            """
            INSERT INTO fact_order_entries_kaspi
            (entry_id, order_id, store_code, quantity, raw_json)
            VALUES (?, ?, 'ACMEWEAR', ?, '{"type":"orderentries"}')
            """,
            [
                ("D1#0", "D1", 1),
                ("D2#0", "D2", 2),
                ("D3#0", "D3", 1),
                ("D3#1", "D3", 1),
                ("BAD#0", "BAD", 3),
            ],
        )

    report = sync_sales_workbook_anchor(
        db_path=db,
        workbook_path=workbook,
        apply=False,
    )
    rows, quarantine, summary = build_workbook_anchor_rows(
        workbook_path=workbook,
        first_party_entry_quantities={
            ("D1", "ACMEWEAR"): 1,
            ("D2", "ACMEWEAR"): 2,
            ("D3", "ACMEWEAR"): 2,
            ("BAD", "ACMEWEAR"): 3,
        },
    )

    assert {row["order_id"]: row["quantity"] for row in rows} == {
        "D1": 1.0,
        "D2": 2.0,
        "D3": 2.0,
    }
    assert quarantine[0]["order_id"] == "BAD"
    assert quarantine[0]["reason"] == "FIRST_PARTY_ENTRY_QUANTITY_MISMATCH"
    assert summary["deduplicated_snapshot_rows"] == 2
    assert summary["entry_quantity_mismatch_orders"] == 1
    assert report["deduplicated_snapshot_rows"] == 2
