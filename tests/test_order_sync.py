"""
Tests for Order Sync Engine (Phase 9.5 - TASK-131).

Tests cover:
- Single store sync
- Multi-store sync
- Status change detection
- Order parsing from API
- Database save/update operations
- State mapping
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

from core.sync.order_sync_engine import (
    OrderSyncEngine,
    SyncResult,
    StatusChange,
    MultiSyncResult,
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
            source TEXT DEFAULT 'API',
            imported_at TEXT DEFAULT CURRENT_TIMESTAMP,
            status_updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
            assigned_size TEXT,
            size_source TEXT,
            size_confidence TEXT,
            UNIQUE(order_id, store_code)
        )
    """)
    conn.commit()
    conn.close()

    yield Path(path)

    os.unlink(path)


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
def temp_config():
    """Create temporary config file."""
    fd, path = tempfile.mkstemp(suffix='.yaml')
    os.close(fd)

    with open(path, 'w') as f:
        f.write("""
stores:
  UNIVERSAL:
    name: Universal Store
    priority: 1
    sync_enabled: true
  ACMEWEAR:
    name: AcmeWear Store
    priority: 2
    sync_enabled: false

settings:
  default_lookback_days: 7

order_states:
  NEW:
    internal_status: NEW
  ACCEPTED_BY_MERCHANT:
    internal_status: ACCEPTED
  ASSEMBLY:
    internal_status: READY
  KASPI_DELIVERY:
    internal_status: SHIPPED
  COMPLETED:
    internal_status: COMPLETED
  CANCELLED:
    internal_status: CANCELLED
""")

    yield Path(path)

    os.unlink(path)


@pytest.fixture
def engine(temp_db, temp_config, mock_env):
    """Create OrderSyncEngine with temp db and config."""
    return OrderSyncEngine(db_path=temp_db, config_path=temp_config)


@pytest.fixture
def sample_api_orders():
    """Sample orders from API."""
    return [
        {
            'id': 'order-001',
            'attributes': {
                'code': '111111',
                'state': 'NEW',
                'totalPrice': 10000,
                'deliveryCost': 0,
                'creationDate': int(datetime(2025, 12, 7, 10, 0).timestamp() * 1000),
                'kaspiDelivery': {
                    'waybill': None,
                    'plannedDeliveryDate': int(datetime(2025, 12, 10).timestamp() * 1000),
                }
            }
        },
        {
            'id': 'order-002',
            'attributes': {
                'code': '222222',
                'state': 'ACCEPTED_BY_MERCHANT',
                'totalPrice': 15000,
                'deliveryCost': 500,
                'creationDate': int(datetime(2025, 12, 6, 14, 30).timestamp() * 1000),
                'kaspiDelivery': {
                    'waybill': 'https://kaspi.kz/waybill/222.pdf',
                    'plannedDeliveryDate': int(datetime(2025, 12, 9).timestamp() * 1000),
                }
            }
        },
        {
            'id': 'order-003',
            'attributes': {
                'code': '333333',
                'state': 'KASPI_DELIVERY',
                'totalPrice': 20000,
                'deliveryCost': 1000,
                'creationDate': int(datetime(2025, 12, 5, 9, 0).timestamp() * 1000),
                'kaspiDelivery': {
                    'waybill': 'https://kaspi.kz/waybill/333.pdf',
                    'plannedDeliveryDate': int(datetime(2025, 12, 8).timestamp() * 1000),
                }
            }
        },
    ]


# =============================================================================
# SYNC RESULT TESTS
# =============================================================================

class TestSyncResult:
    """Tests for SyncResult dataclass."""

    def test_sync_result_defaults(self):
        """Test SyncResult default values."""
        result = SyncResult(store_code='TEST', success=True)

        assert result.store_code == 'TEST'
        assert result.success is True
        assert result.orders_fetched == 0
        assert result.orders_inserted == 0
        assert result.orders_updated == 0
        assert result.status_changes == []
        assert result.errors == []

    def test_status_change_defaults(self):
        """Test StatusChange default values."""
        change = StatusChange(
            order_id='123',
            old_status='NEW',
            new_status='ACCEPTED',
        )

        assert change.order_id == '123'
        assert change.old_status == 'NEW'
        assert change.new_status == 'ACCEPTED'
        assert change.detected_at is not None


# =============================================================================
# CONFIG LOADING TESTS
# =============================================================================

