#!/usr/bin/env python3
"""
Kaspi Marketing Ads scraper (API-first).
- Auth via Playwright persistent profile
- Download reports (campaigns + per-campaign products CSV)
- Fetch JSON endpoints for campaign/products
- Normalize into campaign_daily + campaign_product_daily
- Persist to dedicated SQLite + bookkeeper XLSX
"""

import argparse
import json
import logging
import os
import sqlite3
import time
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Optional
from zoneinfo import ZoneInfo

import pandas as pd
from dotenv import load_dotenv
from playwright.sync_api import sync_playwright

ALMATY_TZ = ZoneInfo("Asia/Almaty")

DEFAULT_OUTPUT_ROOT = Path(
    "~/Documents/useful tables/Main crm spreadsheets/main tables/External_database/Kaspi_marketing"
)
DEFAULT_BOOKKEEPER = Path(
    "~/Docs/Autonomous_business/excel/marketing/Kaspi_marketing_bookkeeper.xlsx"
)
DEFAULT_PROFILE_DIR = "~/Library/Application Support/ChromePlaywrightProfile4"
DEFAULT_MERCHANT_ID = "759051"
DEFAULT_STORE_CODE = "30137883"  # AcmeWear

REPORT_CAMPAIGNS_URL = (
    "https://marketing.kaspi.kz/advertising/products/api/v3/merchant/{merchant_id}"
    "/reports/campaigns/csv?dateFrom={date}&dateTo={date}"
)
REPORT_PRODUCTS_URL = (
    "https://marketing.kaspi.kz/advertising/products/api/v3/merchant/{merchant_id}"
    "/reports/products/csv?campaignId={campaign_id}&startDate={date}&endDate={date}"
)
CAMPAIGNS_URL = (
    "https://marketing.kaspi.kz/advertising/products/api/v5/merchant/{merchant_id}"
    "/Campaigns?StartDate={date}&EndDate={date}&state={state}"
)
CAMPAIGN_OVERVIEW_URL = (
    "https://marketing.kaspi.kz/advertising/products/api/v4/merchant/{merchant_id}"
    "/Overview/{campaign_id}"
)
CAMPAIGN_CORE_URL = (
    "https://marketing.kaspi.kz/advertising/products/api/v1/merchant/{merchant_id}"
    "/Campaign/{campaign_id}"
)
CAMPAIGN_PRODUCTS_URL = (
    "https://marketing.kaspi.kz/advertising/products/api/v5/merchant/{merchant_id}"
    "/campaign/{campaign_id}/products?StartDate={date}&EndDate={date}"
)
CAMPAIGN_CATEGORIES_URL = (
    "https://marketing.kaspi.kz/advertising/products/api/v4/merchant/{merchant_id}"
    "/campaign/{campaign_id}/products-categories?StartDate={date}&EndDate={date}"
)
CAMPAIGN_DAILY_VIEWS_URL = (
    "https://marketing.kaspi.kz/advertising/products/api/v3/merchant/{merchant_id}"
    "/overview/daily/{campaign_id}/views"
)

CAMPAIGN_STATES = ["Enabled", "Paused", "Finished"]

ID_COLUMNS = {
    "merchant_id",
    "store_code",
    "campaign_id",
    "sku_key",
    "json_sku",
    "json_merchant_sku",
}
DATE_COLUMNS = {"date"}

CAMPAIGN_REPORT_MAP = {
    "Текущий статус": "report_state",
    "Просмотры": "report_views",
    "Клики": "report_clicks",
    "CTR": "report_ctr",
    "Ср. стоим. клика": "report_avg_cpc",
    "Расходы на рекламу": "report_cost",
    "Сумма заказов": "report_gmv",
    "Все заказы": "report_transactions",
    "В избранное": "report_favorites",
    "В корзину": "report_carts",
    "Доля рекламных расходов": "report_crr",
}


def _coerce_str(value: Any) -> str:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return ""
    return str(value).strip()


def parse_number(value: Any) -> Optional[float]:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    s = str(value).strip()
    if not s or s.lower() in {"nan", "none", "null"}:
        return None
    s = s.replace("\u00a0", " ")
    s = s.replace("₸", "")
    s = s.replace("%", "")
    s = s.replace(" ", "")
    s = s.replace(",", ".")
    if not s:
        return None
    try:
        return float(s)
    except ValueError:
        return None


def parse_int(value: Any) -> Optional[int]:
    num = parse_number(value)
    if num is None:
        return None
    try:
        return int(round(num))
    except Exception:
        return None


def ensure_dirs(*paths: Path) -> None:
    for path in paths:
        path.mkdir(parents=True, exist_ok=True)


def read_csv_semicolon(path: Path) -> pd.DataFrame:
    for enc in ("utf-8-sig", "utf-8", "cp1251"):
        try:
            return pd.read_csv(path, sep=";", encoding=enc)
        except Exception:
            continue
    return pd.read_csv(path, sep=";")


