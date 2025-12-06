"""
Expansion scoring engine for Phase 8.

Scores Kaspi SKUs for potential WB expansion based on:
- Current Kaspi performance (demand, ROIC, margin)
- WB margin potential (with different fee structure)
- Competition density on target channel
"""
import sqlite3
from pathlib import Path
from dataclasses import dataclass
from typing import Optional
from datetime import date

try:
    from core.calc.wb_economics import calc_wb_breakeven_price, calc_wb_profit, calc_wb_margin
except ModuleNotFoundError:
    from wb_economics import calc_wb_breakeven_price, calc_wb_profit, calc_wb_margin

DB_PATH = Path(__file__).parent.parent.parent / "db" / "app.db"


@dataclass
class ExpansionScore:
    """Expansion potential score for a SKU."""

    sku_key: str
    source_channel: str
    target_channel: str
    score_date: date

    # Source metrics
    source_d30: float
    source_roic_pct: float
    source_margin_pct: float
    source_avg_price_kzt: float

    # Target projections
    target_price_rub: float  # Recommended WB price
    target_est_margin_pct: float
    target_est_roic_pct: float
    margin_headroom_pct: float  # How much margin vs Kaspi

    # Component scores (0-100)
    demand_score: float  # Based on Kaspi velocity
    margin_score: float  # Based on projected WB margin
    competition_score: float  # Based on competitive density

    # Final
    expansion_score: float  # Weighted composite
    recommendation: str  # EXPAND, TEST, HOLD, SKIP
    confidence: str  # LOW, MEDIUM, HIGH
    notes: str


def score_sku_for_expansion(
    db_path: Path,
    sku_key: str,
    target_channel: str = "WB",
    target_price_rub: Optional[float] = None,
    competition_count: int = 0,
) -> Optional[ExpansionScore]:
    """
    Score a single SKU for expansion potential.

    Args:
        db_path: Database path
        sku_key: SKU to evaluate
        target_channel: Channel to expand to (default: WB)
        target_price_rub: Optional target price; if None, auto-calculate
        competition_count: Number of competitors on target channel

    Returns:
        ExpansionScore or None if SKU not found
    """
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # Get current Kaspi performance from fact_channel_metrics
    cursor.execute("""
        SELECT
            cm.units_30d,
            cm.roic_30d_pct,
            cm.margin_pct,
            cm.avg_selling_price_kzt,
            s.cogs_kzt
        FROM fact_channel_metrics cm
        JOIN dim_sku s ON cm.sku_key = s.sku_key
        WHERE cm.sku_key = ?
          AND cm.channel_code = 'KSP'
          AND cm.metric_date = (SELECT MAX(metric_date) FROM fact_channel_metrics)
    """, (sku_key,))

    row = cursor.fetchone()
    conn.close()

    if not row:
        return None

    units_30d, kaspi_roic, kaspi_margin, kaspi_price, cogs_kzt = row

    if not cogs_kzt or cogs_kzt <= 0:
        return None

    # Calculate WB price if not provided
    # Default: price that achieves 40% margin (conservative target)
    if not target_price_rub:
        target_price_rub = calc_wb_breakeven_price(cogs_kzt, target_margin_pct=40)

    # Calculate WB economics at target price
    wb_profit = calc_wb_profit(target_price_rub, cogs_kzt)
    wb_margin = calc_wb_margin(target_price_rub, cogs_kzt)

    # Estimate WB ROIC (assumes similar capital deployment pattern, adjust for longer lead times)
    # WB has 56-day cycle vs Kaspi's ~42 days, so ~75% of Kaspi ROIC as baseline
    wb_roic_estimate = kaspi_roic * 0.75 * (wb_margin / kaspi_margin) if kaspi_margin > 0 else 0

    # Calculate scores (0-100)
    demand_score = _calc_demand_score(units_30d)
    margin_score = _calc_margin_score(wb_margin)
    competition_score = _calc_competition_score(competition_count)

    # Weighted composite score
    # Demand: 40%, Margin: 40%, Competition: 20%
    expansion_score = (
        demand_score * 0.40
        + margin_score * 0.40
        + competition_score * 0.20
    )

    # Determine recommendation
    recommendation, confidence, notes = _get_recommendation(
        expansion_score, units_30d, wb_margin, kaspi_margin, competition_count
    )

    return ExpansionScore(
        sku_key=sku_key,
        source_channel="KSP",
        target_channel=target_channel,
        score_date=date.today(),
        source_d30=units_30d,
        source_roic_pct=kaspi_roic,
        source_margin_pct=kaspi_margin,
        source_avg_price_kzt=kaspi_price,
        target_price_rub=target_price_rub,
        target_est_margin_pct=wb_margin,
        target_est_roic_pct=wb_roic_estimate,
        margin_headroom_pct=wb_margin - kaspi_margin,
        demand_score=demand_score,
        margin_score=margin_score,
        competition_score=competition_score,
        expansion_score=expansion_score,
        recommendation=recommendation,
        confidence=confidence,
        notes=notes,
    )