class TestConfigLoading:
    """Tests for configuration loading."""

    def test_load_config(self, engine):
        """Test that config is loaded correctly."""
        assert 'stores' in engine.config
        assert 'UNIVERSAL' in engine.config['stores']

    def test_missing_config_uses_defaults(self, temp_db, mock_env):
        """Test that missing config file uses defaults."""
        engine = OrderSyncEngine(
            db_path=temp_db,
            config_path=Path('/nonexistent/path.yaml')
        )

        assert engine.config == {'stores': {}, 'settings': {}}


# =============================================================================
# ORDER PARSING TESTS
# =============================================================================

class TestOrderParsing:
    """Tests for order parsing from API."""

    def test_parse_new_order(self, engine, sample_api_orders):
        """Test parsing NEW order."""
        order = sample_api_orders[0]
        parsed = engine._parse_api_order(order, 'UNIVERSAL')

        assert parsed['order_id'] == '111111'
        assert parsed['store_code'] == 'UNIVERSAL'
        assert parsed['kaspi_status'] == 'NEW'
        assert parsed['internal_status'] == 'NEW'
        assert parsed['unit_price_kzt'] == 10000
        assert parsed['waybill_url'] is None

    def test_parse_accepted_order(self, engine, sample_api_orders):
        """Test parsing ACCEPTED_BY_MERCHANT order."""
        order = sample_api_orders[1]
        parsed = engine._parse_api_order(order, 'UNIVERSAL')

        assert parsed['kaspi_status'] == 'ACCEPTED_BY_MERCHANT'
        assert parsed['internal_status'] == 'ACCEPTED'
        assert parsed['waybill_url'] == 'https://kaspi.kz/waybill/222.pdf'

    def test_parse_shipped_order(self, engine, sample_api_orders):
        """Test parsing KASPI_DELIVERY order."""
        order = sample_api_orders[2]
        parsed = engine._parse_api_order(order, 'UNIVERSAL')

        assert parsed['kaspi_status'] == 'KASPI_DELIVERY'
        assert parsed['internal_status'] == 'SHIPPED'

    def test_parse_dates(self, engine, sample_api_orders):
        """Test date parsing."""
        order = sample_api_orders[0]
        parsed = engine._parse_api_order(order, 'UNIVERSAL')

        assert parsed['created_at'] is not None
        assert parsed['planned_shipment_date'] is not None


# =============================================================================
# STATE MAPPING TESTS
# =============================================================================

class TestStateMapping:
    """Tests for Kaspi state to internal status mapping."""

    def test_map_new_state(self, engine):
        """Test mapping NEW state."""
        status = engine._map_state_to_status('NEW')
        assert status == 'NEW'

    def test_map_accepted_state(self, engine):
        """Test mapping ACCEPTED_BY_MERCHANT state."""
        status = engine._map_state_to_status('ACCEPTED_BY_MERCHANT')
        assert status == 'ACCEPTED'

    def test_map_assembly_state(self, engine):
        """Test mapping ASSEMBLY state."""
        status = engine._map_state_to_status('ASSEMBLY')
        assert status == 'READY'

    def test_map_delivery_state(self, engine):
        """Test mapping KASPI_DELIVERY state."""
        status = engine._map_state_to_status('KASPI_DELIVERY')
        assert status == 'SHIPPED'

    def test_map_completed_state(self, engine):
        """Test mapping COMPLETED state."""
        status = engine._map_state_to_status('COMPLETED')
        assert status == 'COMPLETED'

    def test_map_cancelled_state(self, engine):
        """Test mapping CANCELLED state."""
        status = engine._map_state_to_status('CANCELLED')
        assert status == 'CANCELLED'

    def test_map_unknown_state(self, engine):
        """Test mapping unknown state defaults to NEW."""
        status = engine._map_state_to_status('UNKNOWN_STATE')
        assert status == 'NEW'


# =============================================================================
# DATABASE OPERATIONS TESTS
# =============================================================================

