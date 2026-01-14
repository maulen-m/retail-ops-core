#!/usr/bin/env python3
"""
Reconcile Kaspi ArchiveOrders exports into Y (archive DB) and Z (experimental DB).

Steps:
1) Merge all ArchiveOrders Excel files into Y DB (kaspi_orders_raw table).
2) Copy base DB into Z.
3) Build kaspi_offer_name -> sku_key mapping from 2025-08-01 onward (DB + CRM archive).
4) Build per-offer size mix for PB_SIZE inference (clothes only).
5) Update Z order statuses/fields from Y; insert missing orders with inferred sku_key/size.

Usage:
  python scripts/reconcile_kaspi_archive_orders.py \
    --archive-dir "/path/to/Kaspi_orders_data_Important" \
    --crm-archive "/path/to/SALES_KSP_CRM_V3.xlsx" \
    --output-y "db/experiments/orders_Y.db" \
    --output-z "db/experiments/orders_Z.db"
"""

from __future__ import annotations

import argparse
import re
import sqlite3
import shutil
from dataclasses import dataclass
from datetime import datetime, date
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_BASE_DB = PROJECT_ROOT / "db" / "app.db"


ARCHIVE_COLS = {
    "№ заказа": "order_id",
    "Дата поступления заказа": "order_date",
    "Название товара в Kaspi Магазине": "kaspi_offer_name",
    "Название в системе продавца": "seller_name",
    "Артикул": "article",
    "Сумма": "amount_kzt",
    "Категория": "category",
    "Адрес самовывоза/доставки": "delivery_address",
    "Дата изменения статуса": "status_updated_at",
    "Статус": "kaspi_status",
    "Причина отмены": "cancel_reason",
    "Способ оплаты": "payment_method",
    "Способ доставки": "delivery_method",
    "Курьерская служба": "courier_service",
    "Принял": "accepted_by",
    "Выдал": "issued_by",
    "Отменил": "cancelled_by",
    "Оценка покупателя": "rating",
    "Отзыв покупателя": "review",
    "Дата публикации отзыва": "review_date",
    "Оформил": "ordered_by",
    "Количество": "quantity",
    "Стоимость доставки для покупателя": "delivery_fee_customer",
    "Стоимость доставки для продавца": "delivery_fee_seller",
    "Компенсация за доставку": "delivery_compensation",
    "Требуется подписание": "signature_required",
    "Плановая дата передачи курьеру": "planned_shipment_date",
    "Склад передачи КД": "kd_warehouse",
}

MANUAL_OFFER_RULES = [
    ("Epson L3218", "ELS_PRINTER_EPSON_L3218_BLACK"),
    ("Epson L3251", "ELS_PRINTER_EPSON_L3251_BLACK"),
    ("Epson L805", "ELS_PRINTER_EPSON_L805_BLACK"),
    ("Marshall Major IV", "ELS_headphones_Marshall_4"),
    ("Marshall Major V", "ELS_headphones_Marshall_5"),
    ("Epson L1800", "ELS_EPSON_PRINTER_L1800_BLACK"),
    ("70mai", "ELS_70mai_Midrive_BLACK"),
    ("Midrive UP03", "ELS_70mai_Midrive_BLACK"),
    ("Canada Goose 1101", "CL_in_MEN_TERMO-canada_BLACK"),
    ("GM SPORT 2882", "CL_in_WOMEN_TERMO-TNF_RED"),
    ("PRO COMBAT однотонный 245", "CL_OC_MEN_LINE52_BLACK"),
    ("Fashion 24052024", "CL_OC_MEN_LINE52_BLACK"),
    ("FIT 719879020", "CL_OC_MEN_LINE52_BLACK"),
]

DROP_OFFER_TOKENS = [
    "Скелет Натуральный",
]

GENERIC_SIZE_ORDER = ["XXS", "XS", "S", "M", "L", "XL", "2XL", "3XL", "4XL"]

INACTIVE_SKU_KEYS = {
    "ELS_EPSON_PRINTER_L1800_BLACK",
    "ELS_70mai_Midrive_BLACK",
    "CL_in_MEN_TERMO-canada_BLACK",
    "CL_in_WOMEN_TERMO-TNF_RED",
}

DATE_COLS = [
    "order_date",
    "status_updated_at",
    "review_date",
    "planned_shipment_date",
]

NUM_COLS = [
    "amount_kzt",
    "quantity",
    "delivery_fee_customer",
    "delivery_fee_seller",
    "delivery_compensation",
    "rating",
]


@dataclass
class OutputPaths:
    y_db: Path
    z_db: Path


def _store_code_from_path(path: Path) -> str:
    for part in path.parts:
        if part.startswith("Universal"):
            return "UNIVERSAL"
        if part.startswith("ACMEWEAR") or part.startswith("AcmeWear"):
            return "ACMEWEAR"
        if part.startswith("11KZ"):
            return "11KZ"
        if part.startswith("STORE-B") or part.startswith("STORE_B"):
            return "STOREB"
        if part.startswith("MELVIS"):
            return "MELVIS"
    return "UNKNOWN"


