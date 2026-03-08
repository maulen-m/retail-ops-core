#!/usr/bin/env python3
"""Helpers for CRM North Star workbook normalization."""

from __future__ import annotations

from datetime import date, datetime
from pathlib import Path
from typing import Any

import pandas as pd


REQUIRED_CRM_COLUMNS = {
    "Date",
    "STORE_NAME",
    "Quantity",
    "OrderID",
    "SKU_key",
    "SKU_ID",
    "Total_net_rev",
}

REQUIRED_RECON_COLUMNS = {
    "№ заказа",
    "Дата изменения статуса",
    "Статус",
}

DELIVERED_STATUSES = {
    "ВЫДАН",
    "ЗАВЕРШЕН",
    "ЗАВЕРШЁН",
    "DELIVERED",
    "COMPLETED",
}
CANCELLED_STATUSES = {
    "ОТМЕНЕН",
    "ОТМЕНЁН",
    "ОТМЕНЕН ПРИ ДОСТАВКЕ",
    "ОТМЕНЁН ПРИ ДОСТАВКЕ",
    "CANCELLED",
}
RETURNED_STATUSES = {
    "ВОЗВРАТ",
    "ВОЗВРАЩЕН",
    "ВОЗВРАЩЁН",
    "ВОЗВРАТ В ПУТИ",
    "RETURNED",
    "RETURN",
}

STORE_ALIAS = {
    "UNIVERSAL": "UNIVERSAL",
    "UNIVERSAL (TEST STORE)": "UNIVERSAL",
    "STORE-B": "STOREB",
    "STOREB": "STOREB",
    "ACMEWEAR": "ACMEWEAR",
    "MELVIS": "MELVIS",
    "11KZ": "11KZ",
}


def normalize_store_code(raw: Any) -> str:
    if raw is None:
        return "UNIVERSAL"
    text = str(raw).strip().upper()
    return STORE_ALIAS.get(text, text.replace(" ", "_").replace("-", "_"))


def _parse_date(value: Any) -> str | None:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    text = str(value).strip()
    if not text:
        return None
    for fmt in ("%d.%m.%Y", "%Y-%m-%d", "%d/%m/%Y"):
        try:
            return datetime.strptime(text, fmt).date().isoformat()
        except ValueError:
            continue
    try:
        return pd.to_datetime(text, errors="raise").date().isoformat()
    except Exception:
        return None


def _to_float(value: Any) -> float:
    if value is None:
        return 0.0
    if isinstance(value, (int, float)):
        if pd.isna(value):
            return 0.0
        return float(value)
    text = str(value).replace(" ", "").replace(",", ".").strip()
    if not text:
        return 0.0
    try:
        return float(text)
    except ValueError:
        return 0.0


def _to_int_str(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, float):
        if pd.isna(value):
            return ""
        if value.is_integer():
            return str(int(value))
    text = str(value).strip()
    if text.endswith(".0"):
        text = text[:-2]
    return text


def load_crm_workbook(path: Path) -> pd.DataFrame:
    if not path.exists():
        raise FileNotFoundError(f"CRM workbook not found: {path}")
    df = pd.read_excel(path, sheet_name="Archive_sales", dtype=object)
    missing = sorted(REQUIRED_CRM_COLUMNS - set(df.columns))
    if missing:
        raise ValueError(f"CRM workbook schema drift. Missing columns: {', '.join(missing)}")

    out = pd.DataFrame()
    out["order_id"] = df["OrderID"].map(_to_int_str)
    out["sale_date"] = df["Date"].map(_parse_date)
    out["store_code"] = df["STORE_NAME"].map(normalize_store_code)
    out["sku_key"] = df["SKU_key"].fillna("").map(lambda x: str(x).strip())
    out["sku_id"] = df["SKU_ID"].fillna("").map(lambda x: str(x).strip())
    out["units"] = df["Quantity"].map(_to_float)
    out["net_rev_kzt"] = df["Total_net_rev"].map(_to_float)
    out["source"] = "crm_workbook"
    out = out[(out["order_id"] != "") & out["sale_date"].notna()].copy()
    return out


