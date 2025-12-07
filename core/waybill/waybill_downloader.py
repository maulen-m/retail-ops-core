"""
Waybill Downloader for Kaspi API (Phase 9.5 - TASK-124).

Downloads waybill PDFs from Kaspi API for orders ready for shipment.

Features:
- Batch download with rate limiting
- Progress tracking
- Resume capability (skips already downloaded)
- Database status updates

Usage:
    from core.waybill.waybill_downloader import WaybillDownloader

    downloader = WaybillDownloader(output_dir=Path("exports/waybills"))
    result = downloader.download_pending(store_code='UNIVERSAL')
"""

import logging
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional

from core.db import get_db
from core.integrations.kaspi_api_client import KaspiAPIClient, get_client


logger = logging.getLogger(__name__)


# =============================================================================
# CONSTANTS
# =============================================================================

DEFAULT_OUTPUT_DIR = Path(__file__).parent.parent.parent / "exports" / "waybills"
DB_PATH = Path(__file__).parent.parent.parent / "db" / "app.db"

# Rate limiting
MIN_DOWNLOAD_INTERVAL = 0.1  # 100ms between downloads
MAX_CONCURRENT = 5  # For future async implementation


# =============================================================================
# DATA CLASSES
# =============================================================================

@dataclass
class DownloadResult:
    """Result of a single waybill download."""
    order_id: str
    success: bool
    filepath: Optional[Path] = None
    error: Optional[str] = None
    file_size: int = 0


@dataclass
class BatchDownloadResult:
    """Result of batch waybill download."""
    total_orders: int = 0
    downloaded: int = 0
    skipped: int = 0
    failed: int = 0
    results: list = field(default_factory=list)
    errors: list = field(default_factory=list)
    duration_sec: float = 0.0


# =============================================================================
# WAYBILL DOWNLOADER
# =============================================================================

