from __future__ import annotations

from collections import defaultdict
from datetime import date, timedelta
from pathlib import Path
from typing import Any, Optional

import pandas as pd

from core.db import get_db
from core.ops.expected_shipping_status import ExpectedShippingFacts, carryforward
from core.utils.kaspi_dates import parse_kaspi_date


STORE_NAME_TO_API_CODE = {
    "AcmeWear": "ACMEWEAR",
    "Universal": "UNIVERSAL",
    "11KZ": "11KZ",
    "STORE-B": "STOREB",
    "Store-C": "MELVIS",
}

DB_STORE_TO_API = {
    "UNIVERSAL": "UNIVERSAL",
    "ACMEWEAR": "ACMEWEAR",
    "11KZ": "11KZ",
    "MELVIS": "MELVIS",
    "STOREB": "STOREB",
    "STORE-B": "STOREB",
    "30137883_PP1": "ACMEWEAR",
    "30000001_PP1": "UNIVERSAL",
    "30290083_PP1": "11KZ",
    "30000002_PP1": "STOREB",
    "30362323_PP1": "MELVIS",
    "PP1": "ACMEWEAR",
    "PP2": "ACMEWEAR",
}


def _normalize_api_store_code(value: Any) -> Optional[str]:
    if pd.isna(value) or value is None:
        return None
    raw = str(value).strip()
    if not raw:
        return None
    upper = raw.upper()
    if upper in DB_STORE_TO_API:
        return DB_STORE_TO_API[upper]
    for display_name, api_code in STORE_NAME_TO_API_CODE.items():
        if display_name.lower() == raw.lower():
            return api_code
    return None


def _has_text(value: Any) -> bool:
    if value is None or pd.isna(value):
        return False
    return str(value).strip().lower() not in {"", "nan", "none"}


def _is_handed_over(value: Any) -> bool:
    if value is None or pd.isna(value):
        return False
    text = str(value).strip().lower()
    return text not in {"", "nan", "none", "nat"}


def get_overdue_waybill_ready_order_ids_from_db(
    db_path: Optional[Path],
    *,
    target_date: date,
    lookback_days: Optional[int],
    store_filter: Optional[str] = None,
) -> dict[str, set[str]]:
    """
    Return overdue orders that are still ready for handover and already have a waybill.

    These are the safe carry-forward candidates for the daily waybill/send flow.
    """
    if not db_path or not Path(db_path).exists():
        return {}

    store_filter_api = _normalize_api_store_code(store_filter) if store_filter else None
    min_date = target_date - timedelta(days=lookback_days) if lookback_days is not None else None

    with get_db(db_path) as conn:
        table = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='fact_orders_kaspi'"
        ).fetchone()
        if not table:
            return {}

        columns = {
            row[1]
            for row in conn.execute("PRAGMA table_info(fact_orders_kaspi)").fetchall()
        }
        waybill_select = "waybill_url" if "waybill_url" in columns else "NULL AS waybill_url"
        waybill_downloaded_select = (
            "waybill_downloaded"
            if "waybill_downloaded" in columns
            else "0 AS waybill_downloaded"
        )
        returned_select = (
            "returned_to_warehouse"
            if "returned_to_warehouse" in columns
            else "NULL AS returned_to_warehouse"
        )

        rows = conn.execute(
            f"""
            SELECT
                order_id,
                store_code,
                assigned_size,
                my_size,
                planned_shipment_date,
                kaspi_status,
                kaspi_status_detail,
                internal_status,
                signature_required,
                courier_transmission_date,
                {waybill_select},
                {waybill_downloaded_select},
                {returned_select}
            FROM fact_orders_kaspi
            WHERE planned_shipment_date IS NOT NULL
              AND planned_shipment_date != ''
            """
        ).fetchall()

    grouped: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        order_id = str(row["order_id"] or "").strip()
        if order_id.endswith(".0"):
            order_id = order_id[:-2]
        if not order_id:
            continue

        store_code = _normalize_api_store_code(row["store_code"])
        if not store_code:
            continue
        if store_filter_api and store_code != store_filter_api:
            continue

        grouped[(store_code, order_id)].append(
            {
                **dict(row),
                "store_code": store_code,
                "order_id": order_id,
            }
        )

    results: dict[str, set[str]] = defaultdict(set)
    for (store_code, order_id), order_rows in grouped.items():
        planned_in_window = any(
            planned_date is not None
            and planned_date < target_date
            and (min_date is None or planned_date >= min_date)
            for planned_date in (
                parse_kaspi_date(row["planned_shipment_date"])
                for row in order_rows
            )
        )
        if not planned_in_window:
            continue
        decision = carryforward.evaluate(
            ExpectedShippingFacts.from_lines(
                order_rows,
                target_date=target_date,
            )
        )
        if decision.projection:
            results[decision.normalized_store].add(order_id)

    return dict(results)
