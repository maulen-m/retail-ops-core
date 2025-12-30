#!/usr/bin/env python3
"""
PO Draft Approval CLI

Part 4 requirement: Assisted autonomy workflow for PO approval.
Allows manual approval/rejection of PO drafts that require review.

Usage:
    # Approve a draft
    python scripts/approve_po_draft.py --draft-id 123 --approve --notes "Approved after review"

    # Reject a draft
    python scripts/approve_po_draft.py --draft-id 123 --reject --notes "ROIC too low, defer to next cycle"

    # List pending drafts
    python scripts/approve_po_draft.py --list-pending

    # Show draft details
    python scripts/approve_po_draft.py --draft-id 123 --show
"""

import argparse
import sqlite3
from datetime import datetime
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

DB_PATH = PROJECT_ROOT / "db" / "app.db"


def get_pending_drafts(db_path: Path) -> list[dict]:
    """Get all PO drafts that need approval."""
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row

    # Check if fact_po_drafts exists
    tables = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='fact_po_drafts'"
    ).fetchall()

    if not tables:
        print("Warning: fact_po_drafts table not found. No drafts to show.")
        conn.close()
        return []

    rows = conn.execute("""
        SELECT
            d.draft_id,
            d.created_at,
            d.status,
            d.total_po_value_kzt,
            d.total_order_qty,
            d.skus_count,
            d.roic_action_summary,
            d.guardrail_status
        FROM fact_po_drafts d
        LEFT JOIN fact_po_approvals a ON d.draft_id = a.draft_id
        WHERE d.status = 'PENDING'
          AND a.approval_id IS NULL
        ORDER BY d.created_at DESC
    """).fetchall()

    conn.close()
    return [dict(row) for row in rows]


def get_draft_details(db_path: Path, draft_id: int) -> dict:
    """Get details of a specific draft."""
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row

    # Check if fact_po_drafts exists
    tables = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='fact_po_drafts'"
    ).fetchall()

    if not tables:
        print("Warning: fact_po_drafts table not found.")
        conn.close()
        return {}

    row = conn.execute("""
        SELECT * FROM fact_po_drafts WHERE draft_id = ?
    """, (draft_id,)).fetchone()

    if not row:
        conn.close()
        return {}

    # Get line items if table exists
    lines = []
    line_tables = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='fact_po_draft_lines'"
    ).fetchall()

    if line_tables:
        lines = conn.execute("""
            SELECT * FROM fact_po_draft_lines
            WHERE draft_id = ?
            ORDER BY po_value_kzt DESC
        """, (draft_id,)).fetchall()

    conn.close()

    result = dict(row)
    result['lines'] = [dict(l) for l in lines]
    return result


