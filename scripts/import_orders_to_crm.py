#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Phase 11: Import Kaspi ActiveOrders to CRM (xlwings version)

Uses xlwings to write to Excel, preserving formulas and external links.
Based on legacy ~/Docs/kaspi_etl/docs/ops/kaspi/import_active_orders.py

Usage:
    python scripts/import_orders_to_crm.py --verbose
    python scripts/import_orders_to_crm.py --dry-run
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import sys
from dataclasses import dataclass
from datetime import datetime, date, timedelta
from pathlib import Path
from typing import Any, Dict, List, Tuple, Optional
from zoneinfo import ZoneInfo

import pandas as pd
from dateutil import parser as dtp
from dotenv import load_dotenv

# xlwings for Excel-safe writing (optional at import time)
try:
    import xlwings as xw
except ModuleNotFoundError:  # pragma: no cover - environment-specific
    xw = None

# openpyxl only for reading (inspection)
from openpyxl import load_workbook
from openpyxl.utils.cell import coordinate_from_string, column_index_from_string

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from core.integrations.kaspi_api_client import KaspiAPIClient, KaspiAuthError, STORE_TOKEN_MAP
from core.integrations.kaspi_order_stage import (
    classify_kaspi_order_stage,
    kaspi_order_to_russian_status,
    stage_to_crm_indicators,
)
from core.parsers.kaspi_parser import extract_sku_from_article
from core.utils.sku_map import extract_kaspi_name_core
from core.utils.kaspi_dates import planned_date_from_order
from core.db import get_db

ALMATY_TZ = ZoneInfo("Asia/Almaty")

# Warehouse → Store code (for API lookup)
WAREHOUSE_STORE_MAP = {
    '30000001_PP1': 'UNIVERSAL',
    '30137883_PP1': 'ACMEWEAR',
    '30290083_PP1': '11KZ',
    '30000002_PP1': 'STOREB',
    '30000002_PP1 ': 'STOREB',
    '30362323_PP1': 'MELVIS',
}

from core.paths import data_path, get_data_root


# ---------- CRM Backup ----------

def backup_crm(crm_path: Path) -> Path:
    """
    Create timestamped backup of CRM file before import.

    Stores backups in excel_ui/backups/, keeps last 7 days.

    Returns:
        Path to backup file
    """
    backup_dir = crm_path.parent / "backups"
    backup_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = backup_dir / f"CRM_backup_{timestamp}.xlsx"

    # Create backup
    shutil.copy2(crm_path, backup_path)

    # Cleanup: keep last 7 days only
    cutoff = datetime.now() - timedelta(days=7)
    for old_backup in backup_dir.glob("CRM_backup_*.xlsx"):
        try:
            # Parse timestamp from filename: CRM_backup_YYYYMMDD_HHMMSS.xlsx
            ts_str = old_backup.stem.replace("CRM_backup_", "")
            ts = datetime.strptime(ts_str, "%Y%m%d_%H%M%S")
            if ts < cutoff:
                old_backup.unlink()
        except (ValueError, OSError):
            pass  # Skip files that don't match pattern

    return backup_path


# ---------- Configuration ----------

STORE_MAP = {
    '30137883_PP1': 'AcmeWear',
    '30000001_PP1': 'Universal',
    '30290083_PP1': '11KZ',
    '30000002_PP1': 'STORE-B',
    '30362323_PP1': 'Store-C',
}

DEFAULT_STATUS = 'Ожидает передачи курьеру'
DEFAULT_SIGNATURE = 'Не требуется'

# Public constants used by tests (legacy aliases)
READY_STATUS = DEFAULT_STATUS
NO_SIGNATURE = DEFAULT_SIGNATURE

# Raw Kaspi column mapping (Y-AZ)
RAW_KASPI_COLUMNS = {
    "№ заказа": "Y",
    "Статус": "Z",
    "Дата изменения статуса": "AA",
    "Требуется подписание": "AB",
    "Плановая дата передачи курьеру": "AC",
    "Название товара в Kaspi Магазине": "AD",
    "Название в системе продавца": "AE",
    "Артикул": "AF",
    "Склад передачи КД": "AG",
    "Телефон": "AH",
    "Количество": "AI",
    "Цена": "AJ",
    "Сумма": "AK",
    "Адрес доставки": "AL",
    "ФИО": "AM",
    "Комментарий": "AN",
    "Способ доставки": "AO",
    "Дата создания": "AP",
    "Код товара": "AQ",
    "Kaspi_Offer_ID": "AR",
    "SKU_key": "AS",
    "SKU_ID": "AT",
    "MY_SIZE": "AU",
    "STORE_NAME": "AV",
    "KASPI_NAME_CORE": "AW",
    "Warehouse": "AX",
    "Seller_name": "AY",
    "Internal_Status": "AZ",
}

PROTECTED_HUMAN_COLUMNS = {
    "MY_SIZE",
}


def _allow_openpyxl_backfill_fallback() -> bool:
    """
    Openpyxl saves can rewrite workbook package internals on complex files.
    Keep this fallback disabled unless explicitly enabled via env.
    """
    raw = os.getenv("CRM_FIXED_BACKFILL_OPENPYXL_FALLBACK", "")
    return str(raw).strip().lower() in {"1", "true", "yes", "on"}


def _excel_automation_preflight(crm_path: Path, strict_excel: bool = True, verbose: bool = False) -> None:
    """
    Validate that Excel automation can safely control the workbook before writes.
    In strict mode this aborts early instead of attempting risky fallbacks.
    """
    if not strict_excel:
        return
    if xw is None:
        raise RuntimeError("xlwings is required for strict Excel mode.")
    lock_file = crm_path.parent / f"~${crm_path.name}"
    if lock_file.exists():
        age_seconds = datetime.now().timestamp() - lock_file.stat().st_mtime
        if age_seconds < 30 * 60:
            raise RuntimeError(
                f"Excel lock file detected ({lock_file.name}). Close workbook and retry."
            )
        if verbose:
            print(
                "  WARNING: stale Excel lock file detected; ignoring "
                f"({lock_file.name}, age={int(age_seconds)}s)"
            )

    app = xw.App(visible=False, add_book=False)
    app.display_alerts = False
    app.screen_updating = False
    try:
        wb = app.books.open(str(crm_path), update_links=False, read_only=True)
        wb.close()
        if verbose:
            print("  Strict Excel preflight OK")
    except Exception as exc:
        raise RuntimeError(
            "Excel automation preflight failed (macOS Automation/Excel state issue). "
            "Grant python automation access to Excel and close all open workbook sessions."
        ) from exc
    finally:
        app.quit()


LINE61_CANONICAL_SKU_KEY = "CL_NEW-CLO2_MEN_SUIT-61_BLACK"
LINE61_CANONICAL_CORE = "6в1_Черный_+Сумка"

FIXED_APPEND_COLUMNS = [
    "STORE_NAME",
    "Quantity",
    "Kaspi_name_core",
    "KASPI_OFFER_NAME",
    "SKU_key",
    "Sell_price_kzt",
    "Total_price",
    "Total_net_rev",
    "MODEL",
    "PLANNED_SHIPPING_DATE",
    "Product_Type",
    "Delivery_fee_kzt",
    "Total_weight",
    "SKU_ID_KSP",
    "Kaspi_name_source",
]

# For recent backfill we use the same set and still avoid human-owned columns.
FIXED_BACKFILL_COLUMNS = list(FIXED_APPEND_COLUMNS)

# Canonical header mapping
CANON = {
    "order_id": ["№заказа", "номерзаказа", "orderid", "заказа"],  # заказа is normalized from "№ заказа"
    "status": ["статус"],
    "status_change_date": ["датаизменениястатуса"],  # Phase 12 Part 6: status change timestamp
    "signature": ["требуетсяподписание"],
    "handover": ["плановаядатапередачикурьеру", "плановаядатапередачи"],
    "offer_name": ["названиетоваравkaspiмагазине"],
    "seller_name": ["названиевсистемепродавца"],
    "sku": ["артикул"],
    "warehouse": ["складпередачикд", "складпередачикурьерскойдоставки"],
    "phone": ["телефон", "phone", "cellphone"],
    "quantity": ["количество", "qty", "quantity"],
}


# ---------- Helpers ----------

def norm(s: str) -> str:
    """Normalize header for matching (lowercase, no punct, cyrillic-friendly)."""
    if s is None:
        return ""
    s = str(s).strip().lower()
    s = re.sub(r"\s+", " ", s)
    s = s.replace("ё", "е")
    s = re.sub(r"[^\w\s]", "", s)
    s = re.sub(r"\s", "", s)
    return s


def normalize_article_code(value: str) -> str:
    text = str(value or "").strip()
    if not text:
        return text
    return re.sub(r"^[\d\s]+", "", text).strip()


def map_headers(df: pd.DataFrame) -> Dict[str, str]:
    """Return dict canonical_key -> actual df column name."""
    colmap = {}
    cols_norm = {norm(c): c for c in df.columns}
    for k, variants in CANON.items():
        for v in variants:
            v_norm = norm(v)
            if v_norm in cols_norm:
                colmap[k] = cols_norm[v_norm]
                break
    return colmap


def _to_float(value: Any, default: float = 0.0) -> float:
    if value is None:
        return default
    if isinstance(value, str):
        raw = value.strip().replace(" ", "")
        if not raw:
            return default
        raw = raw.replace(",", ".")
    else:
        raw = value
    try:
        return float(raw)
    except (TypeError, ValueError):
        return default


def _to_int(value: Any, default: int = 0) -> int:
    try:
        return int(round(_to_float(value, float(default))))
    except (TypeError, ValueError):
        return default


def _norm_key_text(value: Any) -> str:
    text = str(value or "").strip().lower()
    text = re.sub(r"\s+", " ", text)
    return text


def _build_line_dedupe_key(
    order_id: Optional[str],
    planned_date: Optional[date],
    offer_name: Any,
    article: Any,
    quantity: Any,
) -> str:
    clean_order = clean_order_id(order_id) or ""
    planned_iso = planned_date.isoformat() if planned_date else ""
    offer_key = _norm_key_text(offer_name)
    article_key = _norm_key_text(article)
    quantity_key = str(_to_int(quantity, 0))
    return f"{clean_order}|{planned_iso}|{article_key}|{offer_key}|{quantity_key}"


def _load_article_identity_for_articles(articles: List[str]) -> Dict[str, Dict[str, str]]:
    clean_articles = sorted(
        {
            str(a).strip()
            for a in articles
            for a in (a, normalize_article_code(a))
            if str(a).strip()
        }
    )
    if not clean_articles:
        return {}
    mapped: Dict[str, Dict[str, str]] = {}
    chunk_size = 800
    with get_db() as conn:
        if not conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='dim_kaspi_article_map'"
        ).fetchone():
            return {}
        for i in range(0, len(clean_articles), chunk_size):
            batch = clean_articles[i : i + chunk_size]
            placeholders = ",".join("?" for _ in batch)
            rows = conn.execute(
                f"""
                SELECT kaspi_article, sku_key, sku_id, kaspi_name_core
                FROM dim_kaspi_article_map
                WHERE active_flag = 1
                  AND kaspi_article IN ({placeholders})
                ORDER BY updated_at DESC
                """,
                batch,
            ).fetchall()
            for row in rows:
                article = str(row["kaspi_article"] or "").strip()
                if not article or article in mapped:
                    continue
                mapped[article] = {
                    "sku_key": str(row["sku_key"] or "").strip(),
                    "sku_id": str(row["sku_id"] or "").strip(),
                    "kaspi_name_core": str(row["kaspi_name_core"] or "").strip(),
                }
    return mapped


