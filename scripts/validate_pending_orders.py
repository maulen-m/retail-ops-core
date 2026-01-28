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
from dateutil import parser as dtp

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from core.paths import data_path
from core.db import get_db, DEFAULT_DB_PATH


ALMATY_TZ = ZoneInfo("Asia/Almaty")

DEFAULT_CRM = data_path("excel_ui", "SALES_KSP_CRM_V3.xlsx")
DEFAULT_SHEET = "SALES_KSP_CRM_1"
DEFAULT_ACTIVE = data_path("excel_ui", "ActiveOrders", "ActiveOrders.xlsx")
ACCEPTED_BY_MERCHANT = "ACCEPTED_BY_MERCHANT"
READY_STATUS_RU = "Ожидает передачи курьеру"
READY_STATUS_EN = "Awaiting courier"
ACCEPTED_STATUS_RU = "Принят"
ACCEPTED_STATUS_EN = "Accepted"


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


def _is_accepted_by_merchant(value) -> bool:
    return str(value or "").strip().upper() == ACCEPTED_BY_MERCHANT


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


def _norm_status(value: str) -> str:
    s = str(value or "").strip().lower()
    s = s.replace("ё", "е")
    s = s.replace(" ", "")
    return s


def _parse_date(value) -> Optional[date]:
    if pd.isna(value):
        return None
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, (int, float)) and 40000 <= float(value) <= 60000:
        base = datetime(1899, 12, 30)
        return (base + timedelta(days=int(float(value)))).date()
    if isinstance(value, str):
        s = value.strip()
        if len(s) == 10 and s[4] == "-" and s[7] == "-":
            try:
                return datetime.strptime(s, "%Y-%m-%d").date()
            except ValueError:
                pass
    try:
        return dtp.parse(str(value).strip(), dayfirst=True).date()
    except Exception:
        return None


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

        if include_overdue:
            query = """
                SELECT order_id, kaspi_status, kaspi_status_detail, internal_status, signature_required, courier_transmission_date
                FROM fact_orders_kaspi
                WHERE planned_shipment_date <= ?
            """
            params = [target_date.isoformat()]
            if lookback_days is not None:
                min_date = (target_date - timedelta(days=lookback_days)).isoformat()
                query += " AND planned_shipment_date >= ?"
                params.append(min_date)
            rows = conn.execute(query, params).fetchall()
        else:
            rows = conn.execute(
                """
                SELECT order_id, kaspi_status, kaspi_status_detail, internal_status, signature_required, courier_transmission_date
                FROM fact_orders_kaspi
                WHERE planned_shipment_date = ?
                """,
                (target_date.isoformat(),),
            ).fetchall()

    total = len(rows)
    pending = set()

    terminal = {
        "cancelled",
        "cancelling",
        "completed",
        "returned",
        "returning",
        "archive",
        "отменен",
        "отменяется",
        "завершен",
        "возвращен",
        "возвращается",
    }
    for row in rows:
        order_id = _clean_order_id(row["order_id"])
        if not order_id:
            continue
        status_norm = _norm_status(row["kaspi_status"])
        internal_norm = _norm_status(row["internal_status"])
        status_detail = row["kaspi_status_detail"]
        if _is_signature_required(row["signature_required"]):
            continue
        courier_transmission_date = row["courier_transmission_date"]
        if courier_transmission_date:
            continue

        if status_norm in terminal or internal_norm in terminal:
            continue
        if _is_accepted_by_merchant(status_detail):
            pending.add(order_id)
            continue
        if (status_detail is None or str(status_detail).strip() == "") and _is_ready_status(row["internal_status"]):
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