class TestDatabaseOperations:
    """Tests for database save/update operations."""

    def test_insert_new_order(self, engine, temp_db, sample_api_orders):
        """Test inserting new order."""
        conn = sqlite3.connect(temp_db)
        conn.row_factory = sqlite3.Row

        order = sample_api_orders[0]
        result = engine._save_order(conn, 'UNIVERSAL', order)

        assert result['inserted'] is True
        assert result['updated'] is False
        assert result['status_change'] is None

        # Verify in database
        row = conn.execute(
            "SELECT * FROM fact_orders_kaspi WHERE order_id = ?",
            ('111111',)
        ).fetchone()

        assert row is not None
        assert row['store_code'] == 'UNIVERSAL'
        assert row['internal_status'] == 'NEW'

        conn.close()

    def test_update_existing_order(self, engine, temp_db, sample_api_orders):
        """Test updating existing order."""
        conn = sqlite3.connect(temp_db)
        conn.row_factory = sqlite3.Row

        # Insert first
        order = sample_api_orders[0]
        engine._save_order(conn, 'UNIVERSAL', order)
        conn.commit()

        # Update with new state
        order['attributes']['state'] = 'ACCEPTED_BY_MERCHANT'
        result = engine._save_order(conn, 'UNIVERSAL', order)

        assert result['inserted'] is False
        assert result['updated'] is True
        assert result['status_change'] is not None
        assert result['status_change'].old_status == 'NEW'
        assert result['status_change'].new_status == 'ACCEPTED'

        conn.close()

    def test_no_change_on_same_status(self, engine, temp_db, sample_api_orders):
        """Test that no status change when status is same."""
        conn = sqlite3.connect(temp_db)
        conn.row_factory = sqlite3.Row

        order = sample_api_orders[0]

        # Insert first
        engine._save_order(conn, 'UNIVERSAL', order)
        conn.commit()

        # Update with same state
        result = engine._save_order(conn, 'UNIVERSAL', order)

        assert result['status_change'] is None

        conn.close()


# =============================================================================
# SYNC STORE TESTS
# =============================================================================

class TestSyncStore:
    """Tests for single store sync."""

    @patch.object(OrderSyncEngine, '_get_client')
    def test_sync_store_dry_run(self, mock_get_client, engine, sample_api_orders):
        """Test sync_store in dry run mode."""
        mock_client = MagicMock()
        mock_client.list_all_orders.return_value = sample_api_orders
        mock_get_client.return_value = mock_client

        result = engine.sync_store(
            store_code='UNIVERSAL',
            since='2025-12-01',
            dry_run=True,
        )

        assert result.success is True
        assert result.orders_fetched == 3
        assert result.orders_inserted == 0  # Dry run, no inserts
        assert result.orders_updated == 0

    @patch.object(OrderSyncEngine, '_get_client')
    def test_sync_store_inserts_orders(self, mock_get_client, engine, sample_api_orders):
        """Test sync_store inserts new orders."""
        mock_client = MagicMock()
        mock_client.list_all_orders.return_value = sample_api_orders
        mock_get_client.return_value = mock_client

        result = engine.sync_store(
            store_code='UNIVERSAL',
            since='2025-12-01',
            dry_run=False,
        )

        assert result.success is True
        assert result.orders_fetched == 3
        assert result.orders_inserted == 3

    @patch.object(OrderSyncEngine, '_get_client')
    def test_sync_store_detects_status_changes(self, mock_get_client, engine, temp_db, sample_api_orders):
        """Test that sync detects status changes."""
        mock_client = MagicMock()
        mock_client.list_all_orders.return_value = sample_api_orders
        mock_get_client.return_value = mock_client

        # First sync
        engine.sync_store(store_code='UNIVERSAL', dry_run=False)

        # Update order state
        sample_api_orders[0]['attributes']['state'] = 'ACCEPTED_BY_MERCHANT'
        mock_client.list_all_orders.return_value = sample_api_orders

        # Second sync
        result = engine.sync_store(store_code='UNIVERSAL', dry_run=False)

        assert len(result.status_changes) >= 1
        change = result.status_changes[0]
        assert change.order_id == '111111'
        assert change.old_status == 'NEW'
        assert change.new_status == 'ACCEPTED'

    @patch.object(OrderSyncEngine, '_get_client')
    def test_sync_store_with_state_filter(self, mock_get_client, engine, sample_api_orders):
        """Test sync with specific state filters."""
        mock_client = MagicMock()
        mock_client.list_all_orders.return_value = [sample_api_orders[0]]
        mock_get_client.return_value = mock_client

        result = engine.sync_store(
            store_code='UNIVERSAL',
            states=['NEW'],
            dry_run=True,
        )

        # Verify list_all_orders was called with state filter
        mock_client.list_all_orders.assert_called()


