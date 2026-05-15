#!/usr/bin/env python3
"""
Generate single-truth business insides snapshot from paid capital + delivered sales.
"""

from __future__ import annotations

import argparse
from datetime import date, datetime, timedelta
import glob
import json
import os
from pathlib import Path
import re
import sqlite3
import sys
from typing import Any
import warnings

import pandas as pd
import yaml
from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from core.cashflow.paid_capital_truth import compute_paid_capital_truth
from core.ads.canonical_truth import CanonicalAdsError, load_daily_total_ads
from core.db.sales_truth_query_guard import (
    install_sales_truth_query_guard,
    remove_sales_truth_query_guard,
)
from core.sales.ocean_drop_anchor import (
    DEFAULT_REGISTRY as DEFAULT_OCEAN_DROP_ANCHOR_REGISTRY,
    OceanDropAnchorError,
    load_ocean_drop_anchor,
)
from core.sales import ensure_sales_truth_views
from scripts.build_ocean_drop_reference_snapshot import build_ocean_drop_snapshot_dataframe

DEFAULT_DB = PROJECT_ROOT / "db" / "app.db"
DEFAULT_BANK = PROJECT_ROOT / "config" / "bank_accounts.yaml"
DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "config" / "business_insides"
DEFAULT_BI_ALIGNMENT_OUTPUT_ROOT = (
    PROJECT_ROOT / "exports" / "validation" / "business_insides_ocean_drop_alignment"
)
DEFAULT_BI_ALIGNMENT_WINDOW_DAYS = 14
DEFAULT_WAYBILL_SELECTION_CACHE = (
    PROJECT_ROOT / "excel_ui" / "ActiveOrders" / "waybills" / "_waybill_selection_orders.json"
)
DEFAULT_SHIPPED_TRUTH_ROOT = PROJECT_ROOT / "exports" / "validation" / "shipped_truth_crm_waybill"
DEFAULT_WAYBILL_ARCHIVE_DIR = PROJECT_ROOT / "excel_ui" / "Archive"
WAYBILL_ORDER_ID_RE = re.compile(r"(\d{6,})")
DEFAULT_ARCHIVE_ORDERS_GLOBS = [
    str(PROJECT_ROOT / "excel_ui" / "ActiveOrders" / "**" / "ArchiveOrders*.xlsx"),
    str(
        PROJECT_ROOT.parent
        / "kaspi_etl"
        / "docs"
        / "ops"
        / "kaspi"
        / "ActiveOrders"
        / "**"
        / "ArchiveOrders*.xlsx"
    ),
]


def _parse_as_of(value: str | date | None) -> date:
    if isinstance(value, date):
        return value
    if not value:
        return date.today()
    return date.fromisoformat(str(value))


def _fmt_kzt(value: float | None) -> str:
    if value is None:
        return "N/A"
    return f"{float(value):,.2f}"


def _ascii_table(headers: list[str], rows: list[list[str]]) -> str:
    widths = [len(h) for h in headers]
    for row in rows:
        for idx, cell in enumerate(row):
            widths[idx] = max(widths[idx], len(cell))

    def _fmt_row(row: list[str]) -> str:
        return "| " + " | ".join(cell.ljust(widths[i]) for i, cell in enumerate(row)) + " |"

    sep = "+-" + "-+-".join("-" * w for w in widths) + "-+"
    out = [sep, _fmt_row(headers), sep]
    out.extend(_fmt_row(r) for r in rows)
    out.append(sep)
    return "\n".join(out)


def _table_exists(conn: sqlite3.Connection, name: str) -> bool:
    row = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
        (name,),
    ).fetchone()
    return row is not None


def _column_exists(conn: sqlite3.Connection, table: str, column: str) -> bool:
    rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    return any(str(row[1]) == column for row in rows)


def _resolve_archive_orders_files(
    archive_orders_globs: list[str] | None = None,
) -> list[Path]:
    patterns: list[str] = []
    if archive_orders_globs is not None:
        patterns.extend(str(item).strip() for item in archive_orders_globs if str(item).strip())
    else:
        env_value = str(os.environ.get("AB_ARCHIVE_ORDERS_GLOBS") or "").strip()
        if env_value:
            patterns.extend(part.strip() for part in env_value.split(os.pathsep) if part.strip())
        else:
            patterns.extend(DEFAULT_ARCHIVE_ORDERS_GLOBS)

    files: list[Path] = []
    for pattern in patterns:
        for match in sorted(glob.glob(pattern, recursive=True)):
            path = Path(match)
            if path.is_file() and path.name.endswith(".xlsx") and not path.name.startswith("~$"):
                files.append(path.resolve())
    deduped: list[Path] = []
    seen: set[str] = set()
    for path in files:
        key = str(path)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(path)
    return deduped


def _parse_archive_number(value: Any) -> float:
    if value is None:
        return 0.0
    text = str(value).strip()
    if not text or text.lower() in {"nan", "none"}:
        return 0.0
    cleaned = text.replace(" ", "").replace("\u00a0", "").replace(",", ".")
    try:
        return float(cleaned)
    except ValueError:
        return 0.0


