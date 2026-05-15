import sqlite3
from pathlib import Path

import pandas as pd
import pytest

from scripts.sync_po_parts_from_inbound_calendar import sync_po_parts_from_workbook


def _init_db(db_path: Path) -> None:
    conn = sqlite3.connect(str(db_path))
    conn.executescript(
        """
        CREATE TABLE po_header (
            po_id TEXT PRIMARY KEY,
            supplier_code TEXT,
            message_date TEXT,
            ship_date_cargo TEXT,
            ast_arrival_nom TEXT,
            ast_arrival_real TEXT,
            status TEXT,
            units_total INTEGER,
            total_cost_cny REAL,
            weight_nom_kg REAL,
            total_places INTEGER
        );
        CREATE TABLE po_part (
            po_part_id TEXT PRIMARY KEY,
            po_id TEXT,
            supplier_id TEXT,
            message_date TEXT,
            cargo_send_date TEXT,
            estimated_arrival_date TEXT,
            actual_arrival_date TEXT,
            status TEXT,
            total_units INTEGER,
            base_cost_cny REAL,
            est_weight_kg REAL,
            total_bags INTEGER
        );
        CREATE TABLE po_line (
            po_line_id INTEGER PRIMARY KEY AUTOINCREMENT,
            po_id TEXT,
            po_part_id TEXT,
            sku_key TEXT,
            sku_id TEXT,
            my_size TEXT,
            order_qty INTEGER,
            received_qty INTEGER,
            unit_cost_cny REAL,
            status TEXT
        );
        CREATE TABLE dim_sku (
            sku_key TEXT PRIMARY KEY,
            model TEXT,
            product_type TEXT,
            base_cost_cny REAL,
            weight_kg REAL,
            avg_sell_price_kzt_used REAL,
            avg_sell_price_source TEXT,
            active_flag INTEGER
        );
        CREATE TABLE dim_sku_size (
            sku_id TEXT PRIMARY KEY,
            sku_key TEXT,
            my_size TEXT,
            active_flag INTEGER
        );
        """
    )
    conn.execute(
        """
        INSERT INTO dim_sku (
            sku_key, model, product_type, base_cost_cny, weight_kg,
            avg_sell_price_kzt_used, avg_sell_price_source, active_flag
        ) VALUES ('CL_OC_MEN_LINE52_BLACK', 'LINE52', 'CL', 47, 0.95, 0, '', 1)
        """
    )
    conn.commit()
    conn.close()


def _write_workbook(path: Path) -> None:
    inbounds = pd.DataFrame(
        [
            {
                "SKU Key": "CL_OC_MEN_LINE52_BLACK",
                "Size": "M",
                "message_date": "2026-01-21",
                "Order Qty_Approved": 100,
                "PO_id": "PO-5",
                "PO_part_id": "PO-5.1",
                "cargo_send_date": "2026-01-30",
                "Estimated_Arrival_date": "2026-02-20",
                "Actual_Arrival_date": None,
                "Status": "Transit",
                "base_cost": 47,
                "PO Base (CNY)": 4700,
                "Actual_qty": 0,
                "supplier_id": "SHR",
            }
        ]
    )
    part_totals = pd.DataFrame(
        [
            {
                "PO_part_id": "PO-5.1",
                "PO_id": "PO-5",
                "supplier_id": "SHR",
                "Cargo_freight_id": "",
                "message_date": "2026-01-21",
                "cargo_send_date": "2026-01-30",
                "Estimated_Arrival_date": "2026-02-20",
                "Actual_Arrival_date": None,
                "Actual_DLV_PAY_date": None,
                "Status": "Transit",
                "Total SKU Keys": 1,
                "Total Units": 100,
                "Base_cost_CNY": 4700,
                "Base_cost_KZT": 352500,
                "Est. Weight (kg)": 95,
                "Est. Delivery (USD)": 252,
                "Total Bags": 8,
                "Qty Delta": 0,
                "Est. Delivery (KZT)": 131040,
                "Actual_Weight_kg": 0.0,
                "Paid_DLV_USD": 0.0,
                "Paid_DLV_KZT": 0.0,
                "Final_USD_per_kg": 0.0,
                "USD_KZT_rate": 0.0,
                "Actual_DLV_days": 0,
                "is_paid_BASE": "NO",
                "is_paid_DLV": "NO",
                "To_pay_BASE_KZT": 352500,
                "To_pay_DLV_KZT": 131040,
            }
        ]
    )
    dim_sheet = pd.DataFrame(
        [
            {
                "SKU_key": "CL_OC_MEN_LINE52_BLACK",
                "Type": "CL",
                "Wt (kg)": 0.07,
                "CNY": 0.19,
                "AvgPrc": 0.2,
            }
        ]
    )
    with pd.ExcelWriter(path, engine="openpyxl") as writer:
        inbounds.to_excel(writer, sheet_name="Inbounds_sheet", index=False)
        part_totals.to_excel(writer, sheet_name="PO_part_id_Totals", index=False)
        dim_sheet.to_excel(writer, sheet_name="DIM_SKU_light_v7", index=False)


def test_po_parts_sync_does_not_overwrite_dim_sku_weight_from_embedded_sheet_by_default(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    db_path = tmp_path / "app.db"
    xlsx_path = tmp_path / "inbound.xlsx"
    _init_db(db_path)
    _write_workbook(xlsx_path)
    monkeypatch.setenv("ENABLE_PO_PART_SYNC_WRITE", "1")

    sync_po_parts_from_workbook(xlsx_path=xlsx_path, db_path=db_path, apply=True)

    conn = sqlite3.connect(str(db_path))
    weight = conn.execute(
        "SELECT weight_kg FROM dim_sku WHERE sku_key='CL_OC_MEN_LINE52_BLACK'"
    ).fetchone()[0]
    conn.close()
    assert float(weight) == 0.95
