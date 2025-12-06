"""
TASK-026: Forecast Accuracy Measurement

MAPE, bias calculation, and walk-forward backtesting.
Target: MAPE < 20% for reliable forecasts.
"""

from datetime import date, timedelta
from typing import Optional
import sqlite3


def calc_mape(actuals: list[float], forecasts: list[float]) -> float:
    """
    Mean Absolute Percentage Error.

    MAPE = (1/n) * Σ |actual - forecast| / actual * 100

    Skips periods where actual = 0 to avoid division by zero.
    Target: MAPE < 20%

    Args:
        actuals: List of actual values
        forecasts: List of forecasted values (same length as actuals)

    Returns:
        MAPE as percentage (0-100+)
    """
    if len(actuals) != len(forecasts):
        raise ValueError("Actuals and forecasts must have same length")

    if not actuals:
        return 0.0

    errors = []
    for actual, forecast in zip(actuals, forecasts):
        if actual > 0:  # Skip zero actuals
            ape = abs(actual - forecast) / actual * 100
            errors.append(ape)

    if not errors:
        return 0.0

    return sum(errors) / len(errors)


def calc_forecast_bias(actuals: list[float], forecasts: list[float]) -> float:
    """
    Directional bias indicator.

    Bias = (Σ (forecast - actual) / Σ actual) * 100

    Positive = over-forecasting (predicting more than actual)
    Negative = under-forecasting (predicting less than actual)
    Target: bias within ±5%

    Args:
        actuals: List of actual values
        forecasts: List of forecasted values

    Returns:
        Bias as percentage (can be negative)
    """
    if len(actuals) != len(forecasts):
        raise ValueError("Actuals and forecasts must have same length")

    if not actuals:
        return 0.0

    total_actual = sum(actuals)
    total_forecast = sum(forecasts)

    if total_actual == 0:
        return 0.0 if total_forecast == 0 else 100.0

    bias = (total_forecast - total_actual) / total_actual * 100

    return bias


def calc_mae(actuals: list[float], forecasts: list[float]) -> float:
    """
    Mean Absolute Error (not percentage-based).

    MAE = (1/n) * Σ |actual - forecast|

    Useful when actuals can be zero.

    Args:
        actuals: List of actual values
        forecasts: List of forecasted values

    Returns:
        MAE in units
    """
    if len(actuals) != len(forecasts):
        raise ValueError("Actuals and forecasts must have same length")

    if not actuals:
        return 0.0

    total_error = sum(abs(a - f) for a, f in zip(actuals, forecasts))

    return total_error / len(actuals)


def calc_wmape(actuals: list[float], forecasts: list[float]) -> float:
    """
    Weighted Mean Absolute Percentage Error.

    WMAPE = Σ |actual - forecast| / Σ actual * 100

    More robust than MAPE for datasets with varying magnitudes.
    Weights errors by actual values (bigger days matter more).

    Args:
        actuals: List of actual values
        forecasts: List of forecasted values

    Returns:
        WMAPE as percentage
    """
    if len(actuals) != len(forecasts):
        raise ValueError("Actuals and forecasts must have same length")

    total_actual = sum(actuals)
    if total_actual == 0:
        return 0.0

    total_error = sum(abs(a - f) for a, f in zip(actuals, forecasts))

    return total_error / total_actual * 100


