#!/usr/bin/env python3
"""
Generate single-truth business insides snapshot from paid capital + delivered sales.
"""

from __future__ import annotations

import argparse
from datetime import date, datetime, timedelta
import json
import os
from pathlib import Path
import sqlite3
import sys
from typing import Any

import pandas as pd
import yaml

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from core.cashflow.paid_capital_truth import compute_paid_capital_truth
from core.ads.sidecar_contract import resolve_ads_db_path, validate_ads_source
from core.db.sales_truth_query_guard import (
    install_sales_truth_query_guard,
    remove_sales_truth_query_guard,
)
from core.sales import ensure_sales_truth_views

DEFAULT_DB = PROJECT_ROOT / "db" / "app.db"
DEFAULT_BANK = PROJECT_ROOT / "config" / "bank_accounts.yaml"
DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "config" / "business_insides"
DEFAULT_WAYBILL_SELECTION_CACHE = (
    PROJECT_ROOT / "excel_ui" / "ActiveOrders" / "waybills" / "_waybill_selection_orders.json"
)


def _parse_as_of(value: str | date | None) -> date:
    if isinstance(value, date):
        return value
    if not value:
        return date.today()
    return date.fromisoformat(str(value))


def _fmt_kzt(value: float | None) -> str:
    if value is None:
        return "N/A"
    return f"{float(value):,.2f}"


def _ascii_table(headers: list[str], rows: list[list[str]]) -> str:
    widths = [len(h) for h in headers]
    for row in rows:
        for idx, cell in enumerate(row):
            widths[idx] = max(widths[idx], len(cell))

    def _fmt_row(row: list[str]) -> str:
        return "| " + " | ".join(cell.ljust(widths[i]) for i, cell in enumerate(row)) + " |"

    sep = "+-" + "-+-".join("-" * w for w in widths) + "-+"
    out = [sep, _fmt_row(headers), sep]
    out.extend(_fmt_row(r) for r in rows)
    out.append(sep)
    return "\n".join(out)


def _table_exists(conn: sqlite3.Connection, name: str) -> bool:
    row = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
        (name,),
    ).fetchone()
    return row is not None


def _column_exists(conn: sqlite3.Connection, table: str, column: str) -> bool:
    rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    return any(str(row[1]) == column for row in rows)


def load_waybill_selection_snapshot(
    *,
    db_path: Path,
    as_of_date: date,
    selection_cache_path: Path = DEFAULT_WAYBILL_SELECTION_CACHE,
) -> dict[str, Any]:
    target_as_of = as_of_date.isoformat()
    snapshot: dict[str, Any] = {
        "status": "missing",
        "reason": "selection_cache_missing",
        "as_of": target_as_of,
        "target_date": None,
        "cache_path": str(selection_cache_path),
        "include_overdue": None,
        "all_dates": None,
        "stores": {},
        "totals": {"orders": 0, "units": 0},
    }

    if not selection_cache_path.exists():
        return snapshot

    try:
        payload = json.loads(selection_cache_path.read_text(encoding="utf-8"))
    except Exception as exc:  # pragma: no cover - defensive
        snapshot["status"] = "invalid"
        snapshot["reason"] = f"invalid_json:{exc}"
        return snapshot

    if not isinstance(payload, dict):
        snapshot["status"] = "invalid"
        snapshot["reason"] = "invalid_payload_type"
        return snapshot

    target_date = str(payload.get("target_date") or "").strip()
    snapshot["target_date"] = target_date or None
    snapshot["include_overdue"] = bool(payload.get("include_overdue"))
    snapshot["all_dates"] = bool(payload.get("all_dates"))

    stores_raw = payload.get("stores") or {}
    if not isinstance(stores_raw, dict):
        snapshot["status"] = "invalid"
        snapshot["reason"] = "stores_payload_not_dict"
        return snapshot

    order_ids_all: set[str] = set()
    stores_orders: dict[str, set[str]] = {}
    for store_code, raw_ids in stores_raw.items():
        if not isinstance(raw_ids, list):
            continue
        cleaned_ids = {
            str(order_id).strip()
            for order_id in raw_ids
            if str(order_id).strip()
        }
        if cleaned_ids:
            stores_orders[str(store_code).strip().upper()] = cleaned_ids
            order_ids_all.update(cleaned_ids)

    if not stores_orders:
        snapshot["status"] = "invalid"
        snapshot["reason"] = "no_order_ids"
        return snapshot

    quantity_by_order: dict[str, float] = {}
    if db_path.exists() and order_ids_all:
        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row
        try:
            if _table_exists(conn, "fact_orders_kaspi"):
                has_order_id = _column_exists(conn, "fact_orders_kaspi", "order_id")
                has_quantity = _column_exists(conn, "fact_orders_kaspi", "quantity")
                if has_order_id and has_quantity:
                    order_list = sorted(order_ids_all)
                    chunk_size = 500
                    for idx in range(0, len(order_list), chunk_size):
                        chunk = order_list[idx : idx + chunk_size]
                        placeholders = ",".join(["?"] * len(chunk))
                        rows = conn.execute(
                            f"""
                            SELECT
                                CAST(order_id AS TEXT) AS order_id,
                                MAX(CASE
                                    WHEN CAST(COALESCE(quantity, 1) AS REAL) > 0
                                        THEN CAST(quantity AS REAL)
                                    ELSE 1
                                END) AS qty
                            FROM fact_orders_kaspi
                            WHERE CAST(order_id AS TEXT) IN ({placeholders})
                            GROUP BY CAST(order_id AS TEXT)
                            """,
                            chunk,
                        ).fetchall()
                        for row in rows:
                            order_id = str(row["order_id"] or "").strip()
                            if not order_id:
                                continue
                            quantity_by_order[order_id] = float(row["qty"] or 1.0)
        finally:
            conn.close()

    stores_out: dict[str, dict[str, float | int]] = {}
    total_orders = 0
    total_units = 0.0
    for store_code in sorted(stores_orders.keys()):
        ids = stores_orders[store_code]
        order_count = len(ids)
        units = sum(float(quantity_by_order.get(order_id, 1.0)) for order_id in ids)
        stores_out[store_code] = {
            "orders": int(order_count),
            "units": round(float(units), 2),
        }
        total_orders += order_count
        total_units += units

    snapshot["stores"] = stores_out
    snapshot["totals"] = {
        "orders": int(total_orders),
        "units": round(float(total_units), 2),
    }

    if target_date and target_date != target_as_of:
        snapshot["status"] = "as_of_mismatch"
        snapshot["reason"] = f"target_date={target_date} expected={target_as_of}"
    else:
        snapshot["status"] = "available"
        snapshot["reason"] = "ok"

    return snapshot