def _coerce_dates(df: pd.DataFrame) -> pd.DataFrame:
    for col in DATE_COLS:
        if col in df.columns:
            df[col] = pd.to_datetime(df[col], errors="coerce", dayfirst=True).dt.date
            df[col] = df[col].apply(lambda d: d.isoformat() if pd.notna(d) else None)
    return df


def _coerce_numbers(df: pd.DataFrame) -> pd.DataFrame:
    for col in NUM_COLS:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    return df


def _load_archive_file(path: Path) -> pd.DataFrame:
    df = pd.read_excel(path, dtype=str)
    missing = [col for col in ARCHIVE_COLS if col not in df.columns]
    if missing:
        raise ValueError(f"Missing expected columns in {path.name}: {missing}")
    df = df[list(ARCHIVE_COLS.keys())].rename(columns=ARCHIVE_COLS)
    df["source_file"] = str(path)
    df["store_code"] = _store_code_from_path(path)
    return df


def load_archive_exports(source_dir: Path) -> pd.DataFrame:
    files = sorted(
        p for p in source_dir.rglob("*.xlsx")
        if not p.name.startswith("~$")
    )
    if not files:
        raise FileNotFoundError(f"No .xlsx files found under {source_dir}")
    frames = []
    for path in files:
        frames.append(_load_archive_file(path))
    df = pd.concat(frames, ignore_index=True)
    df = _coerce_dates(df)
    df = _coerce_numbers(df)
    df["order_id"] = df["order_id"].astype(str).str.strip()
    df["kaspi_offer_name"] = df["kaspi_offer_name"].astype(str).str.strip()
    df["store_code"] = df["store_code"].astype(str).str.strip()
    df["quantity"] = df["quantity"].fillna(0).astype(int)
    for token in DROP_OFFER_TOKENS:
        df = df[~df["kaspi_offer_name"].str.contains(token, case=False, na=False)]
    df["unit_price_kzt"] = df.apply(
        lambda r: (r["amount_kzt"] / r["quantity"]) if r.get("quantity") else None,
        axis=1,
    )
    # Deduplicate by (store_code, order_id, kaspi_offer_name, order_date) keeping latest status
    df = df.sort_values(by=["status_updated_at"], na_position="last")
    df = df.drop_duplicates(
        subset=["store_code", "order_id", "kaspi_offer_name", "order_date"],
        keep="last",
    )
    return df


def write_y_db(df: pd.DataFrame, y_db: Path) -> None:
    y_db.parent.mkdir(parents=True, exist_ok=True)
    if y_db.exists():
        y_db.unlink()
    conn = sqlite3.connect(str(y_db))
    df.to_sql("kaspi_orders_raw", conn, if_exists="replace", index=False)
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_kaspi_orders_raw_key "
        "ON kaspi_orders_raw(store_code, order_id, kaspi_offer_name)"
    )
    conn.commit()
    conn.close()


def copy_base_db(base_db: Path, z_db: Path) -> None:
    if not base_db.exists():
        raise FileNotFoundError(f"Base DB not found: {base_db}")
    z_db.parent.mkdir(parents=True, exist_ok=True)
    if z_db.exists():
        z_db.unlink()
    shutil.copy2(base_db, z_db)


def _normalize_text(value) -> str | None:
    if value is None or pd.isna(value):
        return None
    text = str(value).strip()
    return text if text else None


def load_crm_sales(crm_path: Path) -> pd.DataFrame:
    usecols = [
        "Date",
        "STORE_NAME",
        "OrderID",
        "KASPI_OFFER_NAME",
        "SKU_key",
        "MY_SIZE",
        "Quantity",
    ]
    frames = []
    for sheet in ["Archive_sales", "SALES_KSP_CRM_1"]:
        try:
            df = pd.read_excel(crm_path, sheet_name=sheet, usecols=usecols, dtype=str)
        except ValueError:
            continue
        df["source_sheet"] = sheet
        frames.append(df)
    if not frames:
        raise ValueError("CRM workbook missing expected sheets for sales mapping")
    df = pd.concat(frames, ignore_index=True)

    df = df[df["OrderID"].notna()].copy()
    df["order_id"] = df["OrderID"].apply(_normalize_text)
    df["kaspi_offer_name"] = df["KASPI_OFFER_NAME"].apply(_normalize_text)
    df["sku_key"] = df["SKU_key"].apply(_normalize_text)
    df["my_size"] = df["MY_SIZE"].apply(_normalize_text)
    df["store_name"] = df["STORE_NAME"].apply(_normalize_text)
    store_map = {
        "Universal": "UNIVERSAL",
        "AcmeWear": "ACMEWEAR",
        "11KZ": "11KZ",
        "STORE-B": "STOREB",
        "MELVIS": "MELVIS",
    }
    df["store_code"] = df["store_name"].map(store_map).fillna(df["store_name"].str.upper())
    df["order_date"] = pd.to_datetime(df["Date"], errors="coerce").dt.date
    df = df[df["order_date"].notna()].copy()
    df["quantity"] = pd.to_numeric(df["Quantity"], errors="coerce").fillna(0).astype(int)
    return df


