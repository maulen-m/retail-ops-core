#!/usr/bin/env python3
"""Upsert daily FX rates into SQLite (dim_fx_rates).

Why this exists
--------------
Project 3 pays suppliers via a real-world funding path:

    KZT -> USDT (Binance P2P) -> CNY (exchanger/BestChange) -> WeChat

So our canonical *internal* daily FX row needs to support:
  - Supplier costing in **CNY/KZT** (derived from the USDT legs)
  - Freight costing in **USD/KZT**
  - A future upgrade path to API-based syncing (without changing consumers)

This script is intentionally:
  - **Idempotent** (safe to run multiple times per day)
  - **Explicit** (no silent migrations during validation)
  - **Fail-fast** on obviously wrong inputs

Usage examples
--------------

Seed today's rates (Asia/Almaty date):

    python scripts/upsert_fx_rates.py \
      --usdt-kzt 510 \
      --usdt-cny 6.813 \
      --usd-kzt 514 \
      --dlv-rate-usd-kg 2.66 \
      --provider MANUAL \
      --source "Binance P2P (median-bottom) + BestChange + Google"

Backfill a prior date:

    python scripts/upsert_fx_rates.py \
      --effective-date 2025-12-26 \
      --usdt-kzt 508 \
      --usdt-cny 6.80 \
      --usd-kzt 512 \
      --dlv-rate-usd-kg 2.66
"""

from __future__ import annotations

import argparse
import logging
import sys
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Iterable, Optional


# Add project root to path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from core.db import get_db  # noqa: E402


DB_PATH = PROJECT_ROOT / "db" / "app.db"


def _today_almaty() -> date:
    """Return today's date in Asia/Almaty timezone."""
    import zoneinfo

    tz = zoneinfo.ZoneInfo("Asia/Almaty")
    return datetime.now(tz).date()


@dataclass(frozen=True)
class FxInput:
    effective_date: date
    usdt_kzt: float
    usdt_cny: float
    usd_kzt: float
    dlv_rate_usd_kg: float
    cny_kzt: float
    provider: str
    source: str


def setup_logging(verbose: bool = False) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s | %(levelname)s | %(message)s",
        datefmt="%H:%M:%S",
    )


