#!/usr/bin/env python3
"""Validate dim_sku base/weight alignment against master workbook."""

from __future__ import annotations

import argparse
from pathlib import Path
import sqlite3
from typing import Any

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DB = PROJECT_ROOT / "db" / "app.db"
DEFAULT_WORKBOOK = PROJECT_ROOT / "excel" / "Inventory_Core_V18.1_V2.xlsx"
DEFAULT_SHEET = "Dim_SKU"


def _norm_header(value: Any) -> str:
    text = str(value or "").strip().lower()
    for ch in (" ", "_", "-", "/", "\\", "\t", "\n", "\r"):
        text = text.replace(ch, "")
    return text


def _find_column(columns: list[str], aliases: list[str]) -> str | None:
    normalized = {_norm_header(col): col for col in columns}
    for alias in aliases:
        key = _norm_header(alias)
        if key in normalized:
            return normalized[key]
    return None


def _is_truthy(value: Any) -> bool:
    if value is None:
        return False
    text = str(value).strip().lower()
    if text in {"", "none", "nan"}:
        return False
    return text in {"1", "true", "yes", "y", "active"}


def _to_float(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip().replace("\u00a0", "").replace(" ", "")
    if not text:
        return None
    if text.count(",") == 1 and text.count(".") == 0:
        text = text.replace(",", ".")
    try:
        return float(text)
    except ValueError:
        return None


def _load_master_dim(
    *,
    workbook_path: Path,
    sheet_name: str,
) -> dict[str, dict[str, float]]:
    if not workbook_path.exists():
        raise FileNotFoundError(f"Master workbook not found: {workbook_path}")

    df = pd.read_excel(workbook_path, sheet_name=sheet_name, dtype=object)
    if df.empty:
        return {}

    sku_col = _find_column(df.columns.tolist(), ["SKU_key", "sku_key", "SKU"])
    base_col = _find_column(df.columns.tolist(), ["BaseCost_CNY", "base_cost_cny", "CNY"])
    weight_col = _find_column(df.columns.tolist(), ["Weight_kg", "weight_kg", "Weight"])
    active_col = _find_column(df.columns.tolist(), ["Is_Active", "active_flag", "Active"])
    if not sku_col or not base_col or not weight_col:
        missing = [
            name
            for name, col in (("SKU_key", sku_col), ("BaseCost_CNY", base_col), ("Weight_kg", weight_col))
            if not col
        ]
        raise RuntimeError(f"Missing required master columns: {', '.join(missing)}")

    out: dict[str, dict[str, float]] = {}
    for _, row in df.iterrows():
        sku = str(row.get(sku_col) or "").strip()
        if not sku:
            continue
        if active_col and not _is_truthy(row.get(active_col)):
            continue
        base = _to_float(row.get(base_col))
        weight = _to_float(row.get(weight_col))
        if base is None or weight is None:
            continue
        out[sku] = {"base_cost_cny": float(base), "weight_kg": float(weight)}
    return out


def validate_dim_sku_master_alignment(
    *,
    db_path: Path,
    workbook_path: Path = DEFAULT_WORKBOOK,
    sheet_name: str = DEFAULT_SHEET,
    weight_tol_kg: float = 0.01,
    base_tol_cny: float = 0.01,
) -> dict[str, Any]:
    master_rows = _load_master_dim(workbook_path=workbook_path, sheet_name=sheet_name)
    errors: list[str] = []
    mismatches: list[dict[str, Any]] = []

    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    try:
        db_rows = conn.execute(
            """
            SELECT
                sku_key,
                base_cost_cny,
                weight_kg,
                COALESCE(active_flag, 1) AS active_flag
            FROM dim_sku
            """
        ).fetchall()
    finally:
        conn.close()

    if not master_rows:
        errors.append("master workbook has no active parsable rows")
        return {
            "ok": False,
            "errors": errors,
            "mismatch_count": 0,
            "compared_count": 0,
            "mismatches": [],
        }

    compared = 0
    for row in db_rows:
        if int(row["active_flag"] or 0) != 1:
            continue
        sku = str(row["sku_key"] or "").strip()
        if not sku or sku not in master_rows:
            continue
        compared += 1
        db_base = _to_float(row["base_cost_cny"])
        db_weight = _to_float(row["weight_kg"])
        ms = master_rows[sku]
        if db_base is None or db_weight is None:
            mismatches.append(
                {
                    "sku_key": sku,
                    "reason": "missing_db_value",
                    "db_base_cost_cny": db_base,
                    "db_weight_kg": db_weight,
                    "master_base_cost_cny": ms["base_cost_cny"],
                    "master_weight_kg": ms["weight_kg"],
                }
            )
            continue
        if (
            abs(float(db_base) - float(ms["base_cost_cny"])) > float(base_tol_cny)
            or abs(float(db_weight) - float(ms["weight_kg"])) > float(weight_tol_kg)
        ):
            mismatches.append(
                {
                    "sku_key": sku,
                    "reason": "value_mismatch",
                    "db_base_cost_cny": float(db_base),
                    "db_weight_kg": float(db_weight),
                    "master_base_cost_cny": float(ms["base_cost_cny"]),
                    "master_weight_kg": float(ms["weight_kg"]),
                }
            )

    if mismatches:
        errors.append(
            f"dim_sku mismatches against master workbook: {len(mismatches)}"
        )
    if compared == 0:
        errors.append("no overlapping active SKUs between dim_sku and master workbook")

    return {
        "ok": not errors,
        "errors": errors,
        "mismatch_count": len(mismatches),
        "compared_count": compared,
        "mismatches": mismatches,
        "workbook_path": str(workbook_path),
        "sheet_name": sheet_name,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate dim_sku against master workbook")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument("--workbook", type=Path, default=DEFAULT_WORKBOOK)
    parser.add_argument("--sheet", type=str, default=DEFAULT_SHEET)
    parser.add_argument("--weight-tol-kg", type=float, default=0.01)
    parser.add_argument("--base-tol-cny", type=float, default=0.01)
    args = parser.parse_args()

    report = validate_dim_sku_master_alignment(
        db_path=args.db,
        workbook_path=args.workbook,
        sheet_name=args.sheet,
        weight_tol_kg=args.weight_tol_kg,
        base_tol_cny=args.base_tol_cny,
    )
    print(
        f"dim_sku/master compared={report['compared_count']} "
        f"mismatches={report['mismatch_count']}"
    )
    if report["errors"]:
        for err in report["errors"]:
            print(f"ERROR: {err}")
        return 1
    print("OK: dim_sku master alignment passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
