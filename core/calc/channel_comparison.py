"""
Cross-channel comparison analysis for Phase 8.

Compares same SKU performance across different channels.
"""
import sqlite3
from pathlib import Path
from dataclasses import dataclass
from typing import Optional

DB_PATH = Path(__file__).parent.parent.parent / "db" / "app.db"


@dataclass
class ChannelComparison:
    """Comparison of SKU performance across two channels."""

    sku_key: str

    # Channel A metrics
    channel_a: str
    a_units_30d: int
    a_revenue_30d: float
    a_margin_pct: float
    a_roic_pct: float

    # Channel B metrics
    channel_b: str
    b_units_30d: int
    b_revenue_30d: float
    b_margin_pct: float
    b_roic_pct: float

    # Comparison
    volume_winner: str
    margin_winner: str
    roic_winner: str
    recommended_channel: str
    recommendation_reason: str


def compare_channels(
    db_path: Path,
    sku_key: str,
    channel_a: str = "KSP",
    channel_b: str = "WB",
) -> Optional[ChannelComparison]:
    """
    Compare SKU performance between two channels.

    Returns None if SKU doesn't exist in both channels.
    """
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # Get latest metrics for each channel
    cursor.execute("""
        SELECT
            channel_code,
            units_30d,
            revenue_30d_kzt,
            margin_pct,
            roic_30d_pct
        FROM fact_channel_metrics
        WHERE sku_key = ?
          AND channel_code IN (?, ?)
          AND metric_date = (SELECT MAX(metric_date) FROM fact_channel_metrics WHERE sku_key = ?)
    """, (sku_key, channel_a, channel_b, sku_key))

    rows = cursor.fetchall()
    conn.close()

    if len(rows) < 2:
        return None  # SKU not in both channels

    # Parse results
    metrics = {}
    for row in rows:
        metrics[row[0]] = {
            "units": row[1] or 0,
            "revenue": row[2] or 0,
            "margin": row[3] or 0,
            "roic": row[4] or 0,
        }

    a = metrics.get(channel_a, {"units": 0, "revenue": 0, "margin": 0, "roic": 0})
    b = metrics.get(channel_b, {"units": 0, "revenue": 0, "margin": 0, "roic": 0})

    # Determine winners
    volume_winner = channel_a if a["units"] >= b["units"] else channel_b
    margin_winner = channel_a if a["margin"] >= b["margin"] else channel_b
    roic_winner = channel_a if a["roic"] >= b["roic"] else channel_b

    # Recommendation logic
    # ROIC is king for capital allocation, but volume matters for absolute profit
    recommended, reason = _get_recommendation(
        channel_a, channel_b, a, b, roic_winner
    )

    return ChannelComparison(
        sku_key=sku_key,
        channel_a=channel_a,
        a_units_30d=a["units"],
        a_revenue_30d=a["revenue"],
        a_margin_pct=a["margin"],
        a_roic_pct=a["roic"],
        channel_b=channel_b,
        b_units_30d=b["units"],
        b_revenue_30d=b["revenue"],
        b_margin_pct=b["margin"],
        b_roic_pct=b["roic"],
        volume_winner=volume_winner,
        margin_winner=margin_winner,
        roic_winner=roic_winner,
        recommended_channel=recommended,
        recommendation_reason=reason,
    )


def _get_recommendation(
    channel_a: str,
    channel_b: str,
    a: dict,
    b: dict,
    roic_winner: str,
) -> tuple[str, str]:
    """Determine recommended channel and reason."""
    # ROIC significantly higher (20%+)
    if a["roic"] > b["roic"] * 1.2 and a["roic"] > 0:
        return (
            channel_a,
            f"ROIC {a['roic']:.1f}% vs {b['roic']:.1f}% — significantly better capital efficiency",
        )
    if b["roic"] > a["roic"] * 1.2 and b["roic"] > 0:
        return (
            channel_b,
            f"ROIC {b['roic']:.1f}% vs {a['roic']:.1f}% — significantly better capital efficiency",
        )

    # Volume significantly higher (50%+)
    if a["units"] > b["units"] * 1.5 and a["units"] > 0:
        return (
            channel_a,
            f"Volume {a['units']} vs {b['units']} — higher absolute profit potential",
        )
    if b["units"] > a["units"] * 1.5 and b["units"] > 0:
        return (
            channel_b,
            f"Volume {b['units']} vs {a['units']} — higher absolute profit potential",
        )

    # Default to ROIC winner
    return (roic_winner, "Similar performance; defaulting to higher ROIC channel")


