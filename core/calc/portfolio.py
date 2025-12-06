"""
TASK-039, TASK-042: Portfolio Analytics & Capital Allocation

Portfolio-level ROIC, capital metrics, and concentration rules.
Implements 20% rule to prevent over-concentration in single SKUs.
"""

from datetime import date, timedelta
from typing import Optional
import sqlite3


def calc_portfolio_roic(db_path: str) -> dict:
    """
    Calculate portfolio-level capital metrics.

    Returns:
        Dict with:
        - total_capital_deployed: Total KZT in inventory
        - weighted_roic: Capital-weighted average ROIC
        - top_10_skus: Best performers by ROIC
        - bottom_10_skus: Worst performers
        - capital_at_risk: Capital in declining/negative ROIC SKUs
    """
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # Get all SKUs with metrics
    cursor.execute("""
        SELECT
            m.sku_key,
            m.roic_monthly,
            m.k_avg,
            m.d30,
            m.status,
            l.lifecycle_status
        FROM fact_sku_metrics m
        LEFT JOIN dim_sku_lifecycle l ON m.sku_key = l.sku_key
        WHERE m.k_avg > 0
    """)

    skus = []
    total_capital = 0.0
    weighted_roic_sum = 0.0
    capital_at_risk = 0.0

    for row in cursor.fetchall():
        sku_key, roic, k_avg, d30, status, lifecycle = row
        roic = roic or 0.0
        k_avg = k_avg or 0.0

        skus.append({
            'sku_key': sku_key,
            'roic': roic,
            'k_avg': k_avg,
            'd30': d30 or 0.0,
            'status': status or 'UNKNOWN',
            'lifecycle': lifecycle or 'GROW'
        })

        total_capital += k_avg
        weighted_roic_sum += roic * k_avg

        # Capital at risk: negative ROIC or KILL status
        if roic < 0 or lifecycle == 'KILL':
            capital_at_risk += k_avg

    conn.close()

    # Sort by ROIC
    sorted_by_roic = sorted(skus, key=lambda x: x['roic'], reverse=True)

    weighted_roic = weighted_roic_sum / total_capital if total_capital > 0 else 0.0

    return {
        'total_capital_deployed': round(total_capital, 0),
        'weighted_roic': round(weighted_roic / 100, 4),  # Convert to decimal
        'weighted_roic_pct': round(weighted_roic, 2),
        'top_10_skus': sorted_by_roic[:10],
        'bottom_10_skus': sorted_by_roic[-10:] if len(sorted_by_roic) >= 10 else sorted_by_roic,
        'capital_at_risk': round(capital_at_risk, 0),
        'total_skus': len(skus)
    }


def calc_sku_capital_share(sku_key: str, db_path: str) -> float:
    """
    Calculate % of total capital deployed in a single SKU.

    Args:
        sku_key: SKU to check
        db_path: Path to database

    Returns:
        Percentage of total capital (0-100)
    """
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # Get SKU capital
    cursor.execute("""
        SELECT k_avg FROM fact_sku_metrics WHERE sku_key = ?
    """, (sku_key,))
    sku_result = cursor.fetchone()
    sku_capital = sku_result[0] if sku_result and sku_result[0] else 0.0

    # Get total capital
    cursor.execute("""
        SELECT SUM(k_avg) FROM fact_sku_metrics WHERE k_avg > 0
    """)
    total_result = cursor.fetchone()
    total_capital = total_result[0] if total_result and total_result[0] else 0.0

    conn.close()

    if total_capital == 0:
        return 0.0

    return (sku_capital / total_capital) * 100


def identify_kill_candidates(
    db_path: str,
    roic_threshold: float = 10.0,
    min_days_declining: int = 30
) -> list[dict]:
    """
    Identify SKUs that should be considered for liquidation.

    Candidates have:
    - ROIC < threshold AND
    - Declining sales trend

    Args:
        db_path: Path to database
        roic_threshold: ROIC threshold in % (default: 10%)
        min_days_declining: Minimum days of decline to flag

    Returns:
        List of kill candidate dicts
    """
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # Get SKUs with low ROIC
    cursor.execute("""
        SELECT
            m.sku_key,
            m.roic_monthly,
            m.k_avg,
            m.d30,
            m.current_stock,
            l.lifecycle_status
        FROM fact_sku_metrics m
        LEFT JOIN dim_sku_lifecycle l ON m.sku_key = l.sku_key
        WHERE m.roic_monthly < ?
        AND m.roic_monthly IS NOT NULL
    """, (roic_threshold,))

    candidates = []
    for row in cursor.fetchall():
        sku_key, roic, k_avg, d30, stock, lifecycle = row

        # Check trend (compare last 30 days to previous 30 days)
        cursor.execute("""
            SELECT
                SUM(CASE WHEN sale_date >= date('now', '-30 days') THEN units ELSE 0 END) as recent,
                SUM(CASE WHEN sale_date >= date('now', '-60 days')
                         AND sale_date < date('now', '-30 days') THEN units ELSE 0 END) as previous
            FROM fact_sales_daily
            WHERE sku_key = ?
        """, (sku_key,))

        trend_result = cursor.fetchone()
        recent = trend_result[0] or 0
        previous = trend_result[1] or 0

        # Calculate trend
        is_declining = previous > 0 and recent < previous * 0.8  # 20%+ decline

        if is_declining or roic < 0:
            # Calculate days of inventory
            doi = stock / d30 if d30 > 0 else 999

            recommendation = 'LIQUIDATE' if roic < 0 else 'DISCOUNT 20%'
            if doi > 90:
                recommendation = 'CLEARANCE SALE'

            candidates.append({
                'sku_key': sku_key,
                'roic': round(roic, 1),
                'k_avg': round(k_avg or 0, 0),
                'd30': round(d30 or 0, 2),
                'current_stock': stock or 0,
                'days_of_inventory': round(doi, 0),
                'trend': 'DECLINING' if is_declining else 'STABLE',
                'lifecycle': lifecycle or 'GROW',
                'recommendation': recommendation
            })

    conn.close()

    # Sort by ROIC ascending (worst first)
    candidates.sort(key=lambda x: x['roic'])

    return candidates


