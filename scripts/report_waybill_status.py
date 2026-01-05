#!/usr/bin/env python3
"""
Report daily waybill health in a compact ASCII table.

Compares Kaspi API (planned date = target) vs CRM/DB/PDF/output.
"""

import argparse
import csv
import logging
import re
import sys
import tempfile
import zipfile
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

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

# Kaspi dates are in Asia/Almaty timezone
ALMATY_TZ = ZoneInfo("Asia/Almaty")

DEFAULT_CRM_PATH = data_path("excel_ui", "SALES_KSP_CRM_V3.xlsx")
DEFAULT_WAYBILL_DIR = data_path("excel_ui", "ActiveOrders")
DEFAULT_OUTPUT_DIR = data_path("excel_ui", "Kaspi_orders", "Today")
DEFAULT_SHEET_NAME = "SALES_KSP_CRM_1"

STORE_MAP = {
    "30137883_PP1": "AcmeWear",
    "30000001_PP1": "Universal",
    "30290083_PP1": "11KZ",
    "30000002_PP1": "STORE-B",
}

API_TO_DISPLAY = {
    "ACMEWEAR": "AcmeWear",
    "UNIVERSAL": "Universal",
    "11KZ": "11KZ",
    "STOREB": "STORE-B",
    "MELVIS": "Store-C",
}

WAYBILL_PATTERN = re.compile(r"KASPI_SHOP-(\d+)\.pdf", re.IGNORECASE)


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
    if store_str in API_TO_DISPLAY.values():
        return store_str
    for code, name in STORE_MAP.items():
        if code.lower() == store_str.lower() or name.lower() == store_str.lower():
            return name
    return store_str


def parse_date(value: Any) -> Optional[date]:
    if pd.isna(value) or value is None:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    value_str = str(value).strip()
    try:
        return datetime.strptime(value_str, "%d.%m.%Y").date()
    except ValueError:
        pass
    try:
        return datetime.strptime(value_str, "%Y-%m-%d").date()
    except ValueError:
        pass
    try:
        return pd.to_datetime(value, dayfirst=True).date()
    except (ValueError, TypeError):
        return None


def _timestamp_to_date(ts: Optional[int]) -> Optional[date]:
    if ts is None:
        return None
    try:
        return datetime.fromtimestamp(ts / 1000, tz=ALMATY_TZ).date()
    except (ValueError, OSError):
        return None


def _planned_date_from_order(order: dict) -> Optional[date]:
    delivery = order.get("attributes", {}).get("kaspiDelivery", {})
    planned_ts = delivery.get("courierTransmissionPlanningDate") or delivery.get("plannedDeliveryDate")
    return _timestamp_to_date(planned_ts)


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
            orders = client.list_all_orders(state="KASPI_DELIVERY", since=since)
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
        for order in orders:
            planned = _planned_date_from_order(order)
            if planned == target_date:
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
    """Return (crm_all, crm_with_size) per store for target date."""
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

        planned_date = parse_date(row.get("PLANNED_SHIPPING_DATE"))
        if not planned_date:
            planned_date = parse_date(row.get("Плановая дата передачи курьеру"))
        if planned_date != target_date:
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


def get_db_sizes(db_path: Path, order_ids: set[str]) -> set[str]:
    if not order_ids or not db_path.exists():
        return set()
    with get_db(db_path) as conn:
        table = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='fact_orders_kaspi'"
        ).fetchone()
        if not table:
            return set()
        placeholders = ",".join(["?"] * len(order_ids))
        rows = conn.execute(
            f"""
            SELECT order_id, assigned_size, my_size
            FROM fact_orders_kaspi
            WHERE order_id IN ({placeholders})
            """,
            list(order_ids),
        ).fetchall()
    sized = set()
    for row in rows:
        oid = _coerce_str(row["order_id"])
        if oid.endswith(".0"):
            oid = oid[:-2]
        size = _coerce_str(row["assigned_size"]) or _coerce_str(row["my_size"])
        if oid and size:
            sized.add(oid)
    return sized


