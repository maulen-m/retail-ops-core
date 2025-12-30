"""
Blackout period management for PO scheduling.

Handles supplier blackout periods (e.g., Chinese New Year) where:
- Factories are closed
- Shipping/cargo services unavailable
- PO dates should be adjusted to avoid blackouts

Usage:
    from core.po.blackout import BlackoutManager, CNY_2026

    manager = BlackoutManager([CNY_2026])
    adjusted_date = manager.skip_blackout(ship_date)
"""

from dataclasses import dataclass
from datetime import date, timedelta
from typing import List, Optional


@dataclass
class BlackoutPeriod:
    """Represents a blackout period where no PO activities can occur."""
    name: str
    start_date: date
    end_date: date
    reason: str

    def contains(self, d: date) -> bool:
        """Check if a date falls within this blackout period."""
        return self.start_date <= d <= self.end_date

    def days_remaining(self, from_date: date) -> int:
        """Days until this blackout ends (0 if not in blackout)."""
        if not self.contains(from_date):
            return 0
        return (self.end_date - from_date).days + 1


# Pre-defined blackout periods
CNY_2026 = BlackoutPeriod(
    name="CNY_2026",
    start_date=date(2026, 1, 27),
    end_date=date(2026, 2, 20),
    reason="Chinese New Year 2026 factory/shipping blackout"
)

CNY_2027 = BlackoutPeriod(
    name="CNY_2027",
    start_date=date(2027, 2, 12),  # Approximate
    end_date=date(2027, 3, 5),     # Approximate
    reason="Chinese New Year 2027 factory/shipping blackout"
)


class BlackoutManager:
    """
    Manages blackout periods and adjusts dates accordingly.

    Key behaviors:
    - If a date falls within a blackout, push it to the day after blackout ends
    - Provides blackout warnings for planning purposes
    - Supports multiple blackout periods
    """

    def __init__(self, blackout_periods: Optional[List[BlackoutPeriod]] = None):
        """
        Initialize with list of blackout periods.

        Args:
            blackout_periods: List of BlackoutPeriod objects. If None, uses default list.
        """
        self.periods = blackout_periods or [CNY_2026, CNY_2027]
        # Sort by start date
        self.periods.sort(key=lambda p: p.start_date)

    def is_blackout(self, d: date) -> tuple[bool, Optional[BlackoutPeriod]]:
        """
        Check if a date falls within any blackout period.

        Returns:
            Tuple of (is_blackout, period_if_blocked)
        """
        for period in self.periods:
            if period.contains(d):
                return True, period
        return False, None

    def skip_blackout(self, d: date) -> tuple[date, Optional[BlackoutPeriod]]:
        """
        Adjust a date to skip any blackout period.

        If the date falls in a blackout, returns the first day after blackout ends.
        If not in blackout, returns the original date.

        Returns:
            Tuple of (adjusted_date, blocked_period)
        """
        is_blocked, period = self.is_blackout(d)
        if is_blocked and period:
            # Move to day after blackout ends
            adjusted = period.end_date + timedelta(days=1)
            return adjusted, period
        return d, None

    def get_next_blackout(self, from_date: date) -> Optional[BlackoutPeriod]:
        """Get the next upcoming blackout period from a given date."""
        for period in self.periods:
            if period.start_date >= from_date:
                return period
            if period.contains(from_date):
                return period
        return None

    def days_until_blackout(self, from_date: date) -> Optional[int]:
        """Days until the next blackout starts (None if no upcoming blackout)."""
        next_blackout = self.get_next_blackout(from_date)
        if next_blackout is None:
            return None
        if next_blackout.contains(from_date):
            return 0
        return (next_blackout.start_date - from_date).days

    def get_blackout_warning(self, from_date: date, lead_time_days: int) -> Optional[str]:
        """
        Check if a PO placed on from_date with given lead time will hit a blackout.

        Args:
            from_date: PO placement date
            lead_time_days: Expected lead time in days

        Returns:
            Warning message if blackout affects this PO, None otherwise
        """
        eta = from_date + timedelta(days=lead_time_days)

        # Check if ETA falls in blackout
        is_blocked, period = self.is_blackout(eta)
        if is_blocked and period:
            adjusted_eta, _ = self.skip_blackout(eta)
            delay = (adjusted_eta - eta).days
            return (
                f"PO ETA {eta} falls in {period.name} blackout. "
                f"Adjusted ETA: {adjusted_eta} (+{delay} days delay)"
            )

        # Check if blackout is approaching within buffer
        days_until = self.days_until_blackout(eta)
        if days_until is not None and 0 < days_until <= 7:
            next_blackout = self.get_next_blackout(eta)
            if next_blackout:
                return (
                    f"Warning: ETA {eta} is {days_until} days before "
                    f"{next_blackout.name} blackout starts on {next_blackout.start_date}"
                )

        return None


def adjust_po_dates(
    po_date: date,
    ship_date: date,
    est_arrival: date,
    blackout_manager: Optional[BlackoutManager] = None
) -> dict:
    """
    Adjust all PO dates to account for blackout periods.

    Args:
        po_date: Original PO placement date
        ship_date: Original cargo ship date
        est_arrival: Original estimated arrival date
        blackout_manager: BlackoutManager instance (uses default if None)

    Returns:
        Dict with adjusted dates and any warnings:
        {
            "po_date": adjusted_po_date,
            "ship_date": adjusted_ship_date,
            "est_arrival": adjusted_est_arrival,
            "warnings": [list of warning messages],
            "blackout_adjusted": bool
        }
    """
    manager = blackout_manager or BlackoutManager()
    warnings = []
    blackout_adjusted = False

    # Check and adjust ship_date (factory needs to be open to ship)
    adjusted_ship, blocked_period = manager.skip_blackout(ship_date)
    if blocked_period:
        warnings.append(
            f"Ship date {ship_date} falls in {blocked_period.name} blackout. "
            f"Adjusted to {adjusted_ship}"
        )
        blackout_adjusted = True

        # Recalculate ETA based on new ship date
        original_transit = (est_arrival - ship_date).days
        est_arrival = adjusted_ship + timedelta(days=original_transit)
        ship_date = adjusted_ship

    # Check and adjust est_arrival (customs may be affected)
    adjusted_arrival, blocked_period = manager.skip_blackout(est_arrival)
    if blocked_period:
        warnings.append(
            f"Est arrival {est_arrival} falls in {blocked_period.name} blackout. "
            f"Adjusted to {adjusted_arrival}"
        )
        blackout_adjusted = True
        est_arrival = adjusted_arrival

    # PO date usually doesn't need adjustment (ordering can happen anytime)
    # But check if it's too close to blackout for meaningful processing
    warning = manager.get_blackout_warning(po_date, (ship_date - po_date).days)
    if warning:
        warnings.append(warning)

    return {
        "po_date": po_date,
        "ship_date": ship_date,
        "est_arrival": est_arrival,
        "warnings": warnings,
        "blackout_adjusted": blackout_adjusted
    }


# Convenience function for simple usage
def skip_cny_blackout(d: date) -> date:
    """Simple helper to skip CNY blackout for a single date."""
    manager = BlackoutManager([CNY_2026, CNY_2027])
    adjusted, _ = manager.skip_blackout(d)
    return adjusted
