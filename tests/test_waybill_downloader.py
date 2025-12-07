"""
Tests for Waybill Downloader (Phase 9.5 - TASK-132).

Tests cover:
- Waybill URL extraction
- Batch download operations
- Rate limiting
- Database status updates
- File system operations
- Error handling
"""

import os
import sqlite3
import tempfile
import pytest
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch, MagicMock

# Add project root to path
import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from core.waybill.waybill_downloader import (
    WaybillDownloader,
    DownloadResult,
    BatchDownloadResult,
)
from core.integrations.kaspi_api_client import APIResponse


# =============================================================================
# FIXTURES
# =============================================================================

@pytest.fixture
def temp_db():
    """Create temporary database with schema."""
    fd, path = tempfile.mkstemp(suffix='.db')
    os.close(fd)

    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row

    # Create fact_orders_kaspi table
    conn.execute("""
        CREATE TABLE fact_orders_kaspi (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            order_id TEXT NOT NULL,
            store_code TEXT NOT NULL,
            channel_code TEXT DEFAULT 'KSP',
            kaspi_status TEXT,
            internal_status TEXT,
            unit_price_kzt REAL,
            quantity INTEGER DEFAULT 1,
            created_at TEXT,
            planned_shipment_date TEXT,
            waybill_url TEXT,
            waybill_downloaded INTEGER DEFAULT 0,
            waybill_path TEXT,
            source TEXT DEFAULT 'API',
            imported_at TEXT DEFAULT CURRENT_TIMESTAMP,
            status_updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(order_id, store_code)
        )
    """)
    conn.commit()
    conn.close()

    yield Path(path)

    os.unlink(path)


@pytest.fixture
def temp_output_dir():
    """Create temporary output directory."""
    dir_path = tempfile.mkdtemp()
    yield Path(dir_path)
    # Cleanup
    import shutil
    shutil.rmtree(dir_path, ignore_errors=True)


@pytest.fixture
def mock_env():
    """Set up mock environment variables."""
    env_vars = {
        'KASPI_TOKEN_UNIVERSAL': 'test-token-universal',
        'ENABLE_KASPI_WRITE': '0',
    }
    with patch.dict(os.environ, env_vars, clear=False):
        yield env_vars


@pytest.fixture
def downloader(temp_db, temp_output_dir, mock_env):
    """Create WaybillDownloader with temp db."""
    return WaybillDownloader(
        db_path=temp_db,
        output_dir=temp_output_dir,
    )


@pytest.fixture
def sample_orders_data():
    """Sample order data for database."""
    return [
        {
            'order_id': '111111',
            'store_code': 'UNIVERSAL',
            'internal_status': 'READY',
            'waybill_url': 'https://kaspi.kz/waybill/111.pdf',
            'waybill_downloaded': 0,
        },
        {
            'order_id': '222222',
            'store_code': 'UNIVERSAL',
            'internal_status': 'READY',
            'waybill_url': 'https://kaspi.kz/waybill/222.pdf',
            'waybill_downloaded': 0,
        },
        {
            'order_id': '333333',
            'store_code': 'UNIVERSAL',
            'internal_status': 'READY',
            'waybill_url': None,  # No waybill
            'waybill_downloaded': 0,
        },
        {
            'order_id': '444444',
            'store_code': 'UNIVERSAL',
            'internal_status': 'READY',
            'waybill_url': 'https://kaspi.kz/waybill/444.pdf',
            'waybill_downloaded': 1,  # Already downloaded
        },
    ]


def insert_sample_orders(db_path, orders):
    """Insert sample orders into database."""
    conn = sqlite3.connect(db_path)
    for order in orders:
        conn.execute("""
            INSERT INTO fact_orders_kaspi
            (order_id, store_code, internal_status, waybill_url, waybill_downloaded)
            VALUES (?, ?, ?, ?, ?)
        """, (
            order['order_id'],
            order['store_code'],
            order['internal_status'],
            order['waybill_url'],
            order['waybill_downloaded'],
        ))
    conn.commit()
    conn.close()


# =============================================================================
# DOWNLOAD RESULT TESTS
# =============================================================================

class TestDownloadResult:
    """Tests for DownloadResult dataclass."""

    def test_download_result_success(self):
        """Test successful download result."""
        result = DownloadResult(
            order_id='123',
            success=True,
            filepath=Path('/path/to/waybill.pdf'),
        )

        assert result.success is True
        assert result.filepath == Path('/path/to/waybill.pdf')
        assert result.error is None

    def test_download_result_failure(self):
        """Test failed download result."""
        result = DownloadResult(
            order_id='123',
            success=False,
            error='Connection timeout',
        )

        assert result.success is False
        assert result.error == 'Connection timeout'


class TestBatchDownloadResult:
    """Tests for BatchDownloadResult dataclass."""

    def test_batch_result_defaults(self):
        """Test BatchDownloadResult default values."""
        result = BatchDownloadResult()

        assert result.total_orders == 0
        assert result.downloaded == 0
        assert result.failed == 0
        assert result.skipped == 0
        assert result.results == []


