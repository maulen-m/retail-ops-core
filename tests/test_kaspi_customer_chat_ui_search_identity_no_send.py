from datetime import date
from pathlib import Path

from core.ops.customer_size_request import OrderCandidate
from scripts.probe_kaspi_customer_chat_ui_search_identity_no_send import (
    GREEN_CHAT_BUTTON_GATE,
    GREEN_GATE,
    RED_GATE,
    SESSION_CLOSE_GUARD_BLOCKER,
    YELLOW_SESSION_PRESERVATION_GATE,
    YELLOW_CHAT_BUTTON_GATE,
    YELLOW_GATE,
    build_payload,
    build_parser,
    build_session_preservation_guard_payload,
    merchant_account_id_for_store,
    plan_probes,
    validate_redacted_payload,
    _safe_url,
)


def _candidate(
    raw_order_id: str = "938710785",
    *,
    store_code: str = "ACMEWEAR",
    internal_status: str = "ACCEPTED",
    kaspi_status: str = "KASPI_DELIVERY",
) -> OrderCandidate:
    return OrderCandidate(
        db_row_id=1,
        raw_order_id=raw_order_id,
        order_ref="sha256:order-ref",
        store_code=store_code,
        sku_key="CL_LINE31_TEST",
        sku_id="CL_LINE31_TEST_M",
        product_type="CL",
        internal_status=internal_status,
        kaspi_status=kaspi_status,
        planned_shipment_date="2026-06-17",
        created_at="2026-06-17 09:00:00",
        reason_codes=("missing_size",),
    )


def test_plan_probes_keeps_explicit_multistore_candidates_for_selector_runtime():
    plans = plan_probes(
        [
            _candidate(store_code="ACMEWEAR"),
            _candidate(raw_order_id="938710786", store_code="STOREB"),
        ],
        profile_store_code="ACMEWEAR",
        max_candidates=5,
    )

    assert len(plans) == 2
    assert plans[0].candidate.store_code == "ACMEWEAR"
    assert plans[0].status_filter == "KASPI_DELIVERY_CARGO_ASSEMBLY"
    assert plans[1].candidate.store_code == "STOREB"
    assert plans[1].status_filter == "KASPI_DELIVERY_CARGO_ASSEMBLY"


def test_merchant_account_id_mapping_matches_kaspi_selector_ids():
    assert merchant_account_id_for_store("UNIVERSAL") == "30000001"
    assert merchant_account_id_for_store("ACMEWEAR") == "30137883"
    assert merchant_account_id_for_store("STOREB") == "30000002"
    assert merchant_account_id_for_store("MELVIS") == "30362323"
    assert merchant_account_id_for_store("11KZ") == "30290083"
    assert merchant_account_id_for_store("UNKNOWN") == ""


def test_direct_probe_defaults_to_preserving_authenticated_session(tmp_path):
    parser = build_parser()
    args = parser.parse_args([])
    allowed = parser.parse_args(["--allow-session-close"])

    assert args.allow_session_close is False
    assert allowed.allow_session_close is True

    payload = build_session_preservation_guard_payload(
        output_dir=tmp_path,
        target_date=date(2026, 6, 18),
        lookback_days=5,
        profile_store_code="ACMEWEAR",
        persistent_profile_dir=tmp_path / "profile",
    )

    assert payload["gate"] == YELLOW_SESSION_PRESERVATION_GATE
    assert SESSION_CLOSE_GUARD_BLOCKER in payload["blockers"]
    assert payload["browser_context_launched"] is False
    assert payload["browser_closed_by_probe"] is False
    assert payload["session_close_requires_explicit_allow_session_close"] is True
    assert payload["customer_send_allowed"] is False
    assert payload["kaspi_chat_write_allowed"] is False
    assert payload["message_sent"] is False


def test_safe_url_redacts_order_detail_path_ids():
    raw_order_id = "938" + "710785"
    safe = _safe_url(f"https://kaspi.kz/mc/#/orders/{raw_order_id}?foo=bar")

    assert safe == "https://kaspi.kz/mc/#/orders/[redacted]?[redacted]"
    assert raw_order_id not in safe