def parse_date(value: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError as e:
        raise argparse.ArgumentTypeError(
            f"Invalid date '{value}'. Use YYYY-MM-DD."
        ) from e


def _ensure_dim_fx_rates_schema(conn) -> None:
    """Ensure dim_fx_rates exists and has required columns.

    This function is *explicitly* called by the upsert script (manual action),
    not during validation. It's safe to re-run.
    """
    # Create table if missing (fresh DB)
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS dim_fx_rates (
            effective_date TEXT PRIMARY KEY,
            usdt_kzt REAL NOT NULL,
            usdt_cny REAL NOT NULL,
            cny_kzt REAL NOT NULL,
            usd_kzt REAL NOT NULL,
            dlv_rate_usd_kg REAL NOT NULL,
            provider TEXT NOT NULL DEFAULT 'MANUAL',
            source TEXT,
            updated_at TEXT DEFAULT (datetime('now'))
        )
        """
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_fx_rates_effective ON dim_fx_rates(effective_date DESC)"
    )
    # Backwards-compatible schema drift handling (older DBs from Part 3)
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
        # SQLite can only ADD COLUMN (no NOT NULL enforcement retroactively).
        # We allow NULLs for legacy rows; validation requires a usable row <= run_date.
        logging.info(f"Schema drift: adding missing column dim_fx_rates.{col}")
        conn.execute(f"ALTER TABLE dim_fx_rates ADD COLUMN {col} {col_type}")


def _validate_positive(name: str, value: float) -> None:
    if value <= 0:
        raise ValueError(f"{name} must be > 0 (got {value})")


def _range_check(
    name: str,
    value: float,
    lo: float,
    hi: float,
    force: bool,
) -> None:
    """Guardrail against typos.

    We fail fast unless --force is provided, because a single misplaced digit
    can destroy downstream unit economics.
    """
    if lo <= value <= hi:
        return
    msg = f"{name}={value} is outside expected range [{lo}, {hi}]"
    if force:
        logging.warning(f"FORCED: {msg}")
        return
    raise ValueError(msg + "; re-run with --force if intentional")


def build_fx_input(
    effective_date: date,
    usdt_kzt: float,
    usdt_cny: float,
    usd_kzt: float,
    dlv_rate_usd_kg: float,
    cny_kzt: Optional[float],
    provider: str,
    source: str,
    force: bool,
) -> FxInput:
    # Basic positivity
    _validate_positive("usdt_kzt", usdt_kzt)
    _validate_positive("usdt_cny", usdt_cny)
    _validate_positive("usd_kzt", usd_kzt)
    _validate_positive("dlv_rate_usd_kg", dlv_rate_usd_kg)
    # Plausibility ranges (wide enough to avoid false positives)
    _range_check("usdt_kzt", usdt_kzt, lo=200, hi=2000, force=force)
    _range_check("usdt_cny", usdt_cny, lo=3, hi=20, force=force)
    _range_check("usd_kzt", usd_kzt, lo=200, hi=2000, force=force)
    _range_check("dlv_rate_usd_kg", dlv_rate_usd_kg, lo=0.2, hi=20, force=force)
    derived_cny_kzt = usdt_kzt / usdt_cny
    if cny_kzt is None:
        cny_kzt_final = derived_cny_kzt
    else:
        _validate_positive("cny_kzt", cny_kzt)
        # Consistency check: if provided, it should match derived within 1%.
        if derived_cny_kzt == 0:
            raise ValueError("Derived cny_kzt is zero (unexpected)")
        diff_pct = abs(cny_kzt - derived_cny_kzt) / derived_cny_kzt
        if diff_pct > 0.01 and not force:
            raise ValueError(
                "cny_kzt does not match usdt_kzt/usdt_cny within 1%. "
                f"Provided={cny_kzt:.4f}, Derived={derived_cny_kzt:.4f} ({diff_pct*100:.2f}% diff). "
                "Fix inputs or pass --force to accept."
            )
        cny_kzt_final = cny_kzt
    _range_check("cny_kzt", cny_kzt_final, lo=10, hi=500, force=force)
    if not provider.strip():
        raise ValueError("provider must be non-empty")
    return FxInput(
        effective_date=effective_date,
        usdt_kzt=usdt_kzt,
        usdt_cny=usdt_cny,
        usd_kzt=usd_kzt,
        dlv_rate_usd_kg=dlv_rate_usd_kg,
        cny_kzt=cny_kzt_final,
        provider=provider.strip(),
        source=source.strip(),
    )


def upsert_fx_rates(fx: FxInput, db_path: Path = DB_PATH, dry_run: bool = False) -> None:
    if not db_path.exists():
        raise FileNotFoundError(
            f"Database not found: {db_path}\n"
            "Create it first with: python scripts/bootstrap_db.py"
        )
    with get_db(db_path) as conn:
        _ensure_dim_fx_rates_schema(conn)
        if dry_run:
            logging.info("DRY RUN: would upsert dim_fx_rates row:")
            logging.info(f"  effective_date={fx.effective_date.isoformat()}")
            logging.info(f"  usdt_kzt={fx.usdt_kzt}")
            logging.info(f"  usdt_cny={fx.usdt_cny}")
            logging.info(f"  cny_kzt={fx.cny_kzt:.6f}")
            logging.info(f"  usd_kzt={fx.usd_kzt}")
            logging.info(f"  dlv_rate_usd_kg={fx.dlv_rate_usd_kg}")
            logging.info(f"  provider={fx.provider}")
            logging.info(f"  source={fx.source}")
            return
        conn.execute(
            """
            INSERT OR REPLACE INTO dim_fx_rates (
                effective_date,
                usdt_kzt,
                usdt_cny,
                cny_kzt,
                usd_kzt,
                dlv_rate_usd_kg,
                provider,
                source,
                updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))
            """,
            (
                fx.effective_date.isoformat(),
                fx.usdt_kzt,
                fx.usdt_cny,
                fx.cny_kzt,
                fx.usd_kzt,
                fx.dlv_rate_usd_kg,
                fx.provider,
                fx.source,
            ),
        )
        logging.info("✅ Upserted dim_fx_rates")
        logging.info(
            "  "
            f"{fx.effective_date.isoformat()} | "
            f"USDT/KZT={fx.usdt_kzt:.2f} | "
            f"USDT/CNY={fx.usdt_cny:.4f} | "
            f"CNY/KZT={fx.cny_kzt:.4f} | "
            f"USD/KZT={fx.usd_kzt:.2f} | "
            f"DLV_USD_KG={fx.dlv_rate_usd_kg:.4f}"
        )


def show_latest(db_path: Path = DB_PATH) -> None:
    if not db_path.exists():
        raise FileNotFoundError(f"Database not found: {db_path}")
    with get_db(db_path) as conn:
        cursor = conn.execute(
            """
            SELECT
                effective_date, usdt_kzt, usdt_cny, cny_kzt, usd_kzt,
                dlv_rate_usd_kg, provider, source, updated_at
            FROM dim_fx_rates
            ORDER BY effective_date DESC
            LIMIT 5
            """
        )
        rows = cursor.fetchall()
        if not rows:
            print("No dim_fx_rates rows found.")
            return
        print("Latest FX rates (top 5):")
        for r in rows:
            print(
                f"  {r['effective_date']} | "
                f"USDT/KZT={r['usdt_kzt']} | "
                f"USDT/CNY={r['usdt_cny']} | "
                f"CNY/KZT={r['cny_kzt']} | "
                f"USD/KZT={r['usd_kzt']} | "
                f"DLV_USD_KG={r['dlv_rate_usd_kg']} | "
                f"provider={r['provider']}"
            )


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Upsert daily FX rates into dim_fx_rates",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("--db", type=Path, default=DB_PATH, help="Path to SQLite DB")
    parser.add_argument(
        "--effective-date",
        type=parse_date,
        default=None,
        help="FX effective date (YYYY-MM-DD). Defaults to today in Asia/Almaty.",
    )
    parser.add_argument("--usdt-kzt", type=float, required=False, help="KZT per 1 USDT")
    parser.add_argument("--usdt-cny", type=float, required=False, help="CNY per 1 USDT")
    parser.add_argument(
        "--cny-kzt",
        type=float,
        required=False,
        help="Optional KZT per 1 CNY. If omitted, derived as usdt_kzt/usdt_cny.",
    )
    parser.add_argument("--usd-kzt", type=float, required=False, help="KZT per 1 USD")
    parser.add_argument(
        "--dlv-rate-usd-kg",
        type=float,
        required=False,
        help="Delivery rate (USD per kg)",
    )
    parser.add_argument("--provider", type=str, default="MANUAL", help="Rate provider label")
    parser.add_argument("--source", type=str, default="", help="Free-text provenance")
    parser.add_argument("--dry-run", action="store_true", help="Validate only; do not write")
    parser.add_argument(
        "--show-latest",
        action="store_true",
        help="Print latest dim_fx_rates rows and exit",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Allow out-of-range or inconsistent inputs (dangerous; logged)",
    )
    parser.add_argument("--verbose", "-v", action="store_true", help="Verbose logging")
    args = parser.parse_args()
    setup_logging(args.verbose)
    if args.show_latest:
        show_latest(args.db)
        return 0
    # Required rates for an upsert
    missing = [
        name
        for name, val in [
            ("--usdt-kzt", args.usdt_kzt),
            ("--usdt-cny", args.usdt_cny),
            ("--usd-kzt", args.usd_kzt),
            ("--dlv-rate-usd-kg", args.dlv_rate_usd_kg),
        ]
        if val is None
    ]
    if missing:
        parser.error("Missing required args: " + ", ".join(missing))
    eff = args.effective_date or _today_almaty()
    fx = build_fx_input(
        effective_date=eff,
        usdt_kzt=float(args.usdt_kzt),
        usdt_cny=float(args.usdt_cny),
        usd_kzt=float(args.usd_kzt),
        dlv_rate_usd_kg=float(args.dlv_rate_usd_kg),
        cny_kzt=args.cny_kzt,
        provider=args.provider,
        source=args.source,
        force=args.force,
    )
    upsert_fx_rates(fx, db_path=args.db, dry_run=args.dry_run)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
