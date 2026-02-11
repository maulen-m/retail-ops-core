#!/usr/bin/env python3
"""Offline Kaspi ads elasticity and profit/ROIC analysis."""

from __future__ import annotations

import argparse
import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pandas as pd

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

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_APP_DB = PROJECT_ROOT / "db" / "app.db"
DEFAULT_OUT_DIR = PROJECT_ROOT / "reports" / "marketing"


def _table_exists(conn: sqlite3.Connection, table: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=? LIMIT 1",
        (table,),
    ).fetchone()
    return row is not None


def _load_ads_rows(
    conn: sqlite3.Connection,
    *,
    since: str | None,
    until: str | None,
) -> pd.DataFrame:
    if not _table_exists(conn, "campaign_product_daily_current"):
        return pd.DataFrame()

    where = ["COALESCE(bid_cpc, 0) > 0"]
    params: list[Any] = []
    if since:
        where.append("date(date) >= date(?)")
        params.append(since)
    if until:
        where.append("date(date) <= date(?)")
        params.append(until)

    query = f"""
        SELECT
            date,
            merchant_id,
            campaign_id,
            sku_key,
            COALESCE(bid_cpc, 0) AS bid_cpc,
            COALESCE(clicks, 0) AS clicks,
            COALESCE(orders_total, 0) AS orders_total,
            COALESCE(gmv, 0) AS gmv,
            COALESCE(cost, 0) AS cost
        FROM campaign_product_daily_current
        WHERE {' AND '.join(where)}
    """
    return pd.read_sql_query(query, conn, params=params)


def _load_margin_map(
    app_db: Path,
    *,
    since: str | None,
    until: str | None,
) -> pd.DataFrame:
    if not app_db.exists():
        return pd.DataFrame(columns=["sku_key", "margin_pct", "sales_gmv", "profit_sum", "cogs_sum"])

    with sqlite3.connect(app_db) as conn:
        if not _table_exists(conn, "fact_sales"):
            return pd.DataFrame(columns=["sku_key", "margin_pct", "sales_gmv", "profit_sum", "cogs_sum"])

        where = ["1=1"]
        params: list[Any] = []
        if since:
            where.append("date(order_date) >= date(?)")
            params.append(since)
        if until:
            where.append("date(order_date) <= date(?)")
            params.append(until)

        df = pd.read_sql_query(
            f"""
            SELECT
                sku_key,
                SUM(COALESCE(sell_price_kzt, 0) * COALESCE(quantity, 0)) AS sales_gmv,
                SUM(COALESCE(profit_line, 0)) AS profit_sum,
                SUM(COALESCE(cogs_line, 0)) AS cogs_sum
            FROM fact_sales
            WHERE {' AND '.join(where)}
            GROUP BY sku_key
            """,
            conn,
            params=params,
        )

    if df.empty:
        return pd.DataFrame(columns=["sku_key", "margin_pct", "sales_gmv", "profit_sum", "cogs_sum"])

    df["margin_pct"] = 0.0
    non_zero = df["sales_gmv"] > 0
    df.loc[non_zero, "margin_pct"] = (df.loc[non_zero, "profit_sum"] / df.loc[non_zero, "sales_gmv"]).clip(-1.0, 1.0)
    return df[["sku_key", "margin_pct", "sales_gmv", "profit_sum", "cogs_sum"]]


def _build_level_frame(
    ads_df: pd.DataFrame,
    margin_df: pd.DataFrame,
    *,
    default_margin_pct: float,
) -> pd.DataFrame:
    if ads_df.empty:
        return pd.DataFrame()

    ads_df = ads_df.copy()
    grouped = (
        ads_df.groupby(["campaign_id", "sku_key", "bid_cpc"], as_index=False)
        .agg(
            days_observed=("date", "nunique"),
            clicks_total=("clicks", "sum"),
            orders_total=("orders_total", "sum"),
            gmv_total=("gmv", "sum"),
            cost_total=("cost", "sum"),
        )
        .sort_values(["campaign_id", "sku_key", "bid_cpc"])
        .reset_index(drop=True)
    )

    if margin_df.empty:
        grouped["margin_pct"] = float(default_margin_pct)
        grouped["margin_source"] = "default"
    else:
        merged = grouped.merge(
            margin_df[["sku_key", "margin_pct"]],
            on="sku_key",
            how="left",
        )
        merged["margin_source"] = merged["margin_pct"].apply(
            lambda x: "fact_sales" if pd.notna(x) else "default"
        )
        merged["margin_pct"] = merged["margin_pct"].fillna(float(default_margin_pct))
        grouped = merged

    grouped["margin_profit_kzt"] = grouped["gmv_total"] * grouped["margin_pct"]
    grouped["profit_est_kzt"] = grouped["margin_profit_kzt"] - grouped["cost_total"]
    grouped["db_roas"] = grouped.apply(
        lambda r: round(float(r["gmv_total"]) / float(r["cost_total"]), 6) if float(r["cost_total"]) > 0 else 0.0,
        axis=1,
    )
    grouped["ads_roic"] = grouped.apply(
        lambda r: round(float(r["profit_est_kzt"]) / float(r["cost_total"]), 6) if float(r["cost_total"]) > 0 else 0.0,
        axis=1,
    )
    grouped["cost_per_order"] = grouped.apply(
        lambda r: round(float(r["cost_total"]) / float(r["orders_total"]), 6) if float(r["orders_total"]) > 0 else 0.0,
        axis=1,
    )
    return grouped


def _pct_change(prev: float, curr: float) -> float:
    if abs(prev) < 1e-9:
        return 0.0 if abs(curr) < 1e-9 else 100.0
    return (curr - prev) / abs(prev) * 100.0


