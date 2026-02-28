#!/usr/bin/env python3
"""Fail-closed parity validator: published sales truth vs Ocean Drop reference."""

from __future__ import annotations

import argparse
from datetime import date, datetime, timedelta
import json
import os
from pathlib import Path
import sqlite3
import sys
from typing import Any

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.sales import ensure_sales_truth_views
from core.sales.ocean_drop_anchor import (
    DEFAULT_REGISTRY as DEFAULT_ANCHOR_REGISTRY,
    OceanDropAnchorError,
    resolve_ocean_drop_path,
)
from scripts.build_ocean_drop_reference_snapshot import build_ocean_drop_snapshot_dataframe


DEFAULT_DB = PROJECT_ROOT / "db" / "app.db"
DEFAULT_OUTPUT_ROOT = PROJECT_ROOT / "exports" / "validation" / "sales_ocean_drop_parity"
DEFAULT_CRM_LOOKUP = None


def _safe_float(v: Any) -> float:
    try:
        return float(v or 0.0)
    except Exception:
        return 0.0


def _load_db_order_lines(db_path: Path, start_day: str, end_day: str) -> pd.DataFrame:
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    try:
        ensure_sales_truth_views(conn)
        rows = conn.execute(
            """
            SELECT
                date(sale_date) AS sale_date,
                UPPER(COALESCE(store_code, 'UNKNOWN')) AS store_code,
                CAST(order_id AS TEXT) AS order_id,
                SUM(COALESCE(units, 0)) AS units,
                SUM(COALESCE(net_rev_kzt, 0)) AS revenue_kzt
            FROM view_sales_line_truth
            WHERE date(sale_date) BETWEEN ? AND ?
            GROUP BY date(sale_date), UPPER(COALESCE(store_code, 'UNKNOWN')), CAST(order_id AS TEXT)
            """,
            (start_day, end_day),
        ).fetchall()
    finally:
        conn.close()
    if not rows:
        return pd.DataFrame(columns=["sale_date", "store_code", "order_id", "units", "revenue_kzt"])
    df = pd.DataFrame([dict(r) for r in rows])
    df["sale_date"] = df["sale_date"].astype(str).str[:10]
    df["store_code"] = df["store_code"].astype(str).str.upper()
    df["order_id"] = df["order_id"].astype(str).str.strip()
    df["units"] = df["units"].apply(_safe_float)
    df["revenue_kzt"] = df["revenue_kzt"].apply(_safe_float)
    return df


def _render_md(report: dict[str, Any]) -> str:
    lines = [
        "# Sales Ocean Drop Parity",
        "",
        f"- generated_at: `{report['generated_at']}`",
        f"- as_of: `{report['as_of']}`",
        f"- strict: `{str(report['strict']).lower()}`",
        f"- volatility_days: `{report['volatility_days']}`",
        f"- volatile_start_date: `{report['volatile_start_date']}`",
        f"- status: `{report['status']}`",
        f"- reference_rows_delivered: `{report['reference_rows_delivered']}`",
        f"- nonvolatile_mismatch_count: `{report['nonvolatile_mismatch_count']}`",
        f"- volatile_mismatch_count: `{report['volatile_mismatch_count']}`",
        "",
        "## Daily Aggregate Parity",
        "",
        "| sale_date | store_code | ref_units | db_units | ref_rev | db_rev | ref_orders | db_orders | volatile | match |",
        "|---|---|---:|---:|---:|---:|---:|---:|---|---|",
    ]
    for row in report["daily_rows"]:
        lines.append(
            f"| `{row['sale_date']}` | `{row['store_code']}` | {row['ref_units']:.2f} | {row['db_units']:.2f} | "
            f"{row['ref_rev_kzt']:.2f} | {row['db_rev_kzt']:.2f} | {row['ref_orders']} | {row['db_orders']} | "
            f"{str(row['is_volatile']).lower()} | {str(row['match']).lower()} |"
        )
    if report["nonvolatile_mismatch_count"] > 0:
        lines.extend(["", "## Non-Volatile Mismatches", ""])
        for item in report["nonvolatile_mismatches"][:200]:
            lines.append(f"- {item}")
    if report["volatile_mismatch_count"] > 0:
        lines.extend(["", "## Volatile Mismatches", ""])
        for item in report["volatile_mismatches"][:100]:
            lines.append(f"- {item}")
    return "\n".join(lines) + "\n"