def _derive_identity_from_raw_row(
    raw_row: Dict[str, Any],
    article_identity_by_article: Optional[Dict[str, Dict[str, str]]] = None,
    valid_sku_keys: Optional[set[str]] = None,
) -> Dict[str, Optional[str]]:
    article_raw = str(
        raw_row.get("Артикул")
        or raw_row.get("SKU_ID_KSP")
        or raw_row.get("Kaspi_article")
        or ""
    ).strip()
    article = normalize_article_code(article_raw) or article_raw
    offer_name = str(
        raw_row.get("Название товара в Kaspi Магазине")
        or raw_row.get("KASPI_OFFER_NAME")
        or raw_row.get("Kaspi_offer")
        or ""
    ).strip()
    sku_key = str(raw_row.get("SKU_key") or "").strip() or None
    my_size = str(raw_row.get("MY_SIZE") or "").strip() or None
    product_type = str(raw_row.get("Product_Type") or "").strip() or None

    article_identity = (
        (article_identity_by_article or {}).get(article_raw)
        or (article_identity_by_article or {}).get(article)
        or (article_identity_by_article or {}).get(article.upper())
        or {}
    )
    if valid_sku_keys and sku_key and sku_key not in valid_sku_keys:
        sku_key = None
        my_size = None

    parsed = extract_sku_from_article(article, offer_name)
    parsed_sku_key = parsed.get("sku_key")
    parsed_my_size = parsed.get("my_size")
    parsed_product_type = parsed.get("product_type")
    if valid_sku_keys and parsed_sku_key and parsed_sku_key not in valid_sku_keys:
        parsed_sku_key = None
        parsed_my_size = None

    # Prefer deterministic article parser output first; DB article map is fallback
    # for legacy/unparseable article strings.
    if not sku_key and parsed_sku_key:
        sku_key = parsed_sku_key
    if not my_size and parsed_my_size:
        my_size = parsed_my_size
    if not product_type and parsed_product_type:
        product_type = parsed_product_type

    mapped_sku_key = str(article_identity.get("sku_key") or "").strip() or None
    mapped_sku_id = str(article_identity.get("sku_id") or "").strip() or None
    if mapped_sku_key and (not valid_sku_keys or mapped_sku_key in valid_sku_keys):
        if not sku_key:
            sku_key = mapped_sku_key
        if not my_size and mapped_sku_id and "_" in mapped_sku_id:
            my_size = mapped_sku_id.rsplit("_", 1)[-1]

    if sku_key and my_size:
        if not product_type and "_" in sku_key:
            product_type = sku_key.split("_", 1)[0]
        return {"sku_key": sku_key, "my_size": my_size, "product_type": product_type}

    if not sku_key:
        sku_key = parsed_sku_key
    if not my_size:
        my_size = parsed_my_size
    if not product_type:
        product_type = parsed_product_type
    if not product_type and sku_key and "_" in sku_key:
        product_type = sku_key.split("_", 1)[0]
    return {"sku_key": sku_key, "my_size": my_size, "product_type": product_type}


def _load_sku_meta_for_keys(sku_keys: List[str]) -> Tuple[Dict[str, Dict[str, Any]], Dict[str, str], set[str]]:
    clean_keys = sorted({str(k).strip() for k in sku_keys if str(k).strip()})
    sku_meta: Dict[str, Dict[str, Any]] = {}
    kaspi_core: Dict[str, str] = {}
    valid_sku_keys: set[str] = set()

    with get_db() as conn:
        if clean_keys:
            placeholders = ",".join("?" for _ in clean_keys)
            rows = conn.execute(
                f"""
                SELECT sku_key, model, product_type, weight_kg
                FROM dim_sku
                WHERE sku_key IN ({placeholders})
                """,
                clean_keys,
            ).fetchall()
        else:
            rows = []
        for row in rows:
            sku_meta[row["sku_key"]] = {
                "model": row["model"],
                "product_type": row["product_type"],
                "weight_kg": row["weight_kg"],
            }
            valid_sku_keys.add(row["sku_key"])

        if conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='dim_kaspi_article_map'"
        ).fetchone() and clean_keys:
            placeholders = ",".join("?" for _ in clean_keys)
            core_rows = conn.execute(
                f"""
                SELECT sku_key, kaspi_name_core
                FROM dim_kaspi_article_map
                WHERE active_flag = 1
                  AND kaspi_name_core IS NOT NULL
                  AND TRIM(kaspi_name_core) <> ''
                  AND sku_key IN ({placeholders})
                ORDER BY updated_at DESC
                """,
                clean_keys,
            ).fetchall()
            for row in core_rows:
                if row["sku_key"] not in kaspi_core:
                    kaspi_core[row["sku_key"]] = str(row["kaspi_name_core"]).strip()

    return sku_meta, kaspi_core, valid_sku_keys


def compute_fixed_value_columns(
    raw_row: Dict[str, Any],
    sku_meta_by_key: Optional[Dict[str, Dict[str, Any]]] = None,
    kaspi_core_by_key: Optional[Dict[str, str]] = None,
    article_identity_by_article: Optional[Dict[str, Dict[str, str]]] = None,
    valid_sku_keys: Optional[set[str]] = None,
) -> Dict[str, Any]:
    """
    Compute trivial formula columns as fixed values.

    SKU_ID is intentionally excluded; it stays formula-driven in workbook.
    """
    sku_meta_by_key = sku_meta_by_key or {}
    kaspi_core_by_key = kaspi_core_by_key or {}
    identity = _derive_identity_from_raw_row(
        raw_row,
        article_identity_by_article=article_identity_by_article,
        valid_sku_keys=valid_sku_keys,
    )
    sku_key = identity.get("sku_key") or ""
    my_size = identity.get("my_size") or ""
    sku_meta = sku_meta_by_key.get(sku_key, {})

    quantity = _to_int(raw_row.get("Количество", raw_row.get("Quantity", 0)), 0)
    total_price = _to_float(raw_row.get("Сумма", raw_row.get("Total_price", 0.0)), 0.0)
    sell_price = (total_price / quantity) if quantity else 0.0

    delivery_fee = _to_float(raw_row.get("Стоимость доставки для продавца"), 0.0)
    # Mirror current workbook formula semantics: fixed 12.5% commission and 3% VAT.
    total_net_rev = ((total_price * (1 - 0.125)) - delivery_fee) * (1 - 0.03)

    warehouse = str(raw_row.get("Склад передачи КД") or "").strip()
    store_name = STORE_MAP.get(warehouse, "")

    model = str(sku_meta.get("model") or "").strip()
    product_type = str(identity.get("product_type") or sku_meta.get("product_type") or "").strip()
    weight_kg = _to_float(sku_meta.get("weight_kg"), 0.0)
    total_weight = weight_kg * quantity

    offer_name = str(
        raw_row.get("Название товара в Kaspi Магазине")
        or raw_row.get("KASPI_OFFER_NAME")
        or ""
    ).strip()
    article = str(
        raw_row.get("Артикул")
        or raw_row.get("SKU_ID_KSP")
        or raw_row.get("Kaspi_article")
        or ""
    ).strip()
    article_identity = (article_identity_by_article or {}).get(article) or {}
    mapped_core = str(article_identity.get("kaspi_name_core") or "").strip()
    kaspi_name_core = mapped_core or kaspi_core_by_key.get(sku_key) or extract_kaspi_name_core(offer_name)
    if sku_key == LINE61_CANONICAL_SKU_KEY or article.upper().startswith("OF_SUIT-61_BLK_"):
        kaspi_name_core = LINE61_CANONICAL_CORE

    return {
        "STORE_NAME": store_name,
        "Quantity": quantity,
        "Kaspi_name_core": kaspi_name_core,
        "KASPI_OFFER_NAME": offer_name,
        "SKU_key": sku_key,
        "MY_SIZE": my_size,
        "Sell_price_kzt": sell_price,
        "Total_price": total_price,
        "Total_net_rev": total_net_rev,
        "MODEL": model,
        "PLANNED_SHIPPING_DATE": raw_row.get("Плановая дата передачи курьеру"),
        "Product_Type": product_type,
        "Delivery_fee_kzt": delivery_fee,
        "Total_weight": total_weight,
        "SKU_ID_KSP": str(raw_row.get("Артикул") or "").strip(),
        "Kaspi_name_source": str(raw_row.get("Название в системе продавца") or "").strip(),
    }


def _row_in_backfill_window(
    row_date: Optional[date],
    date_from: Optional[date],
    date_to: Optional[date],
) -> bool:
    if not row_date or not date_from or not date_to:
        return False
    return date_from <= row_date <= date_to


def _resolve_backfill_window(
    days: int,
    date_from: Optional[date],
    date_to: Optional[date],
) -> Tuple[Optional[date], Optional[date]]:
    if days <= 0 and not date_from and not date_to:
        return (None, None)
    if not date_from and not date_to:
        date_to = today_local()
        date_from = date_to - timedelta(days=max(days - 1, 0))
    elif date_from and not date_to:
        date_to = date_from
    elif date_to and not date_from:
        date_from = date_to
    if not date_from or not date_to:
        return (None, None)
    if date_from > date_to:
        raise ValueError(f"fixed-value backfill date range invalid: {date_from} > {date_to}")
    return (date_from, date_to)


def build_fixed_value_payload(df_filt: pd.DataFrame) -> List[Dict[str, Any]]:
    rows = df_filt.to_dict(orient="records")
    articles = [str(r.get("Артикул") or r.get("SKU_ID_KSP") or "").strip() for r in rows]
    article_identity = _load_article_identity_for_articles(articles)
    identities = [
        _derive_identity_from_raw_row(
            r,
            article_identity_by_article=article_identity,
        )
        for r in rows
    ]
    sku_keys = [x.get("sku_key") for x in identities if x.get("sku_key")]
    sku_meta, kaspi_core, valid_sku_keys = _load_sku_meta_for_keys([str(k) for k in sku_keys])
    return [
        compute_fixed_value_columns(
            row,
            sku_meta,
            kaspi_core,
            article_identity_by_article=article_identity,
            valid_sku_keys=valid_sku_keys,
        )
        for row in rows
    ]


def parse_kz_date(v) -> Optional[date]:
    """Parse various date formats from Kaspi exports."""
    if pd.isna(v):
        return None
    s = str(v).strip()
    try:
        d = dtp.parse(s, dayfirst=True, yearfirst=False).date()
        return d
    except Exception:
        try:
            if isinstance(v, pd.Timestamp):
                return v.date()
        except Exception:
            pass
        return None


def today_local() -> date:
    return datetime.now().date()


def _resolve_refresh_date(value: Optional[str], default_date: date) -> date:
    if not value:
        return default_date
    v = str(value).strip().lower()
    if v == "today":
        return today_local()
    if v == "yesterday":
        return today_local() - timedelta(days=1)
    if v == "tomorrow":
        return today_local() + timedelta(days=1)
    parsed = parse_date(v)
    if parsed is None:
        raise ValueError(f"Invalid refresh date: {value}")
    return parsed


def backfill_seller_delivery_fee(
    crm_path: Path,
    sheet_name: str,
    table_name: str,
    date_from: date,
    date_to: date,
    dry_run: bool = False,
    verbose: bool = False,
    snapshot: Optional[CRMSnapshot] = None,
) -> int:
    """
    Backfill seller delivery fee from Delivery_fee_kzt for rows in date range.

    Sets 'Стоимость доставки для продавца' when it is blank/0 but Delivery_fee_kzt is present.
    Returns number of rows updated.
    """
    updates: list[tuple[int, float]] = []
    seller_col = None

    if snapshot and snapshot.delivery_fee_rows and snapshot.seller_fee_col:
        seller_col = snapshot.seller_fee_col
        for row_num, parsed_date, seller_num, fee_num in snapshot.delivery_fee_rows:
            if not parsed_date:
                continue
            if parsed_date < date_from or parsed_date > date_to:
                continue
            if seller_num == 0.0 and fee_num != 0.0:
                updates.append((row_num, fee_num))
    else:
        wb = load_workbook(filename=str(crm_path), read_only=False, data_only=True)
        try:
            ws = wb[sheet_name]
            table = _resolve_table(ws, table_name)
            start_col, start_row, end_col, end_row = _table_bounds(table)

            header_row = list(ws.iter_rows(min_row=start_row, max_row=start_row,
                                           min_col=start_col, max_col=end_col))[0]
            col_map: Dict[str, int] = {}
            for i, cell in enumerate(header_row):
                header = str(cell.value or "").strip()
                if header:
                    col_map[header] = start_col + i

            date_col = col_map.get("Date") or col_map.get("Дата поступления заказа")
            fee_col = col_map.get("Delivery_fee_kzt") or col_map.get("Delivery_fee")
            seller_col = col_map.get("Стоимость доставки для продавца")

            if not date_col or not fee_col or not seller_col:
                if verbose:
                    print("  Delivery fee backfill skipped: required columns not found")
                return 0

            for row_num in range(start_row + 1, end_row + 1):
                row_date = ws.cell(row=row_num, column=date_col).value
                parsed_date = parse_date(row_date)
                if not parsed_date:
                    continue
                if parsed_date < date_from or parsed_date > date_to:
                    continue

                seller_val = ws.cell(row=row_num, column=seller_col).value
                fee_val = ws.cell(row=row_num, column=fee_col).value

                try:
                    seller_num = float(seller_val) if seller_val not in (None, "") else 0.0
                except (TypeError, ValueError):
                    seller_num = 0.0
                try:
                    fee_num = float(fee_val) if fee_val not in (None, "") else 0.0
                except (TypeError, ValueError):
                    fee_num = 0.0

                if seller_num == 0.0 and fee_num != 0.0:
                    updates.append((row_num, fee_num))
        finally:
            wb.close()

    if verbose:
        print(f"  Delivery fee backfill candidates: {len(updates)} rows")

    if dry_run or not updates or seller_col is None:
        return len(updates)

    _require_xlwings()
    app = xw.App(visible=False, add_book=False)
    try:
        book = app.books.open(str(crm_path))
        sheet = book.sheets[sheet_name]
        for row_num, value in updates:
            sheet.cells(row_num, seller_col).value = value
        book.save()
        book.close()
    finally:
        app.quit()

    return len(updates)


