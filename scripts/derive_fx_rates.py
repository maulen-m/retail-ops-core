#!/usr/bin/env python3
"""Derive and upsert FX rates from Binance P2P and exchanger emails."""

from __future__ import annotations

import argparse
from datetime import date
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from core.db import get_db  # noqa: E402
from core.transfer_ledger.fx_derive import derive_daily_fx_rows  # noqa: E402


DB_PATH = PROJECT_ROOT / "db" / "app.db"


def _parse_date(value: str) -> date:
    return date.fromisoformat(value)


def _ensure_dim_fx_rates_schema(conn) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS dim_fx_rates (
            effective_date TEXT PRIMARY KEY,
            usdt_kzt REAL NOT NULL,
            usdt_cny REAL NOT NULL,
            cny_kzt REAL NOT NULL,
            usd_kzt REAL NOT NULL,
            dlv_rate_usd_kg REAL NOT NULL,
            provider TEXT NOT NULL DEFAULT 'AUTO',
            source TEXT,
            updated_at TEXT DEFAULT (datetime('now'))
        )
        """
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_fx_rates_effective ON dim_fx_rates(effective_date DESC)"
    )
    cols = [row[1] for row in conn.execute("PRAGMA table_info('dim_fx_rates')").fetchall()]
    required_cols = {
        "effective_date": "TEXT",
        "usdt_kzt": "REAL",
        "usdt_cny": "REAL",
        "cny_kzt": "REAL",
        "usd_kzt": "REAL",
        "dlv_rate_usd_kg": "REAL",
        "provider": "TEXT",
        "source": "TEXT",
        "updated_at": "TEXT",
    }
    for col, col_type in required_cols.items():
        if col in cols:
            continue
        conn.execute(f"ALTER TABLE dim_fx_rates ADD COLUMN {col} {col_type}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Derive and upsert FX rates")
    parser.add_argument("--db", type=Path, default=DB_PATH, help="Path to SQLite DB")
    parser.add_argument("--start-date", type=_parse_date, default=None, help="YYYY-MM-DD")
    parser.add_argument("--end-date", type=_parse_date, default=None, help="YYYY-MM-DD")
    parser.add_argument("--min-count", type=int, default=1, help="Minimum orders per day")
    parser.add_argument("--statuses", default="COMPLETED", help="Comma-separated exchanger statuses")
    parser.add_argument("--dry-run", action="store_true", help="Print derived rows without upsert")
    args = parser.parse_args()

    statuses = [s.strip().upper() for s in args.statuses.split(",") if s.strip()]

    rows = derive_daily_fx_rows(
        db_path=args.db,
        start_date=args.start_date,
        end_date=args.end_date,
        min_count=args.min_count,
        include_statuses=statuses,
    )

    if not rows:
        print("No FX rows derived (need both P2P USDT/KZT and exchanger USDT/CNY).")
        return 1

    if args.dry_run:
        print("Derived FX rows:")
        for row in rows:
            print(row)
        return 0

    with get_db(args.db) as conn:
        _ensure_dim_fx_rates_schema(conn)
        for row in rows:
            conn.execute(
                """
                INSERT OR REPLACE INTO dim_fx_rates (
                    effective_date, usdt_kzt, usdt_cny, cny_kzt,
                    usd_kzt, dlv_rate_usd_kg, provider, source, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))
                """,
                (
                    row["effective_date"],
                    row["usdt_kzt"],
                    row["usdt_cny"],
                    row["cny_kzt"],
                    row["usd_kzt"],
                    row["dlv_rate_usd_kg"],
                    row["provider"],
                    row["source"],
                ),
            )

    print(f"Upserted {len(rows)} FX rows into dim_fx_rates.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