def _load_ads_daily(
    db_path: Path,
    start_date: date,
    end_date: date,
) -> tuple[dict[str, float], dict[str, float]]:
    ads_source_path = resolve_ads_db_path(require_exists=False)
    ads_max_age_hours = float(os.environ.get("AB_ADS_DB_MAX_AGE_HOURS", "36"))
    ads_source_status = validate_ads_source(ads_source_path, max_age_hours=ads_max_age_hours)
    if not ads_source_status.get("ok", False):
        return {}, {
            "status": "unavailable",
            "reason": str(ads_source_status.get("reason") or "unknown"),
            "source_path": str(ads_source_status.get("path") or ads_source_path),
            "mapped_rows": None,
            "unmapped_rows": None,
            "mapped_cost_kzt": None,
            "unmapped_cost_kzt": None,
            "total_cost_kzt": None,
            "mapping_coverage_pct": None,
        }

    effective_cost_mode = os.environ.get("AB_ADS_EFFECTIVE_COST_MODE", "").strip().lower() in {
        "1",
        "true",
        "yes",
        "y",
    }
    effective_policy_path = Path(
        os.environ.get(
            "AB_ADS_EFFECTIVE_COST_POLICY_PATH",
            str(PROJECT_ROOT / "config" / "kaspi_ads_cost_adjustments.yaml"),
        )
    ).expanduser()

    policy: dict[str, Any] | None = None
    default_multiplier = 1.0
    date_overrides: list[dict[str, Any]] = []
    if effective_cost_mode:
        if not effective_policy_path.exists():
            return {}, {
                "status": "unavailable",
                "reason": "policy_missing",
                "source_path": str(ads_source_path),
                "policy_path": str(effective_policy_path),
                "mapped_rows": None,
                "unmapped_rows": None,
                "mapped_cost_kzt": None,
                "unmapped_cost_kzt": None,
                "total_cost_kzt": None,
                "mapping_coverage_pct": None,
            }
        try:
            policy = yaml.safe_load(effective_policy_path.read_text(encoding="utf-8")) or {}
        except Exception:
            return {}, {
                "status": "unavailable",
                "reason": "policy_parse_error",
                "source_path": str(ads_source_path),
                "policy_path": str(effective_policy_path),
                "mapped_rows": None,
                "unmapped_rows": None,
                "mapped_cost_kzt": None,
                "unmapped_cost_kzt": None,
                "total_cost_kzt": None,
                "mapping_coverage_pct": None,
            }
        default_multiplier = float(policy.get("default_multiplier", 1.0) or 1.0)
        date_overrides = list(policy.get("date_overrides") or [])

    def _multiplier_for_day(day_iso: str) -> float:
        if not effective_cost_mode:
            return 1.0
        multiplier = default_multiplier
        for row in date_overrides:
            start = str(row.get("start_date") or "").strip()
            end = str(row.get("end_date") or "").strip()
            if start and day_iso < start:
                continue
            if end and day_iso > end:
                continue
            candidate = float(row.get("multiplier", multiplier) or multiplier)
            multiplier = candidate
        return multiplier

    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    try:
        if not _table_exists(conn, "ads_spend_sidecar_daily"):
            return {}, {
                "status": "unavailable",
                "reason": "sidecar_table_missing",
                "source_path": str(ads_source_path),
                "mapped_rows": None,
                "unmapped_rows": None,
                "mapped_cost_kzt": None,
                "unmapped_cost_kzt": None,
                "total_cost_kzt": None,
                "mapping_coverage_pct": None,
            }
        rows = conn.execute(
            """
            SELECT
                date,
                SUM(COALESCE(total_cost_kzt, 0)) AS total_cost_kzt,
                SUM(COALESCE(mapped_rows, 0)) AS mapped_rows,
                SUM(COALESCE(unmapped_rows, 0)) AS unmapped_rows,
                SUM(COALESCE(mapped_cost_kzt, 0)) AS mapped_cost_kzt,
                SUM(COALESCE(unmapped_cost_kzt, 0)) AS unmapped_cost_kzt
            FROM ads_spend_sidecar_daily
            WHERE date(date) BETWEEN ? AND ?
            GROUP BY date
            """,
            (start_date.isoformat(), end_date.isoformat()),
        ).fetchall()
    finally:
        conn.close()

    by_date: dict[str, float] = {}
    totals = {
        "status": "available",
        "reason": "effective_cost_policy" if effective_cost_mode else "ok",
        "source_path": str(ads_source_path),
        "policy_path": str(effective_policy_path) if effective_cost_mode else None,
        "effective_cost_mode": bool(effective_cost_mode),
        "default_multiplier": float(default_multiplier) if effective_cost_mode else 1.0,
        "mapped_rows": 0.0,
        "unmapped_rows": 0.0,
        "mapped_cost_kzt": 0.0,
        "unmapped_cost_kzt": 0.0,
        "total_cost_kzt": 0.0,
        "mapping_coverage_pct": 0.0,
    }
    for row in rows:
        d = str(row["date"])
        multiplier = _multiplier_for_day(d)
        cost = float(row["total_cost_kzt"] or 0.0) * multiplier
        mapped_cost = float(row["mapped_cost_kzt"] or 0.0) * multiplier
        unmapped_cost = float(row["unmapped_cost_kzt"] or 0.0) * multiplier
        by_date[d] = round(cost, 2)
        totals["mapped_rows"] += float(row["mapped_rows"] or 0.0)
        totals["unmapped_rows"] += float(row["unmapped_rows"] or 0.0)
        totals["mapped_cost_kzt"] += mapped_cost
        totals["unmapped_cost_kzt"] += unmapped_cost
        totals["total_cost_kzt"] += cost
    total_rows = totals["mapped_rows"] + totals["unmapped_rows"]
    totals["mapping_coverage_pct"] = (
        round((totals["mapped_rows"] / total_rows) * 100.0, 2) if total_rows else 0.0
    )
    for key in ("mapped_cost_kzt", "unmapped_cost_kzt", "total_cost_kzt"):
        totals[key] = round(totals[key], 2)
    return by_date, totals


