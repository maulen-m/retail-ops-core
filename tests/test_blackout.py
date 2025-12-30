#!/usr/bin/env python3
"""
Tests for blackout period handling.

Validates:
- Blackout only affects supplier-side dates (prep/ship), NOT arrival
- Ship date falling in blackout is pushed to day after blackout ends
- ETA is recalculated as: adjusted_ship_date + original_transit_time
"""

import pytest
from datetime import date, timedelta

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from core.po.blackout import (
    BlackoutPeriod,
    BlackoutManager,
    CNY_2026,
    adjust_po_dates,
    skip_cny_blackout,
)


class TestBlackoutPeriod:
    """Tests for BlackoutPeriod dataclass."""

    def test_cny_2026_dates(self):
        """Verify CNY 2026 blackout dates are correct."""
        assert CNY_2026.start_date == date(2026, 1, 27)
        assert CNY_2026.end_date == date(2026, 2, 20)

    def test_contains_in_blackout(self):
        """Test that dates within blackout are detected."""
        assert CNY_2026.contains(date(2026, 1, 27)) is True
        assert CNY_2026.contains(date(2026, 2, 1)) is True
        assert CNY_2026.contains(date(2026, 2, 20)) is True

    def test_contains_outside_blackout(self):
        """Test that dates outside blackout are not flagged."""
        assert CNY_2026.contains(date(2026, 1, 26)) is False
        assert CNY_2026.contains(date(2026, 2, 21)) is False
        assert CNY_2026.contains(date(2025, 2, 1)) is False


class TestBlackoutManager:
    """Tests for BlackoutManager class."""

    def test_skip_blackout_pushes_to_day_after(self):
        """Ship date in blackout should be pushed to day after blackout ends."""
        manager = BlackoutManager([CNY_2026])

        # Date in middle of blackout
        adjusted, period = manager.skip_blackout(date(2026, 2, 1))
        assert adjusted == date(2026, 2, 21)
        assert period == CNY_2026

    def test_skip_blackout_no_change_if_outside(self):
        """Date outside blackout should not change."""
        manager = BlackoutManager([CNY_2026])

        # Date before blackout
        adjusted, period = manager.skip_blackout(date(2026, 1, 20))
        assert adjusted == date(2026, 1, 20)
        assert period is None

        # Date after blackout
        adjusted, period = manager.skip_blackout(date(2026, 2, 25))
        assert adjusted == date(2026, 2, 25)
        assert period is None


class TestAdjustPoDates:
    """Tests for adjust_po_dates function - the key blackout logic."""

    def test_ship_date_in_blackout_pushes_eta(self):
        """
        CRITICAL TEST from plan P0-2:
        message_date 2026-01-25, prep_days 10 -> ship_date_cargo >= 2026-02-21

        If ship_date (2026-01-25 + 10 = 2026-02-04) falls in blackout,
        it should be pushed to 2026-02-21 (day after blackout ends).
        """
        po_date = date(2026, 1, 25)
        prep_days = 10
        ship_date = po_date + timedelta(days=prep_days)  # 2026-02-04
        transit_days = 14  # L
        est_arrival = ship_date + timedelta(days=transit_days)  # 2026-02-18

        result = adjust_po_dates(po_date, ship_date, est_arrival)

        # Ship date should be pushed past blackout
        assert result["ship_date"] >= date(2026, 2, 21), \
            f"Ship date {result['ship_date']} should be >= 2026-02-21"

        # ETA should be recalculated with same transit time
        expected_eta = result["ship_date"] + timedelta(days=transit_days)
        assert result["est_arrival"] == expected_eta, \
            f"ETA {result['est_arrival']} should be {expected_eta}"

        assert result["blackout_adjusted"] is True
        assert len(result["warnings"]) >= 1

    def test_arrival_not_independently_adjusted(self):
        """
        Arrival date should NOT be independently adjusted.
        Only ship_date gets blackout treatment; ETA is derived from it.
        """
        po_date = date(2026, 1, 10)
        ship_date = date(2026, 1, 20)  # Before blackout
        transit_days = 20
        est_arrival = date(2026, 2, 9)  # Falls IN blackout

        result = adjust_po_dates(po_date, ship_date, est_arrival)

        # Ship date is before blackout, so no adjustment
        assert result["ship_date"] == ship_date

        # Arrival is NOT independently adjusted (this was the bug)
        # It should stay the same since ship_date wasn't adjusted
        assert result["est_arrival"] == est_arrival
        assert result["blackout_adjusted"] is False

    def test_transit_time_preserved_after_adjustment(self):
        """Transit time (L) should be preserved when ship_date is adjusted."""
        po_date = date(2026, 1, 20)
        ship_date = date(2026, 2, 1)  # In blackout
        original_transit = 18
        est_arrival = ship_date + timedelta(days=original_transit)

        result = adjust_po_dates(po_date, ship_date, est_arrival)

        # Transit time should be the same
        new_transit = (result["est_arrival"] - result["ship_date"]).days
        assert new_transit == original_transit, \
            f"Transit time changed from {original_transit} to {new_transit}"

    def test_no_adjustment_when_outside_blackout(self):
        """Dates outside blackout should not change."""
        po_date = date(2026, 3, 1)
        ship_date = date(2026, 3, 10)
        est_arrival = date(2026, 3, 25)

        result = adjust_po_dates(po_date, ship_date, est_arrival)

        assert result["ship_date"] == ship_date
        assert result["est_arrival"] == est_arrival
        assert result["blackout_adjusted"] is False


class TestSkipCnyBlackout:
    """Tests for convenience function."""

    def test_skip_cny_simple(self):
        """Simple date skip."""
        d = date(2026, 2, 1)
        result = skip_cny_blackout(d)
        assert result == date(2026, 2, 21)

    def test_skip_cny_no_change(self):
        """Date outside CNY returns unchanged."""
        d = date(2026, 3, 15)
        result = skip_cny_blackout(d)
        assert result == d


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