def normalize_campaign_name(value: Any) -> str:
    name = _coerce_str(value).lower()
    return " ".join(name.split())


def download_to_path(context, url: str, dest: Path) -> bool:
    resp = context.request.get(url)
    if resp.status != 200:
        return False
    dest.write_bytes(resp.body())
    return True


def ensure_login(page, login_value: str, password_value: str) -> bool:
    def login_required() -> bool:
        if "sign-in" in page.url:
            return True
        try:
            if page.locator("input[type='password']").count() > 0:
                return True
        except Exception:
            return False
        return False

    page.goto("https://marketing.kaspi.kz/advertising/", wait_until="domcontentloaded")
    page.wait_for_timeout(1500)
    if not login_required():
        return True
    if not login_value or not password_value:
        return False

    inputs = page.locator("input:not([type='password'])")
    for i in range(min(inputs.count(), 10)):
        inp = inputs.nth(i)
        if not inp.is_visible():
            continue
        try:
            inp.fill(login_value)
            break
        except Exception:
            continue

    # Some flows are two-step (login -> continue -> password)
    if page.locator("input[type='password']").count() == 0:
        for label in ("Продолжить", "Далее", "Войти"):
            try:
                page.locator(f"button:has-text('{label}')").first.click(timeout=3000)
                break
            except Exception:
                continue
        page.wait_for_timeout(1500)

    try:
        page.locator("input[type='password']").first.fill(password_value)
    except Exception:
        return False

    for label in ("Войти", "Продолжить", "Далее"):
        try:
            page.locator(f"button:has-text('{label}')").first.click(timeout=5000)
            break
        except Exception:
            continue

    page.wait_for_timeout(4000)
    return not login_required()


def fetch_campaigns(context, merchant_id: str, target_date: str) -> list[dict[str, Any]]:
    campaigns: dict[str, dict[str, Any]] = {}
    for state in CAMPAIGN_STATES:
        url = CAMPAIGNS_URL.format(merchant_id=merchant_id, date=target_date, state=state)
        resp = context.request.get(url)
        if resp.status != 200:
            continue
        data = resp.json()
        items = data.get("data") if isinstance(data, dict) else []
        if not isinstance(items, list):
            continue
        for item in items:
            if not isinstance(item, dict):
                continue
            cid = str(item.get("id") or item.get("campaignId") or "")
            if not cid:
                continue
            item.setdefault("state", state)
            campaigns[cid] = item
    return list(campaigns.values())


def parse_campaign_products_csv(path: Path, campaign_id: str) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    df = read_csv_semicolon(path)
    rows = []
    for _, row in df.iterrows():
        rows.append(
            {
                "campaign_id": str(campaign_id),
                "sku_key": _coerce_str(row.get("Рекламируемый товар")),
                "product_name": _coerce_str(row.get("Товар")),
                "product_status": _coerce_str(row.get("Текущий статус")),
                "ad_score": _coerce_str(row.get("Рекламная оценка") or row.get("Оценка")),
                "bid_cpc": parse_number(row.get("Ставка за клик")),
                "views": parse_int(row.get("Просмотры")),
                "clicks": parse_int(row.get("Клики")),
                "ctr": parse_number(row.get("CTR")),
                "avg_cpc": parse_number(row.get("Ср. стоим. клика")),
                "cost": parse_number(row.get("Расходы на рекламу")),
                "gmv": parse_number(row.get("Сумма заказов")),
                "orders_total": parse_int(row.get("Все заказы")),
                "orders_direct": parse_int(row.get("Прямые заказы")),
                "orders_assisted": parse_int(row.get("Сопутствующие заказы")),
                "conversion_order": parse_number(row.get("CR")),
                "order_numbers": _coerce_str(row.get("Номера заказов")),
                "favorites": parse_int(row.get("В избранное")),
                "carts": parse_int(row.get("В корзину")),
                "acos_share": parse_number(row.get("Доля рекламных расходов")),
                "assisted_products": _coerce_str(row.get("Товары из сопутствующих заказов")),
            }
        )
    return rows


