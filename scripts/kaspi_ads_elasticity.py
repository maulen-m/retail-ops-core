#!/usr/bin/env python3
"""Offline Kaspi ads elasticity and profit/ROIC analysis."""

from __future__ import annotations

import argparse
import json
import re
import sqlite3
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

import pandas as pd
import yaml

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
DEFAULT_COST_ADJUSTMENTS_CONFIG = PROJECT_ROOT / "config" / "kaspi_ads_cost_adjustments.yaml"


def _table_exists(conn: sqlite3.Connection, table: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=? LIMIT 1",
        (table,),
    ).fetchone()
    return row is not None


def _parse_iso_date(value: Any, *, field_name: str) -> date | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    try:
        return datetime.strptime(text, "%Y-%m-%d").date()
    except ValueError as exc:
        raise ValueError(f"Invalid {field_name}: {text!r} (expected YYYY-MM-DD)") from exc


def _coerce_multiplier(value: Any, *, field_name: str) -> float:
    try:
        multiplier = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Invalid {field_name}: {value!r} (expected float > 0)") from exc
    if multiplier <= 0:
        raise ValueError(f"Invalid {field_name}: {multiplier!r} (must be > 0)")
    return multiplier


def _load_cost_adjustments_config(path: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    if not path.exists():
        raise FileNotFoundError(
            f"Missing cost adjustments config: {path}. "
            "Phase N2 requires an explicit policy file (no silent fallback)."
        )

    payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(payload, dict):
        raise ValueError(f"Invalid cost adjustments config format in {path}: expected mapping at root.")

    default_multiplier = _coerce_multiplier(
        payload.get("default_effective_cost_multiplier", 1.0),
        field_name="default_effective_cost_multiplier",
    )

    campaign_multipliers_raw = payload.get("campaign_multipliers") or {}
    if not isinstance(campaign_multipliers_raw, dict):
        raise ValueError("campaign_multipliers must be a mapping of campaign_id -> multiplier|object")

    campaign_multipliers: dict[str, dict[str, Any]] = {}
    campaign_meta: list[dict[str, Any]] = []
    for campaign_id_raw, cfg in campaign_multipliers_raw.items():
        campaign_id = str(campaign_id_raw).strip()
        if not campaign_id:
            continue
        if isinstance(cfg, dict):
            multiplier = _coerce_multiplier(cfg.get("multiplier", 1.0), field_name=f"campaign_multipliers[{campaign_id}].multiplier")
            reason = str(cfg.get("reason", "") or "").strip()
        else:
            multiplier = _coerce_multiplier(cfg, field_name=f"campaign_multipliers[{campaign_id}]")
            reason = ""
        campaign_multipliers[campaign_id] = {"multiplier": multiplier, "reason": reason}
        campaign_meta.append(
            {
                "campaign_id": campaign_id,
                "multiplier": multiplier,
                "reason": reason,
            }
        )

    rules_raw = payload.get("rules") or []
    if not isinstance(rules_raw, list):
        raise ValueError("rules must be a list of rule objects")

    rules: list[dict[str, Any]] = []
    rules_meta: list[dict[str, Any]] = []
    for idx, raw in enumerate(rules_raw, start=1):
        if not isinstance(raw, dict):
            raise ValueError(f"rules[{idx}] must be an object")
        rule_id = str(raw.get("id", f"RULE_{idx:03d}")).strip()
        if not rule_id:
            raise ValueError(f"rules[{idx}] has empty id")
        enabled = bool(raw.get("enabled", True))
        priority = int(raw.get("priority", 0))
        multiplier = _coerce_multiplier(raw.get("multiplier", 1.0), field_name=f"rules[{rule_id}].multiplier")
        reason = str(raw.get("reason", "") or "").strip()
        start_date = _parse_iso_date(raw.get("start_date"), field_name=f"rules[{rule_id}].start_date")
        end_date = _parse_iso_date(raw.get("end_date"), field_name=f"rules[{rule_id}].end_date")
        if start_date and end_date and end_date < start_date:
            raise ValueError(f"rules[{rule_id}] has end_date before start_date")

        match = raw.get("match") or {}
        if not isinstance(match, dict):
            raise ValueError(f"rules[{rule_id}].match must be an object")
        campaign_ids = {str(v).strip() for v in (match.get("campaign_ids") or []) if str(v).strip()}
        sku_keys = {str(v).strip() for v in (match.get("sku_keys") or []) if str(v).strip()}
        sku_key_regex = str(match.get("sku_key_regex", "") or "").strip()
        sku_pattern = re.compile(sku_key_regex) if sku_key_regex else None

        rule = {
            "id": rule_id,
            "enabled": enabled,
            "priority": priority,
            "multiplier": multiplier,
            "reason": reason,
            "start_date": start_date,
            "end_date": end_date,
            "campaign_ids": campaign_ids,
            "sku_keys": sku_keys,
            "sku_key_regex": sku_key_regex,
            "sku_pattern": sku_pattern,
        }
        rules.append(rule)
        rules_meta.append(
            {
                "id": rule_id,
                "enabled": enabled,
                "priority": priority,
                "multiplier": multiplier,
                "reason": reason,
                "start_date": start_date.isoformat() if start_date else "",
                "end_date": end_date.isoformat() if end_date else "",
                "match": {
                    "campaign_ids": sorted(campaign_ids),
                    "sku_keys": sorted(sku_keys),
                    "sku_key_regex": sku_key_regex,
                },
            }
        )

    rules.sort(key=lambda r: (-int(r["priority"]), str(r["id"])))
    return (
        {
            "config_path": str(path),
            "default_multiplier": default_multiplier,
            "campaign_multipliers": campaign_multipliers,
            "rules": rules,
        },
        {
            "config_path": str(path),
            "default_effective_cost_multiplier": default_multiplier,
            "campaign_multipliers": campaign_meta,
            "rules_defined": rules_meta,
        },
    )


def _row_matches_rule(
    *,
    row_date: date,
    campaign_id: str,
    sku_key: str,
    rule: dict[str, Any],
) -> bool:
    if not bool(rule.get("enabled", True)):
        return False
    start_date = rule.get("start_date")
    end_date = rule.get("end_date")
    if start_date and row_date < start_date:
        return False
    if end_date and row_date > end_date:
        return False
    campaign_ids = rule.get("campaign_ids") or set()
    if campaign_ids and campaign_id not in campaign_ids:
        return False
    sku_keys = rule.get("sku_keys") or set()
    if sku_keys and sku_key not in sku_keys:
        return False
    pattern = rule.get("sku_pattern")
    if pattern and not bool(pattern.search(sku_key)):
        return False
    return True


def _apply_effective_cost_policy(
    ads_df: pd.DataFrame,
    *,
    policy: dict[str, Any],
    policy_meta: dict[str, Any],
) -> tuple[pd.DataFrame, dict[str, Any]]:
    if ads_df.empty:
        empty_report = {
            **policy_meta,
            "rows_total": 0,
            "rows_with_campaign_multiplier": 0,
            "rows_with_discount_rule": 0,
            "rows_with_any_adjustment": 0,
            "rows_without_adjustment": 0,
            "applied_rule_counts": {},
        }
        return ads_df.copy(), empty_report

    working = ads_df.copy()
    parsed_dates = pd.to_datetime(working["date"], errors="coerce").dt.date
    if parsed_dates.isna().any():
        bad_dates = sorted({str(v) for v in working.loc[parsed_dates.isna(), "date"].tolist()})
        raise ValueError(f"Invalid date values in ads data: {bad_dates}")

    campaign_multiplier_col: list[float] = []
    campaign_reason_col: list[str] = []
    discount_multiplier_col: list[float] = []
    discount_rule_id_col: list[str] = []
    discount_rule_reason_col: list[str] = []
    effective_multiplier_col: list[float] = []

    rows_with_campaign_multiplier = 0
    rows_with_discount_rule = 0
    applied_rule_counts: dict[str, int] = {}

    campaign_cfg = policy.get("campaign_multipliers", {})
    rules = policy.get("rules", [])
    default_multiplier = float(policy.get("default_multiplier", 1.0))

    for idx, row in working.iterrows():
        row_date = parsed_dates.iloc[idx]
        campaign_id = str(row.get("campaign_id", "")).strip()
        sku_key = str(row.get("sku_key", "")).strip()

        campaign_entry = campaign_cfg.get(campaign_id)
        if campaign_entry:
            campaign_multiplier = _coerce_multiplier(
                campaign_entry.get("multiplier", 1.0),
                field_name=f"campaign_multipliers[{campaign_id}]",
            )
            campaign_reason = str(campaign_entry.get("reason", "") or "").strip()
            rows_with_campaign_multiplier += 1
        else:
            campaign_multiplier = 1.0
            campaign_reason = ""

        matched_rule: dict[str, Any] | None = None
        for rule in rules:
            if _row_matches_rule(
                row_date=row_date,
                campaign_id=campaign_id,
                sku_key=sku_key,
                rule=rule,
            ):
                matched_rule = rule
                break

        if matched_rule is not None:
            discount_multiplier = _coerce_multiplier(
                matched_rule.get("multiplier", default_multiplier),
                field_name=f"rules[{matched_rule.get('id', 'UNKNOWN')}].multiplier",
            )
            discount_rule_id = str(matched_rule.get("id", "UNKNOWN"))
            discount_rule_reason = str(matched_rule.get("reason", "") or "").strip()
            rows_with_discount_rule += 1
            applied_rule_counts[discount_rule_id] = applied_rule_counts.get(discount_rule_id, 0) + 1
        else:
            discount_multiplier = default_multiplier
            discount_rule_id = "NONE"
            discount_rule_reason = ""

        effective_multiplier = campaign_multiplier * discount_multiplier
        campaign_multiplier_col.append(campaign_multiplier)
        campaign_reason_col.append(campaign_reason)
        discount_multiplier_col.append(discount_multiplier)
        discount_rule_id_col.append(discount_rule_id)
        discount_rule_reason_col.append(discount_rule_reason)
        effective_multiplier_col.append(effective_multiplier)

    working["campaign_cost_multiplier"] = campaign_multiplier_col
    working["campaign_cost_reason"] = campaign_reason_col
    working["discount_cost_multiplier"] = discount_multiplier_col
    working["discount_rule_id"] = discount_rule_id_col
    working["discount_rule_reason"] = discount_rule_reason_col
    working["effective_cost_multiplier"] = effective_multiplier_col
    working["effective_cost"] = working["cost"] * working["effective_cost_multiplier"]
    working["effective_cost_adjusted"] = (
        (working["campaign_cost_multiplier"] - 1.0).abs() > 1e-9
    ) | ((working["discount_cost_multiplier"] - 1.0).abs() > 1e-9)

    rows_with_any_adjustment = int(working["effective_cost_adjusted"].sum())
    report = {
        **policy_meta,
        "rows_total": int(len(working)),
        "rows_with_campaign_multiplier": int(rows_with_campaign_multiplier),
        "rows_with_discount_rule": int(rows_with_discount_rule),
        "rows_with_any_adjustment": rows_with_any_adjustment,
        "rows_without_adjustment": int(len(working) - rows_with_any_adjustment),
        "applied_rule_counts": {k: int(v) for k, v in sorted(applied_rule_counts.items())},
    }
    return working, report


def _load_ads_rows(
    conn: sqlite3.Connection,
    *,
    since: str | None,
    until: str | None,
    campaign_ids: list[str] | None,
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
    if campaign_ids:
        unique_ids = sorted({str(cid).strip() for cid in campaign_ids if str(cid).strip()})
        if unique_ids:
            placeholders = ",".join("?" for _ in unique_ids)
            where.append(f"campaign_id IN ({placeholders})")
            params.extend(unique_ids)

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
            effective_cost_total=("effective_cost", "sum"),
            adjusted_rows=("effective_cost_adjusted", "sum"),
            campaign_cost_multiplier_avg=("campaign_cost_multiplier", "mean"),
            discount_cost_multiplier_avg=("discount_cost_multiplier", "mean"),
        )
        .sort_values(["campaign_id", "sku_key", "bid_cpc"])
        .reset_index(drop=True)
    )
    grouped["raw_cost_total"] = grouped["cost_total"]

    rule_trace = (
        ads_df.groupby(["campaign_id", "sku_key", "bid_cpc"], as_index=False)["discount_rule_id"]
        .apply(lambda s: "|".join(sorted({str(v) for v in s if str(v).strip() and str(v) != "NONE"}) or ["NONE"]))
        .rename(columns={"discount_rule_id": "effective_cost_rule_ids"})
    )
    campaign_reason_trace = (
        ads_df.groupby(["campaign_id", "sku_key", "bid_cpc"], as_index=False)["campaign_cost_reason"]
        .apply(lambda s: "|".join(sorted({str(v).strip() for v in s if str(v).strip()}) or ["NONE"]))
        .rename(columns={"campaign_cost_reason": "campaign_cost_reasons"})
    )
    grouped = grouped.merge(rule_trace, on=["campaign_id", "sku_key", "bid_cpc"], how="left")
    grouped = grouped.merge(campaign_reason_trace, on=["campaign_id", "sku_key", "bid_cpc"], how="left")

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
    grouped["effective_profit_est_kzt"] = grouped["margin_profit_kzt"] - grouped["effective_cost_total"]
    grouped["effective_cost_delta_kzt"] = grouped["cost_total"] - grouped["effective_cost_total"]
    grouped["db_roas"] = grouped.apply(
        lambda r: round(float(r["gmv_total"]) / float(r["cost_total"]), 6) if float(r["cost_total"]) > 0 else 0.0,
        axis=1,
    )
    grouped["ads_roic"] = grouped.apply(
        lambda r: round(float(r["profit_est_kzt"]) / float(r["cost_total"]), 6) if float(r["cost_total"]) > 0 else 0.0,
        axis=1,
    )
    grouped["effective_db_roas"] = grouped.apply(
        lambda r: round(float(r["gmv_total"]) / float(r["effective_cost_total"]), 6)
        if float(r["effective_cost_total"]) > 0
        else 0.0,
        axis=1,
    )
    grouped["effective_ads_roic"] = grouped.apply(
        lambda r: round(float(r["effective_profit_est_kzt"]) / float(r["effective_cost_total"]), 6)
        if float(r["effective_cost_total"]) > 0
        else 0.0,
        axis=1,
    )
    grouped["cost_per_order"] = grouped.apply(
        lambda r: round(float(r["cost_total"]) / float(r["orders_total"]), 6) if float(r["orders_total"]) > 0 else 0.0,
        axis=1,
    )
    grouped["effective_cost_per_order"] = grouped.apply(
        lambda r: round(float(r["effective_cost_total"]) / float(r["orders_total"]), 6)
        if float(r["orders_total"]) > 0
        else 0.0,
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
                    "delta_effective_profit_est_kzt": round(
                        float(curr["effective_profit_est_kzt"]) - float(prev["effective_profit_est_kzt"]),
                        6,
                    ),
                    "delta_effective_roic": round(
                        float(curr["effective_ads_roic"]) - float(prev["effective_ads_roic"]),
                        6,
                    ),
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
        chosen = eligible.sort_values(
            ["effective_profit_est_kzt", "effective_ads_roic", "bid_cpc"],
            ascending=[False, False, True],
        ).iloc[0]
        rows.append(
            {
                "campaign_id": campaign_id,
                "sku_key": sku_key,
                "recommended_bid_cpc": float(chosen["bid_cpc"]),
                "expected_profit_est_kzt": round(float(chosen["profit_est_kzt"]), 6),
                "expected_ads_roic": round(float(chosen["ads_roic"]), 6),
                "expected_effective_profit_est_kzt": round(float(chosen["effective_profit_est_kzt"]), 6),
                "expected_effective_ads_roic": round(float(chosen["effective_ads_roic"]), 6),
                "expected_db_roas": round(float(chosen["db_roas"]), 6),
                "expected_effective_db_roas": round(float(chosen["effective_db_roas"]), 6),
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
    campaign_ids: list[str] | None = None,
    cost_adjustments_config: Path | None = None,
) -> dict[str, Any]:
    if cost_adjustments_config is None:
        cost_adjustments_config = DEFAULT_COST_ADJUSTMENTS_CONFIG

    with sqlite3.connect(ads_db) as conn:
        ads_df = _load_ads_rows(conn, since=since, until=until, campaign_ids=campaign_ids)

    cost_policy, cost_policy_meta = _load_cost_adjustments_config(Path(cost_adjustments_config))
    ads_df, cost_adjustment_report = _apply_effective_cost_policy(
        ads_df,
        policy=cost_policy,
        policy_meta=cost_policy_meta,
    )

    margin_df = _load_margin_map(app_db, since=since, until=until)
    level_df = _build_level_frame(ads_df, margin_df, default_margin_pct=float(default_margin_pct))
    transition_df = _build_transition_frame(level_df)
    recommendation_df = _build_recommendations(level_df, min_days=max(1, int(min_days)))

    out_dir.mkdir(parents=True, exist_ok=True)
    level_path = out_dir / "kaspi_ads_elasticity_levels.csv"
    transition_path = out_dir / "kaspi_ads_elasticity_transitions.csv"
    recommendation_path = out_dir / "kaspi_ads_bid_recommendations.csv"
    adjustment_audit_path = out_dir / "kaspi_ads_cost_adjustments_audit.csv"
    summary_path = out_dir / "kaspi_ads_elasticity_summary.json"

    level_df.to_csv(level_path, index=False)
    transition_df.to_csv(transition_path, index=False)
    recommendation_df.to_csv(recommendation_path, index=False)
    ads_df.to_csv(adjustment_audit_path, index=False)

    total_raw_cost = float(level_df["cost_total"].sum()) if not level_df.empty else 0.0
    total_effective_cost = float(level_df["effective_cost_total"].sum()) if not level_df.empty else 0.0
    total_raw_profit = float(level_df["profit_est_kzt"].sum()) if not level_df.empty else 0.0
    total_effective_profit = float(level_df["effective_profit_est_kzt"].sum()) if not level_df.empty else 0.0

    summary = {
        "generated_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "ads_db": str(ads_db),
        "app_db": str(app_db),
        "since": since,
        "until": until,
        "campaign_ids": sorted({str(cid).strip() for cid in (campaign_ids or []) if str(cid).strip()}),
        "level_rows": int(len(level_df)),
        "transition_rows": int(len(transition_df)),
        "recommendation_rows": int(len(recommendation_df)),
        "economics_rows": int(len(margin_df)),
        "outputs": {
            "levels_csv": str(level_path),
            "transitions_csv": str(transition_path),
            "recommendations_csv": str(recommendation_path),
            "cost_adjustments_audit_csv": str(adjustment_audit_path),
        },
        "totals": {
            "raw_cost_kzt": round(total_raw_cost, 6),
            "effective_cost_kzt": round(total_effective_cost, 6),
            "raw_profit_est_kzt": round(total_raw_profit, 6),
            "effective_profit_est_kzt": round(total_effective_profit, 6),
            "raw_ads_roic": round(total_raw_profit / total_raw_cost, 6) if total_raw_cost > 0 else 0.0,
            "effective_ads_roic": round(total_effective_profit / total_effective_cost, 6)
            if total_effective_cost > 0
            else 0.0,
        },
        "cost_adjustments_report": cost_adjustment_report,
        "recommendations": recommendation_df.to_dict(orient="records"),
    }
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    return summary


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Offline Kaspi ads elasticity and profit/ROIC optimizer")
    parser.add_argument("--ads-db", type=Path, default=None, help="Ads DB path (or set KASPI_MARKETING_DB_PATH)")
    parser.add_argument("--app-db", type=Path, default=DEFAULT_APP_DB)
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR)
    parser.add_argument(
        "--cost-adjustments-config",
        type=Path,
        default=DEFAULT_COST_ADJUSTMENTS_CONFIG,
        help="YAML policy for effective-cost adjustments (required for N2 transparency).",
    )
    parser.add_argument("--since", default=None)
    parser.add_argument("--until", default=None)
    parser.add_argument(
        "--campaign-ids",
        default=None,
        help="Comma-separated campaign IDs filter (e.g. 2545773,2488450).",
    )
    parser.add_argument("--min-days", type=int, default=3)
    parser.add_argument("--default-margin-pct", type=float, default=0.25)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    ads_db = resolve_ads_db_path(ads_db_arg=args.ads_db, default_path=DEFAULT_WORKTREE_ADS_DB_PATH)
    assert_ads_db_path_safe(ads_db_path=ads_db)

    campaign_ids = None
    if args.campaign_ids:
        campaign_ids = [part.strip() for part in str(args.campaign_ids).split(",") if part.strip()]

    summary = analyze_elasticity(
        ads_db=ads_db,
        app_db=args.app_db,
        out_dir=args.out_dir,
        since=args.since,
        until=args.until,
        min_days=args.min_days,
        default_margin_pct=args.default_margin_pct,
        campaign_ids=campaign_ids,
        cost_adjustments_config=args.cost_adjustments_config,
    )
    print(json.dumps(summary, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
