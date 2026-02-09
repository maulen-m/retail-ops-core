#!/usr/bin/env python3
"""
Build owner-facing Kaspi marketing workbook + CSV mirrors from ads DB + app DB.
"""

from __future__ import annotations

import argparse
import shutil
import sqlite3
from datetime import date, datetime
from pathlib import Path
from typing import Iterable
from zoneinfo import ZoneInfo

import pandas as pd
import re

ALMATY_TZ = ZoneInfo("Asia/Almaty")

DEFAULT_ADS_DB = Path(
    "~/Documents/useful tables/Main crm spreadsheets/main tables/External_database/Kaspi_marketing/db/kaspi_marketing.db"
)
DEFAULT_APP_DB = Path("~/Docs/Autonomous_business/db/app.db")
DEFAULT_WORKBOOK = Path(
    "~/Documents/useful tables/Main crm spreadsheets/main tables/External_database/Kaspi_marketing/Kaspi_marketing_owner.xlsx"
)
DEFAULT_CSV_DIR = Path(
    "~/Documents/useful tables/Main crm spreadsheets/main tables/External_database/Kaspi_marketing"
)
DEFAULT_HISTORY_START = "2025-01-01"
DEFAULT_STRICT_MODELS = "line51,line61,suit-61"
DEFAULT_STORE_CODE = "ACMEWEAR"


def canonical_model(model: str | None) -> str:
    if model is None:
        return ""
    return "".join(ch for ch in str(model).lower() if ch.isalnum())


def parse_models_csv(value: str) -> set[str]:
    return {canonical_model(x.strip()) for x in value.split(",") if x.strip()}


def parse_iso_date(value: str) -> date:
    return datetime.strptime(value, "%Y-%m-%d").date()


def normalize_mapping_key(value: str | None) -> str:
    if value is None:
        return ""
    key = str(value).strip()
    if not key:
        return ""
    parts = key.split("_")
    if len(parts) > 1 and parts[-1].isdigit():
        return "_".join(parts[:-1])
    return key


def parse_bid_value(value: object) -> float | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip()
    if not text:
        return None
    text = text.replace("\u00a0", " ").replace("₸", "").replace("%", "").replace(" ", "")
    text = text.replace(",", ".")
    try:
        return float(text)
    except ValueError:
        return None


def _extract_size_token(text: str) -> str:
    match = re.search(r"(?:_|^)(XS|S|M|L|XL|2XL|3XL|4XL|5XL)(?:_|$)", text.upper())
    return match.group(1) if match else ""


def _infer_line61_mapping(
    merchant_sku: str,
    mapping_lookup_df: pd.DataFrame,
) -> tuple[str, str, str]:
    sku = merchant_sku.upper()
    if "SUIT-61" not in sku and "LINE61" not in sku:
        return "", "", ""
    if mapping_lookup_df.empty:
        return "", "", ""

    candidates = mapping_lookup_df[
        mapping_lookup_df["mapped_model_canonical"] == "line61"
    ].copy()
    if candidates.empty:
        return "", "", ""

    if "_BLK_" in sku or "_BLACK_" in sku:
        candidates = candidates[
            candidates["mapped_sku_id"].str.upper().str.contains("_BLACK_", na=False)
        ]

    size = _extract_size_token(sku)
    if size:
        size_candidates = candidates[
            candidates["mapped_sku_id"].str.upper().str.endswith(f"_{size}")
        ]
        if not size_candidates.empty:
            candidates = size_candidates

    if candidates.empty:
        return "", "", ""

    candidates = candidates.sort_values("mapped_sku_id")
    row = candidates.iloc[0]
    return (
        str(row.get("mapped_sku_id", "")).strip(),
        str(row.get("mapped_sku_key", "")).strip(),
        str(row.get("mapped_model", "")).strip(),
    )


def _table_exists(conn: sqlite3.Connection, table: str) -> bool:
    cur = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=? LIMIT 1",
        (table,),
    )
    return cur.fetchone() is not None