# ---------- Legacy helpers (for tests/backward compatibility) ----------

def parse_date(v) -> Optional[date]:
    """Parse dates from CRM/Kaspi exports (supports Excel serials)."""
    if pd.isna(v):
        return None
    if isinstance(v, date) and not isinstance(v, datetime):
        return v
    if isinstance(v, datetime):
        return v.date()
    if isinstance(v, str):
        s = v.strip()
        if len(s) == 10 and s[4] == "-" and s[7] == "-":
            return datetime.strptime(s, "%Y-%m-%d").date()
    if isinstance(v, (int, float)) and 40000 <= float(v) <= 60000:
        base = datetime(1899, 12, 30)
        return (base + timedelta(days=int(float(v)))).date()
    try:
        return dtp.parse(str(v).strip(), dayfirst=True).date()
    except Exception:
        if isinstance(v, pd.Timestamp):
            return v.date()
        return None


def clean_value(v):
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return None
    s = str(v).strip()
    return s if s else None


def clean_order_id(v) -> Optional[str]:
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return None
    if isinstance(v, float) and v.is_integer():
        v = int(v)
    s = str(v).strip()
    if s.endswith(".0"):
        s = s[:-2]
    if not s.isdigit():
        return None
    if len(s) < 9 or len(s) > 12:
        return None
    return s


def _timestamp_to_ddmmyyyy(ts_ms: Optional[int]) -> Optional[str]:
    """Convert milliseconds timestamp to DD.MM.YYYY (Asia/Almaty)."""
    if not ts_ms:
        return None
    try:
        dt = datetime.fromtimestamp(ts_ms / 1000, tz=ALMATY_TZ)
        return dt.strftime('%d.%m.%Y')
    except Exception:
        return None


def _extract_delivery_costs(order: dict) -> tuple[Optional[float], Optional[float]]:
    attrs = order.get('attributes', {}) if isinstance(order, dict) else {}
    delivery = attrs.get('kaspiDelivery', {}) if isinstance(attrs.get('kaspiDelivery', {}), dict) else {}
    buyer_cost = delivery.get('customerDeliveryCost')
    if buyer_cost is None:
        buyer_cost = attrs.get('deliveryCost')
    seller_cost = attrs.get('deliveryCostForSeller')
    if seller_cost is None:
        seller_cost = delivery.get('deliveryCostForSeller')
    return buyer_cost, seller_cost


def _order_to_update_fields(order: dict) -> Dict[str, object]:
    attrs = order.get('attributes', {})
    delivery = attrs.get('kaspiDelivery', {})
    stage = classify_kaspi_order_stage(order)
    russian_status = kaspi_order_to_russian_status(order)
    indicators = stage_to_crm_indicators(stage)
    planned_date_obj = planned_date_from_order(order)
    planned_date = planned_date_obj.strftime('%d.%m.%Y') if planned_date_obj else None
    status_change_date = _timestamp_to_ddmmyyyy(attrs.get('statusChangeDate'))
    buyer_cost, seller_cost = _extract_delivery_costs(order)
    comp = delivery.get('deliveryCostCompensation', 0)

    data = {
        'Статус': russian_status,
        'Дата изменения статуса': status_change_date,
        'Принял': indicators['Принял'],
        'Выдал': indicators['Выдал'],
        'Отменил': indicators['Отменил'],
        'Плановая дата передачи курьеру': planned_date,
        'Стоимость доставки для покупателя': buyer_cost,
        'Стоимость доставки для продавца': seller_cost,
        'Компенсация за доставку': comp,
    }
    return {k: v for k, v in data.items() if v is not None}


def read_crm_pending_orders(
    crm_path: Path,
    sheet_name: str,
    target_date: date,
) -> List[Dict[str, Optional[str]]]:
    """Read CRM pending orders (planned date == target_date, status READY)."""
    header_df = pd.read_excel(crm_path, sheet_name=sheet_name, nrows=0)
    cols = header_df.columns.tolist()

    order_col = None
    for name in ("OrderID", "№ заказа"):
        if name in cols:
            order_col = name
            break
    status_col = "Статус" if "Статус" in cols else None
    planned_cols = []
    for name in ("PLANNED_SHIPPING_DATE", "Плановая дата передачи курьеру"):
        if name in cols:
            planned_cols.append(name)
    warehouse_col = None
    for name in ("Склад передачи КД", "Warehouse"):
        if name in cols:
            warehouse_col = name
            break

    if not order_col or not status_col or not planned_cols:
        return []

    usecols = [order_col, status_col] + planned_cols
    if warehouse_col:
        usecols.append(warehouse_col)

    df = pd.read_excel(crm_path, sheet_name=sheet_name, usecols=usecols)

    pending = []
    for _, row in df.iterrows():
        order_id = clean_order_id(row.get(order_col))
        if not order_id:
            continue
        planned = None
        for pcol in planned_cols:
            planned = parse_date(row.get(pcol))
            if planned:
                break
        if planned != target_date:
            continue
        status = str(row.get(status_col) or "").strip()
        if status != READY_STATUS:
            continue
        warehouse = str(row.get(warehouse_col) or "").strip() if warehouse_col else ""
        store_code = WAREHOUSE_STORE_MAP.get(warehouse)
        pending.append({"order_id": order_id, "store_code": store_code})

    return pending


def fetch_missing_status_updates(
    missing_orders: List[Dict[str, Optional[str]]],
    verbose: bool = False,
) -> Dict[str, Dict[str, object]]:
    """Fetch current statuses for missing orders via API (by order code)."""
    if not missing_orders:
        return {}

    load_dotenv()
    clients: Dict[str, KaspiAPIClient] = {}
    updates: Dict[str, Dict[str, object]] = {}

    for item in missing_orders:
        order_id = item.get("order_id")
        if not order_id:
            continue
        preferred_store = item.get("store_code")
        stores = [preferred_store] if preferred_store else list(STORE_TOKEN_MAP.keys())

        for store_code in stores:
            if not store_code:
                continue
            try:
                client = clients.get(store_code)
                if client is None:
                    client = KaspiAPIClient(store_code=store_code)
                    clients[store_code] = client
            except KaspiAuthError as e:
                if verbose:
                    print(f"  Skipping {store_code}: {e}")
                continue

            resp = client.get_order(order_id)
            if not resp.success or not resp.data:
                continue

            data = resp.data
            if isinstance(data, dict) and data.get('type') != 'orders':
                if 'data' in data and isinstance(data['data'], list) and data['data']:
                    data = data['data'][0]
            if isinstance(data, dict) and data.get('type') == 'orders':
                updates[order_id] = _order_to_update_fields(data)
                break

        if order_id not in updates and verbose:
            print(f"  WARN: order {order_id} not found via API")

    return updates


def summarize_order_rows(df: pd.DataFrame) -> Dict[str, int]:
    """
    Summarize orders vs rows for a filtered dataframe.

    Returns dict with keys: rows, unique_orders, multi_line_orders, max_lines_per_order
    """
    colmap = map_headers(df)
    order_col = colmap.get("order_id")
    if not order_col:
        return {}

    order_ids = df[order_col].apply(clean_order_id).dropna()
    if order_ids.empty:
        return {
            "rows": int(len(df)),
            "unique_orders": 0,
            "multi_line_orders": 0,
            "max_lines_per_order": 0,
        }

    counts = order_ids.value_counts()
    multi_line = int((counts > 1).sum())
    max_lines = int(counts.max()) if not counts.empty else 0
    return {
        "rows": int(len(df)),
        "unique_orders": int(counts.size),
        "multi_line_orders": multi_line,
        "max_lines_per_order": max_lines,
    }


def find_active_orders_files(orders_dir: Path) -> List[Path]:
    return find_active_orders(orders_dir)


def parse_orders_from_excel(orders_dir: Path) -> List[dict]:
    df, _ = read_active_orders(orders_dir)
    return df.to_dict(orient="records")


def load_existing_order_ids(crm_path: Path, sheet_name: str) -> set:
    wb = load_workbook(filename=str(crm_path), read_only=True, data_only=True)
    try:
        ws = wb[sheet_name]
        header = [c.value for c in next(ws.iter_rows(min_row=1, max_row=1))]
        order_col = None
        for idx, val in enumerate(header, start=1):
            if norm(val) in {"№заказа", "номерзаказа", "заказа"}:
                order_col = idx
                break
        if order_col is None:
            return set()
        order_ids = set()
        for row in ws.iter_rows(min_row=2, min_col=order_col, max_col=order_col):
            val = row[0].value
            cleaned = clean_order_id(val)
            if cleaned:
                order_ids.add(cleaned)
        return order_ids
    finally:
        wb.close()


def deduplicate_orders(orders: List[dict], existing_ids: set) -> Tuple[List[dict], int]:
    new_orders = []
    skipped = 0
    for order in orders:
        order_id = order.get("_order_id") or order.get("order_id")
        if order_id in existing_ids:
            skipped += 1
            continue
        new_orders.append(order)
    return new_orders, skipped


def filter_orders_for_shipment(orders: List[dict], target_date: date) -> List[dict]:
    filtered = []
    for order in orders:
        status = str(order.get("Статус", "")).strip()
        signature = str(order.get("Требуется подписание", "")).strip()
        planned = parse_date(order.get("Плановая дата передачи курьеру"))
        if status != READY_STATUS:
            continue
        if signature and signature != NO_SIGNATURE:
            continue
        if planned and planned != target_date:
            continue
        filtered.append(order)
    return filtered


# ---------- Read & Filter ActiveOrders ----------

def find_active_orders(orders_dir: Path) -> List[Path]:
    """Find all ActiveOrders*.xlsx files in directory."""
    files = sorted([
        p for p in orders_dir.glob("*.xlsx")
        if p.is_file()
        and "ActiveOrders" in p.name
        and not p.name.startswith("~$")
    ])
    return files


def read_active_orders(orders_dir: Path) -> Tuple[pd.DataFrame, List[Path]]:
    """Read all ActiveOrders files and concat."""
    files = find_active_orders(orders_dir)
    if not files:
        raise SystemExit(f"No .xlsx files found in {orders_dir}")
    
    frames = []
    for p in files:
        try:
            df = pd.read_excel(p, engine="openpyxl")
            df["__source_file__"] = p.name
            frames.append(df)
            print(f"  Read {p.name}: {len(df)} rows")
        except Exception as e:
            print(f"  WARN: cannot read {p.name}: {e}")
    
    if not frames:
        raise SystemExit("No valid Excel files found")
    
    return pd.concat(frames, ignore_index=True), files


def filter_for_shipping(
    df: pd.DataFrame, 
    status_wanted: str, 
    signature_wanted: Optional[str], 
    end_date: date
) -> Tuple[pd.DataFrame, Dict]:
    """Filter orders for shipping readiness."""
    colmap = map_headers(df)
    
    ok = pd.Series([True] * len(df))
    
    # Status filter
    if "status" in colmap:
        ok &= (df[colmap["status"]].astype(str).str.strip() == status_wanted)
    
    # Signature filter (exclude "Да" / "Требуется")
    if signature_wanted and "signature" in colmap:
        sig_col = df[colmap["signature"]].astype(str).str.strip().str.lower()
        ok &= ~sig_col.isin(['да', 'yes', 'true', '1', 'требуется'])
    
    # Date filter: planned_date == end_date (exact match for TODAY only)
    # Phase 12 Part 3: Changed from <= to == for TODAY-only filtering
    if "handover" in colmap:
        handover = df[colmap["handover"]].apply(parse_kz_date)
        ok &= handover.apply(lambda d: d is not None and d == end_date)
    
    df_filtered = df[ok].copy()
    
    stats = {
        "files_seen": len(df["__source_file__"].unique()) if "__source_file__" in df else 0,
        "rows_in_files": int(len(df)),
        "rows_after_filters": int(len(df_filtered)),
        "target_end_date": end_date.isoformat(),
    }
    
    return df_filtered, stats


