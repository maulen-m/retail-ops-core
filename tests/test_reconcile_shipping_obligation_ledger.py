from __future__ import annotations

from datetime import date, datetime
from zoneinfo import ZoneInfo

from core.ops.waybill_shipping_obligations import OPEN_STATUSES
from scripts.reconcile_shipping_obligation_ledger import reconcile_ledger


ALMATY = ZoneInfo("Asia/Almaty")
NOW = datetime(2026, 7, 17, 21, 0, tzinfo=ALMATY)
CONTAMINATION_DATE = date(2026, 7, 17)
ROLLOVER_DATE = date(2026, 7, 18)


def _entry(
    store: str,
    order_id: str,
    *,
    status: str = "unresolved",
    first_seen: str = "2026-07-17",
) -> dict:
    return {
        "store_code": store,
        "order_id": order_id,
        "status": status,
        "first_seen_target_date": first_seen,
        "last_seen_target_date": "2026-07-17",
        "last_stage": "API_ACTIVE_SELECTOR",
        "last_api_error": "",
    }


def _order(
    order_id: str,
    *,
    state: str = "KASPI_DELIVERY",
    status: str = "ACCEPTED_BY_MERCHANT",
    courier_transmission_date: int | None = None,
) -> dict:
    delivery: dict[str, object] = {
        "waybill": f"https://kaspi.example/{order_id}.pdf",
    }
    if courier_transmission_date is not None:
        delivery["courierTransmissionDate"] = courier_transmission_date
    return {
        "attributes": {
            "code": order_id,
            "state": state,
            "status": status,
            "assembled": True,
            "kaspiDelivery": delivery,
        }
    }


def _ledger(entries: dict[str, dict]) -> dict:
    return {
        "schema_version": 1,
        "updated_at": "2026-07-17T19:33:23+05:00",
        "request_identity": {
            "target_date": "2026-07-17",
            "ready_set_at": "2026-07-17T19:08:30+05:00",
        },
        "entries": entries,
    }


def _run(
    ledger: dict,
    details: dict[str, dict],
    *,
    manual: set[str] | None = None,
    carry: set[str] | None = None,
) -> dict:
    return reconcile_ledger(
        prior_ledger=ledger,
        detail_results=details,
        contamination_date=CONTAMINATION_DATE,
        rollover_date=ROLLOVER_DATE,
        manual_handover_stores=manual or set(),
        carryforward_stores=carry or set(),
        now=NOW,
        ready_set_at="ledger-reconcile:test",
    )


def test_fresh_handover_discharges_and_replaces_premature_registration() -> None:
    key = "STOREB:1001"
    result = _run(
        _ledger({key: _entry("STOREB", "1001")}),
        {key: {"order": _order("1001", courier_transmission_date=1784310000000)}},
        manual={"STOREB"},
    )

    decision = result["decisions"][0]
    candidate = result["candidate_ledger"]["entries"][key]
    assert decision["action"] == "discharge-with-evidence"
    assert decision["premature_registration_removed"] is True
    assert candidate["status"] == "discharged"
    assert candidate["discharge_reason"] == "IN_DELIVERY"
    assert candidate["first_seen_target_date"] == "2026-07-18"
    assert result["summary"]["remaining_contamination_keys"] == []


def test_manual_handover_not_yet_in_api_stays_open_for_next_reconcile() -> None:
    key = "ACMEWEAR:2001"
    result = _run(
        _ledger({key: _entry("ACMEWEAR", "2001")}),
        {key: {"order": _order("2001")}},
        manual={"ACMEWEAR"},
    )

    decision = result["decisions"][0]
    candidate = result["candidate_ledger"]["entries"][key]
    assert decision["action"] == "keep-open"
    assert decision["reason"] == "manual handover not yet in API"
    assert candidate["status"] == "unresolved"
    assert candidate["first_seen_target_date"] == "2026-07-18"


def test_universal_postponement_remains_legitimate_open_carryforward() -> None:
    current_key = "UNIVERSAL:3001"
    prior_key = "UNIVERSAL:3000"
    result = _run(
        _ledger(
            {
                current_key: _entry("UNIVERSAL", "3001"),
                prior_key: _entry(
                    "UNIVERSAL", "3000", first_seen="2026-07-16"
                ),
            }
        ),
        {
            current_key: {"order": _order("3001")},
            prior_key: {"order": _order("3000")},
        },
        carry={"UNIVERSAL"},
    )

    entries = result["candidate_ledger"]["entries"]
    assert entries[current_key]["status"] in OPEN_STATUSES
    assert entries[current_key]["first_seen_target_date"] == "2026-07-18"
    assert entries[prior_key]["status"] in OPEN_STATUSES
    assert entries[prior_key]["first_seen_target_date"] == "2026-07-16"
    assert result["summary"]["open_counts_by_store"] == {"UNIVERSAL": 2}


def test_contradictory_manual_cancellation_is_flagged_and_never_discharged() -> None:
    key = "STOREB:4001"
    result = _run(
        _ledger({key: _entry("STOREB", "4001")}),
        {
            key: {
                "order": _order(
                    "4001",
                    state="ARCHIVE",
                    status="CANCELLED",
                )
            }
        },
        manual={"STOREB"},
    )

    decision = result["decisions"][0]
    candidate = result["candidate_ledger"]["entries"][key]
    assert decision["action"] == "keep-open"
    assert "contradicts day truth" in decision["reason"]
    assert decision["contradiction"]
    assert candidate["status"] == "unresolved"
    assert result["summary"]["contradiction_count"] == 1


def test_unclaimed_premature_registration_is_removed_and_untouched_entry_is_exact() -> None:
    premature_key = "MELVIS:5001"
    historical_key = "STOREB:OLD"
    historical = _entry(
        "STOREB",
        "OLD",
        status="discharged",
        first_seen="2026-07-12",
    )
    historical["discharge_reason"] = "IN_DELIVERY"
    ledger = _ledger(
        {
            premature_key: _entry("MELVIS", "5001"),
            historical_key: historical,
        }
    )
    result = _run(
        ledger,
        {premature_key: {"order": _order("5001")}},
    )

    decision = result["decisions"][0]
    entries = result["candidate_ledger"]["entries"]
    assert decision["action"] == "remove-premature-registration"
    assert premature_key not in entries
    assert entries[historical_key] == historical
    assert result["summary"]["untouched_entry_count"] == 1