def _read_ads_table(conn: sqlite3.Connection, table: str) -> pd.DataFrame:
    if not _table_exists(conn, table):
        return pd.DataFrame()
    return pd.read_sql_query(f"SELECT * FROM {table}", conn)


def _load_ads_data(ads_db: Path) -> tuple[pd.DataFrame, pd.DataFrame]:
    with sqlite3.connect(ads_db) as conn:
        campaign_df = _read_ads_table(conn, "campaign_daily_current")
        product_df = _read_ads_table(conn, "campaign_product_daily_current")
    return campaign_df, product_df


def _load_mapping_and_sales(app_db: Path, history_start: str, store_code: str) -> tuple[pd.DataFrame, pd.DataFrame]:
    with sqlite3.connect(app_db) as conn:
        mapping_df = pd.read_sql_query(
            """
            SELECT
              dss.sku_id AS mapped_sku_id,
              dss.sku_key AS mapped_sku_key,
              ds.model AS mapped_model
            FROM dim_sku_size dss
            JOIN dim_sku ds ON ds.sku_key = dss.sku_key
            """,
            conn,
        )
        sales_df = pd.read_sql_query(
            """
            SELECT
              order_date AS date,
              sku_key AS mapped_sku_key,
              COUNT(DISTINCT order_id) AS db_orders_count,
              ROUND(SUM(COALESCE(sell_price_kzt, 0) * COALESCE(quantity, 0)), 2) AS db_sales_gmv_kzt,
              ROUND(SUM(COALESCE(cogs_line, 0)), 2) AS db_cogs,
              ROUND(SUM(COALESCE(profit_line, 0)), 2) AS db_profit_line
            FROM fact_sales
            WHERE store_code = ?
              AND order_date >= ?
            GROUP BY order_date, sku_key
            """,
            conn,
            params=(store_code, history_start),
        )
    return mapping_df, sales_df


