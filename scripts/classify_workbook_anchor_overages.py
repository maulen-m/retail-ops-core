#!/usr/bin/env python3
"""Classify workbook anchor overages by source lineage."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sqlite3
import sys
from typing import Any

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.sales import ensure_sales_truth_views
from scripts.validate_sales_against_workbook import (
    DEFAULT_DB,
    DEFAULT_SHEET,
    DEFAULT_WORKBOOK,
    _find_column,
    _to_date_iso,
    _to_float,
    validate_sales_against_workbook,
)

DEFAULT_OUTPUT_DIR = (
    PROJECT_ROOT / "exports" / "validation" / "workbook_anchor_recon" / "2026-03-07"
)

DATE_DRIFT_BUCKETS = {
    "OCEAN_DROP_ANCHOR": "OCEAN_DROP_ANCHOR_DATE_DRIFT",
    "KASPI_API_ENTRIES_REBUILD": "KASPI_REBUILD_DATE_DRIFT",
}
SAME_DAY_BUCKETS = {
    "OCEAN_DROP_ANCHOR": "OCEAN_DROP_ANCHOR_SAME_DAY_VALUE_OVERAGE",
    "KASPI_API_ENTRIES_REBUILD": "KASPI_REBUILD_SAME_DAY_VALUE_OVERAGE",
}
BUCKET_PRIORITY = {
    "ORDER_NOT_IN_WORKBOOK": 0,
    "OCEAN_DROP_ANCHOR_DATE_DRIFT": 1,
    "KASPI_REBUILD_DATE_DRIFT": 2,
    "INTERNAL_SOURCE_DATE_DRIFT": 3,
    "OCEAN_DROP_ANCHOR_SAME_DAY_VALUE_OVERAGE": 4,
    "KASPI_REBUILD_SAME_DAY_VALUE_OVERAGE": 5,
    "INTERNAL_SOURCE_SAME_DAY_VALUE_OVERAGE": 6,
}


def _load_workbook_order_rows(workbook_path: Path, *, sheet_name: str = DEFAULT_SHEET) -> pd.DataFrame:
    df = pd.read_excel(workbook_path, sheet_name=sheet_name, dtype=object)
    if df.empty:
        return pd.DataFrame(
            columns=[
                "order_id",
                "workbook_date",
                "workbook_units",
                "workbook_net_rev_kzt",
                "workbook_total_price_kzt",
                "workbook_store_code",
            ]
        )

    order_col = _find_column(df.columns.tolist(), ["OrderID", "№ заказа"])
    date_col = _find_column(df.columns.tolist(), ["Date", "order_date", "Дата поступления заказа"])
    qty_col = _find_column(df.columns.tolist(), ["Quantity", "qty", "Количество"])
    total_price_col = _find_column(df.columns.tolist(), ["Total_price", "totalprice", "Сумма"])
    net_rev_col = _find_column(df.columns.tolist(), ["Total_net_rev", "net_rev", "Line_NetRev"])
    store_col = _find_column(df.columns.tolist(), ["STORE_NAME", "store_name", "Store"])

    if order_col is None or date_col is None or qty_col is None:
        raise RuntimeError("workbook missing order/date/quantity columns required for lineage classification")

    rows: list[dict[str, Any]] = []
    for _, row in df.iterrows():
        order_id = str(row.get(order_col) or "").strip()
        workbook_date = _to_date_iso(row.get(date_col))
        workbook_units = _to_float(row.get(qty_col))
        if not order_id or workbook_date is None or workbook_units is None:
            continue
        total_price = _to_float(row.get(total_price_col)) if total_price_col else None
        net_rev = _to_float(row.get(net_rev_col)) if net_rev_col else None
        rows.append(
            {
                "order_id": order_id,
                "workbook_date": workbook_date,
                "workbook_units": round(float(workbook_units or 0.0), 2),
                "workbook_net_rev_kzt": round(float(net_rev or 0.0), 2),
                "workbook_total_price_kzt": round(float(total_price or 0.0), 2),
                "workbook_store_code": str(row.get(store_col) or "").strip().upper() if store_col else "",
            }
        )
    return pd.DataFrame(rows)


def _load_sales_fact_lineage(conn: sqlite3.Connection, *, start: str, end: str) -> pd.DataFrame:
    if conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='sales_fact_v2'"
    ).fetchone() is None:
        return pd.DataFrame(
            columns=["date", "order_id", "store_code", "source_file", "published_units", "published_net_rev_kzt"]
        )
    query = """
        SELECT
            date(order_date) AS date,
            CAST(order_id AS TEXT) AS order_id,
            UPPER(COALESCE(store_code, '')) AS store_code,
            UPPER(COALESCE(source_file, '')) AS source_file,
            ROUND(SUM(COALESCE(quantity, 0)), 2) AS published_units,
            ROUND(SUM(COALESCE(net_rev, 0)), 2) AS published_net_rev_kzt
        FROM sales_fact_v2
        WHERE date(order_date) BETWEEN ? AND ?
          AND UPPER(COALESCE(status, 'DELIVERED')) = 'DELIVERED'
          AND COALESCE(return_flag, 0) = 0
        GROUP BY 1, 2, 3, 4
        ORDER BY 1, 2, 3, 4
    """
    return pd.read_sql_query(query, conn, params=[start, end])


def _load_published_daily(conn: sqlite3.Connection, *, start: str, end: str) -> pd.DataFrame:
    ensure_sales_truth_views(conn)
    query = """
        SELECT
            sale_date AS date,
            ROUND(SUM(COALESCE(units, 0)), 2) AS published_units,
            ROUND(SUM(COALESCE(revenue_kzt, 0)), 2) AS published_net_rev_kzt
        FROM view_sales_daily_truth
        WHERE sale_date BETWEEN ? AND ?
        GROUP BY sale_date
        ORDER BY sale_date
    """
    return pd.read_sql_query(query, conn, params=[start, end])


def _bucket_for_row(pair_status: str, source_file: str) -> str:
    source_norm = str(source_file or "").strip().upper()
    if pair_status == "ORDER_NOT_IN_WORKBOOK":
        return "ORDER_NOT_IN_WORKBOOK"
    if pair_status == "MATCH_SAME_DAY":
        return SAME_DAY_BUCKETS.get(source_norm, "INTERNAL_SOURCE_SAME_DAY_VALUE_OVERAGE")
    return DATE_DRIFT_BUCKETS.get(source_norm, "INTERNAL_SOURCE_DATE_DRIFT")


def _build_lineage_frame(
    lineage: pd.DataFrame,
    workbook_rows: pd.DataFrame,
    fail_dates: set[str],
) -> pd.DataFrame:
    if lineage.empty:
        lineage = pd.DataFrame(
            columns=["date", "order_id", "store_code", "source_file", "published_units", "published_net_rev_kzt"]
        )
    fail_lineage = lineage[lineage["date"].isin(fail_dates)].copy()

    workbook_by_order = (
        workbook_rows.groupby("order_id", dropna=False)
        .agg(
            workbook_dates=("workbook_date", lambda s: "|".join(sorted(set(str(v) for v in s if str(v))))),
            workbook_date_count=("workbook_date", lambda s: int(pd.Series(s).nunique())),
            workbook_units_total=("workbook_units", "sum"),
            workbook_net_rev_total=("workbook_net_rev_kzt", "sum"),
        )
        .reset_index()
    )
    fail_lineage = fail_lineage.merge(workbook_by_order, on="order_id", how="left")
    if fail_lineage.empty:
        fail_lineage["pair_status"] = pd.Series(dtype=str)
        fail_lineage["bucket"] = pd.Series(dtype=str)
        return fail_lineage
    fail_lineage["workbook_date_count"] = pd.to_numeric(
        fail_lineage["workbook_date_count"], errors="coerce"
    ).fillna(0).astype(int)
    fail_lineage["workbook_dates"] = fail_lineage["workbook_dates"].fillna("")
    fail_lineage["workbook_units_total"] = pd.to_numeric(
        fail_lineage["workbook_units_total"], errors="coerce"
    ).fillna(0.0)
    fail_lineage["workbook_net_rev_total"] = pd.to_numeric(
        fail_lineage["workbook_net_rev_total"], errors="coerce"
    ).fillna(0.0)

    def _pair_status(row: pd.Series) -> str:
        if int(row["workbook_date_count"]) == 0:
            return "ORDER_NOT_IN_WORKBOOK"
        workbook_dates = {part for part in str(row["workbook_dates"]).split("|") if part}
        return "MATCH_SAME_DAY" if str(row["date"]) in workbook_dates else "ORDER_IN_WB_OTHER_DAY"

    fail_lineage["pair_status"] = fail_lineage.apply(_pair_status, axis=1)
    fail_lineage["bucket"] = fail_lineage.apply(
        lambda row: _bucket_for_row(str(row["pair_status"]), str(row["source_file"])),
        axis=1,
    )
    return fail_lineage


def _allocate_day_overage(day_rows: pd.DataFrame, *, units_overage: float, net_overage: float) -> pd.DataFrame:
    if day_rows.empty:
        return pd.DataFrame(
            columns=[
                "date",
                "bucket",
                "source_file",
                "pair_status",
                "line_count",
                "bucket_published_units",
                "bucket_published_net_rev_kzt",
                "attributed_units_overage",
                "attributed_net_overage_kzt",
            ]
        )

    grouped = (
        day_rows.groupby(["date", "bucket", "source_file", "pair_status"], dropna=False)
        .agg(
            line_count=("order_id", "count"),
            bucket_published_units=("published_units", "sum"),
            bucket_published_net_rev_kzt=("published_net_rev_kzt", "sum"),
        )
        .reset_index()
    )
    grouped["bucket_priority"] = grouped["bucket"].map(BUCKET_PRIORITY).fillna(999).astype(int)
    grouped = grouped.sort_values(["bucket_priority", "source_file", "pair_status"]).reset_index(drop=True)

    remaining_units = round(float(units_overage or 0.0), 2)
    remaining_net = round(float(net_overage or 0.0), 2)
    attributed_units: list[float] = []
    attributed_net: list[float] = []
    for _, row in grouped.iterrows():
        units_take = min(remaining_units, round(float(row["bucket_published_units"] or 0.0), 2))
        net_take = min(remaining_net, round(float(row["bucket_published_net_rev_kzt"] or 0.0), 2))
        attributed_units.append(round(units_take, 2))
        attributed_net.append(round(net_take, 2))
        remaining_units = round(remaining_units - units_take, 2)
        remaining_net = round(remaining_net - net_take, 2)
    grouped["attributed_units_overage"] = attributed_units
    grouped["attributed_net_overage_kzt"] = attributed_net
    grouped["remaining_units_after_allocation"] = remaining_units
    grouped["remaining_net_after_allocation_kzt"] = remaining_net
    return grouped


def _fail_daily_from_report(report: dict[str, Any]) -> pd.DataFrame:
    daily = pd.DataFrame(report.get("daily") or [])
    if daily.empty:
        return pd.DataFrame(
            columns=[
                "date",
                "workbook_units",
                "published_units",
                "workbook_net_rev_kzt",
                "published_net_rev_kzt",
            ]
        )
    daily = daily.rename(columns={"published_net_rev_kzt": "published_net_rev_kzt"})
    fail_mask = (
        (daily["published_units"] > daily["workbook_units"] * 1.05)
        | (daily["published_net_rev_kzt"] > daily["workbook_net_rev_kzt"] * 1.05)
    )
    fail_daily = daily.loc[fail_mask].copy()
    fail_daily["units_overage"] = (
        fail_daily["published_units"] - fail_daily["workbook_units"]
    ).clip(lower=0).round(2)
    fail_daily["net_overage_kzt"] = (
        fail_daily["published_net_rev_kzt"] - fail_daily["workbook_net_rev_kzt"]
    ).clip(lower=0).round(2)
    fail_daily["units_error"] = fail_daily["published_units"] > fail_daily["workbook_units"] * 1.05
    fail_daily["net_error"] = (
        fail_daily["published_net_rev_kzt"] > fail_daily["workbook_net_rev_kzt"] * 1.05
    )
    fail_daily["error_reference_count"] = (
        fail_daily["units_error"].astype(int) + fail_daily["net_error"].astype(int)
    )
    return fail_daily


def _write_root_causes_md(
    *,
    path: Path,
    report: dict[str, Any],
    fail_daily: pd.DataFrame,
    source_mix: pd.DataFrame,
) -> None:
    lines = [
        "# Workbook Overage Root Causes",
        "",
        f"- status: `{report['status']}`",
        f"- period: `{report['start']}`..`{report['end']}`",
        f"- error_references_total: `{report['error_references_total']}`",
        f"- error_references_classified: `{report['error_references_classified']}`",
        f"- unique_failing_dates: `{report['unique_failing_dates']}`",
        f"- unresolved_error_references: `{report['unresolved_error_references']}`",
        f"- unresolved_ratio: `{report['unresolved_ratio']:.4f}`",
        "",
        "## Summary",
        "",
    ]

    bucket_summary = (
        source_mix.groupby("bucket", dropna=False)[
            ["attributed_units_overage", "attributed_net_overage_kzt"]
        ]
        .sum()
        .sort_values(["attributed_net_overage_kzt", "attributed_units_overage"], ascending=False)
        .reset_index()
    )
    if bucket_summary.empty:
        lines.append("- No workbook overages detected.")
    else:
        for _, row in bucket_summary.iterrows():
            lines.append(
                "- "
                + f"{row['bucket']}: "
                + f"units_overage={round(float(row['attributed_units_overage'] or 0.0), 2)}, "
                + f"net_overage_kzt={round(float(row['attributed_net_overage_kzt'] or 0.0), 2)}"
            )

    lines.extend(
        [
            "",
            "## Fail-Day Totals",
            "",
            f"- summed_units_overage: `{round(float(fail_daily['units_overage'].sum() if not fail_daily.empty else 0.0), 2)}`",
            f"- summed_net_overage_kzt: `{round(float(fail_daily['net_overage_kzt'].sum() if not fail_daily.empty else 0.0), 2)}`",
        ]
    )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def classify_workbook_anchor_overages(
    *,
    db_path: Path,
    workbook_path: Path,
    start: str,
    end: str,
    output_dir: Path,
    sheet_name: str = DEFAULT_SHEET,
    strict: bool = False,
) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)

    workbook_rows = _load_workbook_order_rows(workbook_path, sheet_name=sheet_name)
    workbook_report = validate_sales_against_workbook(
        db_path=db_path,
        workbook_path=workbook_path,
        sheet_name=sheet_name,
        start=start,
        end=end,
        min_overlap_days=1,
        max_lag_days=366,
        output_dir=None,
    )
    fail_daily = _fail_daily_from_report(workbook_report)
    fail_dates = set(str(value) for value in fail_daily["date"].tolist())

    conn = sqlite3.connect(str(db_path))
    try:
        lineage = _load_sales_fact_lineage(conn, start=start, end=end)
        published_daily = _load_published_daily(conn, start=start, end=end)
    finally:
        conn.close()

    lineage_rows = _build_lineage_frame(lineage, workbook_rows, fail_dates)
    if not published_daily.empty:
        published_fail = published_daily[published_daily["date"].isin(fail_dates)].copy()
    else:
        published_fail = pd.DataFrame(columns=["date", "published_units", "published_net_rev_kzt"])

    days_records: list[dict[str, Any]] = []
    source_mix_frames: list[pd.DataFrame] = []
    unresolved_rows: list[dict[str, Any]] = []

    for _, day_row in fail_daily.sort_values("date").iterrows():
        day = str(day_row["date"])
        day_lineage = lineage_rows[lineage_rows["date"] == day].copy()
        day_public = published_fail[published_fail["date"] == day]
        source_units = round(float(day_lineage["published_units"].sum() if not day_lineage.empty else 0.0), 2)
        source_net = round(
            float(day_lineage["published_net_rev_kzt"].sum() if not day_lineage.empty else 0.0), 2
        )
        published_units = round(float(day_public["published_units"].sum() if not day_public.empty else 0.0), 2)
        published_net = round(
            float(day_public["published_net_rev_kzt"].sum() if not day_public.empty else 0.0), 2
        )

        mix = _allocate_day_overage(
            day_lineage,
            units_overage=float(day_row["units_overage"] or 0.0),
            net_overage=float(day_row["net_overage_kzt"] or 0.0),
        )
        if not mix.empty:
            source_mix_frames.append(mix)
            remaining_units = round(float(mix["remaining_units_after_allocation"].iloc[-1] or 0.0), 2)
            remaining_net = round(float(mix["remaining_net_after_allocation_kzt"].iloc[-1] or 0.0), 2)
        else:
            remaining_units = round(float(day_row["units_overage"] or 0.0), 2)
            remaining_net = round(float(day_row["net_overage_kzt"] or 0.0), 2)

        if remaining_units > 0:
            unresolved_rows.append({"date": day, "metric": "units", "unresolved_amount": remaining_units})
        if remaining_net > 0:
            unresolved_rows.append({"date": day, "metric": "net_rev_kzt", "unresolved_amount": remaining_net})

        day_buckets = (
            "|".join(sorted(day_lineage["bucket"].dropna().astype(str).unique().tolist()))
            if not day_lineage.empty
            else ""
        )
        days_records.append(
            {
                "date": day,
                "workbook_units": round(float(day_row["workbook_units"] or 0.0), 2),
                "published_units": round(float(day_row["published_units"] or 0.0), 2),
                "units_overage": round(float(day_row["units_overage"] or 0.0), 2),
                "units_error": bool(day_row["units_error"]),
                "workbook_net_rev_kzt": round(float(day_row["workbook_net_rev_kzt"] or 0.0), 2),
                "published_net_rev_kzt": round(float(day_row["published_net_rev_kzt"] or 0.0), 2),
                "net_overage_kzt": round(float(day_row["net_overage_kzt"] or 0.0), 2),
                "net_error": bool(day_row["net_error"]),
                "error_reference_count": int(day_row["error_reference_count"] or 0),
                "source_lineage_units": source_units,
                "source_lineage_net_rev_kzt": source_net,
                "published_truth_units": published_units,
                "published_truth_net_rev_kzt": published_net,
                "unresolved_units_overage": remaining_units,
                "unresolved_net_overage_kzt": remaining_net,
                "buckets_present": day_buckets,
            }
        )

    days_df = pd.DataFrame(days_records)
    source_mix_df = (
        pd.concat(source_mix_frames, ignore_index=True)
        if source_mix_frames
        else pd.DataFrame(
            columns=[
                "date",
                "bucket",
                "source_file",
                "pair_status",
                "line_count",
                "bucket_published_units",
                "bucket_published_net_rev_kzt",
                "attributed_units_overage",
                "attributed_net_overage_kzt",
                "remaining_units_after_allocation",
                "remaining_net_after_allocation_kzt",
            ]
        )
    )
    unresolved_df = pd.DataFrame(unresolved_rows, columns=["date", "metric", "unresolved_amount"])

    error_references_total = int(len(workbook_report.get("errors") or []))
    error_references_classified = int(
        days_df["units_error"].astype(int).sum() + days_df["net_error"].astype(int).sum()
        if not days_df.empty
        else 0
    )
    unresolved_error_references = int(len(unresolved_df))
    unresolved_ratio = (
        float(unresolved_error_references) / float(error_references_total)
        if error_references_total > 0
        else 0.0
    )

    days_csv = output_dir / "workbook_overage_days.csv"
    source_mix_csv = output_dir / "workbook_overage_source_mix.csv"
    lineage_csv = output_dir / "workbook_overage_order_lineage.csv"
    unresolved_csv = output_dir / "workbook_overage_unresolved.csv"
    root_causes_md = output_dir / "workbook_overage_root_causes.md"

    days_df.to_csv(days_csv, index=False)
    source_mix_df.to_csv(source_mix_csv, index=False)
    lineage_rows.sort_values(["date", "source_file", "order_id"]).to_csv(lineage_csv, index=False)
    unresolved_df.to_csv(unresolved_csv, index=False)

    status = "PASS"
    errors: list[str] = []
    if error_references_classified != error_references_total:
        status = "FAIL"
        errors.append(
            f"classified error references mismatch: {error_references_classified} != {error_references_total}"
        )
    if unresolved_ratio > 0.05:
        status = "FAIL"
        errors.append(f"unresolved ratio above threshold: {unresolved_ratio:.4f}")
    if not days_df.empty:
        summed_units = round(float(days_df["units_overage"].sum()), 2)
        attributed_units = round(float(source_mix_df["attributed_units_overage"].sum() if not source_mix_df.empty else 0.0), 2)
        summed_net = round(float(days_df["net_overage_kzt"].sum()), 2)
        attributed_net = round(
            float(source_mix_df["attributed_net_overage_kzt"].sum() if not source_mix_df.empty else 0.0), 2
        )
        if abs(summed_units - attributed_units - round(float(unresolved_df.loc[unresolved_df["metric"] == "units", "unresolved_amount"].sum() if not unresolved_df.empty else 0.0), 2)) > 1e-6:
            status = "FAIL"
            errors.append("units overage attribution does not reconcile to day totals")
        if abs(summed_net - attributed_net - round(float(unresolved_df.loc[unresolved_df["metric"] == "net_rev_kzt", "unresolved_amount"].sum() if not unresolved_df.empty else 0.0), 2)) > 1e-6:
            status = "FAIL"
            errors.append("net_rev overage attribution does not reconcile to day totals")

    report = {
        "status": status,
        "ok": status == "PASS",
        "start": start,
        "end": end,
        "error_references_total": error_references_total,
        "error_references_classified": error_references_classified,
        "unique_failing_dates": int(len(days_df)),
        "unresolved_error_references": unresolved_error_references,
        "unresolved_ratio": round(unresolved_ratio, 6),
        "errors": errors,
        "outputs": {
            "workbook_overage_days_csv": str(days_csv),
            "workbook_overage_source_mix_csv": str(source_mix_csv),
            "workbook_overage_order_lineage_csv": str(lineage_csv),
            "workbook_overage_unresolved_csv": str(unresolved_csv),
            "workbook_overage_root_causes_md": str(root_causes_md),
        },
    }
    _write_root_causes_md(path=root_causes_md, report=report, fail_daily=days_df, source_mix=source_mix_df)

    if strict and status != "PASS":
        raise RuntimeError("; ".join(errors) if errors else "unresolved workbook overage classification")
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description="Classify workbook anchor overages by source lineage")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument("--workbook", type=Path, default=DEFAULT_WORKBOOK)
    parser.add_argument("--sheet-name", default=DEFAULT_SHEET)
    parser.add_argument("--start", required=True)
    parser.add_argument("--end", required=True)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args()

    report = classify_workbook_anchor_overages(
        db_path=args.db,
        workbook_path=args.workbook,
        start=args.start,
        end=args.end,
        output_dir=args.output_dir,
        sheet_name=args.sheet_name,
        strict=args.strict,
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
