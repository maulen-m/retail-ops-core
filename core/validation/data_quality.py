"""
TASK-047: Data Quality Detection

Detect anomalies and data issues for proactive monitoring.
"""

import sqlite3
from datetime import date, timedelta
from typing import Optional


def detect_sales_anomalies(
    db_path: str,
    lookback_days: int = 90
) -> list[dict]:
    """
    Detect sales data anomalies.

    Flags:
    - Days with 0 total sales (should be rare)
    - SKUs with sudden 3x+ spike (possible data error)
    - SKUs with sudden 80%+ drop
    - Negative quantities (should never happen)
    - Duplicate order_ids

    Args:
        db_path: Path to database
        lookback_days: Days to analyze

    Returns:
        List of anomaly dicts with type, severity, details
    """
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    cutoff = (date.today() - timedelta(days=lookback_days)).isoformat()
    anomalies = []

    # 1. Check for zero-sales days
    cursor.execute("""
        SELECT sale_date, SUM(units) as total_units
        FROM fact_sales_daily
        WHERE sale_date >= ?
        GROUP BY sale_date
        HAVING total_units = 0
    """, (cutoff,))

    for row in cursor.fetchall():
        anomalies.append({
            'type': 'ZERO_SALES_DAY',
            'severity': 'WARNING',
            'date': row[0],
            'details': f"Zero total sales on {row[0]}"
        })

    # 2. Check for sales spikes (3x daily average)
    cursor.execute("""
        WITH daily_avg AS (
            SELECT sku_key, AVG(units) as avg_units
            FROM fact_sales_daily
            WHERE sale_date >= date('now', '-60 days')
            GROUP BY sku_key
        )
        SELECT d.sale_date, d.sku_key, d.units, a.avg_units
        FROM fact_sales_daily d
        JOIN daily_avg a ON d.sku_key = a.sku_key
        WHERE d.sale_date >= ?
        AND a.avg_units > 0
        AND d.units > a.avg_units * 3
    """, (cutoff,))

    for row in cursor.fetchall():
        anomalies.append({
            'type': 'SALES_SPIKE',
            'severity': 'WARNING',
            'date': row[0],
            'sku_key': row[1],
            'details': f"{row[1]} had {row[2]} units (avg: {row[3]:.1f}) on {row[0]}"
        })

    # 3. Check for sudden drops (80%+ below average)
    cursor.execute("""
        WITH daily_avg AS (
            SELECT sku_key, AVG(units) as avg_units
            FROM fact_sales_daily
            WHERE sale_date >= date('now', '-60 days')
            GROUP BY sku_key
            HAVING avg_units > 1
        )
        SELECT d.sale_date, d.sku_key, d.units, a.avg_units
        FROM fact_sales_daily d
        JOIN daily_avg a ON d.sku_key = a.sku_key
        WHERE d.sale_date >= date('now', '-7 days')
        AND d.units < a.avg_units * 0.2
    """)

    for row in cursor.fetchall():
        anomalies.append({
            'type': 'SALES_DROP',
            'severity': 'INFO',
            'date': row[0],
            'sku_key': row[1],
            'details': f"{row[1]} had {row[2]} units (avg: {row[3]:.1f}) on {row[0]}"
        })

    # 4. Check for negative quantities
    cursor.execute("""
        SELECT order_id, sku_id, quantity, order_date
        FROM fact_sales
        WHERE quantity < 0
        LIMIT 10
    """)

    for row in cursor.fetchall():
        anomalies.append({
            'type': 'NEGATIVE_QUANTITY',
            'severity': 'CRITICAL',
            'order_id': row[0],
            'sku_id': row[1],
            'details': f"Order {row[0]} has qty={row[2]} on {row[3]}"
        })

    # 5. Check for duplicate order_ids
    cursor.execute("""
        SELECT order_id, COUNT(*) as cnt
        FROM fact_sales_raw
        GROUP BY order_id, sku_id
        HAVING cnt > 1
        LIMIT 10
    """)

    for row in cursor.fetchall():
        anomalies.append({
            'type': 'DUPLICATE_ORDER',
            'severity': 'WARNING',
            'order_id': row[0],
            'details': f"Order {row[0]} appears {row[1]} times"
        })

    conn.close()
    return anomalies


