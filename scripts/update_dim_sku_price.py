#!/usr/bin/env python3
"""
Update dim_sku average sell price (single source of truth).

Usage:
  python3 scripts/update_dim_sku_price.py --sku-key CL_NEW-CLO2_MEN_SUIT-61_BLACK --price-kzt 12990 --apply
"""

from __future__ import annotations

import argparse
from pathlib import Path

import sys

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from core.db import DEFAULT_DB_PATH, get_db
from core.db.ledger import log_audit


def main() -> int:
    parser = argparse.ArgumentParser(description="Update dim_sku avg_sell_price_kzt_used")
    parser.add_argument("--sku-key", required=True, help="SKU key to update")
    parser.add_argument("--price-kzt", required=True, type=float, help="New price in KZT")
    parser.add_argument("--source", default="MANUAL", help="Source label (default: MANUAL)")
    parser.add_argument("--db", default=str(DEFAULT_DB_PATH), help="DB path (default: db/app.db)")
    parser.add_argument("--apply", action="store_true", help="Apply change (default: dry-run)")
    args = parser.parse_args()

    db_path = Path(args.db)
    if not db_path.is_absolute():
        db_path = PROJECT_ROOT / db_path

    audit_payload = None
    with get_db(db_path) as conn:
        row = conn.execute(
            "SELECT avg_sell_price_kzt_used, avg_sell_price_source FROM dim_sku WHERE sku_key = ?",
            (args.sku_key,),
        ).fetchone()
        if not row:
            print(f"ERROR: sku_key not found: {args.sku_key}")
            return 1

        old_price = row["avg_sell_price_kzt_used"]
        old_source = row["avg_sell_price_source"]
        new_price = float(args.price_kzt)

        if not args.apply:
            print("[DRY RUN] Would update dim_sku:")
            print(f"  sku_key={args.sku_key}")
            print(f"  avg_sell_price_kzt_used: {old_price} -> {new_price}")
            print(f"  avg_sell_price_source: {old_source} -> {args.source}")
            return 0

        if old_price == new_price and old_source == args.source:
            print("No change required.")
            return 0

        conn.execute(
            """
            UPDATE dim_sku
               SET avg_sell_price_kzt_used = ?,
                   avg_sell_price_source = ?,
                   price_missing_flag = 0,
                   updated_at = datetime('now')
             WHERE sku_key = ?
            """,
            (new_price, args.source, args.sku_key),
        )
        audit_payload = {
            "table_name": "dim_sku",
            "record_id": args.sku_key,
            "field_name": "avg_sell_price_kzt_used",
            "old_value": old_price,
            "new_value": new_price,
            "change_type": "UPDATE",
            "reason": "Manual price update",
            "source": args.source,
        }

        print("Updated dim_sku price:")
        print(f"  sku_key={args.sku_key}")
        print(f"  avg_sell_price_kzt_used: {old_price} -> {new_price}")
        print(f"  avg_sell_price_source: {old_source} -> {args.source}")

    if audit_payload:
        log_audit(db_path=db_path, **audit_payload)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