def sort_for_crm(df: pd.DataFrame) -> pd.DataFrame:
    """
    Sort dataframe for CRM append order.

    Sort order (Phase 12 Part 6 - Updated):
    1. Status (cancelled/returned on top) - problematic orders first
    2. STORE_NAME / warehouse (ascending) - group by store for visual clarity
    3. OrderID (ascending) - group same orders together
    4. Quantity (ascending) - single items first
    5. KASPI_OFFER_NAME / offer_name (ascending) - alphabetical by product
    6. Date / handover (ascending) - oldest first

    This sort order groups orders by store for easier visual scanning.
    """
    colmap = map_headers(df)

    sort_cols = []
    sort_ascending = []

    # 1. Status column - cancelled/returned first (0 = top, 1 = bottom)
    if "status" in colmap:
        df = df.copy()  # Avoid SettingWithCopyWarning
        df["_status_sort"] = df[colmap["status"]].apply(
            lambda x: 0 if str(x).lower() in ['отменен', 'возвращен', 'cancelled', 'returned', 'cancelling', 'returning'] else 1
        )
        sort_cols.append("_status_sort")
        sort_ascending.append(True)

    # 2. STORE_NAME / warehouse (ascending) - group by store first
    if "warehouse" in colmap:
        sort_cols.append(colmap["warehouse"])
        sort_ascending.append(True)

    # 3. OrderID (ascending)
    if "order_id" in colmap:
        sort_cols.append(colmap["order_id"])
        sort_ascending.append(True)

    # 4. Quantity (ascending)
    if "quantity" in colmap:
        sort_cols.append(colmap["quantity"])
        sort_ascending.append(True)

    # 5. KASPI_OFFER_NAME / offer_name (ascending)
    if "offer_name" in colmap:
        sort_cols.append(colmap["offer_name"])
        sort_ascending.append(True)

    # 6. Date / handover (ascending)
    if "handover" in colmap:
        sort_cols.append(colmap["handover"])
        sort_ascending.append(True)

    if sort_cols:
        df_sorted = df.sort_values(by=sort_cols, ascending=sort_ascending, na_position='last')
        # Drop helper column
        if "_status_sort" in df_sorted.columns:
            df_sorted = df_sorted.drop(columns=["_status_sort"])
        return df_sorted.reset_index(drop=True)

    return df


# ---------- CRM Inspection (openpyxl read-only) ----------

def inspect_crm_sheet(
    crm_path: Path,
    sheet_name: str,
    table_name: str
) -> Tuple[int, Optional[int], int, int, List[str]]:
    """
    Inspect CRM to find column positions.

    CRM structure:
    - Column B (2): Date - we write here
    - Column I (9): Phone - we write here (Phase 12)
    - Columns A-X: Formula columns (auto-calculate)
    - Columns Y-AZ (25-52): Raw Kaspi data - we write here

    Returns: (date_col, phone_col, start_col, end_col, slice_headers)
    """
    wb = load_workbook(filename=str(crm_path), read_only=True, data_only=True)
    if sheet_name not in wb.sheetnames:
        raise SystemExit(f'Sheet "{sheet_name}" not found in {crm_path}')

    ws = wb[sheet_name]
    header_vals = [c.value if c.value is not None else "" for c in next(ws.iter_rows(min_row=1, max_row=1))]

    idx_date = None
    idx_phone = None  # Phone column (column I)
    idx_start = None  # Raw Kaspi start (№ заказа in column Y)
    idx_end = None    # Raw Kaspi end (Склад передачи КД in column AZ)

    for i, h in enumerate(header_vals, start=1):
        hnorm = norm(h)
        if idx_date is None and hnorm in {"date", "дата"}:
            idx_date = i
        # Phone column (column I in CRM)
        if idx_phone is None and hnorm in {"phone", "телефон", "cellphone"}:
            idx_phone = i
        # Look for raw Kaspi columns (Russian headers starting at Y)
        # Note: "№ заказа" normalizes to "заказа" (№ symbol stripped)
        if idx_start is None and hnorm in {"№заказа", "номерзаказа", "заказа"}:
            idx_start = i
        if hnorm in {"складпередачикд", "складпередачикурьерскойдоставки"}:
            idx_end = i  # Keep updating to get the last one

    if idx_date is None:
        raise SystemExit(f"Could not find 'Date' column. Headers: {header_vals[:10]}...")

    if idx_start is None or idx_end is None or idx_end < idx_start:
        raise SystemExit(
            f"Could not locate raw Kaspi columns (Y-AZ). Need '№ заказа' and 'Склад передачи КД'. "
            f"Headers at positions 25-30: {header_vals[24:30] if len(header_vals) >= 30 else 'N/A'}"
        )

    slice_headers = [header_vals[j-1] for j in range(idx_start, idx_end + 1)]
    wb.close()

    print(f"  Date column: {idx_date} (B)")
    if idx_phone:
        print(f"  Phone column: {idx_phone} (I)")
    else:
        print(f"  Phone column: not found (will skip phone import)")
    print(f"  Raw Kaspi columns: {idx_start}-{idx_end} (Y-AZ)")

    return idx_date, idx_phone, idx_start, idx_end, slice_headers


def _resolve_table(ws, table_name: str):
    """Find table in worksheet."""
    tables = ws.tables
    if table_name in tables:
        return tables[table_name]
    if tables:
        return next(iter(tables.values()))
    raise RuntimeError(f"No tables found on sheet {ws.title}")


def _table_bounds(table) -> Tuple[int, int, int, int]:
    """Get table bounds: (start_col, start_row, end_col, end_row)."""
    start_ref, end_ref = table.ref.split(':')
    start_col_letters, start_row = coordinate_from_string(start_ref)
    end_col_letters, end_row = coordinate_from_string(end_ref)
    start_col = column_index_from_string(start_col_letters)
    end_col = column_index_from_string(end_col_letters)
    return start_col, start_row, end_col, end_row


@dataclass
class CRMSnapshot:
    date_col: int
    phone_col: Optional[int]
    start_col: int
    end_col: int
    start_row: int
    end_row: int
    slice_headers: list[str]
    order_ids: set[str]
    order_rows: Dict[str, int]
    existing_keys: set[str]
    column_positions: Dict[str, int]
    planned_col_abs: Optional[int]
    table_date_col: Optional[int]
    delivery_fee_col: Optional[int]
    seller_fee_col: Optional[int]
    delivery_fee_rows: list[tuple[int, Optional[date], float, float]]


def load_crm_snapshot(crm_path: Path, sheet_name: str, table_name: str) -> CRMSnapshot:
    """Load CRM metadata in a single openpyxl session (read-only snapshot)."""
    wb = load_workbook(filename=str(crm_path), read_only=False, data_only=True)
    try:
        if sheet_name not in wb.sheetnames:
            raise SystemExit(f'Sheet "{sheet_name}" not found in {crm_path}')

        ws = wb[sheet_name]
        header_vals = [c.value if c.value is not None else "" for c in next(ws.iter_rows(min_row=1, max_row=1))]

        idx_date = None
        idx_phone = None
        idx_start = None
        idx_end = None

        for i, h in enumerate(header_vals, start=1):
            hnorm = norm(h)
            if idx_date is None and hnorm in {"date", "дата"}:
                idx_date = i
            if idx_phone is None and hnorm in {"phone", "телефон", "cellphone"}:
                idx_phone = i
            if idx_start is None and hnorm in {"№заказа", "номерзаказа", "заказа"}:
                idx_start = i
            if hnorm in {"складпередачикд", "складпередачикурьерскойдоставки"}:
                idx_end = i

        if idx_date is None:
            raise SystemExit(f"Could not find 'Date' column. Headers: {header_vals[:10]}...")

        if idx_start is None or idx_end is None or idx_end < idx_start:
            raise SystemExit(
                "Could not locate raw Kaspi columns (Y-AZ). Need '№ заказа' and 'Склад передачи КД'."
            )

        slice_headers = [header_vals[j - 1] for j in range(idx_start, idx_end + 1)]

        table = _resolve_table(ws, table_name)
        start_col, start_row, end_col, end_row = _table_bounds(table)

        target_columns = {
            'Статус': None,
            'Дата изменения статуса': None,
            'Принял': None,
            'Выдал': None,
            'Отменил': None,
            'Плановая дата передачи курьеру': None,
            'Стоимость доставки для покупателя': None,
            'Стоимость доставки для продавца': None,
            'Компенсация за доставку': None,
        }

        header_row = list(
            ws.iter_rows(min_row=1, max_row=1, min_col=idx_start, max_col=idx_end)
        )[0]
        for i, cell in enumerate(header_row):
            header = str(cell.value or '').strip()
            if header in target_columns:
                target_columns[header] = idx_start + i

        planned_col_abs = target_columns.get("Плановая дата передачи курьеру")

        order_ids: set[str] = set()
        order_rows: Dict[str, int] = {}
        existing_keys: set[str] = set()
        delivery_fee_rows: list[tuple[int, Optional[date], float, float]] = []

        planned_in_table = (
            planned_col_abs is not None
            and start_col <= planned_col_abs <= end_col
        )

        table_header = list(
            ws.iter_rows(min_row=start_row, max_row=start_row, min_col=start_col, max_col=end_col)
        )[0]
        table_map: Dict[str, int] = {}
        for i, cell in enumerate(table_header):
            header = str(cell.value or "").strip()
            if header:
                table_map[header] = start_col + i

        table_date_col = table_map.get("Date") or table_map.get("Дата поступления заказа")
        delivery_fee_col = table_map.get("Delivery_fee_kzt") or table_map.get("Delivery_fee")
        seller_fee_col = table_map.get("Стоимость доставки для продавца")
        offer_col_abs = table_map.get("Название товара в Kaspi Магазине")
        article_col_abs = table_map.get("Артикул")
        quantity_col_abs = table_map.get("Количество")

        for row_num in range(start_row + 1, end_row + 1):
            order_val = ws.cell(row=row_num, column=idx_start).value
            if order_val in (None, ""):
                continue
            if isinstance(order_val, str) and order_val.startswith("="):
                continue
            if isinstance(order_val, float):
                order_val = int(order_val)
            order_id = str(order_val).strip()
            if not order_id:
                continue
            order_ids.add(order_id)
            order_rows[order_id] = row_num

            cleaned = clean_order_id(order_val)
            if not cleaned:
                continue

            planned_date = None
            if planned_in_table:
                planned_val = ws.cell(row=row_num, column=planned_col_abs).value
                planned_date = parse_date(planned_val)

            offer_val = ws.cell(row=row_num, column=offer_col_abs).value if offer_col_abs else ""
            article_val = ws.cell(row=row_num, column=article_col_abs).value if article_col_abs else ""
            qty_val = ws.cell(row=row_num, column=quantity_col_abs).value if quantity_col_abs else 0
            key = _build_line_dedupe_key(
                cleaned,
                planned_date,
                offer_val,
                article_val,
                qty_val,
            )
            existing_keys.add(key)

            if table_date_col and delivery_fee_col and seller_fee_col:
                row_date = ws.cell(row=row_num, column=table_date_col).value
                parsed_date = parse_date(row_date)
                seller_val = ws.cell(row=row_num, column=seller_fee_col).value
                fee_val = ws.cell(row=row_num, column=delivery_fee_col).value
                try:
                    seller_num = float(seller_val) if seller_val not in (None, "") else 0.0
                except (TypeError, ValueError):
                    seller_num = 0.0
                try:
                    fee_num = float(fee_val) if fee_val not in (None, "") else 0.0
                except (TypeError, ValueError):
                    fee_num = 0.0
                delivery_fee_rows.append((row_num, parsed_date, seller_num, fee_num))

        print(f"  Date column: {idx_date} (B)")
        if idx_phone:
            print(f"  Phone column: {idx_phone} (I)")
        else:
            print("  Phone column: not found (will skip phone import)")
        print(f"  Raw Kaspi columns: {idx_start}-{idx_end} (Y-AZ)")

        return CRMSnapshot(
            date_col=idx_date,
            phone_col=idx_phone,
            start_col=idx_start,
            end_col=idx_end,
            start_row=start_row,
            end_row=end_row,
            slice_headers=slice_headers,
            order_ids=order_ids,
            order_rows=order_rows,
            existing_keys=existing_keys,
            column_positions=target_columns,
            planned_col_abs=planned_col_abs,
            table_date_col=table_date_col,
            delivery_fee_col=delivery_fee_col,
            seller_fee_col=seller_fee_col,
            delivery_fee_rows=delivery_fee_rows,
        )
    finally:
        wb.close()


def collect_existing_order_ids(
    crm_path: Path, 
    sheet_name: str, 
    table_name: str, 
    order_col_abs: int
) -> set:
    """Get set of existing OrderIDs from CRM."""
    wb = load_workbook(filename=str(crm_path), read_only=False, data_only=True)
    try:
        ws = wb[sheet_name]
        table = _resolve_table(ws, table_name)
        start_col, start_row, end_col, end_row = _table_bounds(table)
        
        if not (start_col <= order_col_abs <= end_col):
            return set()
        
        order_ids = set()
        for row in ws.iter_rows(min_row=start_row + 1, max_row=end_row, 
                                min_col=order_col_abs, max_col=order_col_abs):
            cell = row[0]
            val = cell.value
            if val in (None, ""):
                continue
            if isinstance(val, str) and val.startswith("="):
                continue
            order_ids.add(str(val).strip())
        return order_ids
    finally:
        wb.close()


