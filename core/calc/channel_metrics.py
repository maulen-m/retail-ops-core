"""
Channel-level metrics calculation for Phase 8.

Computes daily and rolling metrics per SKU per channel.
"""
import sqlite3
from pathlib import Path
from datetime import date, timedelta
from dataclasses import dataclass
from typing import Optional

DB_PATH = Path(__file__).parent.parent.parent / "db" / "app.db"


@dataclass
class ChannelMetrics:
    """Metrics for a SKU on a specific channel."""

    sku_key: str
    channel_code: str
    store_code: str
    metric_date: date

    # Daily
    units_sold: int
    units_returned: int
    net_units: int
    gross_revenue_kzt: float
    net_revenue_kzt: float
    cogs_kzt: float
    profit_kzt: float
    avg_selling_price_kzt: float
    margin_pct: float
    return_rate_pct: float

    # Rolling 30-day
    units_30d: int
    revenue_30d_kzt: float
    profit_30d_kzt: float
    roic_30d_pct: float


def calc_channel_metrics_for_date(
    db_path: Path,
    metric_date: date,
    channel_code: Optional[str] = None,
) -> list[ChannelMetrics]:
    """
    Calculate channel metrics for all SKUs for a given date.

    Args:
        db_path: Path to database
        metric_date: Date to calculate metrics for
        channel_code: Optional filter for specific channel

    Returns:
        List of ChannelMetrics
    """
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    date_str = metric_date.isoformat()
    date_30d_ago = (metric_date - timedelta(days=30)).isoformat()

    # Build channel filter
    channel_filter = ""
    params_daily = [date_str]
    params_rolling = [date_30d_ago, date_str]

    if channel_code:
        channel_filter = "AND COALESCE(fs.channel_code, 'KSP') = ?"
        params_daily.append(channel_code)
        params_rolling.append(channel_code)

    # Query daily metrics
    cursor.execute(f"""
        SELECT
            sku_key,
            COALESCE(channel_code, 'KSP') as channel_code,
            store_code,
            SUM(CASE WHEN quantity > 0 THEN quantity ELSE 0 END) as units_sold,
            SUM(CASE WHEN quantity < 0 THEN ABS(quantity) ELSE 0 END) as units_returned,
            SUM(quantity) as net_units,
            SUM(CASE WHEN quantity > 0 THEN sell_price_kzt * quantity ELSE 0 END) as gross_revenue,
            SUM(net_rev_kzt) as net_revenue,
            SUM(CASE WHEN quantity > 0 THEN cogs_kzt * quantity ELSE 0 END) as cogs,
            SUM(profit_kzt) as profit
        FROM fact_sales fs
        WHERE DATE(order_date) = ?
        {channel_filter}
        GROUP BY sku_key, COALESCE(channel_code, 'KSP'), store_code
    """, params_daily)

    daily_data = {}
    for row in cursor.fetchall():
        key = (row[0], row[1], row[2])  # sku_key, channel, store
        daily_data[key] = {
            "units_sold": row[3] or 0,
            "units_returned": row[4] or 0,
            "net_units": row[5] or 0,
            "gross_revenue": row[6] or 0,
            "net_revenue": row[7] or 0,
            "cogs": row[8] or 0,
            "profit": row[9] or 0,
        }

    # Query rolling 30-day metrics
    cursor.execute(f"""
        SELECT
            sku_key,
            COALESCE(channel_code, 'KSP') as channel_code,
            store_code,
            SUM(quantity) as units_30d,
            SUM(net_rev_kzt) as revenue_30d,
            SUM(profit_kzt) as profit_30d
        FROM fact_sales fs
        WHERE DATE(order_date) BETWEEN ? AND ?
        {channel_filter}
        GROUP BY sku_key, COALESCE(channel_code, 'KSP'), store_code
    """, params_rolling)

    rolling_data = {}
    for row in cursor.fetchall():
        key = (row[0], row[1], row[2])
        rolling_data[key] = {
            "units_30d": row[3] or 0,
            "revenue_30d": row[4] or 0,
            "profit_30d": row[5] or 0,
        }

    # Query capital data for ROIC
    cursor.execute("""
        SELECT sku_key, total_capital_kzt
        FROM fact_capital_allocation
        WHERE snapshot_date = (SELECT MAX(snapshot_date) FROM fact_capital_allocation)
    """)
    capital_data = dict(cursor.fetchall())

    conn.close()

    # Build results
    results = []

    # Get all unique keys from either daily or rolling data
    all_keys = set(daily_data.keys()) | set(rolling_data.keys())

    for key in all_keys:
        sku_key, channel, store = key
        daily = daily_data.get(key, {
            "units_sold": 0, "units_returned": 0, "net_units": 0,
            "gross_revenue": 0, "net_revenue": 0, "cogs": 0, "profit": 0,
        })
        rolling = rolling_data.get(key, {"units_30d": 0, "revenue_30d": 0, "profit_30d": 0})
        capital = capital_data.get(sku_key, 0)

        # Calculate derived metrics
        units_sold = daily["units_sold"]
        units_returned = daily["units_returned"]
        gross_rev = daily["gross_revenue"]
        net_rev = daily["net_revenue"]
        profit = daily["profit"]

        avg_price = gross_rev / units_sold if units_sold > 0 else 0
        margin = (profit / net_rev * 100) if net_rev > 0 else 0
        total_handled = units_sold + units_returned
        return_rate = (units_returned / total_handled * 100) if total_handled > 0 else 0

        # ROIC (annualized)
        profit_30d = rolling["profit_30d"]
        roic_30d = (profit_30d / capital * 100 * 12.17) if capital > 0 else 0

        results.append(ChannelMetrics(
            sku_key=sku_key,
            channel_code=channel,
            store_code=store,
            metric_date=metric_date,
            units_sold=units_sold,
            units_returned=units_returned,
            net_units=daily["net_units"],
            gross_revenue_kzt=gross_rev,
            net_revenue_kzt=net_rev,
            cogs_kzt=daily["cogs"],
            profit_kzt=profit,
            avg_selling_price_kzt=avg_price,
            margin_pct=margin,
            return_rate_pct=return_rate,
            units_30d=rolling["units_30d"],
            revenue_30d_kzt=rolling["revenue_30d"],
            profit_30d_kzt=profit_30d,
            roic_30d_pct=roic_30d,
        ))

    return results


