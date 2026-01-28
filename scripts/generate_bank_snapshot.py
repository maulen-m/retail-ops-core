#!/usr/bin/env python3
"""Generate bank_accounts.yaml snapshot from bank_accounts_history.yaml.

Reads the latest entry from the append-only history file and generates
a formatted snapshot with computed totals by currency and store.

FX Rate Sources (priority order):
  1. binance_c2c_orders - latest actual USDT/KZT trade rate
  2. dim_fx_rates - canonical rates for USDT/KZT, USD/KZT, CNY/KZT
  3. Hardcoded defaults - RUB/KZT = 6.6 (from wb_economics)

Usage:
    python scripts/generate_bank_snapshot.py
    python scripts/generate_bank_snapshot.py --dry-run
    python scripts/generate_bank_snapshot.py --show-rates
"""

from __future__ import annotations

import argparse
import logging
import sys
from collections import defaultdict
from datetime import date, datetime
from pathlib import Path
from typing import Optional

import yaml

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from core.db import get_db, DEFAULT_DB_PATH

HISTORY_PATH = PROJECT_ROOT / "config" / "bank_accounts_history.yaml"
SNAPSHOT_PATH = PROJECT_ROOT / "config" / "bank_accounts.yaml"

# Default FX rates (fallback if DB has no data)
DEFAULT_FX_RATES = {
    "USDT_KZT": 510.0,
    "USD_KZT": 514.0,
    "RUB_KZT": 6.6,  # from core/calc/wb_economics.py
    "CNY_KZT": 75.0,
}


def setup_logging(verbose: bool = False) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s | %(levelname)s | %(message)s",
        datefmt="%H:%M:%S",
    )


def get_fx_rates(db_path: Path = DEFAULT_DB_PATH) -> dict[str, tuple[float, str, str]]:
    """
    Fetch FX rates from multiple sources.

    Returns dict: currency_pair -> (rate, source_name, effective_date)
    """
    rates: dict[str, tuple[float, str, str]] = {}

    # Start with defaults
    for pair, rate in DEFAULT_FX_RATES.items():
        rates[pair] = (rate, "default", "hardcoded")

    if not db_path.exists():
        logging.warning(f"Database not found: {db_path}, using defaults")
        return rates

    with get_db(db_path) as conn:
        # 1. dim_fx_rates - canonical rates
        try:
            row = conn.execute(
                """
                SELECT effective_date, usdt_kzt, usd_kzt, cny_kzt
                FROM dim_fx_rates
                ORDER BY effective_date DESC
                LIMIT 1
                """
            ).fetchone()
            if row:
                eff_date = row["effective_date"]
                rates["USDT_KZT"] = (row["usdt_kzt"], "dim_fx_rates", eff_date)
                rates["USD_KZT"] = (row["usd_kzt"], "dim_fx_rates", eff_date)
                rates["CNY_KZT"] = (row["cny_kzt"], "dim_fx_rates", eff_date)
                logging.debug(f"dim_fx_rates: USDT={row['usdt_kzt']}, USD={row['usd_kzt']}, CNY={row['cny_kzt']} ({eff_date})")
        except Exception as e:
            logging.warning(f"Failed to read dim_fx_rates: {e}")

        # 2. binance_c2c_orders - actual trade rates (higher priority for USDT)
        try:
            row = conn.execute(
                """
                SELECT create_time, unit_price, fiat
                FROM binance_c2c_orders
                WHERE asset = 'USDT' AND fiat = 'KZT'
                ORDER BY create_time DESC
                LIMIT 1
                """
            ).fetchone()
            if row:
                # Use Binance P2P rate if more recent than dim_fx_rates
                binance_date = row["create_time"][:10] if row["create_time"] else ""
                current_usdt_date = rates.get("USDT_KZT", (0, "", ""))[2]

                if binance_date >= current_usdt_date:
                    rates["USDT_KZT"] = (row["unit_price"], "binance_p2p", binance_date)
                    logging.debug(f"binance_p2p: USDT/KZT={row['unit_price']} ({binance_date})")
        except Exception as e:
            logging.debug(f"No binance_c2c_orders data: {e}")

    return rates


def load_history(path: Path = HISTORY_PATH) -> list[dict]:
    """Load all entries from history file."""
    if not path.exists():
        raise FileNotFoundError(f"History file not found: {path}")

    with open(path, "r") as f:
        data = yaml.safe_load(f)

    entries = data.get("entries", [])
    if not entries:
        raise ValueError("No entries found in history file")

    return entries


