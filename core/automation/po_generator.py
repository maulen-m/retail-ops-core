"""
TASK-059: Auto PO Generator
TASK-166: Phase 9.6 Size-Aware Allocation Integration

Automatically generates PO drafts when conditions are met.

Phase 9.6 Changes:
- Added generate_po_draft_size_aware() using true size-level allocation
- Kept apply_size_splits() for backward compatibility
- New function uses OOS-filtered demand, per-size SS/ROP, and ROIC gate
"""

import sqlite3
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Optional

# Phase 9.6 imports
from core.calc.size_allocation import (
    generate_po_draft as calc_generate_po_draft,
    PODraft,
    ROICAction
)
from core.db.queries import (
    get_size_sales_history,
    get_size_stock_history,
    get_size_current_stock,
    get_size_inbound,
    get_size_sales_90d,
    get_sku_age_days
)


def calc_order_quantity(
    sku_key: str,
    current_stock: int,
    rop: int,
    d_forecast: float,
    l_days: int = 21,
    r_days: int = 10,
    on_order: int = 0
) -> int:
    """
    Calculate order quantity using T_post formula.

    Order_qty = max(0, ROP + D_forecast × (L + R) - current_stock - on_order)
    Round to nearest 5 for ordering convenience.

    Args:
        sku_key: SKU identifier
        current_stock: Current stock level
        rop: Reorder point
        d_forecast: Forecasted daily demand
        l_days: Lead time in days
        r_days: Review period in days
        on_order: Units already on order

    Returns:
        Suggested order quantity (rounded to nearest 5)
    """
    # Target = ROP + forecast coverage for L+R period
    target = rop + d_forecast * (l_days + r_days)

    # Available = current + on_order
    available = current_stock + on_order

    # Order quantity
    order_qty = max(0, target - available)

    # Round to nearest 5
    rounded = round(order_qty / 5) * 5

    return max(0, int(rounded))


