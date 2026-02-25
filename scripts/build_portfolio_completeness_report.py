#!/usr/bin/env python3
"""Build fail-closed portfolio completeness report for active SKUs."""

from __future__ import annotations

import argparse
from datetime import date, datetime, timezone
import json
from pathlib import Path
import sqlite3
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DB = PROJECT_ROOT / "db" / "app.db"
DEFAULT_OUTPUT_ROOT = PROJECT_ROOT / "exports" / "daily"
DEMAND_LOOKBACK_DAYS = 60


def _table_exists(conn: sqlite3.Connection, name: str) -> bool:
    row = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
        (name,),
    ).fetchone()
    return row is not None


def _table_columns(conn: sqlite3.Connection, name: str) -> set[str]:
    rows = conn.execute(f"PRAGMA table_info({name})").fetchall()
    return {str(row[1]) for row in rows}


def _render_md(payload: dict[str, Any]) -> str:
    lines = [
        "# Portfolio Completeness Report",
        "",
        f"- generated_at: `{payload['generated_at']}`",
        f"- as_of: `{payload['as_of']}`",
        f"- status: `{payload['status']}`",
        f"- active_skus: `{payload['active_skus']}`",
        f"- stock_covered: `{payload['stock_covered']}`",
        f"- demand_covered: `{payload['demand_covered']}`",
        f"- demand_required_skus: `{payload['demand_required_skus']}`",
        f"- pending_launch_count: `{payload['pending_launch_count']}`",
        f"- unit_econ_covered: `{payload['unit_econ_covered']}`",
        f"- coverage_pct: `{payload['coverage_pct']}`",
        "",
        "## Missing Counts",
        "",
        f"- missing_stock: `{payload['missing_stock_count']}`",
        f"- missing_demand: `{payload['missing_demand_count']}`",
        f"- missing_unit_econ: `{payload['missing_unit_econ_count']}`",
    ]
    pending = payload.get("pending_launch") or []
    if pending:
        lines.append("")
        lines.append("## pending_launch")
        lines.append("")
        for sku in pending[:50]:
            lines.append(f"- `{sku}`")
    for key in ("missing_stock", "missing_demand", "missing_unit_econ"):
        values = payload.get(key) or []
        if values:
            lines.append("")
            lines.append(f"## {key}")
            lines.append("")
            for sku in values[:50]:
                lines.append(f"- `{sku}`")
    return "\n".join(lines) + "\n"