def ensure_bid_override_table(ads_db: Path) -> None:
    with sqlite3.connect(ads_db) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS bid_cpc_overrides (
                date TEXT NOT NULL,
                merchant_id TEXT NOT NULL,
                campaign_id TEXT NOT NULL,
                sku_key TEXT NOT NULL,
                bid_cpc REAL NOT NULL,
                source TEXT DEFAULT 'owner_workbook_manual',
                updated_at TEXT DEFAULT (datetime('now')),
                PRIMARY KEY (date, merchant_id, campaign_id, sku_key)
            )
            """
        )
        conn.commit()


def _load_raw_bid_map(ads_db: Path) -> dict[tuple[str, str, str, str], float]:
    with sqlite3.connect(ads_db) as conn:
        if not _table_exists(conn, "campaign_product_daily_current"):
            return {}
        rows = conn.execute(
            """
            SELECT date, merchant_id, campaign_id, sku_key, bid_cpc
            FROM campaign_product_daily_current
            """
        ).fetchall()
    result: dict[tuple[str, str, str, str], float] = {}
    for d, mid, cid, sku, bid in rows:
        key = (str(d or ""), str(mid or ""), str(cid or ""), str(sku or ""))
        bid_val = parse_bid_value(bid)
        if bid_val is None:
            continue
        result[key] = bid_val
    return result


def ingest_bid_overrides_from_workbook(ads_db: Path, workbook_path: Path) -> int:
    ensure_bid_override_table(ads_db)
    if not workbook_path.exists():
        return 0

    try:
        df = pd.read_excel(workbook_path, sheet_name="campaign_product_daily")
    except Exception:
        return 0
    if df.empty:
        return 0

    required = {"date", "merchant_id", "campaign_id", "sku_key", "bid_cpc"}
    if not required.issubset(df.columns):
        return 0

    raw_map = _load_raw_bid_map(ads_db)
    upserts: list[tuple[str, str, str, str, float]] = []

    for _, row in df.iterrows():
        d = row.get("date")
        try:
            date_key = str(pd.to_datetime(d).date()) if pd.notna(d) else ""
        except Exception:
            date_key = str(d or "").strip()
        merchant_id = str(row.get("merchant_id", "")).strip()
        campaign_id = str(row.get("campaign_id", "")).strip()
        sku_key = str(row.get("sku_key", "")).strip()
        bid = parse_bid_value(row.get("bid_cpc"))

        if not (date_key and merchant_id and campaign_id and sku_key):
            continue
        if bid is None:
            continue

        key = (date_key, merchant_id, campaign_id, sku_key)
        raw_bid = raw_map.get(key)
        if raw_bid is None:
            continue
        if abs(raw_bid - bid) < 1e-9:
            continue
        upserts.append((date_key, merchant_id, campaign_id, sku_key, bid))

    if not upserts:
        return 0

    with sqlite3.connect(ads_db) as conn:
        conn.executemany(
            """
            INSERT INTO bid_cpc_overrides (date, merchant_id, campaign_id, sku_key, bid_cpc, source, updated_at)
            VALUES (?, ?, ?, ?, ?, 'owner_workbook_manual', datetime('now'))
            ON CONFLICT(date, merchant_id, campaign_id, sku_key)
            DO UPDATE SET bid_cpc = excluded.bid_cpc, source = excluded.source, updated_at = excluded.updated_at
            """,
            upserts,
        )
        conn.commit()
    return len(upserts)


def load_bid_overrides(ads_db: Path) -> pd.DataFrame:
    ensure_bid_override_table(ads_db)
    with sqlite3.connect(ads_db) as conn:
        return pd.read_sql_query(
            "SELECT date, merchant_id, campaign_id, sku_key, bid_cpc, source FROM bid_cpc_overrides",
            conn,
        )


def _to_float(series: pd.Series) -> pd.Series:
    return pd.to_numeric(series, errors="coerce").fillna(0.0)


def _to_int(series: pd.Series) -> pd.Series:
    return pd.to_numeric(series, errors="coerce").fillna(0).astype(int)


def _safe_div(numerator: pd.Series, denominator: pd.Series) -> pd.Series:
    num = _to_float(numerator)
    den = _to_float(denominator)
    out = pd.Series(0.0, index=num.index, dtype=float)
    mask = den > 0
    out.loc[mask] = num.loc[mask] / den.loc[mask]
    return out


def build_owner_frames(
    ads_db: Path,
    app_db: Path,
    history_start_date: str,
    future_cutover_date: str,
    strict_models: Iterable[str],
    store_code: str = DEFAULT_STORE_CODE,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    if not ads_db.exists():
        raise FileNotFoundError(f"Ads DB not found: {ads_db}")
    if not app_db.exists():
        raise FileNotFoundError(f"App DB not found: {app_db}")

    strict_set = {canonical_model(x) for x in strict_models if str(x).strip()}
    campaign_df, product_df = _load_ads_data(ads_db)
    mapping_df, sales_df = _load_mapping_and_sales(app_db, history_start_date, store_code)

    if product_df.empty:
        return pd.DataFrame(), pd.DataFrame()

    cutover = parse_iso_date(future_cutover_date)

    product_df = product_df.copy()
    product_df["date"] = pd.to_datetime(product_df["date"], errors="coerce").dt.date
    product_df = product_df[product_df["date"] >= parse_iso_date(history_start_date)]

    for col in ("json_merchant_sku", "sku_key", "campaign_id", "merchant_id", "campaign_name", "product_name"):
        if col in product_df.columns:
            product_df[col] = product_df[col].fillna("").astype(str).str.strip()

    if "json_merchant_sku" not in product_df.columns:
        product_df["json_merchant_sku"] = ""
    if "sku_key" not in product_df.columns:
        product_df["sku_key"] = ""

    mapping_df = mapping_df.copy()
    mapping_df["mapping_join_key"] = mapping_df["mapped_sku_id"].apply(normalize_mapping_key)
    mapping_df["mapped_model_canonical"] = mapping_df["mapped_model"].apply(canonical_model)

    product_df["mapping_join_key"] = product_df["json_merchant_sku"].apply(normalize_mapping_key)
    empty_mask = product_df["mapping_join_key"] == ""
    product_df.loc[empty_mask, "mapping_join_key"] = product_df.loc[empty_mask, "sku_key"].apply(
        normalize_mapping_key
    )

    mapped = product_df.merge(
        mapping_df,
        on="mapping_join_key",
        how="left",
    )

    # Heuristic mapping for LINE61 ads SKU payloads like OF_SUIT-61_BLK_XL_48.
    suit_candidates = mapped["mapped_sku_key"].isna() | (mapped["mapped_sku_key"] == "")
    for idx in mapped[suit_candidates].index:
        merchant_sku = str(mapped.at[idx, "json_merchant_sku"] or "").strip()
        mapped_sku_id, mapped_sku_key, mapped_model = _infer_line61_mapping(merchant_sku, mapping_df)
        if mapped_sku_key:
            mapped.at[idx, "mapped_sku_id"] = mapped_sku_id
            mapped.at[idx, "mapped_sku_key"] = mapped_sku_key
            mapped.at[idx, "mapped_model"] = mapped_model
            mapped.at[idx, "mapped_model_canonical"] = canonical_model(mapped_model)

    mapped["mapping_status"] = mapped["mapped_sku_key"].apply(
        lambda x: "mapped" if isinstance(x, str) and x.strip() else "unmapped"
    )
    mapped["mapped_model_canonical"] = mapped["mapped_model"].apply(canonical_model)
    mapped["zone_type"] = mapped["date"].apply(
        lambda d: "historical_strict" if d < cutover else "future_all"
    )

    historical_keep = (
        (mapped["zone_type"] == "historical_strict")
        & (mapped["mapping_status"] == "mapped")
        & (mapped["mapped_model_canonical"].isin(strict_set))
    )
    future_keep = mapped["zone_type"] == "future_all"
    mapped["include_row"] = historical_keep | future_keep
    mapped["filter_rule"] = mapped["zone_type"].apply(
        lambda z: "historical:mapped_and_model_filtered"
        if z == "historical_strict"
        else "future:no_sku_filter"
    )

    mapped = mapped[mapped["include_row"]].copy()
    if mapped.empty:
        return pd.DataFrame(), pd.DataFrame()

    for col in (
        "orders_total",
        "orders_direct",
        "orders_assisted",
        "views",
        "clicks",
        "favorites",
        "carts",
        "gmv",
        "cost",
        "ctr",
        "conversion_order",
        "avg_cpc",
        "acos_share",
        "bid_cpc",
    ):
        if col not in mapped.columns:
            mapped[col] = 0
    mapped["orders_total"] = _to_int(mapped["orders_total"])
    mapped["orders_direct"] = _to_int(mapped["orders_direct"])
    mapped["orders_assisted"] = _to_int(mapped["orders_assisted"])
    mapped["gmv"] = _to_float(mapped["gmv"])
    mapped["cost"] = _to_float(mapped["cost"])
    mapped["ctr"] = _to_float(mapped["ctr"])
    mapped["conversion_order"] = _to_float(mapped["conversion_order"])
    mapped["avg_cpc"] = _to_float(mapped["avg_cpc"])
    mapped["acos_share"] = _to_float(mapped["acos_share"])
    mapped["bid_cpc"] = _to_float(mapped["bid_cpc"])
    mapped["views"] = _to_int(mapped["views"])
    mapped["clicks"] = _to_int(mapped["clicks"])
    mapped["favorites"] = _to_int(mapped["favorites"])
    mapped["carts"] = _to_int(mapped["carts"])
    if "bid_cpc_source" not in mapped.columns:
        mapped["bid_cpc_source"] = "api_current"
    mapped["bid_cpc_source"] = mapped["bid_cpc_source"].fillna("").astype(str).str.strip()
    mapped.loc[mapped["bid_cpc_source"] == "", "bid_cpc_source"] = "api_current"

    if not sales_df.empty:
        sales_df = sales_df.copy()
        sales_df["date"] = pd.to_datetime(sales_df["date"], errors="coerce").dt.date
        sales_df["mapped_sku_key"] = sales_df["mapped_sku_key"].fillna("").astype(str)
        sales_df["db_orders_count"] = _to_int(sales_df["db_orders_count"])
        sales_df["db_sales_gmv_kzt"] = _to_float(sales_df["db_sales_gmv_kzt"])
        sales_df["db_cogs"] = _to_float(sales_df["db_cogs"])
        sales_df["db_profit_line"] = _to_float(sales_df["db_profit_line"])
    else:
        sales_df = pd.DataFrame(
            columns=[
                "date",
                "mapped_sku_key",
                "db_orders_count",
                "db_sales_gmv_kzt",
                "db_cogs",
                "db_profit_line",
            ]
        )

    mapped = mapped.merge(
        sales_df,
        on=["date", "mapped_sku_key"],
        how="left",
    )
    mapped["bid_cpc_2"] = _to_float(mapped["bid_cpc"])
    mapped["db_orders_count"] = _to_int(mapped["db_orders_count"])
    mapped["db_sales_gmv_kzt"] = _to_float(mapped["db_sales_gmv_kzt"])
    mapped["db_cogs"] = _to_float(mapped["db_cogs"])
    mapped["db_profit_line"] = _to_float(mapped["db_profit_line"])
    mapped["delta_orders_db_minus_ads"] = mapped["db_orders_count"] - mapped["orders_total"]
    mapped["delta_gmv_db_minus_ads"] = mapped["db_sales_gmv_kzt"] - mapped["gmv"]

    # Apply persisted manual bid overrides last so owner workbook stays stable.
    overrides_df = load_bid_overrides(ads_db)
    if not overrides_df.empty:
        overrides_df = overrides_df.rename(columns={"bid_cpc": "bid_cpc_override", "source": "bid_cpc_override_source"})
        overrides_df["date"] = pd.to_datetime(overrides_df["date"], errors="coerce").dt.date
        for col in ("merchant_id", "campaign_id", "sku_key"):
            overrides_df[col] = overrides_df[col].fillna("").astype(str).str.strip()
        mapped = mapped.merge(
            overrides_df,
            on=["date", "merchant_id", "campaign_id", "sku_key"],
            how="left",
        )
        has_override = mapped["bid_cpc_override"].notna()
        mapped.loc[has_override, "bid_cpc"] = mapped.loc[has_override, "bid_cpc_override"]
        mapped.loc[has_override, "bid_cpc_source"] = "manual_override"
        mapped.drop(columns=["bid_cpc_override", "bid_cpc_override_source"], inplace=True, errors="ignore")

    mapped["db_acos"] = _safe_div(mapped["cost"], mapped["db_sales_gmv_kzt"]) * 100.0
    mapped["db_roas"] = _safe_div(mapped["db_sales_gmv_kzt"], mapped["cost"])
    mapped["db_asp_kzt"] = _safe_div(mapped["db_sales_gmv_kzt"], mapped["db_orders_count"])
    mapped["ads_cost_per_db_order"] = _safe_div(mapped["cost"], mapped["db_orders_count"])
    mapped["db_profit_est_kzt"] = mapped["db_profit_line"] - mapped["cost"]
    mapped["db_Unit_profit_%"] = _safe_div(mapped["db_profit_est_kzt"], mapped["db_sales_gmv_kzt"]) * 100.0

    product_cols = [
        "date",
        "merchant_id",
        "store_code",
        "campaign_id",
        "campaign_name",
        "sku_key",
        "product_name",
        "product_status",
        "ingested_at",
        "mapped_sku_id",
        "mapped_sku_key",
        "mapped_model",
        "mapping_status",
        "filter_rule",
        "zone_type",
        "bid_cpc",
        "bid_cpc_source",
        "ad_score",
        "avg_cpc",
        "views",
        "clicks",
        "ctr",
        "favorites",
        "carts",
        "conversion_order",
        "orders_total",
        "orders_direct",
        "orders_assisted",
        "gmv",
        "cost",
        "acos_share",
        "delta_orders_db_minus_ads",
        "db_acos",
        "db_roas",
        "delta_gmv_db_minus_ads",
        "db_sales_gmv_kzt",
        "bid_cpc_2",
        "db_asp_kzt",
        "db_orders_count",
        "ads_cost_per_db_order",
        "db_cogs",
        "db_profit_est_kzt",
        "db_Unit_profit_%",
    ]
    numeric_int_cols = {
        "views",
        "clicks",
        "favorites",
        "carts",
        "orders_total",
        "orders_direct",
        "orders_assisted",
        "db_orders_count",
        "delta_orders_db_minus_ads",
    }
    numeric_float_cols = {
        "bid_cpc",
        "avg_cpc",
        "ctr",
        "conversion_order",
        "gmv",
        "cost",
        "acos_share",
        "db_acos",
        "db_roas",
        "delta_gmv_db_minus_ads",
        "db_sales_gmv_kzt",
        "bid_cpc_2",
        "db_asp_kzt",
        "ads_cost_per_db_order",
        "db_cogs",
        "db_profit_est_kzt",
        "db_Unit_profit_%",
    }
    for col in product_cols:
        if col not in mapped.columns:
            if col in numeric_int_cols:
                mapped[col] = 0
            elif col in numeric_float_cols:
                mapped[col] = 0.0
            else:
                mapped[col] = ""
    for col in numeric_int_cols:
        mapped[col] = _to_int(mapped[col])
    for col in numeric_float_cols:
        mapped[col] = _to_float(mapped[col])
    product_out = mapped[product_cols].sort_values(["date", "campaign_id", "sku_key"]).reset_index(drop=True)

    campaign_group = (
        product_out.groupby(["date", "merchant_id", "campaign_id", "campaign_name"], as_index=False)
        .agg(
            product_rows=("sku_key", "count"),
            ads_views_products=("views", "sum"),
            ads_clicks_products=("clicks", "sum"),
            ads_favorites_products=("favorites", "sum"),
            ads_carts_products=("carts", "sum"),
            ads_orders_total_products=("orders_total", "sum"),
            ads_gmv_products=("gmv", "sum"),
            ads_cost_products=("cost", "sum"),
            db_orders_count=("db_orders_count", "sum"),
            db_sales_gmv_kzt=("db_sales_gmv_kzt", "sum"),
        )
        .reset_index(drop=True)
    )
    campaign_group["delta_orders_db_minus_ads"] = (
        campaign_group["db_orders_count"] - campaign_group["ads_orders_total_products"]
    )
    campaign_group["delta_gmv_db_minus_ads"] = (
        campaign_group["db_sales_gmv_kzt"] - campaign_group["ads_gmv_products"]
    )

    if not campaign_df.empty:
        campaign_df = campaign_df.copy()
        campaign_df["date"] = pd.to_datetime(campaign_df["date"], errors="coerce").dt.date
        campaign_df = campaign_df[campaign_df["date"] >= parse_iso_date(history_start_date)]
        for col in ("merchant_id", "campaign_id"):
            if col in campaign_df.columns:
                campaign_df[col] = campaign_df[col].fillna("").astype(str).str.strip()
        campaign_out = campaign_df.merge(
            campaign_group,
            on=["date", "merchant_id", "campaign_id", "campaign_name"],
            how="left",
        )
    else:
        campaign_out = campaign_group.copy()

    for col in (
        "views",
        "clicks",
        "favorites",
        "carts",
        "transactions",
        "gmv",
        "cost",
        "crr",
        "db_orders_count",
        "db_sales_gmv_kzt",
    ):
        if col in campaign_out.columns:
            if col in {"views", "clicks", "favorites", "carts", "transactions", "db_orders_count"}:
                campaign_out[col] = _to_int(campaign_out[col])
            else:
                campaign_out[col] = _to_float(campaign_out[col])

    campaign_out["zone_type"] = campaign_out["date"].apply(
        lambda d: "historical_strict" if d < cutover else "future_all"
    )
    campaign_out["filter_rule"] = campaign_out["zone_type"].apply(
        lambda z: "historical:mapped_and_model_filtered"
        if z == "historical_strict"
        else "future:no_sku_filter"
    )

    campaign_out = campaign_out.sort_values(["date", "campaign_id"]).reset_index(drop=True)
    return campaign_out, product_out


def write_owner_outputs(
    campaign_df: pd.DataFrame,
    product_df: pd.DataFrame,
    workbook_path: Path,
    csv_dir: Path,
) -> None:
    workbook_path.parent.mkdir(parents=True, exist_ok=True)
    csv_dir.mkdir(parents=True, exist_ok=True)

    if workbook_path.exists():
        backup_dir = workbook_path.parent / "backups"
        backup_dir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now(ALMATY_TZ).strftime("%Y%m%d_%H%M%S")
        backup_path = backup_dir / f"{workbook_path.stem}_{stamp}.xlsx"
        shutil.copy2(workbook_path, backup_path)

    temp_path = workbook_path.with_suffix(".tmp.xlsx")
    with pd.ExcelWriter(temp_path, engine="openpyxl") as writer:
        campaign_df.to_excel(writer, sheet_name="campaign_daily", index=False)
        product_df.to_excel(writer, sheet_name="campaign_product_daily", index=False)
    temp_path.replace(workbook_path)

    campaign_df.to_csv(csv_dir / "campaign_daily_owner.csv", index=False)
    product_df.to_csv(csv_dir / "campaign_product_daily_owner.csv", index=False)


def build_owner_workbook(
    ads_db: Path,
    app_db: Path,
    workbook_path: Path,
    csv_dir: Path,
    history_start_date: str,
    future_cutover_date: str,
    strict_models: Iterable[str],
    store_code: str = DEFAULT_STORE_CODE,
) -> dict[str, int]:
    override_upserts = ingest_bid_overrides_from_workbook(ads_db, workbook_path)
    campaign_df, product_df = build_owner_frames(
        ads_db=ads_db,
        app_db=app_db,
        history_start_date=history_start_date,
        future_cutover_date=future_cutover_date,
        strict_models=strict_models,
        store_code=store_code,
    )
    write_owner_outputs(campaign_df, product_df, workbook_path, csv_dir)
    return {
        "campaign_rows": int(len(campaign_df)),
        "product_rows": int(len(product_df)),
        "bid_override_upserts": int(override_upserts),
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build owner-facing Kaspi marketing workbook")
    parser.add_argument("--ads-db", type=Path, default=DEFAULT_ADS_DB)
    parser.add_argument("--app-db", type=Path, default=DEFAULT_APP_DB)
    parser.add_argument("--workbook-path", type=Path, default=DEFAULT_WORKBOOK)
    parser.add_argument("--csv-dir", type=Path, default=DEFAULT_CSV_DIR)
    parser.add_argument("--history-start-date", default=DEFAULT_HISTORY_START)
    parser.add_argument(
        "--future-cutover-date",
        default=datetime.now(ALMATY_TZ).date().isoformat(),
        help="Date when future no-filter mode starts (YYYY-MM-DD)",
    )
    parser.add_argument("--strict-models", default=DEFAULT_STRICT_MODELS)
    parser.add_argument("--store-code", default=DEFAULT_STORE_CODE)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    summary = build_owner_workbook(
        ads_db=args.ads_db,
        app_db=args.app_db,
        workbook_path=args.workbook_path,
        csv_dir=args.csv_dir,
        history_start_date=args.history_start_date,
        future_cutover_date=args.future_cutover_date,
        strict_models=parse_models_csv(args.strict_models),
        store_code=args.store_code,
    )
    print(summary)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
