"""
Order Sync Engine for Kaspi API Integration (Phase 9.5).

Synchronizes orders between Kaspi API and local database (fact_orders_kaspi).

Features:
- Single store sync with incremental updates
- Multi-store sync with configurable priority
- Status change detection and logging
- Waybill URL extraction
- Dry-run mode for testing

Usage:
    from core.sync.order_sync_engine import OrderSyncEngine

    engine = OrderSyncEngine()
    result = engine.sync_store('UNIVERSAL', since='2025-12-01')
    result = engine.sync_all_stores(since='2025-12-01')
"""

import logging
import yaml
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Optional

from core.db import get_db
from core.integrations.kaspi_api_client import (
    KaspiAPIClient,
    KaspiAPIError,
    KaspiAuthError,
    get_client,
    STORE_TOKEN_MAP,
)
from core.utils.kaspi_dates import planned_date_from_order


logger = logging.getLogger(__name__)


# =============================================================================
# CONSTANTS
# =============================================================================

CONFIG_PATH = Path(__file__).parent.parent.parent / "config" / "kaspi_stores.yaml"
DB_PATH = Path(__file__).parent.parent.parent / "db" / "app.db"

DEFAULT_LOOKBACK_DAYS = 7
MAX_ORDERS_PER_SYNC = 1000


# =============================================================================
# DATA CLASSES
# =============================================================================

@dataclass
class SyncResult:
    """Result of a sync operation."""
    store_code: str
    success: bool
    orders_fetched: int = 0
    orders_inserted: int = 0
    orders_updated: int = 0
    status_changes: list = field(default_factory=list)
    errors: list = field(default_factory=list)
    duration_sec: float = 0.0


@dataclass
class StatusChange:
    """Represents an order status change."""
    order_id: str
    old_status: str
    new_status: str
    kaspi_status: Optional[str] = None
    detected_at: datetime = field(default_factory=datetime.now)


@dataclass
class MultiSyncResult:
    """Result of multi-store sync."""
    total_orders_fetched: int = 0
    total_orders_inserted: int = 0
    total_orders_updated: int = 0
    store_results: dict = field(default_factory=dict)
    errors: list = field(default_factory=list)
    duration_sec: float = 0.0


# =============================================================================
# SYNC ENGINE
# =============================================================================

