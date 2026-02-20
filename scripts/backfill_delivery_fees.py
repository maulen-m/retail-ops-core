#!/usr/bin/env python3
"""
Backfill delivery_fee + economics for rows where delivery_fee is zero/NULL.

Targets:
- fact_sales (unit + line economics)
- sales_fact_v2 (line economics)

Uses Master_Inventory_Rules_v8 formulas via core.calc.economics.
"""

import argparse
import sqlite3
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from datetime import date

from core.calc.economics import calc_cogs, calc_delivery_fee, calc_net_rev
from core.config.business_params import get_fx_rates
from core.db import DEFAULT_DB_PATH


def load_sku_meta(conn: sqlite3.Connection) -> dict[str, tuple[float, float]]:
    rows = conn.execute("""
        SELECT sku_key, base_cost_cny, weight_kg
        FROM dim_sku
    """).fetchall()
    return {
        row["sku_key"]: (
            float(row["base_cost_cny"] or 0),
            float(row["weight_kg"] or 0),
        )
        for row in rows
    }


def _coerce_date(value) -> date | None:
    if value is None:
        return None
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value))
    except ValueError:
        return None


def _calc_line(
    sell_price_kzt: float,
    base_cost_cny: float,
    weight_kg: float,
    quantity: int,
    order_date: date | None,
    fx_rates,
) -> dict:
    delivery_fee = calc_delivery_fee(sell_price_kzt, weight_kg=weight_kg, delivery_type="city")
    cogs_unit = calc_cogs(
        base_cost_cny,
        weight_kg,
        cny_kzt=fx_rates.cny_kzt,
        volumetric_factor=fx_rates.dlv_rate_usd_kg,
        freight_rate=fx_rates.usd_kzt,
    )
    net_rev_unit = calc_net_rev(
        sell_price_kzt,
        delivery_fee,
        weight_kg=weight_kg,
        delivery_type="city",
        as_of_date=order_date,
    )
    profit_unit = net_rev_unit - cogs_unit
    return {
        "delivery_fee": delivery_fee,
        "net_rev_unit": net_rev_unit,
        "line_net_rev": net_rev_unit * quantity,
        "cogs_unit": cogs_unit,
        "cogs_line": cogs_unit * quantity,
        "profit_unit": profit_unit,
        "profit_line": profit_unit * quantity,
    }


def backfill_fact_sales(conn: sqlite3.Connection, sku_meta: dict, fx_rates, dry_run: bool) -> int:
    rows = conn.execute("""
        SELECT id, order_date, sku_key, quantity, sell_price_kzt
        FROM fact_sales
        WHERE (delivery_fee IS NULL OR delivery_fee = 0)
          AND sell_price_kzt > 0
    """).fetchall()

    updated = 0
    for row in rows:
        sku_key = row["sku_key"]
        base_cost_cny, weight_kg = sku_meta.get(sku_key, (0.0, 0.0))
        order_date = _coerce_date(row["order_date"])
        values = _calc_line(
            sell_price_kzt=row["sell_price_kzt"],
            base_cost_cny=base_cost_cny,
            weight_kg=weight_kg,
            quantity=int(row["quantity"] or 0),
            order_date=order_date,
            fx_rates=fx_rates,
        )
        if dry_run:
            updated += 1
            continue
        conn.execute("""
            UPDATE fact_sales
            SET delivery_fee = ?,
                net_rev_unit = ?,
                line_net_rev = ?,
                cogs_unit = ?,
                cogs_line = ?,
                profit_unit = ?,
                profit_line = ?
            WHERE id = ?
        """, (
            values["delivery_fee"],
            values["net_rev_unit"],
            values["line_net_rev"],
            values["cogs_unit"],
            values["cogs_line"],
            values["profit_unit"],
            values["profit_line"],
            row["id"],
        ))
        updated += 1
    return updated


def backfill_sales_fact_v2(conn: sqlite3.Connection, sku_meta: dict, fx_rates, dry_run: bool) -> int:
    rows = conn.execute("""
        SELECT sale_id, order_date, sku_key, quantity, sell_price_kzt
        FROM sales_fact_v2
        WHERE (delivery_fee IS NULL OR delivery_fee = 0)
          AND sell_price_kzt > 0
    """).fetchall()

    updated = 0
    for row in rows:
        sku_key = row["sku_key"]
        base_cost_cny, weight_kg = sku_meta.get(sku_key, (0.0, 0.0))
        order_date = _coerce_date(row["order_date"])
        values = _calc_line(
            sell_price_kzt=row["sell_price_kzt"],
            base_cost_cny=base_cost_cny,
            weight_kg=weight_kg,
            quantity=int(row["quantity"] or 0),
            order_date=order_date,
            fx_rates=fx_rates,
        )
        if dry_run:
            updated += 1
            continue
        conn.execute("""
            UPDATE sales_fact_v2
            SET delivery_fee = ?,
                net_rev = ?,
                cogs = ?,
                profit = ?
            WHERE sale_id = ?
        """, (
            values["delivery_fee"],
            values["line_net_rev"],
            values["cogs_line"],
            values["profit_line"],
            row["sale_id"],
        ))
        updated += 1
    return updated


def main():
    parser = argparse.ArgumentParser(description="Backfill delivery fees using v8 formulas.")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB_PATH, help="Path to db/app.db")
    parser.add_argument("--dry-run", action="store_true", help="Preview changes without writing")
    args = parser.parse_args()

    db_path = args.db
    if not db_path.exists():
        raise SystemExit(f"DB not found: {db_path}")

    with sqlite3.connect(str(db_path)) as conn:
        conn.row_factory = sqlite3.Row
        sku_meta = load_sku_meta(conn)
        fx_rates = get_fx_rates()

        fact_sales_updated = backfill_fact_sales(conn, sku_meta, fx_rates, args.dry_run)
        sales_v2_updated = backfill_sales_fact_v2(conn, sku_meta, fx_rates, args.dry_run)

        if args.dry_run:
            conn.rollback()
        else:
            conn.commit()

    print("Backfill complete:")
    print(f"  fact_sales rows updated: {fact_sales_updated}")
    print(f"  sales_fact_v2 rows updated: {sales_v2_updated}")
    if args.dry_run:
        print("  [DRY RUN] No changes committed.")


if __name__ == "__main__":
    main()
