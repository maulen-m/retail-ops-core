#!/usr/bin/env python3
"""
Download Waybills CLI (Phase 9.5 - TASK-125).

Downloads waybill PDFs from Kaspi API for orders ready for shipment.

Usage:
    # Download all pending waybills
    python scripts/download_waybills.py

    # Download for specific store
    python scripts/download_waybills.py --store UNIVERSAL

    # Limit number of downloads
    python scripts/download_waybills.py --limit 20

    # Show download statistics
    python scripts/download_waybills.py --stats

    # Clean old waybills (older than 30 days)
    python scripts/download_waybills.py --clean --days 30

Environment Variables:
    KASPI_TOKEN_UNIVERSAL, KASPI_TOKEN_ACMEWEAR, etc.
"""

import argparse
import logging
import sys
from datetime import datetime
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
load_dotenv()

from core.waybill.waybill_downloader import WaybillDownloader, BatchDownloadResult


def setup_logging(verbose: bool = False):
    """Configure logging."""
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format='%(asctime)s | %(levelname)s | %(message)s',
        datefmt='%H:%M:%S',
    )


def print_stats(downloader: WaybillDownloader):
    """Print download statistics."""
    stats = downloader.get_download_stats()

    print(f"\n{'=' * 60}")
    print("WAYBILL DOWNLOAD STATISTICS")
    print(f"{'=' * 60}")

    print(f"\nTotal orders with waybills: {stats['total']}")
    print(f"Downloaded: {stats['downloaded']}")
    print(f"Pending: {stats['pending']}")
    print(f"Files on disk: {stats['files_on_disk']}")
    print(f"Output directory: {stats['output_dir']}")

    if stats['by_store']:
        print("\nBy Store:")
        for store, counts in stats['by_store'].items():
            print(
                f"  {store}: "
                f"downloaded={counts['downloaded']}, "
                f"pending={counts['pending']}"
            )

    # List pending
    pending = downloader.get_pending_orders()
    if pending:
        print(f"\nPending Downloads ({len(pending)}):")
        for order in pending[:10]:
            print(f"  {order['order_id']} | {order['store_code']} | {order.get('planned_shipment_date', 'N/A')}")
        if len(pending) > 10:
            print(f"  ... and {len(pending) - 10} more")
    else:
        print("\nNo pending downloads")


def print_result(result: BatchDownloadResult):
    """Print download result."""
    print(f"\n{'=' * 60}")
    print("DOWNLOAD RESULT")
    print(f"{'=' * 60}")

    print(f"\nTotal orders: {result.total_orders}")
    print(f"Downloaded: {result.downloaded}")
    print(f"Skipped (already exists): {result.skipped}")
    print(f"Failed: {result.failed}")
    print(f"Duration: {result.duration_sec:.1f}s")

    if result.errors:
        print(f"\nErrors ({len(result.errors)}):")
        for error in result.errors[:10]:
            print(f"  - {error}")
        if len(result.errors) > 10:
            print(f"  ... and {len(result.errors) - 10} more")

    # Summary of successful downloads
    successful = [r for r in result.results if r.success and r.filepath]
    if successful:
        total_size = sum(r.file_size for r in successful)
        print(f"\nDownloaded {len(successful)} files ({total_size / 1024:.1f} KB)")


def main():
    parser = argparse.ArgumentParser(
        description="Download Kaspi waybill PDFs",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    # Mode
    mode_group = parser.add_mutually_exclusive_group()
    mode_group.add_argument(
        '--stats',
        action='store_true',
        help='Show download statistics only',
    )
    mode_group.add_argument(
        '--clean',
        action='store_true',
        help='Clean old waybill files',
    )

    # Filters
    parser.add_argument(
        '--store',
        type=str,
        help='Download for specific store only',
    )
    parser.add_argument(
        '--limit',
        type=int,
        help='Maximum number of waybills to download',
    )

    # Clean options
    parser.add_argument(
        '--days',
        type=int,
        default=30,
        help='Delete waybills older than N days (default: 30)',
    )

    # Options
    parser.add_argument(
        '--output-dir',
        type=str,
        help='Output directory for waybills',
    )
    parser.add_argument(
        '--force',
        action='store_true',
        help='Re-download even if already downloaded',
    )
    parser.add_argument(
        '-v', '--verbose',
        action='store_true',
        help='Enable verbose logging',
    )

    args = parser.parse_args()

    setup_logging(args.verbose)

    # Initialize downloader
    output_dir = Path(args.output_dir) if args.output_dir else None
    downloader = WaybillDownloader(output_dir=output_dir)

    print(f"\n{'=' * 60}")
    print("KASPI WAYBILL DOWNLOADER")
    print(f"{'=' * 60}")
    print(f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"Output: {downloader.output_dir}")

    if args.stats:
        print_stats(downloader)
        return 0

    if args.clean:
        print(f"\nCleaning waybills older than {args.days} days...")
        deleted = downloader.clean_old_waybills(days=args.days)
        print(f"Deleted {deleted} old waybill files")
        return 0

    # Download waybills
    store_code = args.store.upper() if args.store else None
    print(f"\nStore: {store_code or 'ALL'}")
    print(f"Limit: {args.limit or 'None'}")
    print(f"Skip downloaded: {not args.force}")

    result = downloader.download_pending(
        store_code=store_code,
        limit=args.limit,
        skip_downloaded=not args.force,
    )

    print_result(result)

    # Show updated stats
    print_stats(downloader)

    return 0 if result.failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
