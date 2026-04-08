#!/usr/bin/env python3
"""
Post-import health report (API vs CRM vs DB) in ASCII table.
"""

import argparse
import csv
import json
import logging
import re
import sys
from collections import defaultdict
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo
from pathlib import Path
from typing import Any, Optional

import pandas as pd
from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.db import DEFAULT_DB_PATH, get_db  # noqa: E402
from core.paths import data_path, get_data_root  # noqa: E402
from core.integrations.kaspi_api_client import (  # noqa: E402
    KaspiAPIClient,
    KaspiAuthError,
    STORE_TOKEN_MAP,
)
from core.integrations.kaspi_order_stage import StageCode, api_state_filter_for_stage  # noqa: E402
from core.integrations.kaspi_order_stage import classify_kaspi_stage_from_db_row, classify_kaspi_order_stage  # noqa: E402
from core.utils.kaspi_dates import parse_kaspi_date, planned_date_from_order  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

# Kaspi dates are in Asia/Almaty timezone
ALMATY_TZ = ZoneInfo("Asia/Almaty")

DEFAULT_CRM_PATH = data_path("excel_ui", "SALES_KSP_CRM_V3.xlsx")
DEFAULT_SHEET_NAME = "SALES_KSP_CRM_1"

STORE_MAP = {
    "30137883_PP1": "AcmeWear",
    "30000001_PP1": "Universal",
    "30290083_PP1": "11KZ",
    "30000002_PP1": "STORE-B",
    "30362323_PP1": "Store-C",
}

API_TO_DISPLAY = {
    "ACMEWEAR": "AcmeWear",
    "UNIVERSAL": "Universal",
    "11KZ": "11KZ",
    "STOREB": "STORE-B",
    "MELVIS": "Store-C",
}

PENDING_STAGES = {
    StageCode.ACCEPTED_PENDING_ASSEMBLY,
    StageCode.ASSEMBLED_PENDING_HANDOVER,
}


def _coerce_str(value: Any) -> str:
    if value is None or pd.isna(value):
        return ""
    return str(value).strip()


def normalize_store_name(value: Any) -> str:
    if pd.isna(value) or not value:
        return "UNKNOWN"
    store_str = str(value).strip()
    if store_str in STORE_MAP:
        return STORE_MAP[store_str]
    if store_str.upper() in API_TO_DISPLAY:
        return API_TO_DISPLAY[store_str.upper()]
    if store_str in API_TO_DISPLAY.values():
        return store_str
    for code, name in STORE_MAP.items():
        if code.lower() == store_str.lower() or name.lower() == store_str.lower():
            return name
    return store_str


def parse_date(value: Any) -> Optional[date]:
    return parse_kaspi_date(value)


def _planned_date_from_order(order: dict, store_code: Optional[str] = None) -> Optional[date]:
    return planned_date_from_order(order, store_code=store_code)


def _db_row_planned_date(row: Any) -> Optional[date]:
    if not hasattr(row, "get"):
        row = dict(row)
    return parse_date(row.get("courier_transmission_planning_date")) or parse_date(
        row.get("planned_shipment_date")
    )


def get_api_orders_by_store(
    target_date: date,
    since_days: int = 7,
    store_filter: Optional[str] = None,
    verbose: bool = False,
) -> tuple[dict[str, set[str]], set[str]]:
    orders_by_store: dict[str, set[str]] = {}
    error_stores: set[str] = set()

    stores = list(STORE_TOKEN_MAP.keys())
    if store_filter:
        sf = store_filter.upper()
        if sf in STORE_TOKEN_MAP:
            stores = [sf]

    since = (datetime.now(ALMATY_TZ) - timedelta(days=since_days)).strftime("%Y-%m-%d")

    for store_code in stores:
        try:
            client = KaspiAPIClient(store_code=store_code)
            orders = client.list_all_orders(
                state=api_state_filter_for_stage(StageCode.ACCEPTED_PENDING_ASSEMBLY),
                since=since,
                include_orders="user",
            )
        except KaspiAuthError as exc:
            logger.warning(f"{store_code}: Auth error - {exc}")
            error_stores.add(store_code)
            continue
        except Exception as exc:
            logger.warning(f"{store_code}: API error - {exc}")
            error_stores.add(store_code)
            continue

        if verbose:
            logger.info(f"{store_code}: API returned {len(orders)} orders")

        ids = set()
        min_date = target_date - timedelta(days=max(int(since_days), 0))
        for order in orders:
            planned = _planned_date_from_order(order, store_code=store_code)
            stage = classify_kaspi_order_stage(order)
            if stage in PENDING_STAGES and planned and min_date <= planned <= target_date:
                code = order.get("attributes", {}).get("code", "")
                if code:
                    ids.add(code)

        if ids:
            orders_by_store[store_code] = ids
        if verbose:
            logger.info(f"{store_code}: {len(ids)} orders for {target_date}")

    return orders_by_store, error_stores


