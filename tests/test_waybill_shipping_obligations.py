from __future__ import annotations

import json
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from core.ops import waybill_shipping_obligations as obligation_mod
from core.ops.waybill_shipping_obligations import (
    active_obligation_ids_by_store,
    load_required_orders_file,
    load_shipping_obligation_ledger,
    reconcile_shipping_obligations,
    required_line_scope_hash,
)


ALMATY = ZoneInfo("Asia/Almaty")


@pytest.mark.parametrize(
    ("key", "entry", "message"),
    [
        ("UNIVERSAL:123", "not-an-object", "must be an object"),
        (
            "UNIVERSAL:123",
            {"store_code": "", "order_id": "123", "status": "unresolved"},
            "identity is incomplete",
        ),
        (
            "TYPO:123",
            {"store_code": "TYPO", "order_id": "123", "status": "unresolved"},
            "unknown store_code",
        ),
        (
            "UNIVERSAL:123",
            {"store_code": "UNIVERSAL", "order_id": "123", "status": "typo"},
            "unknown status",
        ),
        (
            "UNIVERSAL:123",
            {"store_code": "ACMEWEAR", "order_id": "123", "status": "unresolved"},
            "key/identity mismatch",
        ),
    ],
)
def test_obligation_ledger_loader_rejects_ambiguous_entries(
    tmp_path: Path,
    key: str,
    entry: object,
    message: str,
) -> None:
    path = tmp_path / "ledger.json"
    path.write_text(
        json.dumps({"schema_version": 1, "entries": {key: entry}}),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match=message):
        load_shipping_obligation_ledger(path)


def _order(
    order_id: str,
    *,
    state: str = "KASPI_DELIVERY",
    status: str = "ACCEPTED_BY_MERCHANT",
    assembled: bool = True,
    courier_transmission_date: int | None = None,
) -> dict:
    delivery: dict[str, object] = {
        "courierTransmissionPlanningDate": 1783616400000,
        "waybill": f"https://kaspi.example/{order_id}.pdf",
    }
    if courier_transmission_date is not None:
        delivery["courierTransmissionDate"] = courier_transmission_date
    return {
        "attributes": {
            "code": order_id,
            "state": state,
            "status": status,
            "assembled": assembled,
            "kaspiDelivery": delivery,
        }
    }


def _prior_ledger(order_id: str = "992447685") -> dict:
    return {
        "schema_version": 1,
        "entries": {
            f"UNIVERSAL:{order_id}": {
                "store_code": "UNIVERSAL",
                "order_id": order_id,
                "status": "unresolved",
                "first_seen_target_date": "2026-07-10",
                "last_seen_target_date": "2026-07-10",
            }
        },
    }


def test_reconcile_keeps_prior_active_obligation_without_expiry() -> None:
    result = reconcile_shipping_obligations(
        prior_ledger=_prior_ledger(),
        current_active_order_ids_by_store={},
        detail_results={"UNIVERSAL:992447685": {"order": _order("992447685")}},
        target_date=date(2026, 11, 30),
        ready_set_at="2026-11-30T17:03:04+05:00",
        now=datetime(2026, 11, 30, 17, 3, 5, tzinfo=ALMATY),
    )

    assert result["ok"] is True
    assert result["issues"] == []
    assert active_obligation_ids_by_store(result["ledger"]) == {
        "UNIVERSAL": {"992447685"}
    }
    entry = result["ledger"]["entries"]["UNIVERSAL:992447685"]
    assert entry["status"] == "unresolved"
    assert entry["last_stage"] == "ASSEMBLED_PENDING_HANDOVER"
    assert entry["last_seen_target_date"] == "2026-11-30"