def get_all_channel_comparisons(
    db_path: Path,
    channel_a: str = "KSP",
    channel_b: str = "WB",
) -> list[ChannelComparison]:
    """Get comparisons for all SKUs present in both channels."""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # Find SKUs in both channels
    cursor.execute("""
        SELECT DISTINCT sku_key
        FROM fact_channel_metrics
        WHERE channel_code = ?
        INTERSECT
        SELECT DISTINCT sku_key
        FROM fact_channel_metrics
        WHERE channel_code = ?
    """, (channel_a, channel_b))

    skus = [row[0] for row in cursor.fetchall()]
    conn.close()

    comparisons = []
    for sku in skus:
        comp = compare_channels(db_path, sku, channel_a, channel_b)
        if comp:
            comparisons.append(comp)

    return comparisons


def get_channel_summary(db_path: Path) -> dict:
    """
    Get summary statistics per channel.

    Returns dict with channel_code -> summary metrics.
    """
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    cursor.execute("""
        SELECT
            channel_code,
            COUNT(DISTINCT sku_key) as sku_count,
            SUM(units_30d) as total_units,
            SUM(revenue_30d_kzt) as total_revenue,
            SUM(profit_30d_kzt) as total_profit,
            AVG(margin_pct) as avg_margin,
            AVG(roic_30d_pct) as avg_roic
        FROM fact_channel_metrics
        WHERE metric_date = (SELECT MAX(metric_date) FROM fact_channel_metrics)
        GROUP BY channel_code
    """)

    summary = {}
    for row in cursor.fetchall():
        summary[row[0]] = {
            "sku_count": row[1],
            "total_units_30d": row[2] or 0,
            "total_revenue_30d": row[3] or 0,
            "total_profit_30d": row[4] or 0,
            "avg_margin_pct": row[5] or 0,
            "avg_roic_pct": row[6] or 0,
        }

    conn.close()
    return summary


def identify_channel_opportunities(
    db_path: Path,
    source_channel: str = "KSP",
    target_channel: str = "WB",
    min_units_30d: int = 10,
) -> list[str]:
    """
    Identify SKUs that sell well on source_channel but aren't on target_channel.

    These are expansion opportunities.
    """
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # Find SKUs on source channel with good volume, not on target
    cursor.execute("""
        SELECT DISTINCT sku_key
        FROM fact_channel_metrics
        WHERE channel_code = ?
          AND units_30d >= ?
          AND metric_date = (SELECT MAX(metric_date) FROM fact_channel_metrics)
        EXCEPT
        SELECT DISTINCT sku_key
        FROM fact_channel_metrics
        WHERE channel_code = ?
    """, (source_channel, min_units_30d, target_channel))

    skus = [row[0] for row in cursor.fetchall()]
    conn.close()

    return skus


if __name__ == "__main__":
    print("Channel Comparison Module")
    print("=" * 60)

    # Get channel summary
    summary = get_channel_summary(DB_PATH)
    print("\nChannel Summary:")
    for ch, stats in summary.items():
        print(f"\n  {ch}:")
        print(f"    SKUs: {stats['sku_count']}")
        print(f"    30d Units: {stats['total_units_30d']:,}")
        print(f"    30d Revenue: {stats['total_revenue_30d']:,.0f} KZT")
        print(f"    Avg Margin: {stats['avg_margin_pct']:.1f}%")
        print(f"    Avg ROIC: {stats['avg_roic_pct']:.1f}%")

    # Get all comparisons
    comparisons = get_all_channel_comparisons(DB_PATH)
    if comparisons:
        print(f"\n{len(comparisons)} SKUs present on both channels:")
        for c in comparisons[:5]:
            print(f"\n  {c.sku_key}:")
            print(f"    {c.channel_a}: {c.a_units_30d} units, {c.a_margin_pct:.1f}% margin")
            print(f"    {c.channel_b}: {c.b_units_30d} units, {c.b_margin_pct:.1f}% margin")
            print(f"    Recommended: {c.recommended_channel}")

    # Identify opportunities
    opportunities = identify_channel_opportunities(DB_PATH)
    if opportunities:
        print(f"\n{len(opportunities)} SKUs with WB expansion potential:")
        for sku in opportunities[:10]:
            print(f"  - {sku}")
