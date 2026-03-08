#!/usr/bin/env python3
"""Validate that returned orders do not leak into delivered economics beyond volatility window."""

from __future__ import annotations

import argparse
from datetime import date, datetime, timedelta, timezone
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

DEFAULT_DB = PROJECT_ROOT / "db" / "app.db"
DEFAULT_OUTPUT_ROOT = PROJECT_ROOT / "exports" / "validation" / "returns_economics"


class ReturnsEconomicsError(RuntimeError):
    """Raised when strict returns economics validation fails."""


def _render_md(report: dict[str, Any]) -> str:
    lines = [
        "# Returns Economics Audit",
        "",
        f"- generated_at: `{report['generated_at']}`",
        f"- as_of: `{report['as_of']}`",
        f"- since: `{report['since']}`",
        f"- status: `{report['status']}`",
        f"- error_code: `{report.get('error_code') or 'none'}`",
        f"- volatility_days: `{report['volatility_days']}`",
        "",
        "| check | status | details |",
        "|---|---:|---|",
    ]
    for check in report["checks"]:
        lines.append(
            f"| `{check['check']}` | {'PASS' if check['ok'] else 'FAIL'} | {check['details']} |"
        )

    if report["errors"]:
        lines.extend(["", "## Errors", ""])
        for err in report["errors"]:
            lines.append(f"- {err}")

    if report.get("stale_leak_orders_csv"):
        lines.extend([
            "",
            "## Artifacts",
            "",
            f"- stale_leak_orders_csv: `{report['stale_leak_orders_csv']}`",
            f"- monthly_returns_csv: `{report['monthly_returns_csv']}`",
        ])
    return "\n".join(lines) + "\n"


