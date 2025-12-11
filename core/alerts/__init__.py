"""
Alerts module for sending notifications via various channels.

Supports:
- Telegram (REORDER alerts, order alerts, error alerts)
- Future: WhatsApp, Slack, Email
"""

from .telegram import (
    send_message,
    format_reorder_alert,
    check_cooldown,
    log_alert,
    send_reorder_alerts,
)
from .order_alerts import (
    alert_new_orders,
    alert_status_changes,
    alert_shipment_ready,
    alert_deadline_warning,
    send_all_order_alerts,
)
from .error_alerts import (
    send_error_alert,
    send_success_alert,
    alert_import_failed,
    alert_export_failed,
)

__all__ = [
    # Telegram base
    "send_message",
    "format_reorder_alert",
    "check_cooldown",
    "log_alert",
    "send_reorder_alerts",
    # Order alerts
    "alert_new_orders",
    "alert_status_changes",
    "alert_shipment_ready",
    "alert_deadline_warning",
    "send_all_order_alerts",
    # Error alerts (Phase 12)
    "send_error_alert",
    "send_success_alert",
    "alert_import_failed",
    "alert_export_failed",
]