def get_crm_orders(
    crm_path: Path,
    sheet_name: str,
    target_date: date,
) -> tuple[dict[str, set[str]], dict[str, set[str]]]:
    if not crm_path.exists():
        return {}, {}
    df = pd.read_excel(crm_path, sheet_name=sheet_name)
    crm_all: dict[str, set[str]] = defaultdict(set)
    crm_size: dict[str, set[str]] = defaultdict(set)

    for _, row in df.iterrows():
        order_id = row.get("OrderID")
        if pd.isna(order_id):
            order_id = row.get("№ заказа")
        if pd.isna(order_id):
            continue
        order_id = str(order_id).strip()
        if order_id.endswith(".0"):
            order_id = order_id[:-2]
        if not order_id:
            continue

        row_date = parse_date(row.get("Date"))
        if row_date != target_date:
            continue

        store_name = row.get("STORE_NAME")
        if pd.isna(store_name):
            store_name = row.get("Склад передачи КД")
        store_name = normalize_store_name(store_name)

        crm_all[store_name].add(order_id)
        my_size = _coerce_str(row.get("MY_SIZE"))
        if my_size:
            crm_size[store_name].add(order_id)

    return dict(crm_all), dict(crm_size)


def get_db_orders(
    db_path: Path,
    target_date: date,
    since_days: int = 7,
) -> tuple[dict[str, set[str]], dict[str, set[str]]]:
    if not db_path.exists():
        return {}, {}
    with get_db(db_path) as conn:
        table = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='fact_orders_kaspi'"
        ).fetchone()
        if not table:
            return {}, {}

        cols = {
            row[1] for row in conn.execute("PRAGMA table_info(fact_orders_kaspi)").fetchall()
        }
        select_cols = [
            col
            for col in (
                "order_id",
                "store_code",
                "assigned_size",
                "my_size",
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
            )
            if col in cols
        ]
        rows = conn.execute(
            f"""
            SELECT {", ".join(select_cols)}
            FROM fact_orders_kaspi
            """
        ).fetchall()

    db_all: dict[str, set[str]] = defaultdict(set)
    db_size: dict[str, set[str]] = defaultdict(set)
    min_date = target_date - timedelta(days=max(int(since_days), 0))
    for row in rows:
        order_id = _coerce_str(row["order_id"])
        if order_id.endswith(".0"):
            order_id = order_id[:-2]
        if not order_id:
            continue

        planned_date = _db_row_planned_date(row)
        if not planned_date or not (min_date <= planned_date <= target_date):
            continue

        stage = classify_kaspi_stage_from_db_row(row)
        if stage not in PENDING_STAGES:
            continue

        store_name = normalize_store_name(row["store_code"])
        db_all[store_name].add(order_id)

        size = _coerce_str(row["assigned_size"]) or _coerce_str(row["my_size"])
        if size:
            db_size[store_name].add(order_id)

    return dict(db_all), dict(db_size)


def _crm_numeric(value: Any) -> float:
    if value is None or pd.isna(value):
        return 0.0
    text = str(value).strip().replace(",", ".")
    if not text:
        return 0.0
    try:
        return float(text)
    except (TypeError, ValueError):
        return 0.0


