"""
TASK-179: PO Lifecycle Module (Phase 10)

Manages Purchase Order lifecycle: create, update, arrive, receive, close.

Status Flow:
DRAFT → SENT → PREPARING → SHIPPED_SELLER → SHIPPED_CARGO → IN_TRANSIT →
ARRIVED_ALM → ARRIVED_AST → RECEIVED → CLOSED

Key Constraints:
- archive_alm_arrival and archive_ast_arrival are IMMUTABLE once set
- Lead time L = 21 days (ship_date_cargo → ast_arrival_date)
- FX rates entered manually (CNY/KZT after supplier payment, USD/KZT at cargo arrival)
- Cargo rate = 2.66 USD/kg for clothes

Tables used:
- po_header: PO lifecycle with dates, costs, FX rates
- po_line: Size-level PO items
- stock_ledger: INBOUND events when PO arrives
- fact_input_audit: Audit logging for changes
"""

import sqlite3
from datetime import date, datetime
from pathlib import Path
from typing import Optional

from core.db import get_db, DEFAULT_DB_PATH
from core.db.ledger import add_ledger_event, log_audit


# PO Status Flow - ordered from start to end
PO_STATUS_FLOW = [
    "DRAFT",           # Initial state
    "SENT",            # Sent to supplier
    "PREPARING",       # Supplier preparing order
    "SHIPPED_SELLER",  # Shipped from seller
    "SHIPPED_CARGO",   # Handed to cargo company
    "IN_TRANSIT",      # In transit
    "ARRIVED_ALM",     # Arrived in Almaty
    "ARRIVED_AST",     # Arrived in Astana
    "RECEIVED",        # Received and counted
    "CLOSED",          # Fully processed
]

# Fields that are immutable once set
IMMUTABLE_FIELDS = frozenset([
    "archive_alm_arrival",
    "archive_ast_arrival",
])

# Date fields that trigger status updates
DATE_STATUS_MAP = {
    "order_date": "SENT",
    "ship_date_seller": "SHIPPED_SELLER",
    "ship_date_cargo": "SHIPPED_CARGO",
    "alm_arrival_date": "ARRIVED_ALM",
    "ast_arrival_date": "ARRIVED_AST",
}


def generate_po_id(prefix: str = "PO", db_path: Optional[Path] = None) -> str:
    """
    Generate a unique PO ID.

    Format: PO-YYYY-NNN (e.g., PO-2025-001)
    """
    if db_path is None:
        db_path = DEFAULT_DB_PATH

    year = date.today().year

    with get_db(db_path) as conn:
        # Get the max PO number for this year
        result = conn.execute("""
            SELECT MAX(CAST(SUBSTR(po_id, -3) AS INTEGER)) as max_num
            FROM po_header
            WHERE po_id LIKE ?
        """, (f"{prefix}-{year}-%",)).fetchone()

        next_num = (result["max_num"] or 0) + 1

    return f"{prefix}-{year}-{next_num:03d}"


def create_po(
    supplier_code: str,
    po_id: str = None,
    order_date: date = None,
    notes: str = None,
    created_by: str = "system",
    db_path: Optional[Path] = None,
) -> str:
    """
    Create a new PO in DRAFT status.

    Args:
        supplier_code: Supplier code (e.g., SUPP_A, SUPP_B)
        po_id: Optional custom PO ID (auto-generated if not provided)
        order_date: Order date (sets status to SENT if provided)
        notes: Optional notes
        created_by: User creating the PO
        db_path: Database path

    Returns:
        po_id of the created PO
    """
    if db_path is None:
        db_path = DEFAULT_DB_PATH

    if po_id is None:
        po_id = generate_po_id(db_path=db_path)

    status = "DRAFT"
    if order_date:
        status = "SENT"

    with get_db(db_path) as conn:
        conn.execute("""
            INSERT INTO po_header (
                po_id, supplier_code, status, order_date, notes, created_by
            ) VALUES (?, ?, ?, ?, ?, ?)
        """, (
            po_id,
            supplier_code,
            status,
            order_date.isoformat() if order_date else None,
            notes,
            created_by,
        ))

    # Audit logging for PO creation
    log_audit(
        table_name="po_header",
        record_id=po_id,
        field_name="*",
        old_value=None,
        new_value=f"supplier={supplier_code}, status={status}",
        change_type="INSERT",
        source=created_by,
        db_path=db_path,
    )

    return po_id


