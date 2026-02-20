import sqlite3
from pathlib import Path

import pandas as pd
import pytest

from scripts.sync_po_parts_from_inbound_calendar import sync_po_parts_from_workbook


def _create_test_db(db_path: Path) -> None:
    conn = sqlite3.connect(str(db_path))
    conn.execute(
        """
        CREATE TABLE po_header (
            po_id TEXT PRIMARY KEY,
            supplier_code TEXT DEFAULT 'SHR',
            message_date TEXT,
            ship_date_cargo TEXT,
            ast_arrival_nom TEXT,
            ast_arrival_real TEXT,
            status TEXT DEFAULT 'DRAFT',
            units_total INTEGER DEFAULT 0,
            total_cost_cny REAL DEFAULT 0,
            weight_nom_kg REAL DEFAULT 0,
            total_places INTEGER DEFAULT 0
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE po_part (
            po_part_id TEXT PRIMARY KEY,
            po_id TEXT NOT NULL,
            supplier_id TEXT,
            message_date TEXT,
            cargo_send_date TEXT,
            estimated_arrival_date TEXT,
            actual_arrival_date TEXT,
            status TEXT,
            total_sku_keys INTEGER DEFAULT 0,
            total_units INTEGER DEFAULT 0,
            base_cost_cny REAL DEFAULT 0,
            base_cost_kzt REAL DEFAULT 0,
            est_weight_kg REAL DEFAULT 0,
            est_delivery_usd REAL DEFAULT 0,
            total_bags INTEGER DEFAULT 0,
            qty_delta INTEGER DEFAULT 0,
            est_delivery_kzt REAL DEFAULT 0,
            is_paid_base INTEGER DEFAULT 0,
            is_paid_dlv INTEGER DEFAULT 0,
            to_pay_base_kzt REAL DEFAULT 0,
            to_pay_dlv_kzt REAL DEFAULT 0
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE po_line (
            po_line_id INTEGER PRIMARY KEY AUTOINCREMENT,
            po_id TEXT NOT NULL,
            po_part_id TEXT,
            sku_key TEXT NOT NULL,
            sku_id TEXT NOT NULL,
            my_size TEXT NOT NULL,
            order_qty INTEGER NOT NULL,
            received_qty INTEGER DEFAULT 0,
            unit_cost_cny REAL NOT NULL,
            status TEXT DEFAULT 'PENDING'
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE dim_sku (
            sku_key TEXT PRIMARY KEY,
            model TEXT NOT NULL,
            product_type TEXT NOT NULL,
            base_cost_cny REAL NOT NULL,
            weight_kg REAL NOT NULL,
            avg_sell_price_kzt_used REAL,
            avg_sell_price_source TEXT,
            active_flag INTEGER DEFAULT 1
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE dim_sku_size (
            sku_id TEXT PRIMARY KEY,
            sku_key TEXT NOT NULL,
            my_size TEXT NOT NULL,
            active_flag INTEGER DEFAULT 1
        )
        """
    )
    conn.commit()
    conn.close()