def get_latest_entry(entries: list[dict]) -> dict:
    """Get the most recent entry by as_of timestamp."""
    def parse_as_of(entry: dict) -> datetime:
        as_of = entry.get("as_of", "")
        # Parse formats like "2026-01-24 13:49:00 GMT+5"
        try:
            # Strip timezone suffix for parsing
            clean = as_of.replace(" GMT+5", "").replace(" GMT+0", "")
            return datetime.strptime(clean, "%Y-%m-%d %H:%M:%S")
        except ValueError:
            try:
                return datetime.strptime(as_of[:10], "%Y-%m-%d")
            except ValueError:
                return datetime.min

    return max(entries, key=parse_as_of)


def compute_totals(
    balances: list[dict],
    fx_rates: dict[str, tuple[float, str, str]],
) -> tuple[dict[str, float], dict[str, dict[str, float]], float]:
    """
    Compute totals by currency and by store.

    Returns:
        - by_currency: {currency: total_amount}
        - by_store: {store: {currency: amount}}
        - total_kzt: grand total in KZT
    """
    by_currency: dict[str, float] = defaultdict(float)
    by_store: dict[str, dict[str, float]] = defaultdict(lambda: defaultdict(float))

    for bal in balances:
        store = bal["store"]
        currency = bal["currency"]
        amount = bal["amount"]

        by_currency[currency] += amount
        by_store[store][currency] += amount

    # Compute KZT equivalent
    total_kzt = 0.0
    for currency, amount in by_currency.items():
        if currency == "KZT":
            total_kzt += amount
        else:
            rate_key = f"{currency}_KZT"
            rate = fx_rates.get(rate_key, (1.0, "", ""))[0]
            total_kzt += amount * rate

    return dict(by_currency), dict(by_store), total_kzt


def format_currency_table(
    by_currency: dict[str, float],
    fx_rates: dict[str, tuple[float, str, str]],
) -> list[str]:
    """Format the currency totals table."""
    lines = []
    lines.append("#   | Currency | Amount    | Rate | KZT Equivalent |")
    lines.append("#   |----------|-----------|------|----------------|")

    total_kzt = 0.0
    # Order: KZT first, then others alphabetically
    currencies = ["KZT"] + sorted(c for c in by_currency if c != "KZT")

    for currency in currencies:
        amount = by_currency.get(currency, 0)
        if currency == "KZT":
            rate = 1
            kzt_equiv = amount
        else:
            rate_key = f"{currency}_KZT"
            rate = fx_rates.get(rate_key, (1.0, "", ""))[0]
            kzt_equiv = amount * rate

        total_kzt += kzt_equiv

        # Format numbers
        if amount == int(amount):
            amt_str = f"{int(amount):,}".replace(",", ",")
        else:
            amt_str = f"{amount:,.2f}".replace(",", ",")

        rate_str = str(int(rate)) if rate == int(rate) else f"{rate}"
        kzt_str = f"{int(round(kzt_equiv)):,}".replace(",", ",")

        lines.append(f"#   | {currency:<8} | {amt_str:>9} | {rate_str:>4} | {kzt_str:>14} |")

    # Total row
    total_str = f"{int(round(total_kzt)):,}".replace(",", ",")
    lines.append(f"#   | {'Total':<8} |{' ':>10} |{' ':>5} | {total_str:>10} KZT |")

    return lines


def format_store_summary(by_store: dict[str, dict[str, float]]) -> list[str]:
    """Format the by-store summary."""
    lines = []
    store_order = ["UNIVERSAL", "11KZ", "STOREB", "ACMEWEAR", "MELVIS"]

    for store in store_order:
        if store not in by_store:
            continue
        currencies = by_store[store]
        parts = []
        # KZT first
        if "KZT" in currencies:
            amt = currencies["KZT"]
            parts.append(f"{int(amt):,} KZT".replace(",", ","))
        # Others
        for cur in sorted(c for c in currencies if c != "KZT"):
            amt = currencies[cur]
            if amt == int(amt):
                parts.append(f"{int(amt):,} {cur}".replace(",", ","))
            else:
                parts.append(f"{amt:,.2f} {cur}".replace(",", ","))

        lines.append(f"#   - {store}: {' + '.join(parts)}")

    return lines


