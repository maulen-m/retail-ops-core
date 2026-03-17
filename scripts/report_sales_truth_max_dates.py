#!/usr/bin/env python3
"""Report raw-vs-published sales truth max dates for owner-surface recency auditing."""

from __future__ import annotations

import argparse
from datetime import date, datetime, timezone
import json
from pathlib import Path
import sqlite3
from typing import Any


def _now_utc() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _table_exists(conn: sqlite3.Connection, table: str) -> bool:
    row = conn.execute(
        "SELECT name FROM sqlite_master WHERE type IN ('table','view') AND name = ?",
        (table,),
    ).fetchone()
    return row is not None


def _column_exists(conn: sqlite3.Connection, table: str, column: str) -> bool:
    rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    return any(str(row[1]) == column for row in rows)


def _select_max(conn: sqlite3.Connection, table: str, column: str, where: str | None = None) -> str | None:
    if not _table_exists(conn, table) or not _column_exists(conn, table, column):
        return None
    query = f"SELECT MAX({column}) FROM {table}"
    if where:
        query += f" WHERE {where}"
    row = conn.execute(query).fetchone()
    return str(row[0]) if row and row[0] is not None else None


def _load_json(path: Path | None) -> dict[str, Any]:
    if path is None or not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _coerce_iso_date(value: str | None) -> str | None:
    if not value:
        return None
    text = str(value).strip()
    if not text:
        return None
    return text[:10]


def _lag_days(later: str | None, earlier: str | None) -> int | None:
    if not later or not earlier:
        return None
    return (date.fromisoformat(later) - date.fromisoformat(earlier)).days


def build_sales_truth_max_dates_report(
    *,
    as_of: str,
    db_path: Path,
    owner_truth_summary_path: Path | None,
    system_health_path: Path | None,
) -> dict[str, Any]:
    conn = sqlite3.connect(str(db_path))
    try:
        raw = {
            "fact_orders_created_max": _coerce_iso_date(_select_max(conn, "fact_orders_kaspi", "created_at")),
            "fact_orders_updated_max": _coerce_iso_date(_select_max(conn, "fact_orders_kaspi", "updated_at")),
            "fact_orders_status_updated_max": _coerce_iso_date(_select_max(conn, "fact_orders_kaspi", "status_updated_at")),
            "sales_fact_v2_any_max": _coerce_iso_date(_select_max(conn, "sales_fact_v2", "order_date")),
            "sales_fact_v2_delivered_max": _coerce_iso_date(
                _select_max(
                    conn,
                    "sales_fact_v2",
                    "order_date",
                    "UPPER(COALESCE(status, 'DELIVERED')) = 'DELIVERED' AND COALESCE(return_flag, 0) = 0",
                )
            ),
            "fact_sales_historical_max": _coerce_iso_date(_select_max(conn, "fact_sales", "order_date")),
            "fact_sales_external_ref_max": _coerce_iso_date(
                _select_max(
                    conn,
                    "fact_sales_external_ref",
                    "sale_date" if _column_exists(conn, "fact_sales_external_ref", "sale_date") else "order_date",
                )
            ),
            "fact_sales_workbook_anchor_max": _coerce_iso_date(
                _select_max(
                    conn,
                    "fact_sales_workbook_anchor",
                    "sale_date" if _column_exists(conn, "fact_sales_workbook_anchor", "sale_date") else "order_date",
                )
            ),
        }
        published = {
            "view_sales_line_truth_max": _coerce_iso_date(_select_max(conn, "view_sales_line_truth", "sale_date")),
            "view_sales_daily_truth_max": _coerce_iso_date(_select_max(conn, "view_sales_daily_truth", "sale_date")),
        }
    finally:
        conn.close()

    owner_truth = _load_json(owner_truth_summary_path)
    system_health = _load_json(system_health_path)
    published_max = published["view_sales_daily_truth_max"]
    raw_delivered_max = raw["sales_fact_v2_delivered_max"]
    workbook_anchor_max = raw["fact_sales_workbook_anchor_max"]
    anchor_binding = bool(
        published_max
        and workbook_anchor_max
        and published_max == workbook_anchor_max
        and raw_delivered_max
        and raw_delivered_max > published_max
    )

    explanation: list[str] = [
        "Raw recent sales chronology comes from `sales_fact_v2` and order lifecycle tables.",
        "Published owner-facing sales truth comes from `view_sales_line_truth` / `view_sales_daily_truth` only.",
        "Published truth can lag raw staging because workbook chronology (`fact_sales_workbook_anchor`) can restamp sale_date and cap recent published dates.",
        "Owner surfaces must read published truth or derived owner outputs; they must not read raw `sales_fact_v2` directly.",
    ]
    if anchor_binding:
        explanation.append(
            "Current report shows workbook chronology is binding: published max date equals workbook-anchor max date and trails raw delivered staging."
        )

    return {
        "generated_at": _now_utc(),
        "as_of": as_of,
        "db_path": str(db_path),
        "owner_truth_summary_path": str(owner_truth_summary_path) if owner_truth_summary_path else None,
        "system_health_path": str(system_health_path) if system_health_path else None,
        "truth_source": owner_truth.get("truth_source") or system_health.get("truth_source"),
        "owner_truth_as_of": owner_truth.get("as_of"),
        "system_health_as_of": system_health.get("as_of"),
        "raw_max_dates": raw,
        "published_max_dates": published,
        "derived": {
            "published_vs_raw_delivered_lag_days": _lag_days(raw_delivered_max, published_max),
            "published_vs_workbook_anchor_lag_days": _lag_days(workbook_anchor_max, published_max),
            "anchor_binding": anchor_binding,
            "raw_recentity_explained_by": "fact_sales_workbook_anchor" if anchor_binding else "no_binding_anchor_detected",
        },
        "explanation": explanation,
    }