def validate_returns_economics_audit(
    *,
    db_path: Path,
    as_of: date,
    since: date,
    output_root: Path,
    volatility_days: int,
    strict: bool,
) -> dict[str, Any]:
    if since > as_of:
        raise ReturnsEconomicsError("since must be <= as_of")
    if volatility_days < 0:
        raise ReturnsEconomicsError("volatility_days must be >= 0")
    if not db_path.exists():
        raise ReturnsEconomicsError(f"db not found: {db_path}")

    conn = sqlite3.connect(str(db_path))
    try:
        ensure_sales_truth_views(conn)
        returned = pd.read_sql_query(
            """
            SELECT
                CAST(order_id AS TEXT) AS order_id,
                UPPER(COALESCE(store_code, 'UNKNOWN')) AS store_code,
                date(COALESCE(status_updated_at, updated_at, created_at)) AS return_date,
                UPPER(COALESCE(internal_status, '')) AS internal_status
            FROM fact_orders_kaspi
            WHERE date(COALESCE(status_updated_at, updated_at, created_at)) BETWEEN ? AND ?
              AND UPPER(COALESCE(internal_status, '')) = 'RETURNED'
            """,
            conn,
            params=(since.isoformat(), as_of.isoformat()),
        )

        leaked = pd.read_sql_query(
            """
            SELECT
                CAST(v.order_id AS TEXT) AS order_id,
                UPPER(COALESCE(v.store_code, 'UNKNOWN')) AS store_code,
                date(v.sale_date) AS sale_date,
                r.return_date
            FROM view_sales_line_truth v
            INNER JOIN (
                SELECT CAST(order_id AS TEXT) AS order_id,
                       date(COALESCE(status_updated_at, updated_at, created_at)) AS return_date
                FROM fact_orders_kaspi
                WHERE UPPER(COALESCE(internal_status, '')) = 'RETURNED'
            ) r
              ON r.order_id = CAST(v.order_id AS TEXT)
            WHERE date(v.sale_date) <= ?
            """,
            conn,
            params=(as_of.isoformat(),),
        )

        refunds = pd.read_sql_query(
            """
            SELECT
                substr(date(event_date), 1, 7) AS sale_month,
                COUNT(*) AS refund_events,
                ROUND(SUM(COALESCE(amount_kzt, 0)), 2) AS refund_amount_kzt
            FROM fact_cashflow_events
            WHERE event_type = 'REFUND'
              AND date(event_date) BETWEEN ? AND ?
            GROUP BY substr(date(event_date), 1, 7)
            ORDER BY sale_month
            """,
            conn,
            params=(since.isoformat(), as_of.isoformat()),
        )
    finally:
        conn.close()

    now_cutoff = as_of - timedelta(days=int(volatility_days))

    if leaked.empty:
        leaked = pd.DataFrame(columns=["order_id", "store_code", "sale_date", "return_date"])
    leaked["return_date"] = pd.to_datetime(leaked["return_date"], errors="coerce").dt.date
    leaked["sale_date"] = pd.to_datetime(leaked["sale_date"], errors="coerce").dt.date
    stale_leaks = leaked[leaked["return_date"].notna() & (leaked["return_date"] <= now_cutoff)].copy()

    returned_monthly = pd.DataFrame()
    if not returned.empty:
        returned["return_date"] = pd.to_datetime(returned["return_date"], errors="coerce").dt.date
        returned = returned[returned["return_date"].notna()].copy()
        returned["sale_month"] = pd.to_datetime(returned["return_date"]).dt.to_period("M").astype(str)
        returned_monthly = (
            returned.groupby("sale_month", dropna=False)
            .agg(returned_orders=("order_id", "nunique"))
            .reset_index()
            .sort_values("sale_month")
        )
    else:
        returned_monthly = pd.DataFrame(columns=["sale_month", "returned_orders"])

    monthly = returned_monthly.merge(refunds, on="sale_month", how="left").fillna(0)
    if "refund_events" not in monthly.columns:
        monthly["refund_events"] = 0
    if "refund_amount_kzt" not in monthly.columns:
        monthly["refund_amount_kzt"] = 0.0

    months_missing_refunds: list[str] = []
    for _, row in monthly.iterrows():
        month = str(row.get("sale_month") or "")
        if not month:
            continue
        year, mon = month.split("-")
        month_end = date(int(year), int(mon), 1)
        if mon == "12":
            month_end = date(int(year) + 1, 1, 1) - timedelta(days=1)
        else:
            month_end = date(int(year), int(mon) + 1, 1) - timedelta(days=1)
        if month_end > now_cutoff:
            continue
        if int(row.get("returned_orders") or 0) > 0 and int(row.get("refund_events") or 0) == 0:
            months_missing_refunds.append(month)

    checks: list[dict[str, Any]] = []
    errors: list[str] = []
    error_codes: list[str] = []

    checks.append(
        {
            "check": "returned_orders_present",
            "ok": True,
            "details": f"returned_orders={int(returned['order_id'].nunique()) if not returned.empty else 0}",
        }
    )

    stale_leak_count = int(stale_leaks["order_id"].nunique()) if not stale_leaks.empty else 0
    stale_ok = stale_leak_count == 0
    checks.append(
        {
            "check": "stale_return_leak",
            "ok": stale_ok,
            "details": f"stale_leaked_orders={stale_leak_count} cutoff={now_cutoff.isoformat()}",
        }
    )
    if not stale_ok:
        error_codes.append("RETURNS_LEAK_STALE")
        errors.append(
            f"{stale_leak_count} returned order(s) still present in delivered sales beyond {volatility_days}d window"
        )

    refunds_ok = len(months_missing_refunds) == 0
    checks.append(
        {
            "check": "monthly_refund_presence",
            "ok": refunds_ok,
            "details": (
                "all covered months include refund events"
                if refunds_ok
                else f"missing_refund_months={','.join(months_missing_refunds)}"
            ),
        }
    )
    if not refunds_ok:
        error_codes.append("RETURNS_REFUND_GAP")
        errors.append(
            "no REFUND cashflow events for closed month(s): " + ", ".join(months_missing_refunds)
        )

    out_dir = output_root.resolve() / as_of.isoformat()
    out_dir.mkdir(parents=True, exist_ok=True)
    stale_leaks_csv = out_dir / "stale_leak_orders.csv"
    monthly_csv = out_dir / "monthly_returns.csv"
    stale_leaks.to_csv(stale_leaks_csv, index=False, encoding="utf-8")
    monthly.to_csv(monthly_csv, index=False, encoding="utf-8")

    report = {
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "as_of": as_of.isoformat(),
        "since": since.isoformat(),
        "status": "PASS" if not errors else "FAIL",
        "ok": len(errors) == 0,
        "error_code": error_codes[0] if error_codes else None,
        "error_codes": error_codes,
        "errors": errors,
        "checks": checks,
        "volatility_days": int(volatility_days),
        "db_path": str(db_path.resolve()),
        "returned_orders": int(returned["order_id"].nunique()) if not returned.empty else 0,
        "stale_leaked_orders": stale_leak_count,
        "months_missing_refunds": months_missing_refunds,
        "stale_leak_orders_csv": str(stale_leaks_csv),
        "monthly_returns_csv": str(monthly_csv),
    }

    json_path = out_dir / "returns_economics_report.json"
    md_path = out_dir / "returns_economics_report.md"
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    md_path.write_text(_render_md(report), encoding="utf-8")
    report["json_path"] = str(json_path)
    report["md_path"] = str(md_path)

    if strict and errors:
        raise ReturnsEconomicsError("returns economics audit failed")
    return report


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Validate returned-order economics drift")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument("--as-of", required=True)
    parser.add_argument("--since", default=None)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--volatility-days", type=int, default=14)
    parser.add_argument("--strict", action="store_true")
    return parser


def main() -> int:
    args = _build_parser().parse_args()
    as_of = date.fromisoformat(str(args.as_of))
    since = date.fromisoformat(str(args.since)) if args.since else (as_of - timedelta(days=90))
    try:
        report = validate_returns_economics_audit(
            db_path=args.db,
            as_of=as_of,
            since=since,
            output_root=args.output_root,
            volatility_days=int(args.volatility_days),
            strict=bool(args.strict),
        )
    except ReturnsEconomicsError as exc:
        print("status=FAIL")
        print("error_code=RETURNS_ECONOMICS_FAIL")
        print(f"message={exc}")
        return 1

    print(f"returns_economics_json={report['json_path']}")
    print(f"returns_economics_md={report['md_path']}")
    print(f"status={report['status']}")
    if report.get("error_code"):
        print(f"error_code={report['error_code']}")
    return 0 if report["ok"] or not args.strict else 1


if __name__ == "__main__":
    raise SystemExit(main())