def _write_workbook(
    path: Path,
    *,
    suit_qty: int = 200,
    include_junk_part_rows: bool = False,
    po41_dlv_paid: str = "NO",
) -> None:
    inbounds = pd.DataFrame(
        [
            {
                "SKU Key": "CL_NEW-CLO2_MEN_SUIT-61_BLACK",
                "Size": "M",
                "message_date": "2026-01-21",
                "Order Qty_Approved": suit_qty,
                "PO_id": "PO-5",
                "PO_part_id": "PO-5.1",
                "cargo_send_date": "2026-02-04",
                "Estimated_Arrival_date": "2026-02-25",
                "Actual_Arrival_date": None,
                "Status": "Transit",
                "Last_update": "2026-02-07",
                "base_cost": 74,
                "PO Base (CNY)": suit_qty * 74,
                "Actual_qty": 0,
                "actual_PO_Base_(CNY)": 0,
                "supplier_id": "SHR",
            },
            {
                "SKU Key": "Bag_gift",
                "Size": "ONE_SIZE",
                "message_date": "2025-12-21",
                "Order Qty_Approved": 1000,
                "PO_id": "PO-4.1",
                "PO_part_id": "PO-4.1",
                "cargo_send_date": "2026-01-21",
                "Estimated_Arrival_date": "2026-02-11",
                "Actual_Arrival_date": "2026-02-05",
                "Status": "Arrived",
                "Last_update": "2026-02-07",
                "base_cost": 0,
                "PO Base (CNY)": 0,
                "Actual_qty": 1000,
                "actual_PO_Base_(CNY)": 0,
                "supplier_id": "SHR",
            },
            {
                "SKU Key": "CL_NC_MEN_RUSH-31_BLACK",
                "Size": "M",
                "message_date": "2026-02-04",
                "Order Qty_Approved": 30,
                "PO_id": "PO-6",
                "PO_part_id": "PO-6.0",
                "cargo_send_date": "2026-02-07",
                "Estimated_Arrival_date": "2026-02-28",
                "Actual_Arrival_date": None,
                "Status": "Transit",
                "Last_update": "2026-02-08",
                "base_cost": 67,
                "PO Base (CNY)": 2010,
                "Actual_qty": 0,
                "actual_PO_Base_(CNY)": 0,
                "supplier_id": "SHR",
            },
            {
                "SKU Key": "CL_OF_ARC_LINE31_SET_DARK",
                "Size": "S",
                "message_date": "2026-02-01",
                "Order Qty_Approved": 20,
                "PO_id": "PO_ARC-1",
                "PO_part_id": "ARC-1.0",
                "cargo_send_date": "2026-02-05",
                "Estimated_Arrival_date": "2026-02-20",
                "Actual_Arrival_date": "2026-02-19",
                "Status": "Arrived",
                "Last_update": "2026-02-07",
                "base_cost": 110,
                "PO Base (CNY)": 2200,
                "Actual_qty": 20,
                "actual_PO_Base_(CNY)": 2200,
                "supplier_id": "ARC",
            },
        ]
    )
    part_rows = [
            {
                "PO_part_id": "PO-5.1",
                "PO_id": "PO-5",
                "supplier_id": "SHR",
                "message_date": "2026-01-21",
                "cargo_send_date": "2026-02-04",
                "Estimated_Arrival_date": "2026-02-25",
                "Actual_Arrival_date": None,
                "Status": "Transit",
                "Total SKU Keys": 1,
                "Total Units": suit_qty,
                "Base_cost_CNY": suit_qty * 74,
                "Base_cost_KZT": suit_qty * 74 * 75,
                "Est. Weight (kg)": 516.6,
                "Est. Delivery (USD)": 2647.5,
                "Total Bags": 10,
                "Qty Delta": 0,
                "Est. Delivery (KZT)": 1376700,
                "is_paid_BASE": "NO",
                "is_paid_DLV": "NO",
                "To_pay_BASE_KZT": suit_qty * 74 * 75,
                "To_pay_DLV_KZT": 1376700,
            },
            {
                "PO_part_id": "PO-4.1",
                "PO_id": "PO-4.1",
                "supplier_id": "SHR",
                "message_date": "2025-12-21",
                "cargo_send_date": "2026-01-21",
                "Estimated_Arrival_date": "2026-02-11",
                "Actual_Arrival_date": "2026-02-05",
                "Status": "Arrived",
                "Total SKU Keys": 2,
                "Total Units": 1430,
                "Base_cost_CNY": 25610,
                "Base_cost_KZT": 1920750,
                "Est. Weight (kg)": 475.8,
                "Est. Delivery (USD)": 1290.0,
                "Total Bags": 13,
                "Qty Delta": 0,
                "Est. Delivery (KZT)": 670800,
                "is_paid_BASE": "YES",
                "is_paid_DLV": po41_dlv_paid,
                "To_pay_BASE_KZT": 0,
                "To_pay_DLV_KZT": 0 if po41_dlv_paid == "YES" else 670800,
            },
            {
                "PO_part_id": "PO-6.0",
                "PO_id": "PO-6",
                "supplier_id": "SHR",
                "message_date": "2026-02-04",
                "cargo_send_date": "2026-02-07",
                "Estimated_Arrival_date": "2026-02-28",
                "Actual_Arrival_date": None,
                "Status": "Transit",
                "Total SKU Keys": 1,
                "Total Units": 1710,
                "Base_cost_CNY": 15267,
                "Base_cost_KZT": 1145025,
                "Est. Weight (kg)": 326.6,
                "Est. Delivery (USD)": 885.6,
                "Total Bags": 11,
                "Qty Delta": 0,
                "Est. Delivery (KZT)": 460512,
                "is_paid_BASE": "NO",
                "is_paid_DLV": "NO",
                "To_pay_BASE_KZT": 1145025,
                "To_pay_DLV_KZT": 460512,
            },
            {
                "PO_part_id": "ARC-1.0",
                "PO_id": "PO_ARC-1",
                "supplier_id": "ARC",
                "message_date": "2026-02-01",
                "cargo_send_date": "2026-02-05",
                "Estimated_Arrival_date": "2026-02-20",
                "Actual_Arrival_date": "2026-02-19",
                "Status": "Arrived",
                "Total SKU Keys": 1,
                "Total Units": 20,
                "Base_cost_CNY": 2200,
                "Base_cost_KZT": 165000,
                "Est. Weight (kg)": 172.3,
                "Est. Delivery (USD)": 332.1,
                "Total Bags": 4,
                "Qty Delta": 0,
                "Est. Delivery (KZT)": 172700,
                "is_paid_BASE": "NO",
                "is_paid_DLV": "NO",
                "To_pay_BASE_KZT": 165000,
                "To_pay_DLV_KZT": 172700,
            },
        ]
    if include_junk_part_rows:
        part_rows.extend(
            [
                {
                    "PO_part_id": "TOTAL PENDING",
                    "PO_id": "nan",
                    "supplier_id": "",
                    "message_date": None,
                    "cargo_send_date": None,
                    "Estimated_Arrival_date": None,
                    "Actual_Arrival_date": None,
                    "Status": "",
                    "Total SKU Keys": 0,
                    "Total Units": 9999,
                    "Base_cost_CNY": 0,
                    "Base_cost_KZT": 0,
                    "Est. Weight (kg)": 0,
                    "Est. Delivery (USD)": 0,
                    "Total Bags": 0,
                    "Qty Delta": 0,
                    "Est. Delivery (KZT)": 0,
                    "is_paid_BASE": "",
                    "is_paid_DLV": "",
                    "To_pay_BASE_KZT": 0,
                    "To_pay_DLV_KZT": 0,
                },
                {
                    "PO_part_id": "PENDING PAYMENTS",
                    "PO_id": "4",
                    "supplier_id": "",
                    "message_date": None,
                    "cargo_send_date": None,
                    "Estimated_Arrival_date": None,
                    "Actual_Arrival_date": None,
                    "Status": "",
                    "Total SKU Keys": 0,
                    "Total Units": 1234,
                    "Base_cost_CNY": 0,
                    "Base_cost_KZT": 0,
                    "Est. Weight (kg)": 0,
                    "Est. Delivery (USD)": 0,
                    "Total Bags": 0,
                    "Qty Delta": 0,
                    "Est. Delivery (KZT)": 0,
                    "is_paid_BASE": "",
                    "is_paid_DLV": "",
                    "To_pay_BASE_KZT": 0,
                    "To_pay_DLV_KZT": 0,
                },
            ]
        )
    part_totals = pd.DataFrame(part_rows)
    dim_sku_light = pd.DataFrame(
        [
            {"SKU_key": "CL_OF_ARC_LINE31_SET_DARK", "Type": "CL", "Wt (kg)": 0.9, "CNY": 110, "AvgPrc": 26990},
            {"SKU_key": "CL_NEW-CLO2_MEN_SUIT-61_BLACK", "Type": "CL", "Wt (kg)": 1.0, "CNY": 74, "AvgPrc": 25990},
        ]
    )

    with pd.ExcelWriter(path, engine="openpyxl") as writer:
        inbounds.to_excel(writer, sheet_name="Inbounds_sheet", index=False)
        part_totals.to_excel(writer, sheet_name="PO_part_id_Totals", index=False)
        dim_sku_light.to_excel(writer, sheet_name="DIM_SKU_light_v5", index=False)