def _render_md(report: dict[str, Any]) -> str:
    raw = report["raw_max_dates"]
    published = report["published_max_dates"]
    derived = report["derived"]
    lines = [
        "# Raw vs Published Sales Max Dates",
        "",
        f"- generated_at: `{report['generated_at']}`",
        f"- as_of: `{report['as_of']}`",
        f"- truth_source: `{report.get('truth_source')}`",
        f"- owner_truth_as_of: `{report.get('owner_truth_as_of')}`",
        f"- system_health_as_of: `{report.get('system_health_as_of')}`",
        "",
        "## Raw Layers",
        "",
        f"- fact_orders_created_max: `{raw.get('fact_orders_created_max')}`",
        f"- fact_orders_updated_max: `{raw.get('fact_orders_updated_max')}`",
        f"- fact_orders_status_updated_max: `{raw.get('fact_orders_status_updated_max')}`",
        f"- sales_fact_v2_any_max: `{raw.get('sales_fact_v2_any_max')}`",
        f"- sales_fact_v2_delivered_max: `{raw.get('sales_fact_v2_delivered_max')}`",
        f"- fact_sales_historical_max: `{raw.get('fact_sales_historical_max')}`",
        f"- fact_sales_external_ref_max: `{raw.get('fact_sales_external_ref_max')}`",
        f"- fact_sales_workbook_anchor_max: `{raw.get('fact_sales_workbook_anchor_max')}`",
        "",
        "## Published Layers",
        "",
        f"- view_sales_line_truth_max: `{published.get('view_sales_line_truth_max')}`",
        f"- view_sales_daily_truth_max: `{published.get('view_sales_daily_truth_max')}`",
        "",
        "## Derived",
        "",
        f"- published_vs_raw_delivered_lag_days: `{derived.get('published_vs_raw_delivered_lag_days')}`",
        f"- published_vs_workbook_anchor_lag_days: `{derived.get('published_vs_workbook_anchor_lag_days')}`",
        f"- anchor_binding: `{derived.get('anchor_binding')}`",
        f"- raw_recentity_explained_by: `{derived.get('raw_recentity_explained_by')}`",
        "",
        "## Explanation",
        "",
    ]
    for item in report.get("explanation") or []:
        lines.append(f"- {item}")
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description="Report raw-vs-published sales max dates.")
    parser.add_argument("--as-of", required=True)
    parser.add_argument("--db", type=Path, default=Path("db/app.db"))
    parser.add_argument("--owner-truth-summary", type=Path, default=None)
    parser.add_argument("--system-health", type=Path, default=None)
    parser.add_argument("--output-json", type=Path, required=True)
    parser.add_argument("--output-md", type=Path, required=True)
    args = parser.parse_args()

    report = build_sales_truth_max_dates_report(
        as_of=args.as_of,
        db_path=args.db,
        owner_truth_summary_path=args.owner_truth_summary,
        system_health_path=args.system_health,
    )
    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    args.output_md.parent.mkdir(parents=True, exist_ok=True)
    args.output_json.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    args.output_md.write_text(_render_md(report), encoding="utf-8")
    print(f"output_json={args.output_json.resolve()}")
    print(f"output_md={args.output_md.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
