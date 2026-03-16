from __future__ import annotations

import sqlite3
from pathlib import Path

import openpyxl
import pandas as pd
import pytest

from scripts.classify_workbook_anchor_overages import classify_workbook_anchor_overages


def _write_workbook(path: Path, rows: list[tuple[str, str, float, float, str]]) -> None:
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
    for order_id, day, qty, net_rev, store in rows:
        ws.append([order_id, day, f"OFFER-{order_id}", qty, net_rev, net_rev, store])
    wb.save(path)


def _seed_sales_fact_v2(
    db_path: Path,
    rows: list[tuple[str, str, str, str, str, float, float, str, int]],
) -> None:
    conn = sqlite3.connect(db_path)
    conn.executescript(
        """
        CREATE TABLE sales_fact_v2 (
            order_id TEXT,
            order_date TEXT,
            sku_key TEXT,
            sku_id TEXT,
            store_code TEXT,
            quantity REAL,
            net_rev REAL,
            source_file TEXT,
            status TEXT,
            return_flag INTEGER,
            cogs REAL,
            profit REAL,
            my_size TEXT
        );
        """
    )
    conn.executemany(
        """
        INSERT INTO sales_fact_v2 (
            order_id, order_date, sku_key, sku_id, store_code, quantity, net_rev,
            source_file, status, return_flag, cogs, profit, my_size
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, 0, '')
        """,
        rows,
    )
    conn.commit()
    conn.close()


def _read_csv(path: Path) -> pd.DataFrame:
    return pd.read_csv(path)


def test_classify_workbook_anchor_overages_reconciles_bucket_totals(tmp_path: Path) -> None:
    db = tmp_path / "app.db"
    workbook = tmp_path / "crm.xlsx"
    output_dir = tmp_path / "out"

    _seed_sales_fact_v2(
        db,
        [
            (
                "ORD-DRIFT",
                "2026-02-05",
                "SKU_A",
                "SKU_A_L",
                "ACMEWEAR",
                1.0,
                100.0,
                "OCEAN_DROP_ANCHOR",
                "DELIVERED",
                0,
            ),
            (
                "ORD-OK",
                "2026-02-05",
                "SKU_B",
                "SKU_B_L",
                "ACMEWEAR",
                1.0,
                80.0,
                "KASPI_API_ENTRIES_REBUILD",
                "DELIVERED",
                0,
            ),
            (
                "ORD-SAME-DAY-OVER",
                "2026-02-05",
                "SKU_C",
                "SKU_C_L",
                "ACMEWEAR",
                1.0,
                70.0,
                "KASPI_API_ENTRIES_REBUILD",
                "DELIVERED",
                0,
            ),
        ],
    )
    _write_workbook(
        workbook,
        [
            ("ORD-OK", "2026-02-05", 1.0, 80.0, "ACMEWEAR"),
            ("ORD-SAME-DAY-OVER", "2026-02-05", 1.0, 50.0, "ACMEWEAR"),
            ("ORD-DRIFT", "2026-02-06", 1.0, 100.0, "ACMEWEAR"),
        ],
    )

    report = classify_workbook_anchor_overages(
        db_path=db,
        workbook_path=workbook,
        start="2026-02-05",
        end="2026-02-06",
        output_dir=output_dir,
        strict=True,
    )

    assert report["ok"] is True
    assert report["error_references_total"] == 2
    assert report["error_references_classified"] == 2

    days = _read_csv(output_dir / "workbook_overage_days.csv")
    assert days.loc[0, "date"] == "2026-02-05"
    assert days.loc[0, "units_overage"] == 1.0
    assert days.loc[0, "net_overage_kzt"] == 120.0
    assert days.loc[0, "unresolved_units_overage"] == 0.0
    assert days.loc[0, "unresolved_net_overage_kzt"] == 0.0

    source_mix = _read_csv(output_dir / "workbook_overage_source_mix.csv")
    units_mix = source_mix[["bucket", "attributed_units_overage"]].groupby("bucket").sum().to_dict()["attributed_units_overage"]
    net_mix = source_mix[["bucket", "attributed_net_overage_kzt"]].groupby("bucket").sum().to_dict()["attributed_net_overage_kzt"]
    assert units_mix["OCEAN_DROP_ANCHOR_DATE_DRIFT"] == 1.0
    assert net_mix["OCEAN_DROP_ANCHOR_DATE_DRIFT"] == 100.0
    assert net_mix["KASPI_REBUILD_SAME_DAY_VALUE_OVERAGE"] == 20.0

    lineage = _read_csv(output_dir / "workbook_overage_order_lineage.csv")
    assert set(lineage["pair_status"]) == {"MATCH_SAME_DAY", "ORDER_IN_WB_OTHER_DAY"}
    assert set(lineage["bucket"]) == {
        "OCEAN_DROP_ANCHOR_DATE_DRIFT",
        "KASPI_REBUILD_SAME_DAY_VALUE_OVERAGE",
        "KASPI_REBUILD_SAME_DAY_VALUE_OVERAGE",
    }

    unresolved = _read_csv(output_dir / "workbook_overage_unresolved.csv")
    assert unresolved.empty


def test_classify_workbook_anchor_overages_fails_closed_when_no_source_lineage_exists(tmp_path: Path) -> None:
    db = tmp_path / "app.db"
    workbook = tmp_path / "crm.xlsx"
    output_dir = tmp_path / "out"

    conn = sqlite3.connect(db)
    conn.executescript(
        """
        CREATE TABLE fact_sales (
            order_id TEXT,
            order_date TEXT,
            sku_key TEXT,
            sku_id TEXT,
            quantity REAL,
            line_net_rev REAL,
            cogs_line REAL,
            store_code TEXT,
            my_size TEXT
        );
        """
    )
    conn.execute(
        """
        INSERT INTO fact_sales (
            order_id, order_date, sku_key, sku_id, quantity, line_net_rev, cogs_line, store_code, my_size
        ) VALUES ('ORD-ONLY-FACT', '2026-02-05', 'SKU_A', 'SKU_A_L', 2, 200, 0, 'ACMEWEAR', 'L')
        """
    )
    conn.commit()
    conn.close()

    _write_workbook(
        workbook,
        [
            ("ORD-WB", "2026-02-05", 1.0, 50.0, "ACMEWEAR"),
        ],
    )

    with pytest.raises(RuntimeError, match="unresolved"):
        classify_workbook_anchor_overages(
            db_path=db,
            workbook_path=workbook,
            start="2026-02-05",
            end="2026-02-05",
            output_dir=output_dir,
            strict=True,
        )