def add_po_line(
    po_id: str,
    sku_id: str,
    order_qty: int,
    unit_cost_cny: float,
    sku_key: str = None,
    my_size: str = None,
    db_path: Optional[Path] = None,
) -> int:
    """
    Add a line item to a PO.

    Args:
        po_id: PO ID
        sku_id: Size-level SKU
        order_qty: Quantity ordered
        unit_cost_cny: Unit cost in CNY
        sku_key: Style-level SKU (auto-derived if not provided)
        my_size: Size label (auto-derived if not provided)
        db_path: Database path

    Returns:
        po_line_id of the created line
    """
    if db_path is None:
        db_path = DEFAULT_DB_PATH

    with get_db(db_path) as conn:
        # Auto-derive sku_key and my_size if not provided
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
                # Fallback: extract from sku_id pattern
                parts = sku_id.rsplit("_", 1)
                if len(parts) == 2:
                    if sku_key is None:
                        sku_key = parts[0]
                    if my_size is None:
                        my_size = parts[1]
                else:
                    if my_size is None:
                        my_size = "UNKNOWN"
                    if sku_key is None:
                        sku_key = sku_id

        cursor = conn.execute("""
            INSERT INTO po_line (
                po_id, sku_key, sku_id, my_size, order_qty,
                received_qty, unit_cost_cny, status
            ) VALUES (?, ?, ?, ?, ?, 0, ?, 'PENDING')
        """, (
            po_id,
            sku_key,
            sku_id,
            my_size,
            order_qty,
            unit_cost_cny,
        ))

        po_line_id = cursor.lastrowid

    # Audit logging for PO line creation
    log_audit(
        table_name="po_line",
        record_id=str(po_line_id),
        field_name="*",
        old_value=None,
        new_value=f"po_id={po_id}, sku_id={sku_id}, qty={order_qty}",
        change_type="INSERT",
        source="SYSTEM",
        db_path=db_path,
    )

    return po_line_id


def get_po(po_id: str, db_path: Optional[Path] = None) -> dict:
    """
    Get PO header by ID.

    Args:
        po_id: PO ID
        db_path: Database path

    Returns:
        PO header dict or None
    """
    if db_path is None:
        db_path = DEFAULT_DB_PATH

    with get_db(db_path) as conn:
        row = conn.execute("""
            SELECT * FROM po_header WHERE po_id = ?
        """, (po_id,)).fetchone()

        return dict(row) if row else None


def get_po_lines(po_id: str, db_path: Optional[Path] = None) -> list[dict]:
    """
    Get all lines for a PO.

    Args:
        po_id: PO ID
        db_path: Database path

    Returns:
        List of PO line dicts
    """
    if db_path is None:
        db_path = DEFAULT_DB_PATH

    with get_db(db_path) as conn:
        rows = conn.execute("""
            SELECT * FROM po_line WHERE po_id = ? ORDER BY po_line_id
        """, (po_id,)).fetchall()

        return [dict(row) for row in rows]


