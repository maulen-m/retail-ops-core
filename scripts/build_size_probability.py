#!/usr/bin/env python3
"""
Build Size Probability Table CLI (Phase 9.5 - TASK-137).

Rebuilds dim_size_probability from fact_sales history.

Usage:
    # Build probabilities with defaults
    python scripts/build_size_probability.py

    # Build with custom thresholds
    python scripts/build_size_probability.py --min-samples 10

    # Rebuild all (clear existing first)
    python scripts/build_size_probability.py --rebuild

    # Export to CSV
    python scripts/build_size_probability.py --export

    # Show statistics only
    python scripts/build_size_probability.py --stats
"""

import argparse
import csv
import logging
import sys
from datetime import datetime
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from core.db import get_db
from core.calc.size_probability import (
    calc_offer_size_mode,
    calc_style_size_mode,
    save_size_probability,
    get_coverage_stats,
    OFFER_MIN_SAMPLES,
    STYLE_MIN_SAMPLES,
)


DB_PATH = Path(__file__).parent.parent / "db" / "app.db"
EXPORT_DIR = Path(__file__).parent.parent / "exports"


def setup_logging(verbose: bool = False):
    """Configure logging."""
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format='%(asctime)s | %(levelname)s | %(message)s',
        datefmt='%H:%M:%S',
    )


def get_unique_offers() -> list[str]:
    """Get unique kaspi_offer_names from fact_sales."""
    with get_db(DB_PATH) as conn:
        rows = conn.execute(
            """
            SELECT DISTINCT kaspi_offer_name
            FROM fact_sales
            WHERE kaspi_offer_name IS NOT NULL
              AND kaspi_offer_name != ''
            ORDER BY kaspi_offer_name
            """
        ).fetchall()
        return [row[0] for row in rows]


def get_unique_styles() -> list[str]:
    """Get unique sku_keys from fact_sales."""
    with get_db(DB_PATH) as conn:
        rows = conn.execute(
            """
            SELECT DISTINCT sku_key
            FROM fact_sales
            WHERE sku_key IS NOT NULL
              AND sku_key != ''
            ORDER BY sku_key
            """
        ).fetchall()
        return [row[0] for row in rows]


def clear_probabilities(level: str = None):
    """Clear existing probabilities."""
    with get_db(DB_PATH) as conn:
        if level:
            conn.execute(
                "DELETE FROM dim_size_probability WHERE level = ?",
                (level,)
            )
        else:
            # Keep PRODUCT_TYPE defaults
            conn.execute(
                "DELETE FROM dim_size_probability WHERE level != 'PRODUCT_TYPE'"
            )


def build_offer_probabilities(
    min_samples: int = OFFER_MIN_SAMPLES,
    verbose: bool = False,
) -> dict:
    """Build offer-level probabilities."""
    offers = get_unique_offers()
    logging.info(f"Processing {len(offers)} unique offers...")

    stats = {'processed': 0, 'saved': 0, 'skipped': 0}

    for i, offer_name in enumerate(offers):
        if verbose and i % 50 == 0:
            logging.info(f"  Progress: {i}/{len(offers)}")

        prob = calc_offer_size_mode(offer_name)
        stats['processed'] += 1

        if prob and prob.sample_count >= min_samples:
            save_size_probability('OFFER', offer_name, prob)
            stats['saved'] += 1
        else:
            stats['skipped'] += 1

    return stats


def build_style_probabilities(
    min_samples: int = STYLE_MIN_SAMPLES,
    verbose: bool = False,
) -> dict:
    """Build style-level probabilities."""
    styles = get_unique_styles()
    logging.info(f"Processing {len(styles)} unique styles...")

    stats = {'processed': 0, 'saved': 0, 'skipped': 0}

    for i, sku_key in enumerate(styles):
        if verbose and i % 20 == 0:
            logging.info(f"  Progress: {i}/{len(styles)}")

        prob = calc_style_size_mode(sku_key)
        stats['processed'] += 1

        if prob and prob.sample_count >= min_samples:
            save_size_probability('STYLE', sku_key, prob)
            stats['saved'] += 1
        else:
            stats['skipped'] += 1

    return stats


