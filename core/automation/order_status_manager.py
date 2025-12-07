"""
Order Status Manager for Kaspi API Order Lifecycle (Phase 9.5).

Manages order status transitions via the Kaspi API:
- Accept NEW orders
- Mark orders as assembled (ASSEMBLY)
- Ship orders (hand to Kaspi delivery)
- Cancel orders with reason

Features:
- ENABLE_KASPI_WRITE guard for all write operations
- Telegram confirmation for bulk operations
- Dry-run mode for testing
- Batch operations with rate limiting

Usage:
    from core.automation.order_status_manager import OrderStatusManager

    manager = OrderStatusManager(store_code='UNIVERSAL')

    # Accept a single order
    result = manager.accept_order('123456')

    # Accept all NEW orders
    result = manager.accept_ready_orders(confirm=True)

    # Mark order as assembled
    result = manager.assemble_order('123456')
"""

import logging
import os
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

from core.db import get_db
from core.integrations.kaspi_api_client import (
    KaspiAPIClient,
    KaspiAPIError,
    KaspiWriteDisabledError,
    get_client,
)
from core.alerts.telegram import send_message, get_telegram_config


logger = logging.getLogger(__name__)


# =============================================================================
# CONSTANTS
# =============================================================================

DB_PATH = os.environ.get('DB_PATH', 'db/app.db')

# Minimum orders before requiring Telegram confirmation
BULK_THRESHOLD = 5

# Cancellation reasons supported by Kaspi API
CANCEL_REASONS = [
    'OUT_OF_STOCK',
    'CUSTOMER_REQUEST',
    'WRONG_PRICE',
    'DUPLICATE',
    'OTHER',
]


# =============================================================================
# DATA CLASSES
# =============================================================================

@dataclass
class OperationResult:
    """Result of a single order operation."""
    order_id: str
    success: bool
    old_status: Optional[str] = None
    new_status: Optional[str] = None
    error: Optional[str] = None


@dataclass
class BulkOperationResult:
    """Result of a bulk order operation."""
    operation: str
    total: int = 0
    success_count: int = 0
    failed_count: int = 0
    skipped_count: int = 0
    results: list = field(default_factory=list)
    errors: list = field(default_factory=list)
    confirmation_sent: bool = False
    confirmed: bool = False


# =============================================================================
# ORDER STATUS MANAGER
# =============================================================================

