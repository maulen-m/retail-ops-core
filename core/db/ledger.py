"""
TASK-173: Stock Ledger Operations Module (Phase 10)

Provides event-sourced stock tracking functions for the stock_ledger table.

Event Types:
- INITIAL: Bootstrap/opening balance
- SALE: Stock decrease from customer order (qty_change < 0)
- INBOUND: Stock increase from PO arrival (qty_change > 0)
- RETURN: Stock increase from customer return (qty_change > 0)
- ADJUSTMENT: Manual stock correction (+/-)
- WRITE_OFF: Stock decrease from damage/loss (qty_change < 0)

Tables used:
- stock_ledger: Event-sourced stock changes
- po_line: Pending PO quantities for inbound calculation
- fact_inventory_snapshot_size: Rebuilt from ledger
- dim_sku_size: Size definitions for a SKU
"""

import sqlite3
from datetime import date, datetime
from pathlib import Path
from typing import Optional

from . import get_db, DEFAULT_DB_PATH


# Valid event types
VALID_EVENT_TYPES = frozenset([
    "INITIAL",      # Bootstrap/opening balance
    "SALE",         # Customer order (decreases stock)
    "INBOUND",      # PO arrival (increases stock)
    "RETURN",       # Customer return (increases stock)
    "ADJUSTMENT",   # Manual correction (+/-)
    "WRITE_OFF",    # Damage/loss (decreases stock)
])


