"""
Order alerting for Kaspi order lifecycle (Phase 9.5).

Provides Telegram alerts for:
- New orders received
- Order status changes
- Orders ready for shipment
- Shipment deadlines approaching

Uses the same Telegram infrastructure as reorder alerts.

Usage:
    from core.alerts.order_alerts import (
        alert_new_orders,
        alert_status_changes,
        alert_shipment_ready,
    )

    # Alert on new orders
    alert_new_orders(conn, store_code='UNIVERSAL')

    # Alert on status changes
    alert_status_changes(conn, status_changes)
"""

import logging
from datetime import datetime, timedelta
from typing import Optional

from core.alerts.telegram import (
    send_message,
    get_telegram_config,
    log_alert,
    create_alert_log_table,
    check_cooldown,
)
from core.db import get_db


logger = logging.getLogger(__name__)


# =============================================================================
# CONSTANTS
# =============================================================================

# Alert cooldown in hours
NEW_ORDER_COOLDOWN_HOURS = 1
STATUS_CHANGE_COOLDOWN_HOURS = 4
SHIPMENT_DEADLINE_COOLDOWN_HOURS = 12

# Urgent shipment window (hours before planned delivery)
URGENT_SHIPMENT_HOURS = 24


# =============================================================================
# ALERT FORMATTERS
# =============================================================================

def format_new_orders_alert(orders: list[dict], store_code: str) -> str:
    """
    Format alert for new orders.

    Args:
        orders: List of order dicts
        store_code: Store code

    Returns:
        Formatted HTML message
    """
    count = len(orders)
    total_value = sum(o.get('unit_price_kzt', 0) for o in orders)

    message = f"""<b>NEW ORDERS</b>

<b>Store:</b> {store_code}
<b>New Orders:</b> {count}
<b>Total Value:</b> {total_value:,.0f} KZT

"""

    # List first 5 orders
    for order in orders[:5]:
        order_id = order.get('order_id', 'Unknown')
        price = order.get('unit_price_kzt', 0)
        message += f"- <code>{order_id}</code>: {price:,.0f} KZT\n"

    if count > 5:
        message += f"\n<i>...and {count - 5} more</i>\n"

    message += "\n<i>Action: Review and accept orders</i>"

    return message


def format_status_change_alert(changes: list, store_code: str) -> str:
    """
    Format alert for order status changes.

    Args:
        changes: List of StatusChange objects
        store_code: Store code

    Returns:
        Formatted HTML message
    """
    count = len(changes)

    message = f"""<b>ORDER STATUS CHANGES</b>

<b>Store:</b> {store_code}
<b>Changes:</b> {count}

"""

    # Group by status transition
    transitions = {}
    for change in changes:
        key = f"{change.old_status} -> {change.new_status}"
        if key not in transitions:
            transitions[key] = []
        transitions[key].append(change.order_id)

    for transition, order_ids in transitions.items():
        message += f"<b>{transition}:</b> {len(order_ids)}\n"
        for oid in order_ids[:3]:
            message += f"  - <code>{oid}</code>\n"
        if len(order_ids) > 3:
            message += f"  <i>...and {len(order_ids) - 3} more</i>\n"

    return message


def format_shipment_ready_alert(orders: list[dict], store_code: str) -> str:
    """
    Format alert for orders ready for shipment.

    Args:
        orders: List of order dicts ready to ship
        store_code: Store code

    Returns:
        Formatted HTML message
    """
    count = len(orders)

    # Count urgent orders (deadline within 24h)
    urgent_count = 0
    for order in orders:
        if order.get('planned_shipment_date'):
            deadline = datetime.strptime(order['planned_shipment_date'], '%Y-%m-%d')
            if deadline <= datetime.now() + timedelta(hours=URGENT_SHIPMENT_HOURS):
                urgent_count += 1

    urgent_emoji = "" if urgent_count > 0 else ""

    message = f"""<b>{urgent_emoji} SHIPMENT READY</b>

<b>Store:</b> {store_code}
<b>Ready to Ship:</b> {count}
<b>Urgent (<24h):</b> {urgent_count}

"""

    # List urgent orders first
    urgent_orders = []
    regular_orders = []

    for order in orders:
        if order.get('planned_shipment_date'):
            deadline = datetime.strptime(order['planned_shipment_date'], '%Y-%m-%d')
            if deadline <= datetime.now() + timedelta(hours=URGENT_SHIPMENT_HOURS):
                urgent_orders.append(order)
            else:
                regular_orders.append(order)
        else:
            regular_orders.append(order)

    if urgent_orders:
        message += "<b>URGENT:</b>\n"
        for order in urgent_orders[:5]:
            message += f"- <code>{order['order_id']}</code> ({order.get('planned_shipment_date', 'N/A')})\n"

    if regular_orders:
        message += "\n<b>Regular:</b>\n"
        for order in regular_orders[:5]:
            message += f"- <code>{order['order_id']}</code>\n"

    if len(orders) > 10:
        message += f"\n<i>...and {len(orders) - 10} more</i>\n"

    message += "\n<i>Action: Ship these orders today</i>"

    return message


