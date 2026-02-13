#!/usr/bin/env python3
"""Kaspi ads hourly snapshot collector with idempotent delta generation."""

from __future__ import annotations

import argparse
import fcntl
import json
import os
import sqlite3
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Mapping
from zoneinfo import ZoneInfo

try:
    from scripts.kaspi_ads_paths import (
        DEFAULT_WORKTREE_ADS_DB_PATH,
        PROD_ADS_DB_PATH,
        assert_ads_db_path_safe,
        copy_ads_db_once,
        resolve_ads_db_path,
    )
except ModuleNotFoundError:
    from kaspi_ads_paths import (  # type: ignore
        DEFAULT_WORKTREE_ADS_DB_PATH,
        PROD_ADS_DB_PATH,
        assert_ads_db_path_safe,
        copy_ads_db_once,
        resolve_ads_db_path,
    )

ALMATY_TZ = ZoneInfo("Asia/Almaty")
PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_LOCK_FILE = PROJECT_ROOT / "logs" / ".kaspi_ads_lock"
DEFAULT_MERCHANT_ID = "759051"
DEFAULT_MERCHANT_IDS = [DEFAULT_MERCHANT_ID]
DEFAULT_PROFILE_DIR = "~/Library/Application Support/ChromePlaywrightProfile4"
DEFAULT_CREDENTIAL_PROFILE = "default"

CAMPAIGNS_URL = (
    "https://marketing.kaspi.kz/advertising/products/api/v5/merchant/{merchant_id}"
    "/Campaigns?StartDate={date}&EndDate={date}&state=Enabled"
)
CAMPAIGN_PRODUCTS_URL = (
    "https://marketing.kaspi.kz/advertising/products/api/v5/merchant/{merchant_id}"
    "/campaign/{campaign_id}/products?StartDate={date}&EndDate={date}"
)


def _env_get(env: Mapping[str, str] | Any | None, key: str) -> str | None:
    if env is None:
        return os.environ.get(key)
    if isinstance(env, Mapping):
        value = env.get(key)
        return None if value is None else str(value)
    getter = getattr(env, "get", None)
    if callable(getter):
        value = getter(key)
        return None if value is None else str(value)
    return None


def load_env_file(path: Path | None) -> dict[str, str]:
    if path is None or not path.exists():
        return {}
    env_map: dict[str, str] = {}
    for raw in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key_txt = key.strip()
        if not key_txt:
            continue
        env_map[key_txt] = value.strip()
    return env_map


def _split_csv(value: str | None) -> list[str]:
    if value is None:
        return []
    out: list[str] = []
    for part in str(value).split(","):
        item = part.strip()
        if item:
            out.append(item)
    return out


def parse_merchant_ids(
    *,
    merchant_id_arg: str | None,
    merchant_ids_arg: str | None,
    env: Mapping[str, str] | Any | None = None,
    default_ids: list[str] | None = None,
) -> list[str]:
    values: list[str]
    if _split_csv(merchant_ids_arg):
        values = _split_csv(merchant_ids_arg)
    elif merchant_id_arg and str(merchant_id_arg).strip():
        values = [str(merchant_id_arg).strip()]
    else:
        env_multi = _split_csv(_env_get(env, "KASPI_MARKETING_MERCHANT_IDS"))
        if env_multi:
            values = env_multi
        else:
            env_single = (_env_get(env, "KASPI_MARKETING_MERCHANT_ID") or "").strip()
            if env_single:
                values = [env_single]
            else:
                values = list(default_ids or DEFAULT_MERCHANT_IDS)

    deduped: list[str] = []
    seen: set[str] = set()
    for item in values:
        if item not in seen:
            seen.add(item)
            deduped.append(item)
    return deduped


