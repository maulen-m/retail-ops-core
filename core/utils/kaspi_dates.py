from __future__ import annotations

import os
from datetime import date, datetime, time, timedelta
from typing import Optional
from zoneinfo import ZoneInfo

ALMATY_TZ = ZoneInfo("Asia/Almaty")
_CUTOFF_HOUR_ENV = "KASPI_PLANNED_CUTOFF_HOUR"
_CUTOFF_MINUTE_ENV = "KASPI_PLANNED_CUTOFF_MINUTE"


def _safe_int(value: str, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _get_cutoff_time() -> time:
    """Return cutoff time for planned date (local Kaspi rule)."""
    hour = _safe_int(os.environ.get(_CUTOFF_HOUR_ENV, "16"), 16)
    minute = _safe_int(os.environ.get(_CUTOFF_MINUTE_ENV, "0"), 0)
    # Clamp to valid ranges to avoid ValueError.
    hour = min(max(hour, 0), 23)
    minute = min(max(minute, 0), 59)
    return time(hour=hour, minute=minute)


def _timestamp_to_dt(ts: Optional[int]) -> Optional[datetime]:
    if ts is None:
        return None
    try:
        return datetime.fromtimestamp(ts / 1000, tz=ALMATY_TZ)
    except (OSError, ValueError, TypeError):
        return None


def _planned_ts_from_order(order: dict) -> Optional[int]:
    attrs = order.get("attributes", {}) or {}
    delivery = attrs.get("kaspiDelivery", {}) or {}
    return (
        delivery.get("courierTransmissionPlanningDate")
        or delivery.get("plannedDeliveryDate")
        or attrs.get("plannedDeliveryDate")
    )


def planned_date_from_order(order: dict) -> Optional[date]:
    """
    Compute planned ship date using local cutoff logic.

    Rule:
      - Orders created up to cutoff time (default 16:00) -> same-day ship date
      - Orders created after cutoff -> next-day ship date
      - If API planned date is far in the future (preorder), keep API planned date
    """
    attrs = order.get("attributes", {}) or {}
    created_dt = _timestamp_to_dt(attrs.get("creationDate"))

    planned_ts = _planned_ts_from_order(order)
    planned_dt = _timestamp_to_dt(planned_ts)
    planned_date = planned_dt.date() if planned_dt else None

    if not created_dt:
        return planned_date

    cutoff = _get_cutoff_time()
    cutoff_dt = created_dt.replace(
        hour=cutoff.hour, minute=cutoff.minute, second=0, microsecond=0
    )
    base_date = created_dt.date()
    if created_dt > cutoff_dt:
        base_date = base_date + timedelta(days=1)

    # Preserve API planned dates that are much later (preorders)
    if planned_date and planned_date > base_date + timedelta(days=1):
        return planned_date

    return base_date

