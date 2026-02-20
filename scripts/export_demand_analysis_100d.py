#!/usr/bin/env python3
"""
Export demand analysis for SKUs sold in the last 100 days.

Includes denoised demand estimates, OOS/partial-OOS diagnostics, and
dashboard delta vs anchor for SKUs present in PLAN-0.
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from datetime import date, timedelta
from pathlib import Path

# Add project root to path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from core.db import get_db
from core.db.queries import get_cutoff_date_almaty
from core.calc.demand_estimator import DemandEstimator, DemandEstimatorConfig

DB_PATH = PROJECT_ROOT / "db" / "app.db"
EXPORTS_DIR = PROJECT_ROOT / "exports"
PO_DASHBOARD_JSON = PROJECT_ROOT / "exports" / "po_dashboard_data.json"


def _load_plan0_demand(json_path: Path) -> tuple[dict[str, float], str | None]:
    if not json_path.exists():
        return {}, None
    data = json.loads(json_path.read_text())
    cutoff = data.get("cutoff_date")
    pos = data.get("pos", {})
    plan0 = pos.get("PLAN-0")
    if not plan0 and "sku_level" in data:
        plan0 = data
    if not plan0:
        return {}, cutoff
    mapping = {}
    for sku in plan0.get("sku_level", []):
        sku_key = sku.get("sku_key")
        d_sku = sku.get("d_sku")
        if sku_key and d_sku is not None:
            mapping[sku_key] = float(d_sku)
    return mapping, cutoff


def _fetch_dim_sku_meta(conn, sku_keys: list[str]) -> dict[str, dict]:
    if not sku_keys:
        return {}
    meta: dict[str, dict] = {}
    chunk_size = 800
    for i in range(0, len(sku_keys), chunk_size):
        chunk = sku_keys[i:i + chunk_size]
        placeholders = ",".join(["?"] * len(chunk))
        rows = conn.execute(
            f"""
            SELECT sku_key, model, product_type
            FROM dim_sku
            WHERE sku_key IN ({placeholders})
            """,
            chunk,
        ).fetchall()
        for row in rows:
            meta[row["sku_key"]] = {
                "model": row["model"],
                "product_type": row["product_type"],
            }
    return meta


def _load_sales_summary(conn, start_date: str, end_date: str) -> dict[str, dict]:
    rows = conn.execute(
        """
        SELECT
            sku_key,
            COUNT(DISTINCT order_date) AS sales_days,
            SUM(quantity) AS total_units
        FROM sales_fact_v2
        WHERE order_date >= ?
          AND order_date <= ?
          AND status NOT IN ('CANCELLED', 'RETURNED')
        GROUP BY sku_key
        HAVING SUM(quantity) > 0
        """,
        (start_date, end_date),
    ).fetchall()
    summary: dict[str, dict] = {}
    for row in rows:
        summary[row["sku_key"]] = {
            "sales_days": row["sales_days"] or 0,
            "total_units": row["total_units"] or 0,
        }
    return summary


def build_report(
    db_path: Path,
    cutoff_date: date,
    output_path: Path,
) -> Path:
    EXPORTS_DIR.mkdir(parents=True, exist_ok=True)
    dashboard_d, dashboard_cutoff = _load_plan0_demand(PO_DASHBOARD_JSON)

    start_date = cutoff_date - timedelta(days=99)
    start_str = start_date.isoformat()
    end_str = cutoff_date.isoformat()

    config = DemandEstimatorConfig(lookback_days=100)
    estimator = DemandEstimator(db_path=db_path, config=config, use_db_anchors=True)

    with get_db(db_path) as conn:
        sales_summary = _load_sales_summary(conn, start_str, end_str)
        sku_keys = sorted(sales_summary.keys())
        sku_meta = _fetch_dim_sku_meta(conn, sku_keys)

    rows = []
    for sku_key in sku_keys:
        summary = sales_summary[sku_key]
        try:
            result = estimator.estimate_demand(sku_key)
        except Exception as exc:
            rows.append(
                {
                    "sku_key": sku_key,
                    "error": str(exc),
                }
            )
            continue

        meta = sku_meta.get(sku_key, {})
        d_anchor = round(result.d_anchor, 4)
        d_final = round(result.d_final, 4)
        d_data = round(result.d_data, 4)
        d_dashboard = dashboard_d.get(sku_key)
        delta_dashboard_anchor = None
        if d_dashboard is not None:
            delta_dashboard_anchor = round(d_dashboard - result.d_anchor, 4)

        rows.append(
            {
                "sku_key": sku_key,
                "model": meta.get("model"),
                "product_type": meta.get("product_type"),
                "cutoff_date": end_str,
                "window_start": start_str,
                "window_days": 100,
                "sales_days_100d": summary["sales_days"],
                "total_units_100d": summary["total_units"],
                "d_anchor": d_anchor,
                "d_data": d_data,
                "d_final": d_final,
                "sigma_anchor": round(result.sigma_anchor, 4),
                "sigma_data": round(result.sigma_data, 4),
                "sigma_final": round(result.sigma_final, 4),
                "anchor_weight": round(result.anchor_weight, 4),
                "confidence": result.confidence.value,
                "calendar_days": result.calendar_days,
                "sales_coverage_days": result.sales_coverage_days,
                "eligible_days": result.eligible_days,
                "good_days": result.good_days,
                "availability_score": round(result.availability_score, 4),
                "oos_type": result.oos_type.value,
                "partial_oos_sizes": ",".join(result.partial_oos_sizes),
                "suppression_count": result.suppression_count,
                "winsorize_pctl": config.winsorize_percentile,
                "in_po_dashboard": "Y" if sku_key in dashboard_d else "N",
                "d_dashboard": round(d_dashboard, 4) if d_dashboard is not None else None,
                "delta_dashboard_vs_anchor": delta_dashboard_anchor,
                "delta_final_vs_anchor": round(result.d_final - result.d_anchor, 4),
                "warnings": "; ".join(result.warnings),
            }
        )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "sku_key",
        "model",
        "product_type",
        "cutoff_date",
        "window_start",
        "window_days",
        "sales_days_100d",
        "total_units_100d",
        "d_anchor",
        "d_data",
        "d_final",
        "sigma_anchor",
        "sigma_data",
        "sigma_final",
        "anchor_weight",
        "confidence",
        "calendar_days",
        "sales_coverage_days",
        "eligible_days",
        "good_days",
        "availability_score",
        "oos_type",
        "partial_oos_sizes",
        "suppression_count",
        "winsorize_pctl",
        "in_po_dashboard",
        "d_dashboard",
        "delta_dashboard_vs_anchor",
        "delta_final_vs_anchor",
        "warnings",
        "error",
    ]

    with open(output_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)

    print(f"Demand analysis written to: {output_path}")
    if dashboard_cutoff:
        print(f"Dashboard cutoff (for reference): {dashboard_cutoff}")
    return output_path


def main() -> int:
    parser = argparse.ArgumentParser(description="Export demand analysis for last 100 days")
    parser.add_argument("--db", type=Path, default=DB_PATH, help="Path to SQLite DB")
    parser.add_argument("--cutoff-date", type=str, help="Cutoff date YYYY-MM-DD (default: Almaty yesterday)")
    parser.add_argument("--output", type=Path, help="Output CSV path")
    args = parser.parse_args()

    if not args.db.exists():
        print(f"ERROR: Database not found at {args.db}")
        return 1

    if args.cutoff_date:
        cutoff = date.fromisoformat(args.cutoff_date)
    else:
        cutoff = get_cutoff_date_almaty()

    output_path = args.output
    if output_path is None:
        stamp = cutoff.strftime("%Y%m%d")
        output_path = EXPORTS_DIR / f"demand_analysis_100d_{stamp}.csv"

    build_report(args.db, cutoff, output_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