def load_db_sales(conn: sqlite3.Connection, since: date) -> pd.DataFrame:
    queries = [
        (
            """
            SELECT order_date, store_code, order_id, kaspi_offer_name, sku_key, my_size, quantity
            FROM fact_sales
            WHERE order_date >= ?
            """,
            (since.isoformat(),),
        ),
        (
            """
            SELECT order_date, store_code, order_id, kaspi_offer_name, sku_key, my_size, quantity
            FROM sales_fact_v2
            WHERE order_date >= ?
            """,
            (since.isoformat(),),
        ),
        (
            """
            SELECT created_at as order_date, store_code, order_id, kaspi_offer_name, sku_key, my_size, quantity
            FROM fact_orders_kaspi
            WHERE created_at >= ?
            """,
            (since.isoformat(),),
        ),
    ]
    frames = []
    for sql, params in queries:
        try:
            frames.append(pd.read_sql_query(sql, conn, params=params))
        except Exception:
            continue
    if not frames:
        return pd.DataFrame(columns=["order_date", "store_code", "order_id", "kaspi_offer_name", "sku_key", "my_size", "quantity"])
    df = pd.concat(frames, ignore_index=True)
    for col in ["order_id", "kaspi_offer_name", "sku_key", "my_size", "store_code"]:
        if col in df.columns:
            df[col] = df[col].apply(_normalize_text)
    df["order_date"] = pd.to_datetime(df["order_date"], errors="coerce").dt.date
    df = df[df["order_date"].notna()].copy()
    df["quantity"] = pd.to_numeric(df["quantity"], errors="coerce").fillna(0).astype(int)
    df = df.drop_duplicates(
        subset=["order_date", "store_code", "order_id", "kaspi_offer_name", "sku_key", "my_size", "quantity"]
    )
    return df


def _build_size_map(
    dim_sku_size: pd.DataFrame,
    dim_sku: pd.DataFrame,
) -> tuple[dict[str, tuple[dict[str, str], list[str]]], dict[str, str], dict[str, str]]:
    size_map: dict[str, tuple[dict[str, str], list[str]]] = {}
    single_size_map: dict[str, str] = {}
    els_default_map: dict[str, str] = {}
    product_types = dict(dim_sku[["sku_key", "product_type"]].values)
    sku_id_sizes = (
        dim_sku_size.loc[dim_sku_size["sku_id"] == dim_sku_size["sku_key"], ["sku_key", "my_size"]]
        .dropna()
        .drop_duplicates(subset=["sku_key"])
    )
    sku_id_size_map = dict(sku_id_sizes.values)
    grouped = dim_sku_size.groupby("sku_key")["my_size"].apply(list).reset_index()
    for _, row in grouped.iterrows():
        sizes = [s for s in row["my_size"] if s and str(s).strip()]
        sizes_upper = {str(s).upper(): str(s) for s in sizes}
        sizes_sorted = sorted(sizes_upper.keys(), key=len, reverse=True)
        size_map[row["sku_key"]] = (sizes_upper, sizes_sorted)
        if len(sizes_upper) == 1:
            single_size_map[row["sku_key"]] = next(iter(sizes_upper.values()))
        if product_types.get(row["sku_key"]) == "ELS":
            default_size = "ONE_SIZE"
            if default_size in sizes_upper:
                default_size = sizes_upper[default_size]
            els_default_map[row["sku_key"]] = default_size
    return size_map, single_size_map, els_default_map


def _infer_sku_key_from_article(article: str | None, sku_keys_sorted: list[str]) -> str | None:
    if not article:
        return None
    text = str(article).strip()
    if not text:
        return None
    for key in sku_keys_sorted:
        if text.startswith(key):
            return key
    for key in sku_keys_sorted:
        if key in text:
            return key
    return None


def _manual_offer_map(kaspi_offer_name: str | None) -> str | None:
    if not kaspi_offer_name:
        return None
    text = str(kaspi_offer_name).lower()
    for token, sku_key in MANUAL_OFFER_RULES:
        if token.lower() in text:
            return sku_key
    return None


def _infer_size_from_text(text: str | None, sizes_upper: dict[str, str], sizes_sorted: list[str]) -> str | None:
    if not text:
        return None
    blob = str(text).upper()
    for match in re.findall(r"\(([^)]+)\)", blob):
        candidate = match.strip()
        if candidate in sizes_upper:
            return sizes_upper[candidate]
    for size_key in sizes_sorted:
        pattern = rf"(?<![A-Z0-9]){re.escape(size_key)}(?![A-Z0-9])"
        if re.search(pattern, blob):
            return sizes_upper[size_key]
    return None


def _infer_generic_size(text: str | None) -> str | None:
    if not text:
        return None
    blob = str(text).upper()
    for token in GENERIC_SIZE_ORDER:
        pattern = rf"(?<![A-Z0-9]){re.escape(token)}(?![A-Z0-9])"
        if re.search(pattern, blob):
            return token
    match = re.search(r"(?<!\\d)(2[2-9]|30)(?!\\d)", blob)
    if match:
        return match.group(1)
    return None


