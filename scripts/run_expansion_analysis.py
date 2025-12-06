#!/usr/bin/env python3
"""
Run expansion analysis to score Kaspi SKUs for WB potential.

Usage:
    python scripts/run_expansion_analysis.py
    python scripts/run_expansion_analysis.py --min-units 10
    python scripts/run_expansion_analysis.py --export
"""
import argparse
import csv
import logging
import sys
from pathlib import Path
from datetime import date

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from core.calc.expansion_scorer import (  # noqa: E402
    score_all_skus,
    save_expansion_scores,
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


def run_analysis(min_units: int = 5, save: bool = True) -> list:
    """
    Run expansion analysis for all eligible SKUs.

    Args:
        min_units: Minimum 30-day units to consider
        save: Whether to save scores to database

    Returns:
        List of ExpansionScore objects
    """
    logger.info(f"Scoring SKUs with ≥{min_units} units/30d for WB expansion...")

    scores = score_all_skus(DB_PATH, min_units_30d=min_units)

    logger.info(f"Scored {len(scores)} SKUs")

    if save and scores:
        saved = save_expansion_scores(DB_PATH, scores)
        logger.info(f"Saved {saved} scores to fact_expansion_scores")

    return scores


def export_to_csv(scores: list, output_path: Path) -> None:
    """Export scores to CSV file."""
    if not scores:
        logger.warning("No scores to export")
        return

    output_path.parent.mkdir(parents=True, exist_ok=True)

    with open(output_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)

        # Header
        writer.writerow([
            "sku_key",
            "source_d30",
            "source_margin_pct",
            "source_roic_pct",
            "target_price_rub",
            "target_margin_pct",
            "demand_score",
            "margin_score",
            "competition_score",
            "expansion_score",
            "recommendation",
            "confidence",
            "notes",
        ])

        # Data
        for s in scores:
            writer.writerow([
                s.sku_key,
                s.source_d30,
                round(s.source_margin_pct, 1),
                round(s.source_roic_pct, 1),
                s.target_price_rub,
                round(s.target_est_margin_pct, 1),
                round(s.demand_score, 1),
                round(s.margin_score, 1),
                round(s.competition_score, 1),
                round(s.expansion_score, 1),
                s.recommendation,
                s.confidence,
                s.notes,
            ])

    logger.info(f"Exported {len(scores)} scores to {output_path}")


def print_summary(scores: list) -> None:
    """Print analysis summary to console."""
    if not scores:
        print("\nNo SKUs scored.")
        return

    # Group by recommendation
    by_rec = {}
    for s in scores:
        by_rec.setdefault(s.recommendation, []).append(s)

    print("\n" + "=" * 70)
    print("EXPANSION ANALYSIS SUMMARY")
    print("=" * 70)

    for rec in ["EXPAND", "TEST", "HOLD", "SKIP"]:
        if rec in by_rec:
            skus = by_rec[rec]
            print(f"\n{rec}: {len(skus)} SKUs")
            print("-" * 50)

            # Show top 5 per category
            for s in skus[:5]:
                print(
                    f"  {s.sku_key:30} "
                    f"Score: {s.expansion_score:5.1f}  "
                    f"Margin: {s.target_est_margin_pct:5.1f}%  "
                    f"D30: {s.source_d30:4.0f}"
                )

            if len(skus) > 5:
                print(f"  ... and {len(skus) - 5} more")

    # Top recommendations
    expand_skus = by_rec.get("EXPAND", [])
    test_skus = by_rec.get("TEST", [])

    if expand_skus or test_skus:
        print("\n" + "=" * 70)
        print("TOP RECOMMENDATIONS")
        print("=" * 70)

        top_candidates = (expand_skus + test_skus)[:10]
        for i, s in enumerate(top_candidates, 1):
            print(
                f"\n{i}. {s.sku_key}"
                f"\n   Recommendation: {s.recommendation} ({s.confidence} confidence)"
                f"\n   Kaspi: D30={s.source_d30:.0f}, Margin={s.source_margin_pct:.1f}%"
                f"\n   WB:    Price={s.target_price_rub:.0f}₽, Est.Margin={s.target_est_margin_pct:.1f}%"
                f"\n   Score: {s.expansion_score:.1f} (demand={s.demand_score:.0f}, margin={s.margin_score:.0f})"
                f"\n   Notes: {s.notes}"
            )


def main():
    parser = argparse.ArgumentParser(
        description="Run WB expansion analysis",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    # Run analysis for all eligible SKUs
    python scripts/run_expansion_analysis.py

    # Require at least 10 units/30d
    python scripts/run_expansion_analysis.py --min-units 10

    # Export results to CSV
    python scripts/run_expansion_analysis.py --export

    # Don't save to database (dry run)
    python scripts/run_expansion_analysis.py --no-save
        """,
    )
    parser.add_argument(
        "--min-units",
        type=int,
        default=5,
        help="Minimum 30-day units to consider (default: 5)",
    )
    parser.add_argument(
        "--export",
        action="store_true",
        help="Export results to CSV",
    )
    parser.add_argument(
        "--no-save",
        action="store_true",
        help="Don't save scores to database",
    )

    args = parser.parse_args()

    print()
    print("=" * 70)
    print("WB EXPANSION ANALYSIS")
    print("=" * 70)
    print(f"Date:      {date.today()}")
    print(f"Min units: {args.min_units}")

    # Run analysis
    scores = run_analysis(
        min_units=args.min_units,
        save=not args.no_save,
    )

    # Print summary
    print_summary(scores)

    # Export if requested
    if args.export:
        today = date.today().isoformat()
        output_path = REPORTS_DIR / f"expansion_scores_{today}.csv"
        export_to_csv(scores, output_path)

    print()


if __name__ == "__main__":
    main()