def format_deadline_alert(orders: list[dict], store_code: str) -> str:
    """
    Format alert for approaching shipment deadlines.

    Args:
        orders: List of orders with approaching deadlines
        store_code: Store code

    Returns:
        Formatted HTML message
    """
    message = f"""<b> SHIPMENT DEADLINE WARNING</b>

<b>Store:</b> {store_code}
<b>Orders at risk:</b> {len(orders)}

"""

    for order in orders[:10]:
        order_id = order.get('order_id', 'Unknown')
        deadline = order.get('planned_shipment_date', 'Unknown')
        status = order.get('internal_status', 'Unknown')
        message += f"- <code>{order_id}</code>: {deadline} ({status})\n"

    message += "\n<b>Immediate action required!</b>"

    return message


# =============================================================================
# ALERT FUNCTIONS
# =============================================================================

def alert_new_orders(
    conn,
    store_code: str,
    dry_run: bool = False,
    cooldown_hours: int = NEW_ORDER_COOLDOWN_HOURS,
) -> dict:
    """
    Send alert for new orders in the database.

    Args:
        conn: Database connection
        store_code: Store code
        dry_run: If True, format but don't send
        cooldown_hours: Hours between alerts

    Returns:
        Dict with sent status and message
    """
    create_alert_log_table(conn)

    # Get NEW orders
    rows = conn.execute(
        """
        SELECT order_id, internal_status, unit_price_kzt, created_at
        FROM fact_orders_kaspi
        WHERE store_code = ? AND internal_status = 'NEW'
        ORDER BY created_at DESC
        """,
        (store_code,)
    ).fetchall()

    orders = [dict(r) for r in rows]

    if not orders:
        return {
            'sent': False,
            'note': 'No new orders',
        }

    # Check cooldown
    should_send, reason = check_cooldown(
        conn, 'NEW_ORDERS', store_code, cooldown_hours
    )

    if not should_send and not dry_run:
        return {
            'sent': False,
            'suppressed': True,
            'reason': reason,
            'order_count': len(orders),
        }

    # Format message
    message = format_new_orders_alert(orders, store_code)

    if dry_run:
        return {
            'sent': False,
            'dry_run': True,
            'message': message,
            'order_count': len(orders),
        }

    # Send message
    try:
        config = get_telegram_config()
        response = send_message(
            chat_id=config['chat_id'],
            message=message,
            token=config['token'],
        )

        if response['success']:
            log_alert(
                conn, 'NEW_ORDERS', store_code,
                alert_type='NEW_ORDERS',
                channel='telegram',
                message=message,
                status='SENT',
                external_id=response.get('message_id'),
            )
            return {
                'sent': True,
                'order_count': len(orders),
            }
        else:
            return {
                'sent': False,
                'error': response.get('error'),
            }

    except ValueError as e:
        return {
            'sent': False,
            'error': str(e),
        }


def alert_status_changes(
    conn,
    status_changes: list,
    store_code: str,
    dry_run: bool = False,
) -> dict:
    """
    Send alert for order status changes.

    Args:
        conn: Database connection
        status_changes: List of StatusChange objects
        store_code: Store code
        dry_run: If True, format but don't send

    Returns:
        Dict with sent status and message
    """
    if not status_changes:
        return {
            'sent': False,
            'note': 'No status changes',
        }

    create_alert_log_table(conn)

    # Check cooldown
    should_send, reason = check_cooldown(
        conn, 'STATUS_CHANGES', store_code, STATUS_CHANGE_COOLDOWN_HOURS
    )

    if not should_send and not dry_run:
        return {
            'sent': False,
            'suppressed': True,
            'reason': reason,
        }

    message = format_status_change_alert(status_changes, store_code)

    if dry_run:
        return {
            'sent': False,
            'dry_run': True,
            'message': message,
            'change_count': len(status_changes),
        }

    try:
        config = get_telegram_config()
        response = send_message(
            chat_id=config['chat_id'],
            message=message,
            token=config['token'],
        )

        if response['success']:
            log_alert(
                conn, 'STATUS_CHANGES', store_code,
                alert_type='STATUS_CHANGES',
                channel='telegram',
                message=message,
                status='SENT',
                external_id=response.get('message_id'),
            )
            return {
                'sent': True,
                'change_count': len(status_changes),
            }
        else:
            return {
                'sent': False,
                'error': response.get('error'),
            }

    except ValueError as e:
        return {
            'sent': False,
            'error': str(e),
        }