# =============================================================================
# MULTI-STORE SYNC TESTS
# =============================================================================

class TestMultiStoreSync:
    """Tests for multi-store sync."""

    @patch.object(OrderSyncEngine, 'sync_store')
    def test_sync_all_stores_skips_disabled(self, mock_sync_store, engine):
        """Test that disabled stores are skipped."""
        mock_sync_store.return_value = SyncResult(
            store_code='UNIVERSAL',
            success=True,
            orders_fetched=5,
        )

        result = engine.sync_all_stores(dry_run=True, skip_disabled=True)

        # Only UNIVERSAL should be synced (ACMEWEAR is disabled in config)
        assert 'UNIVERSAL' in result.store_results

    @patch.object(OrderSyncEngine, 'sync_store')
    def test_sync_all_stores_aggregates_results(self, mock_sync_store, engine):
        """Test that multi-store results are aggregated."""
        mock_sync_store.return_value = SyncResult(
            store_code='UNIVERSAL',
            success=True,
            orders_fetched=10,
            orders_inserted=5,
            orders_updated=3,
        )

        result = engine.sync_all_stores(dry_run=False)

        assert isinstance(result, MultiSyncResult)
        assert result.total_orders_fetched >= 10


# =============================================================================
# STATUS CHANGE DETECTION TESTS
# =============================================================================

class TestStatusChangeDetection:
    """Tests for status change detection queries."""

    def test_detect_status_changes_empty(self, engine, temp_db):
        """Test detect_status_changes with no orders."""
        changes = engine.detect_status_changes(store_code='UNIVERSAL')
        assert changes == []

    @patch.object(OrderSyncEngine, '_get_client')
    def test_detect_status_changes_with_data(self, mock_get_client, engine, sample_api_orders):
        """Test detect_status_changes with orders."""
        mock_client = MagicMock()
        mock_client.list_all_orders.return_value = sample_api_orders
        mock_get_client.return_value = mock_client

        # Sync to populate database
        engine.sync_store(store_code='UNIVERSAL', dry_run=False)

        # Detect changes (recent updates)
        changes = engine.detect_status_changes(store_code='UNIVERSAL', since_hours=24)

        # Should find the 3 newly inserted orders
        assert len(changes) == 3


# =============================================================================
# UTILITY METHODS TESTS
# =============================================================================

class TestUtilityMethods:
    """Tests for utility methods."""

    @patch.object(OrderSyncEngine, '_get_client')
    def test_get_pending_orders(self, mock_get_client, engine, sample_api_orders):
        """Test get_pending_orders."""
        mock_client = MagicMock()
        mock_client.list_all_orders.return_value = sample_api_orders
        mock_get_client.return_value = mock_client

        # Sync to populate
        engine.sync_store(store_code='UNIVERSAL', dry_run=False)

        orders = engine.get_pending_orders(store_code='UNIVERSAL', status='NEW')

        assert len(orders) == 1
        assert orders[0]['order_id'] == '111111'

    @patch.object(OrderSyncEngine, '_get_client')
    def test_get_ready_for_shipment(self, mock_get_client, engine, sample_api_orders):
        """Test get_ready_for_shipment."""
        mock_client = MagicMock()

        # Make one order READY with waybill
        sample_api_orders[1]['attributes']['state'] = 'ASSEMBLY'
        mock_client.list_all_orders.return_value = sample_api_orders
        mock_get_client.return_value = mock_client

        engine.sync_store(store_code='UNIVERSAL', dry_run=False)

        orders = engine.get_ready_for_shipment(store_code='UNIVERSAL')

        # Order 222222 should be READY with waybill
        assert len(orders) == 1
        assert orders[0]['order_id'] == '222222'

    @patch.object(OrderSyncEngine, '_get_client')
    def test_get_sync_stats(self, mock_get_client, engine, sample_api_orders):
        """Test get_sync_stats."""
        mock_client = MagicMock()
        mock_client.list_all_orders.return_value = sample_api_orders
        mock_get_client.return_value = mock_client

        engine.sync_store(store_code='UNIVERSAL', dry_run=False)

        stats = engine.get_sync_stats()

        assert 'by_status' in stats
        assert 'by_store' in stats
        assert 'total' in stats
        assert stats['total'] == 3


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