def test_validate_redacted_payload_rejects_raw_order_id_value():
    payload = {
        "customer_send_allowed": False,
        "kaspi_chat_write_allowed": False,
        "chat_opened": False,
        "message_sent": False,
        "raw_order_id_exported": False,
        "leak": "938710785",
    }

    blockers = validate_redacted_payload(payload, ["938710785"])

    assert "raw_order_id_value_detected" in blockers


def test_build_payload_green_when_visible_result_without_raw_export():
    candidate = _candidate()
    plans = plan_probes([candidate], profile_store_code="ACMEWEAR", max_candidates=1)
    payload = build_payload(
        output_dir=Path("out"),
        target_date=date(2026, 6, 17),
        lookback_days=5,
        profile_store_code="ACMEWEAR",
        persistent_profile_dir=Path("profile"),
        plans=plans,
        results=[
            {
                "db_row_id": 1,
                "order_ref": candidate.order_ref,
                "store_code": "ACMEWEAR",
                "expected_merchant_account_id": merchant_account_id_for_store("ACMEWEAR"),
                "merchant_account_selector_matched": True,
                "merchant_account_match_proven": True,
                "status_filter": "KASPI_DELIVERY_CARGO_ASSEMBLY",
                "result_or_detail_reached": True,
                "chat_button_present": False,
                "chat_opened": False,
                "message_sent": False,
                "raw_order_id_exported": False,
            }
        ],
        unsafe_events=[],
        raw_order_ids=[candidate.raw_order_id],
    )

    assert payload["gate"] == GREEN_GATE
    assert candidate.raw_order_id not in str(payload)
    assert merchant_account_id_for_store("ACMEWEAR") in str(payload)
    assert payload["customer_send_allowed"] is False
    assert payload["kaspi_chat_write_allowed"] is False


def test_build_payload_requires_merchant_match_for_identity_green():
    candidate = _candidate()
    plans = plan_probes([candidate], profile_store_code="ACMEWEAR", max_candidates=1)
    payload = build_payload(
        output_dir=Path("out"),
        target_date=date(2026, 6, 17),
        lookback_days=5,
        profile_store_code="ACMEWEAR",
        persistent_profile_dir=Path("profile"),
        plans=plans,
        results=[
            {
                "db_row_id": 1,
                "order_ref": candidate.order_ref,
                "store_code": "ACMEWEAR",
                "expected_merchant_account_id": merchant_account_id_for_store("ACMEWEAR"),
                "merchant_account_match_proven": False,
                "status_filter": "KASPI_DELIVERY_CARGO_ASSEMBLY",
                "result_or_detail_reached": True,
                "chat_button_present": False,
                "chat_opened": False,
                "message_sent": False,
                "raw_order_id_exported": False,
            }
        ],
        unsafe_events=[],
        raw_order_ids=[candidate.raw_order_id],
    )

    assert payload["gate"] == YELLOW_GATE
    assert payload["found_result_count"] == 0
    assert payload["unqualified_found_result_count"] == 1
    assert payload["customer_send_allowed"] is False


def test_build_payload_requires_chat_button_when_requested():
    candidate = _candidate()
    plans = plan_probes([candidate], profile_store_code="ACMEWEAR", max_candidates=1)
    payload = build_payload(
        output_dir=Path("out"),
        target_date=date(2026, 6, 17),
        lookback_days=5,
        profile_store_code="ACMEWEAR",
        persistent_profile_dir=Path("profile"),
        plans=plans,
        results=[
            {
                "db_row_id": 1,
                "order_ref": candidate.order_ref,
                "store_code": "ACMEWEAR",
                "result_or_detail_reached": True,
                "chat_button_present": False,
                "merchant_account_match_proven": True,
                "chat_opened": False,
                "message_sent": False,
                "raw_order_id_exported": False,
            }
        ],
        unsafe_events=[],
        raw_order_ids=[candidate.raw_order_id],
        require_chat_button=True,
    )

    assert payload["gate"] == YELLOW_CHAT_BUTTON_GATE
    assert payload["found_result_count"] == 1
    assert payload["chat_button_found_count"] == 0


