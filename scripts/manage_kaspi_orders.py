#!/usr/bin/env python3
"""
CLI for managing Kaspi orders (Phase 9.5).

Commands:
- list: List orders by status
- accept: Accept NEW orders
- assemble: Mark orders as assembled
- ship: Ship orders with waybills
- cancel: Cancel orders
- status: Show status summary

Usage:
    python scripts/manage_kaspi_orders.py list --status NEW
    python scripts/manage_kaspi_orders.py accept ORDER_ID
    python scripts/manage_kaspi_orders.py accept-all --confirm
    python scripts/manage_kaspi_orders.py assemble ORDER_ID
    python scripts/manage_kaspi_orders.py ship ORDER_ID
    python scripts/manage_kaspi_orders.py cancel ORDER_ID --reason OUT_OF_STOCK
    python scripts/manage_kaspi_orders.py status

IMPORTANT: Write operations require ENABLE_KASPI_WRITE=1 in .env
"""

import argparse
import logging
import sys
from datetime import datetime
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from dotenv import load_dotenv

from core.db import get_db
from core.automation.order_status_manager import (
    OrderStatusManager,
    CANCEL_REASONS,
)


# Load environment
load_dotenv(project_root / ".env")

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def cmd_list(args):
    """List orders by status."""
    manager = OrderStatusManager(store_code=args.store)

    status = args.status.upper() if args.status else None

    with get_db(manager.db_path) as conn:
        query = """
            SELECT order_id, internal_status, kaspi_status, unit_price_kzt,
                   created_at, planned_shipment_date, waybill_url IS NOT NULL as has_waybill
            FROM fact_orders_kaspi
            WHERE store_code = ?
        """
        params = [args.store]

        if status:
            query += " AND internal_status = ?"
            params.append(status)

        query += " ORDER BY created_at DESC"

        if args.limit:
            query += f" LIMIT {args.limit}"

        rows = conn.execute(query, params).fetchall()

    print(f"\n{'='*70}")
    print(f"ORDERS - {args.store}" + (f" - Status: {status}" if status else ""))
    print(f"{'='*70}")

    if not rows:
        print("No orders found.")
        return

    # Print header
    print(f"{'Order ID':<15} {'Status':<12} {'Kaspi':<20} {'Price':>12} {'Waybill':>8}")
    print("-" * 70)

    for row in rows:
        waybill = "Yes" if row['has_waybill'] else "No"
        print(f"{row['order_id']:<15} {row['internal_status']:<12} "
              f"{row['kaspi_status']:<20} {row['unit_price_kzt']:>12,.0f} {waybill:>8}")

    print(f"\nTotal: {len(rows)} orders")


def cmd_accept(args):
    """Accept a single order."""
    manager = OrderStatusManager(store_code=args.store)

    if not manager.writes_enabled and not args.dry_run:
        print("ERROR: Write operations disabled. Set ENABLE_KASPI_WRITE=1")
        sys.exit(1)

    result = manager.accept_order(args.order_id, dry_run=args.dry_run)

    if result.success:
        print(f"{'[DRY RUN] ' if args.dry_run else ''}Order {args.order_id} accepted")
        print(f"  Status: {result.old_status} -> {result.new_status}")
    else:
        print(f"ERROR: {result.error}")
        sys.exit(1)


def cmd_accept_all(args):
    """Accept all NEW orders."""
    manager = OrderStatusManager(store_code=args.store, require_confirmation=not args.confirm)

    if not manager.writes_enabled and not args.dry_run:
        print("ERROR: Write operations disabled. Set ENABLE_KASPI_WRITE=1")
        sys.exit(1)

    result = manager.accept_ready_orders(confirm=args.confirm, dry_run=args.dry_run)

    print(f"\n{'='*50}")
    print(f"ACCEPT ALL - {args.store}")
    print(f"{'='*50}")

    if result.confirmation_sent:
        print(f"Confirmation required for {result.total} orders.")
        print("Run with --confirm to proceed.")
        return

    print(f"Total: {result.total}")
    print(f"Success: {result.success_count}")
    print(f"Failed: {result.failed_count}")

    if result.errors:
        print("\nErrors:")
        for err in result.errors[:10]:
            print(f"  - {err}")


def cmd_assemble(args):
    """Mark order as assembled."""
    manager = OrderStatusManager(store_code=args.store)

    if not manager.writes_enabled and not args.dry_run:
        print("ERROR: Write operations disabled. Set ENABLE_KASPI_WRITE=1")
        sys.exit(1)

    result = manager.assemble_order(
        args.order_id,
        parcel_count=args.parcels,
        dry_run=args.dry_run
    )

    if result.success:
        print(f"{'[DRY RUN] ' if args.dry_run else ''}Order {args.order_id} assembled")
        print(f"  Status: {result.old_status} -> {result.new_status}")
    else:
        print(f"ERROR: {result.error}")
        sys.exit(1)


