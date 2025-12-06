#!/usr/bin/env python3
"""
TASK-041: Weekly Portfolio Review

Analyzes portfolio performance and generates recommendations.
Updates lifecycle statuses and sends alerts.

Usage:
    python scripts/run_portfolio_review.py [--output-format csv|json] [--update-status]

Output:
    reports/portfolio_review_YYYY-MM-DD.csv
"""

import argparse
import csv
import json
import sqlite3
from datetime import date, timedelta
from pathlib import Path
import sys

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from core.calc.portfolio import (
    calc_portfolio_roic,
    calc_sku_capital_share,
    identify_kill_candidates,
    get_lifecycle_distribution,
    recommend_lifecycle_status,
    update_lifecycle_status
)
from core.calc.forecast import calc_trend_slope


def get_sku_details(db_path: str) -> list[dict]:
    """
    Get detailed SKU metrics for portfolio review.

    Args:
        db_path: Path to database

    Returns:
        List of SKU detail dicts
    """
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    cursor.execute("""
        SELECT
            m.sku_key,
            m.roic,
            m.k_avg,
            m.d30,
            m.current_stock,
            m.status,
            l.lifecycle_status,
            s.product_type
        FROM fact_sku_metrics m
        LEFT JOIN dim_sku_lifecycle l ON m.sku_key = l.sku_key
        LEFT JOIN dim_sku s ON m.sku_key = s.sku_key
    """)

    skus = []
    for row in cursor.fetchall():
        sku_key, roic, k_avg, d30, stock, status, lifecycle, product_type = row

        # Get trend
        cursor.execute("""
            SELECT sale_date, units
            FROM fact_sales_daily
            WHERE sku_key = ? AND sale_date >= date('now', '-30 days')
            ORDER BY sale_date
        """, (sku_key,))

        daily_sales = [(date.fromisoformat(r[0]), float(r[1])) for r in cursor.fetchall()]
        trend = calc_trend_slope(daily_sales) if daily_sales else 0.0

        # Calculate capital share
        capital_share = calc_sku_capital_share(sku_key, db_path)

        # Get recommended status
        recommended = recommend_lifecycle_status(roic or 0, trend, d30 or 0)

        # Generate recommendation text
        if recommended == 'GROW':
            recommendation = "Increase order quantity by 20%"
        elif recommended == 'MAINTAIN':
            recommendation = "Hold current inventory levels"
        elif recommended == 'HARVEST':
            recommendation = "Reduce orders, sell through existing stock"
        else:  # KILL
            recommendation = "Liquidate at 30% discount"

        skus.append({
            'sku_key': sku_key,
            'current_status': lifecycle or 'GROW',
            'recommended_status': recommended,
            'roic_pct': round(roic or 0, 1),
            'capital_deployed_kzt': round(k_avg or 0, 0),
            'capital_share_pct': round(capital_share, 2),
            'trend_slope': round(trend, 4),
            'd30': round(d30 or 0, 2),
            'current_stock': stock or 0,
            'status': status or 'UNKNOWN',
            'product_type': product_type,
            'recommendation': recommendation,
            'needs_update': lifecycle != recommended
        })

    conn.close()

    # Sort by capital share descending
    skus.sort(key=lambda x: x['capital_share_pct'], reverse=True)

    return skus


def generate_csv_report(skus: list[dict], output_path: Path) -> None:
    """
    Generate CSV portfolio review report.

    Args:
        skus: List of SKU detail dicts
        output_path: Path to write CSV
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with open(output_path, 'w', newline='') as f:
        writer = csv.writer(f)
        writer.writerow([
            'sku_key', 'current_status', 'recommended_status',
            'roic_pct', 'capital_deployed_kzt', 'capital_share_pct',
            'trend_slope', 'recommendation'
        ])

        for sku in skus:
            writer.writerow([
                sku['sku_key'],
                sku['current_status'],
                sku['recommended_status'],
                sku['roic_pct'],
                sku['capital_deployed_kzt'],
                sku['capital_share_pct'],
                sku['trend_slope'],
                sku['recommendation']
            ])


def generate_json_report(skus: list[dict], portfolio: dict, output_path: Path) -> None:
    """
    Generate JSON portfolio review report.

    Args:
        skus: List of SKU detail dicts
        portfolio: Portfolio-level metrics
        output_path: Path to write JSON
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)

    report = {
        'report_date': date.today().isoformat(),
        'portfolio': {
            'total_capital': portfolio['total_capital_deployed'],
            'weighted_roic_pct': portfolio['weighted_roic_pct'],
            'capital_at_risk': portfolio['capital_at_risk'],
            'total_skus': portfolio['total_skus']
        },
        'skus': skus
    }

    with open(output_path, 'w') as f:
        json.dump(report, f, indent=2)


