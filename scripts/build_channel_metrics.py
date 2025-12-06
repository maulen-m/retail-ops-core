#!/usr/bin/env python3
"""
Build daily channel metrics from fact_sales.

Usage:
    python scripts/build_channel_metrics.py [--date 2025-12-06]
    python scripts/build_channel_metrics.py --backfill --days 30
"""
import argparse
import logging
import sys
from pathlib import Path
from datetime import date, timedelta

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from core.calc.channel_metrics import (  # noqa: E402
    calc_channel_metrics_for_date,
    save_channel_metrics,
)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

DB_PATH = Path(__file__).parent.parent / "db" / "app.db"


def build_for_date(target_date: date) -> int:
    """Build channel metrics for a single date."""
    logger.info(f"Building channel metrics for {target_date}...")

    metrics = calc_channel_metrics_for_date(DB_PATH, target_date)

    if metrics:
        saved = save_channel_metrics(DB_PATH, metrics)
        logger.info(f"  Saved {saved} SKU-channel metrics")
        return saved
    else:
        logger.info(f"  No sales data for {target_date}")
        return 0


def backfill(days: int) -> int:
    """Backfill metrics for the last N days."""
    end_date = date.today()
    start_date = end_date - timedelta(days=days)

    logger.info(f"Backfilling channel metrics from {start_date} to {end_date}")

    total = 0
    current = start_date
    while current <= end_date:
        count = build_for_date(current)
        total += count
        current += timedelta(days=1)

    logger.info(f"Total metrics saved: {total}")
    return total


def main():
    parser = argparse.ArgumentParser(
        description="Build channel metrics",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    # Build for today
    python scripts/build_channel_metrics.py

    # Build for specific date
    python scripts/build_channel_metrics.py --date 2025-12-01

    # Backfill last 30 days
    python scripts/build_channel_metrics.py --backfill --days 30
        """,
    )
    parser.add_argument(
        "--date",
        type=str,
        help="Specific date (YYYY-MM-DD)",
    )
    parser.add_argument(
        "--backfill",
        action="store_true",
        help="Backfill historical data",
    )
    parser.add_argument(
        "--days",
        type=int,
        default=30,
        help="Days to backfill (default: 30)",
    )

    args = parser.parse_args()

    print()
    print("=" * 60)
    print("CHANNEL METRICS BUILD")
    print("=" * 60)

    if args.backfill:
        total = backfill(args.days)
        print(f"\nBackfill complete: {total} metrics saved")
    elif args.date:
        target = date.fromisoformat(args.date)
        count = build_for_date(target)
        print(f"\nBuild complete: {count} metrics saved")
    else:
        count = build_for_date(date.today())
        print(f"\nBuild complete: {count} metrics saved")


if __name__ == "__main__":
    main()
