#!/usr/bin/env python3
"""Fail-closed parity validator: published sales truth vs external Kaspi ETL reference."""

from __future__ import annotations

import argparse
from datetime import date, datetime, timezone
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
from core.sales.kaspi_etl_reference import (
    build_reference_from_archive_dir,
    load_reference_from_csv_dir,
)

DEFAULT_DB = PROJECT_ROOT / "db" / "app.db"
DEFAULT_OUTPUT_ROOT = PROJECT_ROOT / "exports" / "daily"


def _parse_as_of(value: str | None) -> date:
    return date.fromisoformat(value) if value else date.today()


def _safe_float(value: Any) -> float:
    try:
        return float(value or 0.0)
    except Exception:
        return 0.0


def _render_md(report: dict[str, Any]) -> str:
    lines = [
        "# Sales Truth External Reference Parity",
        "",
        f"- generated_at: `{report['generated_at']}`",
        f"- as_of: `{report['as_of']}`",
        f"- include_as_of_day: `{str(report['include_as_of_day']).lower()}`",
        f"- status: `{report['status']}`",
        f"- reference_source: `{report['reference_source']}`",
        f"- reference_status: `{report['reference_status']}`",
        f"- reference_rows: `{report.get('reference_rows', 0)}`",
        f"- mismatch_count: `{len(report['mismatches'])}`",
        "",
        "## Daily By Store",
        "",
        "| sale_date | store_code | ref_units | db_units | ref_rev | db_rev | ref_orders | db_orders | status |",
        "|---|---|---:|---:|---:|---:|---:|---:|---|",
    ]
    for row in report["daily_rows"]:
        status = "PASS" if row["ok"] else "FAIL"
        lines.append(
            f"| `{row['sale_date']}` | `{row['store_code']}` | "
            f"{row['ref_units']:.2f} | {row['db_units']:.2f} | "
            f"{row['ref_rev_kzt']:.2f} | {row['db_rev_kzt']:.2f} | "
            f"{row['ref_orders']} | {row['db_orders']} | {status} |"
        )
    if report["mismatches"]:
        lines.extend(["", "## Mismatches", ""])
        for mismatch in report["mismatches"][:50]:
            lines.append(f"- {mismatch}")
    if report["missing_in_db"]:
        lines.extend(["", "## Missing In DB (sample)", ""])
        for row in report["missing_in_db"][:50]:
            lines.append(f"- `{row}`")
    if report["extra_in_db"]:
        lines.extend(["", "## Extra In DB (sample)", ""])
        for row in report["extra_in_db"][:50]:
            lines.append(f"- `{row}`")
    return "\n".join(lines) + "\n"


def _load_reference(
    *,
    as_of: date,
    include_as_of_day: bool,
    archive_dir: Path | None,
    reference_dir: Path | None,
    db_path: Path,
) -> tuple[dict[str, Any], str]:
    if reference_dir:
        ref = load_reference_from_csv_dir(
            reference_dir=reference_dir.resolve(),
            as_of=as_of,
            include_as_of_day=include_as_of_day,
        )
        return ref, "csv_dir"
    if archive_dir:
        ref = build_reference_from_archive_dir(
            archive_dir=archive_dir.resolve(),
            as_of=as_of,
            include_as_of_day=include_as_of_day,
            db_path=db_path.resolve(),
        )
        return ref, "archive_dir"
    return {
        "status": "missing",
        "reason": "no_reference_source",
        "lines": pd.DataFrame(),
        "daily_by_store": pd.DataFrame(),
        "daily_total": pd.DataFrame(),
        "files": [],
        "unresolved_warehouses": [],
    }, "none"