def save_channel_metrics(db_path: Path, metrics: list[ChannelMetrics]) -> int:
    """
    Save calculated metrics to fact_channel_metrics.

    Returns:
        Number of records saved
    """
    if not metrics:
        return 0

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    saved = 0
    for m in metrics:
        cursor.execute("""
            INSERT INTO fact_channel_metrics (
                metric_date, sku_key, channel_code, store_code,
                units_sold, units_returned, net_units,
                gross_revenue_kzt, net_revenue_kzt, cogs_kzt, profit_kzt,
                avg_selling_price_kzt, margin_pct, return_rate_pct,
                units_30d, revenue_30d_kzt, profit_30d_kzt, roic_30d_pct
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(metric_date, sku_key, channel_code, store_code)
            DO UPDATE SET
                units_sold = excluded.units_sold,
                units_returned = excluded.units_returned,
                net_units = excluded.net_units,
                gross_revenue_kzt = excluded.gross_revenue_kzt,
                net_revenue_kzt = excluded.net_revenue_kzt,
                cogs_kzt = excluded.cogs_kzt,
                profit_kzt = excluded.profit_kzt,
                avg_selling_price_kzt = excluded.avg_selling_price_kzt,
                margin_pct = excluded.margin_pct,
                return_rate_pct = excluded.return_rate_pct,
                units_30d = excluded.units_30d,
                revenue_30d_kzt = excluded.revenue_30d_kzt,
                profit_30d_kzt = excluded.profit_30d_kzt,
                roic_30d_pct = excluded.roic_30d_pct
        """, (
            m.metric_date.isoformat(),
            m.sku_key,
            m.channel_code,
            m.store_code,
            m.units_sold,
            m.units_returned,
            m.net_units,
            m.gross_revenue_kzt,
            m.net_revenue_kzt,
            m.cogs_kzt,
            m.profit_kzt,
            m.avg_selling_price_kzt,
            m.margin_pct,
            m.return_rate_pct,
            m.units_30d,
            m.revenue_30d_kzt,
            m.profit_30d_kzt,
            m.roic_30d_pct,
        ))
        saved += 1

    conn.commit()
    conn.close()

    return saved


def get_latest_channel_metrics(
    db_path: Path,
    sku_key: Optional[str] = None,
    channel_code: Optional[str] = None,
) -> list[ChannelMetrics]:
    """
    Get latest channel metrics from the database.

    Args:
        db_path: Path to database
        sku_key: Optional filter for specific SKU
        channel_code: Optional filter for specific channel

    Returns:
        List of ChannelMetrics from the latest date
    """
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # Build filters
    filters = ["metric_date = (SELECT MAX(metric_date) FROM fact_channel_metrics)"]
    params = []

    if sku_key:
        filters.append("sku_key = ?")
        params.append(sku_key)

    if channel_code:
        filters.append("channel_code = ?")
        params.append(channel_code)

    where_clause = " AND ".join(filters)

    cursor.execute(f"""
        SELECT
            sku_key, channel_code, store_code, metric_date,
            units_sold, units_returned, net_units,
            gross_revenue_kzt, net_revenue_kzt, cogs_kzt, profit_kzt,
            avg_selling_price_kzt, margin_pct, return_rate_pct,
            units_30d, revenue_30d_kzt, profit_30d_kzt, roic_30d_pct
        FROM fact_channel_metrics
        WHERE {where_clause}
        ORDER BY sku_key, channel_code
    """, params)

    results = []
    for row in cursor.fetchall():
        results.append(ChannelMetrics(
            sku_key=row[0],
            channel_code=row[1],
            store_code=row[2],
            metric_date=date.fromisoformat(row[3]),
            units_sold=row[4],
            units_returned=row[5],
            net_units=row[6],
            gross_revenue_kzt=row[7],
            net_revenue_kzt=row[8],
            cogs_kzt=row[9],
            profit_kzt=row[10],
            avg_selling_price_kzt=row[11],
            margin_pct=row[12],
            return_rate_pct=row[13],
            units_30d=row[14],
            revenue_30d_kzt=row[15],
            profit_30d_kzt=row[16],
            roic_30d_pct=row[17],
        ))

    conn.close()
    return results


if __name__ == "__main__":
    from datetime import date

    print("Channel Metrics Calculator")
    print("=" * 60)

    # Test calculation
    today = date.today()
    metrics = calc_channel_metrics_for_date(DB_PATH, today)

    print(f"\nMetrics for {today}:")
    print(f"  Total SKU-channel combinations: {len(metrics)}")

    if metrics:
        print("\nSample metrics (first 3):")
        for m in metrics[:3]:
            print(f"\n  {m.sku_key} @ {m.channel_code}/{m.store_code}:")
            print(f"    Daily: {m.units_sold} sold, {m.net_units} net")
            print(f"    Revenue: {m.net_revenue_kzt:,.0f} KZT")
            print(f"    Margin: {m.margin_pct:.1f}%")
            print(f"    30d Units: {m.units_30d}, ROIC: {m.roic_30d_pct:.1f}%")