def _count(conn: sqlite3.Connection, table: str) -> int:
    return int(conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])


def test_dry_run_no_writes_without_apply(tmp_path: Path) -> None:
    db_path = tmp_path / "app.db"
    xlsx_path = tmp_path / "inbound.xlsx"
    _create_test_db(db_path)
    _write_workbook(xlsx_path)

    summary = sync_po_parts_from_workbook(xlsx_path=xlsx_path, db_path=db_path, apply=False)

    conn = sqlite3.connect(str(db_path))
    try:
        assert summary["apply"] is False
        assert _count(conn, "po_header") == 0
        assert _count(conn, "po_part") == 0
        assert _count(conn, "po_line") == 0
    finally:
        conn.close()


def test_apply_requires_env_gate(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    db_path = tmp_path / "app.db"
    xlsx_path = tmp_path / "inbound.xlsx"
    _create_test_db(db_path)
    _write_workbook(xlsx_path)
    monkeypatch.delenv("ENABLE_PO_PART_SYNC_WRITE", raising=False)

    with pytest.raises(RuntimeError, match="ENABLE_PO_PART_SYNC_WRITE=1"):
        sync_po_parts_from_workbook(xlsx_path=xlsx_path, db_path=db_path, apply=True)


def test_apply_upserts_po_header_po_part_po_line_with_part_ids(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    db_path = tmp_path / "app.db"
    xlsx_path = tmp_path / "inbound.xlsx"
    _create_test_db(db_path)
    _write_workbook(xlsx_path, suit_qty=215)
    monkeypatch.setenv("ENABLE_PO_PART_SYNC_WRITE", "1")

    summary = sync_po_parts_from_workbook(xlsx_path=xlsx_path, db_path=db_path, apply=True)

    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    try:
        assert summary["apply"] is True
        assert _count(conn, "po_header") == 4
        assert _count(conn, "po_part") == 4
        assert _count(conn, "po_line") == 4
        row = conn.execute(
            "SELECT order_qty, po_part_id, status FROM po_line WHERE po_id='PO-5' AND sku_key='CL_NEW-CLO2_MEN_SUIT-61_BLACK'"
        ).fetchone()
        assert row is not None
        assert row["order_qty"] == 215
        assert row["po_part_id"] == "PO-5.1"
        assert row["status"] == "IN_TRANSIT"
    finally:
        conn.close()


def test_existing_rows_update_not_duplicate(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    db_path = tmp_path / "app.db"
    xlsx_path = tmp_path / "inbound.xlsx"
    _create_test_db(db_path)
    _write_workbook(xlsx_path, suit_qty=200)
    monkeypatch.setenv("ENABLE_PO_PART_SYNC_WRITE", "1")

    sync_po_parts_from_workbook(xlsx_path=xlsx_path, db_path=db_path, apply=True)
    _write_workbook(xlsx_path, suit_qty=240)
    sync_po_parts_from_workbook(xlsx_path=xlsx_path, db_path=db_path, apply=True)

    conn = sqlite3.connect(str(db_path))
    try:
        assert _count(conn, "po_line") == 4
        qty = conn.execute(
            "SELECT order_qty FROM po_line WHERE po_id='PO-5' AND sku_key='CL_NEW-CLO2_MEN_SUIT-61_BLACK' AND my_size='M'"
        ).fetchone()[0]
        assert qty == 240
    finally:
        conn.close()


def test_arc_skus_upsert_with_target_price_from_dim_sheet(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    db_path = tmp_path / "app.db"
    xlsx_path = tmp_path / "inbound.xlsx"
    _create_test_db(db_path)
    _write_workbook(xlsx_path)
    monkeypatch.setenv("ENABLE_PO_PART_SYNC_WRITE", "1")

    sync_po_parts_from_workbook(xlsx_path=xlsx_path, db_path=db_path, apply=True)

    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    try:
        row = conn.execute(
            "SELECT avg_sell_price_kzt_used, avg_sell_price_source FROM dim_sku WHERE sku_key='CL_OF_ARC_LINE31_SET_DARK'"
        ).fetchone()
        assert row is not None
        assert row["avg_sell_price_kzt_used"] == 26990
        assert row["avg_sell_price_source"] == "INBOUND_CALENDAR_V10.002"
    finally:
        conn.close()


def test_parts_sheet_skips_summary_rows(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    db_path = tmp_path / "app.db"
    xlsx_path = tmp_path / "inbound.xlsx"
    _create_test_db(db_path)
    _write_workbook(xlsx_path, include_junk_part_rows=True)
    monkeypatch.setenv("ENABLE_PO_PART_SYNC_WRITE", "1")

    sync_po_parts_from_workbook(xlsx_path=xlsx_path, db_path=db_path, apply=True)

    conn = sqlite3.connect(str(db_path))
    try:
        rows = conn.execute("SELECT po_part_id, po_id FROM po_part ORDER BY po_part_id").fetchall()
        po_part_ids = {row[0] for row in rows}
        assert po_part_ids == {"ARC-1.0", "PO-4.1", "PO-5.1", "PO-6.0"}
    finally:
        conn.close()


def test_sync_parses_yes_no_paid_flags(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    db_path = tmp_path / "app.db"
    xlsx_path = tmp_path / "inbound.xlsx"
    _create_test_db(db_path)
    _write_workbook(xlsx_path, po41_dlv_paid="YES")
    monkeypatch.setenv("ENABLE_PO_PART_SYNC_WRITE", "1")

    sync_po_parts_from_workbook(xlsx_path=xlsx_path, db_path=db_path, apply=True)

    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    try:
        row = conn.execute(
            "SELECT is_paid_base, is_paid_dlv, to_pay_base_kzt, to_pay_dlv_kzt FROM po_part WHERE po_part_id='PO-4.1'"
        ).fetchone()
        assert row is not None
        assert int(row["is_paid_base"]) == 1
        assert int(row["is_paid_dlv"]) == 1
        assert float(row["to_pay_base_kzt"] or 0.0) == 0.0
        assert float(row["to_pay_dlv_kzt"] or 0.0) == 0.0
    finally:
        conn.close()


def test_sync_backfills_po_header_weight_and_total_places_from_part_totals(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    db_path = tmp_path / "app.db"
    xlsx_path = tmp_path / "inbound.xlsx"
    _create_test_db(db_path)
    _write_workbook(xlsx_path)
    monkeypatch.setenv("ENABLE_PO_PART_SYNC_WRITE", "1")

    sync_po_parts_from_workbook(xlsx_path=xlsx_path, db_path=db_path, apply=True)

    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    try:
        row = conn.execute(
            "SELECT weight_nom_kg, total_places FROM po_header WHERE po_id='PO-6'"
        ).fetchone()
        assert row is not None
        assert float(row["weight_nom_kg"] or 0.0) == 326.6
        assert int(row["total_places"] or 0) == 11
    finally:
        conn.close()
