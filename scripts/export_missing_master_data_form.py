#!/usr/bin/env python3
"""
Generate an editable XLSX form for missing master data.

Reads missing SKUs from report_missing_master_data and writes an Excel file
with current values + blank fill-in columns for updates.
"""
from __future__ import annotations

import argparse
import sqlite3
import sys
from datetime import date
from pathlib import Path
from typing import Any

import pandas as pd

PROJECT_ROOT = Path(__file__).parent.parent
SCRIPT_DIR = Path(__file__).parent
sys.path.insert(0, str(SCRIPT_DIR))

from report_missing_master_data import (  # noqa: E402
    DB_PATH,
    EXPORTS_DIR,
    get_missing_master_data,
)


def _load_dim_sku_values(db_path: Path, sku_keys: list[str]) -> dict[str, dict[str, Any]]:
    if not sku_keys:
        return {}
    placeholders = ",".join("?" for _ in sku_keys)
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    cols = {row[1] for row in conn.execute("PRAGMA table_info(dim_sku)").fetchall()}
    has_price = "kaspi_price_kzt" in cols
    has_supplier = "supplier_code" in cols
    has_avg_price = "avg_sell_price_kzt_used" in cols

    price_expr = "kaspi_price_kzt" if has_price else ("avg_sell_price_kzt_used" if has_avg_price else "0")
    supplier_expr = "supplier_code" if has_supplier else "NULL"

    query = (
        "SELECT sku_key, weight_kg, base_cost_cny, cogs_kzt, "
        f"{price_expr} as kaspi_price_kzt, {supplier_expr} as supplier_code "
        f"FROM dim_sku WHERE sku_key IN ({placeholders})"
    )
    rows = conn.execute(query, sku_keys).fetchall()
    conn.close()
    return {
        row["sku_key"]: {
            "weight_kg": row["weight_kg"],
            "base_cost_cny": row["base_cost_cny"],
            "cogs_kzt": row["cogs_kzt"],
            "kaspi_price_kzt": row["kaspi_price_kzt"],
            "supplier_code": row["supplier_code"],
        }
        for row in rows
    }


def build_form_df(db_path: Path, field_filter: str | None = None) -> pd.DataFrame:
    report = get_missing_master_data(db_path, field_filter)
    sku_keys = [sku.sku_key for sku in report.sku_details]
    current = _load_dim_sku_values(db_path, sku_keys)

    rows = []
    for sku in report.sku_details:
        cur = current.get(sku.sku_key, {})
        rows.append({
            "sku_key": sku.sku_key,
            "sku_id": sku.sku_id,
            "product_name": sku.product_name,
            "missing_fields": ", ".join(sku.missing_fields),
            "proposed_spend_kzt": round(sku.proposed_spend_kzt, 2),
            "daily_demand": round(sku.daily_demand, 4),
            "blocked_reason": sku.blocked_reason,
            "current_weight_kg": cur.get("weight_kg") or 0,
            "current_base_cost_cny": cur.get("base_cost_cny") or 0,
            "current_cogs_kzt": cur.get("cogs_kzt") or 0,
            "current_kaspi_price_kzt": cur.get("kaspi_price_kzt") or 0,
            "current_supplier_code": cur.get("supplier_code") or "",
            "fill_weight_kg": "",
            "fill_base_cost_cny": "",
            "fill_cogs_kzt": "",
            "fill_kaspi_price_kzt": "",
            "fill_supplier_code": "",
            "notes": "",
        })

    return pd.DataFrame(rows)


def main() -> int:
    parser = argparse.ArgumentParser(description="Export missing master data XLSX form")
    parser.add_argument("--db", type=str, help="Database path")
    parser.add_argument("--field", type=str, choices=["weight", "cost", "price", "supplier"],
                        help="Filter by missing field")
    parser.add_argument("--output", type=str, help="Output XLSX path")
    args = parser.parse_args()

    db_path = Path(args.db) if args.db else DB_PATH
    df = build_form_df(db_path, args.field)

    EXPORTS_DIR.mkdir(parents=True, exist_ok=True)
    default_name = f"missing_master_data_form_{date.today().isoformat()}.xlsx"
    output_path = Path(args.output) if args.output else (EXPORTS_DIR / default_name)

    df.to_excel(output_path, index=False, engine="openpyxl")

    print(f"Rows: {len(df)}")
    print(f"Output: {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
