#!/usr/bin/env python3
"""
Sync Kaspi Orders CLI (Phase 9.5 - TASK-123).

Synchronizes orders between Kaspi API and local database.

Usage:
    # Sync single store (Universal - test store)
    python scripts/sync_kaspi_orders.py --store UNIVERSAL

    # Sync all stores
    python scripts/sync_kaspi_orders.py --all

    # Sync with date range
    python scripts/sync_kaspi_orders.py --store UNIVERSAL --since 2025-12-01

    # Sync specific states only
    python scripts/sync_kaspi_orders.py --store UNIVERSAL --states NEW,ACCEPTED_BY_MERCHANT

    # Dry run (fetch but don't save)
    python scripts/sync_kaspi_orders.py --store UNIVERSAL --dry-run

    # Show current stats
    python scripts/sync_kaspi_orders.py --stats

Environment Variables:
    KASPI_TOKEN_UNIVERSAL, KASPI_TOKEN_ACMEWEAR, etc.
    ENABLE_KASPI_WRITE (not needed for sync - read only)
"""

import argparse
import logging
import os
import sys
from datetime import datetime, timedelta, date
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
load_dotenv()

from core.sync.order_sync_engine import OrderSyncEngine, SyncResult, MultiSyncResult
from core.sync.kaspi_order_enrichment import enrich_orders, _load_config as _load_enrichment_config


def setup_logging(verbose: bool = False):
    """Configure logging."""
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format='%(asctime)s | %(levelname)s | %(message)s',
        datefmt='%H:%M:%S',
    )


def print_sync_result(result: SyncResult):
    """Print single store sync result."""
    status = "OK" if result.success else "FAILED"
    print(f"\n  Store: {result.store_code}")
    print(f"  Status: {status}")
    print(f"  Orders fetched: {result.orders_fetched}")
    print(f"  Orders inserted: {result.orders_inserted}")
    print(f"  Orders updated: {result.orders_updated}")
    print(f"  Status changes: {len(result.status_changes)}")
    print(f"  Duration: {result.duration_sec:.1f}s")

    if result.status_changes:
        print("\n  Status Changes:")
        for change in result.status_changes[:10]:  # Show first 10
            print(f"    {change.order_id}: {change.old_status} -> {change.new_status}")
        if len(result.status_changes) > 10:
            print(f"    ... and {len(result.status_changes) - 10} more")

    if result.errors:
        print("\n  Errors:")
        for error in result.errors:
            print(f"    - {error}")





def _run_enrichment(
    stores,
    since,
    until,
    dry_run,
    require_complete=False,
    db_path=None,
):
    if dry_run:
        return []
    cfg_path = Path(__file__).parent.parent / "config" / "kaspi_enrichment.yaml"
    cfg = _load_enrichment_config(cfg_path)
    if not cfg.get("enabled"):
        if require_complete:
            raise RuntimeError("strict Kaspi entry enrichment is disabled in config")
        print("Enrichment disabled in config; skipping.")
        return []
    if os.environ.get("ENABLE_KASPI_ENRICHMENT") != "1":
        if require_complete:
            raise RuntimeError("ENABLE_KASPI_ENRICHMENT=1 is required for strict enrichment")
        print("ENABLE_KASPI_ENRICHMENT not set; skipping enrichment.")
        return []
    lookback_days = int(cfg.get("default_lookback_days") or 0) or 7
    resolved_since = since or (date.today() - timedelta(days=lookback_days - 1)).isoformat()
    resolved_until = until or date.today().isoformat()
    reports = []
    for store in stores:
        reports.append(enrich_orders(
            db_path=Path(db_path) if db_path is not None else Path(__file__).parent.parent / "db" / "app.db",
            store_code=store,
            since=resolved_since,
            until=resolved_until,
            apply=True,
            require_complete=require_complete,
            config_path=cfg_path,
        ))
    return reports


def print_multi_result(result: MultiSyncResult):
    """Print multi-store sync result."""
    print(f"\n{'=' * 60}")
    print("MULTI-STORE SYNC RESULTS")
    print(f"{'=' * 60}")

    print(f"\nSummary:")
    print(f"  Stores synced: {len(result.store_results)}")
    print(f"  Total orders fetched: {result.total_orders_fetched}")
    print(f"  Total orders inserted: {result.total_orders_inserted}")
    print(f"  Total orders updated: {result.total_orders_updated}")
    print(f"  Total duration: {result.duration_sec:.1f}s")

    if result.errors:
        print(f"\n  Errors ({len(result.errors)}):")
        for error in result.errors:
            print(f"    - {error}")

    print("\nPer-Store Results:")
    for store_code, store_result in result.store_results.items():
        status = "OK" if store_result.success else "FAILED"
        print(
            f"  {store_code}: {status} | "
            f"fetched={store_result.orders_fetched}, "
            f"inserted={store_result.orders_inserted}, "
            f"updated={store_result.orders_updated}"
        )