def normalize_status_internal(value: Any) -> str:
    if value is None:
        return "UNKNOWN"
    text = str(value).strip().upper()
    if text in DELIVERED_STATUSES:
        return "DELIVERED"
    if text in CANCELLED_STATUSES:
        return "CANCELLED"
    if text in RETURNED_STATUSES:
        return "RETURNED"
    return text or "UNKNOWN"


def _normalize_status(value: Any) -> str:
    return normalize_status_internal(value)


def load_reconciled_workbook(path: Path) -> pd.DataFrame:
    if not path.exists():
        raise FileNotFoundError(f"Reconciled workbook not found: {path}")
    sheet_name = "sales_daily_sku_size_2024-06-06"
    df = pd.read_excel(path, sheet_name=sheet_name, dtype=object)
    missing = sorted(REQUIRED_RECON_COLUMNS - set(df.columns))
    if missing:
        raise ValueError(
            "Reconciled workbook schema drift. "
            f"Missing columns: {', '.join(missing)}"
        )

    out = pd.DataFrame()
    out["order_id"] = df["№ заказа"].map(_to_int_str)
    out["status_internal"] = df["Статус"].map(normalize_status_internal)
    out["status_change_date"] = df["Дата изменения статуса"].map(_parse_date)
    out["source"] = "reconciled_workbook"
    out = out[out["order_id"] != ""].copy()
    if out.empty:
        return out
    out = out.sort_values(["order_id", "status_change_date"]).drop_duplicates(
        subset=["order_id"], keep="last"
    )
    return out


def load_db_truth(
    db_path: Path,
    start: str,
    end: str,
) -> pd.DataFrame:
    query = """
        SELECT
            CAST(order_id AS TEXT) AS order_id,
            date(sale_date) AS sale_date,
            UPPER(TRIM(COALESCE(store_code, 'UNIVERSAL'))) AS store_code,
            COALESCE(sku_key, '') AS sku_key,
            COALESCE(sku_id, '') AS sku_id,
            CAST(COALESCE(units, 0) AS REAL) AS units,
            CAST(COALESCE(net_rev_kzt, 0) AS REAL) AS net_rev_kzt,
            CAST(COALESCE(cogs_kzt, 0) AS REAL) AS cogs_kzt,
            COALESCE(cogs_source, 'unresolved') AS cogs_source
        FROM view_sales_line_truth
        WHERE date(sale_date) BETWEEN date(?) AND date(?)
    """
    import sqlite3

    conn = sqlite3.connect(str(db_path))
    try:
        out = pd.read_sql_query(query, conn, params=[start, end])
    finally:
        conn.close()
    out["source"] = "db_truth"
    return out


def apply_status_bridge(crm_df: pd.DataFrame, reconciled_df: pd.DataFrame) -> pd.DataFrame:
    if reconciled_df.empty:
        out = crm_df.copy()
        out["bridge_status"] = "UNKNOWN"
        out["bridge_status_date"] = out["sale_date"]
        out["bridge_date_verified"] = False
        out["bridge_date_source"] = "crm_sale_date"
        out["bridge_excluded"] = True
        return out

    merged = crm_df.merge(
        reconciled_df[["order_id", "status_internal", "status_change_date"]],
        on="order_id",
        how="left",
    )
    merged["bridge_status"] = merged["status_internal"].fillna("UNKNOWN")
    merged["bridge_date_verified"] = merged["status_change_date"].notna()
    merged["bridge_status_date"] = merged["status_change_date"].fillna(merged["sale_date"])
    merged["bridge_date_source"] = merged["bridge_date_verified"].map(
        {True: "reconciled_status_change_date", False: "crm_sale_date"}
    )
    merged["bridge_excluded"] = merged["bridge_status"] != "DELIVERED"
    merged = merged.drop(columns=["status_internal", "status_change_date"])
    return merged
