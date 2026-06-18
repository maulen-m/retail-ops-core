#!/usr/bin/env python3
"""Validate published sales COGS integrity for a recent window."""

from __future__ import annotations

import argparse
from datetime import date, timedelta
from pathlib import Path
import sqlite3
import sys
from typing import Any

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from core.db.validation_copy import validation_db_copy
from core.sales import ensure_sales_truth_views
from scripts.validate_cogs_completeness_by_month import (
    CogsCompletenessError,
    UNIT_COGS_COPIED_TEMP_SOURCE,
    _apply_unit_cogs_evidence,
)

DEFAULT_DB = PROJECT_ROOT / "db" / "app.db"


def _window_bounds(as_of: str | None, days: int) -> tuple[str, str]:
    end = date.fromisoformat(as_of) if as_of else date.today()
    start = end - timedelta(days=max(1, int(days)) - 1)
    return start.isoformat(), end.isoformat()


def validate_cogs_integrity(
    *,
    db_path: Path,
    as_of: str | None = None,
    days: int = 30,
    max_unresolved_rows: int = 0,
    max_unresolved_skus: int = 0,
    unit_cogs_evidence_csv: Path | None = None,
) -> dict[str, Any]:
    start, end = _window_bounds(as_of, days)
    errors: list[str] = []

    with validation_db_copy(db_path) as conn:
        conn.row_factory = sqlite3.Row
        ensure_sales_truth_views(conn)
        lines = pd.read_sql_query(
            """
            SELECT
                CAST(order_id AS TEXT) AS order_id,
                date(sale_date) AS sale_date,
                store_code,
                COALESCE(sku_key, '') AS sku_key,
                COALESCE(units, 0) AS units,
                COALESCE(net_rev_kzt, 0) AS net_rev_kzt,
                cogs_kzt,
                profit_kzt,
                COALESCE(cogs_source, 'unresolved') AS cogs_source
            FROM view_sales_line_truth
            WHERE date(sale_date) BETWEEN ? AND ?
            """,
            conn,
            params=[start, end],
        )

    unit_cogs_evidence_applied_rows = 0
    unit_cogs_evidence_applied_skus = 0
    if unit_cogs_evidence_csv is not None:
        try:
            lines, applied = _apply_unit_cogs_evidence(lines, unit_cogs_evidence_csv)
            unit_cogs_evidence_applied_rows = int(len(applied))
            unit_cogs_evidence_applied_skus = int(applied["sku_key"].nunique()) if not applied.empty else 0
            if "profit_kzt" in lines.columns and "net_rev_kzt" in lines.columns:
                applied_mask = (
                    lines["cogs_source"].fillna("").astype(str) == UNIT_COGS_COPIED_TEMP_SOURCE
                )
                lines.loc[applied_mask, "profit_kzt"] = (
                    pd.to_numeric(lines.loc[applied_mask, "net_rev_kzt"], errors="coerce").fillna(0.0)
                    - pd.to_numeric(lines.loc[applied_mask, "cogs_kzt"], errors="coerce").fillna(0.0)
                )
        except CogsCompletenessError as exc:
            errors.append(str(exc))

    total_rows = int(len(lines))
    formula_rows = int((lines["cogs_source"].fillna("").astype(str) == "formula_full").sum()) if total_rows else 0
    unresolved_mask = (
        (lines["cogs_source"].fillna("unresolved").astype(str).str.lower() == "unresolved")
        | (pd.to_numeric(lines["cogs_kzt"], errors="coerce").isna())
        | (pd.to_numeric(lines["profit_kzt"], errors="coerce").isna())
    ) if total_rows else pd.Series(dtype=bool)
    unresolved_rows = int(unresolved_mask.sum()) if total_rows else 0
    unresolved_skus = int(lines.loc[unresolved_mask, "sku_key"].nunique()) if total_rows else 0

    if total_rows <= 0:
        errors.append(f"no published sales rows found in window {start}..{end}")
    if unresolved_rows > int(max_unresolved_rows):
        errors.append(
            f"unresolved COGS rows exceed threshold: "
            f"{unresolved_rows} > {int(max_unresolved_rows)}"
        )
    if unresolved_skus > int(max_unresolved_skus):
        errors.append(
            f"unresolved COGS SKU count exceed threshold: "
            f"{unresolved_skus} > {int(max_unresolved_skus)}"
        )

    return {
        "ok": not errors,
        "errors": errors,
        "window_start": start,
        "window_end": end,
        "total_rows": total_rows,
        "formula_rows": formula_rows,
        "unresolved_rows": unresolved_rows,
        "unresolved_skus": unresolved_skus,
        "unit_cogs_evidence_source_csv": (
            str(unit_cogs_evidence_csv.expanduser().resolve())
            if unit_cogs_evidence_csv is not None
            else None
        ),
        "unit_cogs_evidence_applied_rows": unit_cogs_evidence_applied_rows,
        "unit_cogs_evidence_applied_skus": unit_cogs_evidence_applied_skus,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate published COGS integrity")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument("--as-of", type=str, default=None)
    parser.add_argument("--days", type=int, default=30)
    parser.add_argument("--max-unresolved-rows", type=int, default=0)
    parser.add_argument("--max-unresolved-skus", type=int, default=0)
    parser.add_argument(
        "--unit-cogs-evidence-csv",
        type=Path,
        default=None,
        help=(
            "Copied-temp-only unit COGS evidence CSV. This overlays validation "
            "calculation only; it does not write production economics."
        ),
    )
    args = parser.parse_args()

    report = validate_cogs_integrity(
        db_path=args.db,
        as_of=args.as_of,
        days=args.days,
        max_unresolved_rows=args.max_unresolved_rows,
        max_unresolved_skus=args.max_unresolved_skus,
        unit_cogs_evidence_csv=args.unit_cogs_evidence_csv,
    )
    print(
        "COGS integrity window="
        f"{report['window_start']}..{report['window_end']} "
        f"total_rows={report['total_rows']} "
        f"formula_rows={report['formula_rows']} "
        f"unresolved_rows={report['unresolved_rows']} "
        f"unresolved_skus={report['unresolved_skus']} "
        f"unit_cogs_evidence_applied_rows={report['unit_cogs_evidence_applied_rows']}"
    )
    if report["errors"]:
        for err in report["errors"]:
            print(f"ERROR: {err}")
        return 1
    print("OK: COGS integrity passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