def alert_shipment_ready(
    conn,
    store_code: str,
    dry_run: bool = False,
    cooldown_hours: int = STATUS_CHANGE_COOLDOWN_HOURS,
) -> dict:
    """
    Send alert for orders ready for shipment.

    Args:
        conn: Database connection
        store_code: Store code
        dry_run: If True, format but don't send
        cooldown_hours: Hours between alerts

    Returns:
        Dict with sent status
    """
    create_alert_log_table(conn)

    # Get READY orders with waybills
    rows = conn.execute(
        """
        SELECT order_id, internal_status, unit_price_kzt,
               planned_shipment_date, waybill_url
        FROM fact_orders_kaspi
        WHERE store_code = ?
          AND internal_status = 'READY'
          AND waybill_url IS NOT NULL
        ORDER BY planned_shipment_date ASC
        """,
        (store_code,)
    ).fetchall()

    orders = [dict(r) for r in rows]

    if not orders:
        return {
            'sent': False,
            'note': 'No orders ready for shipment',
        }

    # Check cooldown
    should_send, reason = check_cooldown(
        conn, 'SHIPMENT_READY', store_code, cooldown_hours
    )

    if not should_send and not dry_run:
        return {
            'sent': False,
            'suppressed': True,
            'reason': reason,
            'order_count': len(orders),
        }

    message = format_shipment_ready_alert(orders, store_code)

    if dry_run:
        return {
            'sent': False,
            'dry_run': True,
            'message': message,
            'order_count': len(orders),
        }

    try:
        config = get_telegram_config()
        response = send_message(
            chat_id=config['chat_id'],
            message=message,
            token=config['token'],
        )

        if response['success']:
            log_alert(
                conn, 'SHIPMENT_READY', store_code,
                alert_type='SHIPMENT_READY',
                channel='telegram',
                message=message,
                status='SENT',
                external_id=response.get('message_id'),
            )
            return {
                'sent': True,
                'order_count': len(orders),
            }
        else:
            return {
                'sent': False,
                'error': response.get('error'),
            }

    except ValueError as e:
        return {
            'sent': False,
            'error': str(e),
        }


def alert_deadline_warning(
    conn,
    store_code: str,
    hours_threshold: int = URGENT_SHIPMENT_HOURS,
    dry_run: bool = False,
) -> dict:
    """
    Send alert for orders approaching shipment deadlines.

    Args:
        conn: Database connection
        store_code: Store code
        hours_threshold: Hours before deadline to warn
        dry_run: If True, format but don't send

    Returns:
        Dict with sent status
    """
    create_alert_log_table(conn)

    # Calculate deadline cutoff
    deadline_cutoff = (datetime.now() + timedelta(hours=hours_threshold)).strftime('%Y-%m-%d')

    # Get orders with approaching deadlines (not yet shipped)
    rows = conn.execute(
        """
        SELECT order_id, internal_status, unit_price_kzt,
               planned_shipment_date
        FROM fact_orders_kaspi
        WHERE store_code = ?
          AND internal_status IN ('NEW', 'ACCEPTED', 'READY')
          AND planned_shipment_date IS NOT NULL
          AND planned_shipment_date <= ?
        ORDER BY planned_shipment_date ASC
        """,
        (store_code, deadline_cutoff)
    ).fetchall()

    orders = [dict(r) for r in rows]

    if not orders:
        return {
            'sent': False,
            'note': 'No orders approaching deadline',
        }

    # Check cooldown
    should_send, reason = check_cooldown(
        conn, 'DEADLINE_WARNING', store_code, SHIPMENT_DEADLINE_COOLDOWN_HOURS
    )

    if not should_send and not dry_run:
        return {
            'sent': False,
            'suppressed': True,
            'reason': reason,
            'order_count': len(orders),
        }

    message = format_deadline_alert(orders, store_code)

    if dry_run:
        return {
            'sent': False,
            'dry_run': True,
            'message': message,
            'order_count': len(orders),
        }

    try:
        config = get_telegram_config()
        response = send_message(
            chat_id=config['chat_id'],
            message=message,
            token=config['token'],
        )

        if response['success']:
            log_alert(
                conn, 'DEADLINE_WARNING', store_code,
                alert_type='DEADLINE_WARNING',
                channel='telegram',
                message=message,
                status='SENT',
                external_id=response.get('message_id'),
            )
            return {
                'sent': True,
                'order_count': len(orders),
            }
        else:
            return {
                'sent': False,
                'error': response.get('error'),
            }

    except ValueError as e:
        return {
            'sent': False,
            'error': str(e),
        }


def send_all_order_alerts(
    conn,
    store_code: str,
    dry_run: bool = False,
) -> dict:
    """
    Send all applicable order alerts for a store.

    Args:
        conn: Database connection
        store_code: Store code
        dry_run: If True, format but don't send

    Returns:
        Dict with results for each alert type
    """
    results = {
        'new_orders': alert_new_orders(conn, store_code, dry_run),
        'shipment_ready': alert_shipment_ready(conn, store_code, dry_run),
        'deadline_warning': alert_deadline_warning(conn, store_code, dry_run=dry_run),
    }

    sent_count = sum(1 for r in results.values() if r.get('sent'))
    suppressed_count = sum(1 for r in results.values() if r.get('suppressed'))

    return {
        'results': results,
        'sent_count': sent_count,
        'suppressed_count': suppressed_count,
    }