def build_portfolio_completeness_report(
    *,
    db_path: Path,
    as_of: str,
    output_root: Path = DEFAULT_OUTPUT_ROOT,
    strict: bool = False,
) -> dict[str, Any]:
    if not db_path.exists():
        raise FileNotFoundError(f"db not found: {db_path}")

    as_of_date = date.fromisoformat(as_of)
    with sqlite3.connect(str(db_path)) as conn:
        conn.row_factory = sqlite3.Row
        required_tables = ["dim_sku", "fact_inventory_snapshot_size", "fact_demand_estimates"]
        missing_tables = [t for t in required_tables if not _table_exists(conn, t)]
        if missing_tables:
            raise RuntimeError(f"missing required tables: {', '.join(missing_tables)}")

        active_rows = conn.execute(
            """
            SELECT DISTINCT sku_key
            FROM dim_sku
            WHERE COALESCE(active_flag, 0) = 1
              AND sku_key IS NOT NULL
              AND TRIM(sku_key) <> ''
            ORDER BY sku_key
            """
        ).fetchall()
        active_skus = [str(row["sku_key"]) for row in active_rows]

        latest_snapshot = conn.execute(
            """
            SELECT MAX(snapshot_date) AS latest_snapshot
            FROM fact_inventory_snapshot_size
            WHERE snapshot_date <= ?
            """,
            (as_of,),
        ).fetchone()["latest_snapshot"]
        latest_demand = conn.execute(
            """
            SELECT MAX(cutoff_date) AS latest_cutoff
            FROM fact_demand_estimates
            WHERE cutoff_date <= ?
            """,
            (as_of,),
        ).fetchone()["latest_cutoff"]

        inventory_cols = _table_columns(conn, "fact_inventory_snapshot_size")
        has_current_stock = "current_stock" in inventory_cols
        has_inbound_stock = "inbound_stock" in inventory_cols

        stock_skus: set[str] = set()
        stock_qty_by_sku: dict[str, float] = {}
        inbound_qty_by_sku: dict[str, float] = {}
        if latest_snapshot:
            if has_current_stock or has_inbound_stock:
                current_expr = "COALESCE(current_stock, 0)" if has_current_stock else "0"
                inbound_expr = "COALESCE(inbound_stock, 0)" if has_inbound_stock else "0"
                rows = conn.execute(
                    f"""
                    SELECT sku_key,
                           SUM({current_expr}) AS current_stock_sum,
                           SUM({inbound_expr}) AS inbound_stock_sum
                    FROM fact_inventory_snapshot_size
                    WHERE snapshot_date = ?
                      AND sku_key IS NOT NULL
                      AND TRIM(sku_key) <> ''
                    GROUP BY sku_key
                    """,
                    (latest_snapshot,),
                ).fetchall()
                for row in rows:
                    sku = str(row["sku_key"])
                    current_sum = float(row["current_stock_sum"] or 0.0)
                    inbound_sum = float(row["inbound_stock_sum"] or 0.0)
                    stock_skus.add(sku)
                    stock_qty_by_sku[sku] = current_sum
                    inbound_qty_by_sku[sku] = inbound_sum
            else:
                rows = conn.execute(
                    """
                    SELECT DISTINCT sku_key
                    FROM fact_inventory_snapshot_size
                    WHERE snapshot_date = ?
                      AND sku_key IS NOT NULL
                      AND TRIM(sku_key) <> ''
                    """,
                    (latest_snapshot,),
                ).fetchall()
                stock_skus = {str(row["sku_key"]) for row in rows}
                for row in rows:
                    sku = str(row["sku_key"])
                    stock_qty_by_sku[sku] = 1.0
                    inbound_qty_by_sku[sku] = 0.0

        demand_skus: set[str] = set()
        if latest_demand:
            rows = conn.execute(
                """
                SELECT DISTINCT sku_key
                FROM fact_demand_estimates
                WHERE cutoff_date = ?
                  AND sku_key IS NOT NULL
                  AND TRIM(sku_key) <> ''
                """,
                (latest_demand,),
            ).fetchall()
            demand_skus = {str(row["sku_key"]) for row in rows}

        sales_recent_skus: set[str] = set()
        sales_by_sku: dict[str, float] = {}
        if _table_exists(conn, "fact_sales"):
            sales_cols = _table_columns(conn, "fact_sales")
            if {"sku_key", "order_date", "quantity"}.issubset(sales_cols):
                rows = conn.execute(
                    """
                    SELECT sku_key, SUM(COALESCE(quantity, 0)) AS qty_sum
                    FROM fact_sales
                    WHERE sku_key IS NOT NULL
                      AND TRIM(sku_key) <> ''
                      AND order_date >= date(?, ?)
                    GROUP BY sku_key
                    """,
                    (as_of, f"-{DEMAND_LOOKBACK_DAYS} day"),
                ).fetchall()
                for row in rows:
                    sku = str(row["sku_key"])
                    qty_sum = float(row["qty_sum"] or 0.0)
                    if qty_sum > 0:
                        sales_recent_skus.add(sku)
                    sales_by_sku[sku] = qty_sum

        unit_econ_rows = conn.execute(
            """
            SELECT sku_key, cogs_kzt, base_cost_cny, weight_kg
            FROM dim_sku
            WHERE COALESCE(active_flag, 0) = 1
              AND sku_key IS NOT NULL
              AND TRIM(sku_key) <> ''
            """
        ).fetchall()
        unit_econ_skus = {
            str(row["sku_key"])
            for row in unit_econ_rows
            if float(row["cogs_kzt"] or 0.0) > 0.0
            or (
                float(row["base_cost_cny"] or 0.0) > 0.0
                and float(row["weight_kg"] or 0.0) > 0.0
            )
        }

    active_set = set(active_skus)
    missing_stock = sorted(active_set - stock_skus)
    demand_required_set = {
        sku
        for sku in active_set
        if float(stock_qty_by_sku.get(sku, 0.0)) > 0.0
        or float(sales_by_sku.get(sku, 0.0)) > 0.0
    }
    pending_launch = sorted(
        sku
        for sku in active_set
        if sku not in demand_required_set and float(inbound_qty_by_sku.get(sku, 0.0)) > 0.0
    )
    missing_demand = sorted(demand_required_set - demand_skus)
    missing_unit_econ = sorted(active_set - unit_econ_skus)

    active_total = len(active_skus)
    stock_covered = active_total - len(missing_stock)
    demand_covered = active_total - len(missing_demand)
    unit_econ_covered = active_total - len(missing_unit_econ)
    strict_ok = active_total > 0 and not (missing_stock or missing_demand or missing_unit_econ)
    coverage_pct = round(
        (min(stock_covered, demand_covered, unit_econ_covered) / active_total) * 100.0,
        2,
    ) if active_total else 0.0

    payload = {
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "as_of": as_of_date.isoformat(),
        "status": "GREEN" if strict_ok else "RED",
        "ok": strict_ok,
        "active_skus": active_total,
        "latest_snapshot_date": latest_snapshot,
        "latest_demand_cutoff": latest_demand,
        "stock_covered": stock_covered,
        "demand_covered": demand_covered,
        "demand_required_skus": len(demand_required_set),
        "pending_launch_count": len(pending_launch),
        "unit_econ_covered": unit_econ_covered,
        "coverage_pct": coverage_pct,
        "missing_stock_count": len(missing_stock),
        "missing_demand_count": len(missing_demand),
        "missing_unit_econ_count": len(missing_unit_econ),
        "missing_stock": missing_stock,
        "missing_demand": missing_demand,
        "missing_unit_econ": missing_unit_econ,
        "pending_launch": pending_launch,
    }

    out_dir = Path(output_root).resolve() / as_of
    out_dir.mkdir(parents=True, exist_ok=True)
    json_path = out_dir / "portfolio_completeness_report.json"
    md_path = out_dir / "portfolio_completeness_report.md"
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    md_path.write_text(_render_md(payload), encoding="utf-8")

    return {
        "ok": strict_ok,
        "exit_code": 0 if (strict_ok or not strict) else 1,
        "json_path": str(json_path),
        "md_path": str(md_path),
        "payload": payload,
    }


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build active-portfolio completeness report")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument("--as-of", default=date.today().isoformat())
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--strict", action="store_true")
    return parser


def main() -> int:
    args = _build_parser().parse_args()
    report = build_portfolio_completeness_report(
        db_path=args.db,
        as_of=args.as_of,
        output_root=args.output_root,
        strict=bool(args.strict),
    )
    print(f"portfolio_completeness_json={report['json_path']}")
    print(f"portfolio_completeness_md={report['md_path']}")
    print(f"status={'PASS' if report['ok'] else 'FAIL'}")
    return int(report["exit_code"])


if __name__ == "__main__":
    raise SystemExit(main())