class OrderSyncEngine:
    """
    Synchronizes orders between Kaspi API and local database.

    Args:
        db_path: Path to SQLite database
        config_path: Path to kaspi_stores.yaml config

    Attributes:
        db_path: Database path
        config: Loaded store configuration
    """

    def __init__(
        self,
        db_path: Path = None,
        config_path: Path = None,
    ):
        self.db_path = db_path or DB_PATH
        self.config_path = config_path or CONFIG_PATH
        self.config = self._load_config()

    def _load_config(self) -> dict:
        """Load store configuration from YAML."""
        if not self.config_path.exists():
            logger.warning(f"Config not found: {self.config_path}, using defaults")
            return {'stores': {}, 'settings': {}}

        with open(self.config_path, 'r', encoding='utf-8') as f:
            return yaml.safe_load(f)

    def _get_client(self, store_code: str) -> KaspiAPIClient:
        """Get API client for a store."""
        return get_client(store_code)

    # =========================================================================
    # SINGLE STORE SYNC
    # =========================================================================

    def sync_store(
        self,
        store_code: str,
        since: Optional[str] = None,
        until: Optional[str] = None,
        states: Optional[list[str]] = None,
        dry_run: bool = False,
    ) -> SyncResult:
        """
        Sync orders for a single store.

        Args:
            store_code: Store identifier (UNIVERSAL, ACMEWEAR, etc.)
            since: Start date for sync (ISO format or YYYY-MM-DD)
            until: End date for sync (default: now)
            states: List of order states to fetch (default: all)
            dry_run: If True, fetch but don't save to DB

        Returns:
            SyncResult with counts and status changes
        """
        start_time = datetime.now()
        result = SyncResult(store_code=store_code, success=True)

        logger.info(f"Starting sync for {store_code}, since={since}, dry_run={dry_run}")

        try:
            client = self._get_client(store_code)

            # Fetch orders from API
            orders = self._fetch_orders(
                client,
                since=since,
                until=until,
                states=states,
            )
            result.orders_fetched = len(orders)

            if dry_run:
                logger.info(f"Dry run: Would process {len(orders)} orders")
                result.duration_sec = (datetime.now() - start_time).total_seconds()
                return result

            # Save to database
            with get_db(self.db_path) as conn:
                for order in orders:
                    try:
                        save_result = self._save_order(conn, store_code, order)
                        if save_result['inserted']:
                            result.orders_inserted += 1
                        elif save_result['updated']:
                            result.orders_updated += 1

                        if save_result.get('status_change'):
                            result.status_changes.append(save_result['status_change'])

                    except Exception as e:
                        logger.error(f"Error saving order {order.get('id')}: {e}")
                        result.errors.append(str(e))

        except KaspiAuthError as e:
            logger.error(f"Auth error for {store_code}: {e}")
            result.success = False
            result.errors.append(f"Auth error: {e}")
        except KaspiAPIError as e:
            logger.error(f"API error for {store_code}: {e}")
            result.success = False
            result.errors.append(f"API error: {e}")
        except Exception as e:
            logger.exception(f"Unexpected error syncing {store_code}: {e}")
            result.success = False
            result.errors.append(f"Unexpected error: {e}")

        result.duration_sec = (datetime.now() - start_time).total_seconds()

        logger.info(
            f"Sync complete for {store_code}: "
            f"fetched={result.orders_fetched}, "
            f"inserted={result.orders_inserted}, "
            f"updated={result.orders_updated}, "
            f"status_changes={len(result.status_changes)}, "
            f"duration={result.duration_sec:.1f}s"
        )

        return result

    def _fetch_orders(
        self,
        client: KaspiAPIClient,
        since: Optional[str] = None,
        until: Optional[str] = None,
        states: Optional[list[str]] = None,
    ) -> list[dict]:
        """
        Fetch orders from API with optional filters.

        Args:
            client: Kaspi API client
            since: Start date
            until: End date
            states: Order states to fetch

        Returns:
            List of order dicts from API
        """
        # Default to last N days if no since date
        if since is None:
            lookback = self.config.get('settings', {}).get(
                'default_lookback_days',
                DEFAULT_LOOKBACK_DAYS
            )
            since = (datetime.now() - timedelta(days=lookback)).strftime('%Y-%m-%d')

        # If states specified, fetch each separately
        if states:
            all_orders = []
            for state in states:
                orders = client.list_all_orders(
                    state=state,
                    since=since,
                    until=until,
                )
                all_orders.extend(orders)
            return all_orders

        # Otherwise fetch all states
        return client.list_all_orders(
            since=since,
            until=until,
        )

    def _save_order(
        self,
        conn,
        store_code: str,
        api_order: dict,
    ) -> dict:
        """
        Save or update order in database.

        Args:
            conn: Database connection
            store_code: Store code
            api_order: Order dict from API

        Returns:
            Dict with 'inserted', 'updated', 'status_change' keys
        """
        result = {'inserted': False, 'updated': False, 'status_change': None}

        # Parse API order
        order_data = self._parse_api_order(api_order, store_code)
        order_id = order_data['order_id']

        # Check if order exists
        existing = conn.execute(
            """
            SELECT id, internal_status, kaspi_status
            FROM fact_orders_kaspi
            WHERE order_id = ? AND store_code = ?
            """,
            (order_id, store_code)
        ).fetchone()

        if existing:
            # Check for status change
            old_status = existing['internal_status']
            new_status = order_data['internal_status']

            if old_status != new_status:
                result['status_change'] = StatusChange(
                    order_id=order_id,
                    old_status=old_status,
                    new_status=new_status,
                    kaspi_status=order_data.get('kaspi_status'),
                )

            # Update existing
            self._update_order(conn, existing['id'], order_data)
            result['updated'] = True
        else:
            # Insert new
            self._insert_order(conn, order_data)
            result['inserted'] = True

        return result

    def _parse_api_order(self, api_order: dict, store_code: str) -> dict:
        """
        Parse API order dict into database format.

        Args:
            api_order: Raw order from API
            store_code: Store code

        Returns:
            Dict ready for database insert/update
        """
        attrs = api_order.get('attributes', {})
        delivery = attrs.get('kaspiDelivery', {})

        # Parse dates
        created_at = None
        if attrs.get('creationDate'):
            created_at = datetime.fromtimestamp(
                attrs['creationDate'] / 1000
            ).strftime('%Y-%m-%d %H:%M:%S')

        planned_date = None
        effective_planned = planned_date_from_order(api_order)
        if effective_planned:
            planned_date = effective_planned.isoformat()

        # Map Kaspi state to internal status
        kaspi_state = attrs.get('state', 'NEW')
        internal_status = self._map_state_to_status(kaspi_state)

        # Extract waybill URL
        waybill_url = delivery.get('waybill')

        return {
            'order_id': attrs.get('code', api_order.get('id', '')),
            'store_code': store_code,
            'channel_code': 'KSP',
            'kaspi_status': kaspi_state,
            'internal_status': internal_status,
            'unit_price_kzt': attrs.get('totalPrice', 0),
            'quantity': 1,  # Will be updated from entries
            'created_at': created_at,
            'planned_shipment_date': planned_date,
            'waybill_url': waybill_url,
            'source': 'API',
        }

    def _map_state_to_status(self, kaspi_state: str) -> str:
        """Map Kaspi state to internal status."""
        state_map = self.config.get('order_states', {})

        if kaspi_state in state_map:
            return state_map[kaspi_state].get('internal_status', 'NEW')

        # Default mapping
        default_map = {
            'NEW': 'NEW',
            'ACCEPTED_BY_MERCHANT': 'ACCEPTED',
            'ASSEMBLY': 'READY',
            'KASPI_DELIVERY': 'SHIPPED',
            'DELIVERY': 'SHIPPED',
            'COMPLETED': 'COMPLETED',
            'CANCELLED': 'CANCELLED',
            'RETURNING': 'RETURNING',
            'RETURNED': 'RETURNED',
        }
        return default_map.get(kaspi_state, 'NEW')

    def _insert_order(self, conn, order_data: dict):
        """Insert new order into database."""
        conn.execute(
            """
            INSERT INTO fact_orders_kaspi (
                order_id, store_code, channel_code,
                kaspi_status, internal_status,
                unit_price_kzt, quantity,
                created_at, planned_shipment_date,
                waybill_url, source
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                order_data['order_id'],
                order_data['store_code'],
                order_data['channel_code'],
                order_data['kaspi_status'],
                order_data['internal_status'],
                order_data['unit_price_kzt'],
                order_data['quantity'],
                order_data['created_at'],
                order_data['planned_shipment_date'],
                order_data['waybill_url'],
                order_data['source'],
            )
        )

    def _update_order(self, conn, row_id: int, order_data: dict):
        """Update existing order in database."""
        conn.execute(
            """
            UPDATE fact_orders_kaspi SET
                kaspi_status = ?,
                internal_status = ?,
                unit_price_kzt = ?,
                planned_shipment_date = ?,
                waybill_url = ?,
                status_updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (
                order_data['kaspi_status'],
                order_data['internal_status'],
                order_data['unit_price_kzt'],
                order_data['planned_shipment_date'],
                order_data['waybill_url'],
                row_id,
            )
        )

    # =========================================================================
    # MULTI-STORE SYNC
    # =========================================================================

    def sync_all_stores(
        self,
        since: Optional[str] = None,
        until: Optional[str] = None,
        states: Optional[list[str]] = None,
        dry_run: bool = False,
        skip_disabled: bool = True,
    ) -> MultiSyncResult:
        """
        Sync orders for all configured stores.

        Args:
            since: Start date for sync
            until: End date for sync
            states: Order states to fetch
            dry_run: If True, fetch but don't save
            skip_disabled: Skip stores with sync_enabled=false

        Returns:
            MultiSyncResult with aggregated results
        """
        start_time = datetime.now()
        result = MultiSyncResult()

        # Get stores sorted by priority
        stores_config = self.config.get('stores', {})
        stores = sorted(
            stores_config.items(),
            key=lambda x: x[1].get('priority', 99)
        )

        for store_code, store_config in stores:
            # Skip disabled stores
            if skip_disabled and not store_config.get('sync_enabled', True):
                logger.info(f"Skipping disabled store: {store_code}")
                continue

            # Check if token env var exists
            if store_code not in STORE_TOKEN_MAP:
                logger.warning(f"Unknown store code: {store_code}")
                continue

            try:
                store_result = self.sync_store(
                    store_code=store_code,
                    since=since,
                    until=until,
                    states=states,
                    dry_run=dry_run,
                )

                result.store_results[store_code] = store_result
                result.total_orders_fetched += store_result.orders_fetched
                result.total_orders_inserted += store_result.orders_inserted
                result.total_orders_updated += store_result.orders_updated

                if store_result.errors:
                    result.errors.extend(
                        [f"{store_code}: {e}" for e in store_result.errors]
                    )

            except Exception as e:
                logger.error(f"Error syncing {store_code}: {e}")
                result.errors.append(f"{store_code}: {e}")

        result.duration_sec = (datetime.now() - start_time).total_seconds()

        logger.info(
            f"Multi-store sync complete: "
            f"stores={len(result.store_results)}, "
            f"fetched={result.total_orders_fetched}, "
            f"inserted={result.total_orders_inserted}, "
            f"updated={result.total_orders_updated}, "
            f"duration={result.duration_sec:.1f}s"
        )

        return result

    # =========================================================================
    # STATUS CHANGE DETECTION
    # =========================================================================

    def detect_status_changes(
        self,
        store_code: Optional[str] = None,
        since_hours: int = 24,
    ) -> list[StatusChange]:
        """
        Detect orders with status changes in recent period.

        Args:
            store_code: Filter by store (None for all)
            since_hours: Look back this many hours

        Returns:
            List of StatusChange objects
        """
        cutoff = (datetime.now() - timedelta(hours=since_hours)).strftime(
            '%Y-%m-%d %H:%M:%S'
        )

        with get_db(self.db_path) as conn:
            query = """
                SELECT order_id, internal_status, kaspi_status, status_updated_at
                FROM fact_orders_kaspi
                WHERE status_updated_at >= ?
            """
            params = [cutoff]

            if store_code:
                query += " AND store_code = ?"
                params.append(store_code)

            query += " ORDER BY status_updated_at DESC"

            rows = conn.execute(query, params).fetchall()

            # Note: This returns currently changed orders
            # For full change history, we'd need a separate audit table
            return [
                StatusChange(
                    order_id=row['order_id'],
                    old_status='',  # Not tracked without audit table
                    new_status=row['internal_status'],
                    kaspi_status=row['kaspi_status'],
                    detected_at=datetime.fromisoformat(row['status_updated_at'])
                    if row['status_updated_at'] else datetime.now(),
                )
                for row in rows
            ]

    # =========================================================================
    # UTILITIES
    # =========================================================================

    def get_pending_orders(
        self,
        store_code: Optional[str] = None,
        status: str = 'NEW',
    ) -> list[dict]:
        """
        Get orders with specific status from database.

        Args:
            store_code: Filter by store (None for all)
            status: Internal status to filter

        Returns:
            List of order dicts
        """
        with get_db(self.db_path) as conn:
            query = """
                SELECT * FROM fact_orders_kaspi
                WHERE internal_status = ?
            """
            params = [status]

            if store_code:
                query += " AND store_code = ?"
                params.append(store_code)

            query += " ORDER BY created_at ASC"

            rows = conn.execute(query, params).fetchall()
            return [dict(row) for row in rows]

    def get_ready_for_shipment(
        self,
        store_code: Optional[str] = None,
    ) -> list[dict]:
        """
        Get orders ready for shipment (READY status with waybill).

        Args:
            store_code: Filter by store (None for all)

        Returns:
            List of order dicts ready for shipment
        """
        with get_db(self.db_path) as conn:
            query = """
                SELECT * FROM fact_orders_kaspi
                WHERE internal_status = 'READY'
                  AND waybill_url IS NOT NULL
            """
            params = []

            if store_code:
                query += " AND store_code = ?"
                params.append(store_code)

            query += " ORDER BY planned_shipment_date ASC"

            rows = conn.execute(query, params).fetchall()
            return [dict(row) for row in rows]

    def get_sync_stats(self) -> dict:
        """
        Get sync statistics from database.

        Returns:
            Dict with counts by status, store, etc.
        """
        with get_db(self.db_path) as conn:
            # Count by status
            status_counts = {}
            rows = conn.execute(
                """
                SELECT internal_status, COUNT(*) as cnt
                FROM fact_orders_kaspi
                GROUP BY internal_status
                """
            ).fetchall()
            for row in rows:
                status_counts[row['internal_status']] = row['cnt']

            # Count by store
            store_counts = {}
            rows = conn.execute(
                """
                SELECT store_code, COUNT(*) as cnt
                FROM fact_orders_kaspi
                GROUP BY store_code
                """
            ).fetchall()
            for row in rows:
                store_counts[row['store_code']] = row['cnt']

            # Recent activity
            recent = conn.execute(
                """
                SELECT COUNT(*) as cnt
                FROM fact_orders_kaspi
                WHERE imported_at >= datetime('now', '-24 hours')
                """
            ).fetchone()['cnt']

            return {
                'by_status': status_counts,
                'by_store': store_counts,
                'recent_24h': recent,
                'total': sum(status_counts.values()),
            }


