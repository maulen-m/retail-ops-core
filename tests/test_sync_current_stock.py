from __future__ import annotations

import sqlite3
from pathlib import Path

import pandas as pd
import pytest

from scripts.sync_current_stock import (
    DEFAULT_INBOUND_SHEET,
    DEFAULT_STOCK_SHEET,
    load_inbound_transit_map,
    load_stock_snapshot_rows,
    merge_stock_and_inbound_rows,
    sync_stock_from_excel,
)


def _write_stock_workbook(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    df = pd.DataFrame(
        [
            {
                "SKU_key": "SKU_A",
                "MY_SIZE": "M",
                "Snapshot_date": "2026-02-19",
                "Cutoff_sales_date": "2026-02-18",
                "Stock_snapshot": 12,
                "Inbound_transit": 5,
                "Total_stock": 17,
            },
            {
                "SKU_key": "SKU_B",
                "MY_SIZE": "L",
                "Snapshot_date": "2026-02-19",
                "Cutoff_sales_date": "2026-02-18",
                "Stock_snapshot": 8,
                "Inbound_transit": 0,
                "Total_stock": 8,
            },
        ]
    )
    with pd.ExcelWriter(path, engine="openpyxl") as writer:
        df.to_excel(writer, sheet_name=DEFAULT_STOCK_SHEET, index=False)


def _write_inbound_workbook(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    df = pd.DataFrame(
        [
            {
                "SKU Key": "SKU_A",
                "Size": "M",
                "Status": "Transit",
                "Actual_qty": 9,
                "Order Qty_Approved": 9,
            },
            {
                "SKU Key": "SKU_B",
                "Size": "L",
                "Status": "Arrived",
                "Actual_qty": 50,
                "Order Qty_Approved": 50,
            },
            {
                "SKU Key": "Bag_gift",
                "Size": "ONE_SIZE",
                "Status": "Transit",
                "Actual_qty": 1000,
                "Order Qty_Approved": 1000,
            },
        ]
    )
    with pd.ExcelWriter(path, engine="openpyxl") as writer:
        df.to_excel(writer, sheet_name=DEFAULT_INBOUND_SHEET, index=False)


def _bootstrap_db(db_path: Path) -> None:
    conn = sqlite3.connect(str(db_path))
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS fact_inventory_snapshot_size (
            snapshot_date TEXT NOT NULL,
            sku_id TEXT,
            sku_key TEXT NOT NULL,
            my_size TEXT NOT NULL,
            current_stock INTEGER NOT NULL,
            inbound_stock INTEGER NOT NULL DEFAULT 0
        )
        """
    )
    conn.commit()
    conn.close()


def test_merge_stock_and_inbound_prefers_stock_snapshot_for_current_and_inbound_sheet_for_transit(
    tmp_path: Path,
) -> None:
    stock_path = tmp_path / "stock.xlsx"
    inbound_path = tmp_path / "inbound.xlsx"
    _write_stock_workbook(stock_path)
    _write_inbound_workbook(inbound_path)

    stock_rows = load_stock_snapshot_rows(stock_path)
    inbound_map = load_inbound_transit_map(inbound_path)

    merged = merge_stock_and_inbound_rows(stock_rows, inbound_map)

    by_key = {(row["sku_key"], row["my_size"]): row for row in merged}
    assert by_key[("SKU_A", "M")]["current_stock"] == 12
    assert by_key[("SKU_A", "M")]["inbound_stock"] == 9
    assert by_key[("SKU_B", "L")]["inbound_stock"] == 0
    assert by_key[("Bag_gift", "ONE_SIZE")]["current_stock"] == 0
    assert by_key[("Bag_gift", "ONE_SIZE")]["inbound_stock"] == 1000


def test_load_stock_snapshot_rows_requires_stock_snapshot_column(tmp_path: Path) -> None:
    stock_path = tmp_path / "stock_bad.xlsx"
    stock_path.parent.mkdir(parents=True, exist_ok=True)
    df = pd.DataFrame(
        [
            {
                "SKU_key": "SKU_A",
                "MY_SIZE": "M",
                "Snapshot_date": "2026-02-19",
            }
        ]
    )
    with pd.ExcelWriter(stock_path, engine="openpyxl") as writer:
        df.to_excel(writer, sheet_name=DEFAULT_STOCK_SHEET, index=False)

    with pytest.raises(ValueError, match="missing required columns"):
        load_stock_snapshot_rows(stock_path)


def test_sync_stock_from_excel_apply_requires_env_gate(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    stock_path = tmp_path / "stock.xlsx"
    inbound_path = tmp_path / "inbound.xlsx"
    db_path = tmp_path / "app.db"
    _write_stock_workbook(stock_path)
    _write_inbound_workbook(inbound_path)
    _bootstrap_db(db_path)
    monkeypatch.delenv("ENABLE_STOCK_SNAPSHOT_WRITE", raising=False)

    with pytest.raises(RuntimeError, match="ENABLE_STOCK_SNAPSHOT_WRITE=1"):
        sync_stock_from_excel(
            excel_path=str(stock_path),
            inbound_path=str(inbound_path),
            db_path=str(db_path),
            apply=True,
        )