def backtest_forecast(
    sku_key: str,
    db_path: str,
    test_days: int = 30,
    horizon: int = 7,
    store_code: str = 'ALL'
) -> dict:
    """
    Walk-forward validation for forecast accuracy.

    For each day in test_days:
      1. Use only data available up to that point
      2. Generate forecast for next `horizon` days
      3. Compare to actual sales
      4. Accumulate error metrics

    Args:
        sku_key: SKU to backtest
        db_path: Path to SQLite database
        test_days: Number of days to test (default: 30)
        horizon: Forecast horizon in days (default: 7)
        store_code: Store to filter (default: 'ALL' for aggregate)

    Returns:
        Dict with {
            'mape': float,
            'wmape': float,
            'bias': float,
            'mae': float,
            'sample_size': int,
            'daily_errors': list of dicts
        }
    """
    from .forecast import calc_d_forecast_daily

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # Get all daily sales for this SKU
    cursor.execute("""
        SELECT sale_date, SUM(units) as daily_units
        FROM fact_sales_daily
        WHERE sku_key = ? AND (store_code = ? OR ? = 'ALL')
        GROUP BY sale_date
        ORDER BY sale_date
    """, (sku_key, store_code, store_code))

    all_sales = []
    for row in cursor.fetchall():
        sale_date = date.fromisoformat(row[0])
        units = float(row[1])
        all_sales.append((sale_date, units))

    conn.close()

    if len(all_sales) < test_days + horizon + 30:
        # Not enough data for meaningful backtest
        return {
            'mape': None,
            'wmape': None,
            'bias': None,
            'mae': None,
            'sample_size': 0,
            'daily_errors': [],
            'error': 'Insufficient data'
        }

    # Sort chronologically
    all_sales.sort(key=lambda x: x[0])

    # Create date -> units lookup
    sales_lookup = {d: u for d, u in all_sales}

    # Walk-forward: for each test day, forecast and compare
    actuals = []
    forecasts = []
    daily_errors = []

    # Start testing from (end - test_days)
    end_date = all_sales[-1][0]
    start_test_date = end_date - timedelta(days=test_days)

    current_date = start_test_date

    while current_date <= end_date - timedelta(days=horizon):
        # Get historical data up to current_date
        historical = [(d, u) for d, u in all_sales if d < current_date]

        if len(historical) < 30:
            current_date += timedelta(days=1)
            continue

        # Generate forecast
        forecast_daily = calc_d_forecast_daily(
            historical,
            horizon_days=horizon,
            lookback_days=30
        )

        # Get actual sales for horizon period
        actual_total = 0.0
        for i in range(horizon):
            check_date = current_date + timedelta(days=i)
            actual_total += sales_lookup.get(check_date, 0.0)

        actual_daily = actual_total / horizon

        actuals.append(actual_daily)
        forecasts.append(forecast_daily)

        # Track daily error
        error = abs(actual_daily - forecast_daily)
        pct_error = (error / actual_daily * 100) if actual_daily > 0 else 0

        daily_errors.append({
            'date': current_date.isoformat(),
            'forecast': round(forecast_daily, 2),
            'actual': round(actual_daily, 2),
            'error': round(error, 2),
            'pct_error': round(pct_error, 1)
        })

        current_date += timedelta(days=1)

    if not actuals:
        return {
            'mape': None,
            'wmape': None,
            'bias': None,
            'mae': None,
            'sample_size': 0,
            'daily_errors': [],
            'error': 'No valid test periods'
        }

    return {
        'mape': round(calc_mape(actuals, forecasts), 2),
        'wmape': round(calc_wmape(actuals, forecasts), 2),
        'bias': round(calc_forecast_bias(actuals, forecasts), 2),
        'mae': round(calc_mae(actuals, forecasts), 3),
        'sample_size': len(actuals),
        'daily_errors': daily_errors
    }


def backtest_all_skus(
    db_path: str,
    test_days: int = 30,
    horizon: int = 7,
    min_sales_days: int = 60
) -> list[dict]:
    """
    Run backtest for all SKUs with sufficient history.

    Args:
        db_path: Path to SQLite database
        test_days: Number of days to test
        horizon: Forecast horizon in days
        min_sales_days: Minimum days of sales required

    Returns:
        List of backtest results per SKU
    """
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # Get SKUs with sufficient history
    cursor.execute("""
        SELECT sku_key, COUNT(DISTINCT sale_date) as days_with_sales
        FROM fact_sales_daily
        GROUP BY sku_key
        HAVING days_with_sales >= ?
    """, (min_sales_days,))

    skus = [row[0] for row in cursor.fetchall()]
    conn.close()

    results = []
    for sku_key in skus:
        result = backtest_forecast(
            sku_key=sku_key,
            db_path=db_path,
            test_days=test_days,
            horizon=horizon
        )
        result['sku_key'] = sku_key
        results.append(result)

    return results


def get_accuracy_grade(mape: Optional[float]) -> str:
    """
    Convert MAPE to letter grade.

    A: MAPE < 10% (excellent)
    B: MAPE 10-20% (good, target)
    C: MAPE 20-30% (acceptable)
    D: MAPE 30-50% (poor)
    F: MAPE > 50% (needs work)

    Args:
        mape: MAPE value or None

    Returns:
        Letter grade string
    """
    if mape is None:
        return 'N/A'

    if mape < 10:
        return 'A'
    elif mape < 20:
        return 'B'
    elif mape < 30:
        return 'C'
    elif mape < 50:
        return 'D'
    else:
        return 'F'
