#!/usr/bin/env python3
"""
Normalize stock_ledger store_code to the canonical inventory pool.

Idempotent: only updates rows where store_code != UNIVERSAL.
"""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from core.db import get_db, DEFAULT_DB_PATH
from core.db.ledger import inventory_pool_store_code


def main() -> int:
    parser = argparse.ArgumentParser(description="Normalize ledger store_code to UNIVERSAL pool")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB_PATH, help="DB path")
    parser.add_argument("--apply", action="store_true", help="Apply updates (default: dry-run)")
    args = parser.parse_args()

    pool_code = inventory_pool_store_code()

    with get_db(args.db) as conn:
        rows = conn.execute(
            """
            SELECT store_code, COUNT(*) as cnt
            FROM stock_ledger
            WHERE store_code != ?
            GROUP BY store_code
            ORDER BY cnt DESC
            """,
            (pool_code,),
        ).fetchall()

        total = sum(r["cnt"] for r in rows)

        if args.apply and total > 0:
            conn.execute(
                "UPDATE stock_ledger SET store_code = ? WHERE store_code != ?",
                (pool_code, pool_code),
            )
            conn.commit()
        else:
            conn.rollback()

    print(f"Pool store_code: {pool_code}")
    print(f"Rows to normalize: {total}")
    for r in rows:
        print(f"  {r['store_code']}: {r['cnt']}")
    print(f"Mode: {'APPLY' if args.apply else 'DRY RUN'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