def compute_sales_metrics(
    *,
    db_path: Path = DEFAULT_DB,
    as_of: str | date | None = None,
    last_7_days: int = 7,
    last_30_days: int = 30,
    enforce_query_guard: bool = False,
    waybill_selection_cache_path: Path = DEFAULT_WAYBILL_SELECTION_CACHE,
) -> dict[str, Any]:
    as_of_date = _parse_as_of(as_of)
    start_30 = as_of_date - timedelta(days=max(1, int(last_30_days)) - 1)
    start_7 = as_of_date - timedelta(days=max(1, int(last_7_days)) - 1)

    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    guard_installed = False
    fallback_completed_daily_rows: list[sqlite3.Row] = []
    try:
        ensure_sales_truth_views(conn)
        if enforce_query_guard:
            install_sales_truth_query_guard(conn)
            guard_installed = True
        line_rows = conn.execute(
            """
            SELECT sale_date, sku_key, cogs_source
            FROM view_sales_line_truth
            WHERE date(sale_date) BETWEEN ? AND ?
            """,
            (start_30.isoformat(), as_of_date.isoformat()),
        ).fetchall()
        daily_rows = conn.execute(
            """
            SELECT
                sale_date,
                SUM(COALESCE(units, 0)) AS units_shipped,
                SUM(COALESCE(revenue_kzt, 0)) AS net_rev_kzt,
                SUM(COALESCE(cogs_kzt, 0)) AS cogs_kzt,
                SUM(COALESCE(profit_kzt, 0)) AS profit_kzt
            FROM view_sales_daily_truth
            WHERE date(sale_date) BETWEEN ? AND ?
            GROUP BY sale_date
            ORDER BY sale_date
            """,
            (start_30.isoformat(), as_of_date.isoformat()),
        ).fetchall()

        if _table_exists(conn, "fact_orders_kaspi") and _column_exists(
            conn, "fact_orders_kaspi", "internal_status"
        ):
            sale_date_candidates = [
                candidate
                for candidate in (
                    "status_updated_at",
                    "planned_shipment_date",
                    "courier_transmission_date",
                    "actual_shipment_date",
                    "planned_delivery_date",
                    "updated_at",
                    "created_at",
                )
                if _column_exists(conn, "fact_orders_kaspi", candidate)
            ]
            if sale_date_candidates:
                sale_ts_expr = "COALESCE(" + ", ".join(
                    f"NULLIF(TRIM(CAST({candidate} AS TEXT)), '')"
                    for candidate in sale_date_candidates
                ) + ")"
                sale_date_expr = f"date({sale_ts_expr})"
                qty_expr = (
                    "COALESCE(quantity, 1)"
                    if _column_exists(conn, "fact_orders_kaspi", "quantity")
                    else "1"
                )
                unit_price_expr = (
                    "COALESCE(unit_price_kzt, 0)"
                    if _column_exists(conn, "fact_orders_kaspi", "unit_price_kzt")
                    else "0"
                )
                returned_expr = (
                    "COALESCE(returned_to_warehouse, 0)"
                    if _column_exists(conn, "fact_orders_kaspi", "returned_to_warehouse")
                    else "0"
                )
                fallback_completed_daily_rows = conn.execute(
                    f"""
                    SELECT
                        {sale_date_expr} AS sale_date,
                        SUM({qty_expr}) AS units_shipped,
                        SUM(({unit_price_expr}) * ({qty_expr})) AS net_rev_kzt
                    FROM fact_orders_kaspi
                    WHERE UPPER(COALESCE(internal_status, '')) = 'COMPLETED'
                      AND {returned_expr} = 0
                      AND {sale_date_expr} BETWEEN ? AND ?
                    GROUP BY {sale_date_expr}
                    ORDER BY {sale_date_expr}
                    """,
                    (start_30.isoformat(), as_of_date.isoformat()),
                ).fetchall()
    finally:
        if guard_installed:
            remove_sales_truth_query_guard(conn)
        conn.close()

    by_date: dict[str, dict[str, float]] = {}
    fallback_rows = 0
    unresolved_rows = 0
    unresolved_skus: set[str] = set()
    total_rows = 0

    for row in line_rows:
        total_rows += 1
        sku_key = str(row["sku_key"] or "").strip()
        cogs_source = str(row["cogs_source"] or "")
        if cogs_source in {"fact_sales_fallback", "dim_sku_fallback"}:
            fallback_rows += 1
        elif cogs_source == "unresolved":
            unresolved_rows += 1
            if sku_key:
                unresolved_skus.add(sku_key)

    for row in daily_rows:
        day = str(row["sale_date"])
        units_delivered = round(float(row["units_shipped"] or 0.0), 2)
        by_date[day] = {
            "units_delivered": units_delivered,
            # Backward-compatible alias used by legacy consumers/tests.
            "units_shipped": units_delivered,
            "net_rev_kzt": round(float(row["net_rev_kzt"] or 0.0), 2),
            "cogs_kzt": round(float(row["cogs_kzt"] or 0.0), 2),
            "profit_kzt": round(float(row["profit_kzt"] or 0.0), 2),
        }

    fallback_revenue_days = 0
    for row in fallback_completed_daily_rows:
        day = str(row["sale_date"] or "").strip()
        if not day or day in by_date:
            continue
        units_delivered = round(float(row["units_shipped"] or 0.0), 2)
        by_date[day] = {
            "units_delivered": units_delivered,
            # Backward-compatible alias used by legacy consumers/tests.
            "units_shipped": units_delivered,
            "net_rev_kzt": round(float(row["net_rev_kzt"] or 0.0), 2),
            "cogs_kzt": None,
            "profit_kzt": None,
        }
        fallback_revenue_days += 1

    ads_by_date, ads_totals = _load_ads_daily(db_path, start_30, as_of_date)
    ads_available = ads_totals.get("status") == "available"
    for day, day_row in by_date.items():
        if ads_available:
            ads_cost = float(ads_by_date.get(day, 0.0))
            day_row["ads_spend_kzt"] = round(ads_cost, 2)
            if day_row["profit_kzt"] is None:
                day_row["profit_after_ads_kzt"] = None
            else:
                day_row["profit_after_ads_kzt"] = round(day_row["profit_kzt"] - ads_cost, 2)
        else:
            day_row["ads_spend_kzt"] = None
            day_row["profit_after_ads_kzt"] = None

    last_7_list: list[dict[str, Any]] = []
    for i in range(max(1, int(last_7_days))):
        day = (start_7 + timedelta(days=i)).isoformat()
        if day in by_date:
            item = {"date": day, **by_date[day]}
        else:
            item = {
                "date": day,
                "units_delivered": None,
                "units_shipped": None,
                "net_rev_kzt": None,
                "cogs_kzt": None,
                "profit_kzt": None,
                "ads_spend_kzt": round(float(ads_by_date.get(day, 0.0)), 2) if ads_available else None,
                "profit_after_ads_kzt": None,
            }
        last_7_list.append(item)

    observed_days_last_7_calendar = sum(
        1 for row in last_7_list if row["net_rev_kzt"] is not None
    )

    available_days_sorted = sorted(by_date.keys())
    latest_sale_date_available = available_days_sorted[-1] if available_days_sorted else None
    sales_truth_freshness_days = (
        (as_of_date - date.fromisoformat(latest_sale_date_available)).days
        if latest_sale_date_available
        else None
    )
    latest_7_observed_days: list[dict[str, Any]] = []
    for day in available_days_sorted[-7:]:
        latest_7_observed_days.append({"date": day, **by_date[day]})

    window_30_days = [
        (start_30 + timedelta(days=i)).isoformat() for i in range(max(1, int(last_30_days)))
    ]
    series_30_net = [by_date[d]["net_rev_kzt"] for d in window_30_days if d in by_date]
    series_30_cogs = [
        by_date[d]["cogs_kzt"]
        for d in window_30_days
        if d in by_date and by_date[d]["cogs_kzt"] is not None
    ]
    series_30_profit = [
        by_date[d]["profit_kzt"]
        for d in window_30_days
        if d in by_date and by_date[d]["profit_kzt"] is not None
    ]

    series_7_net = [r["net_rev_kzt"] for r in last_7_list if r["net_rev_kzt"] is not None]
    series_7_cogs = [r["cogs_kzt"] for r in last_7_list if r["cogs_kzt"] is not None]
    series_7_profit = [r["profit_kzt"] for r in last_7_list if r["profit_kzt"] is not None]
    series_30_ads = [
        by_date[d]["ads_spend_kzt"]
        for d in window_30_days
        if d in by_date and by_date[d]["ads_spend_kzt"] is not None
    ]
    series_30_profit_after_ads = [
        by_date[d]["profit_after_ads_kzt"]
        for d in window_30_days
        if d in by_date and by_date[d]["profit_after_ads_kzt"] is not None
    ]
    series_7_ads = [r["ads_spend_kzt"] for r in last_7_list if r["ads_spend_kzt"] is not None]
    series_7_profit_after_ads = [
        r["profit_after_ads_kzt"] for r in last_7_list if r["profit_after_ads_kzt"] is not None
    ]

    def _avg(values: list[float]) -> float:
        if not values:
            return 0.0
        return round(sum(values) / len(values), 2)

    def _avg_or_none(values: list[float]) -> float | None:
        if not values:
            return None
        return round(sum(values) / len(values), 2)

    selection_cache_path = waybill_selection_cache_path
    if (
        selection_cache_path.resolve() == DEFAULT_WAYBILL_SELECTION_CACHE.resolve()
        and db_path.resolve() != DEFAULT_DB.resolve()
    ):
        # Test/fixture DBs should use local sibling cache if present, otherwise fail-closed as missing.
        selection_cache_path = db_path.resolve().parent.parent / "excel_ui" / "ActiveOrders" / "waybills" / "_waybill_selection_orders.json"

    waybill_snapshot = load_waybill_selection_snapshot(
        db_path=db_path,
        as_of_date=as_of_date,
        selection_cache_path=selection_cache_path,
    )

    return {
        "as_of_date": as_of_date.isoformat(),
        "last_7_days": last_7_list,
        "latest_7_observed_days": latest_7_observed_days,
        "avg_30d_net_rev_kzt": _avg(series_30_net),
        "avg_30d_cogs_kzt": _avg(series_30_cogs),
        "avg_30d_profit_kzt": _avg(series_30_profit),
        "avg_30d_ads_spend_kzt": _avg_or_none(series_30_ads),
        "avg_30d_profit_after_ads_kzt": _avg_or_none(series_30_profit_after_ads),
        "avg_7d_net_rev_kzt": _avg(series_7_net),
        "avg_7d_cogs_kzt": _avg_or_none(series_7_cogs),
        "avg_7d_profit_kzt": _avg_or_none(series_7_profit),
        "avg_7d_ads_spend_kzt": _avg_or_none(series_7_ads),
        "avg_7d_profit_after_ads_kzt": _avg_or_none(series_7_profit_after_ads),
        "observed_days_last_7_calendar": observed_days_last_7_calendar,
        "latest_sale_date_available": latest_sale_date_available,
        "sales_truth_freshness_days": sales_truth_freshness_days,
        "revenue_fallback_days": fallback_revenue_days,
        "fallback_rows": fallback_rows,
        "unresolved_rows": unresolved_rows,
        "unresolved_sku_count": len(unresolved_skus),
        "total_rows": total_rows,
        "cogs_fallback_coverage_pct": round((fallback_rows / total_rows * 100.0), 2) if total_rows else 0.0,
        "ads": ads_totals,
        "waybill_snapshot": waybill_snapshot,
    }