def send_portfolio_alert(
    portfolio: dict,
    lifecycle_dist: dict,
    kill_candidates: list[dict]
) -> bool:
    """
    Send Telegram portfolio review alert.

    Args:
        portfolio: Portfolio metrics dict
        lifecycle_dist: Lifecycle distribution
        kill_candidates: List of kill candidates

    Returns:
        True if sent successfully
    """
    try:
        from core.alerts.telegram import send_message

        message = (
            f"<b>Weekly Portfolio Review</b>\n\n"
            f"Total Capital: {portfolio['total_capital_deployed']:,.0f} KZT\n"
            f"Weighted ROIC: {portfolio['weighted_roic_pct']:.1f}%\n"
            f"Capital at Risk: {portfolio['capital_at_risk']:,.0f} KZT\n\n"
            f"<b>Lifecycle Distribution:</b>\n"
            f"• GROW: {lifecycle_dist.get('GROW', 0)}\n"
            f"• MAINTAIN: {lifecycle_dist.get('MAINTAIN', 0)}\n"
            f"• HARVEST: {lifecycle_dist.get('HARVEST', 0)}\n"
            f"• KILL: {lifecycle_dist.get('KILL', 0)}\n"
        )

        if kill_candidates:
            message += f"\n<b>Kill Candidates:</b>\n"
            for kc in kill_candidates[:3]:
                message += (
                    f"• {kc['sku_key']}: ROIC={kc['roic']}%, "
                    f"{kc['current_stock']} units\n"
                )

        send_message(message)
        return True

    except Exception as e:
        print(f"Failed to send alert: {e}")
        return False


def main():
    parser = argparse.ArgumentParser(description='Run portfolio review')
    parser.add_argument(
        '--output-format',
        choices=['csv', 'json'],
        default='csv',
        help='Output format (default: csv)'
    )
    parser.add_argument(
        '--update-status',
        action='store_true',
        help='Update lifecycle statuses based on recommendations'
    )
    parser.add_argument(
        '--send-alert',
        action='store_true',
        help='Send Telegram alert'
    )
    parser.add_argument(
        '--db',
        default='db/app.db',
        help='Path to database (default: db/app.db)'
    )
    args = parser.parse_args()

    # Resolve database path
    db_path = Path(args.db)
    if not db_path.is_absolute():
        db_path = project_root / db_path

    if not db_path.exists():
        print(f"ERROR: Database not found at {db_path}")
        return 1

    print(f"=== Portfolio Review ===")
    print(f"Database: {db_path}")
    print()

    # Get portfolio metrics
    portfolio = calc_portfolio_roic(str(db_path))
    lifecycle_dist = get_lifecycle_distribution(str(db_path))
    kill_candidates = identify_kill_candidates(str(db_path))
    sku_details = get_sku_details(str(db_path))

    # Print summary
    print(f"Total Capital Deployed: {portfolio['total_capital_deployed']:,.0f} KZT")
    print(f"Weighted ROIC: {portfolio['weighted_roic_pct']:.1f}%")
    print(f"Capital at Risk: {portfolio['capital_at_risk']:,.0f} KZT")
    print(f"Total SKUs: {portfolio['total_skus']}")
    print()

    print(f"Lifecycle Distribution:")
    for status in ['GROW', 'MAINTAIN', 'HARVEST', 'KILL']:
        print(f"  {status}: {lifecycle_dist.get(status, 0)}")
    print()

    # Generate report
    report_date = date.today().isoformat()
    if args.output_format == 'json':
        report_path = project_root / 'reports' / f'portfolio_review_{report_date}.json'
        generate_json_report(sku_details, portfolio, report_path)
    else:
        report_path = project_root / 'reports' / f'portfolio_review_{report_date}.csv'
        generate_csv_report(sku_details, report_path)

    print(f"Report saved: {report_path}")

    # Show kill candidates
    if kill_candidates:
        print(f"\nKill Candidates ({len(kill_candidates)}):")
        for kc in kill_candidates[:5]:
            print(f"  {kc['sku_key']}: ROIC={kc['roic']}%, "
                  f"DOI={kc['days_of_inventory']} days, {kc['recommendation']}")

    # Show SKUs needing status update
    needs_update = [s for s in sku_details if s['needs_update']]
    if needs_update:
        print(f"\nSKUs with recommended status change ({len(needs_update)}):")
        for sku in needs_update[:5]:
            print(f"  {sku['sku_key']}: {sku['current_status']} -> {sku['recommended_status']}")

        if args.update_status:
            print(f"\nUpdating lifecycle statuses...")
            for sku in needs_update:
                success = update_lifecycle_status(
                    str(db_path),
                    sku['sku_key'],
                    sku['recommended_status'],
                    f"Auto-updated: ROIC={sku['roic_pct']}%, trend={sku['trend_slope']}"
                )
                if success:
                    print(f"  Updated {sku['sku_key']} to {sku['recommended_status']}")

    # Send alert
    if args.send_alert:
        if send_portfolio_alert(portfolio, lifecycle_dist, kill_candidates):
            print(f"\nTelegram alert sent")

    print(f"\nPortfolio review complete.")
    return 0


if __name__ == '__main__':
    exit(main())
