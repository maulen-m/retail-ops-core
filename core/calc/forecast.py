"""
TASK-025: Trend-Adjusted Demand Forecasting

Replaces flat D30 with trend-weighted demand calculation.
Uses exponentially-weighted moving average and linear regression for trend detection.
"""

from datetime import date, timedelta
from typing import Optional
import math


def calc_weighted_demand(
    daily_sales: list[tuple[date, float]],
    lookback_days: int = 30,
    decay_factor: float = 0.95
) -> float:
    """
    Exponentially-weighted moving average demand.

    Recent days weighted higher than older days.
    decay_factor=0.95 means yesterday = 100%, 7 days ago = 70%, 30 days ago = 21%

    Args:
        daily_sales: List of (date, units_sold) tuples, sorted by date ascending
        lookback_days: Number of days to consider (default: 30)
        decay_factor: Exponential decay rate (default: 0.95)

    Returns:
        Weighted average daily demand (float >= 0)
    """
    if not daily_sales:
        return 0.0

    # Sort by date descending for recency weighting
    sorted_sales = sorted(daily_sales, key=lambda x: x[0], reverse=True)

    # Only consider lookback_days
    cutoff_date = sorted_sales[0][0] - timedelta(days=lookback_days)
    filtered = [(d, units) for d, units in sorted_sales if d > cutoff_date]

    if not filtered:
        return 0.0

    # Calculate weighted sum
    weighted_sum = 0.0
    weight_sum = 0.0

    most_recent_date = filtered[0][0]

    for sale_date, units in filtered:
        days_ago = (most_recent_date - sale_date).days
        weight = decay_factor ** days_ago
        weighted_sum += units * weight
        weight_sum += weight

    if weight_sum == 0:
        return 0.0

    return weighted_sum / weight_sum


def calc_trend_slope(
    daily_sales: list[tuple[date, float]],
    lookback_days: int = 30
) -> float:
    """
    Linear regression slope over lookback period.

    Returns daily change rate (can be negative).
    Positive = growing demand, Negative = declining demand.

    Args:
        daily_sales: List of (date, units_sold) tuples
        lookback_days: Number of days to consider (default: 30)

    Returns:
        Daily change rate (units per day)
    """
    if not daily_sales or len(daily_sales) < 2:
        return 0.0

    # Sort by date ascending
    sorted_sales = sorted(daily_sales, key=lambda x: x[0])

    # Filter to lookback period
    most_recent = sorted_sales[-1][0]
    cutoff_date = most_recent - timedelta(days=lookback_days)
    filtered = [(d, units) for d, units in sorted_sales if d > cutoff_date]

    if len(filtered) < 2:
        return 0.0

    # Convert dates to numeric (days since first date in period)
    base_date = filtered[0][0]
    x_values = [(d - base_date).days for d, _ in filtered]
    y_values = [units for _, units in filtered]

    n = len(x_values)

    # Simple linear regression
    sum_x = sum(x_values)
    sum_y = sum(y_values)
    sum_xy = sum(x * y for x, y in zip(x_values, y_values))
    sum_x2 = sum(x * x for x in x_values)

    denominator = n * sum_x2 - sum_x * sum_x

    if denominator == 0:
        return 0.0

    slope = (n * sum_xy - sum_x * sum_y) / denominator

    return slope


def calc_d_forecast(
    daily_sales: list[tuple[date, float]],
    horizon_days: int = 7,
    lookback_days: int = 30,
    decay_factor: float = 0.95
) -> float:
    """
    Forecast demand for next N days.

    D_forecast = weighted_demand * horizon_days * (1 + trend_adjustment)

    Where trend_adjustment accounts for growth/decline patterns.
    Result is clamped to >= 0 (no negative demand).

    Args:
        daily_sales: List of (date, units_sold) tuples
        horizon_days: Days to forecast (default: 7)
        lookback_days: Historical days to consider (default: 30)
        decay_factor: Exponential decay for recency weighting (default: 0.95)

    Returns:
        Total forecasted units for horizon period (float >= 0)
    """
    if not daily_sales:
        return 0.0

    # Get base demand rate
    weighted_demand = calc_weighted_demand(daily_sales, lookback_days, decay_factor)

    if weighted_demand == 0:
        return 0.0

    # Get trend
    trend_slope = calc_trend_slope(daily_sales, lookback_days)

    # Calculate trend adjustment as percentage of current demand
    # Limit trend effect to ±50% to prevent wild swings
    trend_pct = trend_slope / weighted_demand if weighted_demand > 0 else 0
    trend_adjustment = max(-0.5, min(0.5, trend_pct * horizon_days))

    # Apply adjustment
    adjusted_demand = weighted_demand * (1 + trend_adjustment)

    # Calculate total for horizon
    forecast = adjusted_demand * horizon_days

    # Clamp to >= 0
    return max(0.0, forecast)