def test_reconcile_discharges_only_source_backed_handover_or_terminal_truth() -> None:
    handed_over = reconcile_shipping_obligations(
        prior_ledger=_prior_ledger(),
        current_active_order_ids_by_store={},
        detail_results={
            "UNIVERSAL:992447685": {
                "order": _order("992447685", courier_transmission_date=1783706670000)
            }
        },
        target_date=date(2026, 7, 11),
        ready_set_at="2026-07-11T17:00:00+05:00",
        now=datetime(2026, 7, 11, 17, 0, 1, tzinfo=ALMATY),
    )
    assert active_obligation_ids_by_store(handed_over["ledger"]) == {}
    assert handed_over["ledger"]["entries"]["UNIVERSAL:992447685"]["status"] == "discharged"
    assert handed_over["ledger"]["entries"]["UNIVERSAL:992447685"]["discharge_reason"] == "IN_DELIVERY"

    cancelled = reconcile_shipping_obligations(
        prior_ledger=_prior_ledger("992447686"),
        current_active_order_ids_by_store={},
        detail_results={
            "UNIVERSAL:992447686": {
                "order": _order("992447686", state="ARCHIVE", status="CANCELLED")
            }
        },
        target_date=date(2026, 7, 11),
        ready_set_at="2026-07-11T17:00:00+05:00",
        now=datetime(2026, 7, 11, 17, 0, 1, tzinfo=ALMATY),
    )
    assert active_obligation_ids_by_store(cancelled["ledger"]) == {}
    assert cancelled["ledger"]["entries"]["UNIVERSAL:992447686"]["discharge_reason"] == "CANCELLED"


def test_reconcile_bare_archive_retains_obligation_and_blocks_omission() -> None:
    result = reconcile_shipping_obligations(
        prior_ledger=_prior_ledger(),
        current_active_order_ids_by_store={},
        detail_results={
            "UNIVERSAL:992447685": {
                "order": _order("992447685", state="ARCHIVE", status="")
            }
        },
        target_date=date(2026, 7, 11),
        ready_set_at="2026-07-11T17:00:00+05:00",
        now=datetime(2026, 7, 11, 17, 0, 1, tzinfo=ALMATY),
    )

    entry = result["ledger"]["entries"]["UNIVERSAL:992447685"]
    assert result["ok"] is False
    assert entry["status"] == "unresolved"
    assert entry["last_stage"] == "UNKNOWN"
    assert active_obligation_ids_by_store(result["ledger"]) == {
        "UNIVERSAL": {"992447685"}
    }
    assert result["issues"] == [
        {
            "code": "obligation_api_stage_uncertain",
            "key": "UNIVERSAL:992447685",
            "detail": "ARCHIVE_UNDIFFERENTIATED",
        }
    ]


@pytest.mark.parametrize(
    ("source_status", "expected_stage"),
    [
        ("CANCELLING", "CANCELLING"),
        ("KASPI_DELIVERY_RETURN_REQUESTED", "RETURN_REQUESTED"),
        ("RETURN_REQUESTED", "RETURN_REQUESTED"),
    ],
)
def test_reconcile_transitional_archive_suspends_without_discharge(
    source_status: str,
    expected_stage: str,
) -> None:
    result = reconcile_shipping_obligations(
        prior_ledger=_prior_ledger(),
        current_active_order_ids_by_store={},
        detail_results={
            "UNIVERSAL:992447685": {
                "order": _order(
                    "992447685",
                    state="ARCHIVE",
                    status=source_status,
                )
            }
        },
        target_date=date(2026, 7, 11),
        ready_set_at="2026-07-11T17:00:00+05:00",
        now=datetime(2026, 7, 11, 17, 0, 1, tzinfo=ALMATY),
    )

    entry = result["ledger"]["entries"]["UNIVERSAL:992447685"]
    assert result["ok"] is True
    assert entry["status"] == "suspended"
    assert entry["last_stage"] == expected_stage
    assert entry["suspension_reason"] == expected_stage
    assert entry.get("discharged_at", "") == ""
    assert active_obligation_ids_by_store(result["ledger"]) == {}


def test_current_selector_transitional_detail_is_suspended_not_packed() -> None:
    result = reconcile_shipping_obligations(
        prior_ledger={"schema_version": 1, "entries": {}},
        current_active_order_ids_by_store={"UNIVERSAL": {"RET1"}},
        detail_results={
            "UNIVERSAL:RET1": {
                "order": _order(
                    "RET1",
                    state="KASPI_DELIVERY",
                    status="KASPI_DELIVERY_RETURN_REQUESTED",
                )
            }
        },
        target_date=date(2026, 7, 11),
        ready_set_at="2026-07-11T17:00:00+05:00",
        now=datetime(2026, 7, 11, 17, 0, 1, tzinfo=ALMATY),
    )

    entry = result["ledger"]["entries"]["UNIVERSAL:RET1"]
    assert result["ok"] is True
    assert entry["status"] == "suspended"
    assert entry["last_stage"] == "RETURN_REQUESTED"
    assert active_obligation_ids_by_store(result["ledger"]) == {}