# =============================================================================
# INITIALIZATION TESTS
# =============================================================================

class TestInitialization:
    """Tests for WaybillDownloader initialization."""

    def test_downloader_init(self, downloader, temp_output_dir):
        """Test downloader initialization."""
        assert downloader.output_dir == temp_output_dir

    def test_downloader_creates_output_dir(self, temp_db, mock_env):
        """Test that output directory is created if missing."""
        output_dir = Path(tempfile.mkdtemp()) / 'new_subdir'

        downloader = WaybillDownloader(
            db_path=temp_db,
            output_dir=output_dir,
        )

        assert output_dir.exists()

        # Cleanup
        import shutil
        shutil.rmtree(output_dir.parent)


# =============================================================================
# PENDING ORDERS TESTS
# =============================================================================

class TestPendingOrders:
    """Tests for getting pending waybill downloads."""

    def test_get_pending_no_orders(self, downloader):
        """Test get_pending_orders with no orders."""
        orders = downloader.get_pending_orders(store_code='UNIVERSAL')
        assert orders == []

    def test_get_pending_with_orders(self, downloader, temp_db, sample_orders_data):
        """Test get_pending_orders with orders."""
        insert_sample_orders(temp_db, sample_orders_data)

        orders = downloader.get_pending_orders(store_code='UNIVERSAL')

        # Should find 2 orders (111111 and 222222) - not 333333 (no URL) or 444444 (already downloaded)
        assert len(orders) == 2
        order_ids = [o['order_id'] for o in orders]
        assert '111111' in order_ids
        assert '222222' in order_ids

    def test_get_pending_filters_by_store(self, downloader, temp_db, sample_orders_data):
        """Test that store filter works."""
        insert_sample_orders(temp_db, sample_orders_data)

        orders = downloader.get_pending_orders(store_code='UNIVERSAL')

        # All should be from UNIVERSAL
        assert all(o['store_code'] == 'UNIVERSAL' for o in orders)


# =============================================================================
# DOWNLOAD STATS TESTS
# =============================================================================

class TestDownloadStats:
    """Tests for download statistics."""

    def test_get_download_stats_empty(self, downloader):
        """Test stats with empty database."""
        stats = downloader.get_download_stats()

        assert stats['total'] == 0
        assert stats['pending'] == 0
        assert stats['downloaded'] == 0

    def test_get_download_stats_with_data(self, downloader, temp_db, sample_orders_data):
        """Test stats with data."""
        insert_sample_orders(temp_db, sample_orders_data)

        stats = downloader.get_download_stats()

        # Stats may count only orders with waybill URLs: 3 have URL
        # - 2 pending (have URL and not downloaded: 111111, 222222)
        # - 1 downloaded (444444)
        # total should be 3 (orders with waybill URL)
        assert stats['total'] == 3
        assert stats['pending'] == 2
        assert stats['downloaded'] == 1


# =============================================================================
# BATCH DOWNLOAD TESTS
# =============================================================================

class TestBatchDownload:
    """Tests for batch waybill downloads."""

    @patch('core.waybill.waybill_downloader.get_client')
    def test_download_pending_empty(self, mock_get_client, downloader):
        """Test download_pending with no pending orders."""
        mock_client = MagicMock()
        mock_get_client.return_value = mock_client

        result = downloader.download_pending(store_code='UNIVERSAL')

        assert result.total_orders == 0
        assert result.downloaded == 0

    @patch('core.waybill.waybill_downloader.get_client')
    def test_download_pending_success(self, mock_get_client, downloader, temp_db, sample_orders_data):
        """Test download_pending with orders."""
        insert_sample_orders(temp_db, sample_orders_data)

        mock_client = MagicMock()
        mock_client.download_waybill.return_value = APIResponse(
            success=True,
            data=b'%PDF-1.4 fake pdf content',
            status_code=200,
        )
        mock_get_client.return_value = mock_client

        result = downloader.download_pending(store_code='UNIVERSAL')

        assert result.total_orders == 2  # Two pending
        assert result.downloaded == 2
        assert result.failed == 0

    @patch('core.waybill.waybill_downloader.get_client')
    def test_download_pending_partial_failure(self, mock_get_client, downloader, temp_db, sample_orders_data):
        """Test download_pending with some failures."""
        insert_sample_orders(temp_db, sample_orders_data)

        # First call succeeds, second fails
        mock_client = MagicMock()
        mock_client.download_waybill.side_effect = [
            APIResponse(success=True, data=b'%PDF-1.4', status_code=200),
            APIResponse(success=False, error='Server error', status_code=500),
        ]
        mock_get_client.return_value = mock_client

        result = downloader.download_pending(store_code='UNIVERSAL')

        assert result.total_orders == 2
        assert result.downloaded == 1
        assert result.failed == 1

    @patch('core.waybill.waybill_downloader.get_client')
    def test_download_pending_respects_limit(self, mock_get_client, downloader, temp_db, sample_orders_data):
        """Test that limit parameter works in batch download."""
        insert_sample_orders(temp_db, sample_orders_data)

        mock_client = MagicMock()
        mock_client.download_waybill.return_value = APIResponse(
            success=True,
            data=b'%PDF-1.4',
            status_code=200,
        )
        mock_get_client.return_value = mock_client

        result = downloader.download_pending(store_code='UNIVERSAL', limit=1)

        assert result.total_orders == 1  # Only 1 due to limit


