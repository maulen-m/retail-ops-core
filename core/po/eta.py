"""
TASK-180: ETA Calculation Module (Phase 10)

Calculates Estimated Time of Arrival for Purchase Orders.

Lead Time Rules:
- Supplier prep: weight_kg / 70 kg per day, max 20 days
- Supplier → China warehouse: 1-2 days
- Cargo ship → Astana: L = 21 days total
- Almaty → Astana: ~3 days (part of L=21)

Key dates:
- message_date / order_date: When PO was created/sent
- ship_date_seller: When supplier shipped
- ship_date_cargo: When cargo company shipped
- alm_arrival_nom: Nominal ETA to Almaty
- ast_arrival_nom: Nominal ETA to Astana
"""

import math
from datetime import date, timedelta
from pathlib import Path
from typing import Optional

from core.db import get_db, DEFAULT_DB_PATH


# Lead time constants
CARGO_TO_ALM_DAYS = 18  # From cargo ship to Almaty
ALM_TO_AST_DAYS = 3      # From Almaty to Astana
TOTAL_CARGO_DAYS = 21    # Total: ship_date_cargo → ast_arrival
SELLER_TO_CARGO_DAYS = 2 # Seller → cargo handoff

# Prep estimation
DEFAULT_KG_PER_DAY = 70  # Supplier can prep ~70kg per day
MAX_PREP_DAYS = 20       # Cap prep time estimation


def estimate_prep_days(weight_kg: float, max_days: int = MAX_PREP_DAYS) -> int:
    """
    Estimate supplier prep days based on weight.

    Formula: ceil(weight_kg / 70), capped at max_days.

    Args:
        weight_kg: Total weight in kg
        max_days: Maximum prep days (default: 20)

    Returns:
        Estimated prep days
    """
    if weight_kg <= 0:
        return 1  # Minimum 1 day

    days = math.ceil(weight_kg / DEFAULT_KG_PER_DAY)
    return min(days, max_days)


def calc_eta(
    order_date: Optional[date] = None,
    ship_date_seller: Optional[date] = None,
    ship_date_cargo: Optional[date] = None,
    weight_kg: float = 0,
    delay_days: int = 0,
) -> tuple[Optional[date], Optional[date]]:
    """
    Calculate nominal ETAs (Almaty and Astana).

    Logic priority:
    1. If ship_date_cargo set:
       - alm_arrival_nom = ship_date_cargo + 18 days
       - ast_arrival_nom = ship_date_cargo + 21 days + delay
    2. Elif ship_date_seller set:
       - alm_arrival_nom = ship_date_seller + 20 days (2 days to cargo + 18)
       - ast_arrival_nom = ship_date_seller + 23 days + delay
    3. Elif order_date set:
       - Estimate: prep + seller_to_cargo + transit
       - alm_arrival_nom = order_date + est_prep_days + 20 days
       - ast_arrival_nom = order_date + est_prep_days + 23 days + delay

    Args:
        order_date: When PO was created/sent (message_date)
        ship_date_seller: When supplier shipped
        ship_date_cargo: When cargo company shipped
        weight_kg: PO total weight (for prep estimation)
        delay_days: Additional delay to add to AST arrival

    Returns:
        Tuple of (alm_arrival_nom, ast_arrival_nom) or (None, None) if no dates
    """
    alm_arrival_nom = None
    ast_arrival_nom = None

    if ship_date_cargo:
        # Most accurate: we know when cargo shipped
        alm_arrival_nom = ship_date_cargo + timedelta(days=CARGO_TO_ALM_DAYS)
        ast_arrival_nom = ship_date_cargo + timedelta(days=TOTAL_CARGO_DAYS + delay_days)

    elif ship_date_seller:
        # We know when seller shipped, add 2 days for cargo handoff
        seller_to_alm = SELLER_TO_CARGO_DAYS + CARGO_TO_ALM_DAYS  # 20 days
        seller_to_ast = SELLER_TO_CARGO_DAYS + TOTAL_CARGO_DAYS  # 23 days
        alm_arrival_nom = ship_date_seller + timedelta(days=seller_to_alm)
        ast_arrival_nom = ship_date_seller + timedelta(days=seller_to_ast + delay_days)

    elif order_date:
        # Only have order date, estimate prep time
        prep_days = estimate_prep_days(weight_kg) if weight_kg > 0 else 7  # Default 7 days prep
        order_to_alm = prep_days + SELLER_TO_CARGO_DAYS + CARGO_TO_ALM_DAYS
        order_to_ast = prep_days + SELLER_TO_CARGO_DAYS + TOTAL_CARGO_DAYS
        alm_arrival_nom = order_date + timedelta(days=order_to_alm)
        ast_arrival_nom = order_date + timedelta(days=order_to_ast + delay_days)

    return alm_arrival_nom, ast_arrival_nom


