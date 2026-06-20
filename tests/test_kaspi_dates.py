from __future__ import annotations

from datetime import date, datetime

from core.utils import kaspi_dates


def _ms(dt_str: str) -> int:
    dt = datetime.fromisoformat(dt_str).replace(tzinfo=kaspi_dates.ALMATY_TZ)
    return int(dt.timestamp() * 1000)


def test_planned_date_from_order_rolls_to_next_day_after_1700_when_planned_timestamp_missing(
    monkeypatch,
) -> None:
    monkeypatch.delenv("KASPI_PLANNED_CUTOFF_HOUR", raising=False)
    monkeypatch.delenv("KASPI_PLANNED_CUTOFF_MINUTE", raising=False)
    monkeypatch.delenv("KASPI_PLANNED_CUTOFF_HOUR_ACMEWEAR", raising=False)
    monkeypatch.delenv("KASPI_PLANNED_CUTOFF_MINUTE_ACMEWEAR", raising=False)

    order = {
        "attributes": {
            "creationDate": _ms("2026-03-14T17:00:01"),
            "kaspiDelivery": {},
        }
    }

    assert kaspi_dates.planned_date_from_order(order) == date(2026, 3, 15)


def test_planned_date_from_order_keeps_same_day_through_1700_when_planned_timestamp_missing(
    monkeypatch,
) -> None:
    monkeypatch.delenv("KASPI_PLANNED_CUTOFF_HOUR", raising=False)
    monkeypatch.delenv("KASPI_PLANNED_CUTOFF_MINUTE", raising=False)
    monkeypatch.delenv("KASPI_PLANNED_CUTOFF_HOUR_ACMEWEAR", raising=False)
    monkeypatch.delenv("KASPI_PLANNED_CUTOFF_MINUTE_ACMEWEAR", raising=False)

    order = {
        "attributes": {
            "creationDate": _ms("2026-03-14T17:00:00"),
            "kaspiDelivery": {},
        }
    }

    assert kaspi_dates.planned_date_from_order(order) == date(2026, 3, 14)


def test_planned_date_from_order_uses_all_store_1700_default_when_planned_timestamp_missing(
    monkeypatch,
) -> None:
    monkeypatch.delenv("KASPI_PLANNED_CUTOFF_HOUR", raising=False)
    monkeypatch.delenv("KASPI_PLANNED_CUTOFF_MINUTE", raising=False)
    monkeypatch.delenv("KASPI_PLANNED_CUTOFF_HOUR_ACMEWEAR", raising=False)
    monkeypatch.delenv("KASPI_PLANNED_CUTOFF_MINUTE_ACMEWEAR", raising=False)

    order = {
        "attributes": {
            "creationDate": _ms("2026-03-14T16:59:59"),
            "kaspiDelivery": {},
        }
    }

    assert kaspi_dates.planned_date_from_order(order, store_code="UNIVERSAL") == date(2026, 3, 14)


def test_planned_date_from_order_rolls_any_store_next_day_after_1700_when_planned_timestamp_missing(
    monkeypatch,
) -> None:
    monkeypatch.delenv("KASPI_PLANNED_CUTOFF_HOUR", raising=False)
    monkeypatch.delenv("KASPI_PLANNED_CUTOFF_MINUTE", raising=False)
    monkeypatch.delenv("KASPI_PLANNED_CUTOFF_HOUR_ACMEWEAR", raising=False)
    monkeypatch.delenv("KASPI_PLANNED_CUTOFF_MINUTE_ACMEWEAR", raising=False)

    order = {
        "attributes": {
            "creationDate": _ms("2026-03-14T17:00:01"),
            "kaspiDelivery": {},
        }
    }

    assert kaspi_dates.planned_date_from_order(order, store_code="STOREB") == date(2026, 3, 15)


def test_planned_date_from_order_honors_store_specific_cutoff_when_planned_timestamp_missing(
    monkeypatch,
) -> None:
    monkeypatch.delenv("KASPI_PLANNED_CUTOFF_HOUR", raising=False)
    monkeypatch.delenv("KASPI_PLANNED_CUTOFF_MINUTE", raising=False)
    monkeypatch.setenv("KASPI_PLANNED_CUTOFF_HOUR_ACMEWEAR", "16")
    monkeypatch.setenv("KASPI_PLANNED_CUTOFF_MINUTE_ACMEWEAR", "0")

    order = {
        "attributes": {
            "creationDate": _ms("2026-03-14T15:30:00"),
            "kaspiDelivery": {},
        }
    }

    assert kaspi_dates.planned_date_from_order(order, store_code="ACMEWEAR") == date(2026, 3, 14)


def test_planned_date_from_order_prefers_explicit_api_planned_timestamp_over_store_cutoff(
    monkeypatch,
) -> None:
    monkeypatch.setenv("KASPI_PLANNED_CUTOFF_HOUR_ACMEWEAR", "16")
    monkeypatch.setenv("KASPI_PLANNED_CUTOFF_MINUTE_ACMEWEAR", "0")

    order = {
        "attributes": {
            "creationDate": _ms("2026-03-14T15:30:00"),
            "kaspiDelivery": {
                "courierTransmissionPlanningDate": _ms("2026-03-15T20:00:00"),
            },
        }
    }

    assert kaspi_dates.planned_date_from_order(order, store_code="ACMEWEAR") == date(2026, 3, 15)
