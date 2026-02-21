from __future__ import annotations

from core.ops.shipment_health import classify_ship_health, classify_waybill_health


def test_ship_partial_classified_and_nonzero() -> None:
    state = classify_ship_health({"shipped": 5, "skipped": 2, "errors": []})
    assert state.code == "partial"
    assert state.exit_code == 1


def test_waybill_delayed_classified_and_nonzero() -> None:
    state = classify_waybill_health(
        {
            "downloaded": 0,
            "already_exists": 0,
            "missing_waybill": 12,
            "invalid_pdf": 0,
            "errors": [],
        }
    )
    assert state.code == "delayed"
    assert state.exit_code == 1


def test_waybill_ok_when_downloaded_and_no_errors() -> None:
    state = classify_waybill_health(
        {
            "downloaded": 10,
            "already_exists": 2,
            "missing_waybill": 0,
            "invalid_pdf": 0,
            "errors": [],
        }
    )
    assert state.code == "ok"
    assert state.exit_code == 0