def cmd_assemble_all(args):
    """Assemble all ACCEPTED orders."""
    manager = OrderStatusManager(store_code=args.store, require_confirmation=not args.confirm)

    if not manager.writes_enabled and not args.dry_run:
        print("ERROR: Write operations disabled. Set ENABLE_KASPI_WRITE=1")
        sys.exit(1)

    result = manager.assemble_ready_orders(confirm=args.confirm, dry_run=args.dry_run)

    print(f"\n{'='*50}")
    print(f"ASSEMBLE ALL - {args.store}")
    print(f"{'='*50}")

    if result.confirmation_sent:
        print(f"Confirmation required for {result.total} orders.")
        print("Run with --confirm to proceed.")
        return

    print(f"Total: {result.total}")
    print(f"Success: {result.success_count}")
    print(f"Failed: {result.failed_count}")


def cmd_ship(args):
    """Ship a single order."""
    manager = OrderStatusManager(store_code=args.store)

    if not manager.writes_enabled and not args.dry_run:
        print("ERROR: Write operations disabled. Set ENABLE_KASPI_WRITE=1")
        sys.exit(1)

    result = manager.ship_order(args.order_id, dry_run=args.dry_run)

    if result.success:
        print(f"{'[DRY RUN] ' if args.dry_run else ''}Order {args.order_id} shipped")
        print(f"  Status: {result.old_status} -> {result.new_status}")
    else:
        print(f"ERROR: {result.error}")
        sys.exit(1)


def cmd_ship_all(args):
    """Ship all READY orders with waybills."""
    manager = OrderStatusManager(store_code=args.store, require_confirmation=not args.confirm)

    if not manager.writes_enabled and not args.dry_run:
        print("ERROR: Write operations disabled. Set ENABLE_KASPI_WRITE=1")
        sys.exit(1)

    result = manager.ship_ready_orders(confirm=args.confirm, dry_run=args.dry_run)

    print(f"\n{'='*50}")
    print(f"SHIP ALL - {args.store}")
    print(f"{'='*50}")

    if result.confirmation_sent:
        print(f"Confirmation required for {result.total} orders.")
        print("Run with --confirm to proceed.")
        return

    print(f"Total: {result.total}")
    print(f"Success: {result.success_count}")
    print(f"Failed: {result.failed_count}")


def cmd_cancel(args):
    """Cancel an order."""
    manager = OrderStatusManager(store_code=args.store)

    if not manager.writes_enabled and not args.dry_run:
        print("ERROR: Write operations disabled. Set ENABLE_KASPI_WRITE=1")
        sys.exit(1)

    result = manager.cancel_order(
        args.order_id,
        reason=args.reason,
        dry_run=args.dry_run
    )

    if result.success:
        print(f"{'[DRY RUN] ' if args.dry_run else ''}Order {args.order_id} cancelled")
        print(f"  Reason: {args.reason}")
        print(f"  Status: {result.old_status} -> {result.new_status}")
    else:
        print(f"ERROR: {result.error}")
        sys.exit(1)


def cmd_status(args):
    """Show order status summary."""
    manager = OrderStatusManager(store_code=args.store)

    summary = manager.get_status_summary()
    pending = manager.get_pending_actions()

    print(f"\n{'='*50}")
    print(f"ORDER STATUS SUMMARY - {args.store}")
    print(f"{'='*50}")

    print(f"\nWrites enabled: {manager.writes_enabled}")

    print("\nOrders by status:")
    total = 0
    for status, count in sorted(summary.items()):
        print(f"  {status:<15} {count:>5}")
        total += count
    print(f"  {'TOTAL':<15} {total:>5}")

    print("\nPending actions:")
    print(f"  To accept:     {pending['to_accept']:>5} orders")
    print(f"  To assemble:   {pending['to_assemble']:>5} orders")
    print(f"  To ship:       {pending['to_ship']:>5} orders (with waybill)")
    print(f"  Ready (no WB): {pending['ready_no_waybill']:>5} orders")