class WaybillDownloader:
    """
    Downloads waybill PDFs from Kaspi API.

    Args:
        output_dir: Directory to save downloaded PDFs
        db_path: Path to database
        organize_by_date: Create subdirectories by date

    Attributes:
        output_dir: Base output directory
        organize_by_date: Whether to organize by date
    """

    def __init__(
        self,
        output_dir: Path = None,
        db_path: Path = None,
        organize_by_date: bool = True,
    ):
        self.output_dir = output_dir or DEFAULT_OUTPUT_DIR
        self.db_path = db_path or DB_PATH
        self.organize_by_date = organize_by_date
        self._last_download_time = 0.0

        # Ensure output directory exists
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def _get_output_path(self, order_id: str, date_str: Optional[str] = None) -> Path:
        """
        Get output path for waybill PDF.

        Args:
            order_id: Order ID
            date_str: Date for organizing (YYYY-MM-DD)

        Returns:
            Path to save PDF
        """
        filename = f"waybill_{order_id}.pdf"

        if self.organize_by_date:
            date_dir = date_str or datetime.now().strftime('%Y-%m-%d')
            output_path = self.output_dir / date_dir
            output_path.mkdir(parents=True, exist_ok=True)
            return output_path / filename

        return self.output_dir / filename

    def _rate_limit(self):
        """Apply rate limiting between downloads."""
        now = time.time()
        elapsed = now - self._last_download_time
        if elapsed < MIN_DOWNLOAD_INTERVAL:
            time.sleep(MIN_DOWNLOAD_INTERVAL - elapsed)
        self._last_download_time = time.time()

    def download_waybill(
        self,
        client: KaspiAPIClient,
        order_id: str,
        waybill_url: str,
        output_path: Optional[Path] = None,
    ) -> DownloadResult:
        """
        Download single waybill PDF.

        Args:
            client: Kaspi API client
            order_id: Order ID for tracking
            waybill_url: URL to download from
            output_path: Where to save (auto-generated if None)

        Returns:
            DownloadResult with success status and filepath
        """
        self._rate_limit()

        if output_path is None:
            output_path = self._get_output_path(order_id)

        # Skip if already exists
        if output_path.exists():
            logger.debug(f"Waybill already exists: {output_path}")
            return DownloadResult(
                order_id=order_id,
                success=True,
                filepath=output_path,
                file_size=output_path.stat().st_size,
            )

        try:
            response = client.download_waybill(waybill_url)

            if not response.success:
                return DownloadResult(
                    order_id=order_id,
                    success=False,
                    error=response.error,
                )

            # Save PDF
            output_path.parent.mkdir(parents=True, exist_ok=True)
            with open(output_path, 'wb') as f:
                f.write(response.data)

            file_size = len(response.data)
            logger.debug(f"Downloaded waybill: {output_path} ({file_size} bytes)")

            return DownloadResult(
                order_id=order_id,
                success=True,
                filepath=output_path,
                file_size=file_size,
            )

        except Exception as e:
            logger.error(f"Error downloading waybill for {order_id}: {e}")
            return DownloadResult(
                order_id=order_id,
                success=False,
                error=str(e),
            )

    def download_pending(
        self,
        store_code: Optional[str] = None,
        limit: Optional[int] = None,
        skip_downloaded: bool = True,
    ) -> BatchDownloadResult:
        """
        Download waybills for all pending orders.

        Args:
            store_code: Filter by store (None for all)
            limit: Maximum number to download
            skip_downloaded: Skip orders already marked as downloaded

        Returns:
            BatchDownloadResult with counts and individual results
        """
        start_time = datetime.now()
        result = BatchDownloadResult()

        # Get orders with waybill URLs
        with get_db(self.db_path) as conn:
            query = """
                SELECT
                    order_id, store_code, waybill_url, waybill_downloaded,
                    planned_shipment_date
                FROM fact_orders_kaspi
                WHERE waybill_url IS NOT NULL
                  AND waybill_url != ''
            """
            params = []

            if skip_downloaded:
                query += " AND waybill_downloaded = 0"

            if store_code:
                query += " AND store_code = ?"
                params.append(store_code)

            query += " ORDER BY planned_shipment_date ASC"

            if limit:
                query += f" LIMIT {limit}"

            orders = conn.execute(query, params).fetchall()

        result.total_orders = len(orders)
        logger.info(f"Found {len(orders)} orders to download waybills")

        if not orders:
            return result

        # Group orders by store for client reuse
        orders_by_store = {}
        for order in orders:
            store = order['store_code']
            if store not in orders_by_store:
                orders_by_store[store] = []
            orders_by_store[store].append(dict(order))

        # Download by store
        for store, store_orders in orders_by_store.items():
            try:
                client = get_client(store)

                for order in store_orders:
                    order_id = order['order_id']
                    waybill_url = order['waybill_url']
                    planned_date = order.get('planned_shipment_date')

                    # Download
                    output_path = self._get_output_path(order_id, planned_date)
                    download_result = self.download_waybill(
                        client=client,
                        order_id=order_id,
                        waybill_url=waybill_url,
                        output_path=output_path,
                    )

                    result.results.append(download_result)

                    if download_result.success:
                        if download_result.filepath and download_result.filepath.exists():
                            result.downloaded += 1
                            # Update database
                            self._mark_downloaded(order_id, store)
                        else:
                            result.skipped += 1
                    else:
                        result.failed += 1
                        result.errors.append(
                            f"{order_id}: {download_result.error}"
                        )

            except Exception as e:
                logger.error(f"Error processing store {store}: {e}")
                result.errors.append(f"Store {store}: {e}")

        result.duration_sec = (datetime.now() - start_time).total_seconds()

        logger.info(
            f"Batch download complete: "
            f"total={result.total_orders}, "
            f"downloaded={result.downloaded}, "
            f"skipped={result.skipped}, "
            f"failed={result.failed}, "
            f"duration={result.duration_sec:.1f}s"
        )

        return result

    def _mark_downloaded(self, order_id: str, store_code: str):
        """Mark order as having waybill downloaded."""
        with get_db(self.db_path) as conn:
            conn.execute(
                """
                UPDATE fact_orders_kaspi
                SET waybill_downloaded = 1
                WHERE order_id = ? AND store_code = ?
                """,
                (order_id, store_code)
            )

    def get_download_stats(self) -> dict:
        """
        Get waybill download statistics.

        Returns:
            Dict with download counts and status
        """
        with get_db(self.db_path) as conn:
            # Count by download status
            rows = conn.execute(
                """
                SELECT
                    waybill_downloaded,
                    COUNT(*) as cnt
                FROM fact_orders_kaspi
                WHERE waybill_url IS NOT NULL AND waybill_url != ''
                GROUP BY waybill_downloaded
                """
            ).fetchall()

            downloaded = 0
            pending = 0
            for row in rows:
                if row['waybill_downloaded'] == 1:
                    downloaded = row['cnt']
                else:
                    pending = row['cnt']

            # Count by store
            store_counts = {}
            rows = conn.execute(
                """
                SELECT
                    store_code,
                    SUM(CASE WHEN waybill_downloaded = 1 THEN 1 ELSE 0 END) as downloaded,
                    SUM(CASE WHEN waybill_downloaded = 0 THEN 1 ELSE 0 END) as pending
                FROM fact_orders_kaspi
                WHERE waybill_url IS NOT NULL AND waybill_url != ''
                GROUP BY store_code
                """
            ).fetchall()
            for row in rows:
                store_counts[row['store_code']] = {
                    'downloaded': row['downloaded'],
                    'pending': row['pending'],
                }

            # Count files on disk
            files_on_disk = 0
            if self.output_dir.exists():
                files_on_disk = len(list(self.output_dir.rglob('*.pdf')))

            return {
                'downloaded': downloaded,
                'pending': pending,
                'total': downloaded + pending,
                'by_store': store_counts,
                'files_on_disk': files_on_disk,
                'output_dir': str(self.output_dir),
            }

    def get_pending_orders(
        self,
        store_code: Optional[str] = None,
    ) -> list[dict]:
        """
        Get orders with pending waybill downloads.

        Args:
            store_code: Filter by store

        Returns:
            List of order dicts
        """
        with get_db(self.db_path) as conn:
            query = """
                SELECT *
                FROM fact_orders_kaspi
                WHERE waybill_url IS NOT NULL
                  AND waybill_url != ''
                  AND waybill_downloaded = 0
            """
            params = []

            if store_code:
                query += " AND store_code = ?"
                params.append(store_code)

            query += " ORDER BY planned_shipment_date ASC"

            rows = conn.execute(query, params).fetchall()
            return [dict(row) for row in rows]

    def clean_old_waybills(self, days: int = 30) -> int:
        """
        Remove waybill PDFs older than N days.

        Args:
            days: Delete files older than this many days

        Returns:
            Number of files deleted
        """
        if not self.output_dir.exists():
            return 0

        from datetime import timedelta
        cutoff = datetime.now() - timedelta(days=days)
        deleted = 0

        for pdf_file in self.output_dir.rglob('*.pdf'):
            try:
                mtime = datetime.fromtimestamp(pdf_file.stat().st_mtime)
                if mtime < cutoff:
                    pdf_file.unlink()
                    deleted += 1
                    logger.debug(f"Deleted old waybill: {pdf_file}")
            except Exception as e:
                logger.warning(f"Error deleting {pdf_file}: {e}")

        # Clean empty directories
        for dir_path in sorted(self.output_dir.rglob('*'), reverse=True):
            if dir_path.is_dir() and not any(dir_path.iterdir()):
                try:
                    dir_path.rmdir()
                except Exception:
                    pass

        logger.info(f"Cleaned {deleted} old waybill files (older than {days} days)")
        return deleted


