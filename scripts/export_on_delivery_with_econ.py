#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Export on-delivery Kaspi orders (raw + economics-enriched).

Creates two Excel files in excel_ui/ActiveOrders/on_delivery:
  - *_raw.xlsx  (Kaspi-format export)
  - *_econ.xlsx (with net revenue, COGS, profit per unit + per line)

Economics follow Master_Inventory_Rules_v8 via core.calc.economics.
"""
from __future__ import annotations

import argparse
import logging
import sys
from datetime import datetime, date
from pathlib import Path
from typing import Any, Optional

import pandas as pd
from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from core.calc.economics import calc_cogs, calc_net_rev  # noqa: E402
from core.db import get_db  # noqa: E402
from core.parsers.kaspi_parser import extract_sku_from_article  # noqa: E402
from scripts.export_on_delivery_orders import (  # noqa: E402
    EXCEL_COLUMNS,
    STORE_WAREHOUSE_MAP,
    export_on_delivery_orders,
    write_excel_with_european_format,
)

logger = logging.getLogger(__name__)


def _parse_date(value: Any) -> Optional[date]:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    if isinstance(value, (datetime, date)):
        return value.date() if isinstance(value, datetime) else value
    text = str(value).strip()
    if not text:
        return None
    for fmt in ("%d.%m.%Y", "%Y-%m-%d", "%d/%m/%Y", "%Y/%m/%d"):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    return None


def _to_float(value: Any) -> Optional[float]:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip().replace(" ", "").replace(",", ".")
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def _to_int(value: Any) -> int:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return 0
    if isinstance(value, (int, float)):
        return int(round(float(value)))
    text = str(value).strip().replace(" ", "")
    if not text:
        return 0
    try:
        return int(round(float(text.replace(",", "."))))
    except ValueError:
        return 0


def _load_sku_meta(sku_keys: list[str]) -> dict[str, dict[str, float]]:
    if not sku_keys:
        return {}
    placeholders = ",".join("?" for _ in sku_keys)
    query = (
        "SELECT sku_key, base_cost_cny, weight_kg, cogs_kzt "
        f"FROM dim_sku WHERE sku_key IN ({placeholders})"
    )
    meta: dict[str, dict[str, float]] = {}
    with get_db() as conn:
        rows = conn.execute(query, sku_keys).fetchall()
    for row in rows:
        meta[row["sku_key"]] = {
            "base_cost_cny": row["base_cost_cny"] or 0.0,
            "weight_kg": row["weight_kg"] or 0.0,
            "cogs_kzt": row["cogs_kzt"] or 0.0,
        }
    return meta


def _compute_econ(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df

    warehouse_to_store = {v: k for k, v in STORE_WAREHOUSE_MAP.items()}
    df["STORE_CODE"] = df.get("Склад передачи КД", "").map(warehouse_to_store).fillna("")

    sku_keys: list[str] = []
    sku_ids: list[str] = []
    sizes: list[str] = []
    product_types: list[str] = []

    for _, row in df.iterrows():
        article = row.get("Артикул")
        offer = row.get("Название товара в Kaspi Магазине") or row.get("Название в системе продавца")
        parsed = extract_sku_from_article(article, offer)
        sku_keys.append(parsed.get("sku_key"))
        sku_ids.append(parsed.get("sku_id"))
        sizes.append(parsed.get("my_size"))
        product_types.append(parsed.get("product_type") or "CL")

    df["SKU_key"] = sku_keys
    df["SKU_ID"] = sku_ids
    df["MY_SIZE"] = sizes
    df["Product_Type"] = product_types

    meta = _load_sku_meta([k for k in df["SKU_key"].dropna().unique().tolist() if k])

    econ_fields = {
        "Sell_price_unit_kzt": [],
        "Sell_price_line_kzt": [],
        "Delivery_fee_unit_kzt": [],
        "Net_rev_unit_kzt": [],
        "Net_rev_line_kzt": [],
        "COGS_unit_kzt": [],
        "COGS_line_kzt": [],
        "Profit_unit_kzt": [],
        "Profit_line_kzt": [],
    }

    for _, row in df.iterrows():
        qty = _to_int(row.get("Количество"))
        price_line = _to_float(row.get("Сумма")) or 0.0
        price_unit = (price_line / qty) if qty else price_line

        delivery_fee_total = _to_float(row.get("Стоимость доставки для продавца")) or 0.0
        delivery_fee_unit = (delivery_fee_total / qty) if qty else delivery_fee_total
        if delivery_fee_unit <= 0:
            delivery_fee_unit = None

        order_date = _parse_date(row.get("Дата поступления заказа"))

        sku_key = row.get("SKU_key")
        sku_meta = meta.get(sku_key or "", {})
        base_cost = sku_meta.get("base_cost_cny", 0.0)
        weight_kg = sku_meta.get("weight_kg", 0.0)
        cogs_unit = None
        if base_cost and weight_kg:
            cogs_unit = calc_cogs(base_cost, weight_kg)
        elif sku_meta.get("cogs_kzt"):
            cogs_unit = float(sku_meta.get("cogs_kzt") or 0.0)

        net_rev_unit = None
        if price_unit > 0:
            net_rev_unit = calc_net_rev(
                price_unit,
                delivery_fee=delivery_fee_unit,
                weight_kg=weight_kg,
                as_of_date=order_date,
            )

        econ_fields["Sell_price_unit_kzt"].append(price_unit if price_unit else None)
        econ_fields["Sell_price_line_kzt"].append(price_line if price_line else None)
        econ_fields["Delivery_fee_unit_kzt"].append(delivery_fee_unit if delivery_fee_unit else None)

        econ_fields["Net_rev_unit_kzt"].append(net_rev_unit)
        econ_fields["Net_rev_line_kzt"].append((net_rev_unit * qty) if net_rev_unit is not None else None)

        econ_fields["COGS_unit_kzt"].append(cogs_unit)
        econ_fields["COGS_line_kzt"].append((cogs_unit * qty) if cogs_unit is not None else None)

        profit_unit = (net_rev_unit - cogs_unit) if (net_rev_unit is not None and cogs_unit is not None) else None
        econ_fields["Profit_unit_kzt"].append(profit_unit)
        econ_fields["Profit_line_kzt"].append((profit_unit * qty) if profit_unit is not None else None)

    for key, values in econ_fields.items():
        df[key] = values

    return df


def _summary_table(df: pd.DataFrame) -> str:
    if df.empty:
        return "No rows."

    qty = pd.to_numeric(df.get("Количество", 0), errors="coerce").fillna(0)
    net_rev = pd.to_numeric(df.get("Net_rev_line_kzt", 0), errors="coerce").fillna(0)
    cogs = pd.to_numeric(df.get("COGS_line_kzt", 0), errors="coerce").fillna(0)
    profit = pd.to_numeric(df.get("Profit_line_kzt", 0), errors="coerce").fillna(0)

    df_summary = pd.DataFrame({
        "Store": df.get("STORE_CODE", ""),
        "Units": qty,
        "Net Rev": net_rev,
        "COGS": cogs,
        "Profit": profit,
    })
    grouped = (
        df_summary
        .groupby("Store", dropna=False)
        .sum(numeric_only=True)
        .reset_index()
    )

    totals = {
        "Store": "TOTAL",
        "Units": grouped["Units"].sum(),
        "Net Rev": grouped["Net Rev"].sum(),
        "COGS": grouped["COGS"].sum(),
        "Profit": grouped["Profit"].sum(),
    }
    grouped = pd.concat([grouped, pd.DataFrame([totals])], ignore_index=True)

    def fmt_num(val: float) -> str:
        return f"{val:,.0f}".replace(",", " ")

    headers = ["Store", "Units", "Net Rev", "COGS", "Profit"]
    rows = [
        [
            str(r["Store"]),
            fmt_num(r["Units"]),
            fmt_num(r["Net Rev"]),
            fmt_num(r["COGS"]),
            fmt_num(r["Profit"]),
        ]
        for _, r in grouped.iterrows()
    ]

    widths = [len(h) for h in headers]
    for row in rows:
        for i, cell in enumerate(row):
            widths[i] = max(widths[i], len(cell))

    def fmt_row(values):
        return "| " + " | ".join(val.ljust(widths[i]) for i, val in enumerate(values)) + " |"

    sep = "+-" + "-+-".join("-" * w for w in widths) + "-+"
    lines = [sep, fmt_row(headers), sep]
    lines += [fmt_row(r) for r in rows]
    lines.append(sep)
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Export on-delivery orders (raw + econ)")
    parser.add_argument("--days", type=int, default=14, help="Lookback days (default: 14)")
    parser.add_argument(
        "--output-dir",
        default=str(PROJECT_ROOT / "excel_ui" / "ActiveOrders" / "on_delivery"),
        help="Output directory for exports",
    )
    parser.add_argument("--verbose", "-v", action="store_true", help="Verbose output")
    args = parser.parse_args()

    load_dotenv(PROJECT_ROOT / ".env")

    logging.basicConfig(
        level=logging.INFO if args.verbose else logging.WARNING,
        format="%(levelname)s: %(message)s",
    )

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    stamp = datetime.now().strftime("%Y-%m-%d_%H%M")
    raw_path = output_dir / f"on_delivery_{stamp}_raw.xlsx"
    econ_path = output_dir / f"on_delivery_{stamp}_econ.xlsx"

    print("=" * 60)
    print("  Export On-Delivery Orders (Raw + Economics)")
    print("=" * 60)
    print(f"  Lookback: {args.days} days")
    print(f"  Raw:  {raw_path}")
    print(f"  Econ: {econ_path}")
    print("")

    rows = export_on_delivery_orders(days=args.days, verbose=args.verbose)
    print(f"Fetched {len(rows)} on-delivery rows.")
    if not rows:
        print("No on-delivery orders found.")
        return 0

    print("Writing raw export...")
    write_excel_with_european_format(rows, raw_path)

    print("Computing economics...")
    df = pd.DataFrame(rows)
    df = _compute_econ(df)

    ordered_cols = [c for c in EXCEL_COLUMNS if c in df.columns]
    extra_cols = [
        "STORE_CODE",
        "SKU_key",
        "SKU_ID",
        "MY_SIZE",
        "Product_Type",
        "Sell_price_unit_kzt",
        "Sell_price_line_kzt",
        "Delivery_fee_unit_kzt",
        "Net_rev_unit_kzt",
        "Net_rev_line_kzt",
        "COGS_unit_kzt",
        "COGS_line_kzt",
        "Profit_unit_kzt",
        "Profit_line_kzt",
    ]
    ordered_cols += [c for c in extra_cols if c in df.columns]
    df = df[ordered_cols]
    df.to_excel(econ_path, index=False, engine="openpyxl")

    print("Summary:")
    print(_summary_table(df))
    print("\nDone!")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
