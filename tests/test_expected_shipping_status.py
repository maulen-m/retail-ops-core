from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Any, Mapping

import pytest

from core.ops.expected_shipping_status import (
    POLICIES,
    ExpectedShippingFacts,
    api_fallback,
    board_render,
    carryforward,
    decide_expected_shipping_status,
    expected_orders,
    obligations,
    prewindow,
    waybill_split,
)


FIXTURE_ROOT = Path(__file__).parent / "fixtures" / "expected_status"
WORLD = json.loads((FIXTURE_ROOT / "synthetic_world.json").read_text(encoding="utf-8"))
GOLDEN = json.loads(
    (FIXTURE_ROOT / "expected_status_goldens.json").read_text(encoding="utf-8")
)
TARGET_DATE = date.fromisoformat(WORLD["target_date"])
ORDERS = tuple(WORLD["orders"])
ORDERS_BY_KEY = {order["key"]: order for order in ORDERS}
SYNTHETIC_GOLDEN = GOLDEN["synthetic"]


def _facts(
    order: Mapping[str, Any],
    *,
    active_selector_member: bool | None = None,
) -> ExpectedShippingFacts:
    return ExpectedShippingFacts.from_mapping(
        order,
        target_date=TARGET_DATE,
        active_selector_member=active_selector_member,
    )


def _serial_ids(values: Mapping[str, set[str]]) -> dict[str, list[str]]:
    return {
        store: sorted(order_ids) for store, order_ids in sorted(values.items())
    }


def _carryforward_projection() -> dict[str, list[str]]:
    result: dict[str, set[str]] = {}
    for order in ORDERS:
        decision = carryforward.evaluate(_facts(order))
        if decision.projection:
            result.setdefault(decision.normalized_store, set()).add(decision.order_id)
    return _serial_ids(result)


def _matrix_expected(policy_name: str, order: Mapping[str, Any]) -> Any:
    key = order["key"]
    order_id = order["order_id"]
    if policy_name in {"board_render", "prewindow"}:
        # Prewindow parity rebuilds the same preserved Board payload. The aggregate
        # prewindow capture below proves that replay is green.
        return SYNTHETIC_GOLDEN["site_1_google_board"]["orders"][key]
    if policy_name == "expected_orders":
        return SYNTHETIC_GOLDEN["site_2_expected_orders"]["unfiltered"][
            "orders"
        ].get(order_id)
    if policy_name == "obligations":
        return SYNTHETIC_GOLDEN["site_3_shipping_obligations"]["orders"][key]
    if policy_name == "carryforward":
        return order_id in SYNTHETIC_GOLDEN["site_4_waybill_overdue"].get(
            "UNIVERSAL", []
        )
    if policy_name == "waybill_split":
        planned = date.fromisoformat(order["planned_date"])
        if planned < TARGET_DATE:
            assert "overdue_only" in SYNTHETIC_GOLDEN["site_7_daily_waybills"][
                "overdue_groups"
            ]
            return "OVERDUE"
        if planned > TARGET_DATE:
            assert "future_is_rendered_today" in SYNTHETIC_GOLDEN[
                "site_7_daily_waybills"
            ]["today_groups"]
        else:
            assert "today_only" in SYNTHETIC_GOLDEN["site_7_daily_waybills"][
                "today_groups"
            ]
        return "TODAY"
    if policy_name == "api_fallback":
        # Every synthetic order carries an explicit planned date. The captured API
        # rule says that explicit planned date wins over creation-time fallback.
        assert (
            SYNTHETIC_GOLDEN["site_7_daily_waybills"]["api_date_fallbacks"][
                "explicit_planned_wins"
            ]
            == "2026-07-19"
        )
        return order["planned_date"]
    raise AssertionError(f"unhandled policy: {policy_name}")


@pytest.mark.parametrize("policy", POLICIES, ids=lambda policy: policy.name)
@pytest.mark.parametrize("order", ORDERS, ids=lambda order: order["key"])
def test_every_synthetic_order_matches_each_policy_golden(policy, order) -> None:
    decision = decide_expected_shipping_status(_facts(order), policy=policy)
    assert decision.projection == _matrix_expected(policy.name, order)


@pytest.mark.parametrize("order", ORDERS, ids=lambda order: order["key"])
def test_stage_delegation_matches_classifier_golden(order) -> None:
    facts = _facts(order)
    assert {
        "api_stage": facts.api_stage.value,
        "db_stage": facts.db_stage.value,
    } == SYNTHETIC_GOLDEN["site_6_stage_classifier"][order["key"]]


