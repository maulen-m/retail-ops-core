#!/usr/bin/env python3
"""
Create dim_size_synonyms table for size canonicalization.

Usage:
  python scripts/migrate_015_dim_size_synonyms.py
  python scripts/migrate_015_dim_size_synonyms.py --seed-defaults
"""

from __future__ import annotations

import argparse
from pathlib import Path

from core.db import get_db, DEFAULT_DB_PATH


DEFAULT_SYNONYMS = {
    "ONE SIZE": "ONE_SIZE",
    "ONESIZE": "ONE_SIZE",
    "OS": "ONE_SIZE",
    "O/S": "ONE_SIZE",
    "XXL": "2XL",
    "XXXL": "3XL",
    "XXXXL": "4XL",
    "2XLB": "2XL",
    "2XL\u0411": "2XL",
    "3XLB": "3XL",
    "3XL\u0411": "3XL",
    "4XLB": "4XL",
    "4XL\u0411": "4XL",
}


def _normalize_alias(value: str) -> str:
    return value.upper().replace(" ", "").replace("-", "")


def main() -> int:
    parser = argparse.ArgumentParser(description="Create dim_size_synonyms table")
    parser.add_argument(
        "--db",
        type=Path,
        default=DEFAULT_DB_PATH,
        help="DB path (default: db/app.db)",
    )
    parser.add_argument(
        "--seed-defaults",
        action="store_true",
        help="Insert default size synonym mappings",
    )
    args = parser.parse_args()

    with get_db(args.db) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS dim_size_synonyms (
                alias TEXT PRIMARY KEY,
                canonical_size TEXT NOT NULL,
                notes TEXT,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_dim_size_synonyms_canonical ON dim_size_synonyms(canonical_size)"
        )

        if args.seed_defaults:
            for alias, canonical in DEFAULT_SYNONYMS.items():
                conn.execute(
                    """
                    INSERT OR REPLACE INTO dim_size_synonyms (alias, canonical_size)
                    VALUES (?, ?)
                    """,
                    (_normalize_alias(alias), canonical),
                )

    print("dim_size_synonyms table ready.")
    if args.seed_defaults:
        print("Seeded default size synonym mappings.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
