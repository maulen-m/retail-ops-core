#!/usr/bin/env python3
"""
Run REORDER Alerts: Send Telegram notifications for SKUs needing reorder.

This script:
1. Queries fact_sku_metrics for status='REORDER'
2. Checks 24-hour cooldown to avoid duplicate alerts
3. Sends formatted Telegram messages
4. Logs all alerts to fact_alert_log

Usage:
    python scripts/run_reorder_alerts.py              # Send alerts
    python scripts/run_reorder_alerts.py --dry-run    # Preview without sending
    python scripts/run_reorder_alerts.py --force      # Ignore cooldown
    python scripts/run_reorder_alerts.py --test       # Send test message
"""

import argparse
import os
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

# Load .env file
env_path = Path(__file__).parent.parent / ".env"
if env_path.exists():
    with open(env_path) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, value = line.split("=", 1)
                os.environ.setdefault(key.strip(), value.strip())

from core.db import get_db
from core.alerts.telegram import (
    send_message,
    get_telegram_config,
    send_reorder_alerts,
    get_reorder_skus,
)


def send_test_message() -> dict:
    """Send a test message to verify bot setup."""
    try:
        config = get_telegram_config()
    except ValueError as e:
        return {"success": False, "error": str(e)}

    message = """Test Alert from Inventory System

This is a test message to verify Telegram bot configuration.

If you see this, the bot is working correctly."""

    return send_message(
        chat_id=config["chat_id"],
        message=message,
        token=config["token"],
        parse_mode="HTML",
    )


def main():
    parser = argparse.ArgumentParser(
        description="Send Telegram alerts for REORDER SKUs"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview alerts without sending",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Ignore cooldown, send all REORDER alerts",
    )
    parser.add_argument(
        "--test",
        action="store_true",
        help="Send test message to verify bot setup",
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="Suppress progress output",
    )
    parser.add_argument(
        "--cooldown",
        type=int,
        default=24,
        help="Cooldown period in hours (default: 24)",
    )

    args = parser.parse_args()

    print("=" * 60)
    print("Run REORDER Alerts")
    print("=" * 60)

    # Handle test mode
    if args.test:
        print("\nSending test message...")
        result = send_test_message()
        if result["success"]:
            print(f"  SUCCESS - Message ID: {result.get('message_id')}")
            return 0
        else:
            print(f"  FAILED - {result.get('error')}")
            return 1

    # Get REORDER SKUs
    with get_db() as conn:
        skus = get_reorder_skus(conn)

        if not args.quiet:
            print(f"\nFound {len(skus)} SKUs with REORDER status")

        if not skus:
            print("No alerts to send")
            return 0

        if not args.quiet:
            print("\nREORDER SKUs:")
            for sku in skus[:5]:  # Show first 5
                print(f"  {sku['sku_key']}: stock={sku['current_stock']}, ROP={sku['rop']:.0f}")
            if len(skus) > 5:
                print(f"  ... and {len(skus) - 5} more")

        # Send alerts
        if not args.quiet:
            action = "Would send" if args.dry_run else "Sending"
            print(f"\n{action} alerts...")

        result = send_reorder_alerts(
            conn,
            dry_run=args.dry_run,
            cooldown_hours=args.cooldown,
            force=args.force,
        )

    # Print results
    print("\n" + "-" * 40)
    print("Results:")
    print(f"  Sent: {result['sent']}")
    print(f"  Suppressed (cooldown): {result['suppressed']}")
    print(f"  Failed: {result['failed']}")

    if result.get("error"):
        print(f"\nError: {result['error']}")

    if args.dry_run and result["messages"]:
        print("\n" + "-" * 40)
        print("Message preview (first):")
        print(result["messages"][0]["message"][:500])

    print("\n" + "=" * 60)
    if args.dry_run:
        print("DRY RUN - no messages sent")
    print("=" * 60)

    return 0 if result["failed"] == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