def export_probabilities(output_path: Path = None) -> Path:
    """Export dim_size_probability to CSV."""
    if output_path is None:
        date_str = datetime.now().strftime('%Y-%m-%d')
        EXPORT_DIR.mkdir(parents=True, exist_ok=True)
        output_path = EXPORT_DIR / f"size_probability_{date_str}.csv"

    with get_db(DB_PATH) as conn:
        rows = conn.execute(
            """
            SELECT level, key_value, mode_size, mode_share, sample_count,
                   confidence, size_distribution, updated_at
            FROM dim_size_probability
            ORDER BY level, sample_count DESC
            """
        ).fetchall()

    with open(output_path, 'w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerow([
            'level', 'key_value', 'mode_size', 'mode_share',
            'sample_count', 'confidence', 'size_distribution', 'updated_at'
        ])
        for row in rows:
            writer.writerow(row)

    return output_path


def print_stats():
    """Print coverage statistics."""
    stats = get_coverage_stats()

    print(f"\n{'=' * 60}")
    print("SIZE PROBABILITY STATISTICS")
    print(f"{'=' * 60}")

    print(f"\nBy Level:")
    for level, count in stats['by_level'].items():
        print(f"  {level}: {count}")

    print(f"\nOffer Coverage:")
    print(f"  Total offers in sales: {stats['total_offers']}")
    print(f"  Covered offers: {stats['covered_offers']}")
    print(f"  Coverage: {stats['offer_coverage']:.1%}")

    print(f"\nStyle Coverage:")
    print(f"  Total styles in sales: {stats['total_styles']}")
    print(f"  Covered styles: {stats['covered_styles']}")
    print(f"  Coverage: {stats['style_coverage']:.1%}")

    # Show sample probabilities
    with get_db(DB_PATH) as conn:
        print("\nTop 10 High-Confidence Offers:")
        rows = conn.execute(
            """
            SELECT key_value, mode_size, mode_share, sample_count
            FROM dim_size_probability
            WHERE level = 'OFFER' AND confidence = 'HIGH'
            ORDER BY sample_count DESC
            LIMIT 10
            """
        ).fetchall()
        for row in rows:
            name = row[0][:40] + '...' if len(row[0]) > 40 else row[0]
            print(f"  {name}: {row[1]} ({row[2]:.0%}, n={row[3]})")


def main():
    parser = argparse.ArgumentParser(
        description="Build size probability table from sales history",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    # Mode
    parser.add_argument(
        '--stats',
        action='store_true',
        help='Show statistics only, do not build',
    )
    parser.add_argument(
        '--export',
        action='store_true',
        help='Export to CSV after building',
    )

    # Options
    parser.add_argument(
        '--rebuild',
        action='store_true',
        help='Clear existing and rebuild all',
    )
    parser.add_argument(
        '--min-samples',
        type=int,
        default=OFFER_MIN_SAMPLES,
        help=f'Minimum samples required (default: {OFFER_MIN_SAMPLES})',
    )
    parser.add_argument(
        '--offers-only',
        action='store_true',
        help='Only build offer-level probabilities',
    )
    parser.add_argument(
        '--styles-only',
        action='store_true',
        help='Only build style-level probabilities',
    )
    parser.add_argument(
        '-v', '--verbose',
        action='store_true',
        help='Verbose output',
    )

    args = parser.parse_args()

    setup_logging(args.verbose)

    print(f"\n{'=' * 60}")
    print("SIZE PROBABILITY BUILDER")
    print(f"{'=' * 60}")
    print(f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"Min samples: {args.min_samples}")

    if args.stats:
        print_stats()
        return 0

    # Build probabilities
    start_time = datetime.now()

    if args.rebuild:
        logging.info("Clearing existing probabilities...")
        clear_probabilities()

    if not args.styles_only:
        logging.info("\nBuilding OFFER-level probabilities...")
        offer_stats = build_offer_probabilities(
            min_samples=args.min_samples,
            verbose=args.verbose,
        )
        print(f"\nOffer Stats:")
        print(f"  Processed: {offer_stats['processed']}")
        print(f"  Saved: {offer_stats['saved']}")
        print(f"  Skipped: {offer_stats['skipped']}")

    if not args.offers_only:
        logging.info("\nBuilding STYLE-level probabilities...")
        style_stats = build_style_probabilities(
            min_samples=args.min_samples,
            verbose=args.verbose,
        )
        print(f"\nStyle Stats:")
        print(f"  Processed: {style_stats['processed']}")
        print(f"  Saved: {style_stats['saved']}")
        print(f"  Skipped: {style_stats['skipped']}")

    duration = (datetime.now() - start_time).total_seconds()
    logging.info(f"\nBuild complete in {duration:.1f}s")

    # Show final stats
    print_stats()

    # Export if requested
    if args.export:
        output_path = export_probabilities()
        print(f"\nExported to: {output_path}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