def parse_campaigns_report_csv(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    df = read_csv_semicolon(path)
    rows = []
    for _, row in df.iterrows():
        campaign_name = _coerce_str(row.get("Наименование"))
        extra: dict[str, Any] = {}
        report_row: dict[str, Any] = {
            "campaign_name": campaign_name,
        }
        for col in df.columns:
            if col == "Наименование":
                continue
            target = CAMPAIGN_REPORT_MAP.get(col)
            value = row.get(col)
            if target:
                if target in {"report_views", "report_clicks", "report_transactions", "report_favorites", "report_carts"}:
                    report_row[target] = parse_int(value)
                elif target in {"report_ctr", "report_avg_cpc", "report_cost", "report_gmv", "report_crr"}:
                    report_row[target] = parse_number(value)
                else:
                    report_row[target] = _coerce_str(value)
            else:
                extra[col] = _coerce_str(value)
        report_row["report_extra"] = json.dumps(extra, ensure_ascii=False) if extra else ""
        rows.append(report_row)
    return rows


def merge_campaign_report(
    campaign_rows: list[dict[str, Any]],
    report_rows: list[dict[str, Any]],
    run_log: dict[str, Any],
    target_date: str,
) -> None:
    if not report_rows:
        return
    report_by_name: dict[str, list[dict[str, Any]]] = {}
    for row in report_rows:
        key = normalize_campaign_name(row.get("campaign_name"))
        if not key:
            continue
        report_by_name.setdefault(key, []).append(row)

    duplicates = {k: v for k, v in report_by_name.items() if len(v) > 1}
    if duplicates:
        run_log.setdefault("report_duplicates", {})[target_date] = list(duplicates.keys())

    for campaign in campaign_rows:
        name_key = normalize_campaign_name(campaign.get("campaign_name"))
        matches = report_by_name.get(name_key, [])
        if not matches:
            run_log.setdefault("report_missing", {}).setdefault(target_date, []).append(
                campaign.get("campaign_name")
            )
            continue
        match = max(matches, key=lambda r: parse_number(r.get("report_cost")) or 0)
        for key, val in match.items():
            if key == "campaign_name":
                continue
            if val is None or val == "":
                continue
            campaign.setdefault(key, val)

def normalize_campaign_daily(
    target_date: str,
    merchant_id: str,
    store_code: str,
    campaigns: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    rows = []
    for item in campaigns:
        rows.append(
            {
                "date": target_date,
                "merchant_id": merchant_id,
                "store_code": store_code,
                "campaign_id": _coerce_str(item.get("id") or item.get("campaignId")),
                "campaign_name": _coerce_str(item.get("name")),
                "state": _coerce_str(item.get("state")),
                "daily_budget": parse_number(item.get("dailyBudget")),
                "default_bid": parse_number(item.get("defaultBid")),
                "views": parse_int(item.get("views")),
                "clicks": parse_int(item.get("clicks")),
                "favorites": parse_int(item.get("favorites")),
                "carts": parse_int(item.get("carts")),
                "ctr": parse_number(item.get("ctr")),
                "gmv": parse_number(item.get("gmv")),
                "transactions": parse_int(item.get("transactions")),
                "cost": parse_number(item.get("cost")),
                "crr": parse_number(item.get("crr")),
                "record_timestamp": _coerce_str(item.get("recordTimeStamp")),
            }
        )
    return rows


def merge_product_rows(
    csv_rows: list[dict[str, Any]],
    json_rows: list[dict[str, Any]],
    campaign_name: str,
    target_date: str,
    merchant_id: str,
    store_code: str,
) -> list[dict[str, Any]]:
    json_by_sku = {}
    json_by_merchant = {}
    json_by_title = {}

    for item in json_rows:
        sku = _coerce_str(item.get("sku"))
        if sku:
            json_by_sku[sku] = item
        msku = _coerce_str(item.get("merchantSku"))
        if msku:
            json_by_merchant[msku] = item
        title = _coerce_str(item.get("title"))
        if title:
            json_by_title.setdefault(title, []).append(item)

    merged = []

    for row in csv_rows:
        sku_key = _coerce_str(row.get("sku_key"))
        product_name = _coerce_str(row.get("product_name"))
        match = None
        if sku_key in json_by_sku:
            match = json_by_sku[sku_key]
        elif sku_key in json_by_merchant:
            match = json_by_merchant[sku_key]
        elif product_name in json_by_title and json_by_title[product_name]:
            match = json_by_title[product_name][0]

        def pick(csv_val, json_val):
            return csv_val if csv_val is not None else json_val

        def pick_score(item: dict[str, Any]) -> str:
            for key in (
                "adScore",
                "adRating",
                "rating",
                "productRate",
                "productRating",
                "adsRating",
                "score",
            ):
                if key in item and item.get(key) is not None:
                    return _coerce_str(item.get(key))
            return ""

        merged.append(
            {
                "date": target_date,
                "merchant_id": merchant_id,
                "store_code": store_code,
                "campaign_id": row.get("campaign_id"),
                "campaign_name": campaign_name,
                "sku_key": sku_key,
                "product_name": product_name,
                "product_status": row.get("product_status") or _coerce_str(match.get("productState"))
                if match
                else row.get("product_status"),
                "ad_score": row.get("ad_score") or (pick_score(match) if match else ""),
                "bid_cpc": pick(row.get("bid_cpc"), parse_number(match.get("bid")) if match else None),
                "avg_cpc": pick(row.get("avg_cpc"), parse_number(match.get("avgCpc")) if match else None),
                "views": pick(row.get("views"), parse_int(match.get("views")) if match else None),
                "clicks": pick(row.get("clicks"), parse_int(match.get("clicks")) if match else None),
                "favorites": pick(row.get("favorites"), parse_int(match.get("favorites")) if match else None),
                "carts": pick(row.get("carts"), parse_int(match.get("carts")) if match else None),
                "ctr": pick(row.get("ctr"), parse_number(match.get("ctr")) if match else None),
                "gmv": pick(row.get("gmv"), parse_number(match.get("gmv")) if match else None),
                "orders_total": pick(
                    row.get("orders_total"),
                    parse_int(match.get("transactions")) if match else None,
                ),
                "orders_direct": pick(
                    row.get("orders_direct"),
                    parse_int(match.get("directTransactions")) if match else None,
                ),
                "orders_assisted": pick(
                    row.get("orders_assisted"),
                    parse_int(match.get("inDirectTransactions")) if match else None,
                ),
                "conversion_order": pick(row.get("conversion_order"), parse_number(match.get("cr")) if match else None),
                "cost": pick(row.get("cost"), parse_number(match.get("cost")) if match else None),
                "acos_share": pick(row.get("acos_share"), parse_number(match.get("crr")) if match else None),
                "order_numbers": row.get("order_numbers"),
                "assisted_products": row.get("assisted_products"),
                "json_sku": _coerce_str(match.get("sku")) if match else "",
                "json_merchant_sku": _coerce_str(match.get("merchantSku")) if match else "",
            }
        )

    return merged


def ensure_db_schema(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS campaign_daily_history (
            run_id TEXT,
            ingested_at TEXT,
            date TEXT,
            merchant_id TEXT,
            store_code TEXT,
            campaign_id TEXT,
            campaign_name TEXT,
            state TEXT,
            daily_budget REAL,
            default_bid REAL,
            views INTEGER,
            clicks INTEGER,
            favorites INTEGER,
            carts INTEGER,
            ctr REAL,
            gmv REAL,
            transactions INTEGER,
            cost REAL,
            crr REAL,
            report_state TEXT,
            report_views INTEGER,
            report_clicks INTEGER,
            report_ctr REAL,
            report_avg_cpc REAL,
            report_cost REAL,
            report_gmv REAL,
            report_transactions INTEGER,
            report_favorites INTEGER,
            report_carts INTEGER,
            report_crr REAL,
            report_extra TEXT,
            record_timestamp TEXT
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS campaign_product_daily_history (
            run_id TEXT,
            ingested_at TEXT,
            date TEXT,
            merchant_id TEXT,
            store_code TEXT,
            campaign_id TEXT,
            campaign_name TEXT,
            sku_key TEXT,
            product_name TEXT,
            product_status TEXT,
            ad_score TEXT,
            bid_cpc REAL,
            avg_cpc REAL,
            views INTEGER,
            clicks INTEGER,
            favorites INTEGER,
            carts INTEGER,
            ctr REAL,
            gmv REAL,
            orders_total INTEGER,
            orders_direct INTEGER,
            orders_assisted INTEGER,
            conversion_order REAL,
            cost REAL,
            acos_share REAL,
            order_numbers TEXT,
            assisted_products TEXT,
            json_sku TEXT,
            json_merchant_sku TEXT
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS campaign_daily_current (
            date TEXT,
            merchant_id TEXT,
            store_code TEXT,
            campaign_id TEXT,
            campaign_name TEXT,
            state TEXT,
            daily_budget REAL,
            default_bid REAL,
            views INTEGER,
            clicks INTEGER,
            favorites INTEGER,
            carts INTEGER,
            ctr REAL,
            gmv REAL,
            transactions INTEGER,
            cost REAL,
            crr REAL,
            report_state TEXT,
            report_views INTEGER,
            report_clicks INTEGER,
            report_ctr REAL,
            report_avg_cpc REAL,
            report_cost REAL,
            report_gmv REAL,
            report_transactions INTEGER,
            report_favorites INTEGER,
            report_carts INTEGER,
            report_crr REAL,
            report_extra TEXT,
            record_timestamp TEXT,
            ingested_at TEXT,
            PRIMARY KEY (date, merchant_id, campaign_id)
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS campaign_product_daily_current (
            date TEXT,
            merchant_id TEXT,
            store_code TEXT,
            campaign_id TEXT,
            campaign_name TEXT,
            sku_key TEXT,
            product_name TEXT,
            product_status TEXT,
            ad_score TEXT,
            bid_cpc REAL,
            avg_cpc REAL,
            views INTEGER,
            clicks INTEGER,
            favorites INTEGER,
            carts INTEGER,
            ctr REAL,
            gmv REAL,
            orders_total INTEGER,
            orders_direct INTEGER,
            orders_assisted INTEGER,
            conversion_order REAL,
            cost REAL,
            acos_share REAL,
            order_numbers TEXT,
            assisted_products TEXT,
            json_sku TEXT,
            json_merchant_sku TEXT,
            ingested_at TEXT,
            PRIMARY KEY (date, merchant_id, campaign_id, sku_key)
        )
        """
    )
    conn.commit()

    def ensure_columns(table: str, columns: list[tuple[str, str]]) -> None:
        existing = {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}
        for col, col_type in columns:
            if col not in existing:
                conn.execute(f"ALTER TABLE {table} ADD COLUMN {col} {col_type}")

    ensure_columns(
        "campaign_product_daily_history",
        [
            ("ad_score", "TEXT"),
            ("bid_cpc", "REAL"),
        ],
    )
    ensure_columns(
        "campaign_product_daily_current",
        [
            ("ad_score", "TEXT"),
            ("bid_cpc", "REAL"),
        ],
    )
    ensure_columns(
        "campaign_daily_history",
        [
            ("report_state", "TEXT"),
            ("report_views", "INTEGER"),
            ("report_clicks", "INTEGER"),
            ("report_ctr", "REAL"),
            ("report_avg_cpc", "REAL"),
            ("report_cost", "REAL"),
            ("report_gmv", "REAL"),
            ("report_transactions", "INTEGER"),
            ("report_favorites", "INTEGER"),
            ("report_carts", "INTEGER"),
            ("report_crr", "REAL"),
            ("report_extra", "TEXT"),
        ],
    )
    ensure_columns(
        "campaign_daily_current",
        [
            ("report_state", "TEXT"),
            ("report_views", "INTEGER"),
            ("report_clicks", "INTEGER"),
            ("report_ctr", "REAL"),
            ("report_avg_cpc", "REAL"),
            ("report_cost", "REAL"),
            ("report_gmv", "REAL"),
            ("report_transactions", "INTEGER"),
            ("report_favorites", "INTEGER"),
            ("report_carts", "INTEGER"),
            ("report_crr", "REAL"),
            ("report_extra", "TEXT"),
        ],
    )
    conn.commit()


def insert_history(conn: sqlite3.Connection, table: str, rows: list[dict[str, Any]]) -> None:
    if not rows:
        return
    cols = list(rows[0].keys())
    placeholders = ",".join(["?"] * len(cols))
    sql = f"INSERT INTO {table} ({','.join(cols)}) VALUES ({placeholders})"
    conn.executemany(sql, [[row.get(c) for c in cols] for row in rows])


def upsert_current(
    conn: sqlite3.Connection,
    table: str,
    rows: list[dict[str, Any]],
    key_cols: list[str],
    cost_col: str,
    anomalies: list[dict[str, Any]],
) -> None:
    if not rows:
        return

    for row in rows:
        key_vals = [row.get(k) for k in key_cols]
        where = " AND ".join([f"{k}=?" for k in key_cols])
        cur = conn.execute(f"SELECT {cost_col} FROM {table} WHERE {where}", key_vals)
        existing = cur.fetchone()
        new_cost = row.get(cost_col) or 0
        if existing is None:
            cols = list(row.keys())
            placeholders = ",".join(["?"] * len(cols))
            conn.execute(
                f"INSERT INTO {table} ({','.join(cols)}) VALUES ({placeholders})",
                [row.get(c) for c in cols],
            )
        else:
            old_cost = existing[0] or 0
            if new_cost > old_cost:
                cols = list(row.keys())
                set_clause = ",".join([f"{c}=?" for c in cols])
                conn.execute(
                    f"UPDATE {table} SET {set_clause} WHERE {where}",
                    [row.get(c) for c in cols] + key_vals,
                )
                anomalies.append(
                    {
                        "table": table,
                        "key": dict(zip(key_cols, key_vals)),
                        "old_cost": old_cost,
                        "new_cost": new_cost,
                    }
                )
    conn.commit()


def normalize_excel_df(df: pd.DataFrame, id_cols: set[str], date_cols: set[str]) -> pd.DataFrame:
    df = df.copy()
    for col in id_cols:
        if col in df.columns:
            df[col] = df[col].apply(_coerce_str)
    for col in date_cols:
        if col in df.columns:
            df[col] = pd.to_datetime(df[col], errors="coerce").dt.date
    return df


def normalize_row_keys(rows: list[dict[str, Any]]) -> None:
    if not rows:
        return
    all_keys: set[str] = set()
    for row in rows:
        all_keys.update(row.keys())
    for row in rows:
        for key in all_keys:
            row.setdefault(key, None)


def update_bookkeeper(
    path: Path,
    sheet_name: str,
    rows: list[dict[str, Any]],
    key_cols: list[str],
    cost_col: str,
    anomalies: list[dict[str, Any]],
    backup_dir: Path,
) -> None:
    if not rows:
        return

    ensure_dirs(path.parent, backup_dir)
    ingested_at = datetime.now(ALMATY_TZ).isoformat()

    new_df = pd.DataFrame(rows)
    new_df["ingested_at"] = ingested_at
    new_df = normalize_excel_df(new_df, ID_COLUMNS | set(key_cols), DATE_COLUMNS)

    if path.exists():
        backup = backup_dir / f"{path.stem}_{datetime.now(ALMATY_TZ).strftime('%Y%m%d_%H%M%S')}.xlsx"
        backup.write_bytes(path.read_bytes())
        try:
            existing_sheets = pd.read_excel(
                path,
                sheet_name=None,
                dtype={col: str for col in ID_COLUMNS},
            )
        except Exception:
            existing_sheets = {}
    else:
        existing_sheets = {}

    existing_df = existing_sheets.get(sheet_name, pd.DataFrame())
    existing_df = normalize_excel_df(existing_df, ID_COLUMNS | set(key_cols), DATE_COLUMNS)

    if not existing_df.empty and cost_col in existing_df.columns:
        existing_df[cost_col] = existing_df[cost_col].apply(parse_number)

    if existing_df.empty:
        merged_df = new_df.copy()
    else:
        merged_records = existing_df.to_dict(orient="records")
        merged_index = {tuple(_coerce_str(r.get(k)) for k in key_cols): i for i, r in enumerate(merged_records)}
        for _, row in new_df.iterrows():
            key = tuple(_coerce_str(row.get(k)) for k in key_cols)
            new_cost = parse_number(row.get(cost_col)) or 0
            if key not in merged_index:
                merged_records.append(row.to_dict())
                merged_index[key] = len(merged_records) - 1
            else:
                idx = merged_index[key]
                old_cost = parse_number(merged_records[idx].get(cost_col)) or 0
                if new_cost > old_cost:
                    merged_records[idx] = row.to_dict()
                    anomalies.append(
                        {
                            "sheet": sheet_name,
                            "key": dict(zip(key_cols, key)),
                            "old_cost": old_cost,
                            "new_cost": new_cost,
                        }
                    )
        merged_df = pd.DataFrame(merged_records)

    existing_cols = existing_df.columns.tolist() if not existing_df.empty else []
    combined_cols = existing_cols + [c for c in new_df.columns if c not in existing_cols]
    if "ingested_at" not in combined_cols:
        combined_cols.append("ingested_at")
    for col in combined_cols:
        if col not in merged_df.columns:
            merged_df[col] = ""
    merged_df = merged_df[combined_cols]
    merged_df = normalize_excel_df(merged_df, ID_COLUMNS | set(key_cols), DATE_COLUMNS)

    existing_sheets[sheet_name] = merged_df

    temp_path = path.with_suffix(".tmp.xlsx")
    with pd.ExcelWriter(temp_path, engine="openpyxl") as writer:
        for sheet, df in existing_sheets.items():
            df.to_excel(writer, sheet_name=sheet, index=False)
    temp_path.replace(path)

    try:
        check = pd.read_excel(path, sheet_name=None)
    except Exception as exc:
        raise RuntimeError(f"Bookkeeper validation failed for {path}") from exc
    if sheet_name not in check:
        raise RuntimeError(f"Bookkeeper sheet missing after write: {sheet_name}")


def export_to_app_db(app_db: Path, source_db: Path) -> None:
    if not app_db.exists() or not source_db.exists():
        return
    with sqlite3.connect(source_db) as src, sqlite3.connect(app_db) as dest:
        dest.execute("DROP TABLE IF EXISTS ads_campaign_daily_current")
        dest.execute("DROP TABLE IF EXISTS ads_campaign_product_daily_current")
        dest.execute(
            "CREATE TABLE ads_campaign_daily_current AS SELECT * FROM campaign_daily_current WHERE 0=1"
        )
        dest.execute(
            "CREATE TABLE ads_campaign_product_daily_current AS SELECT * FROM campaign_product_daily_current WHERE 0=1"
        )
        for row in src.execute("SELECT * FROM campaign_daily_current"):
            dest.execute(
                "INSERT INTO ads_campaign_daily_current VALUES (" + ",".join(["?"] * len(row)) + ")",
                row,
            )
        for row in src.execute("SELECT * FROM campaign_product_daily_current"):
            dest.execute(
                "INSERT INTO ads_campaign_product_daily_current VALUES (" + ",".join(["?"] * len(row)) + ")",
                row,
            )
        dest.commit()


def main() -> int:
    env_path = Path("~/Docs/Autonomous_business/.env")
    load_dotenv(env_path)
    env_profile_dir = os.environ.get("KASPI_MARKETING_PROFILE_DIR", DEFAULT_PROFILE_DIR)
    env_merchant_id = os.environ.get("KASPI_MARKETING_MERCHANT_ID", DEFAULT_MERCHANT_ID)
    env_store_code = os.environ.get("KASPI_MARKETING_STORE_CODE", DEFAULT_STORE_CODE)

    parser = argparse.ArgumentParser(description="Kaspi marketing ads scraper (API-first)")
    parser.add_argument("--date", help="Target date YYYY-MM-DD (default: yesterday)")
    parser.add_argument("--days-back", type=int, default=3, help="Number of days to re-run (default: 3)")
    parser.add_argument("--start-date", help="Start date YYYY-MM-DD (inclusive)")
    parser.add_argument("--end-date", help="End date YYYY-MM-DD (inclusive, default: target date)")
    parser.add_argument("--profile-dir", default=env_profile_dir)
    parser.add_argument("--merchant-id", default=env_merchant_id)
    parser.add_argument("--store-code", default=env_store_code)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--bookkeeper", type=Path, default=DEFAULT_BOOKKEEPER)
    parser.add_argument("--headful", action="store_true", help="Run with browser UI (default: headless)")
    parser.add_argument("--export-app-db", action="store_true", help="Export current tables into app.db")
    parser.add_argument("--app-db", type=Path, default=Path("~/Docs/Autonomous_business/db/app.db"))
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
    logger = logging.getLogger(__name__)

    login_value = os.environ.get("Kaspi_marketing_login") or os.environ.get("KASPI_MARKETING_LOGIN")
    password_value = os.environ.get("Kaspi_marketing_Password") or os.environ.get("KASPI_MARKETING_PASSWORD")

    if args.start_date and args.date:
        raise SystemExit("Use either --date or --start-date, not both.")

    if args.date:
        target = datetime.strptime(args.date, "%Y-%m-%d").date()
    else:
        target = datetime.now(ALMATY_TZ).date() - timedelta(days=1)

    if args.start_date:
        start = datetime.strptime(args.start_date, "%Y-%m-%d").date()
        end = datetime.strptime(args.end_date, "%Y-%m-%d").date() if args.end_date else target
        if end < start:
            raise SystemExit("--end-date cannot be before --start-date")
        days = [start + timedelta(days=i) for i in range((end - start).days + 1)]
    else:
        days = [target - timedelta(days=i) for i in range(max(args.days_back, 1))]
        days.sort()
    now = datetime.now(ALMATY_TZ)
    run_id = now.strftime("%Y%m%d_%H%M%S")
    ingested_at = now.isoformat()

    raw_root = args.output_root / "raw"
    details_root = args.output_root / "details"
    db_root = args.output_root / "db"
    log_root = args.output_root / "logs"
    ensure_dirs(raw_root, details_root, db_root, log_root)

    db_path = db_root / "kaspi_marketing.db"

    anomalies: list[dict[str, Any]] = []
    run_log: dict[str, Any] = {
        "run_id": run_id,
        "ingested_at": ingested_at,
        "dates": [d.isoformat() for d in days],
        "merchant_id": args.merchant_id,
        "store_code": args.store_code,
        "anomalies": anomalies,
        "download_failures": [],
        "notes": [],
    }

    with sqlite3.connect(db_path) as conn:
        ensure_db_schema(conn)

    with sync_playwright() as p:
        context = p.chromium.launch_persistent_context(
            user_data_dir=args.profile_dir,
            channel="chrome",
            headless=not args.headful,
        )
        page = context.new_page()

        if not ensure_login(page, login_value or "", password_value or ""):
            run_log["notes"].append("Login failed; aborting.")
            context.close()
            (log_root / f"scrape_{run_id}.json").write_text(
                json.dumps(run_log, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            return 1

        for day in days:
            target_date = day.isoformat()
            day_raw = raw_root / target_date / run_id
            day_details = details_root / target_date / run_id
            ensure_dirs(day_raw, day_details)

            # Campaign list
            campaigns = fetch_campaigns(context, args.merchant_id, target_date)
            run_log.setdefault("campaign_counts", {})[target_date] = len(campaigns)

            campaigns_json_path = day_raw / f"campaigns_{target_date}.json"
            campaigns_json_path.write_text(
                json.dumps(campaigns, ensure_ascii=False, indent=2), encoding="utf-8"
            )

            # Global campaigns report
            report_url = REPORT_CAMPAIGNS_URL.format(merchant_id=args.merchant_id, date=target_date)
            report_path = day_raw / f"campaigns_report_{target_date}_{run_id}.csv"
            if not download_to_path(context, report_url, report_path):
                run_log["download_failures"].append(
                    {"date": target_date, "type": "campaigns_report", "url": report_url}
                )
            report_rows = parse_campaigns_report_csv(report_path)
            if report_rows:
                run_log.setdefault("campaign_report_counts", {})[target_date] = len(report_rows)

            # Normalize campaign daily
            campaign_daily_rows = normalize_campaign_daily(target_date, args.merchant_id, args.store_code, campaigns)
            merge_campaign_report(campaign_daily_rows, report_rows, run_log, target_date)
            for row in campaign_daily_rows:
                row["run_id"] = run_id
                row["ingested_at"] = ingested_at
            normalize_row_keys(campaign_daily_rows)

            # Per-campaign details
            product_rows: list[dict[str, Any]] = []

            for campaign in campaigns:
                cid = str(campaign.get("id"))
                cname = _coerce_str(campaign.get("name"))

                # Per-campaign products CSV
                products_report_url = REPORT_PRODUCTS_URL.format(
                    merchant_id=args.merchant_id,
                    campaign_id=cid,
                    date=target_date,
                )
                products_report_path = day_raw / f"campaign_{cid}_products_{target_date}_{run_id}.csv"
                if not download_to_path(context, products_report_url, products_report_path):
                    run_log["download_failures"].append(
                        {
                            "date": target_date,
                            "campaign_id": cid,
                            "type": "campaign_products_report",
                            "url": products_report_url,
                        }
                    )
                csv_rows = parse_campaign_products_csv(products_report_path, cid)

                # JSON endpoints
                products_url = CAMPAIGN_PRODUCTS_URL.format(
                    merchant_id=args.merchant_id,
                    campaign_id=cid,
                    date=target_date,
                )
                products_json = []
                resp = context.request.get(products_url)
                if resp.status == 200:
                    data = resp.json()
                    products_json = data.get("data") if isinstance(data, dict) else []
                (day_raw / f"campaign_{cid}_products_api_{target_date}.json").write_text(
                    json.dumps(products_json, ensure_ascii=False, indent=2), encoding="utf-8"
                )

                # Extra metadata
                overview_url = CAMPAIGN_OVERVIEW_URL.format(merchant_id=args.merchant_id, campaign_id=cid)
                core_url = CAMPAIGN_CORE_URL.format(merchant_id=args.merchant_id, campaign_id=cid)
                categories_url = CAMPAIGN_CATEGORIES_URL.format(
                    merchant_id=args.merchant_id, campaign_id=cid, date=target_date
                )
                views_url = CAMPAIGN_DAILY_VIEWS_URL.format(merchant_id=args.merchant_id, campaign_id=cid)
                for extra_url, name in (
                    (overview_url, "overview"),
                    (core_url, "core"),
                    (categories_url, "categories"),
                    (views_url, "daily_views"),
                ):
                    extra_resp = context.request.get(extra_url)
                    if extra_resp.status == 200:
                        extra_data = extra_resp.json()
                        (day_raw / f"campaign_{cid}_{name}_{target_date}.json").write_text(
                            json.dumps(extra_data, ensure_ascii=False, indent=2), encoding="utf-8"
                        )

                merged = merge_product_rows(
                    csv_rows,
                    products_json if isinstance(products_json, list) else [],
                    cname,
                    target_date,
                    args.merchant_id,
                    args.store_code,
                )
                for row in merged:
                    row["run_id"] = run_id
                    row["ingested_at"] = ingested_at
                product_rows.extend(merged)

                time.sleep(0.2)

            normalize_row_keys(product_rows)

            # Save normalized CSVs
            pd.DataFrame(campaign_daily_rows).to_csv(
                day_details / f"campaign_daily_{target_date}.csv", index=False
            )
            pd.DataFrame(product_rows).to_csv(
                day_details / f"campaign_product_daily_{target_date}.csv", index=False
            )

            # DB writes
            with sqlite3.connect(db_path) as conn:
                insert_history(conn, "campaign_daily_history", campaign_daily_rows)
                insert_history(conn, "campaign_product_daily_history", product_rows)

                # Upsert current (cost increases only)
                upsert_current(
                    conn,
                    "campaign_daily_current",
                    [
                        {k: v for k, v in row.items() if k not in {"run_id"}}
                        for row in campaign_daily_rows
                    ],
                    ["date", "merchant_id", "campaign_id"],
                    "cost",
                    anomalies,
                )
                upsert_current(
                    conn,
                    "campaign_product_daily_current",
                    [
                        {k: v for k, v in row.items() if k not in {"run_id"}}
                        for row in product_rows
                    ],
                    ["date", "merchant_id", "campaign_id", "sku_key"],
                    "cost",
                    anomalies,
                )

            # Bookkeeper update
            backup_dir = args.bookkeeper.parent / "backups"
            update_bookkeeper(
                args.bookkeeper,
                "campaign_daily",
                [
                    {k: v for k, v in row.items() if k not in {"run_id"}}
                    for row in campaign_daily_rows
                ],
                ["date", "merchant_id", "campaign_id"],
                "cost",
                anomalies,
                backup_dir,
            )
            update_bookkeeper(
                args.bookkeeper,
                "campaign_product_daily",
                [
                    {k: v for k, v in row.items() if k not in {"run_id"}}
                    for row in product_rows
                ],
                ["date", "merchant_id", "campaign_id", "sku_key"],
                "cost",
                anomalies,
                backup_dir,
            )

        context.close()

    # Export to app.db if requested
    if args.export_app_db:
        export_to_app_db(args.app_db, db_path)

    log_path = log_root / f"scrape_{run_id}.json"
    log_path.write_text(json.dumps(run_log, ensure_ascii=False, indent=2), encoding="utf-8")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