def record_approval(
    db_path: Path,
    draft_id: int,
    decision: str,
    approved_by: str,
    notes: str = None
) -> int:
    """Record an approval decision."""
    conn = sqlite3.connect(str(db_path))
    cursor = conn.cursor()

    # Get draft info for recording
    draft = get_draft_details(db_path, draft_id)

    if not draft:
        print(f"Error: Draft {draft_id} not found")
        conn.close()
        return 0

    # Insert approval record
    cursor.execute("""
        INSERT INTO fact_po_approvals (
            draft_id, sku_key, roic_action, approved_by, decision, notes,
            po_value_kzt, order_qty
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        draft_id,
        "ALL",  # Whole draft approval
        draft.get("roic_action_summary", "UNKNOWN"),
        approved_by,
        decision,
        notes,
        draft.get("total_po_value_kzt", 0),
        draft.get("total_order_qty", 0)
    ))

    # Update draft status if fact_po_drafts exists
    tables = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='fact_po_drafts'"
    ).fetchall()

    if tables:
        new_status = "APPROVED" if decision == "APPROVE" else "REJECTED"
        cursor.execute("""
            UPDATE fact_po_drafts
            SET status = ?, updated_at = ?
            WHERE draft_id = ?
        """, (new_status, datetime.now().isoformat(), draft_id))

    conn.commit()
    approval_id = cursor.lastrowid
    conn.close()

    return approval_id


def list_pending(db_path: Path):
    """List all pending drafts."""
    drafts = get_pending_drafts(db_path)

    if not drafts:
        print("No pending drafts found.")
        return

    print(f"\n{'='*70}")
    print("PENDING PO DRAFTS")
    print(f"{'='*70}")
    print(f"{'ID':<8} {'Created':<20} {'SKUs':<6} {'Value (KZT)':<15} {'Status'}")
    print(f"{'-'*70}")

    for d in drafts:
        print(f"{d['draft_id']:<8} {d['created_at'][:19]:<20} {d['skus_count']:<6} "
              f"{d['total_po_value_kzt']:>14,.0f} {d['guardrail_status']}")

    print(f"\nTotal: {len(drafts)} pending drafts")


def show_draft(db_path: Path, draft_id: int):
    """Show details of a draft."""
    draft = get_draft_details(db_path, draft_id)

    if not draft:
        print(f"Draft {draft_id} not found")
        return

    print(f"\n{'='*70}")
    print(f"DRAFT #{draft_id}")
    print(f"{'='*70}")
    print(f"Created:      {draft.get('created_at', 'N/A')}")
    print(f"Status:       {draft.get('status', 'N/A')}")
    print(f"Total Value:  {draft.get('total_po_value_kzt', 0):,.0f} KZT")
    print(f"Total Qty:    {draft.get('total_order_qty', 0)}")
    print(f"SKUs:         {draft.get('skus_count', 0)}")
    print(f"Guardrails:   {draft.get('guardrail_status', 'N/A')}")
    print(f"ROIC Action:  {draft.get('roic_action_summary', 'N/A')}")

    if draft.get('lines'):
        print(f"\n{'SKU':<40} {'Qty':<8} {'Value (KZT)':<15} {'ROIC %'}")
        print(f"{'-'*70}")
        for line in draft['lines'][:20]:  # Top 20 lines
            sku = line.get('sku_key', 'N/A')[:39]
            qty = line.get('order_qty', 0)
            value = line.get('po_value_kzt', 0)
            roic = line.get('roic_pct', 0)
            print(f"{sku:<40} {qty:<8} {value:>14,.0f} {roic:>6.1f}%")

        if len(draft['lines']) > 20:
            print(f"... and {len(draft['lines']) - 20} more lines")


def approve_draft(db_path: Path, draft_id: int, notes: str = None, approved_by: str = "ADIL"):
    """Approve a draft."""
    approval_id = record_approval(db_path, draft_id, "APPROVE", approved_by, notes)

    if approval_id:
        print(f"\nDraft #{draft_id} APPROVED (approval_id={approval_id})")
        if notes:
            print(f"Notes: {notes}")
    else:
        print(f"\nFailed to approve draft #{draft_id}")


def reject_draft(db_path: Path, draft_id: int, notes: str = None, approved_by: str = "ADIL"):
    """Reject a draft."""
    approval_id = record_approval(db_path, draft_id, "REJECT", approved_by, notes)

    if approval_id:
        print(f"\nDraft #{draft_id} REJECTED (approval_id={approval_id})")
        if notes:
            print(f"Notes: {notes}")
    else:
        print(f"\nFailed to reject draft #{draft_id}")


def get_approval_history(db_path: Path, limit: int = 20) -> list[dict]:
    """Get recent approval history."""
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row

    rows = conn.execute("""
        SELECT * FROM fact_po_approvals
        ORDER BY approved_at DESC
        LIMIT ?
    """, (limit,)).fetchall()

    conn.close()
    return [dict(row) for row in rows]


def show_history(db_path: Path, limit: int = 20):
    """Show approval history."""
    history = get_approval_history(db_path, limit)

    if not history:
        print("No approval history found.")
        return

    print(f"\n{'='*70}")
    print("APPROVAL HISTORY")
    print(f"{'='*70}")
    print(f"{'Draft':<8} {'Decision':<10} {'By':<12} {'Date':<20} {'Notes'}")
    print(f"{'-'*70}")

    for h in history:
        notes = (h['notes'] or '')[:30]
        print(f"{h['draft_id']:<8} {h['decision']:<10} {h['approved_by']:<12} "
              f"{h['approved_at'][:19]:<20} {notes}")


def main():
    parser = argparse.ArgumentParser(
        description="PO Draft Approval CLI",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    python scripts/approve_po_draft.py --list-pending
    python scripts/approve_po_draft.py --draft-id 123 --show
    python scripts/approve_po_draft.py --draft-id 123 --approve --notes "Approved"
    python scripts/approve_po_draft.py --draft-id 123 --reject --notes "ROIC too low"
    python scripts/approve_po_draft.py --history
        """
    )

    parser.add_argument("--draft-id", type=int, help="Draft ID to operate on")
    parser.add_argument("--approve", action="store_true", help="Approve the draft")
    parser.add_argument("--reject", action="store_true", help="Reject the draft")
    parser.add_argument("--notes", type=str, help="Notes for the decision")
    parser.add_argument("--by", type=str, default="ADIL", help="Who is approving (default: ADIL)")
    parser.add_argument("--list-pending", action="store_true", help="List pending drafts")
    parser.add_argument("--show", action="store_true", help="Show draft details")
    parser.add_argument("--history", action="store_true", help="Show approval history")
    parser.add_argument("--db", type=str, help="Database path (default: db/app.db)")

    args = parser.parse_args()

    db_path = Path(args.db) if args.db else DB_PATH

    if not db_path.exists():
        print(f"Error: Database not found at {db_path}")
        sys.exit(1)

    if args.list_pending:
        list_pending(db_path)
    elif args.history:
        show_history(db_path)
    elif args.draft_id:
        if args.show:
            show_draft(db_path, args.draft_id)
        elif args.approve:
            if args.reject:
                print("Error: Cannot both approve and reject")
                sys.exit(1)
            approve_draft(db_path, args.draft_id, args.notes, args.by)
        elif args.reject:
            reject_draft(db_path, args.draft_id, args.notes, args.by)
        else:
            # Default to showing the draft
            show_draft(db_path, args.draft_id)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
