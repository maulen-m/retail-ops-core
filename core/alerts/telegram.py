"""
Telegram alerting for REORDER status.

Uses Telegram Bot API to send alerts when SKUs hit REORDER status.
Implements 24-hour cooldown to avoid alert fatigue.

Environment variables required:
- TELEGRAM_BOT_TOKEN: Bot API token
- TELEGRAM_CHAT_ID: Chat ID to send alerts to
"""

import os
import requests
from datetime import datetime, timedelta
from typing import Optional


def get_telegram_config() -> dict:
    """
    Load Telegram config from environment variables.

    Returns dict with token and chat_id.
    Raises ValueError if required vars are missing.
    """
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")

    if not token:
        raise ValueError("TELEGRAM_BOT_TOKEN environment variable not set")
    if not chat_id:
        raise ValueError("TELEGRAM_CHAT_ID environment variable not set")

    return {
        "token": token,
        "chat_id": chat_id,
    }


def send_message(
    chat_id: str,
    message: str,
    token: str,
    parse_mode: str = "HTML",
) -> dict:
    """
    Send a single Telegram message.

    Args:
        chat_id: Telegram chat ID
        message: Message text (supports HTML formatting)
        token: Bot API token
        parse_mode: "HTML" or "Markdown"

    Returns:
        dict with success status and message_id or error
    """
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": message,
        "parse_mode": parse_mode,
    }

    try:
        response = requests.post(url, json=payload, timeout=10)
        data = response.json()

        if data.get("ok"):
            return {
                "success": True,
                "message_id": str(data["result"]["message_id"]),
            }
        else:
            return {
                "success": False,
                "error": data.get("description", "Unknown error"),
            }
    except requests.RequestException as e:
        return {
            "success": False,
            "error": str(e),
        }


def format_reorder_alert(sku_data: dict) -> str:
    """
    Format REORDER alert message with SKU details.

    Args:
        sku_data: Dict with sku_key, store_code, current_stock, rop,
                  suggested_order_qty, roic_monthly, d30, ss_total

    Returns:
        Formatted HTML message string
    """
    sku_key = sku_data.get("sku_key", "Unknown")
    store_code = sku_data.get("store_code", "ALL")
    current_stock = sku_data.get("current_stock", 0)
    rop = sku_data.get("rop", 0)
    suggested_qty = sku_data.get("suggested_order_qty", 0)
    roic = sku_data.get("roic_monthly", 0)
    d30 = sku_data.get("d30", 0)
    ss_total = sku_data.get("ss_total", 0)

    message = f"""<b>REORDER ALERT</b>

<b>SKU:</b> <code>{sku_key}</code>
<b>Store:</b> {store_code}

<b>Current Stock:</b> {current_stock:,} | <b>ROP:</b> {rop:,.0f}
<b>Suggested Order:</b> {suggested_qty:,} units
<b>ROIC:</b> {roic:.1f}%

<b>D30:</b> {d30:.1f} units/day
<b>SS:</b> {ss_total:.0f} units

<i>Action Required: Place PO</i>"""

    return message


def create_alert_log_table(conn):
    """Create fact_alert_log table if not exists."""
    conn.execute("""
        CREATE TABLE IF NOT EXISTS fact_alert_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            alert_date TEXT NOT NULL,
            alert_time TEXT NOT NULL,
            alert_type TEXT NOT NULL,
            channel TEXT NOT NULL,
            store_code TEXT NOT NULL,
            sku_key TEXT NOT NULL,
            message TEXT NOT NULL,
            status TEXT DEFAULT 'SENT',
            external_id TEXT,
            suppression_reason TEXT,
            created_at TEXT DEFAULT (datetime('now'))
        )
    """)
    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_alert_log_date ON fact_alert_log(alert_date)
    """)
    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_alert_log_sku
        ON fact_alert_log(sku_key, store_code, alert_date)
    """)
    conn.commit()


def check_cooldown(
    conn,
    sku_key: str,
    store_code: str,
    hours: int = 24,
) -> tuple[bool, Optional[str]]:
    """
    Check if alert was sent within cooldown period.

    Args:
        conn: Database connection
        sku_key: SKU key
        store_code: Store code
        hours: Cooldown period in hours

    Returns:
        Tuple of (should_send, reason_if_not)
    """
    cutoff = (datetime.now() - timedelta(hours=hours)).strftime("%Y-%m-%d %H:%M:%S")

    cursor = conn.execute(
        """
        SELECT alert_time, status FROM fact_alert_log
        WHERE sku_key = ? AND store_code = ? AND alert_time >= ? AND status = 'SENT'
        ORDER BY alert_time DESC
        LIMIT 1
        """,
        (sku_key, store_code, cutoff)
    )
    row = cursor.fetchone()

    if row:
        return False, f"Alert sent at {row[0]} (within {hours}h cooldown)"
    return True, None


