"""
TASK-031: Day-of-Week Pattern Detection

Detect and apply day-of-week sales patterns for improved forecasting.
Kaspi typically shows weekend traffic spikes (Sat/Sun 20-40% higher).
"""

from datetime import date, timedelta
from typing import Optional
import sqlite3


def calc_dow_indices(
    daily_sales: list[tuple[date, float]],
    min_weeks: int = 4
) -> dict[int, float]:
    """
    Calculate day-of-week sales indices.

    Returns day-of-week index (0=Mon, 6=Sun) -> multiplier.
    Multiplier = avg_sales_on_dow / overall_avg_sales

    Example result: {0: 0.85, 1: 0.90, 2: 0.95, 3: 1.0, 4: 1.05, 5: 1.15, 6: 1.10}

    Args:
        daily_sales: List of (date, units_sold) tuples
        min_weeks: Minimum weeks of data required (default: 4)

    Returns:
        Dict mapping weekday (0-6) to multiplier
    """
    if not daily_sales:
        return {i: 1.0 for i in range(7)}

    # Group sales by day of week
    dow_totals = {i: 0.0 for i in range(7)}
    dow_counts = {i: 0 for i in range(7)}

    for sale_date, units in daily_sales:
        dow = sale_date.weekday()  # 0=Monday, 6=Sunday
        dow_totals[dow] += units
        dow_counts[dow] += 1

    # Check minimum data requirement
    min_count = min(dow_counts.values())
    if min_count < min_weeks:
        # Not enough data, return neutral indices
        return {i: 1.0 for i in range(7)}

    # Calculate averages per day of week
    dow_avgs = {}
    for dow in range(7):
        if dow_counts[dow] > 0:
            dow_avgs[dow] = dow_totals[dow] / dow_counts[dow]
        else:
            dow_avgs[dow] = 0.0

    # Calculate overall average
    total_units = sum(dow_totals.values())
    total_days = sum(dow_counts.values())

    if total_days == 0 or total_units == 0:
        return {i: 1.0 for i in range(7)}

    overall_avg = total_units / total_days

    # Calculate indices (normalized multipliers)
    indices = {}
    for dow in range(7):
        if overall_avg > 0:
            indices[dow] = dow_avgs[dow] / overall_avg
        else:
            indices[dow] = 1.0

    return indices


def apply_dow_adjustment(
    base_forecast: float,
    target_dow: int,
    dow_indices: dict[int, float]
) -> float:
    """
    Adjust forecast for specific day of week.

    Args:
        base_forecast: Base daily forecast value
        target_dow: Target day of week (0=Mon, 6=Sun)
        dow_indices: Dict of dow -> multiplier

    Returns:
        Adjusted forecast value
    """
    if target_dow not in dow_indices:
        return base_forecast

    multiplier = dow_indices[target_dow]
    return base_forecast * multiplier


def calc_weekend_lift(dow_indices: dict[int, float]) -> float:
    """
    Calculate weekend lift vs weekday average.

    Weekend = Saturday (5) + Sunday (6)
    Weekday = Monday (0) through Friday (4)

    Args:
        dow_indices: Dict of dow -> multiplier

    Returns:
        Weekend lift as percentage (e.g., 25 = 25% higher)
    """
    weekday_avg = sum(dow_indices.get(i, 1.0) for i in range(5)) / 5
    weekend_avg = (dow_indices.get(5, 1.0) + dow_indices.get(6, 1.0)) / 2

    if weekday_avg == 0:
        return 0.0

    lift = (weekend_avg - weekday_avg) / weekday_avg * 100
    return round(lift, 1)


def calc_pattern_strength(dow_indices: dict[int, float]) -> float:
    """
    Calculate pattern strength (variability across days).

    Higher std dev = more pronounced day-of-week pattern.
    Low: < 0.1, Medium: 0.1-0.2, High: > 0.2

    Args:
        dow_indices: Dict of dow -> multiplier

    Returns:
        Standard deviation of indices
    """
    if len(dow_indices) < 7:
        return 0.0

    values = list(dow_indices.values())
    mean = sum(values) / len(values)
    variance = sum((x - mean) ** 2 for x in values) / len(values)

    import math
    return round(math.sqrt(variance), 3)


def get_dow_name(dow: int) -> str:
    """
    Get day name from weekday number.

    Args:
        dow: Weekday number (0=Mon, 6=Sun)

    Returns:
        Day name string
    """
    names = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']
    return names[dow] if 0 <= dow <= 6 else 'Unknown'


def analyze_sku_dow_pattern(
    sku_key: str,
    db_path: str,
    lookback_days: int = 90
) -> dict:
    """
    Analyze DOW pattern for a specific SKU.

    Args:
        sku_key: SKU to analyze
        db_path: Path to database
        lookback_days: Days of history to analyze

    Returns:
        Dict with indices, weekend_lift, pattern_strength
    """
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    cutoff = (date.today() - timedelta(days=lookback_days)).isoformat()

    cursor.execute("""
        SELECT sale_date, SUM(units) as daily_units
        FROM fact_sales_daily
        WHERE sku_key = ? AND sale_date >= ?
        GROUP BY sale_date
        ORDER BY sale_date
    """, (sku_key, cutoff))

    daily_sales = []
    for row in cursor.fetchall():
        sale_date = date.fromisoformat(row[0])
        units = float(row[1])
        daily_sales.append((sale_date, units))

    conn.close()

    indices = calc_dow_indices(daily_sales)
    weekend_lift = calc_weekend_lift(indices)
    pattern_strength = calc_pattern_strength(indices)

    return {
        'sku_key': sku_key,
        'indices': indices,
        'weekend_lift': weekend_lift,
        'pattern_strength': pattern_strength,
        'sample_days': len(daily_sales),
        'has_strong_pattern': pattern_strength > 0.15
    }


def analyze_all_skus_dow(
    db_path: str,
    lookback_days: int = 90,
    min_sales_days: int = 30
) -> list[dict]:
    """
    Analyze DOW patterns for all SKUs.

    Args:
        db_path: Path to database
        lookback_days: Days of history to analyze
        min_sales_days: Minimum days with sales required

    Returns:
        List of DOW analysis dicts per SKU
    """
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # Get SKUs with sufficient data
    cutoff = (date.today() - timedelta(days=lookback_days)).isoformat()

    cursor.execute("""
        SELECT sku_key, COUNT(DISTINCT sale_date) as days_with_sales
        FROM fact_sales_daily
        WHERE sale_date >= ?
        GROUP BY sku_key
        HAVING days_with_sales >= ?
    """, (cutoff, min_sales_days))

    skus = [row[0] for row in cursor.fetchall()]
    conn.close()

    results = []
    for sku_key in skus:
        result = analyze_sku_dow_pattern(sku_key, db_path, lookback_days)
        results.append(result)

    return results