def resolve_marketing_credentials(
    *,
    credential_profile: str,
    env: Mapping[str, str] | Any | None = None,
) -> tuple[str, str]:
    profile = (credential_profile or DEFAULT_CREDENTIAL_PROFILE).strip().lower()
    if profile == "universal":
        login_keys = [
            "Kaspi_marketing_login_UNIVERSAL",
            "KASPI_MARKETING_LOGIN_UNIVERSAL",
            "Kaspi_marketing_login",
            "KASPI_MARKETING_LOGIN",
        ]
        password_keys = [
            "Kaspi_marketing_Password_UNIVERSAL",
            "KASPI_MARKETING_PASSWORD_UNIVERSAL",
            "Kaspi_marketing_Password",
            "KASPI_MARKETING_PASSWORD",
        ]
    else:
        login_keys = [
            "Kaspi_marketing_login",
            "KASPI_MARKETING_LOGIN",
            "Kaspi_marketing_login_UNIVERSAL",
            "KASPI_MARKETING_LOGIN_UNIVERSAL",
        ]
        password_keys = [
            "Kaspi_marketing_Password",
            "KASPI_MARKETING_PASSWORD",
            "Kaspi_marketing_Password_UNIVERSAL",
            "KASPI_MARKETING_PASSWORD_UNIVERSAL",
        ]

    login_value = ""
    password_value = ""
    for key in login_keys:
        value = (_env_get(env, key) or "").strip()
        if value:
            login_value = value
            break
    for key in password_keys:
        value = (_env_get(env, key) or "").strip()
        if value:
            password_value = value
            break

    return login_value, password_value


def _num_int(value: Any) -> int:
    if value is None:
        return 0
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(round(value))
    txt = str(value).strip()
    if not txt:
        return 0
    txt = txt.replace("\u00a0", " ").replace(" ", "").replace("₸", "").replace("%", "")
    txt = txt.replace(",", ".")
    try:
        return int(round(float(txt)))
    except ValueError:
        return 0


def _num_float(value: Any) -> float:
    if value is None:
        return 0.0
    if isinstance(value, (int, float)):
        return float(value)
    txt = str(value).strip()
    if not txt:
        return 0.0
    txt = txt.replace("\u00a0", " ").replace(" ", "").replace("₸", "").replace("%", "")
    txt = txt.replace(",", ".")
    try:
        return float(txt)
    except ValueError:
        return 0.0


