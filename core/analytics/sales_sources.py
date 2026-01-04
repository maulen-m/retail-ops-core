"""Load and merge CRM + Fact_Sales sources with CRM precedence."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Tuple

import pandas as pd
import warnings

from core.ingest.sales_ingest import parse_sales_excel


SALES_COLUMNS = [
    "order_id",
    "order_date",
    "sku_key",
    "sku_id",
    "my_size",
    "kaspi_offer_name",
    "store_code",
    "quantity",
    "sell_price_kzt",
    "delivery_fee",
    "cogs",
    "net_rev",
    "profit",
    "status",
    "return_flag",
    "source_file",
]


@dataclass
class MergeStats:
    crm_rows: int
    fact_rows: int
    overlap_rows: int
    combined_rows: int
    crm_only_rows: int
    fact_only_rows: int


def _coerce_date(series: pd.Series) -> pd.Series:
    return pd.to_datetime(series, errors="coerce").dt.date


def _coerce_numeric(series: pd.Series) -> pd.Series:
    return pd.to_numeric(series, errors="coerce")


def _resolve_sheet_name(xl: pd.ExcelFile, sheet: str) -> str:
    if sheet in xl.sheet_names:
        return sheet
    lowered = sheet.lower()
    for name in xl.sheet_names:
        if name.lower() == lowered:
            return name
    for name in xl.sheet_names:
        if lowered.replace("_", "") in name.lower().replace("_", ""):
            return name
    raise ValueError(f"Sheet '{sheet}' not found. Available: {xl.sheet_names}")


def load_crm_sales(crm_path: Path, sheet: str) -> Tuple[pd.DataFrame, int]:
    records = parse_sales_excel(str(crm_path), sheet_name=sheet)
    df = pd.DataFrame(records)
    if df.empty:
        return df, 0

    df["order_date"] = _coerce_date(df["order_date"])
    df["order_id"] = df["order_id"].astype(str)
    df["sku_id"] = df["sku_id"].astype(str)
    df["sku_key"] = df["sku_key"].astype(str)
    df["my_size"] = df["my_size"].fillna(df["sku_id"].str.split("_").str[-1])
    df["store_code"] = df["store_code"].fillna("UNIVERSAL")
    df["kaspi_offer_name"] = df["kaspi_offer_name"].fillna("")
    df["quantity"] = _coerce_numeric(df["quantity"]).fillna(0).astype(int)
    df["sell_price_kzt"] = _coerce_numeric(df["sell_price_kzt"])
    df["delivery_fee"] = _coerce_numeric(df["delivery_fee"])
    df["net_rev"] = _coerce_numeric(df["net_rev"])
    df["cogs"] = None
    df["profit"] = None
    df["status"] = "DELIVERED"
    df["return_flag"] = _coerce_numeric(df.get("return_flag", 0)).fillna(0).astype(int)
    df["source_file"] = crm_path.name

    missing_net_rev = int(df["net_rev"].isna().sum())
    df = df[SALES_COLUMNS].copy()
    return df, missing_net_rev


def load_fact_sales(fact_path: Path, sheet: str) -> pd.DataFrame:
    xl = pd.ExcelFile(fact_path)
    sheet_name = _resolve_sheet_name(xl, sheet)
    df = pd.read_excel(xl, sheet_name=sheet_name)
    if df.empty:
        return df

    if "Channel" in df.columns:
        df = df[df["Channel"] == "Kaspi"].copy()

    df["order_date"] = _coerce_date(df["Date"])
    df["order_id"] = df["OrderID"].astype(str)
    df["kaspi_offer_name"] = df["Kaspi_Offer_name"].fillna("")
    df["sku_key"] = df["SKU_key"].astype(str)
    df["sku_id"] = df["SKU_ID"].astype(str)
    df["my_size"] = df["sku_id"].str.split("_").str[-1]
    df["quantity"] = _coerce_numeric(df["Quantity"]).fillna(0).astype(int)
    df["sell_price_kzt"] = _coerce_numeric(df.get("Sell_price_kzt"))
    df["delivery_fee"] = _coerce_numeric(df.get("Delivery_fee"))
    df["net_rev"] = _coerce_numeric(df.get("Line_NetRev"))
    df["cogs"] = _coerce_numeric(df.get("COGS_line"))
    df["profit"] = _coerce_numeric(df.get("Profit_line"))
    df["status"] = "DELIVERED"
    df["return_flag"] = 0
    df["store_code"] = "UNIVERSAL"
    df["source_file"] = fact_path.name

    df = df[SALES_COLUMNS].copy()
    return df


def merge_sales_sources(
    crm_df: pd.DataFrame,
    fact_df: pd.DataFrame,
) -> Tuple[pd.DataFrame, MergeStats]:
    crm = crm_df.copy()
    fact = fact_df.copy()

    if crm.empty and fact.empty:
        stats = MergeStats(0, 0, 0, 0, 0, 0)
        return crm, stats

    key_cols = ["order_id", "sku_id", "store_code", "kaspi_offer_name"]
    crm = crm.drop_duplicates(subset=key_cols, keep="last")
    fact = fact.drop_duplicates(subset=key_cols, keep="last")

    crm_keys = set(zip(*[crm[col].fillna("") for col in key_cols]))
    fact_keys = set(zip(*[fact[col].fillna("") for col in key_cols]))
    overlap = crm_keys & fact_keys

    fact_filtered = fact[~fact.set_index(key_cols).index.isin(overlap)]
    with warnings.catch_warnings():
        warnings.filterwarnings(
            "ignore",
            category=FutureWarning,
            message="The behavior of DataFrame concatenation with empty or all-NA entries*",
        )
        combined = pd.concat([fact_filtered, crm], ignore_index=True)

    stats = MergeStats(
        crm_rows=len(crm),
        fact_rows=len(fact),
        overlap_rows=len(overlap),
        combined_rows=len(combined),
        crm_only_rows=len(crm_keys - fact_keys),
        fact_only_rows=len(fact_keys - crm_keys),
    )

    return combined, stats
