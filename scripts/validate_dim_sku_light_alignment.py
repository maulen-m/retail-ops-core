#!/usr/bin/env python3
"""Validate dim_sku weight alignment against the live DIM_SKU_light_v7 workbook surface."""

from __future__ import annotations

import argparse
from pathlib import Path
import sqlite3
import sys
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from core.excel.dim_sku_light_parser import parse_dim_sku_light


DEFAULT_DB = PROJECT_ROOT / "db" / "app.db"
DEFAULT_WORKBOOK = Path(
    "~/Documents/useful tables/Main crm spreadsheets/main tables/"
    "Purchase_orders/vibe_code_PO/Inbound_calendar_V10.002.xlsx"
)
DEFAULT_SHEET = "DIM_SKU_light_v7"


def validate_dim_sku_light_alignment(
    *,
    db_path: Path,
    workbook_path: Path = DEFAULT_WORKBOOK,
    sheet_name: str = DEFAULT_SHEET,
    weight_tol_kg: float = 0.01,
    base_tol_cny: float = 0.01,
    enforce_base_cost: bool = False,
) -> dict[str, Any]:
    workbook_rows, parse_diag = parse_dim_sku_light(
        workbook_path,
        sheet_name=sheet_name,
    )
    if not workbook_rows:
        return {
            "ok": False,
            "errors": ["workbook parser returned no valid rows"],
            "warnings": [],
            "error_count": 1,
            "warning_count": 0,
            "compared_count": 0,
            "weight_mismatch_count": 0,
            "base_mismatch_count": 0,
            "weight_mismatches": [],
            "base_mismatches": [],
            "parser_diagnostics": parse_diag,
        }

    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    try:
        db_rows = conn.execute(
            """
            SELECT sku_key, base_cost_cny, weight_kg, COALESCE(active_flag, 1) AS active_flag
            FROM dim_sku
            """
        ).fetchall()
    finally:
        conn.close()

    errors: list[str] = []
    warnings: list[str] = []
    compared_count = 0
    weight_mismatches: list[dict[str, Any]] = []
    base_mismatches: list[dict[str, Any]] = []

    for row in db_rows:
        if int(row["active_flag"] or 0) != 1:
            continue
        sku_key = str(row["sku_key"] or "").strip()
        if not sku_key or sku_key not in workbook_rows:
            continue

        compared_count += 1
        ref = workbook_rows[sku_key]
        db_weight = float(row["weight_kg"] or 0.0)
        db_base = float(row["base_cost_cny"] or 0.0)
        ref_weight = float(ref["weight_kg"])
        ref_base = float(ref["base_cost_cny"])

        if abs(db_weight - ref_weight) > float(weight_tol_kg):
            weight_mismatches.append(
                {
                    "sku_key": sku_key,
                    "db_weight_kg": db_weight,
                    "workbook_weight_kg": ref_weight,
                    "source_row_index": ref["source_row_index"],
                }
            )
        if abs(db_base - ref_base) > float(base_tol_cny):
            base_mismatches.append(
                {
                    "sku_key": sku_key,
                    "db_base_cost_cny": db_base,
                    "workbook_base_cost_cny": ref_base,
                    "source_row_index": ref["source_row_index"],
                }
            )

    if compared_count == 0:
        errors.append("no overlapping active SKUs between dim_sku and dim_sku_light workbook")
    if weight_mismatches:
        errors.append(f"weight mismatches against dim_sku_light workbook: {len(weight_mismatches)}")
    if base_mismatches:
        message = f"base-cost reference drift against dim_sku_light workbook: {len(base_mismatches)}"
        if enforce_base_cost:
            errors.append(message)
        else:
            warnings.append(message)

    return {
        "ok": not errors,
        "errors": errors,
        "warnings": warnings,
        "error_count": len(errors),
        "warning_count": len(warnings),
        "compared_count": compared_count,
        "weight_mismatch_count": len(weight_mismatches),
        "base_mismatch_count": len(base_mismatches),
        "weight_mismatches": weight_mismatches,
        "base_mismatches": base_mismatches,
        "parser_diagnostics": parse_diag,
        "workbook_path": str(workbook_path),
        "sheet_name": sheet_name,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate dim_sku alignment vs Dim sku light workbook")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument("--xlsx", type=Path, default=DEFAULT_WORKBOOK)
    parser.add_argument("--sheet", type=str, default=DEFAULT_SHEET)
    parser.add_argument("--weight-tol-kg", type=float, default=0.01)
    parser.add_argument("--base-tol-cny", type=float, default=0.01)
    parser.add_argument("--enforce-base-cost", action="store_true")
    args = parser.parse_args()

    report = validate_dim_sku_light_alignment(
        db_path=args.db,
        workbook_path=args.xlsx,
        sheet_name=args.sheet,
        weight_tol_kg=args.weight_tol_kg,
        base_tol_cny=args.base_tol_cny,
        enforce_base_cost=args.enforce_base_cost,
    )
    print(
        "dim_sku_light_alignment:",
        f"compared={report['compared_count']}",
        f"weight_mismatches={report['weight_mismatch_count']}",
        f"base_mismatches={report['base_mismatch_count']}",
    )
    for warn in report["warnings"]:
        print(f"WARN: {warn}")
    if report["errors"]:
        for err in report["errors"]:
            print(f"ERROR: {err}")
        return 1
    print("OK: dim_sku light alignment passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