def cmd_workflow(args):
    """Show suggested workflow for today's orders."""
    manager = OrderStatusManager(store_code=args.store)
    pending = manager.get_pending_actions()

    print(f"\n{'='*60}")
    print(f"SUGGESTED WORKFLOW - {args.store}")
    print(f"{'='*60}")

    steps = []

    if pending['to_accept'] > 0:
        steps.append(f"1. Accept {pending['to_accept']} NEW orders:\n"
                    f"   python scripts/manage_kaspi_orders.py accept-all --store {args.store} --dry-run\n"
                    f"   python scripts/manage_kaspi_orders.py accept-all --store {args.store} --confirm")

    if pending['to_assemble'] > 0:
        steps.append(f"2. Assemble {pending['to_assemble']} ACCEPTED orders:\n"
                    f"   python scripts/manage_kaspi_orders.py assemble-all --store {args.store} --dry-run\n"
                    f"   python scripts/manage_kaspi_orders.py assemble-all --store {args.store} --confirm")

    if pending['to_ship'] > 0:
        steps.append(f"3. Ship {pending['to_ship']} READY orders:\n"
                    f"   python scripts/manage_kaspi_orders.py ship-all --store {args.store} --dry-run\n"
                    f"   python scripts/manage_kaspi_orders.py ship-all --store {args.store} --confirm")

    if pending['ready_no_waybill'] > 0:
        steps.append(f"4. Download waybills for {pending['ready_no_waybill']} READY orders:\n"
                    f"   python scripts/download_waybills.py --store {args.store}")

    if not steps:
        print("\nNo pending actions. All orders processed!")
    else:
        print("\n" + "\n\n".join(steps))

    print(f"\n{'='*60}")


def main():
    parser = argparse.ArgumentParser(
        description="Manage Kaspi orders via API",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Show status summary
  python scripts/manage_kaspi_orders.py status --store UNIVERSAL

  # List NEW orders
  python scripts/manage_kaspi_orders.py list --store UNIVERSAL --status NEW

  # Accept single order (dry run)
  python scripts/manage_kaspi_orders.py accept 123456 --store UNIVERSAL --dry-run

  # Accept all NEW orders
  python scripts/manage_kaspi_orders.py accept-all --store UNIVERSAL --confirm

  # Cancel order
  python scripts/manage_kaspi_orders.py cancel 123456 --store UNIVERSAL --reason OUT_OF_STOCK

IMPORTANT: Set ENABLE_KASPI_WRITE=1 in .env to enable write operations.
        """
    )

    subparsers = parser.add_subparsers(dest='command', help='Command')

    # Common arguments
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument('--store', default='UNIVERSAL', help='Store code (default: UNIVERSAL)')
    common.add_argument('--dry-run', action='store_true', help='Validate without executing')

    # list
    p_list = subparsers.add_parser('list', parents=[common], help='List orders')
    p_list.add_argument('--status', help='Filter by status (NEW, ACCEPTED, READY, etc.)')
    p_list.add_argument('--limit', type=int, default=50, help='Max orders to show (default: 50)')
    p_list.set_defaults(func=cmd_list)

    # accept
    p_accept = subparsers.add_parser('accept', parents=[common], help='Accept single order')
    p_accept.add_argument('order_id', help='Order ID to accept')
    p_accept.set_defaults(func=cmd_accept)

    # accept-all
    p_accept_all = subparsers.add_parser('accept-all', parents=[common], help='Accept all NEW orders')
    p_accept_all.add_argument('--confirm', action='store_true', help='Confirm bulk operation')
    p_accept_all.set_defaults(func=cmd_accept_all)

    # assemble
    p_assemble = subparsers.add_parser('assemble', parents=[common], help='Mark order as assembled')
    p_assemble.add_argument('order_id', help='Order ID to assemble')
    p_assemble.add_argument('--parcels', type=int, default=1, help='Number of parcels (default: 1)')
    p_assemble.set_defaults(func=cmd_assemble)

    # assemble-all
    p_assemble_all = subparsers.add_parser('assemble-all', parents=[common], help='Assemble all ACCEPTED orders')
    p_assemble_all.add_argument('--confirm', action='store_true', help='Confirm bulk operation')
    p_assemble_all.set_defaults(func=cmd_assemble_all)

    # ship
    p_ship = subparsers.add_parser('ship', parents=[common], help='Ship order')
    p_ship.add_argument('order_id', help='Order ID to ship')
    p_ship.set_defaults(func=cmd_ship)

    # ship-all
    p_ship_all = subparsers.add_parser('ship-all', parents=[common], help='Ship all READY orders')
    p_ship_all.add_argument('--confirm', action='store_true', help='Confirm bulk operation')
    p_ship_all.set_defaults(func=cmd_ship_all)

    # cancel
    p_cancel = subparsers.add_parser('cancel', parents=[common], help='Cancel order')
    p_cancel.add_argument('order_id', help='Order ID to cancel')
    p_cancel.add_argument('--reason', default='OUT_OF_STOCK',
                         choices=CANCEL_REASONS, help='Cancellation reason')
    p_cancel.set_defaults(func=cmd_cancel)

    # status
    p_status = subparsers.add_parser('status', parents=[common], help='Show status summary')
    p_status.set_defaults(func=cmd_status)

    # workflow
    p_workflow = subparsers.add_parser('workflow', parents=[common], help='Show suggested workflow')
    p_workflow.set_defaults(func=cmd_workflow)

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(1)

    args.func(args)


if __name__ == "__main__":
    main()
