#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Validate pending orders consistency between CRM, DB, and ActiveOrders export.

Checks:
- CRM pending orders for target date (planned date == target date, status = "Ожидает передачи курьеру")
- DB pending orders for target date (fact_orders_kaspi)
- ActiveOrders export for target date (if file exists)

Optional:
- --include-overdue includes planned date <= target (bounded by --lookback-days if set)

Prints mismatches and exits with code:
  0 = OK / no mismatches found
  1 = missing required files or DB not available
  2 = mismatches found
"""

from __future__ import annotations

import argparse
import sys
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Optional, Set, Tuple
from zoneinfo import ZoneInfo

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from core.paths import data_path
from core.db import get_db, DEFAULT_DB_PATH
from core.utils.kaspi_dates import parse_kaspi_date
from core.integrations.kaspi_order_stage import (
    StageCode,
    classify_kaspi_stage_from_db_row,
)


ALMATY_TZ = ZoneInfo("Asia/Almaty")

DEFAULT_CRM = data_path("excel_ui", "SALES_KSP_CRM_V3.xlsx")
DEFAULT_SHEET = "SALES_KSP_CRM_1"
DEFAULT_ACTIVE = data_path("excel_ui", "ActiveOrders", "ActiveOrders.xlsx")
READY_STATUS_RU = "Ожидает передачи курьеру"
READY_STATUS_EN = "Awaiting courier"
ACCEPTED_STATUS_RU = "Принят"
ACCEPTED_STATUS_EN = "Accepted"

DB_STAGE_COLUMNS = [
    "order_id",
    "kaspi_status",
    "kaspi_status_detail",
    "signature_required",
    "pre_order",
    "waybill_url",
    "delivery_mode",
    "returned_to_warehouse",
    "courier_transmission_date",
    "actual_shipment_date",
    "courier_transmission_planning_date",
    "planned_shipment_date",
]


def _is_signature_required(value) -> bool:
    if value is None or pd.isna(value):
        return False
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(int(value))
    text = str(value).strip().lower()
    if text in {"true", "1", "yes", "да", "требуется", "required"}:
        return True
    if text in {"false", "0", "no", "нет", "не требуется", "not required"}:
        return False
    return False


def _is_ready_status(value) -> bool:
    text = str(value or "").strip()
    if not text:
        return False
    if text.upper() in {"READY", "NEW"}:
        return True
    return text in {
        READY_STATUS_RU,
        READY_STATUS_EN,
        ACCEPTED_STATUS_RU,
        ACCEPTED_STATUS_EN,
    }


def _parse_date(value) -> Optional[date]:
    if isinstance(value, (int, float)) and 40000 <= float(value) <= 60000:
        base = datetime(1899, 12, 30)
        return (base + timedelta(days=int(float(value)))).date()
    return parse_kaspi_date(value)


def _db_row_planned_date(row) -> Optional[date]:
    if not hasattr(row, "get"):
        row = dict(row)
    return _parse_date(row.get("courier_transmission_planning_date")) or _parse_date(
        row.get("planned_shipment_date")
    )


def _clean_order_id(value) -> Optional[str]:
    if pd.isna(value):
        return None
    if isinstance(value, float) and value.is_integer():
        value = int(value)
    s = str(value).strip()
    if s.endswith(".0"):
        s = s[:-2]
    return s if s.isdigit() else None


def _get_target_date(arg: Optional[str]) -> date:
    if not arg or arg.lower() == "today":
        return datetime.now(ALMATY_TZ).date()
    return dtp.parse(arg).date()


def read_crm_pending(
    crm_path: Path,
    sheet: str,
    target_date: date,
    include_overdue: bool = False,
    lookback_days: Optional[int] = None,
) -> Set[str]:
    df = pd.read_excel(crm_path, sheet_name=sheet)

    order_col = None
    for name in ("OrderID", "№ заказа"):
        if name in df.columns:
            order_col = name
            break

    status_col = "Статус" if "Статус" in df.columns else None
    signature_col = None
    for name in ("Требуется подписание", "Signature Required"):
        if name in df.columns:
            signature_col = name
            break
    planned_col = None
    for name in ("PLANNED_SHIPPING_DATE", "Плановая дата передачи курьеру"):
        if name in df.columns:
            planned_col = name
            break

    if not order_col or not status_col or not planned_col:
        return set()

    pending = set()
    for _, row in df.iterrows():
        order_id = _clean_order_id(row.get(order_col))
        if not order_id:
            continue
        planned = _parse_date(row.get(planned_col))
        if not planned:
            continue
        if include_overdue:
            if planned > target_date:
                continue
            if lookback_days is not None:
                min_date = target_date - timedelta(days=lookback_days)
                if planned < min_date:
                    continue
        else:
            if planned != target_date:
                continue
        status = row.get(status_col)
        if not _is_ready_status(status):
            continue
        if signature_col and _is_signature_required(row.get(signature_col)):
            continue
        pending.add(order_id)

    return pending


def read_active_orders_pending(
    active_path: Path,
    target_date: date,
    include_overdue: bool = False,
    lookback_days: Optional[int] = None,
) -> Set[str]:
    if not active_path.exists():
        return set()
    df = pd.read_excel(active_path)
    if "№ заказа" not in df.columns or "Плановая дата передачи курьеру" not in df.columns:
        return set()
    status_col = "Статус" if "Статус" in df.columns else None
    signature_col = None
    for name in ("Требуется подписание", "Signature Required"):
        if name in df.columns:
            signature_col = name
            break
    pending = set()
    for _, row in df.iterrows():
        order_id = _clean_order_id(row.get("№ заказа"))
        if not order_id:
            continue
        if status_col and not _is_ready_status(row.get(status_col)):
            continue
        if signature_col and _is_signature_required(row.get(signature_col)):
            continue
        planned = _parse_date(row.get("Плановая дата передачи курьеру"))
        if not planned:
            continue
        if include_overdue:
            if planned > target_date:
                continue
            if lookback_days is not None:
                min_date = target_date - timedelta(days=lookback_days)
                if planned < min_date:
                    continue
        else:
            if planned != target_date:
                continue
        pending.add(order_id)
    return pending


def read_db_pending(
    db_path: Path,
    target_date: date,
    include_overdue: bool = False,
    lookback_days: Optional[int] = None,
) -> Tuple[int, Set[str]]:
    if not db_path.exists():
        return 0, set()

    with get_db(db_path) as conn:
        table = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='fact_orders_kaspi'"
        ).fetchone()
        if not table:
            return 0, set()

        cols = {
            row[1] for row in conn.execute("PRAGMA table_info(fact_orders_kaspi)").fetchall()
        }
        select_cols = [col for col in DB_STAGE_COLUMNS if col in cols]
        select_cols_sql = ",\n                    ".join(select_cols) if select_cols else "order_id"

        rows = conn.execute(
            f"""
            SELECT
                {select_cols_sql}
            FROM fact_orders_kaspi
            """
        ).fetchall()

    total = len(rows)
    pending = set()
    min_date = None
    if include_overdue and lookback_days is not None:
        min_date = target_date - timedelta(days=lookback_days)

    terminal = {
        StageCode.CANCELLED,
        StageCode.CANCELLING,
        StageCode.RETURNED,
        StageCode.RETURN_REQUESTED,
        StageCode.ISSUED_COMPLETED,
    }
    for row in rows:
        order_id = _clean_order_id(row["order_id"])
        if not order_id:
            continue
        planned_date = _db_row_planned_date(row)
        if not planned_date:
            continue
        if include_overdue:
            if planned_date > target_date:
                continue
            if min_date is not None and planned_date < min_date:
                continue
        else:
            if planned_date != target_date:
                continue
        stage = classify_kaspi_stage_from_db_row(row)
        if stage in terminal:
            continue
        if stage in {
            StageCode.ACCEPTED_PENDING_ASSEMBLY,
            StageCode.ASSEMBLED_PENDING_HANDOVER,
        }:
            pending.add(order_id)

    return total, pending


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate pending order alignment")
    parser.add_argument("--crm-file", type=Path, default=DEFAULT_CRM)
    parser.add_argument("--sheet", type=str, default=DEFAULT_SHEET)
    parser.add_argument("--db-path", type=Path, default=DEFAULT_DB_PATH)
    parser.add_argument("--active-orders", type=Path, default=DEFAULT_ACTIVE)
    parser.add_argument("--date", type=str, default="today")
    parser.add_argument("--include-overdue", action="store_true")
    parser.add_argument("--lookback-days", type=int, default=None)
    args = parser.parse_args()

    target_date = _get_target_date(args.date)

    if args.include_overdue:
        window = ""
        if args.lookback_days is not None:
            min_date = target_date - timedelta(days=args.lookback_days)
            window = f" (range {min_date.isoformat()} to {target_date.isoformat()})"
        print(f"Pending order validation for <= {target_date.isoformat()}{window}")
    else:
        print(f"Pending order validation for {target_date.isoformat()}")

    if not args.crm_file.exists():
        print(f"ERROR: CRM file not found: {args.crm_file}")
        return 1

    crm_pending = read_crm_pending(
        args.crm_file,
        args.sheet,
        target_date,
        include_overdue=args.include_overdue,
        lookback_days=args.lookback_days,
    )
    print(f"CRM pending orders: {len(crm_pending)}")

    db_total, db_pending = read_db_pending(
        args.db_path,
        target_date,
        include_overdue=args.include_overdue,
        lookback_days=args.lookback_days,
    )
    if db_total == 0:
        print("DB check skipped (no orders for date or table missing).")
    else:
        print(f"DB orders for date: {db_total} (pending={len(db_pending)})")

    active_pending = read_active_orders_pending(
        args.active_orders,
        target_date,
        include_overdue=args.include_overdue,
        lookback_days=args.lookback_days,
    )
    if active_pending:
        print(f"ActiveOrders pending: {len(active_pending)}")
    else:
        print("ActiveOrders check skipped (file missing or no orders).")

    mismatches = False

    db_missing_in_crm = []
    crm_missing_in_db = []
    active_missing_in_crm = []
    crm_missing_in_active = []

    if db_total > 0:
        db_missing_in_crm = sorted(db_pending - crm_pending)
        crm_missing_in_db = sorted(crm_pending - db_pending)
        if db_missing_in_crm:
            mismatches = True
            print(f"WARNING: {len(db_missing_in_crm)} orders in DB but not in CRM")
            print(f"  Sample: {db_missing_in_crm[:10]}")
        if crm_missing_in_db:
            mismatches = True
            print(f"WARNING: {len(crm_missing_in_db)} orders in CRM but not in DB")
            print(f"  Sample: {crm_missing_in_db[:10]}")

    if active_pending:
        active_missing_in_crm = sorted(active_pending - crm_pending)
        crm_missing_in_active = sorted(crm_pending - active_pending)
        if active_missing_in_crm:
            mismatches = True
            print(f"WARNING: {len(active_missing_in_crm)} orders in ActiveOrders but not in CRM")
            print(f"  Sample: {active_missing_in_crm[:10]}")
        if crm_missing_in_active:
            mismatches = True
            print(f"WARNING: {len(crm_missing_in_active)} orders in CRM but not in ActiveOrders")
            print(f"  Sample: {crm_missing_in_active[:10]}")

    db_pending_count = len(db_pending) if db_total > 0 else None
    active_pending_count = len(active_pending) if active_pending else None
    db_delta = None
    if db_pending_count is not None:
        db_delta = db_pending_count - len(crm_pending)
    active_delta = None
    if active_pending_count is not None:
        active_delta = active_pending_count - len(crm_pending)

    print("\nSummary:")
    print(f"  CRM pending: {len(crm_pending)}")
    print(f"  DB pending: {db_pending_count if db_pending_count is not None else 'n/a'}")
    print(f"  ActiveOrders pending: {active_pending_count if active_pending_count is not None else 'n/a'}")
    if db_delta is not None:
        print(f"  DB - CRM delta: {db_delta:+d}")
    if active_delta is not None:
        print(f"  ActiveOrders - CRM delta: {active_delta:+d}")

    if mismatches:
        print("Validation finished with mismatches.")
        return 2

    print("Validation OK (no mismatches detected).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