def print_stats(engine: OrderSyncEngine):
    """Print current sync statistics."""
    stats = engine.get_sync_stats()

    print(f"\n{'=' * 60}")
    print("KASPI ORDER SYNC STATISTICS")
    print(f"{'=' * 60}")

    print(f"\nTotal orders in database: {stats['total']}")
    print(f"Recent (24h): {stats['recent_24h']}")

    print("\nBy Status:")
    for status, count in sorted(stats['by_status'].items()):
        print(f"  {status}: {count}")

    print("\nBy Store:")
    for store, count in sorted(stats['by_store'].items()):
        print(f"  {store}: {count}")

    # Show pending orders
    print("\nPending Orders (NEW status):")
    pending = engine.get_pending_orders(status='NEW')
    if pending:
        for order in pending[:10]:
            print(f"  {order['order_id']} | {order['store_code']} | {order['created_at']}")
        if len(pending) > 10:
            print(f"  ... and {len(pending) - 10} more")
    else:
        print("  No pending orders")

    # Show ready for shipment
    print("\nReady for Shipment:")
    ready = engine.get_ready_for_shipment()
    if ready:
        for order in ready[:10]:
            has_waybill = "YES" if order.get('waybill_url') else "NO"
            print(
                f"  {order['order_id']} | {order['store_code']} | "
                f"waybill={has_waybill}"
            )
        if len(ready) > 10:
            print(f"  ... and {len(ready) - 10} more")
    else:
        print("  No orders ready for shipment")


def main():
    parser = argparse.ArgumentParser(
        description="Sync Kaspi orders from API to database",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    # Sync mode
    mode_group = parser.add_mutually_exclusive_group()
    mode_group.add_argument(
        '--store',
        type=str,
        help='Sync specific store (UNIVERSAL, ACMEWEAR, 11KZ, MELVIS, STOREB)',
    )
    mode_group.add_argument(
        '--all',
        action='store_true',
        help='Sync all configured stores',
    )
    mode_group.add_argument(
        '--stats',
        action='store_true',
        help='Show current sync statistics',
    )

    # Filters
    parser.add_argument(
        '--since',
        type=str,
        help='Sync orders since this date (YYYY-MM-DD)',
    )
    parser.add_argument(
        '--until',
        type=str,
        help='Sync orders until this date (YYYY-MM-DD)',
    )
    parser.add_argument(
        '--db-path',
        type=Path,
        help='SQLite DB path. Defaults to db/app.db.',
    )
    parser.add_argument(
        '--states',
        type=str,
        help='Comma-separated list of states (NEW,ACCEPTED_BY_MERCHANT,...)',
    )

    # Options
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Fetch orders but do not save to database',
    )
    parser.add_argument(
        '--enrich',
        action='store_true',
        help='Run optional enrichment stage (requires config enabled)',
    )
    parser.add_argument(
        '--require-complete-enrichment',
        action='store_true',
        help='Fail closed unless every selected order has complete API entry readback (requires --enrich).',
    )
    parser.add_argument(
        '-v', '--verbose',
        action='store_true',
        help='Enable verbose logging',
    )

    args = parser.parse_args()
    if args.require_complete_enrichment and not args.enrich:
        parser.error("--require-complete-enrichment requires --enrich")

    setup_logging(args.verbose)
    engine_kwargs = {}
    if args.db_path is not None:
        engine_kwargs["db_path"] = args.db_path
    engine = OrderSyncEngine(**engine_kwargs)

    max_lookback_days = 13

    def parse_date(value: str) -> date:
        return datetime.strptime(value, "%Y-%m-%d").date()

    # Parse states if provided
    states = None
    if args.states:
        states = [s.strip() for s in args.states.split(',')]

    if args.since:
        try:
            since_date = parse_date(args.since)
        except ValueError:
            print(f"ERROR: invalid --since date: {args.since} (expected YYYY-MM-DD)")
            return 2

        end_date = datetime.now().date()
        if args.until:
            try:
                end_date = parse_date(args.until)
            except ValueError:
                print(f"ERROR: invalid --until date: {args.until} (expected YYYY-MM-DD)")
                return 2

        max_since = end_date - timedelta(days=max_lookback_days)
        if since_date < max_since:
            print(
                f"WARNING: since={args.since} exceeds max lookback {max_lookback_days} days; "
                f"clamping to {max_since.isoformat()}."
            )
            args.since = max_since.isoformat()

    print(f"\n{'=' * 60}")
    print("KASPI ORDER SYNC")
    print(f"{'=' * 60}")
    print(f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    if args.stats:
        print_stats(engine)
        return 0

    if args.all:
        print(f"Mode: ALL STORES")
        print(f"Since: {args.since or 'last 7 days'}")
        print(f"States: {states or 'all'}")
        print(f"Dry run: {args.dry_run}")

        result = engine.sync_all_stores(
            since=args.since,
            until=args.until,
            states=states,
            dry_run=args.dry_run,
        )
        if args.enrich:
            synced_stores = [
                store
                for store, store_result in result.store_results.items()
                if getattr(store_result, "success", False)
            ]
            _run_enrichment(
                synced_stores,
                args.since,
                args.until,
                args.dry_run,
                args.require_complete_enrichment,
                getattr(engine, "db_path", None),
            )
        print_multi_result(result)

        return 0 if not result.errors else 1

    if args.store:
        store_code = args.store.upper()
        print(f"Mode: SINGLE STORE ({store_code})")
        print(f"Since: {args.since or 'last 7 days'}")
        print(f"States: {states or 'all'}")
        print(f"Dry run: {args.dry_run}")

        result = engine.sync_store(
            store_code=store_code,
            since=args.since,
            until=args.until,
            states=states,
            dry_run=args.dry_run,
        )
        if args.enrich:
            _run_enrichment(
                [store_code],
                args.since,
                args.until,
                args.dry_run,
                args.require_complete_enrichment,
                getattr(engine, "db_path", None),
            )
        print_sync_result(result)

        return 0 if result.success else 1

    # No mode specified
    parser.print_help()
    print("\nExample:")
    print("  python scripts/sync_kaspi_orders.py --store UNIVERSAL --dry-run")
    return 1


if __name__ == "__main__":
    sys.exit(main())