@pytest.mark.parametrize("order", ORDERS, ids=lambda order: order["key"])
def test_active_filtered_expected_order_policy_matches_golden(order) -> None:
    decision = expected_orders.evaluate(_facts(order, active_selector_member=True))
    assert decision.projection == SYNTHETIC_GOLDEN["site_2_expected_orders"][
        "active_filtered"
    ]["orders"].get(order["order_id"])


def test_prewindow_aggregate_capture_is_green() -> None:
    captured = SYNTHETIC_GOLDEN["site_5_prewindow_parity"]
    assert captured["ok"] is True
    assert captured["issues"] == []
    assert all(tab["ok"] for tab in captured["tabs"].values())
    assert prewindow.evaluate(_facts(ORDERS[0])).projection == board_render.evaluate(
        _facts(ORDERS[0])
    ).projection


@pytest.mark.parametrize("case", WORLD["group_cases"], ids=lambda case: case["key"])
def test_waybill_split_cases_match_daily_waybill_golden(case) -> None:
    lines = [
        {
            "store_code": case["store"],
            "order_id": "GROUP-" + case["key"],
            "planned_date": planned_date,
        }
        for planned_date in case["planned_dates"]
    ]
    decision = waybill_split.evaluate(
        ExpectedShippingFacts.from_lines(lines, target_date=TARGET_DATE)
    )
    expected = (
        "OVERDUE"
        if case["key"]
        in SYNTHETIC_GOLDEN["site_7_daily_waybills"]["overdue_groups"]
        else "TODAY"
    )
    assert decision.projection == expected


@pytest.mark.parametrize("case", WORLD["api_date_cases"], ids=lambda case: case["key"])
def test_api_date_cases_match_daily_waybill_golden(case) -> None:
    line = {
        **case,
        "order_id": "API-" + case["key"],
    }
    decision = api_fallback.evaluate(
        ExpectedShippingFacts.from_mapping(line, target_date=TARGET_DATE)
    )
    assert decision.projection == SYNTHETIC_GOLDEN["site_7_daily_waybills"][
        "api_date_fallbacks"
    ][case["key"]]


def test_divergence_policy_metadata_matches_registry() -> None:
    registry_ids = {entry["id"] for entry in GOLDEN["known_divergences"]}
    policy_ids = {
        divergence_id
        for policy in POLICIES
        for divergence_id in policy.divergence_ids
    }
    assert policy_ids == registry_ids
    for policy in POLICIES:
        docstring = policy.__class__.__doc__ or ""
        for divergence_id in policy.divergence_ids:
            assert divergence_id in docstring


def test_divergence_store_alias_collision_reproduces_both_sides() -> None:
    entry = GOLDEN["known_divergences"][0]
    values = {
        "Universal": ["G01"],
        "UNIVERSAL": ["G02"],
        "30000001_PP1": ["G03"],
    }
    assert _serial_ids(expected_orders.normalize_active_order_ids_by_store(values)) == entry[
        "outputs"
    ]["expected_orders_normalizer"]
    assert _serial_ids(obligations.normalize_active_order_ids_by_store(values)) == entry[
        "outputs"
    ]["obligation_normalizer"]


def test_divergence_archive_ambiguity_reproduces_both_sides() -> None:
    entry = GOLDEN["known_divergences"][1]
    facts = _facts(ORDERS_BY_KEY[entry["input_key"]])
    assert {
        "api_stage": facts.api_stage.value,
        "db_stage": facts.db_stage.value,
    } == entry["outputs"]["stage_classifier"]
    assert obligations.evaluate(facts).projection == entry["outputs"][
        "obligation_classifier"
    ]


def test_divergence_same_day_after_cutoff_reproduces_both_sides() -> None:
    entry = GOLDEN["known_divergences"][2]
    facts = _facts(ORDERS_BY_KEY[entry["input_key"]])
    assert board_render.evaluate(facts).projection == entry["outputs"]["board"]
    assert expected_orders.evaluate(facts).projection == entry["outputs"][
        "expected_orders_unfiltered"
    ]


def test_divergence_overdue_without_waybill_reproduces_both_sides() -> None:
    entry = GOLDEN["known_divergences"][3]
    facts = _facts(ORDERS_BY_KEY[entry["input_key"]])
    assert board_render.evaluate(facts).projection == entry["outputs"]["board"]
    assert _carryforward_projection() == entry["outputs"][
        "waybill_overdue_ids_by_store"
    ]


def test_divergence_active_terminal_trust_reproduces_both_sides() -> None:
    entry = GOLDEN["known_divergences"][4]
    order = ORDERS_BY_KEY[entry["input_key"]]
    assert expected_orders.evaluate(
        _facts(order, active_selector_member=True)
    ).projection == entry["outputs"]["expected_orders_active_filtered"]
    assert obligations.evaluate(_facts(order)).projection == entry["outputs"][
        "obligations"
    ]
