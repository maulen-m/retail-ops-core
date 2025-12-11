"""
Phase 12: Error Alert Notifications

Sends error alerts to Telegram when automated tasks fail.
Uses the same Telegram infrastructure as REORDER alerts.

Usage:
    from core.alerts.error_alerts import send_error_alert

    try:
        # ... operation that might fail
    except Exception as e:
        send_error_alert(str(e), "import_orders_to_crm")
"""

import os
from datetime import datetime
from typing import Optional

from .telegram import get_telegram_config, send_message


# Error alert chat ID (Adil's direct chat for urgent notifications)
ERROR_ALERT_CHAT_ID = "687884487"


def send_error_alert(
    error_message: str,
    script_name: str,
    context: Optional[str] = None,
    use_env_chat: bool = False,
) -> bool:
    """
    Send error alert to Telegram.

    Args:
        error_message: The error message/description
        script_name: Name of the script that failed
        context: Optional additional context
        use_env_chat: If True, use TELEGRAM_CHAT_ID from env instead of hardcoded

    Returns:
        True if alert sent successfully, False otherwise
    """
    try:
        config = get_telegram_config()

        # Use hardcoded error chat ID unless overridden
        chat_id = os.environ.get("TELEGRAM_CHAT_ID", ERROR_ALERT_CHAT_ID) if use_env_chat else ERROR_ALERT_CHAT_ID

        # Format error message
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        message = f"""<b>⚠️ ERROR ALERT</b>

<b>Script:</b> <code>{script_name}</code>
<b>Time:</b> {timestamp}

<b>Error:</b>
<pre>{error_message[:500]}</pre>"""

        if context:
            message += f"""

<b>Context:</b>
<pre>{context[:300]}</pre>"""

        message += """

<i>Check logs for details</i>"""

        result = send_message(chat_id, message, config["token"])
        return result.get("success", False)

    except Exception as e:
        # Don't let alert failures break the main flow
        print(f"Failed to send error alert: {e}")
        return False


def send_success_alert(
    message: str,
    script_name: str,
    stats: Optional[dict] = None,
) -> bool:
    """
    Send success notification to Telegram.

    Args:
        message: Success message
        script_name: Name of the script that completed
        stats: Optional stats dict to include

    Returns:
        True if alert sent successfully, False otherwise
    """
    try:
        config = get_telegram_config()
        chat_id = ERROR_ALERT_CHAT_ID

        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        text = f"""<b>✅ Task Complete</b>

<b>Script:</b> <code>{script_name}</code>
<b>Time:</b> {timestamp}

{message}"""

        if stats:
            stats_text = "\n".join(f"  • {k}: {v}" for k, v in stats.items())
            text += f"""

<b>Stats:</b>
{stats_text}"""

        result = send_message(chat_id, text, config["token"])
        return result.get("success", False)

    except Exception:
        return False


def alert_import_failed(error: Exception, orders_count: int = 0) -> bool:
    """Convenience function for import failures."""
    return send_error_alert(
        error_message=str(error),
        script_name="import_orders_to_crm",
        context=f"Attempted to import {orders_count} orders",
    )


def alert_export_failed(error: Exception, store: str = "unknown") -> bool:
    """Convenience function for export failures."""
    return send_error_alert(
        error_message=str(error),
        script_name="export_api_orders",
        context=f"Store: {store}",
    )