def _parse_archive_date(value: Any) -> date | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text or text.lower() in {"nan", "none"}:
        return None
    for fmt in ("%d.%m.%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(text[:10], fmt).date()
        except ValueError:
            continue
    try:
        parsed = pd.to_datetime(text, dayfirst=True, errors="coerce")
    except Exception:  # pragma: no cover - defensive
        parsed = None
    if parsed is None or pd.isna(parsed):
        return None
    return parsed.date()


def _load_archive_orders_daily(
    *,
    as_of_date: date,
    start_date: date,
    archive_orders_globs: list[str] | None = None,
) -> dict[str, Any]:
    files = _resolve_archive_orders_files(archive_orders_globs)
    if not files:
        return {
            "status": "missing",
            "reason": "no_archive_files",
            "files": [],
            "days": {},
        }

    required_cols = {
        "№ заказа",
        "Дата изменения статуса",
        "Статус",
        "Количество",
        "Сумма",
        "Склад передачи КД",
    }
    delivered_statuses = {"ВЫДАН", "COMPLETED", "DELIVERED"}
    rows_by_line: dict[tuple[Any, ...], dict[str, Any]] = {}
    used_files: list[str] = []

    for file_path in files:
        try:
            with warnings.catch_warnings():
                warnings.filterwarnings(
                    "ignore",
                    message="Workbook contains no default style, apply openpyxl's default",
                    category=UserWarning,
                )
                df = pd.read_excel(file_path, dtype=str)
        except Exception:
            continue
        if not required_cols.issubset(set(df.columns)):
            continue
        used_files.append(str(file_path))
        for _, row in df.iterrows():
            order_id = str(row.get("№ заказа") or "").strip()
            store_code = str(row.get("Склад передачи КД") or "").strip().upper()
            status_raw = str(row.get("Статус") or "").strip()
            status = status_raw.upper()
            if not order_id or not store_code or status not in delivered_statuses:
                continue
            status_date = _parse_archive_date(row.get("Дата изменения статуса"))
            if status_date is None or status_date < start_date or status_date > as_of_date:
                continue
            quantity = _parse_archive_number(row.get("Количество"))
            amount = _parse_archive_number(row.get("Сумма"))
            article = str(row.get("Артикул") or "").strip().upper()
            offer_name = str(row.get("Название товара в Kaspi Магазине") or "").strip().upper()
            stable_line_key = (
                store_code,
                order_id,
                article,
                offer_name,
                round(quantity if quantity > 0 else 1.0, 6),
                round(amount, 6),
            )
            current = rows_by_line.get(stable_line_key)
            candidate = {
                "status_date": status_date,
                "order_id": order_id,
                "quantity": quantity if quantity > 0 else 1.0,
                "amount": amount,
            }
            if current is None or candidate["status_date"] >= current["status_date"]:
                rows_by_line[stable_line_key] = candidate

    if not rows_by_line:
        return {
            "status": "missing",
            "reason": "no_delivered_rows_in_window",
            "files": used_files,
            "days": {},
        }

    by_day: dict[str, dict[str, float]] = {}
    day_orders: dict[str, set[str]] = {}
    for row in rows_by_line.values():
        day = row["status_date"].isoformat()
        agg = by_day.setdefault(day, {"units_delivered": 0.0, "net_rev_kzt": 0.0, "orders": 0.0})
        day_orders.setdefault(day, set()).add(str(row.get("order_id") or ""))
        agg["units_delivered"] += float(row["quantity"])
        agg["net_rev_kzt"] += float(row["amount"])

    for day in list(by_day.keys()):
        by_day[day] = {
            "units_delivered": round(float(by_day[day]["units_delivered"]), 2),
            "net_rev_kzt": round(float(by_day[day]["net_rev_kzt"]), 2),
            "orders": len({oid for oid in day_orders.get(day, set()) if oid}),
        }

    return {
        "status": "available",
        "reason": "ok",
        "files": used_files,
        "days": by_day,
        "row_count": len(rows_by_line),
    }


def _resolve_waybill_archive_root() -> Path:
    env_value = str(os.environ.get("AB_WAYBILL_ARCHIVE_ROOT") or "").strip()
    if env_value:
        return Path(env_value).expanduser().resolve()
    return DEFAULT_WAYBILL_ARCHIVE_DIR.resolve()


def _parse_order_id_from_filename(name: str) -> str | None:
    match = WAYBILL_ORDER_ID_RE.search(name)
    if not match:
        return None
    return str(match.group(1) or "").strip() or None


def _find_waybill_archive_input_dir(*, archive_root: Path, as_of_iso: str) -> Path | None:
    if not archive_root.exists():
        return None
    pattern = f"input_{as_of_iso}_*"
    matches = [
        path
        for path in archive_root.glob(pattern)
        if path.is_dir()
    ]
    if not matches:
        return None
    return sorted(matches)[-1]


def _query_order_store_quantity(
    *,
    db_path: Path,
    order_ids: set[str],
) -> dict[str, tuple[str, float]]:
    if not db_path.exists() or not order_ids:
        return {}
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    try:
        if not _table_exists(conn, "fact_orders_kaspi"):
            return {}
        has_order_id = _column_exists(conn, "fact_orders_kaspi", "order_id")
        has_store = _column_exists(conn, "fact_orders_kaspi", "store_code")
        has_qty = _column_exists(conn, "fact_orders_kaspi", "quantity")
        if not (has_order_id and has_store and has_qty):
            return {}

        result: dict[str, tuple[str, float]] = {}
        order_list = sorted(order_ids)
        chunk_size = 500
        for idx in range(0, len(order_list), chunk_size):
            chunk = order_list[idx : idx + chunk_size]
            placeholders = ",".join(["?"] * len(chunk))
            rows = conn.execute(
                f"""
                SELECT
                    CAST(order_id AS TEXT) AS order_id,
                    UPPER(TRIM(CAST(COALESCE(store_code, 'UNKNOWN') AS TEXT))) AS store_code,
                    MAX(CASE
                        WHEN CAST(COALESCE(quantity, 1) AS REAL) > 0
                            THEN CAST(quantity AS REAL)
                        ELSE 1
                    END) AS qty
                FROM fact_orders_kaspi
                WHERE CAST(order_id AS TEXT) IN ({placeholders})
                GROUP BY CAST(order_id AS TEXT), UPPER(TRIM(CAST(COALESCE(store_code, 'UNKNOWN') AS TEXT)))
                """,
                chunk,
            ).fetchall()
            for row in rows:
                order_id = str(row["order_id"] or "").strip()
                if not order_id:
                    continue
                store_code = str(row["store_code"] or "UNKNOWN").strip().upper() or "UNKNOWN"
                qty = float(row["qty"] or 1.0)
                result[order_id] = (store_code, qty if qty > 0 else 1.0)
        return result
    finally:
        conn.close()


def _load_waybill_archive_snapshot(
    *,
    db_path: Path,
    as_of_date: date,
    selection_cache_path: Path,
) -> dict[str, Any] | None:
    archive_root = _resolve_waybill_archive_root()
    as_of_iso = as_of_date.isoformat()
    archive_dir = _find_waybill_archive_input_dir(archive_root=archive_root, as_of_iso=as_of_iso)
    if archive_dir is None:
        return None

    manifest_path = archive_dir / "archive_manifest.json"
    waybill_dir = archive_dir / "waybills"
    if not manifest_path.exists() or not waybill_dir.exists():
        return None

    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except Exception:
        return None
    if not isinstance(manifest, dict):
        return None

    pdf_order_ids: set[str] = set()
    for pdf in sorted(waybill_dir.glob("*.pdf")):
        order_id = _parse_order_id_from_filename(pdf.name)
        if order_id:
            pdf_order_ids.add(order_id)

    order_meta = _query_order_store_quantity(db_path=db_path, order_ids=pdf_order_ids)
    stores: dict[str, dict[str, float | int]] = {}
    total_units = 0.0
    for order_id in sorted(pdf_order_ids):
        store_code, qty = order_meta.get(order_id, ("UNKNOWN", 1.0))
        bucket = stores.setdefault(store_code, {"orders": 0, "units": 0.0})
        bucket["orders"] = int(bucket["orders"]) + 1
        bucket["units"] = round(float(bucket["units"]) + float(qty), 2)
        total_units += float(qty)

    selected_count = int(float(manifest.get("selected_count") or 0))
    copied_waybills = int(float(manifest.get("copied_waybills") or len(pdf_order_ids)))
    missing_waybills = int(float(manifest.get("missing_waybills") or 0))
    unresolved_missing = max(0, selected_count - len(pdf_order_ids))
    if unresolved_missing > 0:
        missing_bucket = stores.setdefault("_MISSING_WAYBILL_URL", {"orders": 0, "units": 0.0})
        missing_bucket["orders"] = int(missing_bucket["orders"]) + unresolved_missing
        missing_bucket["units"] = round(float(missing_bucket["units"]) + float(unresolved_missing), 2)
        total_units += float(unresolved_missing)

    return {
        "status": "available_archive",
        "reason": "archive_input_snapshot",
        "as_of": as_of_iso,
        "target_date": as_of_iso,
        "cache_path": str(selection_cache_path),
        "include_overdue": True,
        "all_dates": False,
        "stores": stores,
        "totals": {
            "orders": int(selected_count if selected_count > 0 else len(pdf_order_ids)),
            "units": round(float(total_units), 2),
        },
        "archive_snapshot": {
            "archive_root": str(archive_root),
            "archive_input_dir": str(archive_dir),
            "manifest_path": str(manifest_path),
            "selected_count": int(selected_count),
            "copied_waybills": int(copied_waybills),
            "missing_waybills": int(missing_waybills),
            "resolved_waybill_pdf_ids": len(pdf_order_ids),
        },
    }


def _load_waybill_live_snapshot(
    *,
    db_path: Path,
    as_of_date: date,
    selection_cache_path: Path,
) -> dict[str, Any]:
    target_as_of = as_of_date.isoformat()
    load_dotenv(PROJECT_ROOT / ".env", override=False)
    try:
        from scripts.report_waybill_status import get_api_orders_by_store
    except Exception as exc:  # pragma: no cover - defensive
        return {
            "status": "live_api_unavailable",
            "reason": f"live_import_error:{exc}",
            "as_of": target_as_of,
            "target_date": target_as_of,
            "cache_path": str(selection_cache_path),
            "include_overdue": True,
            "all_dates": False,
            "stores": {},
            "totals": {"orders": 0, "units": 0},
        }

    stores_orders, error_stores = get_api_orders_by_store(
        as_of_date,
        since_days=3,
        include_overdue=True,
    )
    if error_stores:
        return {
            "status": "live_api_unavailable",
            "reason": "live_api_errors:" + ",".join(sorted(error_stores)),
            "as_of": target_as_of,
            "target_date": target_as_of,
            "cache_path": str(selection_cache_path),
            "include_overdue": True,
            "all_dates": False,
            "stores": {},
            "totals": {"orders": 0, "units": 0},
            "live_snapshot": {
                "error_stores": sorted(error_stores),
                "since_days": 3,
            },
        }

    normalized_orders: dict[str, set[str]] = {}
    all_order_ids: set[str] = set()
    for store_code, raw_ids in (stores_orders or {}).items():
        cleaned_ids = {
            str(order_id).strip()
            for order_id in (raw_ids or set())
            if str(order_id).strip()
        }
        if not cleaned_ids:
            continue
        normalized_store = str(store_code or "").strip().upper()
        normalized_orders[normalized_store] = cleaned_ids
        all_order_ids.update(cleaned_ids)

    if not normalized_orders:
        return {
            "status": "live_api_unavailable",
            "reason": "live_api_no_orders",
            "as_of": target_as_of,
            "target_date": target_as_of,
            "cache_path": str(selection_cache_path),
            "include_overdue": True,
            "all_dates": False,
            "stores": {},
            "totals": {"orders": 0, "units": 0},
            "live_snapshot": {
                "error_stores": [],
                "since_days": 3,
            },
        }

    quantity_meta = _query_order_store_quantity(
        db_path=db_path,
        order_ids=all_order_ids,
    )
    stores_out: dict[str, dict[str, float | int]] = {}
    total_orders = 0
    total_units = 0.0
    for store_code in sorted(normalized_orders.keys()):
        ids = normalized_orders[store_code]
        order_count = len(ids)
        units = sum(float(quantity_meta.get(order_id, (store_code, 1.0))[1]) for order_id in ids)
        stores_out[store_code] = {
            "orders": int(order_count),
            "units": round(float(units), 2),
        }
        total_orders += order_count
        total_units += units

    return {
        "status": "available_live",
        "reason": "live_api_selection",
        "as_of": target_as_of,
        "target_date": target_as_of,
        "cache_path": str(selection_cache_path),
        "include_overdue": True,
        "all_dates": False,
        "stores": stores_out,
        "totals": {
            "orders": int(total_orders),
            "units": round(float(total_units), 2),
        },
        "live_snapshot": {
            "error_stores": [],
            "since_days": 3,
            "store_count": len(stores_out),
        },
    }


def load_waybill_selection_snapshot(
    *,
    db_path: Path,
    as_of_date: date,
    selection_cache_path: Path = DEFAULT_WAYBILL_SELECTION_CACHE,
) -> dict[str, Any]:
    target_as_of = as_of_date.isoformat()
    snapshot: dict[str, Any] = {
        "status": "missing",
        "reason": "selection_cache_missing",
        "as_of": target_as_of,
        "target_date": None,
        "cache_path": str(selection_cache_path),
        "include_overdue": None,
        "all_dates": None,
        "stores": {},
        "totals": {"orders": 0, "units": 0},
    }

    if not selection_cache_path.exists():
        archive_snapshot = _load_waybill_archive_snapshot(
            db_path=db_path.resolve(),
            as_of_date=as_of_date,
            selection_cache_path=selection_cache_path.resolve(),
        )
        if archive_snapshot is not None:
            return archive_snapshot
        return snapshot

    try:
        payload = json.loads(selection_cache_path.read_text(encoding="utf-8"))
    except Exception as exc:  # pragma: no cover - defensive
        archive_snapshot = _load_waybill_archive_snapshot(
            db_path=db_path.resolve(),
            as_of_date=as_of_date,
            selection_cache_path=selection_cache_path.resolve(),
        )
        if archive_snapshot is not None:
            archive_snapshot["reason"] = f"archive_fallback_after_invalid_cache:{exc}"
            return archive_snapshot
        snapshot["status"] = "invalid"
        snapshot["reason"] = f"invalid_json:{exc}"
        return snapshot

    if not isinstance(payload, dict):
        archive_snapshot = _load_waybill_archive_snapshot(
            db_path=db_path.resolve(),
            as_of_date=as_of_date,
            selection_cache_path=selection_cache_path.resolve(),
        )
        if archive_snapshot is not None:
            archive_snapshot["reason"] = "archive_fallback_after_invalid_payload_type"
            return archive_snapshot
        snapshot["status"] = "invalid"
        snapshot["reason"] = "invalid_payload_type"
        return snapshot

    target_date = str(payload.get("target_date") or "").strip()
    snapshot["target_date"] = target_date or None
    snapshot["include_overdue"] = bool(payload.get("include_overdue"))
    snapshot["all_dates"] = bool(payload.get("all_dates"))

    if target_date and target_date != target_as_of:
        archive_snapshot = _load_waybill_archive_snapshot(
            db_path=db_path.resolve(),
            as_of_date=as_of_date,
            selection_cache_path=selection_cache_path.resolve(),
        )
        if archive_snapshot is not None:
            archive_snapshot["cache_target_date"] = target_date
            archive_snapshot["cache_status"] = "as_of_mismatch"
            archive_snapshot["cache_reason"] = f"target_date={target_date} expected={target_as_of}"
            return archive_snapshot
        live_snapshot = _load_waybill_live_snapshot(
            db_path=db_path.resolve(),
            as_of_date=as_of_date,
            selection_cache_path=selection_cache_path.resolve(),
        )
        live_snapshot["cache_target_date"] = target_date
        live_snapshot["cache_status"] = "as_of_mismatch"
        live_snapshot["cache_reason"] = f"target_date={target_date} expected={target_as_of}"
        return live_snapshot

    stores_raw = payload.get("stores") or {}
    if not isinstance(stores_raw, dict):
        snapshot["status"] = "invalid"
        snapshot["reason"] = "stores_payload_not_dict"
        return snapshot

    order_ids_all: set[str] = set()
    stores_orders: dict[str, set[str]] = {}
    for store_code, raw_ids in stores_raw.items():
        if not isinstance(raw_ids, list):
            continue
        cleaned_ids = {
            str(order_id).strip()
            for order_id in raw_ids
            if str(order_id).strip()
        }
        if cleaned_ids:
            stores_orders[str(store_code).strip().upper()] = cleaned_ids
            order_ids_all.update(cleaned_ids)

    if not stores_orders:
        snapshot["status"] = "invalid"
        snapshot["reason"] = "no_order_ids"
        return snapshot

    cache_order_count = sum(len(ids) for ids in stores_orders.values())
    cache_path_resolved = selection_cache_path.resolve()
    cache_in_project_scope = False
    try:
        cache_in_project_scope = cache_path_resolved.is_relative_to(PROJECT_ROOT.resolve())
    except Exception:  # pragma: no cover - defensive
        cache_in_project_scope = str(cache_path_resolved).startswith(str(PROJECT_ROOT.resolve()))

    if target_date == target_as_of and cache_in_project_scope:
        archive_snapshot = _load_waybill_archive_snapshot(
            db_path=db_path.resolve(),
            as_of_date=as_of_date,
            selection_cache_path=cache_path_resolved,
        )
        if archive_snapshot is not None:
            archive_orders = int(float((archive_snapshot.get("totals") or {}).get("orders") or 0))
            if archive_orders > cache_order_count:
                archive_snapshot["cache_status"] = "underflow"
                archive_snapshot["cache_reason"] = (
                    f"cache_orders={cache_order_count} archive_orders={archive_orders}"
                )
                archive_snapshot["reason"] = "archive_fallback_cache_underflow"
                return archive_snapshot

    quantity_by_order: dict[str, float] = {}
    if db_path.exists() and order_ids_all:
        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row
        try:
            if _table_exists(conn, "fact_orders_kaspi"):
                has_order_id = _column_exists(conn, "fact_orders_kaspi", "order_id")
                has_quantity = _column_exists(conn, "fact_orders_kaspi", "quantity")
                if has_order_id and has_quantity:
                    order_list = sorted(order_ids_all)
                    chunk_size = 500
                    for idx in range(0, len(order_list), chunk_size):
                        chunk = order_list[idx : idx + chunk_size]
                        placeholders = ",".join(["?"] * len(chunk))
                        rows = conn.execute(
                            f"""
                            SELECT
                                CAST(order_id AS TEXT) AS order_id,
                                MAX(CASE
                                    WHEN CAST(COALESCE(quantity, 1) AS REAL) > 0
                                        THEN CAST(quantity AS REAL)
                                    ELSE 1
                                END) AS qty
                            FROM fact_orders_kaspi
                            WHERE CAST(order_id AS TEXT) IN ({placeholders})
                            GROUP BY CAST(order_id AS TEXT)
                            """,
                            chunk,
                        ).fetchall()
                        for row in rows:
                            order_id = str(row["order_id"] or "").strip()
                            if not order_id:
                                continue
                            quantity_by_order[order_id] = float(row["qty"] or 1.0)
        finally:
            conn.close()

    stores_out: dict[str, dict[str, float | int]] = {}
    total_orders = 0
    total_units = 0.0
    for store_code in sorted(stores_orders.keys()):
        ids = stores_orders[store_code]
        order_count = len(ids)
        units = sum(float(quantity_by_order.get(order_id, 1.0)) for order_id in ids)
        stores_out[store_code] = {
            "orders": int(order_count),
            "units": round(float(units), 2),
        }
        total_orders += order_count
        total_units += units

    snapshot["stores"] = stores_out
    snapshot["totals"] = {
        "orders": int(total_orders),
        "units": round(float(total_units), 2),
    }

    snapshot["status"] = "available"
    snapshot["reason"] = "ok"

    return snapshot


def _parse_window_dir_name(name: str) -> tuple[date, date] | None:
    match = re.fullmatch(r"(\d{4}-\d{2}-\d{2})_to_(\d{4}-\d{2}-\d{2})", name)
    if not match:
        return None
    try:
        since = date.fromisoformat(match.group(1))
        until = date.fromisoformat(match.group(2))
    except ValueError:
        return None
    if since > until:
        return None
    return since, until


def load_shipped_truth_snapshot(
    *,
    as_of_date: date,
    shipped_truth_root: Path,
) -> dict[str, Any] | None:
    """Load canonical shipped-primary totals for a day from shipped-truth summaries."""
    target_day = as_of_date.isoformat()
    direct_summary = shipped_truth_root / f"{target_day}_to_{target_day}" / "summary.json"
    candidate_paths: list[Path] = []
    if direct_summary.exists():
        candidate_paths.append(direct_summary)
    for summary_path in sorted(shipped_truth_root.glob("*_to_*/summary.json")):
        window = _parse_window_dir_name(summary_path.parent.name)
        if window is None:
            continue
        since, until = window
        if since <= as_of_date <= until:
            candidate_paths.append(summary_path)

    if not candidate_paths:
        return None

    # Prefer freshest summaries first; use smaller windows as tie-breaker.
    def _window_days(path: Path) -> int:
        window = _parse_window_dir_name(path.parent.name)
        if window is None:
            return 10**9
        return (window[1] - window[0]).days

    unique_paths = {p.resolve() for p in candidate_paths}
    ordered_paths = sorted(
        unique_paths,
        key=lambda path: (
            -path.stat().st_mtime,
            _window_days(path),
        ),
    )

    for summary_path in ordered_paths:
        try:
            payload = json.loads(summary_path.read_text(encoding="utf-8"))
        except Exception:
            continue
        rows = payload.get("rows")
        if not isinstance(rows, list):
            continue
        day_rows = [row for row in rows if str(row.get("day") or "").strip() == target_day]
        if not day_rows:
            continue

        stores: dict[str, dict[str, float | int]] = {}
        total_orders = 0
        for row in day_rows:
            store = str(row.get("store") or "UNKNOWN").strip()
            api_primary = int(row.get("api_primary") or 0)
            if api_primary <= 0:
                continue
            bucket = stores.setdefault(store, {"orders": 0, "units": 0.0})
            bucket["orders"] = int(bucket["orders"]) + api_primary
            bucket["units"] = round(float(bucket["units"]) + float(api_primary), 2)
            total_orders += api_primary

        if total_orders <= 0:
            continue

        return {
            "status": "available_shipped_truth",
            "reason": "canonical_shipped_primary",
            "as_of": target_day,
            "target_date": target_day,
            "cache_path": str(summary_path),
            "include_overdue": None,
            "all_dates": None,
            "stores": stores,
            "totals": {
                "orders": int(total_orders),
                "units": round(float(total_orders), 2),
            },
            "shipped_truth_source": {
                "summary_path": str(summary_path),
            },
        }
    return None


def _load_ads_daily(
    db_path: Path,
    start_date: date,
    end_date: date,
) -> tuple[dict[str, float], dict[str, float]]:
    effective_cost_mode = os.environ.get("AB_ADS_EFFECTIVE_COST_MODE", "").strip().lower() in {
        "1",
        "true",
        "yes",
        "y",
    }
    effective_policy_path = Path(
        os.environ.get(
            "AB_ADS_EFFECTIVE_COST_POLICY_PATH",
            str(PROJECT_ROOT / "config" / "kaspi_ads_cost_adjustments.yaml"),
        )
    ).expanduser()
    try:
        by_date, totals = load_daily_total_ads(
            db_path=db_path,
            start=start_date.isoformat(),
            end=end_date.isoformat(),
            effective_cost_mode=effective_cost_mode,
            effective_policy_path=effective_policy_path if effective_cost_mode else None,
        )
    except CanonicalAdsError as exc:
        message = str(exc)
        reason = "policy_parse_error" if "parse" in message else "policy_missing" if "missing" in message else "canonical_ads_error"
        return {}, {
            "status": "unavailable",
            "reason": reason,
            "source_path": str(db_path),
            "policy_path": str(effective_policy_path) if effective_cost_mode else None,
            "mapped_rows": None,
            "unmapped_rows": None,
            "mapped_cost_kzt": None,
            "unmapped_cost_kzt": None,
            "total_cost_kzt": None,
            "mapping_coverage_pct": None,
        }
    totals["reason"] = "effective_cost_policy" if effective_cost_mode and totals.get("status") == "available" else totals.get("reason")
    if effective_cost_mode:
        totals["policy_path"] = str(effective_policy_path)
        totals["effective_cost_mode"] = True
    return by_date, totals


def compute_sales_metrics(
    *,
    db_path: Path = DEFAULT_DB,
    as_of: str | date | None = None,
    last_7_days: int = 7,
    last_30_days: int = 30,
    enforce_query_guard: bool = False,
    allow_completed_revenue_fallback: bool = True,
    waybill_selection_cache_path: Path = DEFAULT_WAYBILL_SELECTION_CACHE,
    shipped_truth_root: Path | None = DEFAULT_SHIPPED_TRUTH_ROOT,
    archive_orders_globs: list[str] | None = None,
) -> dict[str, Any]:
    as_of_date = _parse_as_of(as_of)
    start_30 = as_of_date - timedelta(days=max(1, int(last_30_days)) - 1)
    start_7 = as_of_date - timedelta(days=max(1, int(last_7_days)) - 1)

    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    guard_installed = False
    fallback_completed_daily_rows: list[sqlite3.Row] = []
    try:
        ensure_sales_truth_views(conn)
        if enforce_query_guard:
            install_sales_truth_query_guard(conn)
            guard_installed = True
        line_rows = conn.execute(
            """
            SELECT sale_date, sku_key, cogs_source
            FROM view_sales_line_truth
            WHERE date(sale_date) BETWEEN ? AND ?
            """,
            (start_30.isoformat(), as_of_date.isoformat()),
        ).fetchall()
        daily_line_rows = conn.execute(
            """
            SELECT
                date(sale_date) AS sale_date,
                SUM(COALESCE(units, 0)) AS units_delivered,
                SUM(COALESCE(net_rev_kzt, 0)) AS net_rev_kzt
            FROM view_sales_line_truth
            WHERE date(sale_date) BETWEEN ? AND ?
            GROUP BY date(sale_date)
            ORDER BY date(sale_date)
            """,
            (start_30.isoformat(), as_of_date.isoformat()),
        ).fetchall()
        daily_fin_rows = conn.execute(
            """
            SELECT
                date(sale_date) AS sale_date,
                SUM(COALESCE(cogs_kzt, 0)) AS cogs_kzt,
                SUM(COALESCE(profit_kzt, 0)) AS profit_kzt
            FROM view_sales_daily_truth
            WHERE date(sale_date) BETWEEN ? AND ?
            GROUP BY date(sale_date)
            ORDER BY date(sale_date)
            """,
            (start_30.isoformat(), as_of_date.isoformat()),
        ).fetchall()

        if _table_exists(conn, "fact_orders_kaspi") and _column_exists(
            conn, "fact_orders_kaspi", "internal_status"
        ):
            sale_date_candidates = [
                candidate
                for candidate in (
                    "status_updated_at",
                    "planned_shipment_date",
                    "courier_transmission_date",
                    "actual_shipment_date",
                    "planned_delivery_date",
                    "updated_at",
                    "created_at",
                )
                if _column_exists(conn, "fact_orders_kaspi", candidate)
            ]
            if sale_date_candidates:
                sale_ts_expr = "COALESCE(" + ", ".join(
                    f"NULLIF(TRIM(CAST({candidate} AS TEXT)), '')"
                    for candidate in sale_date_candidates
                ) + ")"
                sale_date_expr = f"date({sale_ts_expr})"
                qty_expr = (
                    "COALESCE(quantity, 1)"
                    if _column_exists(conn, "fact_orders_kaspi", "quantity")
                    else "1"
                )
                unit_price_expr = (
                    "COALESCE(unit_price_kzt, 0)"
                    if _column_exists(conn, "fact_orders_kaspi", "unit_price_kzt")
                    else "0"
                )
                returned_expr = (
                    "COALESCE(returned_to_warehouse, 0)"
                    if _column_exists(conn, "fact_orders_kaspi", "returned_to_warehouse")
                    else "0"
                )
                fallback_completed_daily_rows = conn.execute(
                    f"""
                    SELECT
                        {sale_date_expr} AS sale_date,
                        SUM({qty_expr}) AS units_shipped,
                        SUM(({unit_price_expr}) * ({qty_expr})) AS net_rev_kzt
                    FROM fact_orders_kaspi
                    WHERE UPPER(COALESCE(internal_status, '')) = 'COMPLETED'
                      AND {returned_expr} = 0
                      AND {sale_date_expr} BETWEEN ? AND ?
                    GROUP BY {sale_date_expr}
                    ORDER BY {sale_date_expr}
                    """,
                    (start_30.isoformat(), as_of_date.isoformat()),
                ).fetchall()
    finally:
        if guard_installed:
            remove_sales_truth_query_guard(conn)
        conn.close()

    by_date: dict[str, dict[str, float]] = {}
    fallback_rows = 0
    unresolved_rows = 0
    unresolved_skus: set[str] = set()
    total_rows = 0

    for row in line_rows:
        total_rows += 1
        sku_key = str(row["sku_key"] or "").strip()
        cogs_source = str(row["cogs_source"] or "")
        if cogs_source in {"fact_sales_fallback", "dim_sku_fallback"}:
            fallback_rows += 1
        elif cogs_source == "unresolved":
            unresolved_rows += 1
            if sku_key:
                unresolved_skus.add(sku_key)

    fin_by_day = {
        str(row["sale_date"]): {
            "cogs_kzt": round(float(row["cogs_kzt"] or 0.0), 2),
            "profit_kzt": round(float(row["profit_kzt"] or 0.0), 2),
        }
        for row in daily_fin_rows
    }
    for row in daily_line_rows:
        day = str(row["sale_date"])
        units_delivered = round(float(row["units_delivered"] or 0.0), 2)
        fin = fin_by_day.get(day)
        by_date[day] = {
            "units_delivered": units_delivered,
            # Backward-compatible alias used by legacy consumers/tests.
            "units_shipped": units_delivered,
            "net_rev_kzt": round(float(row["net_rev_kzt"] or 0.0), 2),
            "cogs_kzt": fin["cogs_kzt"] if fin is not None else None,
            "profit_kzt": fin["profit_kzt"] if fin is not None else None,
        }
    canonical_days = set(by_date.keys())

    fallback_revenue_days = 0
    if allow_completed_revenue_fallback:
        for row in fallback_completed_daily_rows:
            day = str(row["sale_date"] or "").strip()
            if not day or day in by_date:
                continue
            units_delivered = round(float(row["units_shipped"] or 0.0), 2)
            by_date[day] = {
                "units_delivered": units_delivered,
                # Backward-compatible alias used by legacy consumers/tests.
                "units_shipped": units_delivered,
                "net_rev_kzt": round(float(row["net_rev_kzt"] or 0.0), 2),
                "cogs_kzt": None,
                "profit_kzt": None,
            }
            fallback_revenue_days += 1

    archive_orders = {
        "status": "disabled",
        "reason": "disabled_by_default",
        "files": [],
        "days": {},
    }
    archive_override_days = 0
    if archive_orders_globs:
        archive_orders = _load_archive_orders_daily(
            as_of_date=as_of_date,
            start_date=start_30,
            archive_orders_globs=archive_orders_globs,
        )
    if archive_orders.get("status") == "available":
        for day, day_row in (archive_orders.get("days") or {}).items():
            if day in canonical_days:
                continue
            units_delivered = round(float(day_row.get("units_delivered") or 0.0), 2)
            by_date[day] = {
                "units_delivered": units_delivered,
                "units_shipped": units_delivered,
                "net_rev_kzt": round(float(day_row.get("net_rev_kzt") or 0.0), 2),
                "cogs_kzt": None,
                "profit_kzt": None,
            }
            archive_override_days += 1

    ads_by_date, ads_totals = _load_ads_daily(db_path, start_30, as_of_date)
    ads_available = ads_totals.get("status") == "available"
    for day, day_row in by_date.items():
        if ads_available:
            ads_cost = float(ads_by_date.get(day, 0.0))
            day_row["ads_spend_kzt"] = round(ads_cost, 2)
            if day_row["profit_kzt"] is None:
                day_row["profit_after_ads_kzt"] = None
            else:
                day_row["profit_after_ads_kzt"] = round(day_row["profit_kzt"] - ads_cost, 2)
        else:
            day_row["ads_spend_kzt"] = None
            day_row["profit_after_ads_kzt"] = None

    last_7_list: list[dict[str, Any]] = []
    for i in range(max(1, int(last_7_days))):
        day = (start_7 + timedelta(days=i)).isoformat()
        if day in by_date:
            item = {"date": day, **by_date[day]}
        else:
            item = {
                "date": day,
                "units_delivered": None,
                "units_shipped": None,
                "net_rev_kzt": None,
                "cogs_kzt": None,
                "profit_kzt": None,
                "ads_spend_kzt": round(float(ads_by_date.get(day, 0.0)), 2) if ads_available else None,
                "profit_after_ads_kzt": None,
            }
        last_7_list.append(item)

    observed_days_last_7_calendar = sum(
        1 for row in last_7_list if row["net_rev_kzt"] is not None
    )

    available_days_sorted = sorted(by_date.keys())
    latest_sale_date_available = available_days_sorted[-1] if available_days_sorted else None
    sales_truth_freshness_days = (
        (as_of_date - date.fromisoformat(latest_sale_date_available)).days
        if latest_sale_date_available
        else None
    )
    latest_7_observed_days: list[dict[str, Any]] = []
    for day in available_days_sorted[-7:]:
        latest_7_observed_days.append({"date": day, **by_date[day]})

    window_30_days = [
        (start_30 + timedelta(days=i)).isoformat() for i in range(max(1, int(last_30_days)))
    ]
    series_30_net = [by_date[d]["net_rev_kzt"] for d in window_30_days if d in by_date]
    series_30_cogs = [
        by_date[d]["cogs_kzt"]
        for d in window_30_days
        if d in by_date and by_date[d]["cogs_kzt"] is not None
    ]
    series_30_profit = [
        by_date[d]["profit_kzt"]
        for d in window_30_days
        if d in by_date and by_date[d]["profit_kzt"] is not None
    ]

    series_7_net = [r["net_rev_kzt"] for r in last_7_list if r["net_rev_kzt"] is not None]
    series_7_cogs = [r["cogs_kzt"] for r in last_7_list if r["cogs_kzt"] is not None]
    series_7_profit = [r["profit_kzt"] for r in last_7_list if r["profit_kzt"] is not None]
    series_30_ads = [
        by_date[d]["ads_spend_kzt"]
        for d in window_30_days
        if d in by_date and by_date[d]["ads_spend_kzt"] is not None
    ]
    series_30_profit_after_ads = [
        by_date[d]["profit_after_ads_kzt"]
        for d in window_30_days
        if d in by_date and by_date[d]["profit_after_ads_kzt"] is not None
    ]
    series_7_ads = [r["ads_spend_kzt"] for r in last_7_list if r["ads_spend_kzt"] is not None]
    series_7_profit_after_ads = [
        r["profit_after_ads_kzt"] for r in last_7_list if r["profit_after_ads_kzt"] is not None
    ]

    def _avg(values: list[float]) -> float:
        if not values:
            return 0.0
        return round(sum(values) / len(values), 2)

    def _avg_or_none(values: list[float]) -> float | None:
        if not values:
            return None
        return round(sum(values) / len(values), 2)

    selection_cache_path = waybill_selection_cache_path
    if (
        selection_cache_path.resolve() == DEFAULT_WAYBILL_SELECTION_CACHE.resolve()
        and db_path.resolve() != DEFAULT_DB.resolve()
    ):
        # Test/fixture DBs should use local sibling cache if present, otherwise fail-closed as missing.
        selection_cache_path = db_path.resolve().parent.parent / "excel_ui" / "ActiveOrders" / "waybills" / "_waybill_selection_orders.json"

    waybill_snapshot = load_waybill_selection_snapshot(
        db_path=db_path,
        as_of_date=as_of_date,
        selection_cache_path=selection_cache_path,
    )

    shipped_truth_effective = shipped_truth_root
    if shipped_truth_effective is not None:
        shipped_truth_effective = shipped_truth_effective.resolve()
        if (
            shipped_truth_effective == DEFAULT_SHIPPED_TRUTH_ROOT.resolve()
            and db_path.resolve() != DEFAULT_DB.resolve()
        ):
            shipped_truth_effective = None
    if shipped_truth_effective is not None:
        shipped_truth_snapshot = load_shipped_truth_snapshot(
            as_of_date=as_of_date,
            shipped_truth_root=shipped_truth_effective,
        )
        if shipped_truth_snapshot is not None:
            waybill_snapshot = shipped_truth_snapshot

    economics_volatility_days = max(0, int(os.environ.get("AB_ECONOMICS_VOLATILITY_DAYS", "14")))
    economics_missing_days: list[str] = []
    economics_missing_nonvolatile_days: list[str] = []
    for day in sorted(by_date.keys()):
        day_row = by_date[day]
        if day_row.get("net_rev_kzt") is None:
            continue
        if day_row.get("cogs_kzt") is not None and day_row.get("profit_kzt") is not None:
            continue
        economics_missing_days.append(day)
        try:
            lag_days = (as_of_date - date.fromisoformat(day)).days
        except ValueError:
            lag_days = economics_volatility_days + 1
        if lag_days > economics_volatility_days:
            economics_missing_nonvolatile_days.append(day)

    profit_publication_locked = unresolved_rows > 0 or len(economics_missing_days) > 0

    window_30_rows: list[dict[str, Any]] = []
    for day in window_30_days:
        if day in by_date:
            window_30_rows.append({"date": day, **by_date[day]})
        else:
            window_30_rows.append(
                {
                    "date": day,
                    "units_delivered": None,
                    "units_shipped": None,
                    "net_rev_kzt": None,
                    "cogs_kzt": None,
                    "profit_kzt": None,
                    "ads_spend_kzt": round(float(ads_by_date.get(day, 0.0)), 2) if ads_available else None,
                    "profit_after_ads_kzt": None,
                }
            )

    return {
        "as_of_date": as_of_date.isoformat(),
        "window_30_days": window_30_rows,
        "last_7_days": last_7_list,
        "latest_7_observed_days": latest_7_observed_days,
        "avg_30d_net_rev_kzt": _avg(series_30_net),
        "avg_30d_cogs_kzt": (None if profit_publication_locked else _avg(series_30_cogs)),
        "avg_30d_profit_kzt": (None if profit_publication_locked else _avg(series_30_profit)),
        "avg_30d_ads_spend_kzt": _avg_or_none(series_30_ads),
        "avg_30d_profit_after_ads_kzt": (
            None if profit_publication_locked else _avg_or_none(series_30_profit_after_ads)
        ),
        "avg_7d_net_rev_kzt": _avg(series_7_net),
        "avg_7d_cogs_kzt": (None if profit_publication_locked else _avg_or_none(series_7_cogs)),
        "avg_7d_profit_kzt": (None if profit_publication_locked else _avg_or_none(series_7_profit)),
        "avg_7d_ads_spend_kzt": _avg_or_none(series_7_ads),
        "avg_7d_profit_after_ads_kzt": (
            None if profit_publication_locked else _avg_or_none(series_7_profit_after_ads)
        ),
        "observed_days_last_7_calendar": observed_days_last_7_calendar,
        "latest_sale_date_available": latest_sale_date_available,
        "sales_truth_freshness_days": sales_truth_freshness_days,
        "revenue_fallback_days": fallback_revenue_days,
        "archive_orders_fallback_days": archive_override_days,
        "archive_orders": archive_orders,
        "fallback_rows": fallback_rows,
        "unresolved_rows": unresolved_rows,
        "unresolved_sku_count": len(unresolved_skus),
        "economics_volatility_days": economics_volatility_days,
        "economics_missing_days": economics_missing_days,
        "economics_missing_nonvolatile_days": economics_missing_nonvolatile_days,
        "total_rows": total_rows,
        "cogs_fallback_coverage_pct": round((fallback_rows / total_rows * 100.0), 2) if total_rows else 0.0,
        "profit_publication_locked": profit_publication_locked,
        "ads": ads_totals,
        "waybill_snapshot": waybill_snapshot,
    }


def _external_reference_check(
    *,
    external_sales_csv: Path | None,
    metrics: dict[str, Any],
) -> dict[str, Any]:
    if external_sales_csv is None:
        return {"status": "skipped", "reason": "no external csv provided"}
    if not external_sales_csv.exists():
        return {"status": "missing", "path": str(external_sales_csv)}

    try:
        df = pd.read_csv(external_sales_csv)
    except Exception as exc:
        return {"status": "error", "path": str(external_sales_csv), "error": str(exc)}

    needed = {"sale_date", "total_net_rev_kzt", "total_cogs_kzt"}
    if not needed.issubset(set(df.columns)):
        return {
            "status": "error",
            "path": str(external_sales_csv),
            "error": f"missing columns: {sorted(needed - set(df.columns))}",
        }

    grouped = (
        df.groupby("sale_date", dropna=True)[["total_net_rev_kzt", "total_cogs_kzt"]]
        .sum()
        .reset_index()
    )
    ext_map = {
        str(row["sale_date"]): (
            float(row["total_net_rev_kzt"] or 0.0),
            float(row["total_cogs_kzt"] or 0.0),
        )
        for _, row in grouped.iterrows()
    }
    local_map = {
        row["date"]: (float(row["net_rev_kzt"] or 0.0), float(row["cogs_kzt"] or 0.0))
        for row in metrics["last_7_days"]
        if row["net_rev_kzt"] is not None and row["cogs_kzt"] is not None
    }
    overlap = sorted(set(ext_map.keys()) & set(local_map.keys()))
    if not overlap:
        return {"status": "ok", "path": str(external_sales_csv), "matched_days": 0}

    max_net = 0.0
    max_cogs = 0.0
    for day in overlap:
        ext_net, ext_cogs = ext_map[day]
        loc_net, loc_cogs = local_map[day]
        max_net = max(max_net, abs(ext_net - loc_net))
        max_cogs = max(max_cogs, abs(ext_cogs - loc_cogs))
    return {
        "status": "ok",
        "path": str(external_sales_csv),
        "matched_days": len(overlap),
        "max_abs_diff_net_rev_kzt": round(max_net, 2),
        "max_abs_diff_cogs_kzt": round(max_cogs, 2),
    }


def _load_anchor_metadata(registry_path: Path) -> dict[str, Any]:
    try:
        payload = load_ocean_drop_anchor(registry_path)
    except OceanDropAnchorError as exc:
        return {
            "configured": False,
            "status": "missing",
            "reason": str(exc),
            "registry_path": str(Path(registry_path).resolve()),
        }

    return {
        "configured": True,
        "status": "locked",
        "reason": "ok",
        "registry_path": str(Path(registry_path).resolve()),
        "ocean_drop_path": str(payload.get("ocean_drop_path") or ""),
        "ocean_drop_path_resolved": str(payload.get("ocean_drop_path_resolved") or ""),
        "sha256": str(payload.get("sha256") or ""),
        "sha256_computed": str(payload.get("sha256_computed") or ""),
        "as_of_end": str(payload.get("as_of_end") or ""),
        "source": str(payload.get("source") or ""),
        "transaction_date_mode": str(payload.get("transaction_date_mode") or ""),
    }


def _run_ocean_drop_alignment_check(
    *,
    db_path: Path,
    as_of_date: date,
    anchor_registry_path: Path,
    output_root: Path,
    strict: bool,
    window_days: int | None,
) -> dict[str, Any]:
    anchor_meta = _load_anchor_metadata(anchor_registry_path)
    if not anchor_meta.get("configured"):
        return {
            "status": "skipped",
            "ok": not strict,
            "reason": "anchor_registry_missing",
            "details": anchor_meta,
        }

    from scripts.validate_sales_truth_ocean_drop_parity import validate_sales_truth_ocean_drop_parity

    ocean_drop_path = Path(anchor_meta["ocean_drop_path_resolved"])
    try:
        report = validate_sales_truth_ocean_drop_parity(
            db_path=db_path,
            as_of=as_of_date,
            ocean_drop_path=ocean_drop_path,
            output_root=output_root,
            volatility_days=14,
            strict=False,
            crm_archive_lookup_path=None,
            window_days=window_days,
        )
    except RuntimeError as exc:
        message = str(exc)
        if window_days and message == f"no reference rows in requested window_days={window_days}":
            snapshot_df, _meta = build_ocean_drop_snapshot_dataframe(
                ocean_drop_path=ocean_drop_path.resolve(),
                as_of=as_of_date,
                crm_archive_lookup_path=None,
                include_as_of_day=True,
                strict=True,
            )
            ref_df = snapshot_df[
                (snapshot_df["status_internal"] == "DELIVERED")
                & (snapshot_df["return_flag"] == 0)
            ].copy()
            ref_df["sale_date"] = ref_df["sale_date"].astype(str).str[:10]
            ref_min = str(ref_df["sale_date"].min()) if not ref_df.empty else None
            ref_max = str(ref_df["sale_date"].max()) if not ref_df.empty else None
            requested_start = (as_of_date - timedelta(days=window_days - 1)).isoformat()
            requested_end = as_of_date.isoformat()
            return {
                "status": "PASS_NO_OVERLAP",
                "ok": True,
                "reason": "no_reference_rows_in_requested_window",
                "reference_window_overlap": False,
                "requested_window_start": requested_start,
                "requested_window_end": requested_end,
                "reference_min_sale_date": ref_min,
                "reference_max_sale_date": ref_max,
                "details": {
                    "status": "PASS_NO_OVERLAP",
                    "ok": True,
                    "reason": "no_reference_rows_in_requested_window",
                    "requested_window_start": requested_start,
                    "requested_window_end": requested_end,
                    "reference_min_sale_date": ref_min,
                    "reference_max_sale_date": ref_max,
                },
            }
        raise
    status = str(report.get("status") or "FAIL").upper()
    parity_dir = output_root.resolve() / as_of_date.isoformat()
    return {
        "status": status,
        "ok": status == "PASS",
        "reason": "ok" if status == "PASS" else "parity_mismatch",
        "parity_report_json": str(parity_dir / "parity_report.json"),
        "parity_report_md": str(parity_dir / "parity_report.md"),
        "nonvolatile_mismatch_count": int(report.get("nonvolatile_mismatch_count") or 0),
        "volatile_mismatch_count": int(report.get("volatile_mismatch_count") or 0),
        "details": report,
    }


def _render_markdown(
    *,
    generated_at: datetime,
    as_of_date: str,
    capital: dict[str, Any],
    sales_metrics: dict[str, Any],
    ocean_drop_anchor: dict[str, Any],
    external_check: dict[str, Any],
) -> str:
    capital_rows = [
        ["Cash (actual, bank_accounts.yaml)", _fmt_kzt(capital["cash_actual_kzt"])],
        ["Inventory on-hand paid", _fmt_kzt(capital["inventory_on_hand_paid_kzt"])],
        ["Inventory inbound paid", _fmt_kzt(capital["inventory_inbound_paid_kzt"])],
        ["Inventory on-delivery paid", _fmt_kzt(capital["inventory_on_delivery_paid_kzt"])],
        ["Total capital (paid truth)", _fmt_kzt(capital["total_capital_paid_kzt"])],
        ["Inbound unpaid obligations", _fmt_kzt(capital["inbound_unpaid_obligations_kzt"])],
        [
            "Capital + unpaid inbound",
            _fmt_kzt(capital["total_capital_paid_kzt"] + capital["inbound_unpaid_obligations_kzt"]),
        ],
    ]
    observed_days_last_7 = int(sales_metrics.get("observed_days_last_7_calendar") or 0)
    latest_sale_date_available = sales_metrics.get("latest_sale_date_available")
    sales_truth_freshness_days = sales_metrics.get("sales_truth_freshness_days")
    freshness_status = "unknown"
    if sales_truth_freshness_days is not None:
        freshness_status = "fresh" if int(sales_truth_freshness_days) <= 2 else "stale"

    perf_rows = [
        ["Avg 30d Net Rev", _fmt_kzt(sales_metrics["avg_30d_net_rev_kzt"])],
        ["Avg 30d COGS", _fmt_kzt(sales_metrics["avg_30d_cogs_kzt"])],
        ["Avg 30d Profit", _fmt_kzt(sales_metrics["avg_30d_profit_kzt"])],
        ["Avg 30d Ads Spend", _fmt_kzt(sales_metrics["avg_30d_ads_spend_kzt"])],
        ["Avg 30d Profit After Ads", _fmt_kzt(sales_metrics["avg_30d_profit_after_ads_kzt"])],
        ["Avg 7d Net Rev", _fmt_kzt(sales_metrics["avg_7d_net_rev_kzt"] if observed_days_last_7 > 0 else None)],
        ["Avg 7d COGS", _fmt_kzt(sales_metrics["avg_7d_cogs_kzt"] if observed_days_last_7 > 0 else None)],
        ["Avg 7d Profit", _fmt_kzt(sales_metrics["avg_7d_profit_kzt"] if observed_days_last_7 > 0 else None)],
        ["Avg 7d Ads Spend", _fmt_kzt(sales_metrics["avg_7d_ads_spend_kzt"] if observed_days_last_7 > 0 else None)],
        [
            "Avg 7d Profit After Ads",
            _fmt_kzt(sales_metrics["avg_7d_profit_after_ads_kzt"] if observed_days_last_7 > 0 else None),
        ],
    ]
    daily_rows = [
        [
            row["date"],
            str(int(round(float(row.get("units_delivered")))))
            if row.get("units_delivered") is not None
            else "N/A",
            _fmt_kzt(row["net_rev_kzt"]),
            _fmt_kzt(row["cogs_kzt"]),
            _fmt_kzt(row["ads_spend_kzt"]),
            _fmt_kzt(row["profit_kzt"]),
            _fmt_kzt(row["profit_after_ads_kzt"]),
        ]
        for row in sales_metrics["last_7_days"]
    ]
    observed_rows = [
        [
            row["date"],
            str(int(round(float(row.get("units_delivered")))))
            if row.get("units_delivered") is not None
            else "N/A",
            _fmt_kzt(row["net_rev_kzt"]),
            _fmt_kzt(row["cogs_kzt"]),
            _fmt_kzt(row["ads_spend_kzt"]),
            _fmt_kzt(row["profit_kzt"]),
            _fmt_kzt(row["profit_after_ads_kzt"]),
        ]
        for row in sales_metrics.get("latest_7_observed_days") or []
    ]
    waybill_snapshot = sales_metrics.get("waybill_snapshot") or {}
    waybill_status = str(waybill_snapshot.get("status") or "missing")
    waybill_stores = waybill_snapshot.get("stores") or {}
    waybill_rows: list[list[str]] = []
    for store_code in sorted(waybill_stores.keys()):
        store_row = waybill_stores[store_code] or {}
        waybill_rows.append(
            [
                store_code,
                str(int(store_row.get("orders") or 0)),
                str(int(round(float(store_row.get("units") or 0.0)))),
            ]
        )
    if waybill_rows:
        waybill_totals = waybill_snapshot.get("totals") or {}
        waybill_rows.append(
            [
                "TOTAL",
                str(int(waybill_totals.get("orders") or 0)),
                str(int(round(float(waybill_totals.get("units") or 0.0)))),
            ]
        )
    ads_coverage_raw = sales_metrics["ads"].get("mapping_coverage_pct")
    ads_coverage_text = (
        "N/A" if ads_coverage_raw is None else f"{float(ads_coverage_raw):.2f}%"
    )
    revenue_fallback_days = int(sales_metrics.get("revenue_fallback_days") or 0)
    archive_orders_fallback_days = int(sales_metrics.get("archive_orders_fallback_days") or 0)
    archive_orders_meta = sales_metrics.get("archive_orders") or {}
    sales_source_line = (
        "view_sales_line_truth / view_sales_daily_truth "
        "(canonical interface over staging)"
    )
    if revenue_fallback_days > 0:
        sales_source_line += (
            " + fact_orders_kaspi COMPLETED revenue-only fallback "
            f"(days added: {revenue_fallback_days})"
        )
    if archive_orders_fallback_days > 0:
        sales_source_line += (
            " + ArchiveOrders delivered-status fallback "
            f"(days overlaid: {archive_orders_fallback_days})"
        )

    lines = [
        "# Business Insides Snapshot",
        "",
        f"- Generated at: `{generated_at.strftime('%Y-%m-%d %H:%M:%S')}`",
        f"- As of date: `{as_of_date}`",
        f"- Paid-capital snapshot date: `{capital.get('snapshot_date')}`",
        f"- Bank snapshot date: `{capital.get('bank_as_of_date')}`",
        "",
        "## Capital Snapshot (KZT)",
        "",
        "```text",
        _ascii_table(["Metric", "Value KZT"], capital_rows),
        "```",
        "",
        "## Performance Metrics (KZT)",
        "",
        "```text",
        _ascii_table(["Metric", "Value KZT"], perf_rows),
        "```",
        "",
        "## Last 7 Days Values (KZT)",
        "",
        "```text",
        _ascii_table(
            ["Date", "Units Delivered (COMPLETED)", "Net Rev", "COGS", "Ads Spend", "Profit", "Profit After Ads"],
            daily_rows,
        ),
        "```",
        "",
        "## Sales Truth Freshness",
        "",
        f"- Latest observed sale date (truth): `{latest_sale_date_available or 'N/A'}`",
        f"- Freshness lag (days): `{sales_truth_freshness_days if sales_truth_freshness_days is not None else 'N/A'}`",
        f"- Freshness status: `{freshness_status}`",
        f"- Observed rows in last 7 calendar days: `{observed_days_last_7}`",
    ]
    if observed_days_last_7 == 0:
        lines.extend(
            [
                "- Sales truth is stale for recent 7-day calendar window.",
                "",
            ]
        )
    else:
        lines.append("")

    lines.extend(
        [
            "## Latest Observed Sales Days (Truth)",
            "",
            "```text",
            _ascii_table(
                ["Date", "Units Delivered (COMPLETED)", "Net Rev", "COGS", "Ads Spend", "Profit", "Profit After Ads"],
                observed_rows or [["N/A", "N/A", "N/A", "N/A", "N/A", "N/A", "N/A"]],
            ),
            "```",
            "",
            "## Waybill-State Shipment Snapshot",
            "",
            f"- Snapshot status: `{waybill_status}`",
            f"- Cache file: `{waybill_snapshot.get('cache_path')}`",
            f"- Target date in cache: `{waybill_snapshot.get('target_date') or 'N/A'}`",
            f"- Include overdue: `{waybill_snapshot.get('include_overdue')}`",
            f"- Mode all_dates: `{waybill_snapshot.get('all_dates')}`",
        ]
    )
    if waybill_rows:
        lines.extend(
            [
                "",
                "```text",
                _ascii_table(
                    ["Store", "Orders Shipped (Waybill Selection)", "Units Shipped (DB qty)"],
                    waybill_rows,
                ),
                "```",
                "",
            ]
        )
    else:
        lines.extend(
            [
                "- Waybill cache is unavailable for this as_of day; shipment metrics are not decision-grade.",
                "",
            ]
        )

    lines.extend(
        [
        "## Ocean Drop Provenance",
        "",
        f"- Anchor configured: `{str(bool(ocean_drop_anchor.get('configured'))).lower()}`",
        f"- Anchor registry: `{ocean_drop_anchor.get('registry_path')}`",
        f"- Anchor path: `{ocean_drop_anchor.get('ocean_drop_path_resolved') or ocean_drop_anchor.get('ocean_drop_path') or 'N/A'}`",
        f"- Anchor sha256: `{ocean_drop_anchor.get('sha256') or 'N/A'}` "
        f"(computed: `{ocean_drop_anchor.get('sha256_computed') or 'N/A'}`)",
        f"- Anchor as_of_end: `{ocean_drop_anchor.get('as_of_end') or 'N/A'}`",
        f"- Transaction date mode: `{ocean_drop_anchor.get('transaction_date_mode') or 'N/A'}`",
        f"- Anchor source tag: `{ocean_drop_anchor.get('source') or 'N/A'}`",
        "",
        "## Data Quality",
        "",
        f"- Sales source: `{sales_source_line}`.",
        "- Metric definition: `Units Delivered (COMPLETED)` come from canonical sales truth views.",
        "- Metric definition: `Orders/Units Shipped (Waybill Selection)` come from waybill selection cache + DB quantities.",
        f"- COGS fallback rows: `{sales_metrics['fallback_rows']}/{sales_metrics['total_rows']}` "
        f"({sales_metrics['cogs_fallback_coverage_pct']:.2f}%).",
        f"- Unresolved COGS rows: `{sales_metrics['unresolved_rows']}`.",
        f"- Unresolved SKU count: `{sales_metrics['unresolved_sku_count']}`.",
        f"- Economics volatility window (days): `{sales_metrics['economics_volatility_days']}`.",
        f"- Economics missing days (COGS/profit): `{len(sales_metrics['economics_missing_days'])}` "
        f"({', '.join(sales_metrics['economics_missing_days'][:7]) or 'none'}).",
        f"- Economics missing nonvolatile days: `{len(sales_metrics['economics_missing_nonvolatile_days'])}` "
        f"({', '.join(sales_metrics['economics_missing_nonvolatile_days'][:7]) or 'none'}).",
        f"- Profit publication locked: `{str(bool(sales_metrics['profit_publication_locked'])).lower()}`.",
        f"- Ads source status: `{sales_metrics['ads'].get('status')}` "
        f"(reason: `{sales_metrics['ads'].get('reason')}`).",
        f"- Ads mapping coverage: `{ads_coverage_text}`.",
        f"- Ads mapped/unmapped cost: `{_fmt_kzt(sales_metrics['ads'].get('mapped_cost_kzt'))}` / "
        f"`{_fmt_kzt(sales_metrics['ads'].get('unmapped_cost_kzt'))}`.",
        f"- ArchiveOrders source status: `{archive_orders_meta.get('status')}` "
        f"(reason: `{archive_orders_meta.get('reason')}`).",
        f"- ArchiveOrders files used: `{len(archive_orders_meta.get('files') or [])}`.",
        "",
        "## External Reference Check",
        "",
        f"- Status: `{external_check.get('status')}`",
        f"- Details: `{external_check}`",
        "",
        ]
    )
    return "\n".join(lines) + "\n"


def generate_business_insides(
    *,
    db_path: Path = DEFAULT_DB,
    bank_accounts_path: Path = DEFAULT_BANK,
    as_of: str | date | None = None,
    output_dir: Path = DEFAULT_OUTPUT_DIR,
    external_sales_csv: Path | None = None,
    strict_cogs: bool = False,
    strict: bool = False,
    decision_grade: bool = False,
    ocean_drop_anchor_registry: Path = DEFAULT_OCEAN_DROP_ANCHOR_REGISTRY,
    bi_alignment_output_root: Path = DEFAULT_BI_ALIGNMENT_OUTPUT_ROOT,
    bi_alignment_window_days: int | None = DEFAULT_BI_ALIGNMENT_WINDOW_DAYS,
    waybill_selection_cache_path: Path = DEFAULT_WAYBILL_SELECTION_CACHE,
    shipped_truth_root: Path | None = DEFAULT_SHIPPED_TRUTH_ROOT,
    archive_orders_globs: list[str] | None = None,
) -> dict[str, Any]:
    as_of_date = _parse_as_of(as_of)
    strict_alignment = bool(strict or decision_grade)
    generated_at = datetime.now()
    capital = compute_paid_capital_truth(
        db_path=db_path,
        bank_accounts_path=bank_accounts_path,
        as_of=as_of_date,
    )
    sales_metrics = compute_sales_metrics(
        db_path=db_path,
        as_of=as_of_date,
        enforce_query_guard=bool(strict_cogs),
        allow_completed_revenue_fallback=not strict_alignment,
        waybill_selection_cache_path=waybill_selection_cache_path,
        shipped_truth_root=shipped_truth_root,
        archive_orders_globs=archive_orders_globs,
    )
    if strict_cogs and int(sales_metrics["unresolved_rows"]) > 0:
        raise RuntimeError(
            "Unresolved COGS rows detected in requested window: "
            f"rows={sales_metrics['unresolved_rows']}, "
            f"sku_count={sales_metrics['unresolved_sku_count']}"
        )
    ocean_drop_anchor = _load_anchor_metadata(ocean_drop_anchor_registry)
    if strict_alignment and not ocean_drop_anchor.get("configured"):
        raise RuntimeError(
            "Strict BUSINESS_INSIDES run requires locked ocean-drop anchor registry. "
            f"reason={ocean_drop_anchor.get('reason')}"
        )
    if strict_alignment:
        external_check = _run_ocean_drop_alignment_check(
            db_path=db_path,
            as_of_date=as_of_date,
            anchor_registry_path=ocean_drop_anchor_registry,
            output_root=bi_alignment_output_root,
            strict=strict_alignment,
            window_days=bi_alignment_window_days,
        )
        ext_status = str(external_check.get("status") or "").upper()
        ext_ok = bool(external_check.get("ok", ext_status == "PASS"))
        if not ext_ok or ext_status in {"SKIPPED", "MISSING", "ERROR", "FAIL"}:
            raise RuntimeError(
                "Strict BUSINESS_INSIDES alignment failed: "
                f"status={external_check.get('status')} details={external_check}"
            )
    else:
        external_check = _external_reference_check(
            external_sales_csv=external_sales_csv,
            metrics=sales_metrics,
        )
        if ocean_drop_anchor.get("configured") and external_check.get("status") == "skipped":
            external_check = {
                "status": "skipped",
                "reason": "strict_not_requested",
                "anchor_configured": True,
                "anchor_registry": ocean_drop_anchor.get("registry_path"),
            }

    output_dir.mkdir(parents=True, exist_ok=True)
    snapshots_dir = output_dir / "snapshots"
    snapshots_dir.mkdir(parents=True, exist_ok=True)

    snapshot_name = f"BUSINESS_INSIDES_{as_of_date.isoformat()}.md"
    snapshot_path = snapshots_dir / snapshot_name
    latest_path = output_dir / snapshot_name
    snapshot_json_name = f"BUSINESS_INSIDES_{as_of_date.isoformat()}.json"
    snapshot_json_path = snapshots_dir / snapshot_json_name
    latest_json_path = output_dir / snapshot_json_name
    content = _render_markdown(
        generated_at=generated_at,
        as_of_date=as_of_date.isoformat(),
        capital=capital,
        sales_metrics=sales_metrics,
        ocean_drop_anchor=ocean_drop_anchor,
        external_check=external_check,
    )
    snapshot_path.write_text(content, encoding="utf-8")
    latest_path.write_text(content, encoding="utf-8")
    payload = {
        "generated_at": generated_at.replace(microsecond=0).isoformat(),
        "as_of": as_of_date.isoformat(),
        "capital": capital,
        "performance": {
            "avg_30d_net_rev_kzt": sales_metrics["avg_30d_net_rev_kzt"],
            "avg_30d_cogs_kzt": sales_metrics["avg_30d_cogs_kzt"],
            "avg_30d_profit_kzt": sales_metrics["avg_30d_profit_kzt"],
            "avg_30d_ads_spend_kzt": sales_metrics["avg_30d_ads_spend_kzt"],
            "avg_30d_profit_after_ads_kzt": sales_metrics["avg_30d_profit_after_ads_kzt"],
            "avg_7d_net_rev_kzt": sales_metrics["avg_7d_net_rev_kzt"],
            "avg_7d_cogs_kzt": sales_metrics["avg_7d_cogs_kzt"],
            "avg_7d_profit_kzt": sales_metrics["avg_7d_profit_kzt"],
            "avg_7d_ads_spend_kzt": sales_metrics["avg_7d_ads_spend_kzt"],
            "avg_7d_profit_after_ads_kzt": sales_metrics["avg_7d_profit_after_ads_kzt"],
            "observed_days_last_7_calendar": sales_metrics["observed_days_last_7_calendar"],
            "latest_sale_date_available": sales_metrics["latest_sale_date_available"],
            "sales_truth_freshness_days": sales_metrics["sales_truth_freshness_days"],
        },
        "last_7_days": sales_metrics["last_7_days"],
        "window_30_days": sales_metrics["window_30_days"],
        "latest_7_observed_days": sales_metrics["latest_7_observed_days"],
        "fallback_rows": sales_metrics["fallback_rows"],
        "total_rows": sales_metrics["total_rows"],
        "unresolved_rows": sales_metrics["unresolved_rows"],
        "unresolved_sku_count": sales_metrics["unresolved_sku_count"],
        "economics_volatility_days": sales_metrics["economics_volatility_days"],
        "economics_missing_days": sales_metrics["economics_missing_days"],
        "economics_missing_nonvolatile_days": sales_metrics["economics_missing_nonvolatile_days"],
        "profit_publication_locked": sales_metrics["profit_publication_locked"],
        "ads": sales_metrics["ads"],
        "waybill_snapshot": sales_metrics.get("waybill_snapshot"),
        "archive_orders": sales_metrics.get("archive_orders"),
        "ocean_drop_anchor": ocean_drop_anchor,
        "external_check": external_check,
    }
    payload_json = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
    snapshot_json_path.write_text(payload_json, encoding="utf-8")
    latest_json_path.write_text(payload_json, encoding="utf-8")

    return {
        "as_of_date": as_of_date.isoformat(),
        "snapshot_path": str(snapshot_path),
        "latest_path": str(latest_path),
        "snapshot_json_path": str(snapshot_json_path),
        "latest_json_path": str(latest_json_path),
        "capital": capital,
        "performance": payload["performance"],
        "last_7_days": sales_metrics["last_7_days"],
        "window_30_days": sales_metrics["window_30_days"],
        "latest_7_observed_days": sales_metrics["latest_7_observed_days"],
        "fallback_rows": sales_metrics["fallback_rows"],
        "total_rows": sales_metrics["total_rows"],
        "unresolved_rows": sales_metrics["unresolved_rows"],
        "unresolved_sku_count": sales_metrics["unresolved_sku_count"],
        "economics_volatility_days": sales_metrics["economics_volatility_days"],
        "economics_missing_days": sales_metrics["economics_missing_days"],
        "economics_missing_nonvolatile_days": sales_metrics["economics_missing_nonvolatile_days"],
        "profit_publication_locked": sales_metrics["profit_publication_locked"],
        "ads": sales_metrics["ads"],
        "waybill_snapshot": sales_metrics.get("waybill_snapshot"),
        "archive_orders": sales_metrics.get("archive_orders"),
        "ocean_drop_anchor": ocean_drop_anchor,
        "external_check": external_check,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate business insides snapshot markdown")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument("--bank-accounts", type=Path, default=DEFAULT_BANK)
    parser.add_argument("--as-of", type=str, default=None)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--external-sales-csv", type=Path, default=None)
    parser.add_argument("--strict-cogs", action="store_true")
    parser.add_argument("--strict", action="store_true", help="Fail-closed decision-grade mode")
    parser.add_argument(
        "--decision-grade",
        action="store_true",
        help="Alias for --strict (kept for clarity in ops docs)",
    )
    parser.add_argument("--ocean-drop-anchor-registry", type=Path, default=DEFAULT_OCEAN_DROP_ANCHOR_REGISTRY)
    parser.add_argument(
        "--bi-alignment-output-root",
        type=Path,
        default=DEFAULT_BI_ALIGNMENT_OUTPUT_ROOT,
    )
    parser.add_argument("--bi-alignment-window-days", type=int, default=DEFAULT_BI_ALIGNMENT_WINDOW_DAYS)
    parser.add_argument("--waybill-selection-cache", type=Path, default=DEFAULT_WAYBILL_SELECTION_CACHE)
    parser.add_argument("--shipped-truth-root", type=Path, default=DEFAULT_SHIPPED_TRUTH_ROOT)
    parser.add_argument(
        "--archive-orders-glob",
        action="append",
        default=None,
        help=(
            "Glob pattern(s) for ArchiveOrders XLSX files used as delivered-date fallback. "
            "Repeat flag to provide multiple patterns."
        ),
    )
    args = parser.parse_args()

    result = generate_business_insides(
        db_path=args.db,
        bank_accounts_path=args.bank_accounts,
        as_of=args.as_of,
        output_dir=args.output_dir,
        external_sales_csv=args.external_sales_csv,
        strict_cogs=args.strict_cogs,
        strict=args.strict,
        decision_grade=args.decision_grade,
        ocean_drop_anchor_registry=args.ocean_drop_anchor_registry,
        bi_alignment_output_root=args.bi_alignment_output_root,
        bi_alignment_window_days=args.bi_alignment_window_days,
        waybill_selection_cache_path=args.waybill_selection_cache,
        shipped_truth_root=args.shipped_truth_root,
        archive_orders_globs=args.archive_orders_glob,
    )
    def _fmt_metric(value: Any) -> str:
        if value is None:
            return "N/A"
        return f"{float(value):.2f}"

    print(f"snapshot_path={result['snapshot_path']}")
    print(f"snapshot_json_path={result['snapshot_json_path']}")
    print(f"latest_path={result['latest_path']}")
    print(f"latest_json_path={result['latest_json_path']}")
    print(f"avg_7d_net_rev_kzt={_fmt_metric(result['performance']['avg_7d_net_rev_kzt'])}")
    print(f"avg_7d_profit_kzt={_fmt_metric(result['performance']['avg_7d_profit_kzt'])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