def collect_existing_order_keys(
    crm_path: Path,
    sheet_name: str,
    table_name: str,
    order_col_abs: int,
    planned_col_abs: Optional[int],
) -> set:
    """
    Get set of existing order keys from CRM.

    Key format: "{order_id}|{YYYY-MM-DD}" if planned date exists,
    otherwise "{order_id}|" (empty planned date).
    """
    wb = load_workbook(filename=str(crm_path), read_only=False, data_only=True)
    try:
        ws = wb[sheet_name]
        table = _resolve_table(ws, table_name)
        start_col, start_row, end_col, end_row = _table_bounds(table)

        if not (start_col <= order_col_abs <= end_col):
            return set()

        planned_in_table = (
            planned_col_abs is not None
            and start_col <= planned_col_abs <= end_col
        )

        keys = set()
        for row_num in range(start_row + 1, end_row + 1):
            order_val = ws.cell(row=row_num, column=order_col_abs).value
            if order_val in (None, ""):
                continue
            if isinstance(order_val, str) and order_val.startswith("="):
                continue
            order_id = clean_order_id(order_val)
            if not order_id:
                continue

            planned_date = None
            if planned_in_table:
                planned_val = ws.cell(row=row_num, column=planned_col_abs).value
                planned_date = parse_date(planned_val)

            if planned_date:
                key = f"{order_id}|{planned_date.isoformat()}"
            else:
                key = f"{order_id}|"
            keys.add(key)

        return keys
    finally:
        wb.close()


def collect_existing_order_rows(
    crm_path: Path,
    sheet_name: str,
    table_name: str,
    order_col_abs: int
) -> Dict[str, int]:
    """
    Get dict mapping OrderID -> row number from CRM.

    Used for updating existing orders.
    """
    wb = load_workbook(filename=str(crm_path), read_only=False, data_only=True)
    try:
        ws = wb[sheet_name]
        table = _resolve_table(ws, table_name)
        start_col, start_row, end_col, end_row = _table_bounds(table)

        if not (start_col <= order_col_abs <= end_col):
            return {}

        order_rows = {}
        for row_num in range(start_row + 1, end_row + 1):
            cell = ws.cell(row=row_num, column=order_col_abs)
            val = cell.value
            if val in (None, ""):
                continue
            if isinstance(val, str) and val.startswith("="):
                continue
            # Convert float to int to match API format (741866233.0 -> "741866233")
            if isinstance(val, float):
                val = int(val)
            order_id = str(val).strip()
            if order_id:
                order_rows[order_id] = row_num
        return order_rows
    finally:
        wb.close()


def find_update_column_positions(
    crm_path: Path,
    sheet_name: str,
    start_col: int,
    end_col: int
) -> Dict[str, int]:
    """
    Find column positions for update fields within the raw Kaspi columns.

    Returns dict mapping column name -> absolute column position.
    Target columns: Статус, Дата изменения статуса, Принял, Выдал, Отменил,
    Плановая дата передачи курьеру, Стоимость доставки для покупателя,
    Стоимость доставки для продавца, Компенсация за доставку
    """
    wb = load_workbook(filename=str(crm_path), read_only=True, data_only=True)
    try:
        ws = wb[sheet_name]
        header_row = list(ws.iter_rows(min_row=1, max_row=1, min_col=start_col, max_col=end_col))[0]

        target_columns = {
            'Статус': None,
            'Дата изменения статуса': None,
            'Принял': None,
            'Выдал': None,
            'Отменил': None,
            'Плановая дата передачи курьеру': None,
            'Стоимость доставки для покупателя': None,
            'Стоимость доставки для продавца': None,
            'Компенсация за доставку': None,
        }

        for i, cell in enumerate(header_row):
            header = str(cell.value or '').strip()
            if header in target_columns:
                target_columns[header] = start_col + i

        return target_columns
    finally:
        wb.close()


def _require_xlwings() -> None:
    if xw is None:
        raise RuntimeError(
            "xlwings is required for Excel writes. "
            "Install with `pip install xlwings` or run with --dry-run/--no-update."
        )


def update_existing_order_columns(
    crm_path: Path,
    sheet_name: str,
    order_rows: Dict[str, int],  # order_id -> row number
    update_data: Dict[str, dict],  # order_id -> {Статус, Принял, Выдал, Отменил, ...}
    column_positions: Dict[str, int],  # column name -> absolute column position
    dry_run: bool = False,
    verbose: bool = False,
) -> int:
    """
    Update specific columns for existing orders in CRM.

    Only updates: Статус, Дата изменения статуса, Принял, Выдал, Отменил
    Does NOT touch Status column (A) or formula columns.

    Uses BATCH writes by column to avoid slow cell-by-cell operations.

    Args:
        crm_path: Path to CRM file
        sheet_name: Sheet name
        order_rows: Dict mapping order_id -> Excel row number
        update_data: Dict mapping order_id -> column values to update
        column_positions: Dict mapping column name -> absolute column position
        dry_run: If True, don't write changes
        verbose: If True, print progress

    Returns:
        Number of orders updated
    """
    if not order_rows or not update_data:
        return 0

    # Find orders that exist in both
    orders_to_update = set(order_rows.keys()) & set(update_data.keys())

    if not orders_to_update:
        if verbose:
            print("  No existing orders to update")
        return 0

    if verbose:
        print(f"  Found {len(orders_to_update)} orders to update")

    if dry_run:
        print(f"  [DRY RUN] Would update {len(orders_to_update)} orders")
        return 0

    _require_xlwings()

    # Pre-build column updates: {col_pos: [(row, value), ...]}
    # This allows us to batch writes by column instead of cell-by-cell
    column_updates: Dict[int, List[Tuple[int, any]]] = {}

    for order_id in orders_to_update:
        row = order_rows[order_id]
        data = update_data[order_id]

        for col_name, col_pos in column_positions.items():
            if col_pos is None:
                continue
            if col_name in data:
                new_value = data[col_name]
                if new_value is not None:
                    if col_pos not in column_updates:
                        column_updates[col_pos] = []
                    column_updates[col_pos].append((row, new_value))

    if verbose:
        total_cells = sum(len(v) for v in column_updates.values())
        print(f"  Preparing {total_cells} cell updates across {len(column_updates)} columns...")

    # Use xlwings for writing (preserves formulas)
    app = xw.App(visible=False, add_book=False)
    app.display_alerts = False
    app.screen_updating = False

    try:
        wb = app.books.open(str(crm_path))
        ws = wb.sheets[sheet_name]

        # Disable calculation during updates for speed
        original_calc = app.calculation
        app.calculation = 'manual'

        # Write updates column by column
        cols_written = 0
        for col_pos, row_values in column_updates.items():
            # Sort by row for potential range optimization
            row_values.sort(key=lambda x: x[0])

            # Write all values for this column
            for row, value in row_values:
                ws.range((row, col_pos)).value = value

            cols_written += 1
            if verbose:
                print(f"    Column {cols_written}/{len(column_updates)} updated ({len(row_values)} cells)")

        # Restore calculation and save
        app.calculation = original_calc
        wb.save()
        wb.close()

        if verbose:
            print(f"  Updated {len(orders_to_update)} orders")

        return len(orders_to_update)

    finally:
        app.quit()


def build_update_data(df: pd.DataFrame, colmap: Dict[str, str]) -> Dict[str, dict]:
    """
    Build update data dict from DataFrame.

    Extracts: order_id -> {
        Статус, Дата изменения статуса, Принял, Выдал, Отменил,
        Плановая дата передачи курьеру,
        Стоимость доставки для покупателя, Стоимость доставки для продавца, Компенсация за доставку
    }
    for updating existing orders in CRM.
    """
    update_data = {}

    # Find column names in DataFrame
    status_col = None
    status_change_col = None
    prinyal_col = None
    vydal_col = None
    otmenil_col = None
    planned_date_col = None
    buyer_cost_col = None
    seller_cost_col = None
    delivery_comp_col = None

    for col in df.columns:
        col_norm = norm(col)
        if col_norm == 'статус':
            status_col = col
        elif col_norm in {'датаизменениястатуса', 'statuschangedate'}:
            status_change_col = col
        elif col_norm == 'принял':
            prinyal_col = col
        elif col_norm == 'выдал':
            vydal_col = col
        elif col_norm == 'отменил':
            otmenil_col = col
        elif col_norm == 'плановаядатапередачикурьеру':
            planned_date_col = col
        elif col_norm == 'стоимостьдоставкидляпокупателя':
            buyer_cost_col = col
        elif col_norm == 'стоимостьдоставкидляпродавца':
            seller_cost_col = col
        elif col_norm == 'компенсациязадоставку':
            delivery_comp_col = col

    order_col = colmap.get('order_id')
    if not order_col:
        return {}

    for _, row in df.iterrows():
        order_id = str(row.get(order_col, '')).strip()
        if not order_id:
            continue

        # Convert float order_id to int string (741866233.0 -> "741866233")
        try:
            order_id = str(int(float(order_id)))
        except (ValueError, TypeError):
            pass

        data = {}
        if status_col and pd.notna(row.get(status_col)):
            data['Статус'] = str(row[status_col])
        if status_change_col and pd.notna(row.get(status_change_col)):
            data['Дата изменения статуса'] = row[status_change_col]
        if prinyal_col:
            data['Принял'] = str(row.get(prinyal_col, '') or '')
        if vydal_col:
            data['Выдал'] = str(row.get(vydal_col, '') or '')
        if otmenil_col:
            data['Отменил'] = str(row.get(otmenil_col, '') or '')
        if planned_date_col and pd.notna(row.get(planned_date_col)):
            data['Плановая дата передачи курьеру'] = row.get(planned_date_col)
        if buyer_cost_col and pd.notna(row.get(buyer_cost_col)):
            data['Стоимость доставки для покупателя'] = row.get(buyer_cost_col)
        if seller_cost_col and pd.notna(row.get(seller_cost_col)):
            data['Стоимость доставки для продавца'] = row.get(seller_cost_col)
        if delivery_comp_col and pd.notna(row.get(delivery_comp_col)):
            data['Компенсация за доставку'] = row.get(delivery_comp_col)

        if data:
            update_data[order_id] = data

    return update_data


# ---------- Build Staging Data ----------

def build_staging(df_filt: pd.DataFrame, crm_slice_headers: List[str]) -> Tuple[List[List], List[str]]:
    """
    Build 2D list matching CRM slice columns plus phone values.

    Returns: (stage_block, phone_values)
    """
    colmap = map_headers(df_filt)

    # Series by canonical key
    S: Dict[str, pd.Series] = {}
    for k, real in colmap.items():
        S[k] = df_filt[real].astype(object)

    # Direct lookup by normalized header
    cols_norm_map = {norm(col): df_filt[col].astype(object) for col in df_filt.columns}

    n = len(df_filt)
    records = df_filt.to_dict(orient="records")
    articles = [str(r.get("Артикул") or r.get("SKU_ID_KSP") or "").strip() for r in records]
    article_identity = _load_article_identity_for_articles(articles)
    seed_sku_keys = []
    for r in records:
        maybe_key = str(r.get("SKU_key") or "").strip()
        if maybe_key:
            seed_sku_keys.append(maybe_key)
    _, _, valid_sku_keys = _load_sku_meta_for_keys(seed_sku_keys)
    derived_identity = []
    for row in records:
        derived_identity.append(
            _derive_identity_from_raw_row(
                row,
                article_identity_by_article=article_identity,
                valid_sku_keys=valid_sku_keys,
            )
        )
    derived_sku_key = pd.Series([d.get("sku_key") or "" for d in derived_identity], index=df_filt.index, dtype=object)

    def col_for(header_text: str) -> pd.Series:
        h = norm(header_text)

        # Map canonical keys
        # Note: "№ заказа" normalizes to "заказа"
        if h in {"orderid", "номерзаказа", "заказ", "№заказа", "заказа"} and "order_id" in S:
            col = S["order_id"].copy()
            col = col.apply(lambda v: "" if pd.isna(v) else (
                str(int(v)) if isinstance(v, (int, float)) and float(v).is_integer() else str(v)
            ))
            return col

        if h in {"названиевсистемепродавца"} and "seller_name" in S:
            return S["seller_name"]

        if h in {"названиетоваравkaspiмагазине"} and "offer_name" in S:
            return S["offer_name"]

        if h in {"артикул"} and "sku" in S:
            return S["sku"].apply(normalize_article_code)

        if h in {"складпередачикд", "складпередачикурьерскойдоставки"} and "warehouse" in S:
            return S["warehouse"]

        if h in {"skukey", "sku_key"}:
            if h in cols_norm_map:
                source_series = cols_norm_map[h].astype(object)
                if valid_sku_keys:
                    merged = []
                    for idx in source_series.index:
                        src = str(source_series.loc[idx] or "").strip()
                        merged.append(src if src in valid_sku_keys else str(derived_sku_key.loc[idx] or "").strip())
                    return pd.Series(merged, index=df_filt.index, dtype=object)
                return source_series
            return derived_sku_key

        if h in {"mysize", "my_size"}:
            # Human-owned column: must remain blank for manual assignment.
            return pd.Series([""] * n, index=df_filt.index, dtype=object)

        if h in {"датаизменениястатуса"} and "status_change_date" in S:
            return S["status_change_date"]

        # Direct match
        if h in cols_norm_map:
            return cols_norm_map[h]

        return pd.Series([""] * n, index=df_filt.index, dtype=object)

    cols = [col_for(h) for h in crm_slice_headers]

    stage = []
    for i in range(len(df_filt)):
        row = []
        for s in cols:
            v = s.iloc[i]
            if pd.isna(v):
                v = ""
            row.append(v)
        stage.append(row)

    # Extract phone values separately (Phase 12)
    # Format: +7XXXXXXXXXX (Kazakhstan format)
    phone_values = []
    if "phone" in S:
        for i in range(len(df_filt)):
            v = S["phone"].iloc[i]
            if pd.isna(v):
                v = ""
            else:
                v = str(v).strip()
                # Add +7 prefix if phone has digits and doesn't already start with +
                if v and v[0] != '+':
                    # Remove any leading 8 or 7 (common Kazakhstan patterns)
                    if v.startswith('8') and len(v) == 11:
                        v = '+7' + v[1:]
                    elif v.startswith('7') and len(v) == 11:
                        v = '+7' + v[1:]
                    elif len(v) == 10:
                        v = '+7' + v
                    else:
                        v = '+7' + v  # Default: prepend +7
            phone_values.append(v)
    else:
        phone_values = [""] * len(df_filt)

    return stage, phone_values