def log_alert(
    conn,
    sku_key: str,
    store_code: str,
    alert_type: str,
    channel: str,
    message: str,
    status: str = "SENT",
    external_id: Optional[str] = None,
    suppression_reason: Optional[str] = None,
) -> int:
    """
    Log alert to fact_alert_log.

    Returns the inserted row ID.
    """
    create_alert_log_table(conn)

    now = datetime.now()
    alert_date = now.strftime("%Y-%m-%d")
    alert_time = now.strftime("%Y-%m-%d %H:%M:%S")

    cursor = conn.execute(
        """
        INSERT INTO fact_alert_log
        (alert_date, alert_time, alert_type, channel, store_code, sku_key,
         message, status, external_id, suppression_reason)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (alert_date, alert_time, alert_type, channel, store_code, sku_key,
         message, status, external_id, suppression_reason)
    )
    conn.commit()
    return cursor.lastrowid


def get_reorder_skus(conn) -> list[dict]:
    """
    Get all SKUs with REORDER status from fact_sku_metrics.

    Returns list of dicts with SKU details.
    """
    # Get latest computed_at timestamp
    cursor = conn.execute(
        "SELECT MAX(computed_at) FROM fact_sku_metrics"
    )
    latest = cursor.fetchone()[0]

    if not latest:
        return []

    cursor = conn.execute(
        """
        SELECT
            sku_key, store_code, d30, sigma, ss_total, rop,
            current_stock, inbound_stock, total_stock,
            status, suggested_order_qty, roic_monthly
        FROM fact_sku_metrics
        WHERE computed_at = ? AND status = 'REORDER'
        ORDER BY roic_monthly DESC
        """,
        (latest,)
    )

    columns = [
        "sku_key", "store_code", "d30", "sigma", "ss_total", "rop",
        "current_stock", "inbound_stock", "total_stock",
        "status", "suggested_order_qty", "roic_monthly"
    ]

    return [dict(zip(columns, row)) for row in cursor.fetchall()]


def send_reorder_alerts(
    conn,
    dry_run: bool = False,
    cooldown_hours: int = 24,
    force: bool = False,
) -> dict:
    """
    Send Telegram alerts for all REORDER SKUs.

    Args:
        conn: Database connection
        dry_run: If True, format messages but don't send
        cooldown_hours: Hours to wait before re-alerting same SKU
        force: If True, ignore cooldown

    Returns:
        Dict with sent, suppressed, failed counts and messages list
    """
    create_alert_log_table(conn)

    # Get REORDER SKUs
    skus = get_reorder_skus(conn)

    if not skus:
        return {
            "sent": 0,
            "suppressed": 0,
            "failed": 0,
            "messages": [],
            "note": "No SKUs with REORDER status",
        }

    # Get Telegram config
    try:
        config = get_telegram_config()
    except ValueError as e:
        return {
            "sent": 0,
            "suppressed": 0,
            "failed": len(skus),
            "messages": [],
            "error": str(e),
        }

    results = {
        "sent": 0,
        "suppressed": 0,
        "failed": 0,
        "messages": [],
    }

    for sku in skus:
        sku_key = sku["sku_key"]
        store_code = sku["store_code"]

        # Check cooldown (unless forced)
        if not force:
            should_send, reason = check_cooldown(conn, sku_key, store_code, cooldown_hours)
            if not should_send:
                results["suppressed"] += 1
                if not dry_run:
                    log_alert(
                        conn, sku_key, store_code,
                        alert_type="REORDER",
                        channel="telegram",
                        message="",
                        status="SUPPRESSED",
                        suppression_reason=reason,
                    )
                continue

        # Format message
        message = format_reorder_alert(sku)
        results["messages"].append({
            "sku_key": sku_key,
            "store_code": store_code,
            "message": message,
        })

        if dry_run:
            results["sent"] += 1
            continue

        # Send message
        response = send_message(
            chat_id=config["chat_id"],
            message=message,
            token=config["token"],
        )

        if response["success"]:
            results["sent"] += 1
            log_alert(
                conn, sku_key, store_code,
                alert_type="REORDER",
                channel="telegram",
                message=message,
                status="SENT",
                external_id=response.get("message_id"),
            )
        else:
            results["failed"] += 1
            log_alert(
                conn, sku_key, store_code,
                alert_type="REORDER",
                channel="telegram",
                message=message,
                status="FAILED",
                suppression_reason=response.get("error"),
            )

    return results
