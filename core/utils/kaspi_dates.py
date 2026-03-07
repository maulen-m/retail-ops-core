from __future__ import annotations

import os
import re
from datetime import date, datetime, time, timedelta
from typing import Optional
from zoneinfo import ZoneInfo

from dateutil import parser as dtp

ALMATY_TZ = ZoneInfo("Asia/Almaty")
_CUTOFF_HOUR_ENV = "KASPI_PLANNED_CUTOFF_HOUR"
_CUTOFF_MINUTE_ENV = "KASPI_PLANNED_CUTOFF_MINUTE"
_ISO_LIKE_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}(?:[ T].*)?$")


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


def parse_kaspi_date(value: object) -> Optional[date]:
    """
    Parse mixed Kaspi/CRM date values without flipping ISO month/day order.

    The workflow routinely encounters both human-formatted dates (`DD.MM.YYYY`)
    and machine-formatted timestamps (`YYYY-MM-DD HH:MM:SS`). Falling back to a
    generic `dayfirst=True` parser on ISO-like timestamps silently converts
    `2026-03-06` into `2026-06-03`, which can push overdue pending orders out of
    today's operational selection. We keep ISO-like strings on `dayfirst=False`
    and reserve `dayfirst=True` only for ambiguous human-formatted inputs.
    """
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value

    text = str(value).strip()
    if not text:
        return None
    if text.lower() in {"nan", "nat", "none", "null", "<na>"}:
        return None

    try:
        return datetime.strptime(text, "%d.%m.%Y").date()
    except ValueError:
        pass

    try:
        return datetime.strptime(text, "%Y-%m-%d").date()
    except ValueError:
        pass

    try:
        return dtp.parse(text, dayfirst=not bool(_ISO_LIKE_DATE_RE.match(text))).date()
    except Exception:
        return None


def planned_date_from_order(order: dict) -> Optional[date]:
    """
    Resolve the operator-facing planned handover date for a Kaspi order.

    Rule:
      - Prefer Kaspi's explicit courier handover / planned delivery timestamp when present.
      - Fall back to legacy creation-time cutoff logic only when API planned timestamps
        are missing from the payload.

    Why:
      - Operator-facing flows (CRM import, shipping, waybills, reports) must follow the
        real Kaspi planned handover date. Otherwise next-day orders can be surfaced a day
        early and become false pending / missing-waybill targets.
    """
    attrs = order.get("attributes", {}) or {}

    planned_ts = _planned_ts_from_order(order)
    planned_dt = _timestamp_to_dt(planned_ts)
    if planned_dt:
        return planned_dt.date()

    created_dt = _timestamp_to_dt(attrs.get("creationDate"))
    if not created_dt:
        return None

    cutoff = _get_cutoff_time()
    cutoff_dt = created_dt.replace(
        hour=cutoff.hour, minute=cutoff.minute, second=0, microsecond=0
    )
    base_date = created_dt.date()
    if created_dt > cutoff_dt:
        base_date = base_date + timedelta(days=1)

    return base_date
