#!/usr/bin/env python3
"""
TASK-029: Daily Forecast Engine

Generates and stores demand forecasts for all active SKUs.
Applies seasonality multipliers and calculates confidence intervals.

Usage:
    python scripts/run_forecast_engine.py [--horizon 7,14,30] [--sku-filter LINE52]
"""

import argparse
import sqlite3
from datetime import date, datetime, timedelta
from pathlib import Path
import sys

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from core.calc.forecast import (
    calc_d_forecast_daily,
    calc_confidence_interval,
    get_seasonality_from_db,
    apply_seasonality
)


def get_active_skus(db_path: str, sku_filter: str = None) -> list[dict]:
    """
    Get active SKUs with their product type.

    Args:
        db_path: Path to database
        sku_filter: Optional substring filter for sku_key

    Returns:
        List of dicts with sku_key and product_type
    """
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    query = """
        SELECT sku_key, product_type
        FROM dim_sku
        WHERE active_flag = 1
    """
    params = []

    if sku_filter:
        query += " AND sku_key LIKE ?"
        params.append(f"%{sku_filter}%")

    cursor.execute(query, params)

    skus = []
    for row in cursor.fetchall():
        skus.append({
            'sku_key': row[0],
            'product_type': row[1]
        })

    conn.close()
    return skus


def get_daily_sales(db_path: str, sku_key: str, lookback_days: int = 90) -> list[tuple]:
    """
    Get daily sales for a SKU.

    Args:
        db_path: Path to database
        sku_key: SKU to fetch
        lookback_days: Days of history to fetch

    Returns:
        List of (date, units) tuples
    """
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    cutoff = (datetime.now() - timedelta(days=lookback_days)).strftime('%Y-%m-%d')

    cursor.execute("""
        SELECT sale_date, SUM(units) as daily_units
        FROM fact_sales_daily
        WHERE sku_key = ? AND sale_date >= ?
        GROUP BY sale_date
        ORDER BY sale_date
    """, (sku_key, cutoff))

    result = []
    for row in cursor.fetchall():
        sale_date = date.fromisoformat(row[0])
        units = float(row[1])
        result.append((sale_date, units))

    conn.close()
    return result


def generate_forecasts(
    db_path: str,
    horizons: list[int],
    sku_filter: str = None,
    apply_season: bool = True
) -> dict:
    """
    Generate forecasts for all active SKUs.

    Args:
        db_path: Path to database
        horizons: List of horizon days (e.g., [7, 14, 30])
        sku_filter: Optional SKU filter
        apply_season: Whether to apply seasonality

    Returns:
        Dict with summary stats
    """
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # Get active SKUs
    skus = get_active_skus(db_path, sku_filter)
    print(f"Found {len(skus)} active SKUs")

    # Load seasonality
    seasonality = {}
    if apply_season:
        seasonality = get_seasonality_from_db(db_path)
        print(f"Loaded {len(seasonality)} seasonality multipliers")

    # Forecast date and targets
    forecast_date = date.today()
    model_version = 'v1.0'

    total_forecasts = 0
    sku_forecasts = {}
    store_code = 'ALL'  # Aggregate forecasts

    for sku in skus:
        sku_key = sku['sku_key']
        product_type = sku['product_type']

        # Get historical sales
        daily_sales = get_daily_sales(db_path, sku_key, lookback_days=90)

        if len(daily_sales) < 7:
            # Skip SKUs with insufficient history
            continue

        sku_forecasts[sku_key] = {}

        for horizon in horizons:
            # Calculate base forecast (daily rate)
            base_forecast = calc_d_forecast_daily(
                daily_sales,
                horizon_days=horizon,
                lookback_days=30
            )

            # Apply seasonality for target month
            target_month = (forecast_date + timedelta(days=horizon // 2)).month
            if apply_season and (target_month, product_type) in seasonality:
                adjusted_forecast = apply_seasonality(
                    base_forecast,
                    target_month,
                    product_type,
                    seasonality
                )
            else:
                adjusted_forecast = base_forecast

            # Calculate confidence interval
            lower, upper = calc_confidence_interval(
                daily_sales,
                adjusted_forecast * horizon,  # Total for period
                lookback_days=30,
                confidence_level=0.80
            )

            # Store forecast for each target day
            for day_offset in range(horizon):
                target_date = forecast_date + timedelta(days=day_offset)

                cursor.execute("""
                    INSERT OR REPLACE INTO fact_demand_forecast (
                        forecast_date, target_date, sku_key, store_code,
                        horizon_days, predicted_units, confidence_lower,
                        confidence_upper, model_version
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    forecast_date.isoformat(),
                    target_date.isoformat(),
                    sku_key,
                    store_code,
                    horizon,
                    round(adjusted_forecast, 3),
                    round(lower / horizon, 3) if horizon > 0 else 0,
                    round(upper / horizon, 3) if horizon > 0 else 0,
                    model_version
                ))

                total_forecasts += 1

            sku_forecasts[sku_key][horizon] = round(adjusted_forecast, 2)

    conn.commit()
    conn.close()

    return {
        'total_forecasts': total_forecasts,
        'skus_processed': len(sku_forecasts),
        'horizons': horizons,
        'forecast_date': forecast_date.isoformat(),
        'sku_forecasts': sku_forecasts
    }


def main():
    parser = argparse.ArgumentParser(description='Generate demand forecasts')
    parser.add_argument(
        '--horizon',
        default='7,14,30',
        help='Comma-separated forecast horizons (default: 7,14,30)'
    )
    parser.add_argument(
        '--sku-filter',
        help='Filter SKUs by substring (e.g., LINE52)'
    )
    parser.add_argument(
        '--no-seasonality',
        action='store_true',
        help='Disable seasonality adjustment'
    )
    parser.add_argument(
        '--db',
        default='db/app.db',
        help='Path to database (default: db/app.db)'
    )
    args = parser.parse_args()

    # Parse horizons
    horizons = [int(h.strip()) for h in args.horizon.split(',')]

    # Resolve database path
    db_path = Path(args.db)
    if not db_path.is_absolute():
        db_path = project_root / db_path

    if not db_path.exists():
        print(f"ERROR: Database not found at {db_path}")
        return 1

    print(f"=== Forecast Engine ===")
    print(f"Database: {db_path}")
    print(f"Horizons: {horizons} days")
    print(f"Seasonality: {'disabled' if args.no_seasonality else 'enabled'}")
    print()

    # Generate forecasts
    result = generate_forecasts(
        str(db_path),
        horizons,
        args.sku_filter,
        apply_season=not args.no_seasonality
    )

    print(f"\n=== Summary ===")
    print(f"Forecast date: {result['forecast_date']}")
    print(f"SKUs processed: {result['skus_processed']}")
    print(f"Total forecasts: {result['total_forecasts']}")

    # Show top SKUs by 7-day forecast
    if result['sku_forecasts']:
        print(f"\nTop 10 SKUs by 7-day demand forecast:")
        sorted_skus = sorted(
            result['sku_forecasts'].items(),
            key=lambda x: x[1].get(7, 0),
            reverse=True
        )[:10]

        for sku_key, forecasts in sorted_skus:
            d7 = forecasts.get(7, 0)
            d14 = forecasts.get(14, 0)
            d30 = forecasts.get(30, 0)
            print(f"  {sku_key}: D7={d7}, D14={d14}, D30={d30}")

    print(f"\nForecast engine complete.")
    return 0


if __name__ == '__main__':
    exit(main())