def validate_sales_truth_ocean_drop_parity(
    *,
    db_path: Path,
    as_of: date,
    ocean_drop_path: Path,
    output_root: Path,
    volatility_days: int,
    strict: bool,
    crm_archive_lookup_path: Path | None,
    window_days: int | None = None,
) -> dict[str, Any]:
    if volatility_days < 0:
        raise RuntimeError("volatility_days must be >= 0")
    if window_days is not None and window_days <= 0:
        raise RuntimeError("window_days must be > 0 when provided")

    snapshot_df, snapshot_meta = build_ocean_drop_snapshot_dataframe(
        ocean_drop_path=ocean_drop_path.resolve(),
        as_of=as_of,
        crm_archive_lookup_path=crm_archive_lookup_path.resolve() if crm_archive_lookup_path else None,
        include_as_of_day=True,
        strict=True,
    )

    ref_df = snapshot_df[
        (snapshot_df["status_internal"] == "DELIVERED")
        & (snapshot_df["return_flag"] == 0)
    ].copy()
    if ref_df.empty:
        raise RuntimeError("ocean drop reference has no delivered rows")

    ref_df["sale_date"] = ref_df["sale_date"].astype(str).str[:10]
    ref_df["store_code"] = ref_df["store_code"].astype(str).str.upper()
    ref_df["order_id"] = ref_df["order_id"].astype(str).str.strip()
    ref_df["quantity"] = ref_df["quantity"].apply(_safe_float)
    ref_df["net_rev_kzt"] = ref_df["net_rev_kzt"].apply(_safe_float)

    ref_order = (
        ref_df.groupby(["sale_date", "store_code", "order_id"], dropna=False)
        .agg(units=("quantity", "sum"), revenue_kzt=("net_rev_kzt", "sum"))
        .reset_index()
    )

    if window_days is not None:
        start_window = as_of - timedelta(days=window_days - 1)
        ref_order = ref_order[ref_order["sale_date"] >= start_window.isoformat()].copy()
        if ref_order.empty:
            raise RuntimeError(f"no reference rows in requested window_days={window_days}")

    start_day = str(ref_order["sale_date"].min())
    end_day = str(min(ref_order["sale_date"].max(), as_of.isoformat()))
    db_order = _load_db_order_lines(db_path=db_path.resolve(), start_day=start_day, end_day=end_day)

    ref_daily = (
        ref_order.groupby(["sale_date", "store_code"], dropna=False)
        .agg(ref_units=("units", "sum"), ref_rev_kzt=("revenue_kzt", "sum"), ref_orders=("order_id", "nunique"))
        .reset_index()
    )
    db_daily = (
        db_order.groupby(["sale_date", "store_code"], dropna=False)
        .agg(db_units=("units", "sum"), db_rev_kzt=("revenue_kzt", "sum"), db_orders=("order_id", "nunique"))
        .reset_index()
    )

    merged_daily = ref_daily.merge(db_daily, on=["sale_date", "store_code"], how="outer").fillna(0)

    volatile_start = as_of - timedelta(days=max(0, volatility_days - 1)) if volatility_days else date.max

    ref_sets: dict[tuple[str, str], set[str]] = {}
    for _, r in ref_order.iterrows():
        key = (str(r["sale_date"]), str(r["store_code"]))
        ref_sets.setdefault(key, set()).add(str(r["order_id"]))

    db_sets: dict[tuple[str, str], set[str]] = {}
    for _, r in db_order.iterrows():
        key = (str(r["sale_date"]), str(r["store_code"]))
        db_sets.setdefault(key, set()).add(str(r["order_id"]))

    daily_rows: list[dict[str, Any]] = []
    nonvolatile_mismatches: list[str] = []
    volatile_mismatches: list[str] = []
    missing_rows: list[dict[str, Any]] = []
    extra_rows: list[dict[str, Any]] = []
    date_mismatch_rows: list[dict[str, Any]] = []

    for _, row in merged_daily.sort_values(["sale_date", "store_code"]).iterrows():
        sale_date = str(row["sale_date"])
        store = str(row["store_code"]).upper()
        if not sale_date or sale_date == "0":
            continue
        ref_units = _safe_float(row["ref_units"])
        db_units = _safe_float(row["db_units"])
        ref_rev = _safe_float(row["ref_rev_kzt"])
        db_rev = _safe_float(row["db_rev_kzt"])
        ref_orders = int(round(_safe_float(row["ref_orders"])))
        db_orders = int(round(_safe_float(row["db_orders"])))

        day = date.fromisoformat(sale_date)
        is_volatile = bool(day >= volatile_start)

        aggregate_match = (
            abs(ref_units - db_units) < 1e-9
            and abs(ref_rev - db_rev) <= 1.0
            and ref_orders == db_orders
        )

        ref_ids = ref_sets.get((sale_date, store), set())
        db_ids = db_sets.get((sale_date, store), set())
        missing_ids = sorted(ref_ids - db_ids)
        extra_ids = sorted(db_ids - ref_ids)
        id_match = (not missing_ids) and (not extra_ids)

        match = bool(aggregate_match and id_match)
        daily_rows.append(
            {
                "sale_date": sale_date,
                "store_code": store,
                "ref_units": ref_units,
                "db_units": db_units,
                "ref_rev_kzt": ref_rev,
                "db_rev_kzt": db_rev,
                "ref_orders": ref_orders,
                "db_orders": db_orders,
                "is_volatile": is_volatile,
                "match": match,
            }
        )

        if not match:
            msg = (
                f"{sale_date} {store}: ref_units={ref_units:.2f} db_units={db_units:.2f} "
                f"ref_rev={ref_rev:.2f} db_rev={db_rev:.2f} ref_orders={ref_orders} db_orders={db_orders} "
                f"missing_ids={len(missing_ids)} extra_ids={len(extra_ids)}"
            )
            if is_volatile:
                volatile_mismatches.append(msg)
            else:
                nonvolatile_mismatches.append(msg)

            date_mismatch_rows.append(
                {
                    "sale_date": sale_date,
                    "store_code": store,
                    "ref_units": ref_units,
                    "db_units": db_units,
                    "ref_rev_kzt": ref_rev,
                    "db_rev_kzt": db_rev,
                    "ref_orders": ref_orders,
                    "db_orders": db_orders,
                    "is_volatile": is_volatile,
                    "aggregate_match": aggregate_match,
                    "id_set_match": id_match,
                }
            )

            for oid in missing_ids:
                missing_rows.append(
                    {
                        "sale_date": sale_date,
                        "store_code": store,
                        "order_id": oid,
                        "is_volatile": is_volatile,
                    }
                )
            for oid in extra_ids:
                extra_rows.append(
                    {
                        "sale_date": sale_date,
                        "store_code": store,
                        "order_id": oid,
                        "is_volatile": is_volatile,
                    }
                )

    out_dir = output_root.resolve() / as_of.isoformat()
    out_dir.mkdir(parents=True, exist_ok=True)

    diff_missing_csv = out_dir / "diff_missing_order_ids.csv"
    diff_extra_csv = out_dir / "diff_extra_order_ids.csv"
    diff_mismatch_csv = out_dir / "diff_date_mismatches.csv"
    report_json = out_dir / "parity_report.json"
    report_md = out_dir / "parity_report.md"

    pd.DataFrame(missing_rows).to_csv(diff_missing_csv, index=False, encoding="utf-8")
    pd.DataFrame(extra_rows).to_csv(diff_extra_csv, index=False, encoding="utf-8")
    pd.DataFrame(date_mismatch_rows).to_csv(diff_mismatch_csv, index=False, encoding="utf-8")

    status = "PASS" if not nonvolatile_mismatches else "FAIL"
    report = {
        "generated_at": datetime.now().strftime("%Y-%m-%dT%H:%M:%S%z"),
        "as_of": as_of.isoformat(),
        "strict": bool(strict),
        "volatility_days": int(volatility_days),
        "volatile_start_date": volatile_start.isoformat() if volatility_days else None,
        "window_days": int(window_days) if window_days is not None else None,
        "status": status,
        "reference_rows_delivered": int(len(ref_df)),
        "reference_rows_total": int(len(snapshot_df)),
        "snapshot_errors_count": int(snapshot_meta.get("errors_count", 0)),
        "nonvolatile_mismatch_count": int(len(nonvolatile_mismatches)),
        "volatile_mismatch_count": int(len(volatile_mismatches)),
        "nonvolatile_mismatches": nonvolatile_mismatches,
        "volatile_mismatches": volatile_mismatches,
        "daily_rows": daily_rows,
        "diff_missing_order_ids_csv": str(diff_missing_csv),
        "diff_extra_order_ids_csv": str(diff_extra_csv),
        "diff_date_mismatches_csv": str(diff_mismatch_csv),
        "ocean_drop_path": str(ocean_drop_path.resolve()),
    }

    report_json.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    report_md.write_text(_render_md(report), encoding="utf-8")

    if strict and status != "PASS":
        raise RuntimeError("ocean drop parity failed for non-volatile days")
    return report


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Validate published sales truth vs ocean drop reference")
    p.add_argument("--db", type=Path, default=DEFAULT_DB)
    p.add_argument("--as-of", type=str, required=True)
    p.add_argument("--ocean-drop", type=Path, default=None)
    p.add_argument("--anchor-registry", type=Path, default=DEFAULT_ANCHOR_REGISTRY)
    p.add_argument("--crm-archive-lookup", type=Path, default=DEFAULT_CRM_LOOKUP)
    p.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    p.add_argument("--volatility-days", type=int, default=14)
    p.add_argument("--window-days", type=int, default=None)
    p.add_argument("--strict", action="store_true")
    p.add_argument("--strict-if-configured", action="store_true")
    return p


