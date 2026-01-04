#!/usr/bin/env python3
"""
Reconcile sales totals between CRM (SALES_KSP_CRM_1) and Inventory_Core Fact_Sales.

Outputs a CSV and Markdown report in reports/.
"""
from __future__ import annotations

import argparse
import sys
from datetime import date
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from core.analytics.reconciliation import compare_sales_frames
from core.ingest.sales_ingest import parse_sales_excel
from core.paths import data_path
DEFAULT_CRM = data_path("excel_ui", "SALES_KSP_CRM_V3.xlsx")
DEFAULT_FACT = data_path("excel", "Inventory_Core_V18.1_V2.xlsx")
DEFAULT_REPORTS = data_path("reports")


def load_crm(crm_path: Path, sheet: str) -> tuple[pd.DataFrame, int]:
    records = parse_sales_excel(str(crm_path), sheet_name=sheet)
    df = pd.DataFrame(records)
    if df.empty:
        return df, 0

    df["order_date"] = pd.to_datetime(df["order_date"], errors="coerce").dt.date
    df["units"] = pd.to_numeric(df.get("quantity"), errors="coerce").fillna(0)

    net_rev = pd.to_numeric(df.get("net_rev"), errors="coerce")
    missing_net_rev = int(net_rev.isna().sum())
    df["net_rev_line"] = net_rev.fillna(0)

    return df, missing_net_rev


def load_fact(fact_path: Path, sheet: str) -> pd.DataFrame:
    df = pd.read_excel(fact_path, sheet_name=sheet)
    if df.empty:
        return df

    if "Channel" in df.columns:
        df = df[df["Channel"] == "Kaspi"].copy()
    df["order_date"] = pd.to_datetime(df["Date"], errors="coerce").dt.date
    df["units"] = pd.to_numeric(df.get("Quantity"), errors="coerce").fillna(0)
    df["net_rev_line"] = pd.to_numeric(df.get("Line_NetRev"), errors="coerce").fillna(0)
    df = df.rename(columns={"OrderID": "order_id", "SKU_ID": "sku_id"})
    return df


def write_report(report_dir: Path, summary: dict, by_date: pd.DataFrame, missing_net_rev: int) -> tuple[Path, Path]:
    report_dir.mkdir(parents=True, exist_ok=True)
    csv_path = report_dir / "reconciliation_sales_sources.csv"
    md_path = report_dir / "reconciliation_sales_sources.md"

    by_date = by_date.copy()
    by_date["delta_units_pct"] = by_date.apply(
        lambda r: (r["delta_units"] / r["fact_units"]) if r["fact_units"] else None, axis=1
    )
    by_date["delta_net_rev_pct"] = by_date.apply(
        lambda r: (r["delta_net_rev"] / r["fact_net_rev"]) if r["fact_net_rev"] else None, axis=1
    )

    by_date.to_csv(csv_path, index=False)

    def fmt(value):
        if value is None:
            return "—"
        if isinstance(value, date):
            return value.isoformat()
        return f"{value:,.2f}" if isinstance(value, (float, int)) else str(value)

    lines = [
        "# Sales Source Reconciliation",
        "",
        "## Summary",
        f"- CRM rows: {summary['crm_rows']}",
        f"- Fact_Sales rows: {summary['fact_rows']}",
        f"- CRM units: {fmt(summary['crm_units'])}",
        f"- Fact units: {fmt(summary['fact_units'])}",
        f"- CRM net revenue: {fmt(summary['crm_net_rev'])}",
        f"- Fact net revenue: {fmt(summary['fact_net_rev'])}",
        f"- CRM date range: {fmt(summary['crm_min_date'])} → {fmt(summary['crm_max_date'])}",
        f"- Fact date range: {fmt(summary['fact_min_date'])} → {fmt(summary['fact_max_date'])}",
    ]

    if summary.get("missing_in_fact") is not None:
        lines.append(f"- Missing (CRM not in Fact): {summary['missing_in_fact']}")
        lines.append(f"- Missing (Fact not in CRM): {summary['missing_in_crm']}")

    lines.extend([
        "",
        "## Notes",
        f"- CRM rows missing Total_net_rev: {missing_net_rev}",
        f"- CSV breakdown written to: {csv_path}",
        "",
        "## Canonical Source Mapping",
        "- Units + Net Revenue: CRM → sales_fact_v2 (via scripts/sync_crm_to_db.py)",
        "- COGS/Profit: Derived from DB formulas (dim_sku + dim_fx_rates + dim_params) via v_sales_enriched",
        "- Fact_Sales: treated as a derived export (not authoritative for analytics)",
        "",
        "## Likely Drift Causes (validate with code paths)",
        "- Fact_Sales is loaded via scripts/sync_truth_workbook_to_db.py and filters Channel='Kaspi' (may lag or omit new CRM rows).",
        "- CRM includes operational rows that may be missing from Fact_Sales due to manual refresh timing.",
        "- SKU mapping or OrderID/sku_id normalization differences between CRM ingest and Fact_Sales export.",
    ])

    md_path.write_text("\n".join(lines))
    return csv_path, md_path


def main() -> None:
    parser = argparse.ArgumentParser(description="Reconcile CRM vs Fact_Sales")
    parser.add_argument("--crm-file", type=Path, default=DEFAULT_CRM)
    parser.add_argument("--crm-sheet", type=str, default="SALES_KSP_CRM_1")
    parser.add_argument("--fact-file", type=Path, default=DEFAULT_FACT)
    parser.add_argument("--fact-sheet", type=str, default="Fact_Sales")
    parser.add_argument("--reports-dir", type=Path, default=DEFAULT_REPORTS)
    args = parser.parse_args()

    if not args.crm_file.exists():
        raise SystemExit(f"CRM file not found: {args.crm_file}")
    if not args.fact_file.exists():
        raise SystemExit(f"Fact_Sales workbook not found: {args.fact_file}")

    crm_df, missing_net_rev = load_crm(args.crm_file, args.crm_sheet)
    fact_df = load_fact(args.fact_file, args.fact_sheet)

    if crm_df.empty or fact_df.empty:
        raise SystemExit("CRM or Fact_Sales data is empty; cannot reconcile.")

    result = compare_sales_frames(crm_df, fact_df)
    csv_path, md_path = write_report(args.reports_dir, result["summary"], result["by_date"], missing_net_rev)

    print("✅ Reconciliation complete")
    print(f"- CSV: {csv_path}")
    print(f"- MD: {md_path}")


if __name__ == "__main__":
    main()