# =============================================================================
# CLI TEST
# =============================================================================

if __name__ == "__main__":
    import sys
    from dotenv import load_dotenv

    load_dotenv()
    logging.basicConfig(level=logging.INFO)

    engine = OrderSyncEngine()

    print("=" * 60)
    print("Order Sync Engine Test")
    print("=" * 60)

    # Show current stats
    print("\nCurrent database stats:")
    stats = engine.get_sync_stats()
    print(f"  Total orders: {stats['total']}")
    print(f"  By status: {stats['by_status']}")
    print(f"  By store: {stats['by_store']}")
    print(f"  Recent 24h: {stats['recent_24h']}")

    # Test sync
    store = sys.argv[1] if len(sys.argv) > 1 else 'UNIVERSAL'
    dry_run = '--dry-run' in sys.argv

    print(f"\nSyncing {store} (dry_run={dry_run})...")

    result = engine.sync_store(
        store_code=store,
        since='2025-12-01',
        dry_run=dry_run,
    )

    print(f"\nSync Result:")
    print(f"  Success: {result.success}")
    print(f"  Fetched: {result.orders_fetched}")
    print(f"  Inserted: {result.orders_inserted}")
    print(f"  Updated: {result.orders_updated}")
    print(f"  Status changes: {len(result.status_changes)}")
    print(f"  Duration: {result.duration_sec:.1f}s")

    if result.errors:
        print(f"  Errors: {result.errors}")

    print("\n" + "=" * 60)
    print("Test complete!")
    print("=" * 60)