def _external_reference_check(
    *,
    external_sales_csv: Path | None,
    metrics: dict[str, Any],
) -> dict[str, Any]:
    if external_sales_csv is None:
        return {"status": "skipped", "reason": "no external csv provided"}
    if not external_sales_csv.exists():
        return {"status": "missing", "path": str(external_sales_csv)}

    try:
        df = pd.read_csv(external_sales_csv)
    except Exception as exc:
        return {"status": "error", "path": str(external_sales_csv), "error": str(exc)}

    needed = {"sale_date", "total_net_rev_kzt", "total_cogs_kzt"}
    if not needed.issubset(set(df.columns)):
        return {
            "status": "error",
            "path": str(external_sales_csv),
            "error": f"missing columns: {sorted(needed - set(df.columns))}",
        }

    grouped = (
        df.groupby("sale_date", dropna=True)[["total_net_rev_kzt", "total_cogs_kzt"]]
        .sum()
        .reset_index()
    )
    ext_map = {
        str(row["sale_date"]): (
            float(row["total_net_rev_kzt"] or 0.0),
            float(row["total_cogs_kzt"] or 0.0),
        )
        for _, row in grouped.iterrows()
    }
    local_map = {
        row["date"]: (float(row["net_rev_kzt"] or 0.0), float(row["cogs_kzt"] or 0.0))
        for row in metrics["last_7_days"]
        if row["net_rev_kzt"] is not None and row["cogs_kzt"] is not None
    }
    overlap = sorted(set(ext_map.keys()) & set(local_map.keys()))
    if not overlap:
        return {"status": "ok", "path": str(external_sales_csv), "matched_days": 0}

    max_net = 0.0
    max_cogs = 0.0
    for day in overlap:
        ext_net, ext_cogs = ext_map[day]
        loc_net, loc_cogs = local_map[day]
        max_net = max(max_net, abs(ext_net - loc_net))
        max_cogs = max(max_cogs, abs(ext_cogs - loc_cogs))
    return {
        "status": "ok",
        "path": str(external_sales_csv),
        "matched_days": len(overlap),
        "max_abs_diff_net_rev_kzt": round(max_net, 2),
        "max_abs_diff_cogs_kzt": round(max_cogs, 2),
    }


