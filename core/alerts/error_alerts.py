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
from pathlib import Path

from .telegram import get_telegram_config, send_message


# Error alert chat ID (Adil's direct chat for urgent notifications)
ERROR_ALERT_CHAT_ID = "687884487"


def _telegram_env_ready() -> tuple[bool, str]:
    """Check whether required Telegram env vars exist."""
    missing = []
    if not os.environ.get("TELEGRAM_BOT_TOKEN"):
        missing.append("TELEGRAM_BOT_TOKEN")
    if not os.environ.get("TELEGRAM_CHAT_ID"):
        missing.append("TELEGRAM_CHAT_ID")
    if missing:
        return False, f"Telegram env missing: {', '.join(missing)}"
    return True, ""


def _format_duration(seconds: float) -> str:
    minutes = int(seconds // 60)
    secs = int(seconds % 60)
    if minutes <= 0:
        return f"{secs}s"
    return f"{minutes}m {secs}s"


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


def alert_from_run_tracker(tracker) -> bool:
    """
    Send a run summary alert based on RunTracker status.

    Uses existing send_success_alert/send_error_alert and is fail-safe
    when Telegram env vars are missing.
    """
    ready, reason = _telegram_env_ready()
    if not ready:
        print(f"Telegram alert skipped: {reason}")
        return False

    summary = tracker.to_summary() if hasattr(tracker, "to_summary") else {}
    status = summary.get("status") or getattr(tracker, "status", "UNKNOWN")
    run_id = summary.get("run_id") or getattr(tracker, "run_id", None)
    run_type = summary.get("run_type") or getattr(tracker, "run_type", "RUN")
    duration_seconds = summary.get("duration_seconds", 0)
    steps_total = summary.get("steps_total", 0)
    steps_completed = summary.get("steps_completed", 0)

    failed_steps = []
    if getattr(tracker, "steps", None):
        for step in tracker.steps:
            if getattr(step, "status", "").upper() == "FAILED":
                failed_steps.append(step.name)

    duration_str = _format_duration(duration_seconds)

    if status.upper() in {"FAILED", "PARTIAL"}:
        error_lines = [
            f"Run ID: {run_id}",
            f"Status: {status}",
            f"Duration: {duration_str}",
            f"Steps: {steps_completed}/{steps_total}",
        ]
        if failed_steps:
            error_lines.append(f"Failed steps: {', '.join(failed_steps)}")
        error_summary = summary.get("error_summary") or getattr(tracker, "error_summary", [])
        if error_summary:
            error_lines.append("Errors:")
            error_lines.extend(str(e) for e in error_summary)
        error_message = "\n".join(error_lines)
        return send_error_alert(
            error_message=error_message,
            script_name="run_end_of_day",
            context=f"Run type: {run_type}",
        )

    message = (
        f"<b>Run #{run_id} complete</b>\n"
        f"<b>Status:</b> {status}\n"
        f"<b>Duration:</b> {duration_str}\n"
        f"<b>Steps:</b> {steps_completed}/{steps_total}"
    )
    stats = {
        "run_type": run_type,
        "errors": summary.get("errors_count", 0),
    }
    return send_success_alert(message, "run_end_of_day", stats=stats)


def send_shadow_mode_digest(
    run_id: Optional[int],
    duration_seconds: float,
    db_path: str,
) -> bool:
    """
    Send a concise Shadow Mode digest to Telegram.

    Returns True if sent successfully, False otherwise.
    """
    ready, reason = _telegram_env_ready()
    if not ready:
        print(f"Telegram digest skipped: {reason}")
        return False

    config = get_telegram_config()
    chat_id = config["chat_id"]

    duration_str = _format_duration(duration_seconds)
    scorecard_path = None
    try:
        root = Path(db_path).resolve().parent.parent
        candidate = root / "exports" / f"shadow_scorecard_{datetime.now().date().isoformat()}.csv"
        if candidate.exists():
            scorecard_path = str(candidate)
    except Exception:
        scorecard_path = None

    message = [
        "<b>Shadow Mode Digest</b>",
        f"<b>Run ID:</b> {run_id}",
        f"<b>Duration:</b> {duration_str}",
    ]
    if scorecard_path:
        message.append(f"<b>Scorecard:</b> {scorecard_path}")

    result = send_message(chat_id, "\n".join(message), config["token"])
    return result.get("success", False)