def _load_db_daily_and_orders(*, db_path: Path, start_day: str, end_day: str) -> tuple[pd.DataFrame, dict[tuple[str, str], set[str]]]:
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
                SUM(COALESCE(net_rev_kzt, 0)) AS rev_kzt
            FROM view_sales_line_truth
            WHERE date(sale_date) BETWEEN ? AND ?
            GROUP BY date(sale_date), UPPER(COALESCE(store_code, 'UNKNOWN')), CAST(order_id AS TEXT)
            """,
            (start_day, end_day),
        ).fetchall()
    finally:
        conn.close()

    if not rows:
        return pd.DataFrame(columns=["sale_date", "store_code", "units", "rev_kzt", "orders"]), {}

    df = pd.DataFrame([dict(row) for row in rows])
    df["sale_date"] = df["sale_date"].astype(str).str[:10]
    df["store_code"] = df["store_code"].astype(str).str.upper()
    df["units"] = df["units"].apply(_safe_float)
    df["rev_kzt"] = df["rev_kzt"].apply(_safe_float)

    order_sets: dict[tuple[str, str], set[str]] = {}
    for _, row in df.iterrows():
        key = (str(row["sale_date"]), str(row["store_code"]))
        order_sets.setdefault(key, set()).add(str(row["order_id"]))

    daily = (
        df.groupby(["sale_date", "store_code"], dropna=False)
        .agg(units=("units", "sum"), rev_kzt=("rev_kzt", "sum"), orders=("order_id", "nunique"))
        .reset_index()
        .sort_values(["sale_date", "store_code"])
        .reset_index(drop=True)
    )
    return daily, order_sets


def validate_sales_truth_external_reference(
    *,
    project_root: Path,
    db_path: Path,
    as_of: str,
    output_root: Path,
    archive_dir: Path | None,
    reference_dir: Path | None,
    include_as_of_day: bool,
    strict: bool,
    strict_if_configured: bool,
) -> dict[str, Any]:
    as_of_day = _parse_as_of(as_of)
    root = project_root.resolve()

    env_archive = os.environ.get("AB_KASPI_ETL_ARCHIVE_DIR")
    env_ref = os.environ.get("AB_KASPI_ETL_REFERENCE_DIR")
    archive = archive_dir or (Path(env_archive) if env_archive else None)
    ref_dir = reference_dir or (Path(env_ref) if env_ref else None)
    configured = bool(archive or ref_dir)

    reference, ref_source = _load_reference(
        as_of=as_of_day,
        include_as_of_day=include_as_of_day,
        archive_dir=archive,
        reference_dir=ref_dir,
        db_path=db_path,
    )

    out_dir = output_root.resolve() / as_of_day.isoformat()
    out_dir.mkdir(parents=True, exist_ok=True)
    out_json = out_dir / "sales_truth_external_reference_parity.json"
    out_md = out_dir / "sales_truth_external_reference_parity.md"

    if reference.get("status") != "available":
        status = "SKIP"
        ok = not strict_if_configured or not configured
        if strict and configured:
            ok = False
            status = "FAIL"
        report = {
            "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
            "as_of": as_of_day.isoformat(),
            "include_as_of_day": bool(include_as_of_day),
            "status": status,
            "ok": bool(ok),
            "reference_source": ref_source,
            "reference_status": reference.get("status"),
            "reference_reason": reference.get("reason"),
            "reference_rows": 0,
            "daily_rows": [],
            "mismatches": [],
            "missing_in_db": [],
            "extra_in_db": [],
            "configured": configured,
            "files": reference.get("files") or [],
            "json_path": str(out_json),
            "md_path": str(out_md),
        }
        out_json.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        out_md.write_text(_render_md(report), encoding="utf-8")
        if strict and configured:
            raise RuntimeError("sales truth external reference parity failed: reference source missing")
        return report

    ref_lines = reference["lines"].copy()
    ref_daily = reference["daily_by_store"].copy()
    unresolved = list(reference.get("unresolved_warehouses") or [])
    if unresolved:
        raise RuntimeError(f"unresolved warehouse->store mapping: {', '.join(unresolved)}")

    if ref_daily.empty:
        raise RuntimeError("reference contains no delivered rows in selected window")

    ref_daily["sale_date"] = ref_daily["sale_date"].astype(str).str[:10]
    ref_daily["store_code"] = ref_daily["store_code"].astype(str).str.upper()
    ref_daily["units_delivered"] = ref_daily["units_delivered"].apply(_safe_float)
    ref_daily["gross_rev_kzt"] = ref_daily["gross_rev_kzt"].apply(_safe_float)
    ref_daily["orders_delivered"] = ref_daily["orders_delivered"].apply(lambda v: int(round(_safe_float(v))))

    start_day = str(ref_daily["sale_date"].min())
    end_day = str(ref_daily["sale_date"].max())
    db_daily, db_order_sets = _load_db_daily_and_orders(
        db_path=db_path.resolve(),
        start_day=start_day,
        end_day=end_day,
    )
    db_idx = {
        (str(r["sale_date"]), str(r["store_code"])): r
        for _, r in db_daily.iterrows()
    }

    ref_order_sets: dict[tuple[str, str], set[str]] = {}
    for _, row in ref_lines.iterrows():
        key = (str(row.get("sale_date", ""))[:10], str(row.get("store_code", "UNKNOWN")).upper())
        oid = str(row.get("order_id", "")).strip()
        if key[0] and oid:
            ref_order_sets.setdefault(key, set()).add(oid)

    daily_rows: list[dict[str, Any]] = []
    mismatches: list[str] = []
    missing_in_db: list[str] = []
    extra_in_db: list[str] = []

    seen_keys: set[tuple[str, str]] = set()
    for _, row in ref_daily.iterrows():
        key = (str(row["sale_date"]), str(row["store_code"]))
        seen_keys.add(key)
        db_row = db_idx.get(key)
        db_units = _safe_float(db_row["units"]) if db_row is not None else 0.0
        db_rev = _safe_float(db_row["rev_kzt"]) if db_row is not None else 0.0
        db_orders = int(round(_safe_float(db_row["orders"]))) if db_row is not None else 0
        ref_units = _safe_float(row["units_delivered"])
        ref_rev = _safe_float(row["gross_rev_kzt"])
        ref_orders = int(round(_safe_float(row["orders_delivered"])))
        ok_row = (
            abs(ref_units - db_units) < 1e-9
            and abs(ref_rev - db_rev) <= 1.0
            and ref_orders == db_orders
        )
        if not ok_row:
            mismatches.append(
                f"{key[0]} {key[1]} aggregate mismatch: "
                f"ref_units={ref_units:.2f} db_units={db_units:.2f} "
                f"ref_rev={ref_rev:.2f} db_rev={db_rev:.2f} "
                f"ref_orders={ref_orders} db_orders={db_orders}"
            )

        ref_ids = ref_order_sets.get(key, set())
        db_ids = db_order_sets.get(key, set())
        missing = sorted(ref_ids - db_ids)
        extra = sorted(db_ids - ref_ids)
        for oid in missing[:50]:
            missing_in_db.append(f"{key[0]}|{key[1]}|{oid}")
        for oid in extra[:50]:
            extra_in_db.append(f"{key[0]}|{key[1]}|{oid}")
        if missing:
            mismatches.append(
                f"{key[0]} {key[1]} missing_in_db={len(missing)} (sample: {', '.join(missing[:5])})"
            )
        if extra:
            mismatches.append(
                f"{key[0]} {key[1]} extra_in_db={len(extra)} (sample: {', '.join(extra[:5])})"
            )

        daily_rows.append(
            {
                "sale_date": key[0],
                "store_code": key[1],
                "ref_units": ref_units,
                "db_units": db_units,
                "ref_rev_kzt": ref_rev,
                "db_rev_kzt": db_rev,
                "ref_orders": ref_orders,
                "db_orders": db_orders,
                "ok": bool(ok_row and not missing and not extra),
            }
        )

    status = "PASS" if not mismatches else "FAIL"
    report = {
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "as_of": as_of_day.isoformat(),
        "include_as_of_day": bool(include_as_of_day),
        "status": status,
        "ok": status == "PASS",
        "reference_source": ref_source,
        "reference_status": reference.get("status"),
        "reference_reason": reference.get("reason"),
        "reference_rows": int(len(ref_lines)),
        "configured": configured,
        "files": reference.get("files") or [],
        "daily_rows": daily_rows,
        "mismatches": mismatches,
        "missing_in_db": missing_in_db,
        "extra_in_db": extra_in_db,
        "json_path": str(out_json),
        "md_path": str(out_md),
    }
    out_json.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    out_md.write_text(_render_md(report), encoding="utf-8")
    if strict and status != "PASS":
        raise RuntimeError("sales truth external reference parity failed")
    return report


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Validate published sales truth against external Kaspi ETL reference")
    parser.add_argument("--project-root", type=Path, default=PROJECT_ROOT)
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument("--as-of", type=str, required=True)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--archive-dir", type=Path, default=None)
    parser.add_argument("--reference-dir", type=Path, default=None)
    parser.add_argument("--include-as-of-day", action="store_true")
    parser.add_argument("--strict", action="store_true")
    parser.add_argument("--strict-if-configured", action="store_true")
    return parser


def main() -> int:
    args = _build_parser().parse_args()
    report = validate_sales_truth_external_reference(
        project_root=args.project_root,
        db_path=args.db,
        as_of=str(args.as_of),
        output_root=args.output_root,
        archive_dir=args.archive_dir,
        reference_dir=args.reference_dir,
        include_as_of_day=bool(args.include_as_of_day),
        strict=bool(args.strict),
        strict_if_configured=bool(args.strict_if_configured),
    )
    print(f"sales_truth_external_reference_parity_json={report['json_path']}")
    print(f"sales_truth_external_reference_parity_md={report['md_path']}")
    print(f"status={report['status']}")
    return 0 if report["ok"] or (not args.strict and not args.strict_if_configured) else 1


if __name__ == "__main__":
    raise SystemExit(main())