# ---------- Excel Append via xlwings ----------

def excel_append_xlwings(
    out_wb: Path,
    sheet_name: str,
    table_name: str,
    date_col_abs: int,
    phone_col_abs: Optional[int],
    start_col_abs: int,
    end_col_abs: int,
    stage_block: List[List],
    phone_values: List[str],
    set_date: date,
    slice_headers: List[str],
    fixed_values: Optional[List[Dict[str, Any]]] = None,
) -> Tuple[int, int]:
    """
    Append rows to CRM using xlwings (preserves formulas & external links).

    Args:
        phone_col_abs: Column for phone data (column I), or None to skip
        phone_values: List of phone strings to write

    Returns:
        Tuple of (start_row, end_row) where new rows were appended.
        Returns (0, 0) if no rows were appended.
    """
    n = len(stage_block)
    if n == 0:
        return (0, 0)

    _require_xlwings()

    print(f"  Opening Excel (hidden)...")
    app = xw.App(visible=False, add_book=False)
    app.display_alerts = False
    app.screen_updating = False

    try:
        wb = app.books.open(str(out_wb))
        sh = wb.sheets[sheet_name]

        # Find the table
        try:
            tbl = sh.tables[table_name]
        except KeyError:
            tables = list(sh.tables)
            if not tables:
                raise RuntimeError(f"No table found on sheet {sheet_name}")
            tbl = tables[0]

        # Calculate where new rows go
        total_rows_before = tbl.range.rows.count
        header_row = tbl.range.row
        data_rows_before = total_rows_before - 1

        top_row = header_row + data_rows_before + 1
        bottom_row = top_row + n - 1

        print(f"  Appending {n} rows starting at row {top_row}")

        # CRITICAL: Resize table FIRST to include new rows
        # This prevents Excel table corruption (XML errors)
        tbl_start_col = tbl.range.column
        tbl_end_col = tbl.range.columns.count + tbl_start_col - 1
        new_table_range = sh.range(
            (header_row, tbl_start_col),
            (bottom_row, tbl_end_col)
        )
        tbl.resize(new_table_range)
        print(f"  Table resized to include rows up to {bottom_row}")

        # Write date column
        date_vals = [[set_date] for _ in range(n)]
        date_range = sh.range((top_row, date_col_abs), (bottom_row, date_col_abs))
        date_range.value = date_vals
        date_range.number_format = "dd.mm.yyyy"

        # Write "Новый" marker to HEIGHT column (D = 4) for visual identification
        # Phase 12 Part 3: Helps employees see which orders were added in second import
        height_col = 4  # Column D
        height_range = sh.range((top_row, height_col), (bottom_row, height_col))
        height_range.value = [["Новый"] for _ in range(n)]
        print(f"  'Новый' marker written to column D for {n} rows")

        # Write phone column (Phase 12)
        if phone_col_abs and phone_values:
            # Only write non-empty phone values
            has_phones = any(v for v in phone_values)
            if has_phones:
                phone_range = sh.range((top_row, phone_col_abs), (bottom_row, phone_col_abs))
                phone_range.value = [[v] for v in phone_values]
                print(f"  Phone data written to column {phone_col_abs}")

        # Write data columns (skip formula-driven columns like OrderID if they exist in table)
        width = len(slice_headers)
        for offset in range(width):
            header = slice_headers[offset]
            col_values = [row[offset] for row in stage_block]

            # Skip entirely empty columns
            if all((v is None) or (isinstance(v, str) and v == "") for v in col_values):
                continue

            target = sh.range((top_row, start_col_abs + offset), (bottom_row, start_col_abs + offset))
            target.value = [[v] for v in col_values]

        # Write fixed-value columns for appended rows (excluding human-owned fields).
        if fixed_values:
            table_header = sh.range(
                (header_row, tbl_start_col),
                (header_row, tbl_end_col),
            ).value
            header_to_col = {
                str(name).strip(): tbl_start_col + i
                for i, name in enumerate(table_header or [])
                if str(name or "").strip()
            }
            for col_name in FIXED_APPEND_COLUMNS:
                if col_name in PROTECTED_HUMAN_COLUMNS:
                    continue
                col_abs = header_to_col.get(col_name)
                if not col_abs:
                    continue
                col_vals = []
                for row_vals in fixed_values:
                    value = row_vals.get(col_name)
                    col_vals.append([value if value is not None else ""])
                target = sh.range((top_row, col_abs), (bottom_row, col_abs))
                target.value = col_vals

        # MY_SIZE is human-owned; always clear for newly appended rows to
        # prevent Excel table formula autofill from writing pseudo sizes.
        my_size_col_abs = None
        table_header = sh.range(
            (header_row, tbl_start_col),
            (header_row, tbl_end_col),
        ).value
        header_to_col = {
            str(name).strip(): tbl_start_col + i
            for i, name in enumerate(table_header or [])
            if str(name or "").strip()
        }
        my_size_col_abs = header_to_col.get("MY_SIZE")
        if my_size_col_abs:
            sh.range((top_row, my_size_col_abs), (bottom_row, my_size_col_abs)).value = [[""] for _ in range(n)]

        wb.save()
        wb.close()
        print(f"  ✅ Saved {out_wb.name}")

        return (top_row, bottom_row)

    finally:
        app.quit()

    return (0, 0)  # If we get here somehow


def apply_fixed_values_backfill_xlwings(
    crm_path: Path,
    sheet_name: str,
    table_name: str,
    days: int,
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    dry_run: bool = False,
    verbose: bool = False,
) -> int:
    """
    Backfill fixed-value columns for recent rows to reduce formula churn.
    """
    date_from, date_to = _resolve_backfill_window(days, date_from, date_to)
    if not date_from or not date_to:
        return 0
    _require_xlwings()

    app = xw.App(visible=False, add_book=False)
    app.display_alerts = False
    app.screen_updating = False
    updated = 0
    try:
        wb = app.books.open(str(crm_path))
        sh = wb.sheets[sheet_name]
        try:
            tbl = sh.tables[table_name]
        except KeyError:
            tables = list(sh.tables)
            if not tables:
                raise RuntimeError(f"No table found on sheet {sheet_name}")
            tbl = tables[0]

        table_range = tbl.range
        header_row = table_range.row
        start_col = table_range.column
        width = table_range.columns.count
        total_rows = table_range.rows.count
        if total_rows <= 1:
            wb.close()
            return 0

        headers = sh.range((header_row, start_col), (header_row, start_col + width - 1)).value
        header_to_col = {
            str(name).strip(): start_col + i
            for i, name in enumerate(headers or [])
            if str(name or "").strip()
        }
        row_start = header_row + 1
        row_end = header_row + total_rows - 1

        date_col = header_to_col.get("Date")
        if not date_col:
            wb.close()
            return 0

        raw_headers = [
            "Склад передачи КД",
            "Артикул",
            "Название товара в Kaspi Магазине",
            "Название в системе продавца",
            "Количество",
            "Сумма",
            "Стоимость доставки для продавца",
            "Плановая дата передачи курьеру",
            "KASPI_OFFER_NAME",
            "SKU_key",
            "MY_SIZE",
            "Product_Type",
        ]

        n_rows = row_end - row_start + 1
        date_values = _coerce_column_values(
            sh.range((row_start, date_col), (row_end, date_col)).value,
            n_rows,
        )

        raw_col_values: Dict[str, List[Any]] = {}
        for key in raw_headers:
            col_num = header_to_col.get(key)
            if not col_num:
                raw_col_values[key] = [None] * n_rows
                continue
            raw_col_values[key] = _coerce_column_values(
                sh.range((row_start, col_num), (row_end, col_num)).value,
                n_rows,
            )

        target_rows: List[Tuple[int, Dict[str, Any]]] = []
        for offset in range(n_rows):
            row_num = row_start + offset
            row_date = parse_date(date_values[offset])
            if not _row_in_backfill_window(row_date, date_from, date_to):
                continue
            raw_row = {}
            for key in raw_headers:
                raw_row[key] = raw_col_values[key][offset]
            target_rows.append((row_num, raw_row))

        if not target_rows:
            wb.close()
            return 0

        articles = [str(raw.get("Артикул") or raw.get("SKU_ID_KSP") or "").strip() for _, raw in target_rows]
        article_identity = _load_article_identity_for_articles(articles)

        sku_keys: List[str] = []
        for _, raw in target_rows:
            identity = _derive_identity_from_raw_row(
                raw,
                article_identity_by_article=article_identity,
            )
            if identity.get("sku_key"):
                sku_keys.append(str(identity["sku_key"]))
        sku_meta, kaspi_core, valid_sku_keys = _load_sku_meta_for_keys(sku_keys)

        fixed_by_row: Dict[int, Dict[str, Any]] = {}
        for row_num, raw in target_rows:
            fixed_by_row[row_num] = compute_fixed_value_columns(
                raw,
                sku_meta,
                kaspi_core,
                article_identity_by_article=article_identity,
                valid_sku_keys=valid_sku_keys,
            )
            updated += 1

        if not dry_run:
            original_calc = app.calculation
            try:
                app.calculation = "manual"
            except Exception:
                original_calc = None

            row_numbers = sorted(fixed_by_row.keys())
            row_ranges = _iter_consecutive_ranges(row_numbers)
            for col_name in FIXED_BACKFILL_COLUMNS:
                if col_name in PROTECTED_HUMAN_COLUMNS:
                    continue
                col_num = header_to_col.get(col_name)
                if not col_num:
                    continue
                for start_row, end_row in row_ranges:
                    values = []
                    for row_num in range(start_row, end_row + 1):
                        value = fixed_by_row[row_num].get(col_name)
                        values.append([value if value is not None else ""])
                    sh.range((start_row, col_num), (end_row, col_num)).value = values

            if original_calc is not None:
                app.calculation = original_calc

        if not dry_run:
            wb.save()
        wb.close()
        if verbose:
            mode = "DRY RUN" if dry_run else "APPLY"
            print(f"  Fixed-value backfill ({mode}): {updated} rows ({date_from}..{date_to})")
    finally:
        app.quit()

    return updated


def apply_fixed_values_backfill_openpyxl(
    crm_path: Path,
    sheet_name: str,
    table_name: str,
    days: int,
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    dry_run: bool = False,
    verbose: bool = False,
) -> int:
    """
    Openpyxl fallback for fixed-value backfill when xlwings/Excel automation is unavailable.
    """
    date_from, date_to = _resolve_backfill_window(days, date_from, date_to)
    if not date_from or not date_to:
        return 0

    wb = load_workbook(filename=str(crm_path), read_only=False, data_only=False)
    updated = 0
    try:
        ws = wb[sheet_name]
        table = _resolve_table(ws, table_name)
        start_col, start_row, end_col, end_row = _table_bounds(table)
        if end_row <= start_row:
            return 0

        headers = [
            ws.cell(row=start_row, column=c).value
            for c in range(start_col, end_col + 1)
        ]
        header_to_col = {
            str(name).strip(): start_col + i
            for i, name in enumerate(headers or [])
            if str(name or "").strip()
        }
        date_col = header_to_col.get("Date")
        if not date_col:
            return 0

        raw_headers = [
            "Склад передачи КД",
            "Артикул",
            "Название товара в Kaspi Магазине",
            "Название в системе продавца",
            "Количество",
            "Сумма",
            "Стоимость доставки для продавца",
            "Плановая дата передачи курьеру",
            "KASPI_OFFER_NAME",
            "SKU_key",
            "MY_SIZE",
            "Product_Type",
        ]

        target_rows: List[Tuple[int, Dict[str, Any]]] = []
        for row_num in range(start_row + 1, end_row + 1):
            row_date = parse_date(ws.cell(row=row_num, column=date_col).value)
            if not _row_in_backfill_window(row_date, date_from, date_to):
                continue
            raw_row: Dict[str, Any] = {}
            for key in raw_headers:
                col_num = header_to_col.get(key)
                raw_row[key] = ws.cell(row=row_num, column=col_num).value if col_num else None
            target_rows.append((row_num, raw_row))

        if not target_rows:
            return 0

        articles = [str(raw.get("Артикул") or raw.get("SKU_ID_KSP") or "").strip() for _, raw in target_rows]
        article_identity = _load_article_identity_for_articles(articles)

        sku_keys: List[str] = []
        for _, raw in target_rows:
            identity = _derive_identity_from_raw_row(
                raw,
                article_identity_by_article=article_identity,
            )
            if identity.get("sku_key"):
                sku_keys.append(str(identity["sku_key"]))
        sku_meta, kaspi_core, valid_sku_keys = _load_sku_meta_for_keys(sku_keys)

        fixed_by_row: Dict[int, Dict[str, Any]] = {}
        for row_num, raw in target_rows:
            fixed_by_row[row_num] = compute_fixed_value_columns(
                raw,
                sku_meta,
                kaspi_core,
                article_identity_by_article=article_identity,
                valid_sku_keys=valid_sku_keys,
            )
            updated += 1

        if not dry_run:
            for row_num, fixed in fixed_by_row.items():
                for col_name in FIXED_BACKFILL_COLUMNS:
                    if col_name in PROTECTED_HUMAN_COLUMNS:
                        continue
                    col_num = header_to_col.get(col_name)
                    if not col_num:
                        continue
                    value = fixed.get(col_name)
                    ws.cell(row=row_num, column=col_num).value = value if value is not None else ""
            wb.save(str(crm_path))
        if verbose:
            mode = "DRY RUN" if dry_run else "APPLY"
            print(f"  Fixed-value backfill ({mode}, openpyxl): {updated} rows ({date_from}..{date_to})")
        return updated
    finally:
        wb.close()