def _infer_size_from_row(row: pd.Series, size_map: dict[str, tuple[dict[str, str], list[str]]]) -> tuple[str | None, str | None]:
    sku_key = row.get("sku_key_final")
    if not sku_key or sku_key not in size_map:
        return None, None
    sizes_upper, sizes_sorted = size_map[sku_key]
    for source, text in [
        ("ARTICLE", row.get("article")),
        ("OFFER_NAME", row.get("kaspi_offer_name")),
        ("SELLER_NAME", row.get("seller_name")),
    ]:
        size = _infer_size_from_text(text, sizes_upper, sizes_sorted)
        if size:
            return size, source
    return None, None


def build_offer_map(db_sales: pd.DataFrame, crm_sales: pd.DataFrame) -> pd.DataFrame:
    db_counts = (
        db_sales.groupby(["kaspi_offer_name", "sku_key"])["quantity"]
        .sum()
        .reset_index()
        .rename(columns={"quantity": "count_db"})
    )
    crm_counts = (
        crm_sales.groupby(["kaspi_offer_name", "sku_key"])["quantity"]
        .sum()
        .reset_index()
        .rename(columns={"quantity": "count_crm"})
    )
    merged = pd.merge(db_counts, crm_counts, on=["kaspi_offer_name", "sku_key"], how="outer").fillna(0)
    merged["count_total"] = merged["count_db"] + merged["count_crm"]
    merged["count_total"] = merged["count_total"].astype(int)

    # Pick majority sku_key per offer (tie-breaker: DB count)
    merged = merged.sort_values(
        by=["kaspi_offer_name", "count_total", "count_db"],
        ascending=[True, False, False],
    )
    majority = merged.groupby("kaspi_offer_name").head(1).copy()
    total_by_offer = merged.groupby("kaspi_offer_name")["count_total"].sum().reset_index()
    majority = majority.merge(total_by_offer, on="kaspi_offer_name", suffixes=("", "_offer"))
    majority["share_total"] = majority.apply(
        lambda r: (r["count_total"] / r["count_total_offer"]) if r["count_total_offer"] else 0,
        axis=1,
    )
    return majority[["kaspi_offer_name", "sku_key", "count_db", "count_crm", "count_total", "share_total"]]


def build_size_mix(db_sales: pd.DataFrame, crm_sales: pd.DataFrame) -> pd.DataFrame:
    combined = pd.concat([
        db_sales[["kaspi_offer_name", "my_size", "quantity"]],
        crm_sales[["kaspi_offer_name", "my_size", "quantity"]],
    ], ignore_index=True)
    combined = combined[combined["my_size"].notna() & (combined["my_size"] != "")]
    size_counts = combined.groupby(["kaspi_offer_name", "my_size"])["quantity"].sum().reset_index()
    total = size_counts.groupby("kaspi_offer_name")["quantity"].sum().reset_index().rename(columns={"quantity": "total_qty"})
    size_counts = size_counts.merge(total, on="kaspi_offer_name")
    size_counts["share"] = size_counts.apply(
        lambda r: (r["quantity"] / r["total_qty"]) if r["total_qty"] else 0,
        axis=1,
    )
    return size_counts