def test_reconcile_api_uncertainty_retains_obligation_and_blocks() -> None:
    result = reconcile_shipping_obligations(
        prior_ledger=_prior_ledger(),
        current_active_order_ids_by_store={},
        detail_results={"UNIVERSAL:992447685": {"error": "timeout"}},
        target_date=date(2026, 7, 11),
        ready_set_at="2026-07-11T17:00:00+05:00",
        now=datetime(2026, 7, 11, 17, 0, 1, tzinfo=ALMATY),
    )

    assert result["ok"] is False
    assert result["issues"] == [
        {
            "code": "obligation_api_uncertain",
            "key": "UNIVERSAL:992447685",
            "detail": "timeout",
        }
    ]
    assert active_obligation_ids_by_store(result["ledger"]) == {
        "UNIVERSAL": {"992447685"}
    }


@pytest.mark.parametrize(
    ("detail_result", "expected_detail"),
    [
        ({"error": "timeout"}, "timeout"),
        (
            {"order": _order("992447685", state="ARCHIVE", status="")},
            "ARCHIVE_UNDIFFERENTIATED",
        ),
    ],
)
def test_reconcile_exclusion_covered_uncertainty_is_retained_warned_and_nonblocking(
    monkeypatch: pytest.MonkeyPatch,
    detail_result: dict,
    expected_detail: str,
) -> None:
    alerts: list[dict[str, object]] = []
    monkeypatch.setattr(
        obligation_mod,
        "enqueue_alert",
        lambda **kwargs: alerts.append(kwargs) or False,
    )

    result = reconcile_shipping_obligations(
        prior_ledger=_prior_ledger(),
        current_active_order_ids_by_store={},
        detail_results={"UNIVERSAL:992447685": detail_result},
        target_date=date(2026, 7, 18),
        ready_set_at="2026-07-18T17:00:00+05:00",
        now=datetime(2026, 7, 18, 17, 0, 1, tzinfo=ALMATY),
        uncertainty_waiver_ids_by_store={"30000001_PP1": {"992447685"}},
        enqueue_uncertainty_warnings=True,
    )

    assert result["ok"] is True
    assert result["issues"] == [
        {
            "code": "obligation_api_uncertain_excluded_scope",
            "key": "UNIVERSAL:992447685",
            "detail": expected_detail,
        }
    ]
    assert result["uncertainty_scope_counts"] == {"covered": 1, "uncovered": 0}
    assert active_obligation_ids_by_store(result["ledger"]) == {
        "UNIVERSAL": {"992447685"}
    }
    assert result["ledger"]["entries"]["UNIVERSAL:992447685"]["status"] == (
        "unresolved"
    )
    assert alerts == [
        {
            "title": "Shipping obligation uncertainty in prepacked exclusion scope",
            "lines": [
                "Target date: 2026-07-18",
                "Run identity: 2026-07-18T17:00:00+05:00",
                f"UNIVERSAL:992447685: {expected_detail}",
                "The obligations remain unresolved; only this validated exclusion scope is non-blocking.",
            ],
            "severity": "WARN",
            "dedup_key": (
                "shipping_obligation_uncertainty_excluded_scope:"
                "2026-07-18:2026-07-18T17:00:00+05:00"
            ),
        }
    ]


