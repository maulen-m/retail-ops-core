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
              ROUND(SUM(line_net_rev), 2) AS db_sales_gmv_kzt
            FROM fact_sales
            WHERE store_code = ?
              AND order_date >= ?
            GROUP BY order_date, sku_key
            """,
            conn,
            params=(store_code, history_start),
        )
    return mapping_df, sales_df


def _to_float(series: pd.Series) -> pd.Series:
    return pd.to_numeric(series, errors="coerce").fillna(0.0)


def _to_int(series: pd.Series) -> pd.Series:
    return pd.to_numeric(series, errors="coerce").fillna(0).astype(int)


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

    for col in ("orders_total", "gmv", "cost", "views", "clicks", "favorites", "carts"):
        if col not in mapped.columns:
            mapped[col] = 0
    mapped["orders_total"] = _to_int(mapped["orders_total"])
    mapped["gmv"] = _to_float(mapped["gmv"])
    mapped["cost"] = _to_float(mapped["cost"])
    mapped["views"] = _to_int(mapped["views"])
    mapped["clicks"] = _to_int(mapped["clicks"])
    mapped["favorites"] = _to_int(mapped["favorites"])
    mapped["carts"] = _to_int(mapped["carts"])

    if not sales_df.empty:
        sales_df = sales_df.copy()
        sales_df["date"] = pd.to_datetime(sales_df["date"], errors="coerce").dt.date
        sales_df["mapped_sku_key"] = sales_df["mapped_sku_key"].fillna("").astype(str)
        sales_df["db_orders_count"] = _to_int(sales_df["db_orders_count"])
        sales_df["db_sales_gmv_kzt"] = _to_float(sales_df["db_sales_gmv_kzt"])
    else:
        sales_df = pd.DataFrame(columns=["date", "mapped_sku_key", "db_orders_count", "db_sales_gmv_kzt"])

    mapped = mapped.merge(
        sales_df,
        on=["date", "mapped_sku_key"],
        how="left",
    )
    mapped["db_orders_count"] = _to_int(mapped["db_orders_count"])
    mapped["db_sales_gmv_kzt"] = _to_float(mapped["db_sales_gmv_kzt"])
    mapped["delta_orders_db_minus_ads"] = mapped["db_orders_count"] - mapped["orders_total"]
    mapped["delta_gmv_db_minus_ads"] = mapped["db_sales_gmv_kzt"] - mapped["gmv"]

    product_cols = [
        "date",
        "merchant_id",
        "store_code",
        "campaign_id",
        "campaign_name",
        "sku_key",
        "product_name",
        "product_status",
        "ad_score",
        "bid_cpc",
        "bid_cpc_source",
        "avg_cpc",
        "views",
        "clicks",
        "favorites",
        "carts",
        "ctr",
        "gmv",
        "orders_total",
        "orders_direct",
        "orders_assisted",
        "conversion_order",
        "cost",
        "acos_share",
        "mapped_sku_id",
        "mapped_sku_key",
        "mapped_model",
        "mapping_status",
        "filter_rule",
        "zone_type",
        "db_orders_count",
        "db_sales_gmv_kzt",
        "delta_orders_db_minus_ads",
        "delta_gmv_db_minus_ads",
        "ingested_at",
    ]
    for col in product_cols:
        if col not in mapped.columns:
            mapped[col] = ""
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
