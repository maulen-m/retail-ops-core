#!/usr/bin/env python3
"""COGS realism audit for decision-grade profit trust."""

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

from core.calc.economics import calc_cogs
from core.config.business_params import get_fx_rates
from core.sales import ensure_sales_truth_views

DEFAULT_DB = PROJECT_ROOT / "db" / "app.db"
DEFAULT_OUTPUT_ROOT = PROJECT_ROOT / "exports" / "validation" / "cogs_realism"


class CogsAuditError(RuntimeError):
    """Raised when strict COGS realism audit fails."""


def _connect_readonly(db_path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(f"file:{db_path.resolve()}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def _relation_exists(conn: sqlite3.Connection, name: str) -> bool:
    return (
        conn.execute(
            """
            SELECT 1
            FROM sqlite_master
            WHERE name=? AND type IN ('table', 'view')
            """,
            (name,),
        ).fetchone()
        is not None
    )


def _render_md(report: dict[str, Any]) -> str:
    lines = [
        "# COGS Realism Audit",
        "",
        f"- generated_at: `{report['generated_at']}`",
        f"- as_of: `{report['as_of']}`",
        f"- window: `{report['window_start']} -> {report['window_end']}`",
        f"- status: `{report['status']}`",
        f"- error_code: `{report.get('error_code') or 'none'}`",
        f"- formula_coverage_pct: `{report['coverage']['formula_input_coverage_pct']:.2f}`",
        f"- fx_used: `cny_kzt={report['fx_rates']['cny_kzt']}, usd_kzt={report['fx_rates']['usd_kzt']}, dlv_rate_usd_kg={report['fx_rates']['dlv_rate_usd_kg']}`",
        "",
        "## Top SKUs By Net Revenue",
        "",
        "| sku_key | units | net_rev_kzt | cogs_kzt | profit_kzt | margin_pct | base_cost_cny | weight_kg |",
        "|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for row in report["top_skus"]:
        lines.append(
            f"| `{row['sku_key']}` | {row['units']:.2f} | {row['net_rev_kzt']:.2f} | {row['cogs_kzt']:.2f} | "
            f"{row['profit_kzt']:.2f} | {row['margin_pct']:.2f}% | "
            f"{row['base_cost_cny'] if row['base_cost_cny'] is not None else 'N/A'} | "
            f"{row['weight_kg'] if row['weight_kg'] is not None else 'N/A'} |"
        )
    lines.extend(
        [
            "",
            "## Sensitivity Scenarios",
            "",
            "| scenario | usd_kzt_mult | dlv_rate_mult | cogs_kzt | profit_kzt | profit_delta_kzt |",
            "|---|---:|---:|---:|---:|---:|",
        ]
    )
    for row in report["sensitivity"]:
        lines.append(
            f"| `{row['scenario']}` | {row['usd_kzt_multiplier']:.2f} | {row['dlv_rate_multiplier']:.2f} | "
            f"{row['projected_cogs_kzt']:.2f} | {row['projected_profit_kzt']:.2f} | {row['profit_delta_kzt']:.2f} |"
        )
    if report["errors"]:
        lines.extend(["", "## Errors", ""])
        for err in report["errors"]:
            lines.append(f"- {err}")
    return "\n".join(lines) + "\n"


def _load_top_skus(
    *,
    conn: sqlite3.Connection,
    start_date: date,
    end_date: date,
    top_n: int,
) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT
            COALESCE(v.sku_key, '<missing>') AS sku_key,
            SUM(COALESCE(v.units, 0)) AS units,
            SUM(COALESCE(v.net_rev_kzt, 0)) AS net_rev_kzt,
            SUM(COALESCE(v.cogs_kzt, 0)) AS cogs_kzt,
            SUM(COALESCE(v.profit_kzt, 0)) AS profit_kzt,
            AVG(COALESCE(s.base_cost_cny, 0)) AS base_cost_cny_raw,
            AVG(COALESCE(s.weight_kg, 0)) AS weight_kg_raw
        FROM view_sales_line_truth v
        LEFT JOIN dim_sku s
          ON UPPER(COALESCE(v.sku_key, '')) = UPPER(COALESCE(s.sku_key, ''))
        WHERE date(v.sale_date) BETWEEN ? AND ?
        GROUP BY COALESCE(v.sku_key, '<missing>')
        ORDER BY SUM(COALESCE(v.net_rev_kzt, 0)) DESC
        LIMIT ?
        """,
        (start_date.isoformat(), end_date.isoformat(), int(top_n)),
    ).fetchall()

    out: list[dict[str, Any]] = []
    for row in rows:
        net_rev = float(row["net_rev_kzt"] or 0.0)
        profit = float(row["profit_kzt"] or 0.0)
        margin_pct = (profit / net_rev * 100.0) if abs(net_rev) > 1e-9 else 0.0
        base_cost = float(row["base_cost_cny_raw"] or 0.0)
        weight = float(row["weight_kg_raw"] or 0.0)
        out.append(
            {
                "sku_key": str(row["sku_key"]),
                "units": round(float(row["units"] or 0.0), 2),
                "net_rev_kzt": round(net_rev, 2),
                "cogs_kzt": round(float(row["cogs_kzt"] or 0.0), 2),
                "profit_kzt": round(profit, 2),
                "margin_pct": round(margin_pct, 2),
                "base_cost_cny": round(base_cost, 4) if base_cost > 0 else None,
                "weight_kg": round(weight, 4) if weight > 0 else None,
            }
        )
    return out


def _load_formula_lines(
    *,
    conn: sqlite3.Connection,
    start_date: date,
    end_date: date,
) -> tuple[pd.DataFrame, int]:
    base = pd.read_sql_query(
        """
        SELECT
            sf.order_id,
            date(sf.order_date) AS sale_date,
            UPPER(COALESCE(sf.store_code, 'UNKNOWN')) AS store_code,
            COALESCE(sf.sku_key, '') AS sku_key,
            COALESCE(sf.quantity, 0) AS quantity,
            COALESCE(sf.net_rev, 0) AS net_rev,
            COALESCE(ds.base_cost_cny, 0) AS base_cost_cny,
            COALESCE(ds.weight_kg, 0) AS weight_kg
        FROM sales_fact_v2 sf
        LEFT JOIN dim_sku ds
          ON UPPER(COALESCE(sf.sku_key, '')) = UPPER(COALESCE(ds.sku_key, ''))
        WHERE date(sf.order_date) BETWEEN ? AND ?
          AND UPPER(COALESCE(sf.status, '')) = 'DELIVERED'
          AND COALESCE(sf.return_flag, 0) = 0
        """,
        conn,
        params=(start_date.isoformat(), end_date.isoformat()),
    )
    total_lines = int(len(base))
    if base.empty:
        return base, total_lines
    numeric = base.copy()
    for col in ("quantity", "net_rev", "base_cost_cny", "weight_kg"):
        numeric[col] = pd.to_numeric(numeric[col], errors="coerce").fillna(0.0)
    usable = numeric[(numeric["quantity"] > 0) & (numeric["base_cost_cny"] > 0) & (numeric["weight_kg"] > 0)]
    return usable, total_lines


def _build_sensitivity(
    *,
    formula_lines: pd.DataFrame,
    cny_kzt: float,
    usd_kzt: float,
    dlv_rate_usd_kg: float,
) -> list[dict[str, Any]]:
    baseline_cogs = 0.0
    baseline_net_rev = float(formula_lines["net_rev"].sum()) if not formula_lines.empty else 0.0
    for _, row in formula_lines.iterrows():
        unit_cogs = calc_cogs(
            base_cost_cny=float(row["base_cost_cny"]),
            weight_kg=float(row["weight_kg"]),
            cny_kzt=float(cny_kzt),
            freight_rate=float(usd_kzt),
            volumetric_factor=float(dlv_rate_usd_kg),
        )
        baseline_cogs += unit_cogs * float(row["quantity"])
    baseline_profit = baseline_net_rev - baseline_cogs

    scenarios = [
        ("BASE", 1.0, 1.0),
        ("USD_PLUS_10", 1.10, 1.0),
        ("USD_MINUS_10", 0.90, 1.0),
        ("DLV_PLUS_20", 1.0, 1.20),
        ("DLV_MINUS_20", 1.0, 0.80),
    ]
    out: list[dict[str, Any]] = []
    for name, usd_mult, dlv_mult in scenarios:
        cogs_total = 0.0
        for _, row in formula_lines.iterrows():
            unit_cogs = calc_cogs(
                base_cost_cny=float(row["base_cost_cny"]),
                weight_kg=float(row["weight_kg"]),
                cny_kzt=float(cny_kzt),
                freight_rate=float(usd_kzt) * float(usd_mult),
                volumetric_factor=float(dlv_rate_usd_kg) * float(dlv_mult),
            )
            cogs_total += unit_cogs * float(row["quantity"])
        projected_profit = baseline_net_rev - cogs_total
        out.append(
            {
                "scenario": name,
                "usd_kzt_multiplier": float(usd_mult),
                "dlv_rate_multiplier": float(dlv_mult),
                "projected_cogs_kzt": round(float(cogs_total), 2),
                "projected_profit_kzt": round(float(projected_profit), 2),
                "profit_delta_kzt": round(float(projected_profit - baseline_profit), 2),
            }
        )
    return out


def audit_cogs_realism(
    *,
    db_path: Path,
    as_of: date,
    days: int,
    top_n: int,
    output_root: Path,
    min_formula_input_coverage_pct: float = 90.0,
    strict: bool = False,
    ensure_views: bool = False,
) -> dict[str, Any]:
    if days <= 0:
        raise CogsAuditError("days must be > 0")
    start_date = as_of - timedelta(days=int(days) - 1)
    errors: list[str] = []
    error_codes: list[str] = []

    if not db_path.exists():
        raise CogsAuditError(f"db not found: {db_path}")

    conn = sqlite3.connect(str(db_path)) if ensure_views else _connect_readonly(db_path)
    conn.row_factory = sqlite3.Row
    try:
        if ensure_views:
            ensure_sales_truth_views(conn)
        elif not _relation_exists(conn, "view_sales_line_truth"):
            raise CogsAuditError(
                "view_sales_line_truth is missing. Build sales truth views through a governed "
                "schema/view-refresh lane before running the read-only COGS audit."
            )
        top_skus = _load_top_skus(conn=conn, start_date=start_date, end_date=as_of, top_n=top_n)
        formula_lines, total_lines = _load_formula_lines(conn=conn, start_date=start_date, end_date=as_of)
    finally:
        conn.close()

    usable_lines = int(len(formula_lines))
    coverage_pct = (float(usable_lines) / float(total_lines) * 100.0) if total_lines > 0 else 0.0
    if total_lines <= 0:
        error_codes.append("NO_DELIVERED_LINES")
        errors.append("no delivered non-return sales_fact_v2 lines found in selected window")
    if coverage_pct < float(min_formula_input_coverage_pct):
        error_codes.append("COGS_INPUT_COVERAGE_FAIL")
        errors.append(
            f"formula input coverage below threshold: {coverage_pct:.2f}% < {float(min_formula_input_coverage_pct):.2f}%"
        )

    fx = get_fx_rates(as_of_date=as_of, db_path=db_path)
    sensitivity = _build_sensitivity(
        formula_lines=formula_lines,
        cny_kzt=float(fx.cny_kzt),
        usd_kzt=float(fx.usd_kzt),
        dlv_rate_usd_kg=float(fx.dlv_rate_usd_kg),
    )

    out_dir = output_root.resolve() / as_of.isoformat()
    out_dir.mkdir(parents=True, exist_ok=True)
    top_csv = out_dir / "top_skus_margin.csv"
    sensitivity_csv = out_dir / "cogs_sensitivity.csv"
    pd.DataFrame(top_skus).to_csv(top_csv, index=False, encoding="utf-8")
    pd.DataFrame(sensitivity).to_csv(sensitivity_csv, index=False, encoding="utf-8")

    report = {
        "generated_at": datetime.now(timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z"),
        "as_of": as_of.isoformat(),
        "window_start": start_date.isoformat(),
        "window_end": as_of.isoformat(),
        "status": "PASS" if not errors else "FAIL",
        "ok": len(errors) == 0,
        "error_code": error_codes[0] if error_codes else None,
        "error_codes": error_codes,
        "errors": errors,
        "db_path": str(db_path.resolve()),
        "coverage": {
            "total_lines": total_lines,
            "formula_input_lines": usable_lines,
            "formula_input_coverage_pct": round(coverage_pct, 2),
            "min_formula_input_coverage_pct": float(min_formula_input_coverage_pct),
        },
        "fx_rates": {
            "cny_kzt": float(fx.cny_kzt),
            "usd_kzt": float(fx.usd_kzt),
            "dlv_rate_usd_kg": float(fx.dlv_rate_usd_kg),
            "source": str(getattr(fx, "source", "unknown")),
        },
        "top_skus": top_skus,
        "sensitivity": sensitivity,
        "top_skus_csv": str(top_csv),
        "sensitivity_csv": str(sensitivity_csv),
    }
    json_path = out_dir / "cogs_realism_report.json"
    md_path = out_dir / "cogs_realism_report.md"
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    md_path.write_text(_render_md(report), encoding="utf-8")
    report["json_path"] = str(json_path)
    report["md_path"] = str(md_path)

    if strict and errors:
        raise CogsAuditError("cogs realism audit failed")
    return report


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Audit COGS realism for top SKUs and sensitivity.")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument("--as-of", required=True)
    parser.add_argument("--days", type=int, default=60)
    parser.add_argument("--top-n", type=int, default=20)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--min-formula-input-coverage-pct", type=float, default=90.0)
    parser.add_argument("--strict", action="store_true")
    parser.add_argument(
        "--ensure-views",
        action="store_true",
        help=(
            "Create/recreate sales truth views before auditing. Intended for temp DB tests; "
            "normal production audit mode is read-only."
        ),
    )
    return parser


def main() -> int:
    args = _build_parser().parse_args()
    report = audit_cogs_realism(
        db_path=args.db,
        as_of=date.fromisoformat(str(args.as_of)),
        days=int(args.days),
        top_n=int(args.top_n),
        output_root=args.output_root,
        min_formula_input_coverage_pct=float(args.min_formula_input_coverage_pct),
        strict=bool(args.strict),
        ensure_views=bool(args.ensure_views),
    )
    print(f"cogs_realism_json={report['json_path']}")
    print(f"cogs_realism_md={report['md_path']}")
    print(f"status={report['status']}")
    if report.get("error_code"):
        print(f"error_code={report['error_code']}")
    return 0 if report["ok"] or not args.strict else 1


if __name__ == "__main__":
    raise SystemExit(main())