# =============================================================================
# DATABASE UPDATE TESTS
# =============================================================================

class TestDatabaseUpdates:
    """Tests for database status updates after download."""

    @patch('core.waybill.waybill_downloader.get_client')
    def test_download_updates_db(self, mock_get_client, downloader, temp_db, sample_orders_data):
        """Test that successful download updates database."""
        insert_sample_orders(temp_db, sample_orders_data)

        mock_client = MagicMock()
        mock_client.download_waybill.return_value = APIResponse(
            success=True,
            data=b'%PDF-1.4 fake pdf',
            status_code=200,
        )
        mock_get_client.return_value = mock_client

        # Download waybills
        result = downloader.download_pending(store_code='UNIVERSAL')

        assert result.downloaded >= 1

        # Verify database was updated
        conn = sqlite3.connect(temp_db)
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT waybill_downloaded FROM fact_orders_kaspi WHERE order_id = ?",
            ('111111',)
        ).fetchone()
        conn.close()

        assert row['waybill_downloaded'] == 1


# =============================================================================
# FILE OPERATIONS TESTS
# =============================================================================

class TestFileOperations:
    """Tests for file system operations."""

    def test_get_output_path(self, downloader, temp_output_dir):
        """Test output path generation."""
        path = downloader._get_output_path('123456')

        assert '123456' in str(path)
        assert str(path).endswith('.pdf')

    @patch('core.waybill.waybill_downloader.get_client')
    def test_file_saved_correctly(self, mock_get_client, downloader, temp_db, sample_orders_data):
        """Test that file content is saved correctly."""
        insert_sample_orders(temp_db, sample_orders_data)

        pdf_content = b'%PDF-1.4 test content 12345'

        mock_client = MagicMock()
        mock_client.download_waybill.return_value = APIResponse(
            success=True,
            data=pdf_content,
            status_code=200,
        )
        mock_get_client.return_value = mock_client

        result = downloader.download_pending(store_code='UNIVERSAL', limit=1)

        assert result.downloaded == 1

        # Find the downloaded file
        download_result = result.results[0]
        assert download_result.success is True

        # Verify file content
        with open(download_result.filepath, 'rb') as f:
            saved_content = f.read()

        assert saved_content == pdf_content


# =============================================================================
# CLEANUP TESTS
# =============================================================================

class TestCleanup:
    """Tests for waybill cleanup operations."""

    def test_clean_old_waybills(self, downloader, temp_output_dir):
        """Test cleaning old waybill files."""
        # Create some fake waybill files
        old_file = temp_output_dir / 'old_waybill.pdf'
        new_file = temp_output_dir / 'new_waybill.pdf'

        old_file.write_bytes(b'old content')
        new_file.write_bytes(b'new content')

        # Set old file modification time to 40 days ago
        import time
        old_time = time.time() - (40 * 24 * 60 * 60)
        os.utime(old_file, (old_time, old_time))

        # Clean files older than 30 days
        count = downloader.clean_old_waybills(days=30)

        assert count >= 1
        assert not old_file.exists()
        assert new_file.exists()


# =============================================================================
# PENDING ORDERS FILTERING TESTS
# =============================================================================

class TestPendingOrdersFiltering:
    """Tests for pending orders filtering."""

    @patch('core.waybill.waybill_downloader.get_client')
    def test_skips_already_downloaded(self, mock_get_client, downloader, temp_db, sample_orders_data):
        """Test that already downloaded waybills are skipped."""
        insert_sample_orders(temp_db, sample_orders_data)

        mock_client = MagicMock()
        mock_client.download_waybill.return_value = APIResponse(
            success=True,
            data=b'%PDF-1.4',
            status_code=200,
        )
        mock_get_client.return_value = mock_client

        # Normal download should skip already downloaded (order 444444)
        result = downloader.download_pending(store_code='UNIVERSAL')
        assert result.total_orders == 2  # Only pending ones (111111 and 222222)

    def test_skips_orders_without_url(self, downloader, temp_db, sample_orders_data):
        """Test that orders without waybill URL are skipped."""
        insert_sample_orders(temp_db, sample_orders_data)

        orders = downloader.get_pending_orders(store_code='UNIVERSAL')

        # Should not include 333333 (no waybill URL)
        order_ids = [o['order_id'] for o in orders]
        assert '333333' not in order_ids


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
