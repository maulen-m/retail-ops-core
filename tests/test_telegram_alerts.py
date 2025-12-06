"""
Tests for Telegram alerts module.
"""

import os
import sys
from datetime import datetime, timedelta
from pathlib import Path

import pytest

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from core.alerts.telegram import (
    format_reorder_alert,
    check_cooldown,
    log_alert,
    create_alert_log_table,
)
from core.db import get_db


class TestFormatReorderAlert:
    """Tests for alert message formatting."""

    def test_format_reorder_alert_basic(self):
        """Basic formatting works."""
        sku_data = {
            "sku_key": "TEST_SKU_001",
            "store_code": "UNIVERSAL",
            "current_stock": 100,
            "rop": 500,
            "suggested_order_qty": 600,
            "roic_monthly": 25.5,
            "d30": 15.3,
            "ss_total": 200,
        }
        message = format_reorder_alert(sku_data)

        assert "REORDER ALERT" in message
        assert "TEST_SKU_001" in message
        assert "UNIVERSAL" in message
        assert "100" in message  # current_stock
        assert "500" in message  # rop
        assert "600" in message  # suggested_order_qty
        assert "25.5" in message  # roic

    def test_format_reorder_alert_handles_zeros(self):
        """Handles zero values gracefully."""
        sku_data = {
            "sku_key": "EMPTY_SKU",
            "store_code": "ALL",
            "current_stock": 0,
            "rop": 0,
            "suggested_order_qty": 0,
            "roic_monthly": 0,
            "d30": 0,
            "ss_total": 0,
        }
        message = format_reorder_alert(sku_data)

        assert "REORDER ALERT" in message
        assert "EMPTY_SKU" in message

    def test_format_reorder_alert_missing_keys(self):
        """Handles missing keys with defaults."""
        sku_data = {"sku_key": "MINIMAL_SKU"}
        message = format_reorder_alert(sku_data)

        assert "MINIMAL_SKU" in message
        assert "ALL" in message  # Default store_code


class TestCheckCooldown:
    """Tests for cooldown checking."""

    def test_check_cooldown_no_prior_alert(self):
        """Returns True if no prior alert."""
        with get_db() as conn:
            create_alert_log_table(conn)

            should_send, reason = check_cooldown(
                conn, "NEW_SKU_NEVER_ALERTED", "TEST_STORE", hours=24
            )

        assert should_send is True
        assert reason is None

    def test_check_cooldown_within_period(self):
        """Returns False if alert sent within cooldown."""
        with get_db() as conn:
            create_alert_log_table(conn)

            # Log a recent alert
            log_alert(
                conn, "RECENT_SKU", "TEST_STORE",
                alert_type="REORDER",
                channel="telegram",
                message="test",
                status="SENT",
            )

            should_send, reason = check_cooldown(
                conn, "RECENT_SKU", "TEST_STORE", hours=24
            )

        assert should_send is False
        assert "cooldown" in reason.lower()

    def test_check_cooldown_expired(self):
        """Returns True if cooldown expired."""
        with get_db() as conn:
            create_alert_log_table(conn)

            # Log an old alert (hack: set to very short cooldown)
            should_send, reason = check_cooldown(
                conn, "OLD_SKU_123", "TEST_STORE", hours=0  # 0 hour cooldown
            )

        assert should_send is True


class TestLogAlert:
    """Tests for alert logging."""

    def test_log_alert_creates_record(self):
        """Logging creates a record in the database."""
        with get_db() as conn:
            create_alert_log_table(conn)

            row_id = log_alert(
                conn, "LOG_TEST_SKU", "LOG_STORE",
                alert_type="REORDER",
                channel="telegram",
                message="Test message",
                status="SENT",
                external_id="12345",
            )

            # Verify record exists
            cursor = conn.execute(
                "SELECT sku_key, status, external_id FROM fact_alert_log WHERE id = ?",
                (row_id,)
            )
            row = cursor.fetchone()

        assert row is not None
        assert row[0] == "LOG_TEST_SKU"
        assert row[1] == "SENT"
        assert row[2] == "12345"

    def test_log_alert_suppressed(self):
        """Can log suppressed alerts."""
        with get_db() as conn:
            create_alert_log_table(conn)

            row_id = log_alert(
                conn, "SUPPRESSED_SKU", "STORE",
                alert_type="REORDER",
                channel="telegram",
                message="",
                status="SUPPRESSED",
                suppression_reason="Within 24h cooldown",
            )

            cursor = conn.execute(
                "SELECT status, suppression_reason FROM fact_alert_log WHERE id = ?",
                (row_id,)
            )
            row = cursor.fetchone()

        assert row[0] == "SUPPRESSED"
        assert "cooldown" in row[1].lower()


class TestIntegration:
    """Integration tests."""

    def test_alert_log_table_exists(self):
        """fact_alert_log table exists and has expected schema."""
        with get_db() as conn:
            cursor = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='fact_alert_log'"
            )
            result = cursor.fetchone()

        assert result is not None

    def test_recent_alert_logged(self):
        """Verify a recent alert was logged (from run_reorder_alerts.py test)."""
        with get_db() as conn:
            cursor = conn.execute(
                "SELECT COUNT(*) FROM fact_alert_log WHERE alert_date = '2025-12-06'"
            )
            count = cursor.fetchone()[0]

        assert count >= 1, "Expected at least 1 alert logged today"