def update_po_field(
    po_id: str,
    field_name: str,
    new_value,
    updated_by: str = "system",
    db_path: Optional[Path] = None,
) -> bool:
    """
    Update a single field on a PO header.

    Respects immutable fields and auto-updates status based on date fields.

    Args:
        po_id: PO ID
        field_name: Field to update
        new_value: New value
        updated_by: User making the update
        db_path: Database path

    Returns:
        True if updated, False if rejected

    Raises:
        ValueError: If field is immutable and already set
    """
    if db_path is None:
        db_path = DEFAULT_DB_PATH

    with get_db(db_path) as conn:
        # Get current PO state
        po = conn.execute("""
            SELECT * FROM po_header WHERE po_id = ?
        """, (po_id,)).fetchone()

        if not po:
            raise ValueError(f"PO not found: {po_id}")

        # Check immutable fields
        if field_name in IMMUTABLE_FIELDS:
            current_value = po[field_name]
            if current_value is not None:
                raise ValueError(
                    f"Field '{field_name}' is immutable once set. "
                    f"Current value: {current_value}"
                )

        old_value = po[field_name]

        # Convert date to ISO format if needed
        if isinstance(new_value, date):
            new_value = new_value.isoformat()

        # Update the field
        conn.execute(f"""
            UPDATE po_header
            SET {field_name} = ?, updated_at = ?
            WHERE po_id = ?
        """, (new_value, datetime.now().isoformat(), po_id))

        # Auto-update status based on date fields
        if field_name in DATE_STATUS_MAP and new_value:
            new_status = DATE_STATUS_MAP[field_name]
            current_status_idx = PO_STATUS_FLOW.index(po["status"])
            new_status_idx = PO_STATUS_FLOW.index(new_status)

            # Only advance status (never go backwards)
            if new_status_idx > current_status_idx:
                conn.execute("""
                    UPDATE po_header SET status = ? WHERE po_id = ?
                """, (new_status, po_id))

    # Log to audit (outside transaction for consistency)
    log_audit(
        table_name="po_header",
        record_id=po_id,
        field_name=field_name,
        old_value=old_value,
        new_value=new_value,
        change_type="UPDATE",
        source=updated_by,
        db_path=db_path,
    )

    return True


def update_po_status(
    po_id: str,
    new_status: str,
    updated_by: str = "system",
    db_path: Optional[Path] = None,
) -> bool:
    """
    Update PO status.

    Args:
        po_id: PO ID
        new_status: New status (must be valid)
        updated_by: User making the update
        db_path: Database path

    Returns:
        True if updated

    Raises:
        ValueError: If status is invalid or would go backwards
    """
    if new_status not in PO_STATUS_FLOW:
        raise ValueError(f"Invalid status: {new_status}. Must be one of {PO_STATUS_FLOW}")

    if db_path is None:
        db_path = DEFAULT_DB_PATH

    with get_db(db_path) as conn:
        po = conn.execute("""
            SELECT status FROM po_header WHERE po_id = ?
        """, (po_id,)).fetchone()

        if not po:
            raise ValueError(f"PO not found: {po_id}")

        old_status = po["status"]
        old_idx = PO_STATUS_FLOW.index(old_status)
        new_idx = PO_STATUS_FLOW.index(new_status)

        if new_idx < old_idx:
            raise ValueError(
                f"Cannot move status backwards: {old_status} → {new_status}"
            )

        conn.execute("""
            UPDATE po_header
            SET status = ?, updated_at = ?
            WHERE po_id = ?
        """, (new_status, datetime.now().isoformat(), po_id))

    # Log to audit (outside transaction for consistency)
    log_audit(
        table_name="po_header",
        record_id=po_id,
        field_name="status",
        old_value=old_status,
        new_value=new_status,
        change_type="UPDATE",
        source=updated_by,
        db_path=db_path,
    )

    return True