class OrderStatusManager:
    """
    Manages order status transitions via Kaspi API.

    Args:
        store_code: Store identifier (UNIVERSAL, ACMEWEAR, etc.)
        db_path: Path to SQLite database
        require_confirmation: Require Telegram confirmation for bulk ops

    Attributes:
        client: KaspiAPIClient instance
        writes_enabled: Whether write operations are allowed
    """

    def __init__(
        self,
        store_code: str,
        db_path: str = None,
        require_confirmation: bool = True,
    ):
        self.store_code = store_code.upper()
        self.db_path = db_path or DB_PATH
        self.require_confirmation = require_confirmation
        self.client = get_client(store_code)
        self.writes_enabled = self.client.writes_enabled

        logger.info(
            f"OrderStatusManager initialized for {self.store_code}, "
            f"writes_enabled={self.writes_enabled}"
        )

    # =========================================================================
    # SINGLE ORDER OPERATIONS
    # =========================================================================

    def accept_order(self, order_id: str, dry_run: bool = False) -> OperationResult:
        """
        Accept a single order (NEW -> ACCEPTED_BY_MERCHANT).

        Args:
            order_id: Kaspi order code
            dry_run: If True, validate but don't execute

        Returns:
            OperationResult with success status
        """
        result = OperationResult(order_id=order_id, success=False)

        # Verify order exists and is in correct state
        order = self._get_order_from_db(order_id)
        if not order:
            result.error = f"Order {order_id} not found in database"
            return result

        result.old_status = order.get('internal_status')

        if order.get('internal_status') != 'NEW':
            result.error = f"Order not in NEW status (current: {order.get('internal_status')})"
            return result

        if dry_run:
            result.success = True
            result.new_status = 'ACCEPTED'
            logger.info(f"[DRY RUN] Would accept order {order_id}")
            return result

        # Execute API call
        try:
            response = self.client.accept_order(order_id)
            if response.success:
                result.success = True
                result.new_status = 'ACCEPTED'
                self._update_order_status(order_id, 'ACCEPTED', 'ACCEPTED_BY_MERCHANT')
                logger.info(f"Accepted order {order_id}")
            else:
                result.error = response.error
                logger.error(f"Failed to accept order {order_id}: {response.error}")
        except KaspiWriteDisabledError:
            result.error = "Write operations disabled (ENABLE_KASPI_WRITE=0)"
        except KaspiAPIError as e:
            result.error = str(e)
            logger.error(f"API error accepting order {order_id}: {e}")

        return result

    def assemble_order(
        self,
        order_id: str,
        parcel_count: int = 1,
        dry_run: bool = False,
    ) -> OperationResult:
        """
        Mark order as assembled (ACCEPTED -> ASSEMBLY).

        Args:
            order_id: Kaspi order code
            parcel_count: Number of parcels (default 1)
            dry_run: If True, validate but don't execute

        Returns:
            OperationResult with success status
        """
        result = OperationResult(order_id=order_id, success=False)

        order = self._get_order_from_db(order_id)
        if not order:
            result.error = f"Order {order_id} not found in database"
            return result

        result.old_status = order.get('internal_status')

        if order.get('internal_status') not in ('ACCEPTED', 'NEW'):
            result.error = (
                f"Order not in ACCEPTED status "
                f"(current: {order.get('internal_status')})"
            )
            return result

        if dry_run:
            result.success = True
            result.new_status = 'READY'
            logger.info(f"[DRY RUN] Would assemble order {order_id}")
            return result

        try:
            response = self.client.assemble_order(order_id, parcel_count=parcel_count)
            if response.success:
                result.success = True
                result.new_status = 'READY'
                self._update_order_status(order_id, 'READY', 'ASSEMBLY')
                logger.info(f"Assembled order {order_id}")
            else:
                result.error = response.error
        except KaspiWriteDisabledError:
            result.error = "Write operations disabled (ENABLE_KASPI_WRITE=0)"
        except KaspiAPIError as e:
            result.error = str(e)

        return result

    def ship_order(self, order_id: str, dry_run: bool = False) -> OperationResult:
        """
        Ship order (hand to Kaspi delivery).

        Args:
            order_id: Kaspi order code
            dry_run: If True, validate but don't execute

        Returns:
            OperationResult with success status
        """
        result = OperationResult(order_id=order_id, success=False)

        order = self._get_order_from_db(order_id)
        if not order:
            result.error = f"Order {order_id} not found in database"
            return result

        result.old_status = order.get('internal_status')

        if order.get('internal_status') != 'READY':
            result.error = (
                f"Order not in READY status "
                f"(current: {order.get('internal_status')})"
            )
            return result

        if dry_run:
            result.success = True
            result.new_status = 'SHIPPED'
            logger.info(f"[DRY RUN] Would ship order {order_id}")
            return result

        try:
            response = self.client.ship_order(order_id)
            if response.success:
                result.success = True
                result.new_status = 'SHIPPED'
                self._update_order_status(order_id, 'SHIPPED', 'KASPI_DELIVERY')
                logger.info(f"Shipped order {order_id}")
            else:
                result.error = response.error
        except KaspiWriteDisabledError:
            result.error = "Write operations disabled (ENABLE_KASPI_WRITE=0)"
        except KaspiAPIError as e:
            result.error = str(e)

        return result

    def cancel_order(
        self,
        order_id: str,
        reason: str = 'OUT_OF_STOCK',
        dry_run: bool = False,
    ) -> OperationResult:
        """
        Cancel order with reason.

        Args:
            order_id: Kaspi order code
            reason: Cancellation reason (OUT_OF_STOCK, CUSTOMER_REQUEST, etc.)
            dry_run: If True, validate but don't execute

        Returns:
            OperationResult with success status
        """
        result = OperationResult(order_id=order_id, success=False)

        if reason not in CANCEL_REASONS:
            result.error = f"Invalid cancel reason: {reason}. Valid: {CANCEL_REASONS}"
            return result

        order = self._get_order_from_db(order_id)
        if not order:
            result.error = f"Order {order_id} not found in database"
            return result

        result.old_status = order.get('internal_status')

        if order.get('internal_status') in ('SHIPPED', 'COMPLETED', 'CANCELLED'):
            result.error = (
                f"Order cannot be cancelled "
                f"(current: {order.get('internal_status')})"
            )
            return result

        if dry_run:
            result.success = True
            result.new_status = 'CANCELLED'
            logger.info(f"[DRY RUN] Would cancel order {order_id} ({reason})")
            return result

        try:
            response = self.client.cancel_order(order_id, reason=reason)
            if response.success:
                result.success = True
                result.new_status = 'CANCELLED'
                self._update_order_status(order_id, 'CANCELLED', 'CANCELLED')
                logger.warning(f"Cancelled order {order_id} (reason: {reason})")
            else:
                result.error = response.error
        except KaspiWriteDisabledError:
            result.error = "Write operations disabled (ENABLE_KASPI_WRITE=0)"
        except KaspiAPIError as e:
            result.error = str(e)

        return result

    # =========================================================================
    # BULK OPERATIONS
    # =========================================================================

    def accept_ready_orders(
        self,
        confirm: bool = False,
        dry_run: bool = False,
    ) -> BulkOperationResult:
        """
        Accept all NEW orders that are ready.

        Args:
            confirm: If True, proceed without Telegram confirmation
            dry_run: If True, validate but don't execute

        Returns:
            BulkOperationResult with success/fail counts
        """
        result = BulkOperationResult(operation='accept')

        # Get NEW orders
        orders = self._get_orders_by_status('NEW')
        result.total = len(orders)

        if result.total == 0:
            logger.info("No NEW orders to accept")
            return result

        # Check if confirmation required for bulk ops
        if result.total >= BULK_THRESHOLD and self.require_confirmation and not confirm:
            self._send_confirmation_request(result.total, 'accept')
            result.confirmation_sent = True
            logger.info(
                f"Confirmation required for {result.total} orders. "
                f"Use confirm=True to proceed."
            )
            return result

        result.confirmed = True

        # Process each order
        for order in orders:
            order_id = order['order_id']
            op_result = self.accept_order(order_id, dry_run=dry_run)
            result.results.append(op_result)

            if op_result.success:
                result.success_count += 1
            else:
                result.failed_count += 1
                result.errors.append(f"{order_id}: {op_result.error}")

        if not dry_run and result.success_count > 0:
            self._send_bulk_notification('accept', result)

        return result

    def assemble_ready_orders(
        self,
        confirm: bool = False,
        dry_run: bool = False,
    ) -> BulkOperationResult:
        """
        Mark all ACCEPTED orders as assembled.

        Args:
            confirm: If True, proceed without Telegram confirmation
            dry_run: If True, validate but don't execute

        Returns:
            BulkOperationResult with success/fail counts
        """
        result = BulkOperationResult(operation='assemble')

        orders = self._get_orders_by_status('ACCEPTED')
        result.total = len(orders)

        if result.total == 0:
            logger.info("No ACCEPTED orders to assemble")
            return result

        if result.total >= BULK_THRESHOLD and self.require_confirmation and not confirm:
            self._send_confirmation_request(result.total, 'assemble')
            result.confirmation_sent = True
            return result

        result.confirmed = True

        for order in orders:
            order_id = order['order_id']
            op_result = self.assemble_order(order_id, dry_run=dry_run)
            result.results.append(op_result)

            if op_result.success:
                result.success_count += 1
            else:
                result.failed_count += 1
                result.errors.append(f"{order_id}: {op_result.error}")

        if not dry_run and result.success_count > 0:
            self._send_bulk_notification('assemble', result)

        return result

    def ship_ready_orders(
        self,
        confirm: bool = False,
        dry_run: bool = False,
    ) -> BulkOperationResult:
        """
        Ship all READY orders with waybills.

        Args:
            confirm: If True, proceed without Telegram confirmation
            dry_run: If True, validate but don't execute

        Returns:
            BulkOperationResult with success/fail counts
        """
        result = BulkOperationResult(operation='ship')

        orders = self._get_orders_by_status('READY', require_waybill=True)
        result.total = len(orders)

        if result.total == 0:
            logger.info("No READY orders with waybills to ship")
            return result

        if result.total >= BULK_THRESHOLD and self.require_confirmation and not confirm:
            self._send_confirmation_request(result.total, 'ship')
            result.confirmation_sent = True
            return result

        result.confirmed = True

        for order in orders:
            order_id = order['order_id']
            op_result = self.ship_order(order_id, dry_run=dry_run)
            result.results.append(op_result)

            if op_result.success:
                result.success_count += 1
            else:
                result.failed_count += 1
                result.errors.append(f"{order_id}: {op_result.error}")

        if not dry_run and result.success_count > 0:
            self._send_bulk_notification('ship', result)

        return result

    # =========================================================================
    # DATABASE HELPERS
    # =========================================================================

    def _get_order_from_db(self, order_id: str) -> Optional[dict]:
        """Get single order from database."""
        with get_db(self.db_path) as conn:
            row = conn.execute(
                """
                SELECT * FROM fact_orders_kaspi
                WHERE order_id = ? AND store_code = ?
                """,
                (order_id, self.store_code)
            ).fetchone()
            return dict(row) if row else None

    def _get_orders_by_status(
        self,
        status: str,
        require_waybill: bool = False,
    ) -> list[dict]:
        """Get orders by internal status."""
        with get_db(self.db_path) as conn:
            query = """
                SELECT * FROM fact_orders_kaspi
                WHERE internal_status = ? AND store_code = ?
            """
            params = [status, self.store_code]

            if require_waybill:
                query += " AND waybill_url IS NOT NULL"

            query += " ORDER BY created_at ASC"

            rows = conn.execute(query, params).fetchall()
            return [dict(row) for row in rows]

    def _update_order_status(
        self,
        order_id: str,
        internal_status: str,
        kaspi_status: str,
    ):
        """Update order status in database."""
        with get_db(self.db_path) as conn:
            conn.execute(
                """
                UPDATE fact_orders_kaspi SET
                    internal_status = ?,
                    kaspi_status = ?,
                    status_updated_at = CURRENT_TIMESTAMP
                WHERE order_id = ? AND store_code = ?
                """,
                (internal_status, kaspi_status, order_id, self.store_code)
            )

    # =========================================================================
    # TELEGRAM HELPERS
    # =========================================================================

    def _send_confirmation_request(self, count: int, operation: str):
        """Send Telegram confirmation request for bulk operation."""
        try:
            config = get_telegram_config()
            message = f"""<b>CONFIRMATION REQUIRED</b>

<b>Store:</b> {self.store_code}
<b>Operation:</b> {operation.upper()}
<b>Orders:</b> {count}

Run with <code>--confirm</code> to proceed."""

            send_message(
                chat_id=config['chat_id'],
                message=message,
                token=config['token'],
            )
        except (ValueError, Exception) as e:
            logger.warning(f"Failed to send Telegram confirmation: {e}")

    def _send_bulk_notification(self, operation: str, result: BulkOperationResult):
        """Send Telegram notification after bulk operation."""
        try:
            config = get_telegram_config()

            status_emoji = "" if result.failed_count == 0 else ""
            message = f"""<b>{status_emoji} BULK {operation.upper()} COMPLETE</b>

<b>Store:</b> {self.store_code}
<b>Total:</b> {result.total}
<b>Success:</b> {result.success_count}
<b>Failed:</b> {result.failed_count}"""

            if result.errors[:3]:  # Show first 3 errors
                message += "\n\n<b>Errors:</b>"
                for err in result.errors[:3]:
                    message += f"\n- {err}"

            send_message(
                chat_id=config['chat_id'],
                message=message,
                token=config['token'],
            )
        except (ValueError, Exception) as e:
            logger.warning(f"Failed to send Telegram notification: {e}")

    # =========================================================================
    # STATUS QUERIES
    # =========================================================================

    def get_status_summary(self) -> dict:
        """Get summary of orders by status."""
        with get_db(self.db_path) as conn:
            rows = conn.execute(
                """
                SELECT internal_status, COUNT(*) as count
                FROM fact_orders_kaspi
                WHERE store_code = ?
                GROUP BY internal_status
                ORDER BY internal_status
                """,
                (self.store_code,)
            ).fetchall()

            return {row['internal_status']: row['count'] for row in rows}

    def get_pending_actions(self) -> dict:
        """Get counts of orders pending each action."""
        summary = self.get_status_summary()

        with get_db(self.db_path) as conn:
            ready_with_waybill = conn.execute(
                """
                SELECT COUNT(*) as count FROM fact_orders_kaspi
                WHERE store_code = ? AND internal_status = 'READY'
                  AND waybill_url IS NOT NULL
                """,
                (self.store_code,)
            ).fetchone()['count']

        return {
            'to_accept': summary.get('NEW', 0),
            'to_assemble': summary.get('ACCEPTED', 0),
            'to_ship': ready_with_waybill,
            'ready_no_waybill': summary.get('READY', 0) - ready_with_waybill,
        }