def _calc_demand_score(units_30d: float) -> float:
    """
    Calculate demand score based on 30-day units.

    Scoring:
    - 0-10 units: 0-30 (low demand)
    - 10-30 units: 30-60 (moderate)
    - 30-100 units: 60-85 (good)
    - 100+ units: 85-100 (excellent)
    """
    if units_30d <= 0:
        return 0
    if units_30d <= 10:
        return units_30d * 3  # 0-30
    if units_30d <= 30:
        return 30 + (units_30d - 10) * 1.5  # 30-60
    if units_30d <= 100:
        return 60 + (units_30d - 30) * 0.36  # 60-85
    return min(85 + (units_30d - 100) * 0.15, 100)  # 85-100


def _calc_margin_score(margin_pct: float) -> float:
    """
    Calculate margin score based on projected WB margin.

    Scoring:
    - <20%: 0-30 (thin margin, risky)
    - 20-35%: 30-60 (acceptable)
    - 35-50%: 60-85 (good)
    - 50%+: 85-100 (excellent)
    """
    if margin_pct <= 0:
        return 0
    if margin_pct <= 20:
        return margin_pct * 1.5  # 0-30
    if margin_pct <= 35:
        return 30 + (margin_pct - 20) * 2  # 30-60
    if margin_pct <= 50:
        return 60 + (margin_pct - 35) * 1.67  # 60-85
    return min(85 + (margin_pct - 50) * 0.3, 100)  # 85-100


def _calc_competition_score(competition_count: int) -> float:
    """
    Calculate competition score (inverse of competition density).

    Scoring:
    - 0 competitors: 100 (blue ocean)
    - 1-3: 80-90 (low competition)
    - 4-10: 50-80 (moderate)
    - 10+: 20-50 (high competition)
    """
    if competition_count <= 0:
        return 100
    if competition_count <= 3:
        return 90 - competition_count * 3  # 90-80
    if competition_count <= 10:
        return 80 - (competition_count - 3) * 4.3  # 80-50
    return max(50 - (competition_count - 10) * 3, 20)  # 50-20


def _get_recommendation(
    expansion_score: float,
    units_30d: float,
    wb_margin: float,
    kaspi_margin: float,
    competition_count: int,
) -> tuple[str, str, str]:
    """Determine recommendation, confidence, and notes."""
    # Strong EXPAND signals
    if expansion_score >= 75 and wb_margin >= 40:
        confidence = "HIGH" if units_30d >= 30 else "MEDIUM"
        notes = f"Strong candidate: {expansion_score:.0f} score, {wb_margin:.1f}% margin"
        return "EXPAND", confidence, notes

    # TEST candidates
    if expansion_score >= 50:
        if wb_margin >= 35:
            confidence = "MEDIUM"
            notes = f"Worth testing: {expansion_score:.0f} score, moderate risk"
            return "TEST", confidence, notes
        else:
            confidence = "LOW"
            notes = f"Thin margin ({wb_margin:.1f}%), proceed cautiously"
            return "TEST", confidence, notes

    # HOLD - not ready but potential
    if expansion_score >= 30 and wb_margin >= 30:
        notes = "Below threshold but has potential; monitor Kaspi performance"
        return "HOLD", "LOW", notes

    # SKIP - not viable
    if wb_margin < 20:
        notes = f"Margin too thin ({wb_margin:.1f}%), not viable at current costs"
    elif units_30d < 5:
        notes = f"Demand too low ({units_30d:.0f} units/30d), focus on Kaspi first"
    elif competition_count > 15:
        notes = f"High competition ({competition_count} sellers), differentiation needed"
    else:
        notes = f"Low expansion score ({expansion_score:.0f}), not recommended"

    return "SKIP", "HIGH", notes