def add_ledger_event(
    event_type: str,
    sku_id: str,
    qty_change: int,
    event_date: date,
    sku_key: str = None,
    my_size: str = None,
    store_code: str = "UNIVERSAL",
    reference_id: str = None,
    reference_type: str = None,
    kaspi_offer_name: str = None,
    notes: str = None,
    input_source: str = "SYSTEM",
    created_by: str = "system",
    db_path: Optional[Path] = None,
) -> int:
    """
    Insert event into stock_ledger, return ledger_id.

    Args:
        event_type: INITIAL/SALE/INBOUND/ADJUSTMENT/RETURN/WRITE_OFF
        sku_id: Size-level SKU identifier
        qty_change: Quantity change (+ for increase, - for decrease)
        event_date: Date of the event
        sku_key: Style-level SKU (auto-derived if not provided)
        my_size: Size label (auto-derived if not provided)
        store_code: Store code (default: UNIVERSAL)
        reference_id: order_id, po_id, or adjustment_id
        reference_type: SALE/PO/ADJUSTMENT
        kaspi_offer_name: For sales events, the Kaspi listing name
        notes: Free-text notes
        input_source: SYSTEM/MANUAL/IMPORT/API
        created_by: User or system that created this event
        db_path: Optional database path

    Returns:
        ledger_id of the inserted event

    Raises:
        ValueError: If event_type is invalid
    """
    if event_type not in VALID_EVENT_TYPES:
        raise ValueError(f"Invalid event_type: {event_type}. Must be one of {VALID_EVENT_TYPES}")

    with get_db(db_path) as conn:
        # Auto-derive sku_key and my_size from sku_id if not provided
        if sku_key is None or my_size is None:
            row = conn.execute("""
                SELECT sku_key, my_size
                FROM dim_sku_size
                WHERE sku_id = ?
            """, (sku_id,)).fetchone()

            if row:
                if sku_key is None:
                    sku_key = row["sku_key"]
                if my_size is None:
                    my_size = row["my_size"]
            else:
                # Fallback: extract from sku_id pattern (CL_OC_MEN_LINE52_BLACK_XL)
                parts = sku_id.rsplit("_", 1)
                if len(parts) == 2 and sku_key is None:
                    sku_key = parts[0]
                if my_size is None:
                    my_size = parts[1] if len(parts) == 2 else "UNKNOWN"

        # Calculate running balance (sum of all previous events for this sku_id + current change)
        balance_row = conn.execute("""
            SELECT COALESCE(SUM(qty_change), 0) as total
            FROM stock_ledger
            WHERE sku_id = ? AND store_code = ?
        """, (sku_id, store_code)).fetchone()

        previous_balance = balance_row["total"] if balance_row else 0
        running_balance = previous_balance + qty_change

        # Insert the event
        cursor = conn.execute("""
            INSERT INTO stock_ledger (
                event_date, event_type, sku_key, sku_id, my_size, store_code,
                qty_change, running_balance, reference_id, reference_type,
                kaspi_offer_name, notes, input_source, created_by
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            event_date.isoformat() if isinstance(event_date, date) else event_date,
            event_type,
            sku_key,
            sku_id,
            my_size,
            store_code,
            qty_change,
            running_balance,
            reference_id,
            reference_type,
            kaspi_offer_name,
            notes,
            input_source,
            created_by,
        ))

        return cursor.lastrowid


def get_stock_balance(
    sku_id: str,
    store_code: str = "UNIVERSAL",
    as_of_date: date = None,
    db_path: Optional[Path] = None,
) -> int:
    """
    Calculate stock balance from ledger events.

    Args:
        sku_id: Size-level SKU identifier
        store_code: Store code (default: UNIVERSAL)
        as_of_date: Calculate balance up to this date (default: today)
        db_path: Optional database path

    Returns:
        Current stock balance (sum of all qty_change events)
    """
    if as_of_date is None:
        as_of_date = date.today()

    with get_db(db_path) as conn:
        result = conn.execute("""
            SELECT COALESCE(SUM(qty_change), 0) as balance
            FROM stock_ledger
            WHERE sku_id = ?
              AND store_code = ?
              AND event_date <= ?
        """, (
            sku_id,
            store_code,
            as_of_date.isoformat() if isinstance(as_of_date, date) else as_of_date,
        )).fetchone()

        return result["balance"] if result else 0


def get_stock_balances_all(
    store_code: str = "UNIVERSAL",
    as_of_date: date = None,
    db_path: Optional[Path] = None,
) -> dict[str, int]:
    """
    Get all SKU balances: {sku_id: balance}.

    Args:
        store_code: Store code (default: UNIVERSAL)
        as_of_date: Calculate balances up to this date (default: today)
        db_path: Optional database path

    Returns:
        Dict mapping sku_id -> current balance
    """
    if as_of_date is None:
        as_of_date = date.today()

    with get_db(db_path) as conn:
        rows = conn.execute("""
            SELECT sku_id, SUM(qty_change) as balance
            FROM stock_ledger
            WHERE store_code = ?
              AND event_date <= ?
            GROUP BY sku_id
        """, (
            store_code,
            as_of_date.isoformat() if isinstance(as_of_date, date) else as_of_date,
        )).fetchall()

        return {row["sku_id"]: row["balance"] for row in rows}


def get_ledger_events(
    sku_id: str = None,
    sku_key: str = None,
    event_type: str = None,
    store_code: str = None,
    start_date: date = None,
    end_date: date = None,
    limit: int = 100,
    db_path: Optional[Path] = None,
) -> list[dict]:
    """
    Get ledger events with optional filters.

    Args:
        sku_id: Filter by size-level SKU
        sku_key: Filter by style-level SKU
        event_type: Filter by event type
        store_code: Filter by store
        start_date: Filter events from this date
        end_date: Filter events to this date
        limit: Maximum number of events to return
        db_path: Optional database path

    Returns:
        List of event dicts
    """
    with get_db(db_path) as conn:
        conditions = []
        params = []

        if sku_id:
            conditions.append("sku_id = ?")
            params.append(sku_id)

        if sku_key:
            conditions.append("sku_key = ?")
            params.append(sku_key)

        if event_type:
            conditions.append("event_type = ?")
            params.append(event_type)

        if store_code:
            conditions.append("store_code = ?")
            params.append(store_code)

        if start_date:
            conditions.append("event_date >= ?")
            params.append(start_date.isoformat() if isinstance(start_date, date) else start_date)

        if end_date:
            conditions.append("event_date <= ?")
            params.append(end_date.isoformat() if isinstance(end_date, date) else end_date)

        where_clause = " AND ".join(conditions) if conditions else "1=1"

        query = f"""
            SELECT *
            FROM stock_ledger
            WHERE {where_clause}
            ORDER BY event_date DESC, ledger_id DESC
            LIMIT ?
        """
        params.append(limit)

        rows = conn.execute(query, params).fetchall()
        return [dict(row) for row in rows]


def rebuild_snapshot_from_ledger(
    snapshot_date: date = None,
    store_code: str = "UNIVERSAL",
    db_path: Optional[Path] = None,
) -> int:
    """
    Rebuild fact_inventory_snapshot_size from stock_ledger.

    Also calculates inbound_stock from pending po_line.

    Args:
        snapshot_date: Date for snapshot (default: today)
        store_code: Store code (default: UNIVERSAL)
        db_path: Optional database path

    Returns:
        Number of snapshot rows created
    """
    if snapshot_date is None:
        snapshot_date = date.today()

    with get_db(db_path) as conn:
        # Step 1: Calculate current stock from ledger
        ledger_balances = conn.execute("""
            SELECT
                sku_id,
                sku_key,
                my_size,
                SUM(qty_change) as current_stock
            FROM stock_ledger
            WHERE store_code = ?
              AND event_date <= ?
            GROUP BY sku_id, sku_key, my_size
        """, (
            store_code,
            snapshot_date.isoformat(),
        )).fetchall()

        # Step 2: Calculate inbound stock from pending PO lines
        # Join with po_header to get only non-received POs
        inbound_query = conn.execute("""
            SELECT
                pl.sku_id,
                pl.sku_key,
                pl.my_size,
                SUM(pl.order_qty - pl.received_qty) as inbound_stock
            FROM po_line pl
            JOIN po_header ph ON pl.po_id = ph.po_id
            WHERE pl.status IN ('PENDING', 'PARTIAL')
              AND ph.status NOT IN ('CLOSED', 'CANCELLED')
            GROUP BY pl.sku_id, pl.sku_key, pl.my_size
        """).fetchall()

        inbound_by_sku = {row["sku_id"]: row["inbound_stock"] for row in inbound_query}

        # Step 3: Delete existing snapshot for this date/store
        conn.execute("""
            DELETE FROM fact_inventory_snapshot_size
            WHERE snapshot_date = ? AND store_code = ?
        """, (snapshot_date.isoformat(), store_code))

        # Step 4: Insert new snapshot rows
        inserted = 0
        for row in ledger_balances:
            sku_id = row["sku_id"]
            current_stock = row["current_stock"]
            inbound_stock = inbound_by_sku.get(sku_id, 0)

            conn.execute("""
                INSERT INTO fact_inventory_snapshot_size
                (sku_id, sku_key, my_size, current_stock, inbound_stock, snapshot_date, store_code)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (
                sku_id,
                row["sku_key"],
                row["my_size"],
                current_stock,
                inbound_stock,
                snapshot_date.isoformat(),
                store_code,
            ))
            inserted += 1

        return inserted


