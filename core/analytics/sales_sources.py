"""Load and merge CRM + Fact_Sales sources with CRM precedence on overlap."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Tuple

import pandas as pd
import warnings
import sqlite3

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
    fact_rows_after_cutoff: int
    fact_rows_dropped_by_date: int
    overlap_rows: int
    combined_rows: int
    crm_only_rows: int
    fact_only_rows: int
    cutoff_date: Optional[str]


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
    df["sku_id"] = df["sku_id"].where(df["sku_id"].notna(), df["sku_key"])
    df["sku_id"] = df["sku_id"].astype(str).str.strip()
    df.loc[df["sku_id"].str.lower().isin(["nan", "none", ""]), "sku_id"] = df["sku_key"]
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


def load_fact_sales_db(db_path: Path) -> pd.DataFrame:
    """
    Load Fact_Sales directly from DB (fact_sales table).

    Returns a DataFrame aligned to SALES_COLUMNS.
    """
    if not db_path.exists():
        return pd.DataFrame(columns=SALES_COLUMNS)

    conn = sqlite3.connect(str(db_path))
    try:
        table = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='fact_sales'"
        ).fetchone()
        if not table:
            return pd.DataFrame(columns=SALES_COLUMNS)

        query = """
            SELECT
                f.order_id,
                f.order_date,
                f.sku_key,
                f.sku_id,
                s.my_size,
                '' AS kaspi_offer_name,
                f.store_code,
                f.quantity,
                f.sell_price_kzt,
                f.delivery_fee,
                f.cogs_line AS cogs,
                f.line_net_rev AS net_rev,
                f.profit_line AS profit,
                'DELIVERED' AS status,
                0 AS return_flag,
                'fact_sales_db' AS source_file
            FROM fact_sales f
            LEFT JOIN dim_sku_size s ON f.sku_id = s.sku_id
        """
        df = pd.read_sql_query(query, conn)
    finally:
        conn.close()

    if df.empty:
        return df

    df["order_date"] = _coerce_date(df["order_date"])
    df["order_id"] = df["order_id"].astype(str)
    df["sku_id"] = df["sku_id"].astype(str)
    df["sku_key"] = df["sku_key"].astype(str)
    df["quantity"] = _coerce_numeric(df["quantity"]).fillna(0).astype(int)
    df["sell_price_kzt"] = _coerce_numeric(df["sell_price_kzt"])
    df["delivery_fee"] = _coerce_numeric(df["delivery_fee"])
    df["net_rev"] = _coerce_numeric(df["net_rev"])
    df["cogs"] = _coerce_numeric(df["cogs"])
    df["profit"] = _coerce_numeric(df["profit"])
    df["store_code"] = df["store_code"].fillna("UNIVERSAL")
    df["kaspi_offer_name"] = df["kaspi_offer_name"].fillna("")

    df = df[SALES_COLUMNS].copy()
    return df


def merge_sales_sources(
    crm_df: pd.DataFrame,
    fact_df: pd.DataFrame,
    *,
    crm_date_precedence: bool = False,
    prefer_fact: bool = False,
) -> Tuple[pd.DataFrame, MergeStats]:
    crm = crm_df.copy()
    fact = fact_df.copy()

    if crm.empty and fact.empty:
        stats = MergeStats(0, 0, 0, 0, 0, 0, 0, 0, None)
        return crm, stats

    key_cols = ["order_id", "sku_id", "store_code"]
    crm = crm.drop_duplicates(subset=key_cols, keep="last")
    fact = fact.drop_duplicates(subset=key_cols, keep="last")
    crm["order_date"] = _coerce_date(crm["order_date"])
    fact["order_date"] = _coerce_date(fact["order_date"])

    cutoff_date = None
    fact_rows_after_cutoff = len(fact)
    fact_rows_dropped = 0
    if crm_date_precedence and not crm.empty:
        crm_dates = pd.to_datetime(crm["order_date"], errors="coerce").dt.date.dropna()
        if not crm_dates.empty:
            cutoff = crm_dates.min()
            cutoff_date = cutoff.isoformat()
            fact_rows_after_cutoff = fact[fact["order_date"] < cutoff].shape[0]
            fact_rows_dropped = len(fact) - fact_rows_after_cutoff
            fact = fact[fact["order_date"] < cutoff].copy()

    crm_keys = set(zip(*[crm[col].fillna("") for col in key_cols]))
    fact_keys = set(zip(*[fact[col].fillna("") for col in key_cols]))
    overlap = crm_keys & fact_keys

    fact_filtered = fact[~fact.set_index(key_cols).index.isin(overlap)]
    crm_filtered = crm[~crm.set_index(key_cols).index.isin(overlap)]
    with warnings.catch_warnings():
        warnings.filterwarnings(
            "ignore",
            category=FutureWarning,
            message="The behavior of DataFrame concatenation with empty or all-NA entries*",
        )
        if prefer_fact:
            combined = pd.concat([fact, crm_filtered], ignore_index=True)
        else:
            combined = pd.concat([fact_filtered, crm], ignore_index=True)

    if not combined.empty:
        sku_id = combined["sku_id"].fillna("").astype(str)
        sku_key = combined["sku_key"].fillna("").astype(str)
        combined["has_specific_sku"] = (sku_id != "") & (sku_id != sku_key)
        combined["is_sizeless_sku"] = (sku_id == "") | (sku_id == sku_key)
        group_cols = ["order_id", "order_date", "store_code", "sku_key"]
        group_has_specific = combined.groupby(group_cols)["has_specific_sku"].transform("max").fillna(False)
        combined = combined[~(group_has_specific & combined["is_sizeless_sku"])].copy()
        combined = combined.drop(columns=["has_specific_sku", "is_sizeless_sku"])

    stats = MergeStats(
        crm_rows=len(crm),
        fact_rows=len(fact_df),
        fact_rows_after_cutoff=fact_rows_after_cutoff,
        fact_rows_dropped_by_date=fact_rows_dropped,
        overlap_rows=len(overlap),
        combined_rows=len(combined),
        crm_only_rows=len(crm_keys - fact_keys),
        fact_only_rows=len(fact_keys - crm_keys),
        cutoff_date=cutoff_date,
    )

    return combined, stats