def test_reconcile_nine_covered_uncertainties_emit_one_aggregated_warning(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    order_ids = [f"ORDER-{index}" for index in range(1, 10)]
    alerts: list[dict[str, object]] = []
    monkeypatch.setattr(
        obligation_mod,
        "enqueue_alert",
        lambda **kwargs: alerts.append(kwargs) or False,
    )
    prior = {
        "schema_version": 1,
        "entries": {
            f"UNIVERSAL:{order_id}": {
                "store_code": "UNIVERSAL",
                "order_id": order_id,
                "status": "unresolved",
                "first_seen_target_date": "2026-07-17",
                "last_seen_target_date": "2026-07-17",
            }
            for order_id in order_ids
        },
    }

    result = reconcile_shipping_obligations(
        prior_ledger=prior,
        current_active_order_ids_by_store={},
        detail_results={
            f"UNIVERSAL:{order_id}": {"error": f"timeout-{index}"}
            for index, order_id in enumerate(order_ids, start=1)
        },
        target_date=date(2026, 7, 18),
        ready_set_at="2026-07-18T17:00:00+05:00",
        now=datetime(2026, 7, 18, 17, 0, 1, tzinfo=ALMATY),
        uncertainty_waiver_ids_by_store={"UNIVERSAL": set(order_ids)},
        enqueue_uncertainty_warnings=True,
    )

    assert result["ok"] is True
    assert result["uncertainty_scope_counts"] == {"covered": 9, "uncovered": 0}
    assert len(alerts) == 1
    assert alerts[0]["severity"] == "WARN"
    assert alerts[0]["dedup_key"] == (
        "shipping_obligation_uncertainty_excluded_scope:"
        "2026-07-18:2026-07-18T17:00:00+05:00"
    )
    alert_body = "\n".join(alerts[0]["lines"])
    for index, order_id in enumerate(order_ids, start=1):
        assert f"UNIVERSAL:{order_id}: timeout-{index}" in alert_body


def test_reconcile_uncovered_uncertainty_still_blocks_with_waiver_present() -> None:
    result = reconcile_shipping_obligations(
        prior_ledger=_prior_ledger(),
        current_active_order_ids_by_store={},
        detail_results={"UNIVERSAL:992447685": {"error": "timeout"}},
        target_date=date(2026, 7, 18),
        ready_set_at="2026-07-18T17:00:00+05:00",
        now=datetime(2026, 7, 18, 17, 0, 1, tzinfo=ALMATY),
        uncertainty_waiver_ids_by_store={"UNIVERSAL": {"OTHER-ORDER"}},
    )

    assert result["ok"] is False
    assert result["issues"][0]["code"] == "obligation_api_uncertain"
    assert result["uncertainty_scope_counts"] == {"covered": 0, "uncovered": 1}


def test_reconcile_exclusion_scope_does_not_waive_identity_mismatch() -> None:
    result = reconcile_shipping_obligations(
        prior_ledger=_prior_ledger(),
        current_active_order_ids_by_store={},
        detail_results={
            "UNIVERSAL:992447685": {"order": _order("DIFFERENT-ORDER")}
        },
        target_date=date(2026, 7, 18),
        ready_set_at="2026-07-18T17:00:00+05:00",
        now=datetime(2026, 7, 18, 17, 0, 1, tzinfo=ALMATY),
        uncertainty_waiver_ids_by_store={"UNIVERSAL": {"992447685"}},
    )

    assert result["ok"] is False
    assert result["issues"][0]["code"] == "obligation_api_identity_mismatch"
    assert result["uncertainty_scope_counts"] == {"covered": 0, "uncovered": 0}


def test_reconcile_exclusion_covered_handover_still_discharges_normally(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    alerts: list[dict[str, object]] = []
    monkeypatch.setattr(
        obligation_mod,
        "enqueue_alert",
        lambda **kwargs: alerts.append(kwargs) or False,
    )

    result = reconcile_shipping_obligations(
        prior_ledger=_prior_ledger(),
        current_active_order_ids_by_store={},
        detail_results={
            "UNIVERSAL:992447685": {
                "order": _order(
                    "992447685",
                    courier_transmission_date=1784383200000,
                )
            }
        },
        target_date=date(2026, 7, 18),
        ready_set_at="2026-07-18T17:00:00+05:00",
        now=datetime(2026, 7, 18, 17, 0, 1, tzinfo=ALMATY),
        uncertainty_waiver_ids_by_store={"UNIVERSAL": {"992447685"}},
        enqueue_uncertainty_warnings=True,
    )

    entry = result["ledger"]["entries"]["UNIVERSAL:992447685"]
    assert result["ok"] is True
    assert result["issues"] == []
    assert result["uncertainty_scope_counts"] == {"covered": 0, "uncovered": 0}
    assert entry["status"] == "discharged"
    assert entry["discharge_reason"] == "IN_DELIVERY"
    assert alerts == []


def test_reconcile_absent_uncertainty_waiver_keeps_legacy_result_contract() -> None:
    result = reconcile_shipping_obligations(
        prior_ledger=_prior_ledger(),
        current_active_order_ids_by_store={},
        detail_results={"UNIVERSAL:992447685": {"error": "timeout"}},
        target_date=date(2026, 7, 18),
        ready_set_at="2026-07-18T17:00:00+05:00",
        now=datetime(2026, 7, 18, 17, 0, 1, tzinfo=ALMATY),
    )

    assert set(result) == {
        "ok",
        "issues",
        "ledger",
        "active_order_ids_by_store",
    }
    assert result["ok"] is False
    assert result["issues"][0]["code"] == "obligation_api_uncertain"


def test_reconcile_adds_every_current_active_order_without_daily_approval() -> None:
    result = reconcile_shipping_obligations(
        prior_ledger={"schema_version": 1, "entries": {}},
        current_active_order_ids_by_store={
            "30000001_PP1": ["TODAY100"],
            "STOREB": ["OVERDUE101"],
        },
        detail_results={},
        target_date=date(2026, 7, 11),
        ready_set_at="2026-07-11T17:00:00+05:00",
        now=datetime(2026, 7, 11, 17, 0, 1, tzinfo=ALMATY),
    )

    assert result["ok"] is True
    assert active_obligation_ids_by_store(result["ledger"]) == {
        "STOREB": {"OVERDUE101"},
        "UNIVERSAL": {"TODAY100"},
    }
    assert result["ledger"]["request_identity"] == {
        "target_date": "2026-07-11",
        "ready_set_at": "2026-07-11T17:00:00+05:00",
    }
    assert "approval" not in json.dumps(result["ledger"]).lower()


def test_load_required_orders_file_identity_locks_target_and_store_mapping(tmp_path: Path) -> None:
    path = tmp_path / "expected_closeout_orders.json"
    path.write_text(
        json.dumps(
            {
                "target_date": "2026-07-11",
                "request_identity": {
                    "target_date": "2026-07-11",
                    "ready_set_at": "2026-07-11T17:00:00+05:00",
                },
                "expected_order_ids": ["TODAY100", "OVERDUE101"],
                "orders": [
                    {"order_id": "TODAY100", "store_code": "UNIVERSAL"},
                    {"order_id": "OVERDUE101", "store_code": "STORE-B"},
                ],
            }
        ),
        encoding="utf-8",
    )

    loaded = load_required_orders_file(path, target_date=date(2026, 7, 11))

    assert loaded["orders_by_store"] == {
        "STOREB": {"OVERDUE101"},
        "UNIVERSAL": {"TODAY100"},
    }
    assert len(loaded["sha256"]) == 64
    assert loaded["request_identity"]["ready_set_at"] == "2026-07-11T17:00:00+05:00"


def test_load_required_orders_file_rejects_unmapped_or_wrong_day(tmp_path: Path) -> None:
    path = tmp_path / "expected_closeout_orders.json"
    path.write_text(
        json.dumps(
            {
                "target_date": "2026-07-10",
                "expected_order_ids": ["UNMAPPED"],
                "orders": [],
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="target_date mismatch"):
        load_required_orders_file(path, target_date=date(2026, 7, 11))


def test_required_line_scope_rejects_parent_identity_override(tmp_path: Path) -> None:
    path = tmp_path / "expected_closeout_orders.json"
    child_lines = [
        {
            "db_row_id": "41",
            "store_code": "ACMEWEAR",
            "order_id": "TODAY100",
                "sku_key": "SKU-A",
                "sku_id": "SKU-A-L",
                "kaspi_offer_name": "Product A",
                "kaspi_name_core": "SKU-A",
            "quantity": 1,
            "final_size": "L",
        }
    ]
    path.write_text(
        json.dumps(
            {
                    "schema_version": 3,
                "target_date": "2026-07-11",
                "request_identity": {
                    "target_date": "2026-07-11",
                    "ready_set_at": "2026-07-11T17:00:00+05:00",
                },
                "expected_order_ids": ["TODAY100"],
                "orders": [
                    {
                        "order_id": "TODAY100",
                            "store_code": "UNIVERSAL",
                            "lines": child_lines,
                            "package_count": 1,
                    }
                ],
                "line_scope_hash": required_line_scope_hash(child_lines),
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="child line with mismatched identity"):
        load_required_orders_file(path, target_date=date(2026, 7, 11))
