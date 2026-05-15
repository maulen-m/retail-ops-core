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

import json
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

CANONICAL_STORE_CODE = "UNIVERSAL"
ALL_STORES_CODE = "ALL"


def inventory_pool_store_code() -> str:
    """Canonical store_code used for inventory pool."""
    return CANONICAL_STORE_CODE


def get_accepted_negative_active_zero_sku_ids(conn: sqlite3.Connection) -> set[str]:
    """Return exact negative-ledger SKUs with owner-approved active-zero controls."""
    if (
        conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='exception_queue'"
        ).fetchone()
        is None
    ):
        return set()

    accepted: set[str] = set()
    rows = conn.execute(
        """
        SELECT exception_id, reason, evidence_json
        FROM exception_queue
        WHERE UPPER(COALESCE(status, 'OPEN')) IN ('OPEN', 'PENDING', 'BLOCKED')
          AND LOWER(COALESCE(severity, '')) IN ('critical', 'high')
        """
    ).fetchall()
    for row in rows:
        evidence_text = row["evidence_json"] or "{}"
        try:
            evidence = json.loads(str(evidence_text))
        except Exception:
            evidence = {}
        if not isinstance(evidence, dict):
            evidence = {}
        combined = " ".join(
            [
                str(row["exception_id"] or ""),
                str(row["reason"] or ""),
                json.dumps(evidence, ensure_ascii=False, sort_keys=True),
            ]
        ).upper()
        is_accepted = (
            "NEGATIVE_LEDGER_EXACT_OWNER_ACTIVE_ZERO_QUARANTINE" in combined
            or (
                "NEGATIVE_RAW_LEDGER_BALANCE" in combined
                and ("BERSERK-RUSH" in combined or "BERSERK_RUSH" in combined)
            )
        )
        sku_id = str(evidence.get("sku_id") or "").strip()
        if is_accepted and sku_id:
            accepted.add(sku_id)
    return accepted