def test_build_payload_green_when_chat_button_is_proven_no_send():
    candidate = _candidate()
    plans = plan_probes([candidate], profile_store_code="ACMEWEAR", max_candidates=1)
    payload = build_payload(
        output_dir=Path("out"),
        target_date=date(2026, 6, 17),
        lookback_days=5,
        profile_store_code="ACMEWEAR",
        persistent_profile_dir=Path("profile"),
        plans=plans,
        results=[
            {
                "db_row_id": 1,
                "order_ref": candidate.order_ref,
                "store_code": "ACMEWEAR",
                "result_or_detail_reached": True,
                "chat_button_present": True,
                "merchant_account_match_proven": True,
                "chat_opened": False,
                "message_sent": False,
                "raw_order_id_exported": False,
            }
        ],
        unsafe_events=[],
        raw_order_ids=[candidate.raw_order_id],
        require_chat_button=True,
    )

    assert payload["gate"] == GREEN_CHAT_BUTTON_GATE
    assert payload["chat_button_found_count"] == 1
    assert candidate.raw_order_id not in str(payload)


def test_build_payload_requires_merchant_match_for_chat_button_green():
    candidate = _candidate()
    plans = plan_probes([candidate], profile_store_code="ACMEWEAR", max_candidates=1)
    payload = build_payload(
        output_dir=Path("out"),
        target_date=date(2026, 6, 17),
        lookback_days=5,
        profile_store_code="ACMEWEAR",
        persistent_profile_dir=Path("profile"),
        plans=plans,
        results=[
            {
                "db_row_id": 1,
                "order_ref": candidate.order_ref,
                "store_code": "ACMEWEAR",
                "result_or_detail_reached": True,
                "chat_button_present": True,
                "merchant_account_match_proven": False,
                "chat_opened": False,
                "message_sent": False,
                "raw_order_id_exported": False,
            }
        ],
        unsafe_events=[],
        raw_order_ids=[candidate.raw_order_id],
        require_chat_button=True,
    )

    assert payload["gate"] == YELLOW_CHAT_BUTTON_GATE
    assert payload["chat_button_found_count"] == 0
    assert payload["unqualified_chat_button_found_count"] == 1


def test_build_payload_yellow_when_no_visible_result():
    candidate = _candidate()
    plans = plan_probes([candidate], profile_store_code="ACMEWEAR", max_candidates=1)
    payload = build_payload(
        output_dir=Path("out"),
        target_date=date(2026, 6, 17),
        lookback_days=5,
        profile_store_code="ACMEWEAR",
        persistent_profile_dir=Path("profile"),
        plans=plans,
        results=[
            {
                "db_row_id": 1,
                "order_ref": candidate.order_ref,
                "store_code": "ACMEWEAR",
                "status_filter": "KASPI_DELIVERY_CARGO_ASSEMBLY",
                "result_or_detail_reached": False,
                "chat_button_present": False,
                "chat_opened": False,
                "message_sent": False,
                "raw_order_id_exported": False,
            }
        ],
        unsafe_events=[],
        raw_order_ids=[candidate.raw_order_id],
    )

    assert payload["gate"] == YELLOW_GATE
    assert payload["found_result_count"] == 0


def test_build_payload_red_when_unsafe_route_observed():
    candidate = _candidate()
    plans = plan_probes([candidate], profile_store_code="ACMEWEAR", max_candidates=1)
    payload = build_payload(
        output_dir=Path("out"),
        target_date=date(2026, 6, 17),
        lookback_days=5,
        profile_store_code="ACMEWEAR",
        persistent_profile_dir=Path("profile"),
        plans=plans,
        results=[],
        unsafe_events=[
            {
                "kind": "request",
                "method": "POST",
                "host": "msg-web.kaspi.kz",
                "path_template": "/paychat/api/v1/messages/sendMessage",
                "blocked_by_probe": True,
            }
        ],
        raw_order_ids=[candidate.raw_order_id],
    )

    assert payload["gate"] == RED_GATE
    assert "unsafe_chat_route_observed_or_blocked" in payload["blockers"]