def _render_markdown(
    *,
    generated_at: datetime,
    as_of_date: str,
    capital: dict[str, Any],
    sales_metrics: dict[str, Any],
    external_check: dict[str, Any],
) -> str:
    capital_rows = [
        ["Cash (actual, bank_accounts.yaml)", _fmt_kzt(capital["cash_actual_kzt"])],
        ["Inventory on-hand paid", _fmt_kzt(capital["inventory_on_hand_paid_kzt"])],
        ["Inventory inbound paid", _fmt_kzt(capital["inventory_inbound_paid_kzt"])],
        ["Inventory on-delivery paid", _fmt_kzt(capital["inventory_on_delivery_paid_kzt"])],
        ["Total capital (paid truth)", _fmt_kzt(capital["total_capital_paid_kzt"])],
        ["Inbound unpaid obligations", _fmt_kzt(capital["inbound_unpaid_obligations_kzt"])],
        [
            "Capital + unpaid inbound",
            _fmt_kzt(capital["total_capital_paid_kzt"] + capital["inbound_unpaid_obligations_kzt"]),
        ],
    ]
    observed_days_last_7 = int(sales_metrics.get("observed_days_last_7_calendar") or 0)
    latest_sale_date_available = sales_metrics.get("latest_sale_date_available")
    sales_truth_freshness_days = sales_metrics.get("sales_truth_freshness_days")
    freshness_status = "unknown"
    if sales_truth_freshness_days is not None:
        freshness_status = "fresh" if int(sales_truth_freshness_days) <= 2 else "stale"

    perf_rows = [
        ["Avg 30d Net Rev", _fmt_kzt(sales_metrics["avg_30d_net_rev_kzt"])],
        ["Avg 30d COGS", _fmt_kzt(sales_metrics["avg_30d_cogs_kzt"])],
        ["Avg 30d Profit", _fmt_kzt(sales_metrics["avg_30d_profit_kzt"])],
        ["Avg 30d Ads Spend", _fmt_kzt(sales_metrics["avg_30d_ads_spend_kzt"])],
        ["Avg 30d Profit After Ads", _fmt_kzt(sales_metrics["avg_30d_profit_after_ads_kzt"])],
        ["Avg 7d Net Rev", _fmt_kzt(sales_metrics["avg_7d_net_rev_kzt"] if observed_days_last_7 > 0 else None)],
        ["Avg 7d COGS", _fmt_kzt(sales_metrics["avg_7d_cogs_kzt"] if observed_days_last_7 > 0 else None)],
        ["Avg 7d Profit", _fmt_kzt(sales_metrics["avg_7d_profit_kzt"] if observed_days_last_7 > 0 else None)],
        ["Avg 7d Ads Spend", _fmt_kzt(sales_metrics["avg_7d_ads_spend_kzt"] if observed_days_last_7 > 0 else None)],
        [
            "Avg 7d Profit After Ads",
            _fmt_kzt(sales_metrics["avg_7d_profit_after_ads_kzt"] if observed_days_last_7 > 0 else None),
        ],
    ]
    daily_rows = [
        [
            row["date"],
            str(int(round(float(row.get("units_delivered")))))
            if row.get("units_delivered") is not None
            else "N/A",
            _fmt_kzt(row["net_rev_kzt"]),
            _fmt_kzt(row["cogs_kzt"]),
            _fmt_kzt(row["ads_spend_kzt"]),
            _fmt_kzt(row["profit_kzt"]),
            _fmt_kzt(row["profit_after_ads_kzt"]),
        ]
        for row in sales_metrics["last_7_days"]
    ]
    observed_rows = [
        [
            row["date"],
            str(int(round(float(row.get("units_delivered")))))
            if row.get("units_delivered") is not None
            else "N/A",
            _fmt_kzt(row["net_rev_kzt"]),
            _fmt_kzt(row["cogs_kzt"]),
            _fmt_kzt(row["ads_spend_kzt"]),
            _fmt_kzt(row["profit_kzt"]),
            _fmt_kzt(row["profit_after_ads_kzt"]),
        ]
        for row in sales_metrics.get("latest_7_observed_days") or []
    ]
    waybill_snapshot = sales_metrics.get("waybill_snapshot") or {}
    waybill_status = str(waybill_snapshot.get("status") or "missing")
    waybill_stores = waybill_snapshot.get("stores") or {}
    waybill_rows: list[list[str]] = []
    for store_code in sorted(waybill_stores.keys()):
        store_row = waybill_stores[store_code] or {}
        waybill_rows.append(
            [
                store_code,
                str(int(store_row.get("orders") or 0)),
                str(int(round(float(store_row.get("units") or 0.0)))),
            ]
        )
    if waybill_rows:
        waybill_totals = waybill_snapshot.get("totals") or {}
        waybill_rows.append(
            [
                "TOTAL",
                str(int(waybill_totals.get("orders") or 0)),
                str(int(round(float(waybill_totals.get("units") or 0.0)))),
            ]
        )
    ads_coverage_raw = sales_metrics["ads"].get("mapping_coverage_pct")
    ads_coverage_text = (
        "N/A" if ads_coverage_raw is None else f"{float(ads_coverage_raw):.2f}%"
    )
    revenue_fallback_days = int(sales_metrics.get("revenue_fallback_days") or 0)
    sales_source_line = (
        "view_sales_line_truth / view_sales_daily_truth "
        "(canonical interface over staging)"
    )
    if revenue_fallback_days > 0:
        sales_source_line += (
            " + fact_orders_kaspi COMPLETED revenue-only fallback "
            f"(days added: {revenue_fallback_days})"
        )

    lines = [
        "# Business Insides Snapshot",
        "",
        f"- Generated at: `{generated_at.strftime('%Y-%m-%d %H:%M:%S')}`",
        f"- As of date: `{as_of_date}`",
        f"- Paid-capital snapshot date: `{capital.get('snapshot_date')}`",
        f"- Bank snapshot date: `{capital.get('bank_as_of_date')}`",
        "",
        "## Capital Snapshot (KZT)",
        "",
        "```text",
        _ascii_table(["Metric", "Value KZT"], capital_rows),
        "```",
        "",
        "## Performance Metrics (KZT)",
        "",
        "```text",
        _ascii_table(["Metric", "Value KZT"], perf_rows),
        "```",
        "",
        "## Last 7 Days Values (KZT)",
        "",
        "```text",
        _ascii_table(
            ["Date", "Units Delivered (COMPLETED)", "Net Rev", "COGS", "Ads Spend", "Profit", "Profit After Ads"],
            daily_rows,
        ),
        "```",
        "",
        "## Sales Truth Freshness",
        "",
        f"- Latest observed sale date (truth): `{latest_sale_date_available or 'N/A'}`",
        f"- Freshness lag (days): `{sales_truth_freshness_days if sales_truth_freshness_days is not None else 'N/A'}`",
        f"- Freshness status: `{freshness_status}`",
        f"- Observed rows in last 7 calendar days: `{observed_days_last_7}`",
    ]
    if observed_days_last_7 == 0:
        lines.extend(
            [
                "- Sales truth is stale for recent 7-day calendar window.",
                "",
            ]
        )
    else:
        lines.append("")

    lines.extend(
        [
            "## Latest Observed Sales Days (Truth)",
            "",
            "```text",
            _ascii_table(
                ["Date", "Units Delivered (COMPLETED)", "Net Rev", "COGS", "Ads Spend", "Profit", "Profit After Ads"],
                observed_rows or [["N/A", "N/A", "N/A", "N/A", "N/A", "N/A", "N/A"]],
            ),
            "```",
            "",
            "## Waybill-State Shipment Snapshot",
            "",
            f"- Snapshot status: `{waybill_status}`",
            f"- Cache file: `{waybill_snapshot.get('cache_path')}`",
            f"- Target date in cache: `{waybill_snapshot.get('target_date') or 'N/A'}`",
            f"- Include overdue: `{waybill_snapshot.get('include_overdue')}`",
            f"- Mode all_dates: `{waybill_snapshot.get('all_dates')}`",
        ]
    )
    if waybill_rows:
        lines.extend(
            [
                "",
                "```text",
                _ascii_table(
                    ["Store", "Orders Shipped (Waybill Selection)", "Units Shipped (DB qty)"],
                    waybill_rows,
                ),
                "```",
                "",
            ]
        )
    else:
        lines.extend(
            [
                "- Waybill cache is unavailable for this as_of day; shipment metrics are not decision-grade.",
                "",
            ]
        )

    lines.extend(
        [
        "## Data Quality",
        "",
        f"- Sales source: `{sales_source_line}`.",
        "- Metric definition: `Units Delivered (COMPLETED)` come from canonical sales truth views.",
        "- Metric definition: `Orders/Units Shipped (Waybill Selection)` come from waybill selection cache + DB quantities.",
        f"- COGS fallback rows: `{sales_metrics['fallback_rows']}/{sales_metrics['total_rows']}` "
        f"({sales_metrics['cogs_fallback_coverage_pct']:.2f}%).",
        f"- Unresolved COGS rows: `{sales_metrics['unresolved_rows']}`.",
        f"- Unresolved SKU count: `{sales_metrics['unresolved_sku_count']}`.",
        f"- Ads source status: `{sales_metrics['ads'].get('status')}` "
        f"(reason: `{sales_metrics['ads'].get('reason')}`).",
        f"- Ads mapping coverage: `{ads_coverage_text}`.",
        f"- Ads mapped/unmapped cost: `{_fmt_kzt(sales_metrics['ads'].get('mapped_cost_kzt'))}` / "
        f"`{_fmt_kzt(sales_metrics['ads'].get('unmapped_cost_kzt'))}`.",
        "",
        "## External Reference Check",
        "",
        f"- Status: `{external_check.get('status')}`",
        f"- Details: `{external_check}`",
        "",
        ]
    )
    return "\n".join(lines) + "\n"


