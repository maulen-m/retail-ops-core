from __future__ import annotations

from datetime import date, datetime

from core.utils import kaspi_dates


def _ms(dt_str: str) -> int:
    dt = datetime.fromisoformat(dt_str).replace(tzinfo=kaspi_dates.ALMATY_TZ)
    return int(dt.timestamp() * 1000)


def test_planned_date_from_order_rolls_to_next_day_at_150100_when_planned_timestamp_missing(
    monkeypatch,
) -> None:
    monkeypatch.delenv("KASPI_PLANNED_CUTOFF_HOUR", raising=False)
    monkeypatch.delenv("KASPI_PLANNED_CUTOFF_MINUTE", raising=False)

    order = {
        "attributes": {
            "creationDate": _ms("2026-03-14T15:01:00"),
            "kaspiDelivery": {},
        }
    }

    assert kaspi_dates.planned_date_from_order(order) == date(2026, 3, 15)


def test_planned_date_from_order_keeps_same_day_before_150100_when_planned_timestamp_missing(
    monkeypatch,
) -> None:
    monkeypatch.delenv("KASPI_PLANNED_CUTOFF_HOUR", raising=False)
    monkeypatch.delenv("KASPI_PLANNED_CUTOFF_MINUTE", raising=False)

    order = {
        "attributes": {
            "creationDate": _ms("2026-03-14T15:00:59"),
            "kaspiDelivery": {},
        }
    }

    assert kaspi_dates.planned_date_from_order(order) == date(2026, 3, 14)
