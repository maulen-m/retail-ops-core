#!/usr/bin/env python3
"""
Export a sizing queue CSV from the DB (DB-first; Excel optional enrichment).

Queue definition:
- planned_shipment_date <= as_of_date
- assigned_size and my_size are NULL/empty

Outputs a CSV that operators can fill with sizing decisions.
"""
from __future__ import annotations

import argparse
import csv
from datetime import date, datetime
from pathlib import Path
from typing import Any

from core.db import DEFAULT_DB_PATH, get_db
from core.paths import data_path, get_data_root


CRM_ORDER_ID_ALIASES = {"orderid", "№заказа", "номерзаказа"}
CRM_PHONE_ALIASES = {"phone", "телефон", "cellphone", "номер"}
CRM_OFFER_SIZE_ALIASES = {"offer_size", "offersize", "размерпредложения", "размер"}


def _normalize(value: Any) -> str:
    return "".join(str(value).strip().lower().split())


def _normalize_order_id(value: Any) -> str:
    if value is None:
        return ""
    order_id = str(value).strip()
    if order_id.endswith(".0"):
        order_id = order_id[:-2]
    return order_id


def _derive_offer_size(sku_id: str) -> str:
    if not sku_id:
        return ""
    if "_" in sku_id:
        return sku_id.split("_")[-1]
    return ""


def _table_exists(conn, table: str) -> bool:
    row = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
        (table,),
    ).fetchone()
    return bool(row)


def _load_crm_enrichment(crm_path: Path, sheet: str) -> dict[str, dict[str, str]]:
    try:
        import pandas as pd
    except Exception:
        return {}

    if not crm_path.exists():
        return {}

    try:
        df = pd.read_excel(crm_path, sheet_name=sheet)
    except Exception:
        return {}

    col_map = {_normalize(col): col for col in df.columns}

    order_col = None
    for alias in CRM_ORDER_ID_ALIASES:
        if alias in col_map:
            order_col = col_map[alias]
            break

    if not order_col:
        return {}

    phone_col = None
    for alias in CRM_PHONE_ALIASES:
        if alias in col_map:
            phone_col = col_map[alias]
            break

    offer_size_col = None
    for alias in CRM_OFFER_SIZE_ALIASES:
        if alias in col_map:
            offer_size_col = col_map[alias]
            break

    enrichment: dict[str, dict[str, str]] = {}
    for _, row in df.iterrows():
        order_id = _normalize_order_id(row.get(order_col))
        if not order_id:
            continue
        if order_id not in enrichment:
            enrichment[order_id] = {"phone": "", "offer_size": ""}
        if phone_col and not enrichment[order_id]["phone"]:
            val = str(row.get(phone_col, "")).strip()
            if val and val.lower() not in ("nan", "none"):
                enrichment[order_id]["phone"] = val
        if offer_size_col and not enrichment[order_id]["offer_size"]:
            val = str(row.get(offer_size_col, "")).strip()
            if val and val.lower() not in ("nan", "none"):
                enrichment[order_id]["offer_size"] = val

    return enrichment


def export_sizing_queue(
    db_path: Path,
    output_path: Path,
    as_of_date: date,
    crm_path: Path | None = None,
    crm_sheet: str | None = None,
) -> int:
    crm_enrichment: dict[str, dict[str, str]] = {}
    if crm_path and crm_sheet:
        crm_enrichment = _load_crm_enrichment(crm_path, crm_sheet)

    with get_db(db_path) as conn:
        if not _table_exists(conn, "fact_orders_kaspi"):
            raise RuntimeError(
                "Missing table fact_orders_kaspi. Run: python scripts/sync_kaspi_orders.py --all"
            )

        rows = conn.execute(
            """
            SELECT
                order_id,
                store_code,
                kaspi_offer_name,
                sku_id,
                my_size,
                assigned_size,
                planned_shipment_date
            FROM fact_orders_kaspi
            WHERE
                (assigned_size IS NULL OR assigned_size = '')
                AND (my_size IS NULL OR my_size = '')
                AND planned_shipment_date IS NOT NULL
                AND planned_shipment_date <= ?
            ORDER BY planned_shipment_date, store_code, order_id
            """,
            (as_of_date.isoformat(),),
        ).fetchall()

    output_path.parent.mkdir(parents=True, exist_ok=True)

    fieldnames = [
        "order_id",
        "store_code",
        "phone",
        "kaspi_offer_name",
        "offer_size",
        "planned_ship_date",
        "my_size",
        "customer_height_cm",
        "customer_weight_kg",
        "decided_by",
        "method",
    ]

    with open(output_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            order_id = _normalize_order_id(row["order_id"])
            sku_id = str(row["sku_id"] or "").strip()
            offer_size = _derive_offer_size(sku_id)
            enrich = crm_enrichment.get(order_id, {})
            if enrich.get("offer_size"):
                offer_size = enrich["offer_size"]
            writer.writerow(
                {
                    "order_id": order_id,
                    "store_code": row["store_code"] or "",
                    "phone": enrich.get("phone", ""),
                    "kaspi_offer_name": row["kaspi_offer_name"] or "",
                    "offer_size": offer_size,
                    "planned_ship_date": row["planned_shipment_date"] or "",
                    "my_size": "",
                    "customer_height_cm": "",
                    "customer_weight_kg": "",
                    "decided_by": "",
                    "method": "",
                }
            )

    return len(rows)


def main() -> int:
    parser = argparse.ArgumentParser(description="Export sizing queue CSV from DB")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB_PATH)
    parser.add_argument("--as-of", type=str, default=date.today().isoformat())
    parser.add_argument("--output", type=Path, default=None)
    parser.add_argument("--crm-file", type=Path, default=data_path("excel_ui", "SALES_KSP_CRM_V3.xlsx"))
    parser.add_argument("--crm-sheet", type=str, default="SALES_KSP_CRM_1")
    args = parser.parse_args()

    as_of_date = date.fromisoformat(args.as_of)
    output_path = args.output or data_path(
        "exports", f"sizing_queue_{as_of_date.isoformat()}.csv"
    )

    print(f"Data root: {get_data_root()}")
    print(f"DB: {args.db}")
    print(f"As of: {as_of_date.isoformat()}")
    print(f"Output: {output_path}")

    count = export_sizing_queue(
        args.db,
        output_path,
        as_of_date,
        crm_path=args.crm_file,
        crm_sheet=args.crm_sheet,
    )

    print(f"Exported {count} orders requiring sizing")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
