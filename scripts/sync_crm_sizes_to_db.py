#!/usr/bin/env python3
"""
Sync manual sizes from CRM workbook into SQLite fact_orders_kaspi.

Writes:
  - assigned_size
  - size_source = CRM_MANUAL
  - size_confidence = HIGH
"""
from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Iterable, Optional

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from core.db import get_db, DEFAULT_DB_PATH
from core.paths import data_path

DEFAULT_CRM = data_path("excel_ui", "SALES_KSP_CRM_V3.xlsx")
DEFAULT_SHEET = "SALES_KSP_CRM_1"

REQUIRED_COLUMNS = {
    "order_id": {"OrderID", "№ заказа"},
    "my_size": {"MY_SIZE"},
    "planned_ship": {"PLANNED_SHIPPING_DATE", "Плановая дата передачи курьеру"},
}

SIZE_SOURCE = "CRM_MANUAL"
SIZE_CONFIDENCE = "HIGH"


@dataclass
class SyncStats:
    total_orders: int
    eligible_orders: int
    updated_orders: int
    skipped_orders: int
    missing_orders: int


def _normalize(value: str) -> str:
    return "".join(str(value).strip().lower().split())


def _select_column(df: pd.DataFrame, aliases: Iterable[str]) -> Optional[str]:
    normalized = {_normalize(c): c for c in df.columns}
    for alias in aliases:
        key = _normalize(alias)
        if key in normalized:
            return normalized[key]
    return None


def _coerce_id(value) -> str:
    if pd.isna(value):
        return ""
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value).strip()


def _coerce_size(value) -> str:
    if pd.isna(value):
        return ""
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value).strip()


def _parse_date(value) -> Optional[date]:
    if pd.isna(value):
        return None
    try:
        parsed = pd.to_datetime(value, errors="coerce", dayfirst=True)
    except Exception:
        return None
    if pd.isna(parsed):
        return None
    if isinstance(parsed, pd.Timestamp):
        return parsed.date()
    if isinstance(parsed, datetime):
        return parsed.date()
    return None


def _check_schema(conn) -> bool:
    table = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='fact_orders_kaspi'"
    ).fetchone()
    if not table:
        print("ERROR: Missing table fact_orders_kaspi in db/app.db.")
        print("Run: python3 scripts/migrate_011.py")
        return False

    cols = conn.execute("PRAGMA table_info(fact_orders_kaspi)").fetchall()
    col_names = {row[1] for row in cols}
    required = {"order_id", "assigned_size", "size_source", "size_confidence"}
    missing = sorted(required - col_names)
    if missing:
        print("ERROR: fact_orders_kaspi missing required columns:")
        print(f"  Missing: {', '.join(missing)}")
        print("Run: python3 scripts/migrate_012.py")
        return False
    return True


def sync_crm_sizes(
    db_path: Path,
    crm_path: Path,
    sheet_name: str,
    as_of: date,
    dry_run: bool,
) -> SyncStats:
    df = pd.read_excel(crm_path, sheet_name=sheet_name)

    order_col = _select_column(df, REQUIRED_COLUMNS["order_id"])
    size_col = _select_column(df, REQUIRED_COLUMNS["my_size"])
    date_col = _select_column(df, REQUIRED_COLUMNS["planned_ship"])

    missing_cols = []
    if not order_col:
        missing_cols.append("order_id")
    if not size_col:
        missing_cols.append("my_size")
    if not date_col:
        missing_cols.append("planned_ship")
    if missing_cols:
        raise ValueError(f"CRM missing required columns: {', '.join(missing_cols)}")

    working = df[[order_col, size_col, date_col]].copy()
    working[order_col] = working[order_col].apply(_coerce_id)
    working[size_col] = working[size_col].apply(_coerce_size)
    working = working[working[order_col] != ""]
    working = working.drop_duplicates(subset=[order_col], keep="last")

    total_orders = len(working)
    eligible_orders = 0
    updated_orders = 0
    skipped_orders = 0
    missing_orders = 0

    with get_db(db_path) as conn:
        if not _check_schema(conn):
            raise RuntimeError("Required schema missing.")

        for _, row in working.iterrows():
            order_id = row[order_col]
            size = row[size_col]
            planned_date = _parse_date(row[date_col])

            if not size or planned_date is None:
                skipped_orders += 1
                continue

            if planned_date > as_of:
                skipped_orders += 1
                continue

            eligible_orders += 1

            existing = conn.execute(
                """
                SELECT assigned_size, size_source, size_confidence
                FROM fact_orders_kaspi
                WHERE order_id = ?
                """,
                (order_id,),
            ).fetchall()

            if not existing:
                missing_orders += 1
                continue

            desired = (size, SIZE_SOURCE, SIZE_CONFIDENCE)
            if all(
                (
                    existing_row["assigned_size"],
                    existing_row["size_source"],
                    existing_row["size_confidence"],
                )
                == desired
                for existing_row in existing
            ):
                skipped_orders += 1
                continue

            if not dry_run:
                conn.execute(
                    """
                    UPDATE fact_orders_kaspi
                    SET assigned_size = ?, size_source = ?, size_confidence = ?
                    WHERE order_id = ?
                    """,
                    (size, SIZE_SOURCE, SIZE_CONFIDENCE, order_id),
                )

            updated_orders += 1

    return SyncStats(
        total_orders=total_orders,
        eligible_orders=eligible_orders,
        updated_orders=updated_orders,
        skipped_orders=skipped_orders,
        missing_orders=missing_orders,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Sync CRM sizes into SQLite")
    parser.add_argument("--crm-file", type=Path, default=DEFAULT_CRM)
    parser.add_argument("--sheet", type=str, default=DEFAULT_SHEET)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument(
        "--date",
        type=str,
        default=None,
        help="Only include orders planned on or before this date (YYYY-MM-DD).",
    )
    parser.add_argument(
        "--db-path",
        type=Path,
        default=DEFAULT_DB_PATH,
        help="Path to SQLite database (default: db/app.db).",
    )
    args = parser.parse_args()

    as_of = date.today()
    if args.date:
        as_of = datetime.strptime(args.date, "%Y-%m-%d").date()

    if not args.crm_file.exists():
        print(f"ERROR: CRM file not found: {args.crm_file}")
        return 1

    try:
        stats = sync_crm_sizes(
            db_path=args.db_path,
            crm_path=args.crm_file,
            sheet_name=args.sheet,
            as_of=as_of,
            dry_run=args.dry_run,
        )
    except Exception as exc:
        print(f"ERROR: {exc}")
        return 1

    print("Sync complete.")
    print(f"Total CRM orders: {stats.total_orders}")
    print(f"Eligible orders: {stats.eligible_orders}")
    print(f"Updated orders: {stats.updated_orders}")
    print(f"Skipped orders: {stats.skipped_orders}")
    print(f"Missing orders (not in DB): {stats.missing_orders}")
    if args.dry_run:
        print("Dry run: no DB writes performed.")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