# =============================================================================
# FACTORY FUNCTION
# =============================================================================

def get_manager(store_code: str, **kwargs) -> OrderStatusManager:
    """Factory function to get OrderStatusManager for a store."""
    return OrderStatusManager(store_code=store_code, **kwargs)


# =============================================================================
# CLI TEST
# =============================================================================

if __name__ == "__main__":
    import sys
    from dotenv import load_dotenv

    load_dotenv()
    logging.basicConfig(level=logging.INFO)

    store = sys.argv[1] if len(sys.argv) > 1 else 'UNIVERSAL'

    print("=" * 60)
    print(f"Order Status Manager Test - {store}")
    print("=" * 60)

    manager = OrderStatusManager(store_code=store)

    print(f"\nWrites enabled: {manager.writes_enabled}")

    print("\nStatus summary:")
    summary = manager.get_status_summary()
    for status, count in summary.items():
        print(f"  {status}: {count}")

    print("\nPending actions:")
    pending = manager.get_pending_actions()
    print(f"  To accept: {pending['to_accept']}")
    print(f"  To assemble: {pending['to_assemble']}")
    print(f"  To ship: {pending['to_ship']}")
    print(f"  Ready (no waybill): {pending['ready_no_waybill']}")

    print("\n" + "=" * 60)
    print("Test complete!")
    print("=" * 60)
