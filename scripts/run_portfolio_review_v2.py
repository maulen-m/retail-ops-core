#!/usr/bin/env python3
"""
Weekly portfolio review.
Analyzes capital allocation and generates recommendations.

Run: python scripts/run_portfolio_review_v2.py [--telegram]

TASK-078
"""
import sqlite3
import argparse
from pathlib import Path
from datetime import date
import json
import sys

sys.path.insert(0, str(Path(__file__).parent.parent))

from core.calc.capital_optimizer import (
    get_current_allocations,
    optimize_allocation,
    calc_portfolio_impact
)
from core.calc.lifecycle_classifier import update_lifecycle_statuses

DB_PATH = Path(__file__).parent.parent / "db" / "app.db"
REPORT_PATH = Path(__file__).parent.parent / "reports"


def run_portfolio_review(send_telegram: bool = False):
    print("=" * 60)
    print(f"WEEKLY PORTFOLIO REVIEW — {date.today()}")
    print("=" * 60)

    # Update lifecycle statuses first
    print("\n1. Updating lifecycle classifications...")
    update_lifecycle_statuses(DB_PATH)

    # Get current allocations
    print("\n2. Loading current allocations...")
    allocations = get_current_allocations(DB_PATH)

    if not allocations:
        print("No allocation data found. Run build_capital_snapshot.py first.")
        return

    print(f"   Found {len(allocations)} SKUs")

    # Run optimization
    print("\n3. Running optimization...")
    optimized = optimize_allocation(
        allocations,
        max_concentration=0.20,
        min_roic_threshold=10.0,
        kill_roic_threshold=5.0
    )

    # Calculate impact
    impact = calc_portfolio_impact(allocations, optimized)

    print(f"\n=== OPTIMIZATION RESULTS ===")
    print(f"Current Portfolio ROIC:    {impact['current_portfolio_roic']:.1f}%")
    print(f"Projected Portfolio ROIC:  {impact['projected_portfolio_roic']:.1f}%")
    print(f"Expected ROIC Lift:        {impact['roic_lift']:.1f}%")
    print(f"Capital to Reallocate:     {impact['capital_reallocated']:,.0f} KZT")
    print(f"SKUs to Increase:          {impact['skus_increased']}")
    print(f"SKUs to Decrease:          {impact['skus_decreased']}")
    print(f"SKUs to Kill:              {impact['skus_killed']}")

    # Generate detailed report
    REPORT_PATH.mkdir(exist_ok=True)
    report_file = REPORT_PATH / f"portfolio_review_{date.today()}.json"

    report = {
        'review_date': date.today().isoformat(),
        'summary': impact,
        'recommendations': [
            {
                'sku_key': o.sku_key,
                'action': o.action,
                'current_capital': o.current_capital,
                'recommended_capital': o.recommended_capital,
                'delta': o.delta_capital,
                'roic_pct': o.roic_pct
            }
            for o in optimized
            if o.action != 'HOLD'
        ]
    }

    with open(report_file, 'w') as f:
        json.dump(report, f, indent=2)

    print(f"\n✓ Report saved: {report_file}")

    # Show top actions
    print("\n=== TOP RECOMMENDATIONS ===")
    print("\n📈 INCREASE (Top 5):")
    increase = sorted([o for o in optimized if o.action == 'INCREASE'],
                      key=lambda x: x.delta_capital, reverse=True)[:5]
    for o in increase:
        print(f"   {o.sku_key}: +{o.delta_capital:,.0f} KZT (ROIC: {o.roic_pct:.1f}%)")

    print("\n📉 DECREASE/KILL:")
    decrease = [o for o in optimized if o.action in ('DECREASE', 'KILL')]
    for o in decrease[:5]:
        print(f"   {o.sku_key}: {o.delta_capital:,.0f} KZT ({o.action}, ROIC: {o.roic_pct:.1f}%)")

    # Send Telegram summary
    if send_telegram:
        try:
            from core.alerts.telegram import send_message

            msg = f"""📊 Weekly Portfolio Review — {date.today()}

Current ROIC: {impact['current_portfolio_roic']:.1f}%
Projected ROIC: {impact['projected_portfolio_roic']:.1f}%
Expected Lift: +{impact['roic_lift']:.1f}%

Actions:
• {impact['skus_increased']} SKUs to increase
• {impact['skus_decreased']} SKUs to decrease
• {impact['skus_killed']} SKUs to kill

Top increase: {increase[0].sku_key if increase else 'None'} (+{increase[0].delta_capital:,.0f} KZT)
"""
            send_message(msg)
            print("\n✓ Telegram summary sent")
        except Exception as e:
            print(f"\n⚠ Telegram failed: {e}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--telegram', action='store_true', help='Send Telegram summary')
    args = parser.parse_args()

    run_portfolio_review(send_telegram=args.telegram)


if __name__ == "__main__":
    main()
