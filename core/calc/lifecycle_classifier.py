#!/usr/bin/env python3
"""
SKU lifecycle classification: GROW / MAINTAIN / HARVEST / KILL

Decision matrix:
- GROW: ROIC > 20% AND trend RISING
- MAINTAIN: ROIC 10-20% AND trend STABLE
- HARVEST: ROIC > 5% AND (trend FALLING OR ROIC declining)
- KILL: ROIC < 5% OR (ROIC < 10% AND trend FALLING for 30+ days)

TASK-077
"""
import sqlite3
from pathlib import Path
from datetime import date
from dataclasses import dataclass
from typing import Optional


@dataclass
class LifecycleDecision:
    sku_key: str
    current_status: str
    recommended_status: str
    roic_pct: float
    trend: str
    reason: str
    action: str  # Human-readable action


def classify_lifecycle(
    sku_key: str,
    roic_pct: float,
    roic_30d_ago: Optional[float],
    sales_trend_slope: float,
    days_since_last_sale: int
) -> LifecycleDecision:
    """
    Classify SKU lifecycle status based on performance metrics.
    """
    # Determine trend
    if sales_trend_slope > 0.05:
        trend = 'RISING'
    elif sales_trend_slope < -0.05:
        trend = 'FALLING'
    else:
        trend = 'STABLE'

    # Classification logic
    if roic_pct >= 20 and trend in ('RISING', 'STABLE'):
        status = 'GROW'
        reason = f"High ROIC ({roic_pct:.1f}%) with {trend.lower()} sales"
        action = "Increase order quantities by 20-30%"

    elif roic_pct >= 10:
        if trend == 'FALLING' or (roic_30d_ago and roic_pct < roic_30d_ago * 0.8):
            status = 'HARVEST'
            reason = f"Good ROIC ({roic_pct:.1f}%) but declining trend"
            action = "Reduce order quantities, let inventory run down"
        else:
            status = 'MAINTAIN'
            reason = f"Solid ROIC ({roic_pct:.1f}%) with stable performance"
            action = "Hold current order quantities"

    elif roic_pct >= 5:
        if trend == 'RISING':
            status = 'MAINTAIN'
            reason = f"Low ROIC ({roic_pct:.1f}%) but improving"
            action = "Monitor closely, consider price increase"
        else:
            status = 'HARVEST'
            reason = f"Low ROIC ({roic_pct:.1f}%) with weak trend"
            action = "No new orders, liquidate at discount if needed"

    else:  # ROIC < 5%
        if days_since_last_sale > 60:
            status = 'KILL'
            reason = f"Dead stock: no sales in {days_since_last_sale} days"
            action = "Liquidate immediately at any price above COGS"
        elif roic_pct < 0:
            status = 'KILL'
            reason = f"Negative ROIC ({roic_pct:.1f}%)"
            action = "Stop orders, liquidate remaining inventory"
        else:
            status = 'HARVEST'
            reason = f"Very low ROIC ({roic_pct:.1f}%)"
            action = "No new orders, sell through existing stock"

    return LifecycleDecision(
        sku_key=sku_key,
        current_status='UNKNOWN',  # Will be filled from DB
        recommended_status=status,
        roic_pct=roic_pct,
        trend=trend,
        reason=reason,
        action=action
    )


def update_lifecycle_statuses(db_path: Path):
    """
    Update dim_sku_lifecycle with latest classifications.
    """
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # Get latest metrics for each SKU
    cursor.execute("""
        SELECT
            ca.sku_key,
            ca.roic_30d_pct,
            ca.lifecycle_status as current_status,

            -- Previous ROIC (30 days ago)
            (SELECT roic_30d_pct
             FROM fact_capital_allocation prev
             WHERE prev.sku_key = ca.sku_key
               AND prev.snapshot_date = date(ca.snapshot_date, '-30 days')
            ) as roic_30d_ago,

            -- Sales trend (simplified - use revenue change)
            COALESCE(
                (ca.revenue_30d_kzt -
                 (SELECT revenue_30d_kzt FROM fact_capital_allocation prev
                  WHERE prev.sku_key = ca.sku_key
                  AND prev.snapshot_date = date(ca.snapshot_date, '-30 days'))
                ) / NULLIF(ca.revenue_30d_kzt, 0),
                0
            ) as trend_slope,

            -- Days since last sale
            COALESCE(
                (SELECT julianday('now') - julianday(MAX(sale_date))
                 FROM fact_sales_daily
                 WHERE sku_key = ca.sku_key),
                999
            ) as days_since_sale

        FROM fact_capital_allocation ca
        WHERE ca.snapshot_date = (SELECT MAX(snapshot_date) FROM fact_capital_allocation)
    """)

    updates = []
    for row in cursor.fetchall():
        sku_key, roic, current, roic_30d_ago, trend_slope, days_since = row

        decision = classify_lifecycle(
            sku_key=sku_key,
            roic_pct=roic or 0,
            roic_30d_ago=roic_30d_ago,
            sales_trend_slope=trend_slope or 0,
            days_since_last_sale=int(days_since or 0)
        )
        decision.current_status = current or 'UNKNOWN'

        updates.append((
            decision.recommended_status,
            decision.reason,
            date.today().isoformat(),
            sku_key
        ))

    # Upsert to dim_sku_lifecycle
    for status, reason, review_date, sku_key in updates:
        cursor.execute("""
            INSERT INTO dim_sku_lifecycle (sku_key, lifecycle_status, status_reason, last_review_date)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(sku_key) DO UPDATE SET
                lifecycle_status = excluded.lifecycle_status,
                status_reason = excluded.status_reason,
                last_review_date = excluded.last_review_date,
                updated_at = CURRENT_TIMESTAMP
        """, (sku_key, status, reason, review_date))

    conn.commit()
    conn.close()

    print(f"✓ Updated lifecycle status for {len(updates)} SKUs")
    return updates