def check_concentration_rule(
    proposed_po: dict,
    current_inventory: dict,
    unit_costs: dict,
    total_capital: float,
    max_concentration: float = 0.20
) -> dict:
    """
    TASK-042: Validate that no single SKU exceeds max concentration.

    Args:
        proposed_po: Dict of {sku_key: qty}
        current_inventory: Dict of {sku_key: current_stock}
        unit_costs: Dict of {sku_key: cogs_per_unit}
        total_capital: Total portfolio capital
        max_concentration: Maximum allowed share (default: 20%)

    Returns:
        Dict with:
        - valid: True/False
        - violations: List of violations
        - adjusted_po: PO with quantities reduced to comply
    """
    if total_capital <= 0:
        return {
            'valid': True,
            'violations': [],
            'adjusted_po': proposed_po.copy(),
            'message': 'No capital data available'
        }

    violations = []
    adjusted_po = {}
    max_capital_per_sku = total_capital * max_concentration

    for sku_key, order_qty in proposed_po.items():
        current_stock = current_inventory.get(sku_key, 0)
        unit_cost = unit_costs.get(sku_key, 0)

        if unit_cost == 0:
            adjusted_po[sku_key] = order_qty
            continue

        # Calculate post-order capital
        post_order_stock = current_stock + order_qty
        post_order_capital = post_order_stock * unit_cost

        # Calculate share
        proposed_share = post_order_capital / total_capital

        if proposed_share > max_concentration:
            # Calculate max allowed quantity
            max_capital = max_capital_per_sku
            max_stock = max_capital / unit_cost
            max_order_qty = max(0, int(max_stock - current_stock))

            violations.append({
                'sku_key': sku_key,
                'proposed_qty': order_qty,
                'proposed_share': round(proposed_share * 100, 1),
                'max_allowed_share': round(max_concentration * 100, 1),
                'adjusted_qty': max_order_qty
            })

            adjusted_po[sku_key] = max_order_qty
        else:
            adjusted_po[sku_key] = order_qty

    return {
        'valid': len(violations) == 0,
        'violations': violations,
        'adjusted_po': adjusted_po,
        'message': f"{len(violations)} SKUs exceed {max_concentration*100:.0f}% limit" if violations else 'OK'
    }


def update_lifecycle_status(
    db_path: str,
    sku_key: str,
    new_status: str,
    reason: str
) -> bool:
    """
    Update SKU lifecycle status.

    Valid statuses: GROW, MAINTAIN, HARVEST, KILL

    Args:
        db_path: Path to database
        sku_key: SKU to update
        new_status: New lifecycle status
        reason: Reason for change

    Returns:
        True if updated successfully
    """
    valid_statuses = ['GROW', 'MAINTAIN', 'HARVEST', 'KILL']
    if new_status not in valid_statuses:
        return False

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    cursor.execute("""
        UPDATE dim_sku_lifecycle
        SET lifecycle_status = ?,
            status_reason = ?,
            last_review_date = date('now'),
            updated_at = datetime('now')
        WHERE sku_key = ?
    """, (new_status, reason, sku_key))

    updated = cursor.rowcount > 0
    conn.commit()
    conn.close()

    return updated


def get_lifecycle_distribution(db_path: str) -> dict:
    """
    Get count of SKUs in each lifecycle status.

    Returns:
        Dict with status -> count
    """
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    cursor.execute("""
        SELECT lifecycle_status, COUNT(*)
        FROM dim_sku_lifecycle
        GROUP BY lifecycle_status
    """)

    result = {}
    for row in cursor.fetchall():
        result[row[0]] = row[1]

    conn.close()

    # Ensure all statuses present
    for status in ['GROW', 'MAINTAIN', 'HARVEST', 'KILL']:
        if status not in result:
            result[status] = 0

    return result


def recommend_lifecycle_status(
    roic: float,
    trend_slope: float,
    d30: float
) -> str:
    """
    Recommend lifecycle status based on metrics.

    Args:
        roic: Monthly ROIC %
        trend_slope: Daily change rate (positive = growing)
        d30: Average daily demand

    Returns:
        Recommended status: GROW, MAINTAIN, HARVEST, or KILL
    """
    if roic < 0:
        return 'KILL'

    if roic < 5:
        return 'HARVEST' if d30 > 0.1 else 'KILL'

    if roic < 15:
        if trend_slope > 0.02:
            return 'MAINTAIN'
        elif trend_slope < -0.02:
            return 'HARVEST'
        else:
            return 'MAINTAIN'

    # ROIC >= 15%
    if trend_slope > 0.02:
        return 'GROW'
    elif trend_slope < -0.02:
        return 'MAINTAIN'
    else:
        return 'GROW'