def _build_transition_frame(level_df: pd.DataFrame) -> pd.DataFrame:
    if level_df.empty:
        return pd.DataFrame()

    rows: list[dict[str, Any]] = []
    for (campaign_id, sku_key), grp in level_df.groupby(["campaign_id", "sku_key"]):
        grp = grp.sort_values("bid_cpc").reset_index(drop=True)
        for idx in range(1, len(grp)):
            prev = grp.iloc[idx - 1]
            curr = grp.iloc[idx]
            bid_pct = _pct_change(float(prev["bid_cpc"]), float(curr["bid_cpc"]))
            clicks_pct = _pct_change(float(prev["clicks_total"]), float(curr["clicks_total"]))
            orders_pct = _pct_change(float(prev["orders_total"]), float(curr["orders_total"]))
            rows.append(
                {
                    "campaign_id": campaign_id,
                    "sku_key": sku_key,
                    "from_bid_cpc": float(prev["bid_cpc"]),
                    "to_bid_cpc": float(curr["bid_cpc"]),
                    "bid_pct_change": round(bid_pct, 6),
                    "clicks_pct_change": round(clicks_pct, 6),
                    "orders_pct_change": round(orders_pct, 6),
                    "click_elasticity": round(clicks_pct / bid_pct, 6) if abs(bid_pct) > 1e-9 else 0.0,
                    "order_elasticity": round(orders_pct / bid_pct, 6) if abs(bid_pct) > 1e-9 else 0.0,
                    "delta_profit_est_kzt": round(float(curr["profit_est_kzt"]) - float(prev["profit_est_kzt"]), 6),
                    "delta_roic": round(float(curr["ads_roic"]) - float(prev["ads_roic"]), 6),
                }
            )
    return pd.DataFrame(rows)


def _build_recommendations(level_df: pd.DataFrame, *, min_days: int) -> pd.DataFrame:
    if level_df.empty:
        return pd.DataFrame()

    rows: list[dict[str, Any]] = []
    for (campaign_id, sku_key), grp in level_df.groupby(["campaign_id", "sku_key"]):
        eligible = grp[grp["days_observed"] >= int(min_days)]
        source = "eligible"
        if eligible.empty:
            eligible = grp
            source = "fallback_all_levels"
        chosen = eligible.sort_values(["profit_est_kzt", "ads_roic", "bid_cpc"], ascending=[False, False, True]).iloc[0]
        rows.append(
            {
                "campaign_id": campaign_id,
                "sku_key": sku_key,
                "recommended_bid_cpc": float(chosen["bid_cpc"]),
                "expected_profit_est_kzt": round(float(chosen["profit_est_kzt"]), 6),
                "expected_ads_roic": round(float(chosen["ads_roic"]), 6),
                "expected_db_roas": round(float(chosen["db_roas"]), 6),
                "days_observed": int(chosen["days_observed"]),
                "selection_source": source,
            }
        )
    return pd.DataFrame(rows)


def analyze_elasticity(
    *,
    ads_db: Path,
    app_db: Path,
    out_dir: Path,
    since: str | None,
    until: str | None,
    min_days: int,
    default_margin_pct: float,
) -> dict[str, Any]:
    with sqlite3.connect(ads_db) as conn:
        ads_df = _load_ads_rows(conn, since=since, until=until)

    margin_df = _load_margin_map(app_db, since=since, until=until)
    level_df = _build_level_frame(ads_df, margin_df, default_margin_pct=float(default_margin_pct))
    transition_df = _build_transition_frame(level_df)
    recommendation_df = _build_recommendations(level_df, min_days=max(1, int(min_days)))

    out_dir.mkdir(parents=True, exist_ok=True)
    level_path = out_dir / "kaspi_ads_elasticity_levels.csv"
    transition_path = out_dir / "kaspi_ads_elasticity_transitions.csv"
    recommendation_path = out_dir / "kaspi_ads_bid_recommendations.csv"
    summary_path = out_dir / "kaspi_ads_elasticity_summary.json"

    level_df.to_csv(level_path, index=False)
    transition_df.to_csv(transition_path, index=False)
    recommendation_df.to_csv(recommendation_path, index=False)

    summary = {
        "generated_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "ads_db": str(ads_db),
        "app_db": str(app_db),
        "since": since,
        "until": until,
        "level_rows": int(len(level_df)),
        "transition_rows": int(len(transition_df)),
        "recommendation_rows": int(len(recommendation_df)),
        "economics_rows": int(len(margin_df)),
        "outputs": {
            "levels_csv": str(level_path),
            "transitions_csv": str(transition_path),
            "recommendations_csv": str(recommendation_path),
        },
        "recommendations": recommendation_df.to_dict(orient="records"),
    }
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    return summary


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Offline Kaspi ads elasticity and profit/ROIC optimizer")
    parser.add_argument("--ads-db", type=Path, default=None, help="Ads DB path (or set KASPI_MARKETING_DB_PATH)")
    parser.add_argument("--app-db", type=Path, default=DEFAULT_APP_DB)
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR)
    parser.add_argument("--since", default=None)
    parser.add_argument("--until", default=None)
    parser.add_argument("--min-days", type=int, default=3)
    parser.add_argument("--default-margin-pct", type=float, default=0.25)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    ads_db = resolve_ads_db_path(ads_db_arg=args.ads_db, default_path=DEFAULT_WORKTREE_ADS_DB_PATH)
    assert_ads_db_path_safe(ads_db_path=ads_db)

    summary = analyze_elasticity(
        ads_db=ads_db,
        app_db=args.app_db,
        out_dir=args.out_dir,
        since=args.since,
        until=args.until,
        min_days=args.min_days,
        default_margin_pct=args.default_margin_pct,
    )
    print(json.dumps(summary, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