def attach_mappings(
    y_df: pd.DataFrame,
    offer_map: pd.DataFrame,
    size_mix: pd.DataFrame,
    dim_sku: pd.DataFrame,
    crm_sales: pd.DataFrame,
    sku_keys_sorted: list[str],
    size_map: dict[str, tuple[dict[str, str], list[str]]],
    single_size_map: dict[str, str],
    els_default_map: dict[str, str],
) -> pd.DataFrame:
    crm_lookup = crm_sales[["store_code", "order_id", "kaspi_offer_name", "sku_key", "my_size"]].copy()
    crm_lookup = crm_lookup.drop_duplicates(subset=["store_code", "order_id", "kaspi_offer_name"])
    y_df = y_df.merge(
        crm_lookup,
        on=["store_code", "order_id", "kaspi_offer_name"],
        how="left",
        suffixes=("", "_crm"),
    )
    offer_map = offer_map.rename(columns={"sku_key": "sku_key_map"})
    y_df = y_df.merge(offer_map, on="kaspi_offer_name", how="left")
    y_df["sku_key_article"] = y_df["article"].apply(lambda a: _infer_sku_key_from_article(a, sku_keys_sorted))
    y_df["sku_key_manual"] = y_df["kaspi_offer_name"].apply(_manual_offer_map)
    y_df["sku_key_final"] = (
        y_df["sku_key"]
        .fillna(y_df["sku_key_article"])
        .fillna(y_df["sku_key_manual"])
        .fillna(y_df["sku_key_map"])
    )

    # Join product type for clothes check
    dim_sku = dim_sku[["sku_key", "product_type"]].rename(columns={"sku_key": "sku_key_final"})
    y_df = y_df.merge(dim_sku, on="sku_key_final", how="left")

    # Size mix for pb_size
    size_mix = size_mix.sort_values(by=["kaspi_offer_name", "share"], ascending=[True, False])
    pb = size_mix.groupby("kaspi_offer_name").head(1).copy()
    pb = pb.rename(columns={"my_size": "pb_size", "share": "pb_size_share"})
    y_df = y_df.merge(pb[["kaspi_offer_name", "pb_size", "pb_size_share"]], on="kaspi_offer_name", how="left")

    # Apply size: prefer CRM size, else infer from text, else PB size for clothes
    y_df["my_size_final"] = y_df["my_size"]
    y_df["size_source_final"] = None
    y_df.loc[y_df["my_size_final"].notna(), "size_source_final"] = "CRM"

    needs_size = y_df["my_size_final"].isna()
    inferred = y_df[needs_size].apply(lambda r: _infer_size_from_row(r, size_map), axis=1, result_type="expand")
    if not inferred.empty:
        y_df.loc[needs_size, "my_size_final"] = inferred[0]
        y_df.loc[needs_size, "size_source_final"] = inferred[1]

    clothes_mask = y_df["product_type"] == "CL"
    pb_mask = clothes_mask & y_df["my_size_final"].isna()
    y_df.loc[pb_mask, "my_size_final"] = y_df.loc[pb_mask, "pb_size"]
    y_df.loc[pb_mask, "size_source_final"] = "PB_SIZE"
    y_df["size_confidence_final"] = y_df["pb_size_share"].where(y_df["size_source_final"] == "PB_SIZE")

    single_mask = y_df["my_size_final"].isna() & y_df["sku_key_final"].isin(single_size_map)
    if single_mask.any():
        y_df.loc[single_mask, "my_size_final"] = y_df.loc[single_mask, "sku_key_final"].map(single_size_map)
        y_df.loc[single_mask, "size_source_final"] = "SKU_ONLY"

    els_mask = y_df["my_size_final"].isna() & y_df["sku_key_final"].isin(els_default_map)
    if els_mask.any():
        y_df.loc[els_mask, "my_size_final"] = y_df.loc[els_mask, "sku_key_final"].map(els_default_map)
        y_df.loc[els_mask, "size_source_final"] = "ELS_DEFAULT"

    generic_mask = y_df["my_size_final"].isna()
    if generic_mask.any():
        generic_sizes = y_df.loc[generic_mask, "kaspi_offer_name"].apply(_infer_generic_size)
        y_df.loc[generic_mask, "my_size_final"] = generic_sizes
        y_df.loc[generic_mask & y_df["my_size_final"].notna(), "size_source_final"] = "OFFER_TEXT"

    unknown_els_mask = y_df["my_size_final"].isna() & y_df["sku_key_final"].fillna("").str.startswith("ELS_")
    if unknown_els_mask.any():
        y_df.loc[unknown_els_mask, "my_size_final"] = "ONE_SIZE"
        y_df.loc[unknown_els_mask, "size_source_final"] = "ELS_DEFAULT"

    return y_df


