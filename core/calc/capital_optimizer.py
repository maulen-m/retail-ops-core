#!/usr/bin/env python3
"""
Capital allocation optimizer.
Maximizes portfolio ROIC subject to constraints.

TASK-076
"""
from dataclasses import dataclass
from typing import Optional
import sqlite3
from pathlib import Path


@dataclass
class SKUAllocation:
    sku_key: str
    current_capital: float
    roic_pct: float
    recommended_capital: float
    delta_capital: float
    action: str  # INCREASE, HOLD, DECREASE, KILL


def get_current_allocations(db_path: Path) -> list[dict]:
    """Load current capital allocation from latest snapshot."""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    cursor.execute("""
        SELECT sku_key, total_capital_kzt, roic_30d_pct, capital_share_pct, lifecycle_status
        FROM fact_capital_allocation
        WHERE snapshot_date = (SELECT MAX(snapshot_date) FROM fact_capital_allocation)
        ORDER BY roic_30d_pct DESC
    """)

    allocations = []
    for row in cursor.fetchall():
        allocations.append({
            'sku_key': row[0],
            'capital': row[1] or 0,
            'roic': row[2] or 0,
            'share': row[3] or 0,
            'lifecycle': row[4] or 'UNKNOWN'
        })

    conn.close()
    return allocations


def optimize_allocation(
    allocations: list[dict],
    total_budget: Optional[float] = None,
    max_concentration: float = 0.20,
    min_roic_threshold: float = 10.0,
    kill_roic_threshold: float = 5.0
) -> list[SKUAllocation]:
    """
    Optimize capital allocation to maximize portfolio ROIC.

    Rules:
    1. No single SKU > max_concentration (20%)
    2. SKUs with ROIC < min_roic_threshold get DECREASE
    3. SKUs with ROIC < kill_roic_threshold get KILL
    4. Freed capital goes to highest-ROIC SKUs
    5. Total allocation = total_budget (or current total if None)
    """
    if not allocations:
        return []

    # Calculate current total
    current_total = sum(a['capital'] for a in allocations)
    budget = total_budget if total_budget else current_total
    max_per_sku = budget * max_concentration

    results = []
    capital_to_reallocate = 0.0

    # First pass: Identify decreases and kills
    for alloc in allocations:
        if alloc['roic'] < kill_roic_threshold:
            action = 'KILL'
            rec_capital = 0.0
            capital_to_reallocate += alloc['capital']
        elif alloc['roic'] < min_roic_threshold:
            action = 'DECREASE'
            rec_capital = alloc['capital'] * 0.5  # Cut by 50%
            capital_to_reallocate += alloc['capital'] * 0.5
        elif alloc['capital'] > max_per_sku:
            action = 'DECREASE'
            rec_capital = max_per_sku
            capital_to_reallocate += alloc['capital'] - max_per_sku
        else:
            action = 'HOLD'
            rec_capital = alloc['capital']

        results.append(SKUAllocation(
            sku_key=alloc['sku_key'],
            current_capital=alloc['capital'],
            roic_pct=alloc['roic'],
            recommended_capital=rec_capital,
            delta_capital=rec_capital - alloc['capital'],
            action=action
        ))

    # Second pass: Allocate freed capital to top performers
    # Sort by ROIC descending, exclude KILL candidates
    top_performers = sorted(
        [r for r in results if r.action not in ('KILL', 'DECREASE')],
        key=lambda x: x.roic_pct,
        reverse=True
    )

    for result in top_performers:
        if capital_to_reallocate <= 0:
            break

        # How much can this SKU absorb?
        headroom = max_per_sku - result.recommended_capital
        if headroom > 0:
            additional = min(headroom, capital_to_reallocate)
            result.recommended_capital += additional
            result.delta_capital = result.recommended_capital - result.current_capital
            result.action = 'INCREASE'
            capital_to_reallocate -= additional

    return results


def calc_portfolio_impact(
    current: list[dict],
    optimized: list[SKUAllocation]
) -> dict:
    """Calculate expected impact of optimization."""
    current_roic = sum(a['capital'] * a['roic'] / 100 for a in current)
    current_total = sum(a['capital'] for a in current)
    current_weighted_roic = (current_roic / current_total * 100) if current_total > 0 else 0

    new_roic = sum(o.recommended_capital * o.roic_pct / 100 for o in optimized)
    new_total = sum(o.recommended_capital for o in optimized)
    new_weighted_roic = (new_roic / new_total * 100) if new_total > 0 else 0

    return {
        'current_portfolio_roic': round(current_weighted_roic, 2),
        'projected_portfolio_roic': round(new_weighted_roic, 2),
        'roic_lift': round(new_weighted_roic - current_weighted_roic, 2),
        'capital_reallocated': sum(abs(o.delta_capital) for o in optimized) / 2,
        'skus_increased': len([o for o in optimized if o.action == 'INCREASE']),
        'skus_decreased': len([o for o in optimized if o.action == 'DECREASE']),
        'skus_killed': len([o for o in optimized if o.action == 'KILL']),
    }


def check_concentration_rule(
    proposed_po: dict,  # {sku_key: qty}
    current_inventory: dict,  # {sku_key: units}
    unit_costs: dict,  # {sku_key: cogs_kzt}
    max_concentration: float = 0.20
) -> dict:
    """
    Validate that proposed PO doesn't violate 20% rule.
    Returns validation result with adjustments if needed.
    """
    # Calculate current capital by SKU
    current_capital = {
        sku: current_inventory.get(sku, 0) * unit_costs.get(sku, 0)
        for sku in set(current_inventory.keys()) | set(proposed_po.keys())
    }

    # Add proposed PO capital
    proposed_capital = {
        sku: current_capital.get(sku, 0) + proposed_po.get(sku, 0) * unit_costs.get(sku, 0)
        for sku in current_capital.keys()
    }

    total_capital = sum(proposed_capital.values())
    max_allowed = total_capital * max_concentration

    violations = []
    adjusted_po = proposed_po.copy()

    for sku, capital in proposed_capital.items():
        if capital > max_allowed and sku in proposed_po:
            excess = capital - max_allowed
            excess_units = int(excess / unit_costs.get(sku, 1))

            violations.append({
                'sku_key': sku,
                'proposed_capital': capital,
                'max_allowed': max_allowed,
                'proposed_share': capital / total_capital if total_capital > 0 else 0,
                'excess_units': excess_units
            })

            # Adjust PO
            adjusted_po[sku] = max(0, proposed_po[sku] - excess_units)

    return {
        'valid': len(violations) == 0,
        'violations': violations,
        'adjusted_po': adjusted_po,
        'total_capital_after': total_capital
    }
