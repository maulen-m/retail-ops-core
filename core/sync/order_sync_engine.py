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
import hashlib
import os
import yaml
from dataclasses import dataclass, field
import json
from datetime import datetime, timedelta, date
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
from core.integrations.kaspi_order_stage import (
    classify_kaspi_order_stage,
    classify_kaspi_stage_from_db_row,
    StageCode,
    stage_to_internal_status,
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
ORDER_STATUS_EVENT_WRITE_ENV_GATE = "ENABLE_ORDER_STATUS_EVENT_WRITE"


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

    def _ensure_sync_log_table(self, conn) -> None:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS kaspi_order_sync_log (
                store_code TEXT PRIMARY KEY,
                last_success_ts TEXT NOT NULL,
                min_date_seen TEXT,
                max_date_seen TEXT,
                orders_fetched INTEGER,
                orders_inserted INTEGER,
                orders_updated INTEGER,
                run_id TEXT,
                created_at TEXT DEFAULT (datetime('now'))
            )
            """
        )

    @staticmethod
    def _status_event_capture_enabled() -> bool:
        return os.environ.get(ORDER_STATUS_EVENT_WRITE_ENV_GATE) == "1"

    @staticmethod
    def _ensure_status_event_capture_schema(conn) -> None:
        columns = {
            str(row[1])
            for row in conn.execute("PRAGMA table_info(order_status_event)").fetchall()
        }
        required = {
            "event_id",
            "store_code",
            "order_id",
            "stage_code",
            "event_ts",
            "source",
            "raw_state",
            "raw_status",
            "source_status_change_at",
            "source_run_id",
            "flags_json",
            "source_row_hash",
            "idempotency_key",
        }
        missing = sorted(required - columns)
        if missing:
            raise RuntimeError(
                "order_status_event capture schema is missing required columns: "
                + ", ".join(missing)
            )
        idempotency_unique = False
        for index_row in conn.execute("PRAGMA index_list(order_status_event)").fetchall():
            if not bool(index_row[2]):
                continue
            index_columns = [
                str(column_row[2])
                for column_row in conn.execute(
                    f"PRAGMA index_info({index_row[1]})"
                ).fetchall()
            ]
            if index_columns == ["idempotency_key"]:
                idempotency_unique = True
                break
        if not idempotency_unique:
            raise RuntimeError(
                "order_status_event capture requires a unique idempotency_key index"
            )

    @staticmethod
    def _status_event_stage_code(stage: StageCode) -> str:
        if stage == StageCode.ISSUED_COMPLETED:
            return "COMPLETED"
        if stage == StageCode.RETURN_REQUESTED:
            return "RETURN"
        return stage.value

    @staticmethod
    def _hash_status_event_payload(payload: dict[str, Any]) -> str:
        encoded = json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        return hashlib.sha256(encoded.encode("utf-8")).hexdigest()

    @staticmethod
    def _db_observed_at(conn) -> str:
        row = conn.execute(
            "SELECT strftime('%Y-%m-%dT%H:%M:%fZ', 'now')"
        ).fetchone()
        observed_at = str(row[0] or "").strip()
        if not observed_at:
            raise RuntimeError("SQLite did not provide a status-event observation timestamp")
        return observed_at

    def _status_event_tuple(
        self,
        *,
        store_code: str,
        order_id: str,
        api_order: dict,
        order_data: dict,
    ) -> dict[str, str | None]:
        stage = classify_kaspi_order_stage(api_order)
        if stage == StageCode.UNKNOWN:
            raise RuntimeError(
                f"cannot append order_status_event for unknown stage: {store_code}/{order_id}"
            )
        raw_state = str(order_data.get("kaspi_status") or "").strip().upper() or None
        raw_status = (
            str(order_data.get("kaspi_status_detail") or "").strip().upper() or None
        )
        if (
            stage == StageCode.ISSUED_COMPLETED
            and not (raw_state == "ARCHIVE" and raw_status == "COMPLETED")
        ):
            raise RuntimeError(
                "cannot append completed order_status_event without strict "
                f"ARCHIVE/COMPLETED header evidence: {store_code}/{order_id}"
            )
        return {
            "stage_code": self._status_event_stage_code(stage),
            "raw_state": raw_state,
            "raw_status": raw_status,
        }

    @staticmethod
    def _latest_status_event(conn, *, store_code: str, order_id: str):
        return conn.execute(
            """
            SELECT event_id, stage_code, raw_state, raw_status, idempotency_key
            FROM order_status_event
            WHERE store_code = ? AND order_id = ?
            ORDER BY event_ts DESC, event_id DESC
            LIMIT 1
            """,
            (store_code, order_id),
        ).fetchone()

    @staticmethod
    def _event_tuple_matches(row, event_tuple: dict[str, str | None]) -> bool:
        if row is None:
            return False
        return (
            str(row["stage_code"] or "").strip().upper()
            == str(event_tuple["stage_code"] or "").strip().upper()
            and str(row["raw_state"] or "").strip().upper()
            == str(event_tuple["raw_state"] or "").strip().upper()
            and str(row["raw_status"] or "").strip().upper()
            == str(event_tuple["raw_status"] or "").strip().upper()
        )

    def _persist_status_event(
        self,
        conn,
        *,
        store_code: str,
        order_id: str,
        order_data: dict,
        event_tuple: dict[str, str | None],
        predecessor_idempotency_key: str | None,
        observed_at: str,
        run_id: str,
        observation_kind: str,
        old_internal_status: str | None,
    ) -> None:
        predecessor = predecessor_idempotency_key or "GENESIS"
        stage_code = str(event_tuple["stage_code"])
        raw_state = event_tuple["raw_state"]
        raw_status = event_tuple["raw_status"]
        source_payload = {
            "source": "KASPI_ORDER_SYNC",
            "store_code": store_code,
            "order_id": order_id,
            "stage_code": stage_code,
            "raw_state": raw_state,
            "raw_status": raw_status,
            "predecessor_idempotency_key": predecessor,
        }
        source_row_hash = self._hash_status_event_payload(source_payload)
        idempotency_key = source_row_hash
        cursor = conn.execute(
            """
            INSERT INTO order_status_event (
                store_code, order_id, stage_code, event_ts, source,
                raw_state, raw_status, source_status_change_at, source_run_id,
                flags_json, source_row_hash, idempotency_key
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(idempotency_key) DO NOTHING
            """,
            (
                store_code,
                order_id,
                stage_code,
                observed_at,
                "KASPI_ORDER_SYNC",
                raw_state,
                raw_status,
                observed_at,
                run_id,
                json.dumps(
                    {
                        "capture": "order_sync_engine",
                        "observation_kind": observation_kind,
                        "old_internal_status": old_internal_status,
                        "new_internal_status": order_data.get("internal_status"),
                        "predecessor_idempotency_key": predecessor,
                    },
                    ensure_ascii=False,
                    sort_keys=True,
                ),
                source_row_hash,
                idempotency_key,
            ),
        )
        if cursor.rowcount == 1:
            return
        existing = conn.execute(
            """
            SELECT store_code, order_id, stage_code, raw_state, raw_status,
                   source, source_row_hash, idempotency_key
            FROM order_status_event
            WHERE idempotency_key = ?
            """,
            (idempotency_key,),
        ).fetchone()
        if existing is None or not (
            str(existing["store_code"] or "") == store_code
            and str(existing["order_id"] or "") == order_id
            and str(existing["stage_code"] or "") == stage_code
            and str(existing["raw_state"] or "").strip().upper()
            == str(raw_state or "").strip().upper()
            and str(existing["raw_status"] or "").strip().upper()
            == str(raw_status or "").strip().upper()
            and str(existing["source"] or "") == "KASPI_ORDER_SYNC"
            and str(existing["source_row_hash"] or "") == source_row_hash
        ):
            raise RuntimeError(
                "order_status_event idempotency conflict did not read back exact semantic row: "
                f"{store_code}/{order_id}"
            )

    def _extract_order_date(self, api_order: dict) -> Optional[date]:
        attrs = api_order.get("attributes", {})
        if attrs.get("creationDate"):
            try:
                return datetime.fromtimestamp(attrs["creationDate"] / 1000).date()
            except Exception:
                return None
        return None

    def _record_sync_log(
        self,
        conn,
        store_code: str,
        orders: list[dict],
        result: SyncResult,
        run_id: str,
    ) -> None:
        self._ensure_sync_log_table(conn)
        dates = [d for d in (self._extract_order_date(o) for o in orders) if d]
        min_date = min(dates).isoformat() if dates else None
        max_date = max(dates).isoformat() if dates else None
        conn.execute(
            """
            INSERT OR REPLACE INTO kaspi_order_sync_log (
                store_code, last_success_ts, min_date_seen, max_date_seen,
                orders_fetched, orders_inserted, orders_updated, run_id
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                store_code,
                datetime.now().isoformat(timespec="seconds"),
                min_date,
                max_date,
                result.orders_fetched,
                result.orders_inserted,
                result.orders_updated,
                run_id,
            ),
        )

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
        run_id = start_time.strftime("%Y%m%d_%H%M%S")
        result = SyncResult(store_code=store_code, success=True)
        capture_status_events = self._status_event_capture_enabled()

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
                if capture_status_events:
                    self._ensure_status_event_capture_schema(conn)
                    # Ensure per-order savepoints are nested inside one store
                    # transaction; releasing a top-level SQLite savepoint would
                    # otherwise commit earlier orders before a later fail-closed stop.
                    conn.execute("BEGIN IMMEDIATE")
                for order in orders:
                    try:
                        save_result = self._save_order(
                            conn,
                            store_code,
                            order,
                            status_event_run_id=run_id,
                        )
                        if save_result['inserted']:
                            result.orders_inserted += 1
                        elif save_result['updated']:
                            result.orders_updated += 1

                        if save_result.get('status_change'):
                            result.status_changes.append(save_result['status_change'])

                    except Exception as e:
                        logger.error(f"Error saving order {order.get('id')}: {e}")
                        result.errors.append(str(e))
                        if capture_status_events:
                            raise
                if result.success:
                    self._record_sync_log(conn, store_code, orders, result, run_id)

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
            if capture_status_events:
                result.orders_inserted = 0
                result.orders_updated = 0
                result.status_changes = []

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
                    include_orders="user",
                )
                all_orders.extend(orders)
            return all_orders

        # Otherwise fetch all states
        return client.list_all_orders(
            since=since,
            until=until,
            include_orders="user",
        )

    def _save_order(
        self,
        conn,
        store_code: str,
        api_order: dict,
        *,
        status_event_run_id: str | None = None,
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
        capture_status_event = self._status_event_capture_enabled()
        if capture_status_event:
            self._ensure_status_event_capture_schema(conn)
            conn.execute("SAVEPOINT order_sync_status_event")

        try:
            # Parse API order
            order_data = self._parse_api_order(api_order, store_code)
            order_id = order_data['order_id']
            observed_at = None
            event_tuple = None
            latest_event = None
            event_changed = False
            if capture_status_event:
                observed_at = self._db_observed_at(conn)
                event_tuple = self._status_event_tuple(
                    store_code=store_code,
                    order_id=order_id,
                    api_order=api_order,
                    order_data=order_data,
                )
                latest_event = self._latest_status_event(
                    conn,
                    store_code=store_code,
                    order_id=order_id,
                )
                event_changed = not self._event_tuple_matches(latest_event, event_tuple)
                existing_rows = conn.execute(
                    """
                    SELECT id, internal_status, kaspi_status, kaspi_status_detail
                    FROM fact_orders_kaspi
                    WHERE order_id = ? AND store_code = ?
                    ORDER BY id
                    """,
                    (order_id, store_code),
                ).fetchall()
                header_tuples = {
                    (
                        str(row["internal_status"] or "").strip().upper(),
                        str(row["kaspi_status"] or "").strip().upper(),
                        str(row["kaspi_status_detail"] or "").strip().upper(),
                    )
                    for row in existing_rows
                }
                headers_conflicting = len(header_tuples) > 1
            else:
                existing = conn.execute(
                    """
                    SELECT id, internal_status, kaspi_status, kaspi_status_detail
                    FROM fact_orders_kaspi
                    WHERE order_id = ? AND store_code = ?
                    """,
                    (order_id, store_code),
                ).fetchone()
                existing_rows = [existing] if existing else []
                headers_conflicting = False

            if existing_rows:
                # Check for status change
                old_status = (
                    "CONFLICTING_HEADERS"
                    if headers_conflicting
                    else existing_rows[0]['internal_status']
                )
                new_status = order_data['internal_status']
                status_changed = any(
                    str(row['internal_status'] or "") != str(new_status or "")
                    for row in existing_rows
                )

                if status_changed:
                    result['status_change'] = StatusChange(
                        order_id=order_id,
                        old_status=old_status,
                        new_status=new_status,
                        kaspi_status=order_data.get('kaspi_status'),
                    )

                # Update every line-grain header row under guarded capture; the
                # legacy default-off path retains its original single-row behavior.
                for existing in existing_rows:
                    self._update_order(
                        conn,
                        existing['id'],
                        order_data,
                        status_changed=(status_changed or event_changed),
                        observed_at=observed_at,
                    )
                result['updated'] = True
            else:
                # Insert new
                self._insert_order(conn, order_data, observed_at=observed_at)
                result['inserted'] = True

            if capture_status_event and event_changed:
                self._persist_status_event(
                    conn,
                    store_code=store_code,
                    order_id=order_id,
                    order_data=order_data,
                    event_tuple=event_tuple,
                    predecessor_idempotency_key=(
                        str(latest_event["idempotency_key"])
                        if latest_event is not None
                        else None
                    ),
                    observed_at=str(observed_at),
                    run_id=status_event_run_id or "order_sync",
                    observation_kind=(
                        "status_transition"
                        if latest_event is not None
                        else ("baseline_existing" if existing_rows else "new_order")
                    ),
                    old_internal_status=(
                        existing_rows[0]['internal_status'] if existing_rows else None
                    ),
                )

            if capture_status_event:
                conn.execute("RELEASE SAVEPOINT order_sync_status_event")
            return result
        except Exception:
            if capture_status_event:
                conn.execute("ROLLBACK TO SAVEPOINT order_sync_status_event")
                conn.execute("RELEASE SAVEPOINT order_sync_status_event")
            raise

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
        customer = attrs.get('customer') or api_order.get('included_user') or {}

        def _ts_to_str(ts: Optional[int]) -> Optional[str]:
            if ts is None:
                return None
            try:
                return datetime.fromtimestamp(ts / 1000).strftime('%Y-%m-%d %H:%M:%S')
            except (OSError, ValueError, TypeError):
                return None

        # Parse dates
        created_at = None
        if attrs.get('creationDate'):
            created_at = datetime.fromtimestamp(
                attrs['creationDate'] / 1000
            ).strftime('%Y-%m-%d %H:%M:%S')

        planned_date = None
        effective_planned = planned_date_from_order(api_order, store_code=store_code)
        if effective_planned:
            planned_date = effective_planned.isoformat()

        planned_delivery_date = _ts_to_str(
            delivery.get('plannedDeliveryDate') or attrs.get('plannedDeliveryDate')
        )
        courier_transmission_planning_date = _ts_to_str(
            delivery.get('courierTransmissionPlanningDate')
        )
        courier_transmission_date = _ts_to_str(
            delivery.get('courierTransmissionDate')
        )
        approved_by_bank_date = _ts_to_str(attrs.get('approvedByBankDate'))
        reservation_date = _ts_to_str(attrs.get('reservationDate'))

        address = delivery.get('address') or {}
        delivery_address = (
            address.get('formattedAddress')
            or address.get('fullAddress')
            or address.get('address')
            or attrs.get('deliveryAddress')
        )

        # Map Kaspi lifecycle to internal status via StageCode
        kaspi_state = attrs.get('state', 'NEW')
        stage = classify_kaspi_order_stage(api_order)
        internal_status = stage_to_internal_status(stage)

        # Extract waybill URL
        waybill_url = delivery.get('waybill')
        waybill_number = delivery.get('waybillNumber') or attrs.get('waybillNumber')
        returned_to_warehouse = (
            delivery.get('returnedToWarehouse')
            if delivery.get('returnedToWarehouse') is not None
            else attrs.get('returnedToWarehouse')
        )
        if stage == StageCode.RETURNED:
            returned_to_warehouse = 1

        order_data = {
            'order_id': attrs.get('code', api_order.get('id', '')),
            'store_code': store_code,
            'channel_code': 'KSP',
            'kaspi_status': kaspi_state,
            'kaspi_status_detail': attrs.get('status'),
            'internal_status': internal_status,
            'unit_price_kzt': attrs.get('totalPrice', 0),
            'quantity': 1,  # Will be updated from entries
            'created_at': created_at,
            'planned_shipment_date': planned_date,
            'planned_delivery_date': planned_delivery_date,
            'courier_transmission_planning_date': courier_transmission_planning_date,
            'courier_transmission_date': courier_transmission_date,
            'actual_shipment_date': courier_transmission_date,
            'waybill_url': waybill_url,
            'waybill_number': waybill_number,
            'delivery_mode': attrs.get('deliveryMode'),
            'payment_mode': attrs.get('paymentMode'),
            'signature_required': attrs.get('signatureRequired'),
            'credit_term': attrs.get('creditTerm'),
            'pre_order': attrs.get('preOrder'),
            'approved_by_bank_date': approved_by_bank_date,
            'reservation_date': reservation_date,
            'delivery_cost': attrs.get('deliveryCost'),
            'delivery_cost_for_seller': (
                attrs.get('deliveryCostForSeller')
                or delivery.get('deliveryCostForSeller')
            ),
            'delivery_address': delivery_address,
            'is_imei_required': attrs.get('isImeiRequired'),
            'express': delivery.get('express') or attrs.get('express'),
            'returned_to_warehouse': returned_to_warehouse,
            'category': attrs.get('category'),
            'customer_first_name': customer.get('firstName'),
            'customer_last_name': customer.get('lastName'),
            'customer_phone': customer.get('cellPhone'),
            'source': 'API',
        }

        def _sanitize_value(value):
            if isinstance(value, (dict, list)):
                return json.dumps(value, ensure_ascii=False)
            return value

        return {key: _sanitize_value(value) for key, value in order_data.items()}

    def _insert_order(
        self,
        conn,
        order_data: dict,
        *,
        observed_at: str | None = None,
    ) -> int:
        """Insert new order into database."""
        cursor = conn.execute(
            """
            INSERT INTO fact_orders_kaspi (
                order_id, store_code, channel_code,
                kaspi_status, kaspi_status_detail, internal_status,
                unit_price_kzt, quantity,
                created_at, planned_shipment_date, planned_delivery_date,
                courier_transmission_planning_date, courier_transmission_date,
                actual_shipment_date,
                waybill_url, waybill_number,
                delivery_mode, payment_mode,
                signature_required, credit_term, pre_order,
                approved_by_bank_date, reservation_date,
                delivery_cost, delivery_cost_for_seller,
                delivery_address, is_imei_required,
                express, returned_to_warehouse, category,
                customer_first_name, customer_last_name, customer_phone,
                source
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                order_data['order_id'],
                order_data['store_code'],
                order_data['channel_code'],
                order_data['kaspi_status'],
                order_data.get('kaspi_status_detail'),
                order_data['internal_status'],
                order_data['unit_price_kzt'],
                order_data['quantity'],
                order_data['created_at'],
                order_data['planned_shipment_date'],
                order_data.get('planned_delivery_date'),
                order_data.get('courier_transmission_planning_date'),
                order_data.get('courier_transmission_date'),
                order_data.get('actual_shipment_date'),
                order_data['waybill_url'],
                order_data.get('waybill_number'),
                order_data.get('delivery_mode'),
                order_data.get('payment_mode'),
                order_data.get('signature_required'),
                order_data.get('credit_term'),
                order_data.get('pre_order'),
                order_data.get('approved_by_bank_date'),
                order_data.get('reservation_date'),
                order_data.get('delivery_cost'),
                order_data.get('delivery_cost_for_seller'),
                order_data.get('delivery_address'),
                order_data.get('is_imei_required'),
                order_data.get('express'),
                order_data.get('returned_to_warehouse'),
                order_data.get('category'),
                order_data.get('customer_first_name'),
                order_data.get('customer_last_name'),
                order_data.get('customer_phone'),
                order_data['source'],
            )
        )
        row_id = int(cursor.lastrowid)
        if observed_at is not None:
            if not self._column_exists(conn, "fact_orders_kaspi", "status_updated_at"):
                raise RuntimeError(
                    "fact_orders_kaspi lacks status_updated_at required for lifecycle capture"
                )
            conn.execute(
                "UPDATE fact_orders_kaspi SET status_updated_at = ? WHERE id = ?",
                (observed_at, row_id),
            )
        return row_id

    @staticmethod
    def _column_exists(conn, table: str, column: str) -> bool:
        """Return True when a column exists on a table."""
        rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
        return any(row[1] == column for row in rows)

    def _update_order(
        self,
        conn,
        row_id: int,
        order_data: dict,
        *,
        status_changed: bool,
        observed_at: str | None = None,
    ):
        """Update existing order in database."""
        has_synced_at = self._column_exists(conn, "fact_orders_kaspi", "synced_at")
        synced_at_clause = ", synced_at = CURRENT_TIMESTAMP" if has_synced_at else ""

        conn.execute(
            f"""
            UPDATE fact_orders_kaspi SET
                kaspi_status = ?,
                kaspi_status_detail = COALESCE(?, kaspi_status_detail),
                internal_status = ?,
                unit_price_kzt = ?,
                planned_shipment_date = ?,
                planned_delivery_date = COALESCE(?, planned_delivery_date),
                courier_transmission_planning_date = COALESCE(?, courier_transmission_planning_date),
                courier_transmission_date = COALESCE(?, courier_transmission_date),
                actual_shipment_date = COALESCE(?, actual_shipment_date),
                waybill_url = ?,
                waybill_number = COALESCE(?, waybill_number),
                delivery_mode = COALESCE(?, delivery_mode),
                payment_mode = COALESCE(?, payment_mode),
                signature_required = COALESCE(?, signature_required),
                credit_term = COALESCE(?, credit_term),
                pre_order = COALESCE(?, pre_order),
                approved_by_bank_date = COALESCE(?, approved_by_bank_date),
                reservation_date = COALESCE(?, reservation_date),
                delivery_cost = COALESCE(?, delivery_cost),
                delivery_cost_for_seller = COALESCE(?, delivery_cost_for_seller),
                delivery_address = COALESCE(?, delivery_address),
                is_imei_required = COALESCE(?, is_imei_required),
                express = COALESCE(?, express),
                returned_to_warehouse = COALESCE(?, returned_to_warehouse),
                category = COALESCE(?, category),
                customer_first_name = COALESCE(?, customer_first_name),
                customer_last_name = COALESCE(?, customer_last_name),
                customer_phone = COALESCE(?, customer_phone),
                status_updated_at = CASE
                    WHEN ? = 1 THEN COALESCE(?, CURRENT_TIMESTAMP)
                    ELSE status_updated_at
                END
                {synced_at_clause}
            WHERE id = ?
            """,
            (
                order_data['kaspi_status'],
                order_data.get('kaspi_status_detail'),
                order_data['internal_status'],
                order_data['unit_price_kzt'],
                order_data['planned_shipment_date'],
                order_data.get('planned_delivery_date'),
                order_data.get('courier_transmission_planning_date'),
                order_data.get('courier_transmission_date'),
                order_data.get('actual_shipment_date'),
                order_data['waybill_url'],
                order_data.get('waybill_number'),
                order_data.get('delivery_mode'),
                order_data.get('payment_mode'),
                order_data.get('signature_required'),
                order_data.get('credit_term'),
                order_data.get('pre_order'),
                order_data.get('approved_by_bank_date'),
                order_data.get('reservation_date'),
                order_data.get('delivery_cost'),
                order_data.get('delivery_cost_for_seller'),
                order_data.get('delivery_address'),
                order_data.get('is_imei_required'),
                order_data.get('express'),
                order_data.get('returned_to_warehouse'),
                order_data.get('category'),
                order_data.get('customer_first_name'),
                order_data.get('customer_last_name'),
                order_data.get('customer_phone'),
                1 if status_changed else 0,
                observed_at,
                row_id,
            ),
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
                WHERE 1=1
            """
            params = []

            if store_code:
                query += " AND store_code = ?"
                params.append(store_code)

            query += " ORDER BY created_at ASC"

            rows = conn.execute(query, params).fetchall()
            results = []
            for row in rows:
                stage = classify_kaspi_stage_from_db_row(row)
                if stage in {
                    StageCode.NEW_APPROVED,
                    StageCode.SIGN_REQUIRED,
                    StageCode.PREORDER_IN_TRANSIT,
                }:
                    results.append(dict(row))
            return results

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
                WHERE 1=1
            """
            params = []

            if store_code:
                query += " AND store_code = ?"
                params.append(store_code)

            query += " ORDER BY planned_shipment_date ASC"

            rows = conn.execute(query, params).fetchall()
            results = []
            for row in rows:
                if not row["waybill_url"]:
                    continue
                stage = classify_kaspi_stage_from_db_row(row)
                if stage == StageCode.ASSEMBLED_PENDING_HANDOVER:
                    results.append(dict(row))
            return results

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