def update_z_db(
    z_db: Path,
    y_df: pd.DataFrame,
    offer_map: pd.DataFrame,
    size_mix: pd.DataFrame,
    offer_size_stats: pd.DataFrame | None = None,
) -> dict[str, int]:
    conn = sqlite3.connect(str(z_db))
    conn.row_factory = sqlite3.Row

    ensure_catalog_entries(conn, y_df)

    # Store mapping tables
    offer_map.to_sql("kaspi_offer_map", conn, if_exists="replace", index=False)
    size_mix.to_sql("kaspi_offer_size_mix", conn, if_exists="replace", index=False)
    if offer_size_stats is not None:
        offer_size_stats.to_sql("kaspi_offer_size_stats", conn, if_exists="replace", index=False)

    # Prepare Y table in Z
    y_table = y_df[[
        "store_code", "order_id", "kaspi_offer_name", "order_date", "quantity",
        "unit_price_kzt", "kaspi_status", "status_updated_at", "planned_shipment_date",
        "sku_key_final", "my_size_final", "size_source_final", "size_confidence_final", "pb_size_share", "source_file",
    ]].copy()
    y_table = y_table.rename(columns={
        "sku_key_final": "sku_key",
        "my_size_final": "my_size",
        "size_source_final": "size_source",
        "size_confidence_final": "size_confidence",
    })
    y_table.to_sql("kaspi_orders_y", conn, if_exists="replace", index=False)
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_kaspi_orders_y_key "
        "ON kaspi_orders_y(store_code, order_id, kaspi_offer_name)"
    )
    # Attach sku_id based on sku_key + my_size
    conn.execute("ALTER TABLE kaspi_orders_y ADD COLUMN sku_id TEXT")
    conn.execute(
        """
        UPDATE kaspi_orders_y
        SET sku_id = (
            SELECT ds.sku_id
            FROM dim_sku_size ds
            WHERE ds.sku_key = kaspi_orders_y.sku_key
              AND ds.my_size = kaspi_orders_y.my_size
            LIMIT 1
        )
        """
    )

    # Update existing orders with missing fields
    conn.execute(
        """
        UPDATE fact_orders_kaspi
        SET kaspi_status = CASE
                WHEN y.kaspi_status IS NOT NULL AND (
                     fact_orders_kaspi.kaspi_status IS NULL
                     OR fact_orders_kaspi.kaspi_status = ''
                     OR fact_orders_kaspi.status_updated_at IS NULL
                     OR y.status_updated_at >= fact_orders_kaspi.status_updated_at
                ) THEN y.kaspi_status
                ELSE fact_orders_kaspi.kaspi_status
            END,
            status_updated_at = CASE
                WHEN y.status_updated_at IS NOT NULL AND (
                     fact_orders_kaspi.status_updated_at IS NULL
                     OR y.status_updated_at >= fact_orders_kaspi.status_updated_at
                ) THEN y.status_updated_at
                ELSE fact_orders_kaspi.status_updated_at
            END,
            planned_shipment_date = COALESCE(fact_orders_kaspi.planned_shipment_date, y.planned_shipment_date),
            quantity = COALESCE(fact_orders_kaspi.quantity, y.quantity),
            unit_price_kzt = COALESCE(fact_orders_kaspi.unit_price_kzt, y.unit_price_kzt),
            kaspi_offer_name = COALESCE(fact_orders_kaspi.kaspi_offer_name, y.kaspi_offer_name),
            sku_key = COALESCE(fact_orders_kaspi.sku_key, y.sku_key),
            my_size = COALESCE(fact_orders_kaspi.my_size, y.my_size),
            assigned_size = COALESCE(fact_orders_kaspi.assigned_size, y.my_size),
            size_source = COALESCE(fact_orders_kaspi.size_source, y.size_source),
            size_confidence = COALESCE(fact_orders_kaspi.size_confidence, y.size_confidence)
        FROM kaspi_orders_y y
        WHERE fact_orders_kaspi.store_code = y.store_code
          AND fact_orders_kaspi.order_id = y.order_id
          AND fact_orders_kaspi.kaspi_offer_name = y.kaspi_offer_name
        """
    )
    # Secondary update by sku_id (handles mismatched offer names)
    conn.execute(
        """
        UPDATE fact_orders_kaspi
        SET kaspi_status = CASE
                WHEN y.kaspi_status IS NOT NULL AND (
                     fact_orders_kaspi.kaspi_status IS NULL
                     OR fact_orders_kaspi.kaspi_status = ''
                     OR fact_orders_kaspi.status_updated_at IS NULL
                     OR y.status_updated_at >= fact_orders_kaspi.status_updated_at
                ) THEN y.kaspi_status
                ELSE fact_orders_kaspi.kaspi_status
            END,
            status_updated_at = CASE
                WHEN y.status_updated_at IS NOT NULL AND (
                     fact_orders_kaspi.status_updated_at IS NULL
                     OR y.status_updated_at >= fact_orders_kaspi.status_updated_at
                ) THEN y.status_updated_at
                ELSE fact_orders_kaspi.status_updated_at
            END,
            planned_shipment_date = COALESCE(fact_orders_kaspi.planned_shipment_date, y.planned_shipment_date),
            quantity = COALESCE(fact_orders_kaspi.quantity, y.quantity),
            unit_price_kzt = COALESCE(fact_orders_kaspi.unit_price_kzt, y.unit_price_kzt),
            kaspi_offer_name = COALESCE(fact_orders_kaspi.kaspi_offer_name, y.kaspi_offer_name),
            sku_key = COALESCE(fact_orders_kaspi.sku_key, y.sku_key),
            my_size = COALESCE(fact_orders_kaspi.my_size, y.my_size),
            assigned_size = COALESCE(fact_orders_kaspi.assigned_size, y.my_size),
            size_source = COALESCE(fact_orders_kaspi.size_source, y.size_source),
            size_confidence = COALESCE(fact_orders_kaspi.size_confidence, y.size_confidence)
        FROM kaspi_orders_y y
        WHERE fact_orders_kaspi.store_code = y.store_code
          AND fact_orders_kaspi.order_id = y.order_id
          AND fact_orders_kaspi.sku_id = y.sku_id
          AND y.sku_id IS NOT NULL
        """
    )

    # Fill sku_id where possible
    conn.execute(
        """
        UPDATE fact_orders_kaspi
        SET sku_id = (
            SELECT ds.sku_id
            FROM dim_sku_size ds
            WHERE ds.sku_key = fact_orders_kaspi.sku_key
              AND ds.my_size = fact_orders_kaspi.my_size
            LIMIT 1
        )
        WHERE (sku_id IS NULL OR sku_id = '')
          AND sku_key IS NOT NULL
          AND my_size IS NOT NULL
        """
    )

    # Insert missing orders
    inserted = conn.execute(
        """
        INSERT OR IGNORE INTO fact_orders_kaspi (
            order_id, store_code, channel_code, kaspi_offer_name,
            sku_key, sku_id, my_size, quantity, unit_price_kzt,
            created_at, planned_shipment_date, kaspi_status, status_updated_at,
            source, source_file, imported_at, assigned_size, size_source, size_confidence
        )
        SELECT
            y.order_id, y.store_code, 'KASPI', y.kaspi_offer_name,
            y.sku_key,
            (SELECT ds.sku_id FROM dim_sku_size ds
             WHERE ds.sku_key = y.sku_key AND ds.my_size = y.my_size LIMIT 1),
            y.my_size, y.quantity, y.unit_price_kzt,
            y.order_date, y.planned_shipment_date, y.kaspi_status, y.status_updated_at,
            'kaspi_archive', y.source_file, ?, y.my_size, y.size_source, y.size_confidence
        FROM kaspi_orders_y y
        LEFT JOIN fact_orders_kaspi f
          ON f.store_code = y.store_code
         AND f.order_id = y.order_id
         AND (
              (y.sku_id IS NOT NULL AND f.sku_id = y.sku_id)
              OR (y.sku_id IS NULL AND f.kaspi_offer_name = y.kaspi_offer_name)
         )
        WHERE f.order_id IS NULL
        """,
        (datetime.now().isoformat(timespec="seconds"),),
    ).rowcount

    # Simple validation
    missing_y_sku = conn.execute(
        "SELECT COUNT(*) FROM kaspi_orders_y WHERE sku_key IS NULL OR sku_key = ''"
    ).fetchone()[0]
    missing_y_size = conn.execute(
        "SELECT COUNT(*) FROM kaspi_orders_y WHERE my_size IS NULL OR my_size = ''"
    ).fetchone()[0]
    missing_sku = conn.execute(
        "SELECT COUNT(*) FROM fact_orders_kaspi WHERE sku_key IS NULL OR sku_key = ''"
    ).fetchone()[0]
    missing_size = conn.execute(
        "SELECT COUNT(*) FROM fact_orders_kaspi WHERE my_size IS NULL OR my_size = ''"
    ).fetchone()[0]

    conn.commit()
    conn.close()

    return {
        "inserted": inserted if inserted is not None else 0,
        "missing_y_sku_key": missing_y_sku,
        "missing_y_my_size": missing_y_size,
        "missing_sku_key": missing_sku,
        "missing_my_size": missing_size,
    }


