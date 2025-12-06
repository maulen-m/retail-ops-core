#!/usr/bin/env python3
"""
TASK-060: Auto PO Generation Script

Daily script to automatically generate PO drafts when ROP triggers.

Usage:
    python scripts/run_auto_po.py [--dry-run] [--force] [--min-confidence 0.7]
"""

import argparse
import sqlite3
from datetime import date
from pathlib import Path
import sys

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from core.automation.po_generator import (
    generate_po_draft,
    get_draft_summary
)


def check_pending_drafts(db_path: str) -> int:
    """Check for existing pending drafts."""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    cursor.execute("""
        SELECT COUNT(*)
        FROM fact_po_draft
        WHERE status = 'PENDING'
    """)

    count = cursor.fetchone()[0]
    conn.close()

    return count


def send_draft_notification(draft: dict) -> bool:
    """Send Telegram notification for new draft."""
    try:
        from core.alerts.telegram import send_message

        message = f"<b>Auto-PO Draft #{draft['draft_id']} Generated</b>\n\n"
        message += f"SKUs: {len(draft['lines'])}\n"
        message += f"Total Units: {draft['total_units']}\n"
        message += f"Est. Cost: ¥{draft['total_cost_cny']:,.0f} ({draft['total_cost_kzt']:,.0f} KZT)\n"
        message += f"Confidence: {draft['confidence']*100:.0f}%\n\n"

        message += "<b>Items:</b>\n"
        for line in draft['lines'][:5]:
            message += f"• {line['sku_key']}: {line['quantity']} units\n"
            message += f"  ({line['sizes']})\n"

        if len(draft['lines']) > 5:
            message += f"... and {len(draft['lines']) - 5} more\n"

        message += f"\n<b>Commands:</b>\n"
        message += f"Approve: /approve {draft['draft_id']}\n"
        message += f"Reject: /reject {draft['draft_id']} [reason]\n"

        send_message(message)
        return True

    except Exception as e:
        print(f"Failed to send notification: {e}")
        return False


def main():
    parser = argparse.ArgumentParser(description='Generate auto PO drafts')
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Show what would be generated without creating'
    )
    parser.add_argument(
        '--force',
        action='store_true',
        help='Generate even if pending drafts exist'
    )
    parser.add_argument(
        '--min-confidence',
        type=float,
        default=0.5,
        help='Minimum confidence to include SKU (default: 0.5)'
    )
    parser.add_argument(
        '--no-notify',
        action='store_true',
        help='Skip Telegram notification'
    )
    parser.add_argument(
        '--db',
        default='db/app.db',
        help='Path to database (default: db/app.db)'
    )
    args = parser.parse_args()

    # Resolve database path
    db_path = Path(args.db)
    if not db_path.is_absolute():
        db_path = project_root / db_path

    if not db_path.exists():
        print(f"ERROR: Database not found at {db_path}")
        return 1

    print(f"=== Auto PO Generator ===")
    print(f"Database: {db_path}")
    print(f"Min confidence: {args.min_confidence}")
    print()

    # Check for existing pending drafts
    pending = check_pending_drafts(str(db_path))
    if pending > 0 and not args.force:
        print(f"WARNING: {pending} pending draft(s) already exist")
        print("Use --force to generate anyway")
        return 0

    if args.dry_run:
        print("DRY RUN MODE - No changes will be made")
        print()

    # Check for SKUs needing reorder
    conn = sqlite3.connect(str(db_path))
    cursor = conn.cursor()

    cursor.execute("""
        SELECT sku_key, current_stock, rop, d30
        FROM fact_sku_metrics
        WHERE status = 'REORDER'
    """)

    reorder_skus = cursor.fetchall()
    conn.close()

    if not reorder_skus:
        print("No SKUs require reorder")
        return 0

    print(f"SKUs requiring reorder: {len(reorder_skus)}")
    for sku in reorder_skus[:5]:
        print(f"  {sku[0]}: stock={sku[1]}, ROP={sku[2]:.0f}, D30={sku[3]:.2f}")

    if len(reorder_skus) > 5:
        print(f"  ... and {len(reorder_skus) - 5} more")
    print()

    if args.dry_run:
        print("Would generate PO draft for above SKUs")
        return 0

    # Generate draft
    draft_id = generate_po_draft(
        str(db_path),
        trigger='ROP',
        min_confidence=args.min_confidence
    )

    if draft_id == 0:
        print("No draft generated (all SKUs below confidence threshold or no quantity needed)")
        return 0

    # Get summary
    draft = get_draft_summary(str(db_path), draft_id)

    print(f"=== Draft #{draft_id} Created ===")
    print(f"Status: {draft['status']}")
    print(f"Total Units: {draft['total_units']}")
    print(f"Total Cost: ¥{draft['total_cost_cny']:,.0f} ({draft['total_cost_kzt']:,.0f} KZT)")
    print(f"Confidence: {draft['confidence']*100:.0f}%")
    print(f"Expires: {draft['expires_at']}")
    print()

    print("Items:")
    for line in draft['lines']:
        print(f"  {line['sku_key']}: {line['quantity']} units")
        print(f"    Sizes: {line['sizes']}")

    # Send notification
    if not args.no_notify:
        print()
        if send_draft_notification(draft):
            print("Telegram notification sent")
        else:
            print("Failed to send notification")

    print(f"\nAuto PO generation complete.")
    return 0


if __name__ == '__main__':
    exit(main())