def calc_d_forecast_daily(
    daily_sales: list[tuple[date, float]],
    horizon_days: int = 7,
    lookback_days: int = 30,
    decay_factor: float = 0.95
) -> float:
    """
    Forecast average daily demand for horizon period.

    Returns daily rate, not total.

    Args:
        daily_sales: List of (date, units_sold) tuples
        horizon_days: Days to forecast (default: 7)
        lookback_days: Historical days to consider (default: 30)
        decay_factor: Exponential decay for recency weighting (default: 0.95)

    Returns:
        Average daily forecasted units (float >= 0)
    """
    total_forecast = calc_d_forecast(
        daily_sales, horizon_days, lookback_days, decay_factor
    )

    if horizon_days <= 0:
        return 0.0

    return total_forecast / horizon_days


def calc_confidence_interval(
    daily_sales: list[tuple[date, float]],
    forecast: float,
    lookback_days: int = 30,
    confidence_level: float = 0.80
) -> tuple[float, float]:
    """
    Calculate confidence interval for forecast.

    Uses historical standard deviation to estimate uncertainty.
    80% CI uses z = 1.28, 95% CI uses z = 1.65

    Args:
        daily_sales: List of (date, units_sold) tuples
        forecast: Point forecast value
        lookback_days: Days to consider for volatility
        confidence_level: Confidence level (default: 0.80)

    Returns:
        Tuple of (lower_bound, upper_bound)
    """
    if not daily_sales or forecast <= 0:
        return (0.0, 0.0)

    # Calculate std dev of daily sales
    sorted_sales = sorted(daily_sales, key=lambda x: x[0], reverse=True)
    most_recent = sorted_sales[0][0]
    cutoff = most_recent - timedelta(days=lookback_days)

    values = [units for d, units in sorted_sales if d > cutoff]

    if len(values) < 2:
        # Not enough data, return wide interval
        return (forecast * 0.5, forecast * 1.5)

    mean = sum(values) / len(values)
    variance = sum((x - mean) ** 2 for x in values) / (len(values) - 1)
    std_dev = math.sqrt(variance)

    # Z-score based on confidence level
    z_scores = {
        0.80: 1.28,
        0.90: 1.65,
        0.95: 1.96,
    }
    z = z_scores.get(confidence_level, 1.28)

    # Coefficient of variation approach
    cv = std_dev / mean if mean > 0 else 0.4

    lower = forecast * (1 - z * cv)
    upper = forecast * (1 + z * cv)

    return (max(0.0, lower), upper)


def apply_seasonality(
    forecast: float,
    target_month: int,
    product_type: str,
    seasonality_data: dict[tuple[int, str], float]
) -> float:
    """
    Apply seasonality multiplier to forecast.

    Args:
        forecast: Base forecast value
        target_month: Month being forecasted (1-12)
        product_type: Product type code (CL, ELS, FUR)
        seasonality_data: Dict of (month, product_type) -> multiplier

    Returns:
        Seasonality-adjusted forecast
    """
    key = (target_month, product_type)
    multiplier = seasonality_data.get(key, 1.0)

    return forecast * multiplier


def get_seasonality_from_db(db_path: str) -> dict[tuple[int, str], float]:
    """
    Load seasonality data from dim_seasonality table.

    Args:
        db_path: Path to SQLite database

    Returns:
        Dict of (month, product_type) -> multiplier
    """
    import sqlite3

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    cursor.execute("""
        SELECT month, product_type, multiplier
        FROM dim_seasonality
    """)

    result = {}
    for row in cursor.fetchall():
        month, product_type, multiplier = row
        result[(month, product_type)] = multiplier

    conn.close()
    return result