def _coerce_column_values(values: Any, n_rows: int) -> List[Any]:
    """Normalize xlwings single-column reads to a list of exactly n_rows."""
    if isinstance(values, list):
        out = list(values)
    else:
        out = [values]
    if len(out) < n_rows:
        out.extend([None] * (n_rows - len(out)))
    return out[:n_rows]


def _iter_consecutive_ranges(rows: List[int]) -> List[Tuple[int, int]]:
    """Return inclusive (start, end) ranges for sorted row numbers."""
    if not rows:
        return []
    ranges: List[Tuple[int, int]] = []
    start = rows[0]
    end = rows[0]
    for value in rows[1:]:
        if value == end + 1:
            end = value
            continue
        ranges.append((start, end))
        start = value
        end = value
    ranges.append((start, end))
    return ranges


# ---------- Archive Source Files ----------

def archive_run(orders_dir: Path, source_files: List[Path], df_filt: pd.DataFrame) -> Path:
    """Archive source files and create log."""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    archive_root = orders_dir / "archive_orders"
    archive_root.mkdir(parents=True, exist_ok=True)
    
    run_dir = archive_root / timestamp
    run_dir.mkdir(parents=True, exist_ok=True)
    
    # Move source files
    for src in source_files:
        dest = run_dir / src.name
        try:
            shutil.move(str(src), str(dest))
            print(f"  Archived: {src.name}")
        except Exception as e:
            print(f"  WARN: could not archive {src.name}: {e}")
    
    # Create log CSV
    colmap = map_headers(df_filt)
    log_cols = []
    for key in ("order_id", "handover", "warehouse", "status"):
        if key in colmap:
            log_cols.append(colmap[key])
    
    if "__source_file__" in df_filt.columns:
        log_cols.append("__source_file__")
    
    if log_cols:
        df_log = df_filt[log_cols].copy()
        rename_map = {colmap[k]: k for k in colmap if colmap[k] in log_cols}
        df_log = df_log.rename(columns=rename_map)
        
        log_path = run_dir / "appended_orders.csv"
        df_log.to_csv(log_path, index=False)
    
    return run_dir


def sync_pending_orders_to_gdrive_safe(
    crm_path: Path,
    target_date: date,
    dry_run: bool = False,
) -> dict:
    print("\n4. Syncing pending orders to Google Drive...")
    try:
        from scripts.sync_to_gdrive import sync_pending_orders_to_gdrive
        stats = sync_pending_orders_to_gdrive(
            crm_path=crm_path,
            target_date=target_date,
            status_value=READY_STATUS,
            dry_run=dry_run,
            validate=not dry_run,
        )
        print(f"   Google Drive sync: {stats['rows_synced']} rows synced")
        return stats
    except Exception as e:
        print(f"   WARNING: Google Drive sync failed: {e}")
        return {"rows_synced": 0, "dry_run": dry_run, "error": str(e)}


def write_import_summary(result: dict, summary_path: Path) -> None:
    """Write a small JSON summary for downstream no-op detection."""
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "orders_imported": int(result.get("orders_imported", 0) or 0),
        "orders_updated": int(result.get("orders_updated", 0) or 0),
        "orders_filtered": int(result.get("orders_filtered", 0) or 0),
        "timestamp": datetime.now().isoformat(timespec="seconds"),
    }
    summary_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


# ---------- CLI ----------

_UNSET = object()


