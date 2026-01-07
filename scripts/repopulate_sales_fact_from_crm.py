#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Repopulate sales_fact_v2 for a specific term (e.g. LINE51) using CRM data.

This is intended to correct recent-period data drift by replacing rows
in sales_fact_v2 that match the term within a date window.
"""

from __future__ import annotations

import argparse
import sqlite3
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Optional

import pandas as pd
from dateutil import parser as dtp

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DB = PROJECT_ROOT / "db" / "app.db"
DEFAULT_CRM = PROJECT_ROOT / "excel_ui" / "SALES_KSP_CRM_V3.xlsx"


STORE_CODE_MAP = {
    "30137883_PP1": "ACMEWEAR",
    "30000001_PP1": "UNIVERSAL",
    "30290083_PP1": "11KZ",
    "30000002_PP1": "STOREB",
    "STORE-B": "STOREB",
    "MELVIS": "MELVIS",
    "ACMEWEAR": "ACMEWEAR",
    "UNIVERSAL": "UNIVERSAL",
    "11KZ": "11KZ",
    "STOREB": "STOREB",
    "AcmeWear": "ACMEWEAR",
    "Universal": "UNIVERSAL",
}


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
    return s if s else None


def _norm_store(value: str) -> str:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return "UNKNOWN"
    raw = str(value).strip()
    if not raw:
        return "UNKNOWN"
    return STORE_CODE_MAP.get(raw, raw.upper())


def _pick_column(df: pd.DataFrame, candidates: list[str]) -> Optional[str]:
    for c in candidates:
        if c in df.columns:
            return c
    return None


def _derive_my_size(row: pd.Series) -> str:
    my_size = str(row.get("MY_SIZE", "")).strip()
    if my_size and my_size.lower() not in ("nan", "none"):
        return my_size
    sku_id = str(row.get("SKU_ID", "")).strip()
    if sku_id and sku_id.lower() not in ("nan", "none"):
        parts = sku_id.split("_")
        return parts[-1] if parts else ""
    return ""


def main() -> int:
    parser = argparse.ArgumentParser(description="Repopulate sales_fact_v2 from CRM for a term")
    parser.add_argument("--term", default="line51", help="Search term (case-insensitive)")
    parser.add_argument("--days", type=int, default=30, help="Lookback days (default: 30)")
    parser.add_argument("--date-end", default="max", help="End date YYYY-MM-DD or 'max'")
    parser.add_argument("--crm-file", type=Path, default=DEFAULT_CRM)
    parser.add_argument("--sheet", default="SALES_KSP_CRM_1")
    parser.add_argument("--db-path", type=Path, default=DEFAULT_DB)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    if not args.crm_file.exists():
        print(f"ERROR: CRM file not found: {args.crm_file}")
        return 1

    conn = sqlite3.connect(args.db_path)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    table = cur.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='sales_fact_v2'"
    ).fetchone()
    if not table:
        print("ERROR: sales_fact_v2 not found in DB")
        return 1

    if args.date_end == "max":
        max_date = cur.execute("SELECT MAX(order_date) AS d FROM sales_fact_v2").fetchone()["d"]
        if not max_date:
            print("ERROR: sales_fact_v2 has no dates")
            return 1
        end_date = datetime.strptime(max_date, "%Y-%m-%d").date()
    else:
        end_date = dtp.parse(args.date_end).date()

    start_date = end_date - timedelta(days=args.days - 1)

    df = pd.read_excel(args.crm_file, sheet_name=args.sheet)

    order_col = _pick_column(df, ["OrderID", "№ заказа"])
    date_col = _pick_column(df, ["Date", "Дата поступления заказа"])
    qty_col = _pick_column(df, ["Quantity", "Количество"])
    sku_key_col = _pick_column(df, ["SKU_key"])
    sku_id_col = _pick_column(df, ["SKU_ID"])
    offer_col = _pick_column(df, ["KASPI_OFFER_NAME", "Название товара в Kaspi Магазине"])
    article_col = _pick_column(df, ["Артикул"])
    store_col = _pick_column(df, ["STORE_NAME", "Склад передачи КД"])
    price_col = _pick_column(df, ["Sell_price_kzt", "Total_price", "Сумма"])
    delivery_col = _pick_column(df, ["Delivery_fee_kzt", "Стоимость доставки для продавца", "Стоимость доставки для покупателя"])
    net_rev_col = _pick_column(df, ["Total_net_rev"])
    status_col = _pick_column(df, ["Status", "Статус"])

    if not order_col or not date_col:
        print("ERROR: CRM missing required OrderID/Date columns")
        return 1

    term = args.term.lower()
    mask = pd.Series([False] * len(df))
    for c in [sku_key_col, sku_id_col, offer_col, article_col]:
        if c:
            mask |= df[c].astype(str).str.lower().str.contains(term, na=False)

    df = df[mask].copy()
    df["__date__"] = df[date_col].apply(_parse_date)
    df = df[df["__date__"].notna()]
    df = df[(df["__date__"] >= start_date) & (df["__date__"] <= end_date)]

    if df.empty:
        print("No CRM rows matched the criteria.")
        return 0

    # Normalize fields
    df["__order_id__"] = df[order_col].apply(_clean_order_id)
    df["__store__"] = df[store_col].apply(_norm_store) if store_col else "UNKNOWN"
    df["__sku_key__"] = df[sku_key_col].astype(str).str.strip() if sku_key_col else ""
    df["__sku_id__"] = df[sku_id_col].astype(str).str.strip() if sku_id_col else ""
    df["__offer__"] = df[offer_col].astype(str).str.strip() if offer_col else ""
    df["__qty__"] = df[qty_col].fillna(1).astype(int) if qty_col else 1
    df["__price__"] = pd.to_numeric(df[price_col], errors="coerce").fillna(0) if price_col else 0
    df["__delivery__"] = pd.to_numeric(df[delivery_col], errors="coerce").fillna(0) if delivery_col else 0
    df["__net_rev__"] = pd.to_numeric(df[net_rev_col], errors="coerce") if net_rev_col else None
    df["__status__"] = df[status_col].astype(str).str.strip() if status_col else ""
    df["__my_size__"] = df.apply(_derive_my_size, axis=1)

    df = df[df["__order_id__"].notna()]

    # Deduplicate
    df = df.drop_duplicates(
        subset=["__order_id__", "__sku_id__", "__date__", "__store__"],
        keep="last",
    )

    # Delete existing matching rows in sales_fact_v2
    like = f"%{term}%"
    delete_sql = """
        DELETE FROM sales_fact_v2
        WHERE order_date BETWEEN ? AND ?
          AND (
            LOWER(sku_key) LIKE ?
            OR LOWER(sku_id) LIKE ?
            OR LOWER(kaspi_offer_name) LIKE ?
          )
    """
    cur.execute(
        "SELECT COUNT(*) AS c FROM sales_fact_v2 WHERE order_date BETWEEN ? AND ?",
        (start_date.isoformat(), end_date.isoformat()),
    )
    before = cur.fetchone()["c"]

    cur.execute(
        "SELECT COUNT(*) AS c FROM sales_fact_v2 WHERE order_date BETWEEN ? AND ? "
        "AND (LOWER(sku_key) LIKE ? OR LOWER(sku_id) LIKE ? OR LOWER(kaspi_offer_name) LIKE ?)",
        (start_date.isoformat(), end_date.isoformat(), like, like, like),
    )
    to_delete = cur.fetchone()["c"]

    if args.dry_run:
        print(f"[DRY RUN] Would delete {to_delete} rows from sales_fact_v2")
    else:
        cur.execute(delete_sql, (start_date.isoformat(), end_date.isoformat(), like, like, like))

    # Insert replacements
    insert_sql = """
        INSERT INTO sales_fact_v2 (
            order_id, order_date, sku_key, sku_id, my_size, kaspi_offer_name,
            store_code, quantity, sell_price_kzt, delivery_fee, net_rev,
            status, return_flag, source_file
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """
    rows = []
    for _, row in df.iterrows():
        rows.append(
            (
                row["__order_id__"],
                row["__date__"].isoformat(),
                row["__sku_key__"] if row["__sku_key__"] != "nan" else "",
                row["__sku_id__"] if row["__sku_id__"] != "nan" else "",
                row["__my_size__"],
                row["__offer__"] if row["__offer__"] != "nan" else "",
                row["__store__"],
                int(row["__qty__"]),
                float(row["__price__"]),
                float(row["__delivery__"]),
                float(row["__net_rev__"]) if row["__net_rev__"] is not None else None,
                row["__status__"],
                0,
                args.crm_file.name,
            )
        )

    if args.dry_run:
        print(f"[DRY RUN] Would insert {len(rows)} rows into sales_fact_v2")
    else:
        cur.executemany(insert_sql, rows)
        conn.commit()

    print(f"Date window: {start_date} to {end_date}")
    print(f"Rows in window before: {before}")
    print(f"Rows deleted (term match): {to_delete}")
    print(f"Rows inserted from CRM: {len(rows)}")

    conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