def load_waybills(waybill_dir: Path) -> set[str]:
    """Load available waybill PDFs from folder + zips."""
    order_ids: set[str] = set()

    waybill_folder = waybill_dir / "waybills"
    if waybill_folder.exists():
        for pdf in waybill_folder.glob("*.pdf"):
            m = WAYBILL_PATTERN.search(pdf.name)
            if m:
                order_ids.add(m.group(1))
            else:
                stem = pdf.stem
                if stem.isdigit():
                    order_ids.add(stem)

    zip_files = list(waybill_dir.glob("waybill*.zip"))
    if zip_files:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_dir = Path(tmp)
            for z in zip_files:
                try:
                    with zipfile.ZipFile(z, "r") as zf:
                        for name in zf.namelist():
                            if not name.lower().endswith(".pdf"):
                                continue
                            base = Path(name).name
                            m = WAYBILL_PATTERN.search(base)
                            if m:
                                order_ids.add(m.group(1))
                except Exception as exc:
                    logger.warning(f"Failed to read {z}: {exc}")

    return order_ids


def load_output_assigned(output_dir: Path) -> tuple[dict[str, set[str]], dict[str, int], dict[str, int]]:
    """Return (assigned_order_ids_by_store, bundles_by_store, packages_by_store)."""
    assigned: dict[str, set[str]] = defaultdict(set)
    bundles: dict[str, int] = defaultdict(int)
    packages: dict[str, int] = defaultdict(int)

    build_log = output_dir / "build_log.csv"
    if build_log.exists():
        with open(build_log, newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                if row.get("type") == "MISSING":
                    continue
                store = row.get("store", "UNKNOWN")
                order_ids = _coerce_str(row.get("order_id")).split(";")
                for oid in order_ids:
                    if oid:
                        assigned[store].add(oid)
                bundles[store] += 1

    summary = output_dir / "package_summary.csv"
    if summary.exists():
        with open(summary, newline="", encoding="utf-8") as f:
            rows = list(csv.reader(f))
        for row in rows:
            if not row or row[0] in ("Сегодня", "Магазин", "Итого"):
                continue
            if len(row) >= 3:
                store = row[0]
                try:
                    packages[store] = int(float(row[2]))
                except ValueError:
                    pass

    return dict(assigned), dict(bundles), dict(packages)


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
    parser = argparse.ArgumentParser(description="Report waybill health for a given date")
    parser.add_argument("--date", help="Target date (YYYY-MM-DD, default: today)")
    parser.add_argument("--crm-file", type=Path, default=DEFAULT_CRM_PATH)
    parser.add_argument("--db-path", type=Path, default=None)
    parser.add_argument("--waybill-dir", type=Path, default=DEFAULT_WAYBILL_DIR)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--sheet", default=DEFAULT_SHEET_NAME)
    parser.add_argument("--since-days", type=int, default=7)
    parser.add_argument("--store", help="Filter by store (ACMEWEAR/UNIVERSAL/11KZ/STOREB)")
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()

    load_dotenv(PROJECT_ROOT / ".env")

    if args.date:
        target_date = datetime.strptime(args.date, "%Y-%m-%d").date()
    else:
        target_date = datetime.now(ALMATY_TZ).date()

    print("\n" + "=" * 80)
    print("WAYBILL HEALTH REPORT")
    print("=" * 80)
    print(f"Data root: {get_data_root()}")
    print(f"Target date: {target_date}")
    print(f"CRM: {args.crm_file}")
    db_path = args.db_path or data_path("db", "app.db")
    print(f"DB: {db_path}")
    print(f"Waybill dir: {args.waybill_dir}")
    print(f"Output dir: {args.output_dir}")
    print()

    api_by_store, api_errors = get_api_orders_by_store(
        target_date, since_days=args.since_days, store_filter=args.store, verbose=args.verbose
    )

    crm_all, crm_size = get_crm_orders(args.crm_file, args.sheet, target_date)
    waybills = load_waybills(args.waybill_dir)
    assigned, bundles, packages = load_output_assigned(args.output_dir)

    all_stores = set()
    for store_code in api_by_store:
        all_stores.add(API_TO_DISPLAY.get(store_code, store_code))
    for store_code in api_errors:
        all_stores.add(API_TO_DISPLAY.get(store_code, store_code))
    all_stores.update(crm_all.keys())
    all_stores.update(assigned.keys())

    headers = [
        "STORE", "API", "CRM", "CRM_SIZE", "DB_SIZE",
        "PDFS", "BUNDLED", "BUNDLES", "PACKAGES",
        "MISS_CRM", "MISS_SIZE", "MISS_PDF", "MISS_BUNDLE",
    ]

    rows = []
    totals = defaultdict(int)

    # Precompute DB sizes for API orders
    api_all_ids = set()
    for ids in api_by_store.values():
        api_all_ids.update(ids)
    db_sized = get_db_sizes(db_path, api_all_ids)

    # Per-store breakdown
    for store in sorted(all_stores):
        api_store_code = None
        for code, disp in API_TO_DISPLAY.items():
            if disp == store:
                api_store_code = code
                break
        api_ids = api_by_store.get(api_store_code, set()) if api_store_code else set()
        api_failed = api_store_code in api_errors if api_store_code else False

        crm_ids = crm_all.get(store, set())
        crm_size_ids = crm_size.get(store, set())

        # Restrict to API expectations
        api_crm_ids = api_ids & crm_ids
        api_crm_size_ids = api_ids & crm_size_ids
        api_db_size_ids = api_ids & db_sized
        api_pdf_ids = api_ids & waybills
        api_assigned_ids = api_ids & assigned.get(store, set())

        miss_crm = len(api_ids - crm_ids)
        size_ok = api_db_size_ids | api_crm_size_ids
        miss_size = len(api_ids - size_ok)
        miss_pdf = len(api_ids - waybills)
        miss_bundle = len(api_ids - assigned.get(store, set()))

        if api_failed:
            row = [
                store,
                "ERR",
                "-",
                "-",
                "-",
                "-",
                "-",
                str(bundles.get(store, 0)),
                str(packages.get(store, 0)),
                "-",
                "-",
                "-",
                "-",
            ]
        else:
            row = [
                store,
                str(len(api_ids)),
                str(len(api_crm_ids)),
                str(len(api_crm_size_ids)),
                str(len(api_db_size_ids)),
                str(len(api_pdf_ids)),
                str(len(api_assigned_ids)),
                str(bundles.get(store, 0)),
                str(packages.get(store, 0)),
                str(miss_crm),
                str(miss_size),
                str(miss_pdf),
                str(miss_bundle),
            ]
        rows.append(row)

        if not api_failed:
            totals["API"] += len(api_ids)
            totals["CRM"] += len(api_crm_ids)
            totals["CRM_SIZE"] += len(api_crm_size_ids)
            totals["DB_SIZE"] += len(api_db_size_ids)
            totals["PDFS"] += len(api_pdf_ids)
            totals["BUNDLED"] += len(api_assigned_ids)
            totals["MISS_CRM"] += miss_crm
            totals["MISS_SIZE"] += miss_size
            totals["MISS_PDF"] += miss_pdf
            totals["MISS_BUNDLE"] += miss_bundle
        totals["BUNDLES"] += bundles.get(store, 0)
        totals["PACKAGES"] += packages.get(store, 0)

    totals_row = [
        "TOTAL",
        str(totals["API"]),
        str(totals["CRM"]),
        str(totals["CRM_SIZE"]),
        str(totals["DB_SIZE"]),
        str(totals["PDFS"]),
        str(totals["BUNDLED"]),
        str(totals["BUNDLES"]),
        str(totals["PACKAGES"]),
        str(totals["MISS_CRM"]),
        str(totals["MISS_SIZE"]),
        str(totals["MISS_PDF"]),
        str(totals["MISS_BUNDLE"]),
    ]
    if api_errors:
        totals_row = [
            "TOTAL",
            "PARTIAL",
            "PARTIAL",
            "PARTIAL",
            "PARTIAL",
            "PARTIAL",
            "PARTIAL",
            str(totals["BUNDLES"]),
            str(totals["PACKAGES"]),
            "PARTIAL",
            "PARTIAL",
            "PARTIAL",
            "PARTIAL",
        ]
    rows.append(totals_row)

    print(format_table(headers, rows))

    # Show first 5 missing IDs per reason
    def show_missing(title: str, ids: set[str]) -> None:
        if not ids:
            return
        sample = sorted(list(ids))[:5]
        print(f"{title} (first 5): {', '.join(sample)}")

    missing_crm_ids = api_all_ids - set().union(*crm_all.values()) if api_all_ids else set()
    size_ok_ids = db_sized | set().union(*crm_size.values()) if api_all_ids else set()
    missing_size_ids = api_all_ids - size_ok_ids
    missing_pdf_ids = api_all_ids - waybills
    assigned_all = set().union(*assigned.values()) if assigned else set()
    missing_bundle_ids = api_all_ids - assigned_all

    if api_errors:
        print("WARNING: API selection failed for stores: " + ", ".join(sorted(api_errors)))
        print("         Counts marked PARTIAL/ERR exclude failed stores.")
    else:
        show_missing("Missing in CRM", missing_crm_ids)
        show_missing("Missing size (DB+CRM)", missing_size_ids)
        show_missing("Missing PDF", missing_pdf_ids)
        show_missing("Missing in bundles", missing_bundle_ids)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
