#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Export orders pending courier handover for today (including overdue).

Primary source: fact_orders_kaspi (DB) to avoid Kaspi API 14-day limit.
Optional enrichment: planned delivery date + courier transmission time from API
(last 14 days) when available.
"""
from __future__ import annotations

import argparse
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Optional
from zoneinfo import ZoneInfo

import pandas as pd
from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from core.db import get_db  # noqa: E402
from core.integrations.kaspi_api_client import KaspiAPIClient, KaspiAuthError, STORE_TOKEN_MAP  # noqa: E402
from core.utils.sku_map import lookup_sku_from_offer  # noqa: E402

ALMATY_TZ = ZoneInfo("Asia/Almaty")
CANCELLED_STATUSES_RU = {"Отменен", "Возврат", "Возвращен"}
CANCELLED_STATES = {"CANCELLED", "CANCELLING", "RETURNING", "RETURNED"}


def _ts_to_dt(value: Any) -> Optional[datetime]:
    if value is None:
        return None
    try:
        return datetime.fromtimestamp(float(value) / 1000.0, tz=ALMATY_TZ)
    except Exception:
        return None


def _parse_date(value: Any) -> Optional[datetime]:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    try:
        return datetime.fromisoformat(text)
    except ValueError:
        pass
    for fmt in ("%Y-%m-%d", "%Y-%m-%d %H:%M:%S", "%d.%m.%Y"):
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            continue
    return None


def _safe_int(value: Any) -> int:
    if value is None:
        return 0
    try:
        return int(float(value))
    except Exception:
        return 0


def _fetch_api_enrichment(days: int, verbose: bool = False) -> dict[str, dict[str, Optional[datetime]]]:
    """Fetch planned delivery + courier transmission times for last N days."""
    since = (datetime.now(ALMATY_TZ) - timedelta(days=days)).strftime("%Y-%m-%d")
    mapping: dict[str, dict[str, Optional[datetime]]] = {}
    states = ["NEW", "KASPI_DELIVERY"]

    for store_code in STORE_TOKEN_MAP.keys():
        try:
            client = KaspiAPIClient(store_code=store_code)
        except KaspiAuthError as exc:
            if verbose:
                print(f"  Skipping API enrich for {store_code}: {exc}")
            continue

        for state in states:
            orders = client.list_all_orders(
                state=state,
                since=since,
                include_orders="user",
            )
            if verbose:
                print(f"  {store_code} API {state}: {len(orders)} orders")
            for order in orders:
                attrs = order.get("attributes", {})
                if (attrs.get("state") in CANCELLED_STATES) or (attrs.get("status") in CANCELLED_STATES):
                    continue
                delivery = attrs.get("kaspiDelivery", {})
                order_code = attrs.get("code", "")
                if not order_code:
                    continue
                if order_code in mapping:
                    continue
                mapping[order_code] = {
                    "planned_delivery_date": _ts_to_dt(delivery.get("plannedDeliveryDate")),
                    "courier_transmission_date": _ts_to_dt(delivery.get("courierTransmissionDate")),
                }

    return mapping


def build_rows(days: int, verbose: bool = False) -> list[dict]:
    today = datetime.now(ALMATY_TZ).date()
    api_map = _fetch_api_enrichment(days=days, verbose=verbose)

    rows: list[dict] = []

    with get_db() as conn:
        db_rows = conn.execute(
            """
            SELECT order_id, kaspi_offer_name, sku_key, my_size, quantity,
                   planned_shipment_date, kaspi_status
            FROM fact_orders_kaspi
            WHERE kaspi_status = 'Ожидает передачи курьеру'
              AND planned_shipment_date IS NOT NULL
            """
        ).fetchall()

    # Precompute order-level flags
    by_order: dict[str, dict[str, int]] = {}
    for row in db_rows:
        order_id = str(row["order_id"])
        qty = _safe_int(row["quantity"])
        if order_id not in by_order:
            by_order[order_id] = {"lines": 0, "qty": 0}
        by_order[order_id]["lines"] += 1
        by_order[order_id]["qty"] += qty

    for row in db_rows:
        if row["kaspi_status"] in CANCELLED_STATUSES_RU:
            continue

        planned_ship_dt = _parse_date(row["planned_shipment_date"])
        if not planned_ship_dt:
            continue
        if planned_ship_dt.date() > today:
            continue

        order_id = str(row["order_id"])
        offer_name = str(row["kaspi_offer_name"] or "")
        sku_key = str(row["sku_key"] or "").strip()
        size = str(row["my_size"] or "").strip()

        if not sku_key:
            map_sku, map_size = lookup_sku_from_offer(offer_name)
            if map_sku:
                sku_key = map_sku
            if not size and map_size:
                size = map_size

        api_info = api_map.get(order_id, {})
        planned_delivery = api_info.get("planned_delivery_date")
        courier_transmission = api_info.get("courier_transmission_date")

        multiline = by_order.get(order_id, {}).get("lines", 0) > 1
        is_multi_qty = by_order.get(order_id, {}).get("qty", 0) > 1

        rows.append({
            "planned_ship_date": planned_ship_dt.date(),
            "planned_delivery_date": planned_delivery.date() if planned_delivery else None,
            "shipped_time": courier_transmission,
            "is_active": True,
            "order_id": order_id,
            "quantity": _safe_int(row["quantity"]),
            "kaspi_offer_name": offer_name,
            "sku_key": sku_key,
            "size": size,
            "is_multiline": multiline,
            "is_multi_qty": is_multi_qty,
        })

    return rows


def write_excel(rows: list[dict], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)

    df = pd.DataFrame(rows)
    columns = [
        "planned_ship_date",
        "planned_delivery_date",
        "shipped_time",
        "is_active",
        "order_id",
        "quantity",
        "kaspi_offer_name",
        "sku_key",
        "size",
        "is_multiline",
        "is_multi_qty",
    ]
    df = df[columns]

    # Ensure IDs are text
    df["order_id"] = df["order_id"].astype(str)
    df["sku_key"] = df["sku_key"].astype(str)

    temp_path = output_path.with_suffix(".tmp.xlsx")
    df.to_excel(temp_path, index=False)
    temp_path.replace(output_path)


def main() -> None:
    parser = argparse.ArgumentParser(description="Export orders pending courier handover for today (including overdue).")
    parser.add_argument("--days", type=int, default=14, help="API lookback days for enrichment")
    parser.add_argument("--output", type=Path, default=None, help="Output xlsx path")
    parser.add_argument("--verbose", action="store_true", help="Verbose output")
    args = parser.parse_args()

    load_dotenv()

    rows = build_rows(days=args.days, verbose=args.verbose)

    now = datetime.now(ALMATY_TZ)
    if args.output is None:
        out_dir = PROJECT_ROOT / "excel_ui" / "ActiveOrders" / "pending_to_ship"
        fname = f"pending_to_ship_{now.strftime('%Y-%m-%d_%H%M')}.xlsx"
        output_path = out_dir / fname
    else:
        output_path = args.output

    write_excel(rows, output_path)

    print(f"Saved: {output_path}")
    print(f"Rows: {len(rows)}")


if __name__ == "__main__":
    main()
