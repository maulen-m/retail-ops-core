#!/usr/bin/env python3
"""
Run transfer analysis to balance inventory between channels.

Usage:
    python scripts/run_transfer_analysis.py
    python scripts/run_transfer_analysis.py --critical-only
    python scripts/run_transfer_analysis.py --alert
"""
import argparse
import csv
import logging
import sys
from pathlib import Path
from datetime import date

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from core.calc.transfer_recommender import (  # noqa: E402
    recommend_transfers,
    get_critical_imbalances,
    get_transfer_summary,
)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

DB_PATH = Path(__file__).parent.parent / "db" / "app.db"
REPORTS_DIR = Path(__file__).parent.parent / "reports"


def run_analysis(critical_only: bool = False) -> list:
    """
    Run transfer analysis.

    Args:
        critical_only: If True, only return critical/high urgency

    Returns:
        List of TransferRecommendation objects
    """
    logger.info("Analyzing inventory imbalances between channels...")

    if critical_only:
        recommendations = get_critical_imbalances(DB_PATH)
        logger.info(f"Found {len(recommendations)} critical/high urgency transfers")
    else:
        recommendations = recommend_transfers(DB_PATH)
        logger.info(f"Found {len(recommendations)} transfer recommendations")

    return recommendations


def send_telegram_alert(recommendations: list) -> bool:
    """Send Telegram alert for critical transfers."""
    try:
        from core.alerts.telegram import send_message
    except ImportError:
        logger.warning("Telegram alerts not configured")
        return False

    critical = [r for r in recommendations if r.urgency == "CRITICAL"]
    high = [r for r in recommendations if r.urgency == "HIGH"]

    if not critical and not high:
        logger.info("No critical/high transfers to alert")
        return False

    # Build message
    lines = ["🔄 *TRANSFER RECOMMENDATIONS*\n"]

    if critical:
        lines.append(f"🚨 *CRITICAL ({len(critical)}):*")
        for r in critical[:5]:
            lines.append(
                f"  • {r.sku_key}: {r.units_to_transfer} units "
                f"{r.from_channel}→{r.to_channel}"
            )

    if high:
        lines.append(f"\n⚠️ *HIGH ({len(high)}):*")
        for r in high[:5]:
            lines.append(
                f"  • {r.sku_key}: {r.units_to_transfer} units "
                f"{r.from_channel}→{r.to_channel}"
            )

    summary = get_transfer_summary(critical + high)
    lines.append(f"\n📊 Total units: {summary['total_units']}")
    lines.append(f"💰 Revenue at risk: {summary['total_revenue_protected']:,.0f} KZT")

    message = "\n".join(lines)

    try:
        send_message(message)
        logger.info("Telegram alert sent")
        return True
    except Exception as e:
        logger.error(f"Failed to send Telegram alert: {e}")
        return False


def export_to_csv(recommendations: list, output_path: Path) -> None:
    """Export recommendations to CSV file."""
    if not recommendations:
        logger.warning("No recommendations to export")
        return

    output_path.parent.mkdir(parents=True, exist_ok=True)

    with open(output_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)

        # Header
        writer.writerow([
            "sku_key",
            "from_channel",
            "to_channel",
            "units_to_transfer",
            "urgency",
            "confidence",
            "from_on_hand",
            "from_days_cover",
            "to_on_hand",
            "to_days_cover",
            "revenue_protected_kzt",
            "reason",
        ])

        # Data
        for r in recommendations:
            writer.writerow([
                r.sku_key,
                r.from_channel,
                r.to_channel,
                r.units_to_transfer,
                r.urgency,
                r.confidence,
                r.from_on_hand,
                round(r.from_days_of_cover, 1),
                r.to_on_hand,
                round(r.to_days_of_cover, 1),
                round(r.estimated_revenue_protected_kzt, 0),
                r.reason,
            ])

    logger.info(f"Exported {len(recommendations)} recommendations to {output_path}")


def print_summary(recommendations: list) -> None:
    """Print analysis summary to console."""
    summary = get_transfer_summary(recommendations)

    print("\n" + "=" * 70)
    print("TRANSFER ANALYSIS SUMMARY")
    print("=" * 70)

    if not recommendations:
        print("\nNo transfer recommendations at this time.")
        print("All channels have balanced inventory levels.")
        return

    print(f"\nTotal recommendations: {summary['total_recommendations']}")
    print(f"SKUs affected: {summary['skus_affected']}")
    print(f"Total units to transfer: {summary['total_units']}")
    print(f"Revenue protected: {summary['total_revenue_protected']:,.0f} KZT")

    print("\nBy urgency:")
    for urgency in ["CRITICAL", "HIGH", "MEDIUM", "LOW"]:
        count = summary["by_urgency"].get(urgency, 0)
        if count > 0:
            icon = {"CRITICAL": "🚨", "HIGH": "⚠️", "MEDIUM": "📋", "LOW": "📝"}.get(urgency, "")
            print(f"  {icon} {urgency}: {count}")

    # Print detailed recommendations by urgency
    for urgency in ["CRITICAL", "HIGH", "MEDIUM"]:
        urgency_recs = [r for r in recommendations if r.urgency == urgency]
        if urgency_recs:
            print(f"\n{urgency} TRANSFERS:")
            print("-" * 50)
            for r in urgency_recs[:5]:
                print(
                    f"  {r.sku_key}:"
                    f"\n    Transfer {r.units_to_transfer} units: {r.from_channel} → {r.to_channel}"
                    f"\n    {r.from_channel}: {r.from_on_hand} units ({r.from_days_of_cover:.0f} days)"
                    f"\n    {r.to_channel}: {r.to_on_hand} units ({r.to_days_of_cover:.0f} days)"
                    f"\n    Revenue protected: {r.estimated_revenue_protected_kzt:,.0f} KZT"
                )
            if len(urgency_recs) > 5:
                print(f"  ... and {len(urgency_recs) - 5} more")


def main():
    parser = argparse.ArgumentParser(
        description="Run inventory transfer analysis",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    # Run full analysis
    python scripts/run_transfer_analysis.py

    # Only critical/high urgency
    python scripts/run_transfer_analysis.py --critical-only

    # Send Telegram alert for critical transfers
    python scripts/run_transfer_analysis.py --alert

    # Export to CSV
    python scripts/run_transfer_analysis.py --export
        """,
    )
    parser.add_argument(
        "--critical-only",
        action="store_true",
        help="Only show critical/high urgency transfers",
    )
    parser.add_argument(
        "--alert",
        action="store_true",
        help="Send Telegram alert for critical transfers",
    )
    parser.add_argument(
        "--export",
        action="store_true",
        help="Export results to CSV",
    )

    args = parser.parse_args()

    print()
    print("=" * 70)
    print("INVENTORY TRANSFER ANALYSIS")
    print("=" * 70)
    print(f"Date: {date.today()}")

    # Run analysis
    recommendations = run_analysis(critical_only=args.critical_only)

    # Print summary
    print_summary(recommendations)

    # Export if requested
    if args.export:
        today = date.today().isoformat()
        output_path = REPORTS_DIR / f"transfer_recommendations_{today}.csv"
        export_to_csv(recommendations, output_path)

    # Send alert if requested
    if args.alert:
        send_telegram_alert(recommendations)

    print()


if __name__ == "__main__":
    main()
