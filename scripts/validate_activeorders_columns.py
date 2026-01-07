#!/usr/bin/env python3
"""
Validate ActiveOrders.xlsx columns against kaspi_export_parser requirements.

Prints a warning and exits non-zero if required columns are missing.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from core.parsers.kaspi_export_parser import load_column_config, _get_column_name


REQUIRED_FIELDS = [
    "order_id",
    "status",
    "planned_date",
    "product_name",
    "article",
    "price",
    "store",
]


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate ActiveOrders columns")
    parser.add_argument("file", type=Path, help="Path to ActiveOrders.xlsx")
    args = parser.parse_args()

    path = args.file
    if not path.exists():
        print(f"ActiveOrders file not found: {path}")
        return 1

    try:
        df = pd.read_excel(path, nrows=1)
    except Exception as exc:
        print(f"Failed to read ActiveOrders header: {exc}")
        return 1

    config = load_column_config()
    missing = []
    for field in REQUIRED_FIELDS:
        if not _get_column_name(config, field, list(df.columns)):
            missing.append(field)

    if missing:
        expected = [config.get("kaspi_export_columns", {}).get(f, f) for f in missing]
        print("WARNING: ActiveOrders columns mismatch.")
        print(f"Missing required columns: {expected}")
        print(f"Available columns: {list(df.columns)}")
        return 2

    print("ActiveOrders columns OK.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
