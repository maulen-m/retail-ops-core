#!/usr/bin/env python3
"""
TASK-062: PO Approval CLI

CLI interface for PO approval while Telegram bot is basic.

Usage:
    python scripts/po_approval_cli.py pending          # List pending drafts
    python scripts/po_approval_cli.py show 47          # Show draft details
    python scripts/po_approval_cli.py approve 47       # Approve draft
    python scripts/po_approval_cli.py reject 47 "Price too high"
    python scripts/po_approval_cli.py expire-old       # Mark old drafts as EXPIRED
"""

import argparse
import sqlite3
from datetime import datetime
from pathlib import Path
import sys

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from core.automation.po_generator import get_draft_summary


def list_pending(db_path: str) -> list[dict]:
    """List all pending drafts."""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    cursor.execute("""
        SELECT
            draft_id, created_at, total_units, total_cost_kzt,
            confidence_score, generation_reason
        FROM fact_po_draft
        WHERE status = 'PENDING'
        ORDER BY created_at DESC
    """)

    drafts = []
    for row in cursor.fetchall():
        drafts.append({
            'draft_id': row[0],
            'created_at': row[1],
            'total_units': row[2],
            'total_cost_kzt': row[3],
            'confidence': row[4],
            'reason': row[5]
        })

    conn.close()
    return drafts


def approve_draft(db_path: str, draft_id: int, approved_by: str = 'cli') -> dict:
    """
    Approve a PO draft.

    Updates status and copies lines to fact_po_lines.

    Args:
        db_path: Path to database
        draft_id: Draft to approve
        approved_by: Approver identifier

    Returns:
        Result dict
    """
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # Check draft exists and is pending
    cursor.execute("""
        SELECT status FROM fact_po_draft WHERE draft_id = ?
    """, (draft_id,))

    result = cursor.fetchone()
    if not result:
        conn.close()
        return {'success': False, 'error': 'Draft not found'}

    if result[0] != 'PENDING':
        conn.close()
        return {'success': False, 'error': f'Draft is {result[0]}, not PENDING'}

    # Update draft status
    cursor.execute("""
        UPDATE fact_po_draft
        SET status = 'APPROVED',
            approved_at = datetime('now'),
            approved_by = ?
        WHERE draft_id = ?
    """, (approved_by, draft_id))

    # Generate PO ID
    po_id = f"PO-{datetime.now().strftime('%Y%m%d')}-{draft_id:04d}"

    # Copy lines to fact_po_lines
    cursor.execute("""
        INSERT INTO fact_po_lines (
            po_id, store_code, sku_key, sku_id, my_size,
            order_quantity, unit_cost_kzt, po_date, status
        )
        SELECT
            ?,
            'ALL',
            sku_key,
            sku_id,
            my_size,
            quantity,
            unit_cost_cny * 78,
            date('now'),
            'UNPAID'
        FROM fact_po_draft_lines
        WHERE draft_id = ?
    """, (po_id, draft_id))

    lines_created = cursor.rowcount

    conn.commit()
    conn.close()

    return {
        'success': True,
        'draft_id': draft_id,
        'po_id': po_id,
        'lines_created': lines_created
    }


def reject_draft(db_path: str, draft_id: int, reason: str) -> dict:
    """
    Reject a PO draft.

    Args:
        db_path: Path to database
        draft_id: Draft to reject
        reason: Rejection reason

    Returns:
        Result dict
    """
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # Check draft exists and is pending
    cursor.execute("""
        SELECT status FROM fact_po_draft WHERE draft_id = ?
    """, (draft_id,))

    result = cursor.fetchone()
    if not result:
        conn.close()
        return {'success': False, 'error': 'Draft not found'}

    if result[0] != 'PENDING':
        conn.close()
        return {'success': False, 'error': f'Draft is {result[0]}, not PENDING'}

    # Update draft status
    cursor.execute("""
        UPDATE fact_po_draft
        SET status = 'REJECTED',
            rejection_reason = ?
        WHERE draft_id = ?
    """, (reason, draft_id))

    conn.commit()
    conn.close()

    return {
        'success': True,
        'draft_id': draft_id,
        'reason': reason
    }


def expire_old_drafts(db_path: str) -> int:
    """
    Mark old pending drafts as expired.

    Args:
        db_path: Path to database

    Returns:
        Number of drafts expired
    """
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    cursor.execute("""
        UPDATE fact_po_draft
        SET status = 'EXPIRED'
        WHERE status = 'PENDING'
        AND expires_at < datetime('now')
    """)

    count = cursor.rowcount
    conn.commit()
    conn.close()

    return count