# =============================================================================
# CLI TEST
# =============================================================================

if __name__ == "__main__":
    import sys
    from dotenv import load_dotenv

    load_dotenv()
    logging.basicConfig(level=logging.INFO)

    downloader = WaybillDownloader()

    print("=" * 60)
    print("Waybill Downloader Test")
    print("=" * 60)

    # Show stats
    stats = downloader.get_download_stats()
    print(f"\nDownload Statistics:")
    print(f"  Total orders with waybills: {stats['total']}")
    print(f"  Downloaded: {stats['downloaded']}")
    print(f"  Pending: {stats['pending']}")
    print(f"  Files on disk: {stats['files_on_disk']}")
    print(f"  Output directory: {stats['output_dir']}")

    if stats['by_store']:
        print("\n  By Store:")
        for store, counts in stats['by_store'].items():
            print(f"    {store}: downloaded={counts['downloaded']}, pending={counts['pending']}")

    # Show pending
    pending = downloader.get_pending_orders()
    if pending:
        print(f"\nPending Downloads ({len(pending)}):")
        for order in pending[:10]:
            print(f"  {order['order_id']} | {order['store_code']}")
        if len(pending) > 10:
            print(f"  ... and {len(pending) - 10} more")
    else:
        print("\nNo pending downloads")

    # Download if --download flag
    if '--download' in sys.argv:
        store = sys.argv[sys.argv.index('--download') + 1] if len(sys.argv) > sys.argv.index('--download') + 1 else None
        print(f"\nDownloading waybills for {store or 'all stores'}...")
        result = downloader.download_pending(store_code=store, limit=10)
        print(f"\nResult:")
        print(f"  Downloaded: {result.downloaded}")
        print(f"  Skipped: {result.skipped}")
        print(f"  Failed: {result.failed}")
        print(f"  Duration: {result.duration_sec:.1f}s")

    print("\n" + "=" * 60)
    print("Test complete!")
    print("=" * 60)
