#!/usr/bin/env python3
"""
Sync sales_fact_v2 from combined CRM + Fact_Sales sources.

Rule: CRM rows override Fact_Sales on overlap (same order_id + sku_id + store_code).
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

import sqlite3
import subprocess

import pandas as pd

from core.analytics.sales_sources import load_crm_sales, load_fact_sales, merge_sales_sources, SALES_COLUMNS
from core.paths import data_path

DEFAULT_CRM = data_path("excel_ui", "SALES_KSP_CRM_V3.xlsx")
DEFAULT_FACT = data_path("excel", "Inventory_Core_V18.1_V2.xlsx")
DEFAULT_DB = data_path("db", "app.db")


def main() -> None:
    parser = argparse.ArgumentParser(description="Sync sales_fact_v2 from CRM + Fact_Sales")
    parser.add_argument("--crm-file", type=Path, default=DEFAULT_CRM)
    parser.add_argument("--crm-sheet", type=str, default="SALES_KSP_CRM_1")
    parser.add_argument("--fact-file", type=Path, default=DEFAULT_FACT)
    parser.add_argument("--fact-sheet", type=str, default="Fact_Sales")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument("--dry-run", action="store_true", help="Read and merge only; do not write DB")
    parser.add_argument("--skip-metrics", action="store_true", help="Skip SKU metrics refresh after sync")
    args = parser.parse_args()

    if not args.crm_file.exists():
        raise SystemExit(f"CRM file not found: {args.crm_file}")
    if not args.fact_file.exists():
        raise SystemExit(f"Fact_Sales workbook not found: {args.fact_file}")

    crm_df, missing_net_rev = load_crm_sales(args.crm_file, args.crm_sheet)
    fact_df = load_fact_sales(args.fact_file, args.fact_sheet)

    if crm_df.empty or fact_df.empty:
        raise SystemExit("CRM or Fact_Sales data is empty; cannot sync.")

    combined, stats = merge_sales_sources(crm_df, fact_df)

    print("Merge summary:")
    print(f"- CRM rows: {stats.crm_rows}")
    print(f"- Fact rows: {stats.fact_rows}")
    print(f"- Fact rows after cutoff: {stats.fact_rows_after_cutoff}")
    print(f"- Fact rows dropped by date cutoff: {stats.fact_rows_dropped_by_date}")
    if stats.cutoff_date:
        print(f"- Cutoff date (CRM precedence): {stats.cutoff_date}")
    else:
        print("- Cutoff date (CRM precedence): none (overlap-only merge)")
    print(f"- Overlap rows: {stats.overlap_rows}")
    print(f"- CRM-only rows: {stats.crm_only_rows}")
    print(f"- Fact-only rows: {stats.fact_only_rows}")
    print(f"- Combined rows: {stats.combined_rows}")
    print(f"- CRM missing Total_net_rev: {missing_net_rev}")

    if args.dry_run:
        return

    conn = sqlite3.connect(str(args.db))
    try:
        required = ["order_id", "order_date", "sku_key", "sku_id", "my_size", "kaspi_offer_name"]
        before = len(combined)
        combined = combined.dropna(subset=required)
        dropped = before - len(combined)
        if dropped:
            print(f"- Dropped rows with missing required fields: {dropped}")
        combined["order_date"] = pd.to_datetime(combined["order_date"], errors="coerce").dt.date.astype(str)
        combined = combined[SALES_COLUMNS].copy()
        conn.execute("DELETE FROM sales_fact_v2")
        combined.to_sql("sales_fact_v2", conn, if_exists="append", index=False)
        conn.commit()
    finally:
        conn.close()

    print(f"✅ sales_fact_v2 updated: {stats.combined_rows} rows")

    if not args.skip_metrics:
        print("↻ Refreshing SKU metrics...")
        subprocess.run(
            [sys.executable, str(PROJECT_ROOT / "scripts" / "run_sku_metrics.py"), "--quiet"],
            check=True,
        )
        print("✅ SKU metrics refreshed")


if __name__ == "__main__":
    main()