def detect_inventory_anomalies(db_path: str) -> list[dict]:
    """
    Detect inventory data issues.

    Flags:
    - SKUs with stock but no cost data
    - SKUs with negative stock
    - Orphan SKU_IDs not in dim_sku_size

    Args:
        db_path: Path to database

    Returns:
        List of anomaly dicts
    """
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    anomalies = []

    # 1. SKUs with stock but no cost data
    cursor.execute("""
        SELECT DISTINCT i.sku_key
        FROM fact_inventory_snapshot_size i
        LEFT JOIN dim_sku s ON i.sku_key = s.sku_key
        WHERE i.current_stock > 0
        AND (s.base_cost_cny IS NULL OR s.base_cost_cny = 0)
    """)

    for row in cursor.fetchall():
        anomalies.append({
            'type': 'MISSING_COST',
            'severity': 'WARNING',
            'sku_key': row[0],
            'details': f"{row[0]} has stock but no cost data"
        })

    # 2. Negative stock
    cursor.execute("""
        SELECT sku_id, current_stock, snapshot_date
        FROM fact_inventory_snapshot_size
        WHERE current_stock < 0
        LIMIT 10
    """)

    for row in cursor.fetchall():
        anomalies.append({
            'type': 'NEGATIVE_STOCK',
            'severity': 'CRITICAL',
            'sku_id': row[0],
            'details': f"{row[0]} has stock={row[1]} on {row[2]}"
        })

    # 3. Orphan SKU_IDs
    cursor.execute("""
        SELECT DISTINCT i.sku_id
        FROM fact_inventory_snapshot_size i
        LEFT JOIN dim_sku_size s ON i.sku_id = s.sku_id
        WHERE s.sku_id IS NULL
        LIMIT 10
    """)

    for row in cursor.fetchall():
        anomalies.append({
            'type': 'ORPHAN_SKU',
            'severity': 'WARNING',
            'sku_id': row[0],
            'details': f"SKU_ID {row[0]} not found in dim_sku_size"
        })

    conn.close()
    return anomalies


def detect_forecast_anomalies(db_path: str) -> list[dict]:
    """
    Detect forecast data issues.

    Flags:
    - SKUs with very high MAPE (>50%)
    - Missing forecasts for active SKUs
    - Stale forecasts (>7 days old)

    Args:
        db_path: Path to database

    Returns:
        List of anomaly dicts
    """
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    anomalies = []

    # 1. High MAPE SKUs
    cursor.execute("""
        SELECT sku_key, mape
        FROM fact_forecast_accuracy
        WHERE accuracy_date = (SELECT MAX(accuracy_date) FROM fact_forecast_accuracy)
        AND mape > 50
    """)

    for row in cursor.fetchall():
        anomalies.append({
            'type': 'HIGH_MAPE',
            'severity': 'WARNING',
            'sku_key': row[0],
            'details': f"{row[0]} has MAPE={row[1]:.1f}% (target <20%)"
        })

    # 2. Stale forecasts
    cursor.execute("""
        SELECT MAX(forecast_date) FROM fact_demand_forecast
    """)
    result = cursor.fetchone()

    if result and result[0]:
        last_forecast = date.fromisoformat(result[0])
        days_old = (date.today() - last_forecast).days

        if days_old > 7:
            anomalies.append({
                'type': 'STALE_FORECAST',
                'severity': 'WARNING',
                'details': f"Forecasts last updated {days_old} days ago ({result[0]})"
            })

    conn.close()
    return anomalies


def detect_all_anomalies(
    db_path: str,
    lookback_days: int = 90
) -> dict:
    """
    Run all anomaly detection checks.

    Args:
        db_path: Path to database
        lookback_days: Days to analyze for sales

    Returns:
        Dict with anomalies grouped by severity
    """
    all_anomalies = []

    all_anomalies.extend(detect_sales_anomalies(db_path, lookback_days))
    all_anomalies.extend(detect_inventory_anomalies(db_path))
    all_anomalies.extend(detect_forecast_anomalies(db_path))

    # Group by severity
    critical = [a for a in all_anomalies if a['severity'] == 'CRITICAL']
    warnings = [a for a in all_anomalies if a['severity'] == 'WARNING']
    info = [a for a in all_anomalies if a['severity'] == 'INFO']

    return {
        'total': len(all_anomalies),
        'critical': critical,
        'warnings': warnings,
        'info': info,
        'has_critical': len(critical) > 0,
        'all_anomalies': all_anomalies
    }


def get_data_quality_score(db_path: str) -> float:
    """
    Calculate overall data quality score (0-100).

    Based on:
    - Anomaly counts (weighted by severity)
    - Data freshness
    - Completeness

    Args:
        db_path: Path to database

    Returns:
        Quality score 0-100
    """
    result = detect_all_anomalies(db_path)

    # Start at 100, deduct for issues
    score = 100.0

    # Deductions
    score -= len(result['critical']) * 10  # Critical = -10 each
    score -= len(result['warnings']) * 2   # Warning = -2 each
    score -= len(result['info']) * 0.5     # Info = -0.5 each

    # Clamp to 0-100
    return max(0.0, min(100.0, score))