def confirm_po_arrival(
    po_id: str,
    arrival_type: str,
    arrival_date: date = None,
    received_qty_by_sku: dict[str, int] = None,
    create_ledger_events: bool = True,
    updated_by: str = "system",
    db_path: Optional[Path] = None,
) -> dict:
    """
    Confirm PO arrival (ALM or AST) and optionally create INBOUND ledger events.

    Args:
        po_id: PO ID
        arrival_type: 'ALM' or 'AST'
        arrival_date: Arrival date (default: today)
        received_qty_by_sku: Dict of {sku_id: received_qty} (default: full order_qty)
        create_ledger_events: Whether to create INBOUND events
        updated_by: User confirming arrival
        db_path: Database path

    Returns:
        Dict with {lines_updated, units_received, ledger_events}
    """
    if arrival_type not in ("ALM", "AST"):
        raise ValueError(f"arrival_type must be 'ALM' or 'AST', got: {arrival_type}")

    if arrival_date is None:
        arrival_date = date.today()

    if db_path is None:
        db_path = DEFAULT_DB_PATH

    result = {
        "lines_updated": 0,
        "units_received": 0,
        "ledger_events": 0,
    }

    # Queue ledger events
    pending_ledger_events = []

    with get_db(db_path) as conn:
        # Get PO
        po = conn.execute("""
            SELECT * FROM po_header WHERE po_id = ?
        """, (po_id,)).fetchone()

        if not po:
            raise ValueError(f"PO not found: {po_id}")

        # Update arrival date
        date_field = "alm_arrival_real" if arrival_type == "ALM" else "ast_arrival_real"
        archive_field = f"archive_{date_field.replace('_real', '')}"

        # Set archive field if not already set
        if po[archive_field] is None:
            conn.execute(f"""
                UPDATE po_header
                SET {archive_field} = ?, updated_at = ?
                WHERE po_id = ?
            """, (arrival_date.isoformat(), datetime.now().isoformat(), po_id))

        # Update arrival date
        conn.execute(f"""
            UPDATE po_header
            SET {date_field} = ?, status = ?, updated_at = ?
            WHERE po_id = ?
        """, (
            arrival_date.isoformat(),
            "ARRIVED_ALM" if arrival_type == "ALM" else "ARRIVED_AST",
            datetime.now().isoformat(),
            po_id,
        ))

        # Get PO lines
        lines = conn.execute("""
            SELECT * FROM po_line WHERE po_id = ?
        """, (po_id,)).fetchall()

        for line in lines:
            sku_id = line["sku_id"]
            order_qty = line["order_qty"]
            current_received = line["received_qty"]

            # Determine received quantity
            if received_qty_by_sku and sku_id in received_qty_by_sku:
                received_qty = received_qty_by_sku[sku_id]
            else:
                # Default: full order quantity
                received_qty = order_qty

            # Skip if already fully received
            if current_received >= order_qty:
                continue

            # Calculate quantity to add
            qty_to_add = min(received_qty, order_qty - current_received)
            if qty_to_add <= 0:
                continue

            new_received = current_received + qty_to_add

            # Update line
            line_status = "RECEIVED" if new_received >= order_qty else "PARTIAL"
            conn.execute("""
                UPDATE po_line
                SET received_qty = ?, status = ?
                WHERE po_line_id = ?
            """, (new_received, line_status, line["po_line_id"]))

            result["lines_updated"] += 1
            result["units_received"] += qty_to_add

            # Queue INBOUND ledger event
            if create_ledger_events:
                pending_ledger_events.append({
                    "sku_id": sku_id,
                    "qty_change": qty_to_add,
                    "sku_key": line["sku_key"],
                    "my_size": line["my_size"],
                })

    # Create ledger events outside transaction
    for event in pending_ledger_events:
        add_ledger_event(
            event_type="INBOUND",
            sku_id=event["sku_id"],
            qty_change=event["qty_change"],
            event_date=arrival_date,
            sku_key=event["sku_key"],
            my_size=event["my_size"],
            reference_id=po_id,
            reference_type="PO",
            notes=f"Arrival at {arrival_type}",
            input_source="SYSTEM",
            created_by=updated_by,
            db_path=db_path,
        )
        result["ledger_events"] += 1

    return result


