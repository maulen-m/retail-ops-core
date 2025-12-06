"""
Transfer recommender for Phase 8.

Recommends inventory transfers between channels to:
- Prevent stockouts on high-velocity channels
- Balance working capital across channels
- Optimize overall portfolio ROIC
"""
import sqlite3
from pathlib import Path
from dataclasses import dataclass
from typing import Optional
from datetime import date

DB_PATH = Path(__file__).parent.parent.parent / "db" / "app.db"


@dataclass
class TransferRecommendation:
    """Recommendation to transfer inventory between channels."""

    sku_key: str
    from_channel: str
    to_channel: str
    units_to_transfer: int
    reason: str
    urgency: str  # LOW, MEDIUM, HIGH, CRITICAL
    confidence: str  # LOW, MEDIUM, HIGH

    # Source channel metrics
    from_on_hand: int
    from_days_of_cover: float
    from_d30: float

    # Target channel metrics
    to_on_hand: int
    to_days_of_cover: float
    to_d30: float

    # Financial impact
    estimated_revenue_protected_kzt: float


@dataclass
class ChannelInventoryStatus:
    """Inventory status for a SKU on a channel."""

    sku_key: str
    channel_code: str
    on_hand: int
    d30: float
    days_of_cover: float
    stockout_risk: str  # LOW, MEDIUM, HIGH, CRITICAL


def get_channel_inventory_status(
    db_path: Path,
    sku_key: Optional[str] = None,
) -> list[ChannelInventoryStatus]:
    """
    Get current inventory status per SKU per channel.

    Args:
        db_path: Path to database
        sku_key: Optional filter for specific SKU

    Returns:
        List of ChannelInventoryStatus
    """
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # Build filter
    sku_filter = ""
    params = []
    if sku_key:
        sku_filter = "AND cm.sku_key = ?"
        params.append(sku_key)

    # Get latest metrics and inventory
    cursor.execute(f"""
        SELECT
            cm.sku_key,
            cm.channel_code,
            COALESCE(ci.on_hand_units, 0) as on_hand,
            cm.units_30d,
            COALESCE(ci.days_of_cover, 0) as days_of_cover,
            COALESCE(ci.stockout_risk, 'UNKNOWN') as stockout_risk
        FROM fact_channel_metrics cm
        LEFT JOIN fact_channel_inventory ci
            ON cm.sku_key = ci.sku_key
            AND cm.channel_code = ci.channel_code
            AND ci.snapshot_date = (SELECT MAX(snapshot_date) FROM fact_channel_inventory)
        WHERE cm.metric_date = (SELECT MAX(metric_date) FROM fact_channel_metrics)
        {sku_filter}
        ORDER BY cm.sku_key, cm.channel_code
    """, params)

    results = []
    for row in cursor.fetchall():
        sku, channel, on_hand, d30, doc, risk = row

        # Calculate days of cover if not in inventory table
        if doc == 0 and d30 > 0:
            daily_demand = d30 / 30
            doc = on_hand / daily_demand if daily_demand > 0 else 999

        # Determine stockout risk if not set
        if risk == "UNKNOWN":
            if doc <= 7:
                risk = "CRITICAL"
            elif doc <= 14:
                risk = "HIGH"
            elif doc <= 21:
                risk = "MEDIUM"
            else:
                risk = "LOW"

        results.append(ChannelInventoryStatus(
            sku_key=sku,
            channel_code=channel,
            on_hand=on_hand,
            d30=d30 or 0,
            days_of_cover=doc,
            stockout_risk=risk,
        ))

    conn.close()
    return results


def recommend_transfers(
    db_path: Path,
    min_days_cover_threshold: int = 14,
    max_days_cover_threshold: int = 60,
) -> list[TransferRecommendation]:
    """
    Recommend inventory transfers between channels.

    Logic:
    - Identify SKUs with stockout risk on one channel but excess on another
    - Calculate optimal transfer quantity
    - Estimate financial impact

    Args:
        db_path: Path to database
        min_days_cover_threshold: Below this = needs stock
        max_days_cover_threshold: Above this = excess stock

    Returns:
        List of TransferRecommendations sorted by urgency
    """
    # Get all inventory status
    all_status = get_channel_inventory_status(db_path)

    # Group by SKU
    by_sku = {}
    for status in all_status:
        by_sku.setdefault(status.sku_key, []).append(status)

    recommendations = []

    for sku_key, channels in by_sku.items():
        if len(channels) < 2:
            continue  # Need at least 2 channels to transfer

        # Find channels with excess and shortage
        excess = [c for c in channels if c.days_of_cover > max_days_cover_threshold]
        shortage = [c for c in channels if c.days_of_cover < min_days_cover_threshold]

        if not excess or not shortage:
            continue

        # Match excess to shortage
        for needy in shortage:
            for surplus in excess:
                rec = _calculate_transfer(
                    sku_key, surplus, needy, min_days_cover_threshold
                )
                if rec:
                    recommendations.append(rec)

    # Sort by urgency (CRITICAL > HIGH > MEDIUM > LOW)
    urgency_order = {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2, "LOW": 3}
    recommendations.sort(key=lambda r: (urgency_order.get(r.urgency, 4), -r.units_to_transfer))

    return recommendations