def apply_size_splits(
    sku_key: str,
    total_qty: int,
    db_path: str
) -> dict[str, int]:
    """
    Split total quantity across sizes based on historical sales mix.

    Returns {size: qty} ensuring sum = total_qty.

    Args:
        sku_key: Style-level SKU key
        total_qty: Total quantity to split
        db_path: Path to database

    Returns:
        Dict mapping size to quantity
    """
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # Get historical size mix from last 90 days
    cursor.execute("""
        SELECT ss.my_size, SUM(d.units) as size_units
        FROM fact_sales_daily_size d
        JOIN dim_sku_size ss ON d.sku_id = ss.sku_id
        WHERE ss.sku_key = ?
        AND d.sale_date >= date('now', '-90 days')
        GROUP BY ss.my_size
        ORDER BY ss.size_order
    """, (sku_key,))

    size_data = cursor.fetchall()
    conn.close()

    if not size_data:
        # No history, use default split
        return {'M': total_qty // 3, 'L': total_qty // 3, 'XL': total_qty - 2 * (total_qty // 3)}

    # Calculate percentages
    total_sold = sum(row[1] for row in size_data)
    if total_sold == 0:
        # Equal split
        n_sizes = len(size_data)
        base = total_qty // n_sizes
        splits = {row[0]: base for row in size_data}
        # Add remainder to first size
        splits[size_data[0][0]] += total_qty - base * n_sizes
        return splits

    # Proportional split
    splits = {}
    allocated = 0
    for i, (size, units) in enumerate(size_data):
        pct = units / total_sold
        qty = round(total_qty * pct)

        # Last size gets remainder
        if i == len(size_data) - 1:
            qty = total_qty - allocated

        splits[size] = max(0, qty)
        allocated += splits[size]

    return splits


def get_confidence_score(sku_key: str, db_path: str) -> float:
    """
    Calculate confidence score based on forecast MAPE.

    MAPE < 15%: confidence = 0.9
    MAPE 15-25%: confidence = 0.7
    MAPE > 25%: confidence = 0.5

    Args:
        sku_key: SKU to check
        db_path: Path to database

    Returns:
        Confidence score (0-1)
    """
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    cursor.execute("""
        SELECT mape
        FROM fact_forecast_accuracy
        WHERE sku_key = ?
        ORDER BY accuracy_date DESC
        LIMIT 1
    """, (sku_key,))

    result = cursor.fetchone()
    conn.close()

    if not result or result[0] is None:
        return 0.6  # Default for unknown

    mape = result[0]
    if mape < 15:
        return 0.9
    elif mape < 25:
        return 0.7
    else:
        return 0.5


def calc_confidence_score(sku_key: str, db_path: str) -> float:
    """Backward-compatible alias for get_confidence_score."""
    return get_confidence_score(sku_key, db_path)


def _summarize_roic_action(lines: list[dict]) -> str:
    actions = set()
    for line in lines:
        action = line.get("roic_action")
        if action:
            actions.add(str(action))
            continue
        pct = line.get("roic_pct")
        if pct is None:
            continue
        try:
            pct_val = float(pct)
        except (TypeError, ValueError):
            continue
        if pct_val >= 20:
            actions.add("ORDER_FULL")
        elif pct_val >= 10:
            actions.add("ORDER_WITH_FLAG")
        else:
            actions.add("REVIEW_REQUIRED")
    if not actions:
        return "UNKNOWN"
    if len(actions) == 1:
        return next(iter(actions))
    return "MIXED"


def generate_po_draft(
    db_path: str,
    trigger: str = 'ROP',
    sku_filter: list[str] = None,
    min_confidence: float = 0.5
) -> int:
    """
    Generate a PO draft based on current inventory state.

    Args:
        db_path: Path to database
        trigger: Trigger type ('ROP', 'FORECAST', 'MANUAL')
        sku_filter: Optional list of SKUs to include
        min_confidence: Minimum confidence to include SKU

    Returns:
        draft_id of created draft, or 0 if no items
    """
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # Get SKUs needing reorder
    query = """
        SELECT
            m.sku_key,
            m.current_stock,
            m.rop,
            m.d30,
            m.roic_monthly,
            s.base_cost_cny
        FROM fact_sku_metrics m
        JOIN dim_sku s ON m.sku_key = s.sku_key
        WHERE m.status = 'REORDER'
    """
    params = []

    if sku_filter:
        placeholders = ','.join('?' * len(sku_filter))
        query += f" AND m.sku_key IN ({placeholders})"
        params.extend(sku_filter)

    cursor.execute(query, params)
    skus_to_order = cursor.fetchall()

    if not skus_to_order:
        conn.close()
        return 0

    # Calculate total
    total_units = 0
    total_cost_cny = 0.0
    lines = []

    for row in skus_to_order:
        sku_key, current_stock, rop, d30, roic, base_cost_cny = row

        # Check confidence
        confidence = get_confidence_score(sku_key, db_path)
        if confidence < min_confidence:
            continue

        # Calculate order quantity
        order_qty = calc_order_quantity(
            sku_key,
            current_stock or 0,
            int(rop or 0),
            d30 or 0
        )

        if order_qty <= 0:
            continue

        # Get size splits
        size_splits = apply_size_splits(sku_key, order_qty, db_path)

        for my_size, qty in size_splits.items():
            if qty <= 0:
                continue

            sku_id = f"{sku_key}_{my_size}"

            lines.append({
                'sku_key': sku_key,
                'sku_id': sku_id,
                'my_size': my_size,
                'quantity': qty,
                'unit_cost_cny': base_cost_cny or 0,
                'current_stock': current_stock or 0,
                'rop': int(rop or 0),
                'd_forecast': d30 or 0,
                'roic_pct': roic or 0
            })

            total_units += qty
            total_cost_cny += qty * (base_cost_cny or 0)

    if not lines:
        conn.close()
        return 0

    # Calculate KZT cost (CNY × 78 exchange rate)
    total_cost_kzt = total_cost_cny * 78

    # Calculate average confidence
    avg_confidence = sum(
        get_confidence_score(line['sku_key'], db_path)
        for line in lines
    ) / len(lines)

    # Create draft header
    expires_at = (datetime.now() + timedelta(hours=48)).isoformat()
    total_po_value_kzt = total_cost_kzt
    total_order_qty = total_units
    skus_count = len({line["sku_key"] for line in lines})
    roic_action_summary = _summarize_roic_action(lines)
    guardrail_status = "PENDING"

    cursor.execute("""
        INSERT INTO fact_po_draft (
            status, supplier_code, total_units, total_cost_cny, total_cost_kzt,
            total_po_value_kzt, total_order_qty, skus_count, roic_action_summary, guardrail_status,
            expires_at, generation_reason, confidence_score
        ) VALUES (?, 'DEFAULT', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        'PENDING',
        total_units,
        round(total_cost_cny, 2),
        round(total_cost_kzt, 2),
        round(total_po_value_kzt, 2),
        total_order_qty,
        skus_count,
        roic_action_summary,
        guardrail_status,
        expires_at,
        f'{trigger} trigger',
        round(avg_confidence, 2)
    ))

    draft_id = cursor.lastrowid

    # Create draft lines
    for line in lines:
        cursor.execute("""
            INSERT INTO fact_po_draft_lines (
                draft_id, sku_key, sku_id, my_size, quantity, unit_cost_cny,
                current_stock, rop, d_forecast, roic_pct
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            draft_id,
            line['sku_key'],
            line['sku_id'],
            line['my_size'],
            line['quantity'],
            line['unit_cost_cny'],
            line['current_stock'],
            line['rop'],
            line['d_forecast'],
            line['roic_pct']
        ))

    conn.commit()
    conn.close()

    return draft_id


def get_draft_summary(db_path: str, draft_id: int) -> dict:
    """
    Get summary of a PO draft.

    Args:
        db_path: Path to database
        draft_id: Draft ID to summarize

    Returns:
        Dict with draft details
    """
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # Get header
    cursor.execute("""
        SELECT
            draft_id, status, supplier_code, total_units,
            total_cost_cny, total_cost_kzt, created_at,
            expires_at, generation_reason, confidence_score
        FROM fact_po_draft
        WHERE draft_id = ?
    """, (draft_id,))

    header = cursor.fetchone()
    if not header:
        conn.close()
        return None

    # Get lines grouped by SKU
    cursor.execute("""
        SELECT sku_key, SUM(quantity) as total_qty,
               GROUP_CONCAT(my_size || ':' || quantity) as size_breakdown
        FROM fact_po_draft_lines
        WHERE draft_id = ?
        GROUP BY sku_key
    """, (draft_id,))

    lines = []
    for row in cursor.fetchall():
        lines.append({
            'sku_key': row[0],
            'quantity': row[1],
            'sizes': row[2]
        })

    conn.close()

    return {
        'draft_id': header[0],
        'status': header[1],
        'supplier': header[2],
        'total_units': header[3],
        'total_cost_cny': header[4],
        'total_cost_kzt': header[5],
        'created_at': header[6],
        'expires_at': header[7],
        'reason': header[8],
        'confidence': header[9],
        'lines': lines
    }


def generate_po_draft_with_validation(
    db_path: str,
    trigger: str = 'ROP',
    max_concentration: float = 0.20
) -> dict:
    """
    Generate PO draft with 20% concentration rule validation.

    TASK-080: Ensures no single SKU exceeds max_concentration of total capital.

    Args:
        db_path: Path to database
        trigger: Trigger type ('ROP', 'FORECAST', 'MANUAL')
        max_concentration: Maximum capital share per SKU (default 0.20 = 20%)

    Returns:
        Dict with draft info and any violation adjustments
    """
    from core.calc.capital_optimizer import check_concentration_rule

    # Generate initial draft
    draft_id = generate_po_draft(db_path, trigger)

    if not draft_id:
        return {'draft_id': 0, 'valid': True, 'violations': [], 'notes': 'No items to order'}

    # Get draft summary
    draft = get_draft_summary(db_path, draft_id)

    if not draft or not draft['lines']:
        return {'draft_id': draft_id, 'valid': True, 'violations': [], 'notes': 'Empty draft'}

    # Get current inventory and costs
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    cursor.execute("""
        SELECT sku_key, SUM(current_stock) as units
        FROM fact_inventory_snapshot_size
        WHERE snapshot_date = (SELECT MAX(snapshot_date) FROM fact_inventory_snapshot_size)
        GROUP BY sku_key
    """)
    current_inventory = dict(cursor.fetchall())

    cursor.execute("SELECT sku_key, cogs_kzt FROM dim_sku WHERE cogs_kzt > 0")
    unit_costs = dict(cursor.fetchall())

    conn.close()

    # Build proposed PO dict
    proposed_po = {line['sku_key']: line['quantity'] for line in draft['lines']}

    # Check concentration rule
    validation = check_concentration_rule(
        proposed_po=proposed_po,
        current_inventory=current_inventory,
        unit_costs=unit_costs,
        max_concentration=max_concentration
    )

    result = {
        'draft_id': draft_id,
        'valid': validation['valid'],
        'violations': validation['violations'],
        'adjusted_po': validation['adjusted_po'] if not validation['valid'] else None,
        'total_capital_after': validation['total_capital_after'],
        'notes': ''
    }

    if not validation['valid']:
        # Update draft lines with adjusted quantities
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        for sku_key, adjusted_qty in validation['adjusted_po'].items():
            original_qty = proposed_po.get(sku_key, 0)
            if adjusted_qty < original_qty:
                # Update the draft line
                cursor.execute("""
                    UPDATE fact_po_draft_lines
                    SET quantity = ?
                    WHERE draft_id = ? AND sku_key = ?
                """, (adjusted_qty, draft_id, sku_key))

        # Recalculate totals
        cursor.execute("""
            UPDATE fact_po_draft
            SET total_units = (SELECT SUM(quantity) FROM fact_po_draft_lines WHERE draft_id = ?),
                total_order_qty = (SELECT SUM(quantity) FROM fact_po_draft_lines WHERE draft_id = ?),
                total_cost_cny = (SELECT SUM(quantity * unit_cost_cny) FROM fact_po_draft_lines WHERE draft_id = ?),
                total_cost_kzt = (SELECT SUM(quantity * unit_cost_cny) FROM fact_po_draft_lines WHERE draft_id = ?) * 78,
                total_po_value_kzt = (SELECT SUM(quantity * unit_cost_cny) FROM fact_po_draft_lines WHERE draft_id = ?) * 78,
                skus_count = (SELECT COUNT(DISTINCT sku_key) FROM fact_po_draft_lines WHERE draft_id = ?),
                notes = COALESCE(notes, '') || ' | Adjusted for 20% concentration rule'
            WHERE draft_id = ?
        """, (draft_id, draft_id, draft_id, draft_id, draft_id, draft_id, draft_id))

        conn.commit()
        conn.close()

        result['notes'] = f"Adjusted {len(validation['violations'])} SKUs for 20% concentration rule"

    return result


# =============================================================================
# TASK-166: Phase 9.6 Size-Aware PO Generation
# =============================================================================

def generate_po_draft_size_aware(
    sku_key: str,
    store_code: str = "UNIVERSAL",
    db_path: Optional[Path] = None
) -> Optional[PODraft]:
    """
    Generate a size-aware PO draft for a single SKU using Phase 9.6 allocation.

    TASK-166: Uses true size-level allocation from size_allocation.py:
    - OOS-filtered demand calculation
    - Size mix with 3%/40% guardrails
    - Per-size safety stock, ROP, T_post
    - ANY-size REORDER trigger
    - New SKU age adjustment
    - Low demand insurance
    - 3-tier ROIC gate

    Args:
        sku_key: Style-level SKU key (e.g., "CL_OC_MEN_LINE52_BLACK")
        store_code: Store code (default: "UNIVERSAL")
        db_path: Optional database path

    Returns:
        PODraft with complete size-level allocations, or None if no data

    Example:
        >>> draft = generate_po_draft_size_aware("LINE52_BLACK")
        >>> if draft.should_order:
        ...     print(f"Order {draft.total_qty} units, ROIC: {draft.roic_monthly:.1%}")
    """
    # Get size-level data from DB
    size_sales_90d = get_size_sales_90d(sku_key, store_code, db_path)
    if not size_sales_90d:
        return None

    size_current_stock = get_size_current_stock(sku_key, store_code, db_path)
    size_inbound_stock = get_size_inbound(sku_key, store_code, db_path)
    size_sales_history = get_size_sales_history(sku_key, store_code, days=90, db_path=db_path)
    size_stock_history = get_size_stock_history(sku_key, store_code, days=90, db_path=db_path)
    sku_age_days = get_sku_age_days(sku_key, store_code, db_path)

    # Get SKU-level cost and profit from dim_sku
    conn = sqlite3.connect(str(db_path) if db_path else str(Path(__file__).parent.parent.parent / "db" / "app.db"))
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    cursor.execute("""
        SELECT base_cost_cny, weight_kg
        FROM dim_sku
        WHERE sku_key = ?
    """, (sku_key,))
    sku_row = cursor.fetchone()
    conn.close()

    if not sku_row:
        return None

    # Calculate COGS and profit (simplified)
    base_cost_cny = sku_row["base_cost_cny"] or 50
    weight_kg = sku_row["weight_kg"] or 0.5

    # Cost calculation (CNY to KZT with shipping)
    cny_to_kzt = 78
    shipping_per_kg = 150  # KZT per kg
    unit_cogs = base_cost_cny * cny_to_kzt + weight_kg * shipping_per_kg

    # Get average sell price for profit calculation
    cursor = sqlite3.connect(str(db_path) if db_path else str(Path(__file__).parent.parent.parent / "db" / "app.db"))
    cursor.row_factory = sqlite3.Row
    cursor = cursor.cursor()
    cursor.execute("""
        SELECT AVG(sell_price_kzt) as avg_price
        FROM fact_sales
        WHERE sku_key = ?
        AND order_date >= date('now', '-90 days')
    """, (sku_key,))
    price_row = cursor.fetchone()
    cursor.close()

    avg_sell_price = (price_row["avg_price"] or 15000) if price_row else 15000
    unit_profit = avg_sell_price - unit_cogs

    # Calculate sigma_sku from demand history
    total_daily_sales = []
    for size, sales_list in size_sales_history.items():
        for i, sales in enumerate(sales_list):
            if i >= len(total_daily_sales):
                total_daily_sales.append(0)
            total_daily_sales[i] += sales

    if total_daily_sales:
        import statistics
        sigma_sku = statistics.stdev(total_daily_sales) if len(total_daily_sales) > 1 else 0.4 * sum(total_daily_sales) / len(total_daily_sales)
    else:
        sigma_sku = 0.0

    # Generate PO draft using Phase 9.6 allocation
    draft = calc_generate_po_draft(
        sku_key=sku_key,
        store_code=store_code,
        size_sales_90d=size_sales_90d,
        size_current_stock=size_current_stock,
        size_inbound_stock=size_inbound_stock,
        size_sales_history=size_sales_history,
        size_stock_history=size_stock_history,
        unit_cogs=unit_cogs,
        unit_profit=unit_profit,
        sigma_sku=sigma_sku,
        sku_age_days=sku_age_days
    )

    return draft


def generate_batch_po_drafts_size_aware(
    db_path: Optional[Path] = None,
    store_code: str = "UNIVERSAL",
    sku_filter: Optional[list[str]] = None,
    trigger: str = "ROP"
) -> int:
    """
    Generate PO drafts for all SKUs needing reorder using Phase 9.6 allocation.

    TASK-166: Batch version of generate_po_draft_size_aware().

    Args:
        db_path: Optional database path
        store_code: Store code (default: "UNIVERSAL")
        sku_filter: Optional list of SKUs to include
        trigger: Trigger type for logging

    Returns:
        draft_id of created draft, or 0 if no items

    Note:
        This replaces the old generate_po_draft() for new deployments.
    """
    db = db_path or Path(__file__).parent.parent.parent / "db" / "app.db"
    conn = sqlite3.connect(str(db))
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    # Get SKUs that might need reorder (have size-level data)
    if sku_filter:
        placeholders = ','.join('?' * len(sku_filter))
        query = f"""
            SELECT DISTINCT sku_key
            FROM dim_sku_size
            WHERE sku_key IN ({placeholders})
              AND active_flag = 1
        """
        cursor.execute(query, sku_filter)
    else:
        cursor.execute("""
            SELECT DISTINCT sku_key
            FROM dim_sku_size
            WHERE active_flag = 1
        """)

    sku_keys = [row["sku_key"] for row in cursor.fetchall()]

    if not sku_keys:
        conn.close()
        return 0

    # Generate drafts for each SKU
    all_lines = []
    total_units = 0
    total_cost_cny = 0.0

    for sku_key in sku_keys:
        draft = generate_po_draft_size_aware(sku_key, store_code, db_path)

        if not draft or not draft.should_order or draft.total_qty == 0:
            continue

        # Skip if ROIC gate blocked
        if draft.roic_action == ROICAction.REVIEW_REQUIRED:
            continue

        # Add lines from this draft
        for size, alloc in draft.allocations.items():
            if alloc.order_qty_adjusted <= 0:
                continue

            sku_id = f"{sku_key}_{size}"
            all_lines.append({
                'sku_key': sku_key,
                'sku_id': sku_id,
                'my_size': size,
                'quantity': alloc.order_qty_adjusted,
                'unit_cost_cny': draft.cogs_unit / 78,  # Convert KZT back to CNY
                'current_stock': draft.allocations[size].target_stock,
                'rop': draft.rop_sku,
                'd_forecast': draft.d_sku,
                'roic_pct': draft.roic_monthly * 100,
                'trigger_sizes': ','.join(draft.trigger_sizes),
                'roic_action': draft.roic_action.value,
                'demand_confidence': draft.demand_confidence.value
            })

            total_units += alloc.order_qty_adjusted
            total_cost_cny += alloc.order_qty_adjusted * (draft.cogs_unit / 78)

    if not all_lines:
        conn.close()
        return 0

    # Create draft header
    expires_at = (datetime.now() + timedelta(hours=48)).isoformat()
    total_cost_kzt = total_cost_cny * 78
    total_po_value_kzt = total_cost_kzt
    total_order_qty = total_units
    skus_count = len({line["sku_key"] for line in all_lines})
    roic_action_summary = _summarize_roic_action(all_lines)
    guardrail_status = "PENDING"

    cursor.execute("""
        INSERT INTO fact_po_draft (
            status, supplier_code, total_units, total_cost_cny, total_cost_kzt,
            total_po_value_kzt, total_order_qty, skus_count, roic_action_summary, guardrail_status,
            expires_at, generation_reason, confidence_score, notes
        ) VALUES (?, 'DEFAULT', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        'PENDING',
        total_units,
        round(total_cost_cny, 2),
        round(total_cost_kzt, 2),
        round(total_po_value_kzt, 2),
        total_order_qty,
        skus_count,
        roic_action_summary,
        guardrail_status,
        expires_at,
        f'{trigger} trigger (Phase 9.6 Size-Aware)',
        0.8,  # Default confidence
        'Generated with Phase 9.6 size-aware allocation'
    ))

    draft_id = cursor.lastrowid

    # Create draft lines
    for line in all_lines:
        cursor.execute("""
            INSERT INTO fact_po_draft_lines (
                draft_id, sku_key, sku_id, my_size, quantity, unit_cost_cny,
                current_stock, rop, d_forecast, roic_pct
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            draft_id,
            line['sku_key'],
            line['sku_id'],
            line['my_size'],
            line['quantity'],
            line['unit_cost_cny'],
            int(line['current_stock']),
            int(line['rop']),
            line['d_forecast'],
            line['roic_pct']
        ))

    conn.commit()
    conn.close()

    return draft_id