def log_audit(
    table_name: str,
    record_id: str,
    field_name: str,
    old_value: Optional[str],
    new_value: Optional[str],
    change_type: str,
    reason: Optional[str] = None,
    source: Optional[str] = None,
    db_path: Optional[Path] = None,
) -> int:
    """
    Insert an audit entry into fact_input_audit.

    This keeps audit logging centralized and tolerant of schema variations.
    """
    with get_db(db_path) as conn:
        table = conn.execute("""
            SELECT name
            FROM sqlite_master
            WHERE type = 'table' AND name = 'fact_input_audit'
        """).fetchone()
        if not table:
            raise RuntimeError(
                "fact_input_audit table missing; run scripts/migrate_013_ledger.py"
            )

        columns = [row["name"] for row in conn.execute("PRAGMA table_info(fact_input_audit)")]
        required = {"table_name", "record_id", "field_name", "change_type"}
        missing = required.difference(columns)
        if missing:
            raise RuntimeError(
                f"fact_input_audit missing required columns: {', '.join(sorted(missing))}"
            )

        payload = {
            "table_name": str(table_name),
            "record_id": str(record_id),
            "field_name": str(field_name),
            "old_value": None if old_value is None else str(old_value),
            "new_value": None if new_value is None else str(new_value),
            "change_type": str(change_type),
        }

        if "reason" in columns and reason is not None:
            payload["reason"] = str(reason)
        if "source" in columns:
            payload["source"] = source or "SYSTEM"

        columns_clause = ", ".join(payload.keys())
        placeholders = ", ".join("?" for _ in payload)
        cursor = conn.execute(
            f"INSERT INTO fact_input_audit ({columns_clause}) VALUES ({placeholders})",
            list(payload.values()),
        )

        return cursor.lastrowid


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
        params = [sku_id, as_of_date.isoformat() if isinstance(as_of_date, date) else as_of_date]
        store_filter = ""
        if store_code and store_code != ALL_STORES_CODE:
            store_filter = "AND store_code = ?"
            params.insert(1, store_code)

        result = conn.execute(f"""
            SELECT COALESCE(SUM(qty_change), 0) as balance
            FROM stock_ledger
            WHERE sku_id = ?
              {store_filter}
              AND event_date <= ?
        """, params).fetchone()

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
        params = [as_of_date.isoformat() if isinstance(as_of_date, date) else as_of_date]
        if store_code and store_code != ALL_STORES_CODE:
            store_filter = "WHERE store_code = ? AND event_date <= ?"
            params.insert(0, store_code)
        else:
            store_filter = "WHERE event_date <= ?"

        rows = conn.execute(f"""
            SELECT sku_id, SUM(qty_change) as balance
            FROM stock_ledger
            {store_filter}
            GROUP BY sku_id
        """, params).fetchall()

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
        def _table_exists(name: str) -> bool:
            row = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name = ?",
                (name,),
            ).fetchone()
            return row is not None
        def _table_has_column(table: str, column: str) -> bool:
            if not _table_exists(table):
                return False
            cols = conn.execute(f"PRAGMA table_info({table})").fetchall()
            return any(c[1] == column for c in cols)

        # Step 1: Calculate current stock from ledger
        params = [snapshot_date.isoformat()]
        store_filter = ""
        if store_code and store_code != ALL_STORES_CODE:
            store_filter = "AND store_code = ?"
            params.append(store_code)

        # Snapshot semantics: MORNING stock before same-day events.
        # Use event_date < snapshot_date to exclude same-day sales/arrivals.
        ledger_balances = conn.execute(f"""
            SELECT
                sku_id,
                sku_key,
                my_size,
                SUM(qty_change) as current_stock
            FROM stock_ledger
            WHERE event_date < ?
              {store_filter}
            GROUP BY sku_id, sku_key, my_size
        """, params).fetchall()

        # Step 2: Calculate inbound stock from pending PO lines
        # Join with po_header to get only non-received POs
        inbound_by_sku: dict[str, int] = {}
        if _table_exists("po_line") and _table_exists("po_header"):
            inbound_query = conn.execute("""
                SELECT
                    pl.sku_id,
                    pl.sku_key,
                    pl.my_size,
                    SUM(pl.order_qty - pl.received_qty) as inbound_stock
                FROM po_line pl
                JOIN po_header ph ON pl.po_id = ph.po_id
                WHERE pl.status IN ('PENDING', 'PARTIAL', 'IN_TRANSIT')
                  AND ph.status NOT IN ('CLOSED', 'CANCELLED')
                GROUP BY pl.sku_id, pl.sku_key, pl.my_size
            """).fetchall()
            inbound_by_sku = {row["sku_id"]: row["inbound_stock"] for row in inbound_query}

        # Fallback: include legacy fact_po_lines rows not represented in po_line
        # (Dim_PO_Header ETA + Fact_PO_Lines import path)
        if _table_exists("fact_po_lines"):
            po_line_ids = set()
            if _table_exists("po_line"):
                po_line_ids = {
                    row["po_id"] for row in conn.execute(
                        "SELECT DISTINCT po_id FROM po_line"
                    ).fetchall()
                }
            placeholders = ",".join("?" for _ in po_line_ids) if po_line_ids else ""
            po_line_filter = f"AND po_id NOT IN ({placeholders})" if po_line_ids else ""
            params = [snapshot_date.isoformat()]
            if po_line_ids:
                params.extend(sorted(po_line_ids))

            inbound_fallback = conn.execute(f"""
                SELECT
                    po_id,
                    sku_id,
                    sku_key,
                    my_size,
                    SUM(order_quantity - received_qty) as inbound_stock
                FROM fact_po_lines
                WHERE (order_quantity - received_qty) > 0
                  AND (est_arrival_date IS NULL OR est_arrival_date >= ?)
                  AND status NOT IN ('ARRIVED', 'CLOSED', 'CANCELLED', 'RECEIVED')
                  {po_line_filter}
                GROUP BY po_id, sku_id, sku_key, my_size
            """, params).fetchall()

            for row in inbound_fallback:
                sku_id = row["sku_id"]
                inbound_by_sku[sku_id] = inbound_by_sku.get(sku_id, 0) + row["inbound_stock"]

        # Step 3: Delete existing snapshot for this date
        # Note: fact_inventory_snapshot_size doesn't have store_code column
        conn.execute("""
            DELETE FROM fact_inventory_snapshot_size
            WHERE snapshot_date = ?
        """, (snapshot_date.isoformat(),))

        # Step 4: Insert new snapshot rows
        # Include all active sizes even if they have no ledger events yet.
        if _table_exists("dim_sku") and _table_has_column("dim_sku_size", "active_flag") and _table_has_column("dim_sku", "active_flag"):
            active_sizes = conn.execute("""
                SELECT ds.sku_id, ds.sku_key, ds.my_size
                FROM dim_sku_size ds
                JOIN dim_sku d ON ds.sku_key = d.sku_key
                WHERE ds.active_flag = 1
                  AND d.active_flag = 1
                  AND ds.my_size IS NOT NULL
                  AND ds.my_size != ''
            """).fetchall()
        else:
            active_sizes = conn.execute("""
                SELECT sku_id, sku_key, my_size
                FROM dim_sku_size
                WHERE my_size IS NOT NULL
                  AND my_size != ''
            """).fetchall()

        base_rows = {
            row["sku_id"]: (row["sku_key"], row["my_size"])
            for row in active_sizes
        }

        for row in ledger_balances:
            base_rows.setdefault(row["sku_id"], (row["sku_key"], row["my_size"]))

        inbound_missing = [sku_id for sku_id in inbound_by_sku if sku_id not in base_rows]
        if inbound_missing:
            placeholders = ",".join("?" for _ in inbound_missing)
            size_rows = conn.execute(f"""
                SELECT sku_id, sku_key, my_size
                FROM dim_sku_size
                WHERE sku_id IN ({placeholders})
            """, inbound_missing).fetchall()
            for row in size_rows:
                base_rows.setdefault(row["sku_id"], (row["sku_key"], row["my_size"]))

            still_missing = [sku_id for sku_id in inbound_missing if sku_id not in base_rows]
            if still_missing:
                placeholders = ",".join("?" for _ in still_missing)
                fallback_rows = conn.execute(f"""
                    SELECT sku_id, sku_key, my_size
                    FROM fact_po_lines
                    WHERE sku_id IN ({placeholders})
                    UNION
                    SELECT sku_id, sku_key, my_size
                    FROM po_line
                    WHERE sku_id IN ({placeholders})
                """, still_missing * 2).fetchall()
                for row in fallback_rows:
                    base_rows.setdefault(row["sku_id"], (row["sku_key"], row["my_size"]))

        ledger_by_sku: dict[str, int] = {}
        for row in ledger_balances:
            sku_id = row["sku_id"]
            ledger_by_sku[sku_id] = ledger_by_sku.get(sku_id, 0) + (row["current_stock"] or 0)

        accepted_negative_active_zero_skus = get_accepted_negative_active_zero_sku_ids(conn)

        inserted = 0
        for sku_id in sorted(base_rows.keys()):
            sku_key, my_size = base_rows[sku_id]
            current_stock = ledger_by_sku.get(sku_id, 0)
            if current_stock < 0 and sku_id in accepted_negative_active_zero_skus:
                current_stock = 0
            inbound_stock = inbound_by_sku.get(sku_id, 0)

            conn.execute("""
                INSERT INTO fact_inventory_snapshot_size
                (sku_id, sku_key, my_size, current_stock, inbound_stock, snapshot_date)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (
                sku_id,
                sku_key,
                my_size,
                current_stock,
                inbound_stock,
                snapshot_date.isoformat(),
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
        params = [as_of_date.isoformat()]
        if store_code and store_code != ALL_STORES_CODE:
            store_filter = "WHERE store_code = ? AND event_date <= ?"
            params.insert(0, store_code)
        else:
            store_filter = "WHERE event_date <= ?"

        rows = conn.execute(f"""
            SELECT
                event_type,
                COUNT(*) as event_count,
                SUM(qty_change) as qty_total
            FROM stock_ledger
            {store_filter}
            GROUP BY event_type
        """, params).fetchall()

        result = {}
        for row in rows:
            result[row["event_type"]] = {
                "count": row["event_count"],
                "qty_total": row["qty_total"],
            }

        return result