def _size_sort_key(size: str | None) -> tuple[int, int]:
    if not size:
        return (99, 0)
    size_str = str(size).upper()
    if size_str in GENERIC_SIZE_ORDER:
        return (0, GENERIC_SIZE_ORDER.index(size_str))
    if size_str.isdigit():
        return (1, int(size_str))
    return (2, 0)


def _size_order_value(size: str | None) -> int | None:
    if not size:
        return None
    size_str = str(size).upper()
    if size_str in GENERIC_SIZE_ORDER:
        return GENERIC_SIZE_ORDER.index(size_str) + 1
    if size_str.isdigit():
        return int(size_str)
    return None


def ensure_catalog_entries(conn: sqlite3.Connection, y_df: pd.DataFrame) -> None:
    existing = {
        row[0]
        for row in conn.execute("SELECT sku_key FROM dim_sku")
    }
    new_keys = {
        key for key in y_df["sku_key_final"].dropna().unique().tolist()
        if key not in existing
    }
    for sku_key in sorted(new_keys):
        product_type = "ELS" if str(sku_key).upper().startswith("ELS_") else "CL"
        active_flag = 0 if sku_key in INACTIVE_SKU_KEYS else 1
        conn.execute(
            """
            INSERT OR IGNORE INTO dim_sku (
                sku_key, model, color, product_type, base_cost_cny, weight_kg,
                category, gender, active_flag, price_missing_flag
            ) VALUES (?, ?, NULL, ?, ?, ?, NULL, NULL, ?, ?)
            """,
            (sku_key, sku_key, product_type, 0.0, 0.0, active_flag, 1),
        )

    existing_sizes = {
        (row[0], row[1])
        for row in conn.execute("SELECT sku_key, my_size FROM dim_sku_size")
    }
    rows = y_df[["sku_key_final", "my_size_final"]].dropna().drop_duplicates().values.tolist()
    for sku_key, my_size in rows:
        if (sku_key, my_size) in existing_sizes:
            continue
        sku_id = re.sub(r"[^A-Z0-9]+", "_", f"{sku_key}_{my_size}".upper())
        conn.execute(
            """
            INSERT OR IGNORE INTO dim_sku_size (
                sku_id, sku_key, my_size, size_order, active_flag
            ) VALUES (?, ?, ?, ?, ?)
            """,
            (sku_id, sku_key, my_size, _size_order_value(my_size), 0),
        )