def _calculate_transfer(
    sku_key: str,
    from_channel: ChannelInventoryStatus,
    to_channel: ChannelInventoryStatus,
    target_days: int,
) -> Optional[TransferRecommendation]:
    """Calculate optimal transfer between two channels."""
    if to_channel.d30 <= 0:
        return None  # No demand on target channel

    # Calculate units needed to reach target days of cover
    daily_demand = to_channel.d30 / 30
    units_needed = int((target_days * daily_demand) - to_channel.on_hand)

    if units_needed <= 0:
        return None

    # Calculate max units we can spare from source
    from_daily_demand = from_channel.d30 / 30 if from_channel.d30 > 0 else 0.1
    min_keep = int(target_days * from_daily_demand)  # Keep at least target days
    max_transfer = max(0, from_channel.on_hand - min_keep)

    if max_transfer <= 0:
        return None

    # Transfer the smaller of needed and available
    units_to_transfer = min(units_needed, max_transfer)

    if units_to_transfer < 5:  # Minimum viable transfer
        return None

    # Determine urgency
    if to_channel.stockout_risk == "CRITICAL":
        urgency = "CRITICAL"
    elif to_channel.stockout_risk == "HIGH":
        urgency = "HIGH"
    elif to_channel.days_of_cover < 10:
        urgency = "MEDIUM"
    else:
        urgency = "LOW"

    # Estimate revenue protected (30-day revenue potential of transferred units)
    # Get average revenue per unit from database
    estimated_revenue = _estimate_revenue_protected(
        sku_key, to_channel.channel_code, units_to_transfer
    )

    # Confidence based on data quality
    if to_channel.d30 >= 30:
        confidence = "HIGH"
    elif to_channel.d30 >= 10:
        confidence = "MEDIUM"
    else:
        confidence = "LOW"

    reason = (
        f"{to_channel.channel_code} has {to_channel.days_of_cover:.0f} days cover "
        f"(needs {target_days}); {from_channel.channel_code} has "
        f"{from_channel.days_of_cover:.0f} days excess"
    )

    return TransferRecommendation(
        sku_key=sku_key,
        from_channel=from_channel.channel_code,
        to_channel=to_channel.channel_code,
        units_to_transfer=units_to_transfer,
        reason=reason,
        urgency=urgency,
        confidence=confidence,
        from_on_hand=from_channel.on_hand,
        from_days_of_cover=from_channel.days_of_cover,
        from_d30=from_channel.d30,
        to_on_hand=to_channel.on_hand,
        to_days_of_cover=to_channel.days_of_cover,
        to_d30=to_channel.d30,
        estimated_revenue_protected_kzt=estimated_revenue,
    )


def _estimate_revenue_protected(
    sku_key: str,
    channel_code: str,
    units: int,
) -> float:
    """Estimate revenue protected by transfer."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # Get average revenue per unit from recent sales
    cursor.execute("""
        SELECT AVG(net_rev_kzt / NULLIF(quantity, 0))
        FROM fact_sales
        WHERE sku_key = ?
          AND COALESCE(channel_code, 'KSP') = ?
          AND quantity > 0
          AND order_date >= date('now', '-30 days')
    """, (sku_key, channel_code))

    row = cursor.fetchone()
    conn.close()

    avg_rev = row[0] if row and row[0] else 0
    return avg_rev * units


def get_critical_imbalances(db_path: Path) -> list[TransferRecommendation]:
    """Get only critical/high urgency transfer recommendations."""
    all_recs = recommend_transfers(db_path)
    return [r for r in all_recs if r.urgency in ("CRITICAL", "HIGH")]


def get_transfer_summary(recommendations: list[TransferRecommendation]) -> dict:
    """Get summary statistics for transfer recommendations."""
    if not recommendations:
        return {
            "total_recommendations": 0,
            "by_urgency": {},
            "total_units": 0,
            "total_revenue_protected": 0,
        }

    by_urgency = {}
    for r in recommendations:
        by_urgency.setdefault(r.urgency, 0)
        by_urgency[r.urgency] += 1

    return {
        "total_recommendations": len(recommendations),
        "by_urgency": by_urgency,
        "total_units": sum(r.units_to_transfer for r in recommendations),
        "total_revenue_protected": sum(r.estimated_revenue_protected_kzt for r in recommendations),
        "skus_affected": len(set(r.sku_key for r in recommendations)),
    }


if __name__ == "__main__":
    print("Transfer Recommender Module")
    print("=" * 60)

    # Get recommendations
    recommendations = recommend_transfers(DB_PATH)

    summary = get_transfer_summary(recommendations)
    print(f"\nTotal recommendations: {summary['total_recommendations']}")
    print(f"By urgency: {summary['by_urgency']}")
    print(f"Total units: {summary['total_units']}")
    print(f"Revenue protected: {summary['total_revenue_protected']:,.0f} KZT")

    if recommendations:
        print("\nTop 5 recommendations:")
        for r in recommendations[:5]:
            print(f"\n  {r.sku_key}:")
            print(f"    Transfer {r.units_to_transfer} units: {r.from_channel} → {r.to_channel}")
            print(f"    Urgency: {r.urgency}, Confidence: {r.confidence}")
            print(f"    Reason: {r.reason}")