def _load_db_seller_fee_truth(db_path: Path, order_ids: set[str]) -> dict[str, float]:
    if not db_path.exists() or not order_ids:
        return {}

    with get_db(db_path) as conn:
        table = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='fact_orders_kaspi'"
        ).fetchone()
        if not table:
            return {}

        cols = {
            row[1] for row in conn.execute("PRAGMA table_info(fact_orders_kaspi)").fetchall()
        }
        if "order_id" not in cols or "delivery_cost_for_seller" not in cols:
            return {}

        out: dict[str, float] = {}
        ordered_ids = sorted(order_ids)
        for i in range(0, len(ordered_ids), 900):
            chunk = ordered_ids[i : i + 900]
            placeholders = ",".join("?" for _ in chunk)
            rows = conn.execute(
                f"""
                SELECT order_id, delivery_cost_for_seller
                FROM fact_orders_kaspi
                WHERE order_id IN ({placeholders})
                """,
                chunk,
            ).fetchall()
            for row in rows:
                order_id = _coerce_str(row["order_id"])
                fee = _crm_numeric(row["delivery_cost_for_seller"])
                if order_id and fee != 0.0:
                    out[order_id] = fee
        return out


def get_crm_seller_fee_coverage(
    crm_path: Path,
    sheet_name: str,
    target_date: date,
    db_path: Path,
) -> dict[str, dict[str, int]]:
    if not crm_path.exists():
        return {}

    df = pd.read_excel(crm_path, sheet_name=sheet_name)
    if df.empty:
        return {}

    order_col = "OrderID" if "OrderID" in df.columns else ("№ заказа" if "№ заказа" in df.columns else None)
    date_col = "Date" if "Date" in df.columns else None
    if order_col is None or date_col is None:
        return {}

    store_col = "STORE_NAME" if "STORE_NAME" in df.columns else ("Склад передачи КД" if "Склад передачи КД" in df.columns else None)
    seller_fee_col = "Стоимость доставки для продавца" if "Стоимость доставки для продавца" in df.columns else None
    raw_delivery_col = "Delivery_fee_kzt" if "Delivery_fee_kzt" in df.columns else ("Delivery_fee" if "Delivery_fee" in df.columns else None)
    if seller_fee_col is None:
        return {}

    row_dates = df[date_col].apply(parse_date)
    today_df = df.loc[row_dates == target_date].copy()
    if today_df.empty:
        return {}

    normalized_order_ids = set()
    order_values: list[str] = []
    for value in today_df[order_col].tolist():
        order_id = _coerce_str(value)
        if order_id.endswith(".0"):
            order_id = order_id[:-2]
        order_values.append(order_id)
        if order_id:
            normalized_order_ids.add(order_id)

    db_truth = _load_db_seller_fee_truth(db_path, normalized_order_ids)
    totals: dict[str, dict[str, int]] = defaultdict(
        lambda: {
            "seller_fee_expected": 0,
            "seller_fee_filled": 0,
            "miss_seller_fee": 0,
        }
    )

    for idx, (_, row) in enumerate(today_df.iterrows()):
        order_id = order_values[idx]
        store_name = normalize_store_name(row.get(store_col) if store_col else None)
        db_fee = _crm_numeric(db_truth.get(order_id))
        raw_fee = _crm_numeric(row.get(raw_delivery_col)) if raw_delivery_col else 0.0
        seller_fee = _crm_numeric(row.get(seller_fee_col))
        expected = db_fee != 0.0 or raw_fee != 0.0
        if not expected:
            continue
        totals[store_name]["seller_fee_expected"] += 1
        if seller_fee != 0.0:
            totals[store_name]["seller_fee_filled"] += 1
        else:
            totals[store_name]["miss_seller_fee"] += 1

    return dict(totals)


def format_table(headers: list[str], rows: list[list[str]]) -> str:
    widths = [len(h) for h in headers]
    for row in rows:
        for i, cell in enumerate(row):
            widths[i] = max(widths[i], len(cell))

    def fmt_row(r: list[str]) -> str:
        return "| " + " | ".join(cell.ljust(widths[i]) for i, cell in enumerate(r)) + " |"

    sep = "+-" + "-+-".join("-" * w for w in widths) + "-+"
    out = [sep, fmt_row(headers), sep]
    out.extend(fmt_row(r) for r in rows)
    out.append(sep)
    return "\n".join(out)