def generate_business_insides(
    *,
    db_path: Path = DEFAULT_DB,
    bank_accounts_path: Path = DEFAULT_BANK,
    as_of: str | date | None = None,
    output_dir: Path = DEFAULT_OUTPUT_DIR,
    external_sales_csv: Path | None = None,
    strict_cogs: bool = False,
    waybill_selection_cache_path: Path = DEFAULT_WAYBILL_SELECTION_CACHE,
) -> dict[str, Any]:
    as_of_date = _parse_as_of(as_of)
    generated_at = datetime.now()
    capital = compute_paid_capital_truth(
        db_path=db_path,
        bank_accounts_path=bank_accounts_path,
        as_of=as_of_date,
    )
    sales_metrics = compute_sales_metrics(
        db_path=db_path,
        as_of=as_of_date,
        enforce_query_guard=bool(strict_cogs),
        waybill_selection_cache_path=waybill_selection_cache_path,
    )
    if strict_cogs and int(sales_metrics["unresolved_rows"]) > 0:
        raise RuntimeError(
            "Unresolved COGS rows detected in requested window: "
            f"rows={sales_metrics['unresolved_rows']}, "
            f"sku_count={sales_metrics['unresolved_sku_count']}"
        )
    external_check = _external_reference_check(
        external_sales_csv=external_sales_csv,
        metrics=sales_metrics,
    )

    output_dir.mkdir(parents=True, exist_ok=True)
    snapshots_dir = output_dir / "snapshots"
    snapshots_dir.mkdir(parents=True, exist_ok=True)

    snapshot_name = f"BUSINESS_INSIDES_{as_of_date.isoformat()}.md"
    snapshot_path = snapshots_dir / snapshot_name
    latest_path = output_dir / snapshot_name
    snapshot_json_name = f"BUSINESS_INSIDES_{as_of_date.isoformat()}.json"
    snapshot_json_path = snapshots_dir / snapshot_json_name
    latest_json_path = output_dir / snapshot_json_name
    content = _render_markdown(
        generated_at=generated_at,
        as_of_date=as_of_date.isoformat(),
        capital=capital,
        sales_metrics=sales_metrics,
        external_check=external_check,
    )
    snapshot_path.write_text(content, encoding="utf-8")
    latest_path.write_text(content, encoding="utf-8")
    payload = {
        "generated_at": generated_at.replace(microsecond=0).isoformat(),
        "as_of": as_of_date.isoformat(),
        "capital": capital,
        "performance": {
            "avg_30d_net_rev_kzt": sales_metrics["avg_30d_net_rev_kzt"],
            "avg_30d_cogs_kzt": sales_metrics["avg_30d_cogs_kzt"],
            "avg_30d_profit_kzt": sales_metrics["avg_30d_profit_kzt"],
            "avg_30d_ads_spend_kzt": sales_metrics["avg_30d_ads_spend_kzt"],
            "avg_30d_profit_after_ads_kzt": sales_metrics["avg_30d_profit_after_ads_kzt"],
            "avg_7d_net_rev_kzt": sales_metrics["avg_7d_net_rev_kzt"],
            "avg_7d_cogs_kzt": sales_metrics["avg_7d_cogs_kzt"],
            "avg_7d_profit_kzt": sales_metrics["avg_7d_profit_kzt"],
            "avg_7d_ads_spend_kzt": sales_metrics["avg_7d_ads_spend_kzt"],
            "avg_7d_profit_after_ads_kzt": sales_metrics["avg_7d_profit_after_ads_kzt"],
            "observed_days_last_7_calendar": sales_metrics["observed_days_last_7_calendar"],
            "latest_sale_date_available": sales_metrics["latest_sale_date_available"],
            "sales_truth_freshness_days": sales_metrics["sales_truth_freshness_days"],
        },
        "last_7_days": sales_metrics["last_7_days"],
        "latest_7_observed_days": sales_metrics["latest_7_observed_days"],
        "fallback_rows": sales_metrics["fallback_rows"],
        "total_rows": sales_metrics["total_rows"],
        "unresolved_rows": sales_metrics["unresolved_rows"],
        "unresolved_sku_count": sales_metrics["unresolved_sku_count"],
        "ads": sales_metrics["ads"],
        "waybill_snapshot": sales_metrics.get("waybill_snapshot"),
        "external_check": external_check,
    }
    payload_json = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
    snapshot_json_path.write_text(payload_json, encoding="utf-8")
    latest_json_path.write_text(payload_json, encoding="utf-8")

    return {
        "as_of_date": as_of_date.isoformat(),
        "snapshot_path": str(snapshot_path),
        "latest_path": str(latest_path),
        "snapshot_json_path": str(snapshot_json_path),
        "latest_json_path": str(latest_json_path),
        "capital": capital,
        "performance": payload["performance"],
        "last_7_days": sales_metrics["last_7_days"],
        "latest_7_observed_days": sales_metrics["latest_7_observed_days"],
        "fallback_rows": sales_metrics["fallback_rows"],
        "total_rows": sales_metrics["total_rows"],
        "unresolved_rows": sales_metrics["unresolved_rows"],
        "unresolved_sku_count": sales_metrics["unresolved_sku_count"],
        "ads": sales_metrics["ads"],
        "waybill_snapshot": sales_metrics.get("waybill_snapshot"),
        "external_check": external_check,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate business insides snapshot markdown")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument("--bank-accounts", type=Path, default=DEFAULT_BANK)
    parser.add_argument("--as-of", type=str, default=None)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--external-sales-csv", type=Path, default=None)
    parser.add_argument("--strict-cogs", action="store_true")
    parser.add_argument("--waybill-selection-cache", type=Path, default=DEFAULT_WAYBILL_SELECTION_CACHE)
    args = parser.parse_args()

    result = generate_business_insides(
        db_path=args.db,
        bank_accounts_path=args.bank_accounts,
        as_of=args.as_of,
        output_dir=args.output_dir,
        external_sales_csv=args.external_sales_csv,
        strict_cogs=args.strict_cogs,
        waybill_selection_cache_path=args.waybill_selection_cache,
    )
    def _fmt_metric(value: Any) -> str:
        if value is None:
            return "N/A"
        return f"{float(value):.2f}"

    print(f"snapshot_path={result['snapshot_path']}")
    print(f"snapshot_json_path={result['snapshot_json_path']}")
    print(f"latest_path={result['latest_path']}")
    print(f"latest_json_path={result['latest_json_path']}")
    print(f"avg_7d_net_rev_kzt={_fmt_metric(result['performance']['avg_7d_net_rev_kzt'])}")
    print(f"avg_7d_profit_kzt={_fmt_metric(result['performance']['avg_7d_profit_kzt'])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