def count_ledger_events(
    event_type: str = None,
    sku_id: str = None,
    store_code: str = None,
    db_path: Optional[Path] = None,
) -> int:
    """
    Count ledger events with optional filters.

    Args:
        event_type: Filter by event type
        sku_id: Filter by size-level SKU
        store_code: Filter by store
        db_path: Optional database path

    Returns:
        Count of matching events
    """
    with get_db(db_path) as conn:
        conditions = []
        params = []

        if event_type:
            conditions.append("event_type = ?")
            params.append(event_type)

        if sku_id:
            conditions.append("sku_id = ?")
            params.append(sku_id)

        if store_code:
            conditions.append("store_code = ?")
            params.append(store_code)

        where_clause = " AND ".join(conditions) if conditions else "1=1"

        result = conn.execute(f"""
            SELECT COUNT(*) as cnt
            FROM stock_ledger
            WHERE {where_clause}
        """, params).fetchone()

        return result["cnt"] if result else 0


def get_event_summary(
    as_of_date: date = None,
    store_code: str = "UNIVERSAL",
    db_path: Optional[Path] = None,
) -> dict:
    """
    Get summary of ledger events by type.

    Args:
        as_of_date: Calculate summary up to this date (default: today)
        store_code: Store code (default: UNIVERSAL)
        db_path: Optional database path

    Returns:
        Dict with event type counts and totals
    """
    if as_of_date is None:
        as_of_date = date.today()

    with get_db(db_path) as conn:
        rows = conn.execute("""
            SELECT
                event_type,
                COUNT(*) as event_count,
                SUM(qty_change) as qty_total
            FROM stock_ledger
            WHERE store_code = ?
              AND event_date <= ?
            GROUP BY event_type
        """, (
            store_code,
            as_of_date.isoformat(),
        )).fetchall()

        result = {}
        for row in rows:
            result[row["event_type"]] = {
                "count": row["event_count"],
                "qty_total": row["qty_total"],
            }

        return result