def main() -> int:
    parser = argparse.ArgumentParser(description="Post-import API/CRM/DB health report")
    parser.add_argument("--date", help="Target date (YYYY-MM-DD, default: today)")
    parser.add_argument("--crm-file", type=Path, default=DEFAULT_CRM_PATH)
    parser.add_argument("--db-path", type=Path, default=None)
    parser.add_argument("--sheet", default=DEFAULT_SHEET_NAME)
    parser.add_argument("--since-days", type=int, default=7)
    parser.add_argument("--store", help="Filter by store (ACMEWEAR/UNIVERSAL/11KZ/STOREB)")
    parser.add_argument("--json-out", type=Path, default=None, help="Write machine-readable JSON summary to path")
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()

    load_dotenv(PROJECT_ROOT / ".env")

    if args.date:
        target_date = datetime.strptime(args.date, "%Y-%m-%d").date()
    else:
        target_date = datetime.now(ALMATY_TZ).date()

    print("\n" + "=" * 80)
    print("POST-IMPORT HEALTH REPORT")
    print("=" * 80)
    print(f"Data root: {get_data_root()}")
    print(f"Target date: {target_date}")
    print(f"CRM: {args.crm_file}")
    db_path = args.db_path or data_path("db", "app.db")
    print(f"DB: {db_path}")
    print()

    api_by_store, api_errors = get_api_orders_by_store(
        target_date, since_days=args.since_days, store_filter=args.store, verbose=args.verbose
    )
    crm_all, crm_size = get_crm_orders(args.crm_file, args.sheet, target_date)
    db_all, db_size = get_db_orders(db_path, target_date, since_days=args.since_days)

    all_stores = set()
    for store_code in api_by_store:
        all_stores.add(API_TO_DISPLAY.get(store_code, store_code))
    for store_code in api_errors:
        all_stores.add(API_TO_DISPLAY.get(store_code, store_code))
    all_stores.update(crm_all.keys())
    all_stores.update(db_all.keys())

    seller_fee_coverage = get_crm_seller_fee_coverage(args.crm_file, args.sheet, target_date, db_path)

    headers = [
        "STORE", "API_TODAY", "CRM_TODAY", "DB_TODAY", "CRM_SIZE", "DB_SIZE",
        "MISS_CRM", "STALE_CRM", "MISS_SIZE", "SELLER_FEE_EXPECTED", "SELLER_FEE_FILLED", "MISS_SELLER_FEE",
    ]
    rows = []
    store_rows_list: list[dict[str, Any]] = []
    store_rows: dict[str, dict[str, Any]] = {}
    totals = defaultdict(int)

    for store in sorted(all_stores):
        api_store_code = None
        for code, disp in API_TO_DISPLAY.items():
            if disp == store:
                api_store_code = code
                break
        api_ids = api_by_store.get(api_store_code, set()) if api_store_code else set()
        api_failed = api_store_code in api_errors if api_store_code else False

        crm_ids = crm_all.get(store, set())
        db_ids = db_all.get(store, set())
        crm_size_ids = crm_size.get(store, set())
        db_size_ids = db_size.get(store, set())
        seller_fee_stats = seller_fee_coverage.get(
            store,
            {
                "seller_fee_expected": 0,
                "seller_fee_filled": 0,
                "miss_seller_fee": 0,
            },
        )

        miss_crm = len(api_ids - crm_ids)
        stale_crm = len(crm_ids - api_ids)
        size_ok = crm_size_ids | db_size_ids
        miss_size = len(api_ids - size_ok)

        if api_failed:
            row = [store, "ERR", "-", "-", "-", "-", "-", "-", "-", "-", "-", "-"]
            store_payload = {
                "store": store,
                "api_error": True,
                "api_today": None,
                "crm_today": None,
                "db_today": None,
                "crm_size": None,
                "db_size": None,
                "miss_crm": None,
                "stale_crm": None,
                "miss_size": None,
                "seller_fee_expected": int(seller_fee_stats["seller_fee_expected"]),
                "seller_fee_filled": int(seller_fee_stats["seller_fee_filled"]),
                "miss_seller_fee": int(seller_fee_stats["miss_seller_fee"]),
            }
        else:
            row = [
                store,
                str(len(api_ids)),
                str(len(crm_ids)),
                str(len(db_ids)),
                str(len(crm_size_ids)),
                str(len(db_size_ids)),
                str(miss_crm),
                str(stale_crm),
                str(miss_size),
                str(int(seller_fee_stats["seller_fee_expected"])),
                str(int(seller_fee_stats["seller_fee_filled"])),
                str(int(seller_fee_stats["miss_seller_fee"])),
            ]
            totals["API"] += len(api_ids)
            totals["CRM"] += len(crm_ids)
            totals["DB"] += len(db_ids)
            totals["CRM_SIZE"] += len(crm_size_ids)
            totals["DB_SIZE"] += len(db_size_ids)
            totals["MISS_CRM"] += miss_crm
            totals["STALE_CRM"] += stale_crm
            totals["MISS_SIZE"] += miss_size
            totals["SELLER_FEE_EXPECTED"] += int(seller_fee_stats["seller_fee_expected"])
            totals["SELLER_FEE_FILLED"] += int(seller_fee_stats["seller_fee_filled"])
            totals["MISS_SELLER_FEE"] += int(seller_fee_stats["miss_seller_fee"])
            store_payload = {
                "store": store,
                "api_error": False,
                "api_today": len(api_ids),
                "crm_today": len(crm_ids),
                "db_today": len(db_ids),
                "crm_size": len(crm_size_ids),
                "db_size": len(db_size_ids),
                "miss_crm": miss_crm,
                "stale_crm": stale_crm,
                "miss_size": miss_size,
                "seller_fee_expected": int(seller_fee_stats["seller_fee_expected"]),
                "seller_fee_filled": int(seller_fee_stats["seller_fee_filled"]),
                "miss_seller_fee": int(seller_fee_stats["miss_seller_fee"]),
            }

        rows.append(row)
        store_rows[store] = store_payload
        store_rows_list.append(store_payload)

    if api_errors:
        totals_row = ["TOTAL", "PARTIAL", "PARTIAL", "PARTIAL", "PARTIAL", "PARTIAL", "PARTIAL", "PARTIAL", "PARTIAL", "PARTIAL", "PARTIAL", "PARTIAL"]
    else:
        totals_row = [
            "TOTAL",
            str(totals["API"]),
            str(totals["CRM"]),
            str(totals["DB"]),
            str(totals["CRM_SIZE"]),
            str(totals["DB_SIZE"]),
            str(totals["MISS_CRM"]),
            str(totals["STALE_CRM"]),
            str(totals["MISS_SIZE"]),
            str(totals["SELLER_FEE_EXPECTED"]),
            str(totals["SELLER_FEE_FILLED"]),
            str(totals["MISS_SELLER_FEE"]),
        ]
    rows.append(totals_row)

    print(format_table(headers, rows))

    report_payload = {
        "target_date": target_date.isoformat(),
        "partial_api": bool(api_errors),
        "api_error_stores": sorted(API_TO_DISPLAY.get(code, code) for code in api_errors),
        "totals": {
            "api_today": int(totals["API"]),
            "crm_today": int(totals["CRM"]),
            "db_today": int(totals["DB"]),
            "crm_size": int(totals["CRM_SIZE"]),
            "db_size": int(totals["DB_SIZE"]),
            "miss_crm": int(totals["MISS_CRM"]),
            "stale_crm": int(totals["STALE_CRM"]),
            "miss_size": int(totals["MISS_SIZE"]),
            "seller_fee_expected": int(totals["SELLER_FEE_EXPECTED"]),
            "seller_fee_filled": int(totals["SELLER_FEE_FILLED"]),
            "miss_seller_fee": int(totals["MISS_SELLER_FEE"]),
        },
        "stores": store_rows,
        "store_rows": store_rows_list,
    }
    if args.json_out:
        args.json_out.parent.mkdir(parents=True, exist_ok=True)
        args.json_out.write_text(
            json.dumps(report_payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        if args.verbose:
            print(f"JSON summary written: {args.json_out}")

    # Missing samples (only if API ok)
    if api_errors:
        print("WARNING: API selection failed for stores: " + ", ".join(sorted(api_errors)))
        print("         Counts marked PARTIAL/ERR exclude failed stores.")
        return 0

    api_all = set().union(*api_by_store.values()) if api_by_store else set()
    crm_all_ids = set().union(*crm_all.values()) if crm_all else set()
    size_ok_ids = set().union(*crm_size.values()) if crm_size else set()
    size_ok_ids |= set().union(*db_size.values()) if db_size else set()

    def show_missing(title: str, ids: set[str]) -> None:
        if not ids:
            return
        sample = sorted(list(ids))[:5]
        print(f"{title} (first 5): {', '.join(sample)}")

    show_missing("Missing in CRM", api_all - crm_all_ids)
    show_missing("Stale in CRM today", crm_all_ids - api_all)
    show_missing("Missing size (DB+CRM)", api_all - size_ok_ids)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