def score_all_skus(
    db_path: Path,
    source_channel: str = "KSP",
    target_channel: str = "WB",
    min_units_30d: int = 5,
) -> list[ExpansionScore]:
    """
    Score all eligible SKUs for expansion.

    Args:
        db_path: Database path
        source_channel: Current selling channel
        target_channel: Expansion target channel
        min_units_30d: Minimum 30-day units to consider

    Returns:
        List of ExpansionScores, sorted by expansion_score descending
    """
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # Get all SKUs meeting criteria
    cursor.execute("""
        SELECT DISTINCT sku_key
        FROM fact_channel_metrics
        WHERE channel_code = ?
          AND units_30d >= ?
          AND metric_date = (SELECT MAX(metric_date) FROM fact_channel_metrics)
    """, (source_channel, min_units_30d))

    skus = [row[0] for row in cursor.fetchall()]
    conn.close()

    # Score each SKU
    scores = []
    for sku in skus:
        score = score_sku_for_expansion(db_path, sku, target_channel)
        if score:
            scores.append(score)

    # Sort by expansion_score descending
    scores.sort(key=lambda x: x.expansion_score, reverse=True)

    return scores


def save_expansion_scores(db_path: Path, scores: list[ExpansionScore]) -> int:
    """Save expansion scores to fact_expansion_scores."""
    if not scores:
        return 0

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    saved = 0
    for s in scores:
        cursor.execute("""
            INSERT INTO fact_expansion_scores (
                score_date, sku_key, source_channel, target_channel,
                source_d30, source_roic_pct, source_margin_pct, source_avg_price_kzt,
                target_price_rub, target_est_margin_pct, target_est_roic_pct, margin_headroom_pct,
                demand_score, margin_score, competition_score, expansion_score,
                recommendation, confidence, notes
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(score_date, sku_key, target_channel)
            DO UPDATE SET
                source_d30 = excluded.source_d30,
                source_roic_pct = excluded.source_roic_pct,
                source_margin_pct = excluded.source_margin_pct,
                source_avg_price_kzt = excluded.source_avg_price_kzt,
                target_price_rub = excluded.target_price_rub,
                target_est_margin_pct = excluded.target_est_margin_pct,
                target_est_roic_pct = excluded.target_est_roic_pct,
                margin_headroom_pct = excluded.margin_headroom_pct,
                demand_score = excluded.demand_score,
                margin_score = excluded.margin_score,
                competition_score = excluded.competition_score,
                expansion_score = excluded.expansion_score,
                recommendation = excluded.recommendation,
                confidence = excluded.confidence,
                notes = excluded.notes
        """, (
            s.score_date.isoformat(),
            s.sku_key,
            s.source_channel,
            s.target_channel,
            s.source_d30,
            s.source_roic_pct,
            s.source_margin_pct,
            s.source_avg_price_kzt,
            s.target_price_rub,
            s.target_est_margin_pct,
            s.target_est_roic_pct,
            s.margin_headroom_pct,
            s.demand_score,
            s.margin_score,
            s.competition_score,
            s.expansion_score,
            s.recommendation,
            s.confidence,
            s.notes,
        ))
        saved += 1

    conn.commit()
    conn.close()

    return saved


if __name__ == "__main__":
    print("Expansion Scorer Module")
    print("=" * 60)

    # Score all eligible SKUs
    scores = score_all_skus(DB_PATH, min_units_30d=5)

    print(f"\nScored {len(scores)} SKUs for WB expansion potential")

    if scores:
        # Group by recommendation
        by_rec = {}
        for s in scores:
            by_rec.setdefault(s.recommendation, []).append(s)

        for rec in ["EXPAND", "TEST", "HOLD", "SKIP"]:
            if rec in by_rec:
                print(f"\n{rec}: {len(by_rec[rec])} SKUs")
                for s in by_rec[rec][:3]:  # Top 3 per category
                    print(f"  {s.sku_key}: score={s.expansion_score:.0f}, margin={s.target_est_margin_pct:.1f}%")