def build_offer_size_stats(
    y_df: pd.DataFrame,
    dim_sku_size: pd.DataFrame,
    export_csv: Path,
) -> pd.DataFrame:
    df = y_df.copy()
    df = df[df["kaspi_offer_name"].notna()].copy()
    df["my_size_final"] = df["my_size_final"].apply(_normalize_text)
    df["sku_key_final"] = df["sku_key_final"].apply(_normalize_text)
    df["quantity"] = pd.to_numeric(df["quantity"], errors="coerce").fillna(0).astype(int)

    sku_id_map = (
        dim_sku_size.dropna(subset=["sku_key", "my_size", "sku_id"])
        .drop_duplicates(subset=["sku_key", "my_size"])
        .set_index(["sku_key", "my_size"])["sku_id"]
        .to_dict()
    )
    df["sku_id_final"] = df.apply(
        lambda r: sku_id_map.get((r["sku_key_final"], r["my_size_final"])),
        axis=1,
    )

    stats = (
        df.groupby(["sku_key_final", "sku_id_final", "kaspi_offer_name", "my_size_final"], dropna=False)["quantity"]
        .sum()
        .reset_index()
        .rename(columns={"quantity": "units"})
    )
    totals = stats.groupby("kaspi_offer_name")["units"].sum().reset_index().rename(columns={"units": "total_units"})
    stats = stats.merge(totals, on="kaspi_offer_name", how="left")
    stats["share"] = stats.apply(
        lambda r: (r["units"] / r["total_units"]) if r["total_units"] else 0,
        axis=1,
    )
    pb = (
        stats.sort_values(by=["kaspi_offer_name", "units"], ascending=[True, False])
        .groupby("kaspi_offer_name")
        .head(1)[["kaspi_offer_name", "my_size_final", "share"]]
        .rename(columns={"my_size_final": "pb_size", "share": "pb_size_share"})
    )
    stats = stats.merge(pb, on="kaspi_offer_name", how="left")

    export_csv.parent.mkdir(parents=True, exist_ok=True)
    stats = stats.sort_values(
        by=["sku_key_final", "pb_size", "my_size_final"],
        key=lambda col: col.map(_size_sort_key) if col.name in {"pb_size", "my_size_final"} else col,
    )
    stats.to_csv(export_csv, index=False)
    return stats


def main() -> int:
    parser = argparse.ArgumentParser(description="Reconcile Kaspi ArchiveOrders into Y/Z DBs.")
    parser.add_argument("--archive-dir", type=Path, required=True, help="Root folder with ArchiveOrders exports")
    parser.add_argument("--crm-archive", type=Path, required=True, help="Path to SALES_KSP_CRM_V3.xlsx")
    parser.add_argument("--output-y", type=Path, required=True, help="Output Y DB path")
    parser.add_argument("--output-z", type=Path, required=True, help="Output Z DB path")
    parser.add_argument("--base-db", type=Path, default=DEFAULT_BASE_DB, help="Base DB to copy into Z")
    parser.add_argument("--since", type=str, default="2025-08-01", help="Start date for mapping (YYYY-MM-DD)")
    args = parser.parse_args()

    since_dt = date.fromisoformat(args.since)

    print("Loading archive exports...")
    y_df = load_archive_exports(args.archive_dir)
    print(f"Archive rows: {len(y_df)}")
    write_y_db(y_df, args.output_y)
    print(f"Y DB written: {args.output_y}")

    print("Copying base DB to Z...")
    copy_base_db(args.base_db, args.output_z)

    print("Building mapping from CRM + DB sales...")
    crm_sales_all = load_crm_sales(args.crm_archive)
    crm_sales_recent = crm_sales_all[crm_sales_all["order_date"] >= since_dt]

    conn = sqlite3.connect(str(args.output_z))
    db_sales_recent = load_db_sales(conn, since_dt)
    db_sales_all = load_db_sales(conn, date(2000, 1, 1))
    dim_sku = pd.read_sql_query("SELECT sku_key, product_type FROM dim_sku", conn)
    dim_sku_size = pd.read_sql_query("SELECT sku_key, my_size, sku_id FROM dim_sku_size", conn)
    conn.close()

    offer_map_recent = build_offer_map(db_sales_recent, crm_sales_recent)
    offer_map_full = build_offer_map(db_sales_all, crm_sales_all)
    missing_offers = set(offer_map_full["kaspi_offer_name"]) - set(offer_map_recent["kaspi_offer_name"])
    offer_map = pd.concat(
        [offer_map_recent, offer_map_full[offer_map_full["kaspi_offer_name"].isin(missing_offers)]],
        ignore_index=True,
    )
    size_mix = build_size_mix(db_sales_all, crm_sales_all)
    sku_keys_sorted = sorted(dim_sku["sku_key"].dropna().astype(str).unique().tolist(), key=len, reverse=True)
    size_map, single_size_map, els_default_map = _build_size_map(dim_sku_size, dim_sku)
    y_df = attach_mappings(
        y_df,
        offer_map,
        size_mix,
        dim_sku,
        crm_sales_all,
        sku_keys_sorted,
        size_map,
        single_size_map,
        els_default_map,
    )

    print("Updating Z with Y data...")
    offer_stats = build_offer_size_stats(
        y_df,
        dim_sku_size,
        PROJECT_ROOT / "exports" / "kaspi_offer_size_report.csv",
    )
    stats = update_z_db(args.output_z, y_df, offer_map, size_mix, offer_stats)

    print("\nVALIDATION")
    print(f"Inserted new orders: {stats['inserted']}")
    print(f"Y rows missing sku_key: {stats['missing_y_sku_key']}")
    print(f"Y rows missing my_size: {stats['missing_y_my_size']}")
    print(f"Orders missing sku_key: {stats['missing_sku_key']}")
    print(f"Orders missing my_size: {stats['missing_my_size']}")
    print("Done.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