def update_po_eta(
    po_id: str,
    delay_days: int = 0,
    db_path: Optional[Path] = None,
) -> tuple[Optional[date], Optional[date]]:
    """
    Update ETA fields for a specific PO.

    Reads PO dates from po_header and updates alm_arrival_nom, ast_arrival_nom.

    Args:
        po_id: PO ID
        delay_days: Additional delay days
        db_path: Database path

    Returns:
        Tuple of (alm_arrival_nom, ast_arrival_nom)
    """
    if db_path is None:
        db_path = DEFAULT_DB_PATH

    with get_db(db_path) as conn:
        po = conn.execute("""
            SELECT order_date, ship_date_seller, ship_date_cargo, weight_kg
            FROM po_header
            WHERE po_id = ?
        """, (po_id,)).fetchone()

        if not po:
            return None, None

        # Parse dates
        order_date = date.fromisoformat(po["order_date"]) if po["order_date"] else None
        ship_date_seller = date.fromisoformat(po["ship_date_seller"]) if po["ship_date_seller"] else None
        ship_date_cargo = date.fromisoformat(po["ship_date_cargo"]) if po["ship_date_cargo"] else None
        weight_kg = po["weight_kg"] or 0

        # Calculate ETAs
        alm_nom, ast_nom = calc_eta(
            order_date=order_date,
            ship_date_seller=ship_date_seller,
            ship_date_cargo=ship_date_cargo,
            weight_kg=weight_kg,
            delay_days=delay_days,
        )

        # Update PO header
        if alm_nom or ast_nom:
            conn.execute("""
                UPDATE po_header
                SET alm_arrival_nom = ?,
                    ast_arrival_nom = ?
                WHERE po_id = ?
            """, (
                alm_nom.isoformat() if alm_nom else None,
                ast_nom.isoformat() if ast_nom else None,
                po_id,
            ))

    return alm_nom, ast_nom


def recalc_all_etas(
    delay_days: int = 0,
    db_path: Optional[Path] = None,
) -> int:
    """
    Recalculate ETAs for all non-closed POs.

    Args:
        delay_days: Additional delay to add
        db_path: Database path

    Returns:
        Count of POs updated
    """
    if db_path is None:
        db_path = DEFAULT_DB_PATH

    updated = 0

    with get_db(db_path) as conn:
        # Get all non-closed POs
        rows = conn.execute("""
            SELECT po_id, order_date, ship_date_seller, ship_date_cargo, weight_kg
            FROM po_header
            WHERE status NOT IN ('CLOSED', 'RECEIVED')
        """).fetchall()

        for row in rows:
            po_id = row["po_id"]

            # Parse dates
            order_date = date.fromisoformat(row["order_date"]) if row["order_date"] else None
            ship_date_seller = date.fromisoformat(row["ship_date_seller"]) if row["ship_date_seller"] else None
            ship_date_cargo = date.fromisoformat(row["ship_date_cargo"]) if row["ship_date_cargo"] else None
            weight_kg = row["weight_kg"] or 0

            # Calculate ETAs
            alm_nom, ast_nom = calc_eta(
                order_date=order_date,
                ship_date_seller=ship_date_seller,
                ship_date_cargo=ship_date_cargo,
                weight_kg=weight_kg,
                delay_days=delay_days,
            )

            # Update if we have ETAs
            if alm_nom or ast_nom:
                conn.execute("""
                    UPDATE po_header
                    SET alm_arrival_nom = ?,
                        ast_arrival_nom = ?
                    WHERE po_id = ?
                """, (
                    alm_nom.isoformat() if alm_nom else None,
                    ast_nom.isoformat() if ast_nom else None,
                    po_id,
                ))
                updated += 1

    return updated


def get_eta_status(
    ast_arrival_nom: date,
    current_date: date = None,
) -> str:
    """
    Get ETA status relative to current date.

    Returns:
        - "ON_TIME" if arrival is in the future
        - "DUE_SOON" if arrival within 3 days
        - "OVERDUE" if past nominal arrival
    """
    if current_date is None:
        current_date = date.today()

    days_until = (ast_arrival_nom - current_date).days

    if days_until < 0:
        return "OVERDUE"
    elif days_until <= 3:
        return "DUE_SOON"
    else:
        return "ON_TIME"


def calc_days_until_arrival(
    ast_arrival_nom: date,
    current_date: date = None,
) -> int:
    """
    Calculate days until nominal Astana arrival.

    Args:
        ast_arrival_nom: Nominal Astana arrival date
        current_date: Reference date (default: today)

    Returns:
        Days until arrival (negative if overdue)
    """
    if current_date is None:
        current_date = date.today()

    return (ast_arrival_nom - current_date).days