def generate_snapshot(
    entry: dict,
    fx_rates: dict[str, tuple[float, str, str]],
) -> str:
    """Generate the full snapshot YAML content."""
    as_of = entry["as_of"]
    source = entry.get("source", "unknown")
    balances = entry["balances"]

    by_currency, by_store, total_kzt = compute_totals(balances, fx_rates)

    # Build FX source string
    fx_sources = set()
    for pair, (rate, src, eff_date) in fx_rates.items():
        if src != "default" and any(c in pair for c in by_currency if c != "KZT"):
            fx_sources.add(f"{src} {eff_date}")
    fx_source_str = " + ".join(sorted(fx_sources)) if fx_sources else "defaults"

    # Extract date from as_of
    as_of_date = as_of.split()[0] if " " in as_of else as_of

    lines = []
    lines.append("## Cash balances by store/account (manual snapshot).")
    lines.append("## Store codes mirror config/kaspi_pay_accounts.yaml.")
    lines.append("## Amounts are raw balances in account currency.")
    lines.append("")
    lines.append("# " + "=" * 78)
    lines.append(f"# TOTALS (as of {as_of_date})")
    lines.append("# " + "=" * 78)
    lines.append("#")
    lines.append(f"# By Currency (FX rates from {fx_source_str}):")
    lines.extend(format_currency_table(by_currency, fx_rates))
    lines.append("#")
    lines.append("# By Store:")
    lines.extend(format_store_summary(by_store))
    lines.append("#")
    lines.append("# " + "=" * 78)
    lines.append("")
    lines.append(f"as_of: {as_of}")
    lines.append("stores:")

    # Group balances by store
    store_accounts: dict[str, list[dict]] = defaultdict(list)
    for bal in balances:
        store_accounts[bal["store"]].append(bal)

    store_order = ["UNIVERSAL", "11KZ", "STOREB", "ACMEWEAR", "MELVIS"]
    for store in store_order:
        if store not in store_accounts:
            continue

        if store == "11KZ":
            lines.append(f'  "{store}":')
        else:
            lines.append(f"  {store}:")
        lines.append("    accounts:")

        for bal in store_accounts[store]:
            account = bal["account"]
            amount = bal["amount"]
            currency = bal["currency"].lower()

            lines.append(f"      {account}:")
            if amount == int(amount):
                lines.append(f"        balance_{currency}: {int(amount)}")
            else:
                lines.append(f"        balance_{currency}: {amount}")

    lines.append("")
    return "\n".join(lines)


def show_rates(db_path: Path = DEFAULT_DB_PATH) -> None:
    """Display current FX rates from all sources."""
    rates = get_fx_rates(db_path)
    print("Current FX Rates:")
    print("-" * 50)
    for pair in sorted(rates.keys()):
        rate, source, eff_date = rates[pair]
        print(f"  {pair}: {rate} ({source}, {eff_date})")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Generate bank_accounts.yaml from history file",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("--db", type=Path, default=DEFAULT_DB_PATH, help="Path to SQLite DB")
    parser.add_argument("--history", type=Path, default=HISTORY_PATH, help="Path to history YAML")
    parser.add_argument("--output", type=Path, default=SNAPSHOT_PATH, help="Output snapshot path")
    parser.add_argument("--dry-run", action="store_true", help="Print output without writing")
    parser.add_argument("--show-rates", action="store_true", help="Show FX rates and exit")
    parser.add_argument("--verbose", "-v", action="store_true", help="Verbose logging")
    args = parser.parse_args()

    setup_logging(args.verbose)

    if args.show_rates:
        show_rates(args.db)
        return 0

    try:
        # Load history and get latest entry
        entries = load_history(args.history)
        latest = get_latest_entry(entries)
        logging.info(f"Latest entry: {latest['as_of']}")

        # Get FX rates
        fx_rates = get_fx_rates(args.db)

        # Generate snapshot
        content = generate_snapshot(latest, fx_rates)

        if args.dry_run:
            print("=" * 60)
            print("DRY RUN - would write to:", args.output)
            print("=" * 60)
            print(content)
            return 0

        # Write output
        with open(args.output, "w") as f:
            f.write(content)

        logging.info(f"Wrote snapshot to {args.output}")
        return 0

    except Exception as e:
        logging.error(f"Failed: {e}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
