"""
TASK-181: Landed Cost Calculation Module (Phase 10)

Calculates landed costs for Purchase Orders.

Cost Structure:
- Supplier cost: unit_cost_cny × fx_rate_cny_actual (after payment)
- Cargo cost: weight_real_kg × 2.66 × fx_rate_usd_kzt (after AST arrival)
- Landed cost per unit: unit_cost_kzt + (freight_share / order_qty)

Key rates:
- Cargo rate: 2.66 USD/kg for clothes
- FX rates are entered manually after payment/arrival
"""

from pathlib import Path
from typing import Optional

from core.db import get_db, DEFAULT_DB_PATH


# Constants
CARGO_RATE_USD_PER_KG = 2.66  # USD per kg for clothes


def calc_supplier_costs(
    po_id: str,
    db_path: Optional[Path] = None,
) -> dict:
    """
    Calculate supplier costs after fx_rate_cny_actual is set.

    Updates:
    - po_line.unit_cost_kzt for each line
    - po_header.total_cost_kzt_supplier

    Args:
        po_id: PO ID
        db_path: Database path

    Returns:
        Dict with {lines_updated, total_supplier_kzt}

    Raises:
        ValueError: If fx_rate_cny_actual not set
    """
    if db_path is None:
        db_path = DEFAULT_DB_PATH

    result = {
        "lines_updated": 0,
        "total_supplier_kzt": 0,
    }

    with get_db(db_path) as conn:
        # Get PO and FX rate
        po = conn.execute("""
            SELECT fx_rate_cny_actual FROM po_header WHERE po_id = ?
        """, (po_id,)).fetchone()

        if not po:
            raise ValueError(f"PO not found: {po_id}")

        fx_rate = po["fx_rate_cny_actual"]
        if not fx_rate:
            raise ValueError(f"fx_rate_cny_actual not set for PO {po_id}")

        # Get lines and update costs
        lines = conn.execute("""
            SELECT po_line_id, unit_cost_cny, order_qty
            FROM po_line WHERE po_id = ?
        """, (po_id,)).fetchall()

        total_supplier_kzt = 0

        for line in lines:
            unit_cost_kzt = line["unit_cost_cny"] * fx_rate
            line_total_kzt = unit_cost_kzt * line["order_qty"]
            total_supplier_kzt += line_total_kzt

            conn.execute("""
                UPDATE po_line SET unit_cost_kzt = ?
                WHERE po_line_id = ?
            """, (unit_cost_kzt, line["po_line_id"]))

            result["lines_updated"] += 1

        # Update PO header
        conn.execute("""
            UPDATE po_header SET total_cost_kzt_supplier = ?
            WHERE po_id = ?
        """, (total_supplier_kzt, po_id))

        result["total_supplier_kzt"] = total_supplier_kzt

    return result


def calc_cargo_costs(
    po_id: str,
    cargo_rate_usd: float = CARGO_RATE_USD_PER_KG,
    db_path: Optional[Path] = None,
) -> dict:
    """
    Calculate cargo costs after weight_real_kg and fx_rate_usd_kzt are set.

    Updates:
    - po_header.cargo_cost_usd
    - po_header.cargo_cost_kzt

    Args:
        po_id: PO ID
        cargo_rate_usd: USD per kg rate (default: 2.66)
        db_path: Database path

    Returns:
        Dict with {weight_kg, cargo_cost_usd, cargo_cost_kzt}

    Raises:
        ValueError: If weight_real_kg or fx_rate_usd_kzt not set
    """
    if db_path is None:
        db_path = DEFAULT_DB_PATH

    with get_db(db_path) as conn:
        po = conn.execute("""
            SELECT weight_real_kg, fx_rate_usd_kzt
            FROM po_header WHERE po_id = ?
        """, (po_id,)).fetchone()

        if not po:
            raise ValueError(f"PO not found: {po_id}")

        weight_kg = po["weight_real_kg"]
        fx_rate = po["fx_rate_usd_kzt"]

        if not weight_kg:
            raise ValueError(f"weight_real_kg not set for PO {po_id}")
        if not fx_rate:
            raise ValueError(f"fx_rate_usd_kzt not set for PO {po_id}")

        cargo_cost_usd = weight_kg * cargo_rate_usd
        cargo_cost_kzt = cargo_cost_usd * fx_rate

        conn.execute("""
            UPDATE po_header
            SET cargo_cost_usd = ?, cargo_cost_kzt = ?
            WHERE po_id = ?
        """, (cargo_cost_usd, cargo_cost_kzt, po_id))

    return {
        "weight_kg": weight_kg,
        "cargo_cost_usd": cargo_cost_usd,
        "cargo_cost_kzt": cargo_cost_kzt,
    }


