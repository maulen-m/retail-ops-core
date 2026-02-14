#!/usr/bin/env python3
"""Build Kaspi ads hourly activity profiles and validate hourly-vs-daily totals."""

from __future__ import annotations

import argparse
import json
import sqlite3
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

try:
    from scripts.kaspi_ads_paths import (
        DEFAULT_WORKTREE_ADS_DB_PATH,
        assert_ads_db_path_safe,
        resolve_ads_db_path,
    )
except ModuleNotFoundError:
    from kaspi_ads_paths import (  # type: ignore
        DEFAULT_WORKTREE_ADS_DB_PATH,
        assert_ads_db_path_safe,
        resolve_ads_db_path,
    )

ALMATY_TZ = ZoneInfo("Asia/Almaty")


def _table_exists(conn: sqlite3.Connection, table: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=? LIMIT 1",
        (table,),
    ).fetchone()
    return row is not None


def ensure_profile_schema(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS hourly_activity_profile (
            campaign_id TEXT NOT NULL,
            sku_key TEXT NOT NULL,
            hour INTEGER NOT NULL,
            days_observed INTEGER,
            avg_views REAL,
            avg_clicks REAL,
            avg_cost REAL,
            avg_orders REAL,
            pct_daily_views REAL,
            pct_daily_clicks REAL,
            pct_daily_orders REAL,
            classification TEXT,
            computed_at TEXT NOT NULL,
            UNIQUE(campaign_id, sku_key, hour)
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS hourly_reconciliation (
            date TEXT NOT NULL,
            merchant_id TEXT NOT NULL,
            campaign_id TEXT NOT NULL,
            sku_key TEXT NOT NULL,
            metric TEXT NOT NULL,
            hourly_total REAL NOT NULL,
            daily_total REAL NOT NULL,
            pct_diff REAL NOT NULL,
            within_tolerance INTEGER NOT NULL,
            tolerance_pct REAL NOT NULL,
            computed_at TEXT NOT NULL,
            UNIQUE(date, merchant_id, campaign_id, sku_key, metric)
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS hourly_delta_daily_fact (
            date TEXT NOT NULL,
            merchant_id TEXT NOT NULL,
            campaign_id TEXT NOT NULL,
            sku_key TEXT NOT NULL,
            bid_cpc REAL,
            views INTEGER NOT NULL DEFAULT 0,
            clicks INTEGER NOT NULL DEFAULT 0,
            cost REAL NOT NULL DEFAULT 0,
            gmv REAL NOT NULL DEFAULT 0,
            orders_total INTEGER NOT NULL DEFAULT 0,
            hour_rows INTEGER NOT NULL DEFAULT 0,
            computed_at TEXT NOT NULL,
            UNIQUE(date, merchant_id, campaign_id, sku_key)
        )
        """
    )
    conn.commit()


def _classify_hour(
    *,
    pct_daily_views: float,
    pct_daily_clicks: float,
    pct_daily_orders: float,
) -> str:
    peak_signal = max(pct_daily_clicks, pct_daily_orders, pct_daily_views)
    if peak_signal >= 15.0:
        return "peak"
    if peak_signal < 1.0:
        return "dead"
    if peak_signal < 5.0:
        return "low"
    return "normal"


def _where_clause(
    since: str | None,
    until: str | None,
    *,
    date_expr: str = "date",
) -> tuple[str, list[Any]]:
    where = ["1=1"]
    params: list[Any] = []
    if since:
        where.append(f"date({date_expr}) >= date(?)")
        params.append(since)
    if until:
        where.append(f"date({date_expr}) <= date(?)")
        params.append(until)
    return " AND ".join(where), params


def _upsert_profile_row(conn: sqlite3.Connection, row: dict[str, Any]) -> None:
    conn.execute(
        """
        INSERT INTO hourly_activity_profile (
            campaign_id, sku_key, hour, days_observed,
            avg_views, avg_clicks, avg_cost, avg_orders,
            pct_daily_views, pct_daily_clicks, pct_daily_orders,
            classification, computed_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(campaign_id, sku_key, hour)
        DO UPDATE SET
            days_observed=excluded.days_observed,
            avg_views=excluded.avg_views,
            avg_clicks=excluded.avg_clicks,
            avg_cost=excluded.avg_cost,
            avg_orders=excluded.avg_orders,
            pct_daily_views=excluded.pct_daily_views,
            pct_daily_clicks=excluded.pct_daily_clicks,
            pct_daily_orders=excluded.pct_daily_orders,
            classification=excluded.classification,
            computed_at=excluded.computed_at
        """,
        (
            row["campaign_id"],
            row["sku_key"],
            row["hour"],
            row["days_observed"],
            row["avg_views"],
            row["avg_clicks"],
            row["avg_cost"],
            row["avg_orders"],
            row["pct_daily_views"],
            row["pct_daily_clicks"],
            row["pct_daily_orders"],
            row["classification"],
            row["computed_at"],
        ),
    )


def _upsert_reconciliation_row(conn: sqlite3.Connection, row: dict[str, Any]) -> None:
    conn.execute(
        """
        INSERT INTO hourly_reconciliation (
            date, merchant_id, campaign_id, sku_key, metric,
            hourly_total, daily_total, pct_diff, within_tolerance,
            tolerance_pct, computed_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(date, merchant_id, campaign_id, sku_key, metric)
        DO UPDATE SET
            hourly_total=excluded.hourly_total,
            daily_total=excluded.daily_total,
            pct_diff=excluded.pct_diff,
            within_tolerance=excluded.within_tolerance,
            tolerance_pct=excluded.tolerance_pct,
            computed_at=excluded.computed_at
        """,
        (
            row["date"],
            row["merchant_id"],
            row["campaign_id"],
            row["sku_key"],
            row["metric"],
            row["hourly_total"],
            row["daily_total"],
            row["pct_diff"],
            row["within_tolerance"],
            row["tolerance_pct"],
            row["computed_at"],
        ),
    )


def _upsert_daily_fact_row(conn: sqlite3.Connection, row: dict[str, Any]) -> None:
    conn.execute(
        """
        INSERT INTO hourly_delta_daily_fact (
            date,
            merchant_id,
            campaign_id,
            sku_key,
            bid_cpc,
            views,
            clicks,
            cost,
            gmv,
            orders_total,
            hour_rows,
            computed_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(date, merchant_id, campaign_id, sku_key)
        DO UPDATE SET
            bid_cpc=excluded.bid_cpc,
            views=excluded.views,
            clicks=excluded.clicks,
            cost=excluded.cost,
            gmv=excluded.gmv,
            orders_total=excluded.orders_total,
            hour_rows=excluded.hour_rows,
            computed_at=excluded.computed_at
        """,
        (
            row["date"],
            row["merchant_id"],
            row["campaign_id"],
            row["sku_key"],
            row["bid_cpc"],
            row["views"],
            row["clicks"],
            row["cost"],
            row["gmv"],
            row["orders_total"],
            row["hour_rows"],
            row["computed_at"],
        ),
    )


def build_hourly_profile_and_reconciliation(
    conn: sqlite3.Connection,
    *,
    since: str | None = None,
    until: str | None = None,
    tolerance_pct: float = 5.0,
) -> dict[str, int]:
    ensure_profile_schema(conn)
    if not _table_exists(conn, "hourly_delta"):
        return {
            "profile_rows": 0,
            "daily_fact_rows": 0,
            "reconciliation_rows": 0,
            "reconciliation_failures": 0,
        }

    where_sql, params = _where_clause(since, until)
    rows = conn.execute(
        f"""
        SELECT
            date,
            hour_end,
            merchant_id,
            campaign_id,
            sku_key,
            COALESCE(views_delta, 0),
            COALESCE(clicks_delta, 0),
            COALESCE(cost_delta, 0),
            COALESCE(orders_delta, 0)
        FROM hourly_delta
        WHERE {where_sql}
        """,
        tuple(params),
    ).fetchall()

    profile_rollup: dict[tuple[str, str, int], dict[str, Any]] = {}
    profile_totals: dict[tuple[str, str], dict[str, float]] = defaultdict(
        lambda: {"views": 0.0, "clicks": 0.0, "cost": 0.0, "orders": 0.0}
    )

    for date_value, hour_end, _mid, cid, sku, views, clicks, cost, orders in rows:
        hour = int(hour_end)
        key = (str(cid), str(sku), hour)
        entry = profile_rollup.setdefault(
            key,
            {
                "campaign_id": str(cid),
                "sku_key": str(sku),
                "hour": hour,
                "days": set(),
                "views": 0.0,
                "clicks": 0.0,
                "cost": 0.0,
                "orders": 0.0,
            },
        )
        entry["days"].add(str(date_value))
        entry["views"] += float(views or 0)
        entry["clicks"] += float(clicks or 0)
        entry["cost"] += float(cost or 0)
        entry["orders"] += float(orders or 0)

        totals = profile_totals[(str(cid), str(sku))]
        totals["views"] += float(views or 0)
        totals["clicks"] += float(clicks or 0)
        totals["cost"] += float(cost or 0)
        totals["orders"] += float(orders or 0)

    computed_at = datetime.now(ALMATY_TZ).isoformat()
    profile_rows = 0
    for key, entry in profile_rollup.items():
        campaign_id, sku_key, _hour = key
        totals = profile_totals[(campaign_id, sku_key)]
        days_observed = max(len(entry["days"]), 1)

        pct_daily_views = round((entry["views"] / totals["views"] * 100.0), 2) if totals["views"] else 0.0
        pct_daily_clicks = round((entry["clicks"] / totals["clicks"] * 100.0), 2) if totals["clicks"] else 0.0
        pct_daily_orders = round((entry["orders"] / totals["orders"] * 100.0), 2) if totals["orders"] else 0.0

        _upsert_profile_row(
            conn,
            {
                "campaign_id": campaign_id,
                "sku_key": sku_key,
                "hour": entry["hour"],
                "days_observed": days_observed,
                "avg_views": round(entry["views"] / days_observed, 4),
                "avg_clicks": round(entry["clicks"] / days_observed, 4),
                "avg_cost": round(entry["cost"] / days_observed, 4),
                "avg_orders": round(entry["orders"] / days_observed, 4),
                "pct_daily_views": pct_daily_views,
                "pct_daily_clicks": pct_daily_clicks,
                "pct_daily_orders": pct_daily_orders,
                "classification": _classify_hour(
                    pct_daily_views=pct_daily_views,
                    pct_daily_clicks=pct_daily_clicks,
                    pct_daily_orders=pct_daily_orders,
                ),
                "computed_at": computed_at,
            },
        )
        profile_rows += 1

    where_sql_delta, params_delta = _where_clause(since, until, date_expr="d.date")
    hourly_totals_rows = conn.execute(
        f"""
        SELECT
            d.date,
            d.merchant_id,
            d.campaign_id,
            d.sku_key,
            (
                SELECT d2.bid_cpc
                FROM hourly_delta d2
                WHERE d2.date = d.date
                  AND d2.merchant_id = d.merchant_id
                  AND d2.campaign_id = d.campaign_id
                  AND d2.sku_key = d.sku_key
                  AND d2.bid_cpc IS NOT NULL
                ORDER BY d2.hour_end DESC, COALESCE(d2.snapshot_at, '') DESC, d2.delta_id DESC
                LIMIT 1
            ) AS latest_bid_cpc,
            COALESCE(SUM(d.views_delta), 0) AS views_total,
            COALESCE(SUM(d.clicks_delta), 0) AS clicks_total,
            COALESCE(SUM(d.cost_delta), 0) AS cost_total,
            COALESCE(SUM(d.gmv_delta), 0) AS gmv_total,
            COALESCE(SUM(d.orders_delta), 0) AS orders_total,
            COUNT(*) AS hour_rows
        FROM hourly_delta d
        WHERE {where_sql_delta}
        GROUP BY d.date, d.merchant_id, d.campaign_id, d.sku_key
        """,
        tuple(params_delta),
    ).fetchall()

    hourly_map: dict[tuple[str, str, str, str], dict[str, float]] = {}
    daily_fact_rows = 0
    for row in hourly_totals_rows:
        key = (str(row[0]), str(row[1]), str(row[2]), str(row[3]))
        hourly_map[key] = {
            "views": float(row[5]),
            "clicks": float(row[6]),
            "cost": float(row[7]),
            "gmv": float(row[8]),
            "orders": float(row[9]),
        }
        _upsert_daily_fact_row(
            conn,
            {
                "date": key[0],
                "merchant_id": key[1],
                "campaign_id": key[2],
                "sku_key": key[3],
                "bid_cpc": float(row[4] or 0.0),
                "views": int(float(row[5] or 0.0)),
                "clicks": int(float(row[6] or 0.0)),
                "cost": round(float(row[7] or 0.0), 6),
                "gmv": round(float(row[8] or 0.0), 6),
                "orders_total": int(float(row[9] or 0.0)),
                "hour_rows": int(row[10] or 0),
                "computed_at": computed_at,
            },
        )
        daily_fact_rows += 1

    daily_map: dict[tuple[str, str, str, str], dict[str, float]] = {}
    if _table_exists(conn, "campaign_product_daily_current"):
        daily_rows = conn.execute(
            f"""
            SELECT
                date,
                merchant_id,
                campaign_id,
                sku_key,
                COALESCE(views, 0),
                COALESCE(clicks, 0),
                COALESCE(cost, 0),
                COALESCE(gmv, 0),
                COALESCE(orders_total, 0)
            FROM campaign_product_daily_current
            WHERE {where_sql}
            """,
            tuple(params),
        ).fetchall()
        for row in daily_rows:
            key = (str(row[0]), str(row[1]), str(row[2]), str(row[3]))
            daily_map[key] = {
                "views": float(row[4]),
                "clicks": float(row[5]),
                "cost": float(row[6]),
                "gmv": float(row[7]),
                "orders": float(row[8]),
            }

    all_keys = set(hourly_map.keys()) | set(daily_map.keys())
    metrics = ("views", "clicks", "cost", "gmv", "orders")
    reconciliation_rows = 0
    reconciliation_failures = 0

    for key in sorted(all_keys):
        date_value, merchant_id, campaign_id, sku_key = key
        hourly_vals = hourly_map.get(key, {})
        daily_vals = daily_map.get(key, {})

        for metric in metrics:
            hourly_total = float(hourly_vals.get(metric, 0.0))
            daily_total = float(daily_vals.get(metric, 0.0))
            if abs(daily_total) < 1e-9:
                pct_diff = 0.0 if abs(hourly_total) < 1e-9 else 100.0
            else:
                pct_diff = abs(hourly_total - daily_total) / abs(daily_total) * 100.0
            within = 1 if pct_diff <= tolerance_pct else 0

            _upsert_reconciliation_row(
                conn,
                {
                    "date": date_value,
                    "merchant_id": merchant_id,
                    "campaign_id": campaign_id,
                    "sku_key": sku_key,
                    "metric": metric,
                    "hourly_total": round(hourly_total, 6),
                    "daily_total": round(daily_total, 6),
                    "pct_diff": round(pct_diff, 4),
                    "within_tolerance": within,
                    "tolerance_pct": float(tolerance_pct),
                    "computed_at": computed_at,
                },
            )
            reconciliation_rows += 1
            if within == 0:
                reconciliation_failures += 1

    conn.commit()
    return {
        "profile_rows": profile_rows,
        "daily_fact_rows": daily_fact_rows,
        "reconciliation_rows": reconciliation_rows,
        "reconciliation_failures": reconciliation_failures,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build hourly ads profile and reconcile against daily totals")
    parser.add_argument("--ads-db", type=Path, default=None, help="Ads DB path (or set KASPI_MARKETING_DB_PATH)")
    parser.add_argument("--since", default=None)
    parser.add_argument("--until", default=None)
    parser.add_argument("--tolerance-pct", type=float, default=5.0)
    parser.add_argument("--strict", action="store_true", help="Exit non-zero when reconciliation has failures")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    ads_db = resolve_ads_db_path(
        ads_db_arg=args.ads_db,
        default_path=DEFAULT_WORKTREE_ADS_DB_PATH,
    )
    assert_ads_db_path_safe(ads_db_path=ads_db)

    with sqlite3.connect(ads_db) as conn:
        summary = build_hourly_profile_and_reconciliation(
            conn,
            since=args.since,
            until=args.until,
            tolerance_pct=max(0.0, args.tolerance_pct),
        )

    print(json.dumps({"ads_db": str(ads_db), **summary}, ensure_ascii=False))
    if args.strict and summary["reconciliation_failures"] > 0:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