def get_history(db_path: str, limit: int = 10) -> list[dict]:
    """Get recent PO draft history."""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    cursor.execute("""
        SELECT
            draft_id, status, created_at, approved_at,
            total_units, total_cost_kzt, rejection_reason
        FROM fact_po_draft
        ORDER BY created_at DESC
        LIMIT ?
    """, (limit,))

    history = []
    for row in cursor.fetchall():
        history.append({
            'draft_id': row[0],
            'status': row[1],
            'created_at': row[2],
            'approved_at': row[3],
            'total_units': row[4],
            'total_cost_kzt': row[5],
            'rejection_reason': row[6]
        })

    conn.close()
    return history


def main():
    parser = argparse.ArgumentParser(description='PO Approval CLI')
    parser.add_argument(
        'action',
        choices=['pending', 'show', 'approve', 'reject', 'expire-old', 'history'],
        help='Action to perform'
    )
    parser.add_argument(
        'draft_id',
        nargs='?',
        type=int,
        help='Draft ID (required for show/approve/reject)'
    )
    parser.add_argument(
        'reason',
        nargs='?',
        default='',
        help='Rejection reason (for reject action)'
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

    # Execute action
    if args.action == 'pending':
        drafts = list_pending(str(db_path))

        if not drafts:
            print("No pending drafts")
            return 0

        print(f"Pending Drafts ({len(drafts)}):")
        print("-" * 70)
        for d in drafts:
            print(f"#{d['draft_id']:4d} | {d['created_at'][:16]} | "
                  f"{d['total_units']:5d} units | {d['total_cost_kzt']:,.0f} KZT | "
                  f"conf: {d['confidence']*100:.0f}%")
        print("-" * 70)

    elif args.action == 'show':
        if not args.draft_id:
            print("ERROR: draft_id required for show")
            return 1

        draft = get_draft_summary(str(db_path), args.draft_id)
        if not draft:
            print(f"Draft #{args.draft_id} not found")
            return 1

        print(f"=== Draft #{draft['draft_id']} ===")
        print(f"Status: {draft['status']}")
        print(f"Created: {draft['created_at']}")
        print(f"Expires: {draft['expires_at']}")
        print(f"Reason: {draft['reason']}")
        print(f"Confidence: {draft['confidence']*100:.0f}%")
        print()
        print(f"Total Units: {draft['total_units']}")
        print(f"Total Cost: ¥{draft['total_cost_cny']:,.0f} ({draft['total_cost_kzt']:,.0f} KZT)")
        print()
        print("Items:")
        for line in draft['lines']:
            print(f"  {line['sku_key']}: {line['quantity']} units")
            print(f"    Sizes: {line['sizes']}")

    elif args.action == 'approve':
        if not args.draft_id:
            print("ERROR: draft_id required for approve")
            return 1

        result = approve_draft(str(db_path), args.draft_id)

        if result['success']:
            print(f"Draft #{args.draft_id} APPROVED")
            print(f"PO ID: {result['po_id']}")
            print(f"Lines created: {result['lines_created']}")
        else:
            print(f"ERROR: {result['error']}")
            return 1

    elif args.action == 'reject':
        if not args.draft_id:
            print("ERROR: draft_id required for reject")
            return 1

        reason = args.reason or 'No reason provided'
        result = reject_draft(str(db_path), args.draft_id, reason)

        if result['success']:
            print(f"Draft #{args.draft_id} REJECTED")
            print(f"Reason: {result['reason']}")
        else:
            print(f"ERROR: {result['error']}")
            return 1

    elif args.action == 'expire-old':
        count = expire_old_drafts(str(db_path))
        print(f"Expired {count} old draft(s)")

    elif args.action == 'history':
        history = get_history(str(db_path))

        if not history:
            print("No draft history")
            return 0

        print("Recent Drafts:")
        print("-" * 80)
        for h in history:
            status = h['status']
            emoji = '' if status == 'APPROVED' else '' if status == 'REJECTED' else '' if status == 'EXPIRED' else ''
            print(f"#{h['draft_id']:4d} | {status:8s} {emoji} | {h['created_at'][:16]} | "
                  f"{h['total_units']:5d} units | {h['total_cost_kzt']:,.0f} KZT")
            if h['rejection_reason']:
                print(f"       Reason: {h['rejection_reason']}")
        print("-" * 80)

    return 0


if __name__ == '__main__':
    exit(main())