def _str(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def ensure_schema(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS hourly_snapshot (
            snapshot_id INTEGER PRIMARY KEY AUTOINCREMENT,
            snapshot_at TEXT NOT NULL,
            snapshot_hour INTEGER NOT NULL,
            date TEXT NOT NULL,
            merchant_id TEXT NOT NULL,
            campaign_id TEXT NOT NULL,
            campaign_name TEXT,
            sku_key TEXT NOT NULL,
            bid_cpc REAL,
            views_cumul INTEGER,
            clicks_cumul INTEGER,
            cost_cumul REAL,
            gmv_cumul REAL,
            orders_cumul INTEGER,
            favorites_cumul INTEGER,
            carts_cumul INTEGER,
            cost_today REAL,
            ingested_at TEXT DEFAULT (datetime('now')),
            UNIQUE(date, snapshot_hour, merchant_id, campaign_id, sku_key)
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS hourly_delta (
            delta_id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT NOT NULL,
            hour_start INTEGER NOT NULL,
            hour_end INTEGER NOT NULL,
            merchant_id TEXT NOT NULL,
            campaign_id TEXT NOT NULL,
            sku_key TEXT NOT NULL,
            bid_cpc REAL,
            views_delta INTEGER,
            clicks_delta INTEGER,
            cost_delta REAL,
            gmv_delta REAL,
            orders_delta INTEGER,
            favorites_delta INTEGER,
            carts_delta INTEGER,
            delta_method TEXT,
            is_reset_anomaly INTEGER NOT NULL DEFAULT 0,
            snapshot_at TEXT,
            ingested_at TEXT DEFAULT (datetime('now')),
            UNIQUE(date, hour_start, hour_end, merchant_id, campaign_id, sku_key)
        )
        """
    )
    conn.commit()


def _load_prev_snapshot(
    conn: sqlite3.Connection,
    *,
    date_value: str,
    snapshot_hour: int,
    merchant_id: str,
    campaign_id: str,
    sku_key: str,
) -> tuple[Any, ...] | None:
    return conn.execute(
        """
        SELECT
            snapshot_hour,
            views_cumul,
            clicks_cumul,
            cost_cumul,
            gmv_cumul,
            orders_cumul,
            favorites_cumul,
            carts_cumul
        FROM hourly_snapshot
        WHERE date = ?
          AND merchant_id = ?
          AND campaign_id = ?
          AND sku_key = ?
          AND snapshot_hour < ?
        ORDER BY snapshot_hour DESC
        LIMIT 1
        """,
        (date_value, merchant_id, campaign_id, sku_key, snapshot_hour),
    ).fetchone()


def _upsert_snapshot_row(conn: sqlite3.Connection, row: dict[str, Any]) -> None:
    conn.execute(
        """
        INSERT INTO hourly_snapshot (
            snapshot_at,
            snapshot_hour,
            date,
            merchant_id,
            campaign_id,
            campaign_name,
            sku_key,
            bid_cpc,
            views_cumul,
            clicks_cumul,
            cost_cumul,
            gmv_cumul,
            orders_cumul,
            favorites_cumul,
            carts_cumul,
            cost_today
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(date, snapshot_hour, merchant_id, campaign_id, sku_key)
        DO UPDATE SET
            snapshot_at=excluded.snapshot_at,
            campaign_name=excluded.campaign_name,
            bid_cpc=excluded.bid_cpc,
            views_cumul=excluded.views_cumul,
            clicks_cumul=excluded.clicks_cumul,
            cost_cumul=excluded.cost_cumul,
            gmv_cumul=excluded.gmv_cumul,
            orders_cumul=excluded.orders_cumul,
            favorites_cumul=excluded.favorites_cumul,
            carts_cumul=excluded.carts_cumul,
            cost_today=excluded.cost_today,
            ingested_at=datetime('now')
        """,
        (
            row["snapshot_at"],
            row["snapshot_hour"],
            row["date"],
            row["merchant_id"],
            row["campaign_id"],
            row["campaign_name"],
            row["sku_key"],
            row["bid_cpc"],
            row["views_cumul"],
            row["clicks_cumul"],
            row["cost_cumul"],
            row["gmv_cumul"],
            row["orders_cumul"],
            row["favorites_cumul"],
            row["carts_cumul"],
            row["cost_today"],
        ),
    )


def _upsert_delta_row(conn: sqlite3.Connection, row: dict[str, Any]) -> None:
    conn.execute(
        """
        INSERT INTO hourly_delta (
            date,
            hour_start,
            hour_end,
            merchant_id,
            campaign_id,
            sku_key,
            bid_cpc,
            views_delta,
            clicks_delta,
            cost_delta,
            gmv_delta,
            orders_delta,
            favorites_delta,
            carts_delta,
            delta_method,
            is_reset_anomaly,
            snapshot_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(date, hour_start, hour_end, merchant_id, campaign_id, sku_key)
        DO UPDATE SET
            bid_cpc=excluded.bid_cpc,
            views_delta=excluded.views_delta,
            clicks_delta=excluded.clicks_delta,
            cost_delta=excluded.cost_delta,
            gmv_delta=excluded.gmv_delta,
            orders_delta=excluded.orders_delta,
            favorites_delta=excluded.favorites_delta,
            carts_delta=excluded.carts_delta,
            delta_method=excluded.delta_method,
            is_reset_anomaly=excluded.is_reset_anomaly,
            snapshot_at=excluded.snapshot_at,
            ingested_at=datetime('now')
        """,
        (
            row["date"],
            row["hour_start"],
            row["hour_end"],
            row["merchant_id"],
            row["campaign_id"],
            row["sku_key"],
            row["bid_cpc"],
            row["views_delta"],
            row["clicks_delta"],
            row["cost_delta"],
            row["gmv_delta"],
            row["orders_delta"],
            row["favorites_delta"],
            row["carts_delta"],
            row["delta_method"],
            row["is_reset_anomaly"],
            row["snapshot_at"],
        ),
    )


def persist_hourly_snapshot(
    conn: sqlite3.Connection,
    *,
    snapshot_at: datetime,
    rows: list[dict[str, Any]],
) -> dict[str, int]:
    ensure_schema(conn)

    snapshot_hour = int(snapshot_at.hour)
    snapshot_at_iso = snapshot_at.isoformat()
    snapshot_upserts = 0
    delta_upserts = 0
    reset_anomalies = 0

    for raw in rows:
        normalized = {
            "snapshot_at": snapshot_at_iso,
            "snapshot_hour": snapshot_hour,
            "date": _str(raw.get("date")),
            "merchant_id": _str(raw.get("merchant_id")),
            "campaign_id": _str(raw.get("campaign_id")),
            "campaign_name": _str(raw.get("campaign_name")),
            "sku_key": _str(raw.get("sku_key")),
            "bid_cpc": _num_float(raw.get("bid_cpc")),
            "views_cumul": _num_int(raw.get("views_cumul")),
            "clicks_cumul": _num_int(raw.get("clicks_cumul")),
            "cost_cumul": _num_float(raw.get("cost_cumul")),
            "gmv_cumul": _num_float(raw.get("gmv_cumul")),
            "orders_cumul": _num_int(raw.get("orders_cumul")),
            "favorites_cumul": _num_int(raw.get("favorites_cumul")),
            "carts_cumul": _num_int(raw.get("carts_cumul")),
            "cost_today": _num_float(raw.get("cost_today")),
        }

        if not normalized["date"]:
            normalized["date"] = snapshot_at.date().isoformat()
        if not normalized["merchant_id"] or not normalized["campaign_id"] or not normalized["sku_key"]:
            continue

        _upsert_snapshot_row(conn, normalized)
        snapshot_upserts += 1

        prev = _load_prev_snapshot(
            conn,
            date_value=normalized["date"],
            snapshot_hour=snapshot_hour,
            merchant_id=normalized["merchant_id"],
            campaign_id=normalized["campaign_id"],
            sku_key=normalized["sku_key"],
        )

        metrics = [
            "views",
            "clicks",
            "cost",
            "gmv",
            "orders",
            "favorites",
            "carts",
        ]
        current_values = {
            "views": int(normalized["views_cumul"]),
            "clicks": int(normalized["clicks_cumul"]),
            "cost": float(normalized["cost_cumul"]),
            "gmv": float(normalized["gmv_cumul"]),
            "orders": int(normalized["orders_cumul"]),
            "favorites": int(normalized["favorites_cumul"]),
            "carts": int(normalized["carts_cumul"]),
        }

        hour_start = 0
        method = "day_start"
        reset_flag = 0
        deltas: dict[str, float] = {}

        if prev is None:
            for metric in metrics:
                deltas[metric] = float(current_values[metric])
        else:
            prev_hour = int(prev[0])
            hour_start = prev_hour
            prev_values = {
                "views": _num_int(prev[1]),
                "clicks": _num_int(prev[2]),
                "cost": _num_float(prev[3]),
                "gmv": _num_float(prev[4]),
                "orders": _num_int(prev[5]),
                "favorites": _num_int(prev[6]),
                "carts": _num_int(prev[7]),
            }
            negatives = False
            for metric in metrics:
                delta_val = float(current_values[metric]) - float(prev_values[metric])
                if delta_val < 0:
                    negatives = True
                deltas[metric] = max(0.0, delta_val)

            if negatives:
                method = "reset_anomaly"
                reset_flag = 1
                reset_anomalies += 1
            elif snapshot_hour - prev_hour > 1:
                method = "gap_interpolated"
            else:
                method = "sequential"

        _upsert_delta_row(
            conn,
            {
                "date": normalized["date"],
                "hour_start": hour_start,
                "hour_end": snapshot_hour,
                "merchant_id": normalized["merchant_id"],
                "campaign_id": normalized["campaign_id"],
                "sku_key": normalized["sku_key"],
                "bid_cpc": normalized["bid_cpc"],
                "views_delta": int(round(deltas["views"])),
                "clicks_delta": int(round(deltas["clicks"])),
                "cost_delta": float(deltas["cost"]),
                "gmv_delta": float(deltas["gmv"]),
                "orders_delta": int(round(deltas["orders"])),
                "favorites_delta": int(round(deltas["favorites"])),
                "carts_delta": int(round(deltas["carts"])),
                "delta_method": method,
                "is_reset_anomaly": reset_flag,
                "snapshot_at": snapshot_at_iso,
            },
        )
        delta_upserts += 1

    conn.commit()
    return {
        "snapshot_upserts": snapshot_upserts,
        "delta_upserts": delta_upserts,
        "reset_anomalies": reset_anomalies,
    }


def acquire_file_lock(
    lock_path: Path,
    *,
    timeout_seconds: float = 10.0,
    poll_seconds: float = 0.2,
    sleep_fn=time.sleep,
):
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    handle = open(lock_path, "w")
    deadline = time.time() + max(timeout_seconds, 0.0)

    while True:
        try:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            handle.seek(0)
            handle.truncate(0)
            handle.write(f"{os.getpid()}\n")
            handle.flush()
            return handle
        except BlockingIOError:
            if time.time() >= deadline:
                handle.close()
                return None
            sleep_fn(max(poll_seconds, 0.0))


def release_file_lock(handle, lock_path: Path) -> None:
    try:
        fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
    except Exception:
        pass
    try:
        handle.close()
    finally:
        try:
            if lock_path.exists():
                lock_path.unlink()
        except Exception:
            pass


def request_json_with_backoff(
    request_client,
    url: str,
    *,
    headers: dict[str, str] | None = None,
    max_attempts: int = 4,
    retry_statuses: tuple[int, ...] = (429, 500, 502, 503, 504),
    base_sleep_seconds: float = 0.5,
    sleep_fn=time.sleep,
):
    attempt = 0
    while attempt < max_attempts:
        attempt += 1
        resp = request_client.get(url, headers=headers)
        if resp.status == 200:
            return resp.json()

        if resp.status in retry_statuses and attempt < max_attempts:
            sleep_fn(base_sleep_seconds * (2 ** (attempt - 1)))
            continue

        raise RuntimeError(f"Kaspi API request failed: status={resp.status} url={url} attempt={attempt}")

    raise RuntimeError(f"Kaspi API request exhausted retries: url={url}")


def _collect_live_rows(
    *,
    context,
    merchant_id: str,
    target_date: str,
    headers: dict[str, str],
    max_attempts: int,
    base_sleep_seconds: float,
) -> list[dict[str, Any]]:
    campaigns_data = request_json_with_backoff(
        context.request,
        CAMPAIGNS_URL.format(merchant_id=merchant_id, date=target_date),
        headers=headers,
        max_attempts=max_attempts,
        base_sleep_seconds=base_sleep_seconds,
    )
    campaigns = campaigns_data.get("data") if isinstance(campaigns_data, dict) else []
    if not isinstance(campaigns, list):
        campaigns = []

    rows: list[dict[str, Any]] = []
    for campaign in campaigns:
        if not isinstance(campaign, dict):
            continue
        campaign_id = _str(campaign.get("id") or campaign.get("campaignId"))
        if not campaign_id:
            continue

        products_data = request_json_with_backoff(
            context.request,
            CAMPAIGN_PRODUCTS_URL.format(
                merchant_id=merchant_id,
                campaign_id=campaign_id,
                date=target_date,
            ),
            headers=headers,
            max_attempts=max_attempts,
            base_sleep_seconds=base_sleep_seconds,
        )
        products = products_data.get("data") if isinstance(products_data, dict) else []
        if not isinstance(products, list):
            products = []

        for product in products:
            if not isinstance(product, dict):
                continue
            sku_key = _str(
                product.get("id")
                or product.get("sku")
                or product.get("merchantSku")
                or product.get("title")
            )
            if not sku_key:
                continue
            rows.append(
                {
                    "date": target_date,
                    "merchant_id": merchant_id,
                    "campaign_id": campaign_id,
                    "campaign_name": _str(campaign.get("name")),
                    "sku_key": sku_key,
                    "bid_cpc": _num_float(product.get("bid")),
                    "views_cumul": _num_int(product.get("views")),
                    "clicks_cumul": _num_int(product.get("clicks")),
                    "cost_cumul": _num_float(product.get("cost")),
                    "gmv_cumul": _num_float(product.get("gmv")),
                    "orders_cumul": _num_int(product.get("transactions")),
                    "favorites_cumul": _num_int(product.get("favorites")),
                    "carts_cumul": _num_int(product.get("carts")),
                    "cost_today": _num_float(product.get("costToday") or product.get("cost")),
                }
            )

    return rows


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Collect Kaspi ads hourly snapshots")
    parser.add_argument("--ads-db", type=Path, default=None, help="Ads DB path (or set KASPI_MARKETING_DB_PATH)")
    parser.add_argument(
        "--ads-db-copy-source",
        type=Path,
        default=PROD_ADS_DB_PATH,
        help="Copy-once source DB when --ads-db points to a missing local DB",
    )
    parser.add_argument("--skip-ads-db-copy", action="store_true")
    parser.add_argument("--lock-file", type=Path, default=DEFAULT_LOCK_FILE)
    parser.add_argument("--lock-timeout", type=float, default=10.0)
    parser.add_argument(
        "--merchant-id",
        default=None,
        help="Single merchant ID target. Backward-compatible alias for --merchant-ids with one value.",
    )
    parser.add_argument(
        "--merchant-ids",
        default=None,
        help="Comma-separated merchant IDs (e.g. 759051,761413).",
    )
    parser.add_argument("--profile-dir", default=None)
    parser.add_argument("--env-file", type=Path, default=None, help="Optional .env file to source credentials from")
    parser.add_argument(
        "--credential-profile",
        default=DEFAULT_CREDENTIAL_PROFILE,
        choices=("default", "universal"),
        help="Credential profile used for login resolution.",
    )
    parser.add_argument("--date", default=datetime.now(ALMATY_TZ).date().isoformat())
    parser.add_argument("--snapshot-at", default=None, help="Override snapshot timestamp (ISO-8601)")
    parser.add_argument("--headful", action="store_true")
    parser.add_argument("--manual-login", action="store_true")
    parser.add_argument("--login-timeout", type=float, default=300.0)
    parser.add_argument("--max-attempts", type=int, default=4)
    parser.add_argument("--backoff-seconds", type=float, default=0.5)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    env_from_file = load_env_file(args.env_file)
    runtime_env: dict[str, str] = {**env_from_file, **dict(os.environ)}

    ads_db = resolve_ads_db_path(
        ads_db_arg=args.ads_db,
        default_path=DEFAULT_WORKTREE_ADS_DB_PATH,
    )
    assert_ads_db_path_safe(ads_db_path=ads_db)

    if not args.skip_ads_db_copy:
        copy_result = copy_ads_db_once(source_db=args.ads_db_copy_source, dest_db=ads_db)
        print(json.dumps({"ads_db_copy_once": copy_result}, ensure_ascii=False))

    lock_handle = acquire_file_lock(args.lock_file, timeout_seconds=args.lock_timeout)
    if lock_handle is None:
        print(json.dumps({"status": "skipped_locked", "lock_file": str(args.lock_file)}))
        return 0

    snapshot_at = (
        datetime.fromisoformat(args.snapshot_at).astimezone(ALMATY_TZ)
        if args.snapshot_at
        else datetime.now(ALMATY_TZ)
    )
    merchant_ids = parse_merchant_ids(
        merchant_id_arg=args.merchant_id,
        merchant_ids_arg=args.merchant_ids,
        env=runtime_env,
        default_ids=DEFAULT_MERCHANT_IDS,
    )
    profile_dir = args.profile_dir or runtime_env.get("KASPI_MARKETING_PROFILE_DIR") or DEFAULT_PROFILE_DIR

    try:
        with sqlite3.connect(ads_db) as conn:
            ensure_schema(conn)

            try:
                from playwright.sync_api import sync_playwright
            except ImportError as exc:
                raise SystemExit("Playwright is required. Install via: pip install playwright") from exc

            try:
                from scripts.kaspi_marketing_scrape import build_kaspi_headers, ensure_login
            except ModuleNotFoundError:
                from kaspi_marketing_scrape import build_kaspi_headers, ensure_login  # type: ignore

            login_value, password_value = resolve_marketing_credentials(
                credential_profile=args.credential_profile,
                env=runtime_env,
            )

            with sync_playwright() as p:
                context = p.chromium.launch_persistent_context(
                    user_data_dir=profile_dir,
                    channel="chrome",
                    headless=not args.headful,
                )
                try:
                    page = context.new_page()
                    if not ensure_login(
                        page,
                        login_value or "",
                        password_value or "",
                        manual_login=args.manual_login,
                        login_timeout=args.login_timeout,
                    ):
                        print(json.dumps({"status": "login_failed"}))
                        return 1

                    headers = build_kaspi_headers(
                        context.cookies(),
                        "https://marketing.kaspi.kz/advertising/campaigns",
                    )
                    all_rows: list[dict[str, Any]] = []
                    merchant_summary: list[dict[str, Any]] = []
                    for merchant_id in merchant_ids:
                        rows = _collect_live_rows(
                            context=context,
                            merchant_id=merchant_id,
                            target_date=args.date,
                            headers=headers,
                            max_attempts=max(1, args.max_attempts),
                            base_sleep_seconds=max(0.0, args.backoff_seconds),
                        )
                        all_rows.extend(rows)
                        merchant_summary.append(
                            {
                                "merchant_id": merchant_id,
                                "rows_collected": len(rows),
                                "campaign_ids_seen": sorted(
                                    {
                                        _str(row.get("campaign_id"))
                                        for row in rows
                                        if _str(row.get("campaign_id"))
                                    }
                                ),
                            }
                        )
                    summary = persist_hourly_snapshot(conn, snapshot_at=snapshot_at, rows=all_rows)
                    print(
                        json.dumps(
                            {
                                "status": "ok",
                                "ads_db": str(ads_db),
                                "snapshot_at": snapshot_at.isoformat(),
                                "merchant_ids": merchant_ids,
                                "credential_profile": args.credential_profile,
                                "rows_collected": len(all_rows),
                                "merchant_summary": merchant_summary,
                                **summary,
                            },
                            ensure_ascii=False,
                        )
                    )
                finally:
                    context.close()
    finally:
        release_file_lock(lock_handle, args.lock_file)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