def calc_landed_costs(
    po_id: str,
    db_path: Optional[Path] = None,
) -> dict:
    """
    Calculate full landed costs per line.

    For each po_line:
    1. Get weight share (proportional to order_qty if unit_weight not available)
    2. freight_share_kzt = cargo_cost_kzt × weight_share
    3. landed_cost_unit_kzt = unit_cost_kzt + (freight_share_kzt / order_qty)

    Updates:
    - po_line.freight_share_kzt
    - po_line.landed_cost_unit_kzt
    - po_header.total_landed_cost_kzt

    Args:
        po_id: PO ID
        db_path: Database path

    Returns:
        Dict with {lines_updated, total_landed_kzt}

    Raises:
        ValueError: If required costs not calculated
    """
    if db_path is None:
        db_path = DEFAULT_DB_PATH

    result = {
        "lines_updated": 0,
        "total_landed_kzt": 0,
    }

    with get_db(db_path) as conn:
        # Get PO costs
        po = conn.execute("""
            SELECT cargo_cost_kzt, total_cost_kzt_supplier
            FROM po_header WHERE po_id = ?
        """, (po_id,)).fetchone()

        if not po:
            raise ValueError(f"PO not found: {po_id}")

        cargo_cost_kzt = po["cargo_cost_kzt"]
        supplier_cost_kzt = po["total_cost_kzt_supplier"]

        if cargo_cost_kzt is None:
            raise ValueError(f"Cargo costs not calculated for PO {po_id}. Run calc_cargo_costs() first.")
        if supplier_cost_kzt is None:
            raise ValueError(f"Supplier costs not calculated for PO {po_id}. Run calc_supplier_costs() first.")

        # Get lines
        lines = conn.execute("""
            SELECT po_line_id, sku_id, order_qty, unit_cost_kzt
            FROM po_line WHERE po_id = ?
        """, (po_id,)).fetchall()

        # Calculate total quantity for weight share
        total_qty = sum(line["order_qty"] for line in lines)
        if total_qty == 0:
            return result

        total_landed_kzt = 0

        for line in lines:
            order_qty = line["order_qty"]
            unit_cost_kzt = line["unit_cost_kzt"] or 0

            # Weight share proportional to order quantity
            weight_share = order_qty / total_qty
            freight_share_kzt = cargo_cost_kzt * weight_share

            # Landed cost per unit
            landed_cost_unit = unit_cost_kzt + (freight_share_kzt / order_qty)
            line_landed_total = landed_cost_unit * order_qty
            total_landed_kzt += line_landed_total

            conn.execute("""
                UPDATE po_line
                SET freight_share_kzt = ?, landed_cost_unit_kzt = ?
                WHERE po_line_id = ?
            """, (freight_share_kzt, landed_cost_unit, line["po_line_id"]))

            result["lines_updated"] += 1

        # Update PO header total
        conn.execute("""
            UPDATE po_header SET total_landed_cost_kzt = ?
            WHERE po_id = ?
        """, (total_landed_kzt, po_id))

        result["total_landed_kzt"] = total_landed_kzt

    return result


def get_sku_landed_cost(
    po_id: str,
    sku_id: str,
    db_path: Optional[Path] = None,
) -> Optional[float]:
    """
    Get landed cost for specific SKU/size from a PO.

    Args:
        po_id: PO ID
        sku_id: SKU ID
        db_path: Database path

    Returns:
        Landed cost per unit in KZT, or None if not found
    """
    if db_path is None:
        db_path = DEFAULT_DB_PATH

    with get_db(db_path) as conn:
        row = conn.execute("""
            SELECT landed_cost_unit_kzt
            FROM po_line
            WHERE po_id = ? AND sku_id = ?
        """, (po_id, sku_id)).fetchone()

        if row:
            return row["landed_cost_unit_kzt"]
        return None


def calc_all_costs(
    po_id: str,
    db_path: Optional[Path] = None,
) -> dict:
    """
    Calculate all costs for a PO (supplier + cargo + landed).

    Convenience function that runs all cost calculations in sequence.

    Args:
        po_id: PO ID
        db_path: Database path

    Returns:
        Dict with full cost breakdown
    """
    if db_path is None:
        db_path = DEFAULT_DB_PATH

    result = {}

    # Run supplier costs
    try:
        supplier = calc_supplier_costs(po_id, db_path=db_path)
        result["supplier"] = supplier
    except ValueError as e:
        result["supplier_error"] = str(e)

    # Run cargo costs
    try:
        cargo = calc_cargo_costs(po_id, db_path=db_path)
        result["cargo"] = cargo
    except ValueError as e:
        result["cargo_error"] = str(e)

    # Run landed costs (only if supplier and cargo succeeded)
    if "supplier" in result and "cargo" in result:
        try:
            landed = calc_landed_costs(po_id, db_path=db_path)
            result["landed"] = landed
        except ValueError as e:
            result["landed_error"] = str(e)

    return result


def get_po_cost_summary(
    po_id: str,
    db_path: Optional[Path] = None,
) -> dict:
    """
    Get cost summary for a PO.

    Args:
        po_id: PO ID
        db_path: Database path

    Returns:
        Dict with cost breakdown
    """
    if db_path is None:
        db_path = DEFAULT_DB_PATH

    with get_db(db_path) as conn:
        po = conn.execute("""
            SELECT
                total_cost_kzt_supplier,
                cargo_cost_usd,
                cargo_cost_kzt,
                total_landed_cost_kzt,
                fx_rate_cny_actual,
                fx_rate_usd_kzt,
                weight_real_kg
            FROM po_header
            WHERE po_id = ?
        """, (po_id,)).fetchone()

        if not po:
            return {}

        return {
            "supplier_cost_kzt": po["total_cost_kzt_supplier"],
            "cargo_cost_usd": po["cargo_cost_usd"],
            "cargo_cost_kzt": po["cargo_cost_kzt"],
            "total_landed_kzt": po["total_landed_cost_kzt"],
            "fx_rate_cny": po["fx_rate_cny_actual"],
            "fx_rate_usd": po["fx_rate_usd_kzt"],
            "weight_kg": po["weight_real_kg"],
        }