def close_po(
    po_id: str,
    updated_by: str = "system",
    db_path: Optional[Path] = None,
) -> bool:
    """
    Close a PO (mark as CLOSED).

    PO must be in RECEIVED status.

    Args:
        po_id: PO ID
        updated_by: User closing the PO
        db_path: Database path

    Returns:
        True if closed

    Raises:
        ValueError: If PO not in RECEIVED status
    """
    if db_path is None:
        db_path = DEFAULT_DB_PATH

    with get_db(db_path) as conn:
        po = conn.execute("""
            SELECT status FROM po_header WHERE po_id = ?
        """, (po_id,)).fetchone()

        if not po:
            raise ValueError(f"PO not found: {po_id}")

        if po["status"] != "RECEIVED":
            raise ValueError(
                f"Cannot close PO in status '{po['status']}'. "
                f"Must be in RECEIVED status."
            )

        conn.execute("""
            UPDATE po_header
            SET status = 'CLOSED', closed_at = ?, updated_at = ?
            WHERE po_id = ?
        """, (datetime.now().isoformat(), datetime.now().isoformat(), po_id))

    # Log to audit (outside transaction for consistency)
    log_audit(
        table_name="po_header",
        record_id=po_id,
        field_name="status",
        old_value="RECEIVED",
        new_value="CLOSED",
        change_type="UPDATE",
        source=updated_by,
        db_path=db_path,
    )

    return True


def receive_po_line(
    po_line_id: int,
    received_qty: int,
    create_ledger_event: bool = True,
    updated_by: str = "system",
    db_path: Optional[Path] = None,
) -> dict:
    """
    Receive a specific PO line (partial or full).

    Args:
        po_line_id: PO line ID
        received_qty: Quantity to receive
        create_ledger_event: Whether to create INBOUND event
        updated_by: User receiving
        db_path: Database path

    Returns:
        Dict with {sku_id, qty_received, new_total, status, ledger_created}
    """
    if db_path is None:
        db_path = DEFAULT_DB_PATH

    result = {}
    pending_event = None

    with get_db(db_path) as conn:
        line = conn.execute("""
            SELECT * FROM po_line WHERE po_line_id = ?
        """, (po_line_id,)).fetchone()

        if not line:
            raise ValueError(f"PO line not found: {po_line_id}")

        sku_id = line["sku_id"]
        order_qty = line["order_qty"]
        current_received = line["received_qty"]

        # Calculate new total
        qty_to_add = min(received_qty, order_qty - current_received)
        if qty_to_add <= 0:
            return {
                "sku_id": sku_id,
                "qty_received": 0,
                "new_total": current_received,
                "status": line["status"],
                "ledger_created": False,
            }

        new_total = current_received + qty_to_add
        new_status = "RECEIVED" if new_total >= order_qty else "PARTIAL"

        # Update line
        conn.execute("""
            UPDATE po_line
            SET received_qty = ?, status = ?
            WHERE po_line_id = ?
        """, (new_total, new_status, po_line_id))

        result = {
            "sku_id": sku_id,
            "qty_received": qty_to_add,
            "new_total": new_total,
            "status": new_status,
            "ledger_created": False,
        }

        # Queue ledger event
        if create_ledger_event and qty_to_add > 0:
            pending_event = {
                "sku_id": sku_id,
                "qty_change": qty_to_add,
                "po_id": line["po_id"],
                "sku_key": line["sku_key"],
                "my_size": line["my_size"],
            }

    # Create ledger event outside transaction
    if pending_event:
        add_ledger_event(
            event_type="INBOUND",
            sku_id=pending_event["sku_id"],
            qty_change=pending_event["qty_change"],
            event_date=date.today(),
            sku_key=pending_event["sku_key"],
            my_size=pending_event["my_size"],
            reference_id=pending_event["po_id"],
            reference_type="PO",
            notes="Line received",
            input_source="SYSTEM",
            created_by=updated_by,
            db_path=db_path,
        )
        result["ledger_created"] = True

    return result