def main(
    orders_dir=_UNSET,
    crm_path=_UNSET,
    sheet_name=_UNSET,
    table_name=_UNSET,
    date_end=_UNSET,
    append_date=_UNSET,
    status=_UNSET,
    dry_run=_UNSET,
    verbose=_UNSET,
    update_existing=_UNSET,
    no_update=_UNSET,
    fixed_values=_UNSET,
    backfill_fixed_days=_UNSET,
    skip_fixed_backfill=_UNSET,
    strict_excel=_UNSET,
    summary_file=_UNSET,
):
    parser = argparse.ArgumentParser(
        description="Import Kaspi ActiveOrders to CRM (xlwings, Excel-safe)"
    )
    parser.add_argument(
        "--orders-dir",
        type=Path,
        default=data_path("excel_ui", "ActiveOrders"),
        help="Directory containing ActiveOrders*.xlsx",
    )
    parser.add_argument(
        "--crm-file",
        type=Path,
        default=data_path("excel_ui", "SALES_KSP_CRM_V3.xlsx"),
        help="CRM Excel file",
    )
    parser.add_argument(
        "--sheet", 
        default="SALES_KSP_CRM_1",
        help="CRM sheet name"
    )
    parser.add_argument(
        "--table", 
        default="tb_SalesRaw",
        help="CRM table name"
    )
    parser.add_argument(
        "--date-end",
        default="today",
        help="Exact planned delivery date to filter (today, tomorrow, or YYYY-MM-DD)"
    )
    parser.add_argument(
        "--append-date", 
        default="today",
        help="Date to stamp into CRM Date column"
    )
    parser.add_argument(
        "--status", 
        default=DEFAULT_STATUS,
        help="Status filter"
    )
    parser.add_argument(
        "--dry-run", 
        action="store_true",
        help="Preview only, don't write to Excel"
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Verbose output"
    )
    parser.add_argument(
        "--update-existing",
        action="store_true",
        default=True,
        help="Update status columns for existing orders (default: True)"
    )
    parser.add_argument(
        "--no-update",
        action="store_true",
        help="Skip updating existing orders (only append new)"
    )
    parser.add_argument(
        "--fixed-values",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Write fixed values for trivial formula columns on appended rows (default: on)",
    )
    parser.add_argument(
        "--backfill-fixed-days",
        type=int,
        default=14,
        help="Recompute fixed values for recent rows (default: 14 days)",
    )
    parser.add_argument(
        "--fixed-backfill-from",
        default=None,
        help="Explicit backfill window start date (YYYY-MM-DD, today, yesterday)",
    )
    parser.add_argument(
        "--fixed-backfill-to",
        default=None,
        help="Explicit backfill window end date (YYYY-MM-DD, today, yesterday)",
    )
    parser.add_argument(
        "--skip-fixed-backfill",
        action="store_true",
        help="Skip recent fixed-value backfill pass",
    )
    parser.add_argument(
        "--fixed-values-scope",
        choices=["window", "new-only"],
        default="window",
        help="window: append + recent backfill, new-only: append only (default: window)",
    )
    parser.add_argument(
        "--refresh-delivery-fees",
        action="store_true",
        help="Backfill seller delivery fee from Delivery_fee_kzt for a date range"
    )
    parser.add_argument(
        "--refresh-fees-from",
        default=None,
        help="Backfill delivery fees from date (YYYY-MM-DD, today, yesterday)"
    )
    parser.add_argument(
        "--refresh-fees-to",
        default=None,
        help="Backfill delivery fees to date (YYYY-MM-DD, today, yesterday)"
    )
    parser.add_argument(
        "--summary-file",
        type=Path,
        default=data_path("logs", "import_orders_to_crm_latest.json"),
        help="Write JSON summary to this path (default: logs/import_orders_to_crm_latest.json)",
    )
    parser.add_argument(
        "--strict-excel",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Run strict Excel automation preflight and abort if unavailable (default: on).",
    )

    if (
        orders_dir is _UNSET
        and crm_path is _UNSET
        and sheet_name is _UNSET
        and table_name is _UNSET
        and date_end is _UNSET
        and append_date is _UNSET
        and status is _UNSET
        and dry_run is _UNSET
        and verbose is _UNSET
        and update_existing is _UNSET
        and no_update is _UNSET
        and fixed_values is _UNSET
        and backfill_fixed_days is _UNSET
        and skip_fixed_backfill is _UNSET
        and strict_excel is _UNSET
    ):
        args = parser.parse_args()
    else:
        args = argparse.Namespace(
            orders_dir=Path(orders_dir) if orders_dir is not _UNSET else data_path("excel_ui", "ActiveOrders"),
            crm_file=Path(crm_path) if crm_path is not _UNSET else data_path("excel_ui", "SALES_KSP_CRM_V3.xlsx"),
            sheet=sheet_name if sheet_name is not _UNSET else "SALES_KSP_CRM_1",
            table=table_name if table_name is not _UNSET else "tb_SalesRaw",
            date_end=date_end if date_end is not _UNSET else "today",
            append_date=append_date if append_date is not _UNSET else "today",
            status=status if status is not _UNSET else DEFAULT_STATUS,
            dry_run=bool(dry_run) if dry_run is not _UNSET else False,
            verbose=bool(verbose) if verbose is not _UNSET else False,
            update_existing=bool(update_existing) if update_existing is not _UNSET else True,
            no_update=bool(no_update) if no_update is not _UNSET else False,
            fixed_values=bool(fixed_values) if fixed_values is not _UNSET else True,
            backfill_fixed_days=int(backfill_fixed_days) if backfill_fixed_days is not _UNSET else 14,
            fixed_backfill_from=None,
            fixed_backfill_to=None,
            skip_fixed_backfill=bool(skip_fixed_backfill) if skip_fixed_backfill is not _UNSET else False,
            fixed_values_scope="window",
            strict_excel=bool(strict_excel) if strict_excel is not _UNSET else True,
            summary_file=Path(summary_file) if summary_file is not _UNSET else data_path("logs", "import_orders_to_crm_latest.json"),
        )

    result = {
        "orders_imported": 0,
        "orders_updated": 0,
        "orders_filtered": 0,
    }
    backup_done = False
    summary_path = Path(args.summary_file) if getattr(args, "summary_file", None) else None

    def finalize(outcome: dict) -> dict:
        if summary_path:
            write_import_summary(outcome, summary_path)
        return outcome

    def ensure_backup() -> None:
        nonlocal backup_done
        if args.dry_run or backup_done:
            return
        backup_path = backup_crm(args.crm_file)
        print(f"  Backup created: {backup_path.name}")
        backup_done = True

    def maybe_run_fixed_backfill() -> int:
        if not args.fixed_values:
            return 0
        if args.skip_fixed_backfill:
            return 0
        if str(getattr(args, "fixed_values_scope", "window")) == "new-only":
            return 0
        explicit_from = _resolve_refresh_date(getattr(args, "fixed_backfill_from", None), today_local()) if getattr(args, "fixed_backfill_from", None) else None
        explicit_to = _resolve_refresh_date(getattr(args, "fixed_backfill_to", None), today_local()) if getattr(args, "fixed_backfill_to", None) else None
        if int(args.backfill_fixed_days or 0) <= 0 and not (explicit_from or explicit_to):
            return 0
        ensure_backup()
        try:
            return apply_fixed_values_backfill_xlwings(
                crm_path=args.crm_file,
                sheet_name=args.sheet,
                table_name=args.table,
                days=max(int(args.backfill_fixed_days or 0), 0),
                date_from=explicit_from,
                date_to=explicit_to,
                dry_run=args.dry_run,
                verbose=args.verbose,
            )
        except Exception as exc:
            print(f"  WARNING: xlwings fixed-value backfill failed ({exc})")
            if args.verbose:
                import traceback

                traceback.print_exc()
            if not _allow_openpyxl_backfill_fallback():
                print(
                    "  WARNING: openpyxl fallback is disabled "
                    "(set CRM_FIXED_BACKFILL_OPENPYXL_FALLBACK=1 to enable)."
                )
                print("  WARNING: skipping fixed-value backfill to protect workbook structure.")
                return 0
            print("  WARNING: using openpyxl fallback for fixed-value backfill.")
            return apply_fixed_values_backfill_openpyxl(
                crm_path=args.crm_file,
                sheet_name=args.sheet,
                table_name=args.table,
                days=max(int(args.backfill_fixed_days or 0), 0),
                date_from=explicit_from,
                date_to=explicit_to,
                dry_run=args.dry_run,
                verbose=args.verbose,
            )
    
    # Parse dates
    if args.date_end.lower() == "today":
        end_date = today_local()
    elif args.date_end.lower() == "tomorrow":
        end_date = today_local() + timedelta(days=1)
    else:
        end_date = dtp.parse(args.date_end).date()
    
    if args.append_date.lower() == "today":
        append_date = today_local()
    else:
        append_date = dtp.parse(args.append_date).date()
    
    print("=" * 60)
    print("  Kaspi Order Import (xlwings)")
    print("=" * 60)
    print(f"  Data root: {get_data_root()}")
    print(f"  Orders dir: {args.orders_dir}")
    print(f"  CRM file: {args.crm_file}")
    print(f"  Date filter: == {end_date} (TODAY only)")
    print(f"  Append date: {append_date}")
    if args.verbose and args.fixed_values:
        print(f"  Fixed append columns: {', '.join(FIXED_APPEND_COLUMNS)}")
        print(f"  Fixed backfill columns: {', '.join(FIXED_BACKFILL_COLUMNS)}")
        print(f"  Protected columns (never overwritten): {', '.join(sorted(PROTECTED_HUMAN_COLUMNS))}")
        print(f"  Fixed values scope: {args.fixed_values_scope}")
    print()
    
    # Read and filter
    df_all, source_files = read_active_orders(args.orders_dir)
    df_filt, stats = filter_for_shipping(df_all, args.status, None, end_date)

    print(f"\nFiltered: {stats['rows_in_files']} → {stats['rows_after_filters']} rows")
    order_summary = summarize_order_rows(df_filt)
    if order_summary:
        print(
            f"Orders vs rows: {order_summary['unique_orders']} unique orders "
            f"across {order_summary['rows']} rows"
        )
        if order_summary["multi_line_orders"] > 0:
            print(
                f"  Multi-line orders: {order_summary['multi_line_orders']} "
                f"(max lines/order: {order_summary['max_lines_per_order']})"
            )

    result["orders_filtered"] = int(stats.get("rows_after_filters", 0))
    if df_filt.empty:
        print("No orders match filters. Nothing to import.")
        return finalize(result)

    # Sort for CRM append order (Phase 12 Part 6 - Updated)
    # Order: Status → STORE_NAME → OrderID → Quantity → KASPI_OFFER_NAME → Date
    df_filt = sort_for_crm(df_filt)
    print(f"Sorted by: Status (cancelled first), STORE_NAME, OrderID, Quantity, KASPI_OFFER_NAME, Date")

    # Inspect CRM structure (single openpyxl snapshot)
    snapshot = load_crm_snapshot(args.crm_file, args.sheet, args.table)
    date_abs = snapshot.date_col
    phone_abs = snapshot.phone_col
    start_abs = snapshot.start_col
    end_abs = snapshot.end_col
    slice_headers = snapshot.slice_headers

    # Get existing order IDs for dedup
    existing_ids = snapshot.order_ids
    print(f"Existing orders in CRM: {len(existing_ids)}")

    if not args.dry_run:
        _excel_automation_preflight(
            crm_path=args.crm_file,
            strict_excel=bool(getattr(args, "strict_excel", True)),
            verbose=bool(args.verbose),
        )

    # Update existing orders' status columns (Phase 12 Part 7)
    update_existing = args.update_existing and not args.no_update
    updated_count = 0
    column_positions = None
    # Build update source: all orders for target planned date (not just READY)
    update_df = df_all
    update_colmap = map_headers(df_all)
    if "handover" in update_colmap:
        handover = df_all[update_colmap["handover"]].apply(parse_kz_date)
        update_df = df_all[handover.apply(lambda d: d is not None and d == end_date)].copy()

    if update_existing and len(existing_ids) > 0:
        print("\n3. Updating existing orders' status columns...")

        # Get order rows (order_id -> row number)
        order_rows = snapshot.order_rows

        # Find column positions for update columns
        column_positions = snapshot.column_positions
        if args.verbose:
            print(f"  Update column positions: {column_positions}")

        # Build update data from source DataFrame (all statuses for target date)
        colmap = map_headers(update_df)
        update_data = build_update_data(update_df, colmap)

        # Fetch status updates for CRM-pending orders missing from ActiveOrders export
        try:
            update_ids = set()
            order_col = colmap.get("order_id")
            if order_col:
                for v in update_df[order_col].tolist():
                    oid = clean_order_id(v)
                    if oid:
                        update_ids.add(oid)

            crm_pending = read_crm_pending_orders(args.crm_file, args.sheet, end_date)
            missing = [o for o in crm_pending if o.get("order_id") not in update_ids]

            if missing:
                print(f"  Missing {len(missing)} CRM pending orders in ActiveOrders; fetching API status...")
                api_updates = fetch_missing_status_updates(missing, verbose=args.verbose)
                for oid, data in api_updates.items():
                    if not data:
                        continue
                    if oid in update_data:
                        update_data[oid].update(data)
                    else:
                        update_data[oid] = data
        except Exception as e:
            print(f"  WARNING: could not fetch missing order statuses: {e}")

        # How many orders can be updated?
        orders_to_update = set(order_rows.keys()) & set(update_data.keys())
        print(f"  Orders with status updates: {len(orders_to_update)}")

        if orders_to_update:
            updated_count = update_existing_order_columns(
                args.crm_file,
                args.sheet,
                order_rows,
                update_data,
                column_positions,
                dry_run=args.dry_run,
                verbose=args.verbose,
            )
            print(f"  Updated {updated_count} existing orders")
            result["orders_updated"] = updated_count
    else:
        if args.no_update:
            print("\n3. Skipping existing order updates (--no-update flag)")
        elif len(existing_ids) == 0:
            print("\n3. No existing orders to update")

    # Build staging data (returns tuple: stage_block, phone_values)
    stage, phone_values = build_staging(df_filt, slice_headers)
    fixed_values_payload = build_fixed_value_payload(df_filt)

    # Dedup against existing
    colmap = map_headers(df_filt)
    if "order_id" in colmap:
        order_col = colmap["order_id"]
        if column_positions is None:
            column_positions = snapshot.column_positions
        planned_col_abs = None
        if column_positions:
            planned_col_abs = column_positions.get("Плановая дата передачи курьеру")

        existing_keys = snapshot.existing_keys

        handover_col = colmap.get("handover")
        df_filt["_oid"] = df_filt[order_col].apply(clean_order_id)
        if handover_col and handover_col in df_filt.columns:
            df_filt["_pdate"] = df_filt[handover_col].apply(parse_date)
        else:
            df_filt["_pdate"] = None

        offer_col = colmap.get("offer_name")
        sku_col = colmap.get("sku")
        qty_col = colmap.get("quantity")
        df_filt["_okey"] = [
            _build_line_dedupe_key(
                oid,
                p,
                row.get(offer_col) if offer_col else "",
                row.get(sku_col) if sku_col else "",
                row.get(qty_col) if qty_col else 0,
            )
            for (_, row), oid, p in zip(df_filt.iterrows(), df_filt["_oid"], df_filt["_pdate"])
        ]
        new_mask = ~df_filt["_okey"].isin(existing_keys)

        # Filter stage and phone values to match
        indices_to_keep = df_filt[new_mask].index.tolist()
        stage_filtered = [stage[i] for i, idx in enumerate(df_filt.index) if idx in indices_to_keep]
        phone_filtered = [phone_values[i] for i, idx in enumerate(df_filt.index) if idx in indices_to_keep]
        fixed_filtered = [fixed_values_payload[i] for i, idx in enumerate(df_filt.index) if idx in indices_to_keep]

        dup_count = len(stage) - len(stage_filtered)
        if dup_count > 0:
            print(f"Skipped {dup_count} duplicates (same order_id + planned date already in CRM)")

        stage = stage_filtered
        phone_values = phone_filtered
        fixed_values_payload = fixed_filtered

    print(f"\n4. Appending new orders...")
    new_rows_added = len(stage)
    print(f"   Orders to append: {new_rows_added}")

    if len(stage) == 0:
        if updated_count > 0:
            print(f"   No new orders to append (updated {updated_count} existing orders)")
            if args.refresh_delivery_fees:
                refresh_from = _resolve_refresh_date(args.refresh_fees_from, today_local() - timedelta(days=1))
                refresh_to = _resolve_refresh_date(args.refresh_fees_to, today_local())
                backfilled = backfill_seller_delivery_fee(
                    args.crm_file,
                    args.sheet,
                    args.table,
                    refresh_from,
                    refresh_to,
                    dry_run=args.dry_run,
                    verbose=args.verbose,
                    snapshot=snapshot,
                )
                print(f"   Delivery fee backfill rows updated: {backfilled}")
            fixed_backfilled = maybe_run_fixed_backfill()
            if fixed_backfilled:
                print(f"   Fixed-value backfill rows updated: {fixed_backfilled}")
            sync_pending_orders_to_gdrive_safe(args.crm_file, end_date, args.dry_run)
            print(f"\n✅ Import complete! Updated {updated_count} orders, appended 0 new.")
            return finalize(result)
        else:
            print("   All orders already in CRM. Nothing to import or update.")
            print("   NO-OP: skipping Google Drive sync.")
            fixed_backfilled = maybe_run_fixed_backfill()
            if fixed_backfilled:
                print(f"   Fixed-value backfill rows updated: {fixed_backfilled}")
            return finalize(result)

    if args.dry_run:
        print("\n[DRY RUN] Would append but skipping.")
        print(json.dumps(stats, indent=2, ensure_ascii=False))
        return finalize(result)

    # Create backup before writing (Phase 12 / Excel safe ops)
    ensure_backup()

    # Append via xlwings - returns (start_row, end_row) for sync
    append_start_row, append_end_row = excel_append_xlwings(
        args.crm_file,
        args.sheet,
        args.table,
        date_abs,
        phone_abs,
        start_abs,
        end_abs,
        stage,
        phone_values,
        append_date,
        slice_headers,
        fixed_values_payload if args.fixed_values else None,
    )
    fixed_backfilled = maybe_run_fixed_backfill()
    if fixed_backfilled:
        print(f"   Fixed-value backfill rows updated: {fixed_backfilled}")

    # Archive source files
    archive_path = archive_run(args.orders_dir, source_files, df_filt)

    # Backfill seller delivery fee from Delivery_fee_kzt (if requested)
    if args.refresh_delivery_fees:
        refresh_from = _resolve_refresh_date(args.refresh_fees_from, today_local() - timedelta(days=1))
        refresh_to = _resolve_refresh_date(args.refresh_fees_to, today_local())
        backfilled = backfill_seller_delivery_fee(
            args.crm_file,
            args.sheet,
            args.table,
            refresh_from,
            refresh_to,
            dry_run=args.dry_run,
            verbose=args.verbose,
            snapshot=snapshot,
        )
        print(f"   Delivery fee backfill rows updated: {backfilled}")

    # Sync PENDING rows for target date to Google Drive (formatted copy)
    sync_pending_orders_to_gdrive_safe(args.crm_file, end_date, args.dry_run)

    print(f"\n✅ Import complete!")
    print(f"   Updated: {updated_count} existing orders")
    print(f"   Appended: {new_rows_added} new orders")
    print(f"   Archived: {archive_path}")
    result["orders_imported"] = new_rows_added
    result["orders_updated"] = updated_count

    # Phase 12 Part 6: Detailed statistics
    if new_rows_added > 0 and not args.dry_run:
        print("\n" + "=" * 60)
        print("  Import Statistics")
        print("=" * 60)

        # Get warehouse column for grouping
        colmap = map_headers(df_filt)
        if "warehouse" in colmap:
            store_counts = df_filt.groupby(colmap["warehouse"]).size()
            print("\n  Appended Orders by Store:")
            for store, count in sorted(store_counts.items()):
                print(f"    {store}: {count}")

        # Status summary
        if "status" in colmap:
            status_counts = df_filt.groupby(colmap["status"]).size()
            print("\n  Status Summary:")
            for status, count in sorted(status_counts.items()):
                print(f"    {status}: {count}")

        print(f"\n  Total Appended: {new_rows_added}")
        print(f"  Total in CRM (before): {len(existing_ids)}")
        print(f"  Total in CRM (after): {len(existing_ids) + new_rows_added}")
        print("=" * 60)

    return finalize(result)


if __name__ == "__main__":
    main()