def main() -> int:
    args = _build_parser().parse_args()
    as_of = date.fromisoformat(str(args.as_of))
    env_ocean_drop = str(os.environ.get("AB_OCEAN_DROP_SALES_PATH") or "").strip()
    explicit_path = args.ocean_drop if args.ocean_drop else (Path(env_ocean_drop) if env_ocean_drop else None)
    try:
        ocean_drop_path = resolve_ocean_drop_path(
            explicit_path=explicit_path,
            registry_path=args.anchor_registry,
        )
    except OceanDropAnchorError as exc:
        if args.strict_if_configured:
            raise RuntimeError(str(exc)) from exc
        print(f"ocean_drop_parity_skip={exc}")
        return 0

    report = validate_sales_truth_ocean_drop_parity(
        db_path=args.db,
        as_of=as_of,
        ocean_drop_path=ocean_drop_path,
        output_root=args.output_root,
        volatility_days=int(args.volatility_days),
        strict=bool(args.strict),
        crm_archive_lookup_path=args.crm_archive_lookup,
        window_days=args.window_days,
    )
    out_dir = args.output_root.resolve() / as_of.isoformat()
    print(f"ocean_drop_parity_report_json={out_dir / 'parity_report.json'}")
    print(f"ocean_drop_parity_report_md={out_dir / 'parity_report.md'}")
    print(f"status={report['status']}")
    return 0 if (report["status"] == "PASS" or not args.strict) else 1


if __name__ == "__main__":
    raise SystemExit(main())
