import argparse
import hashlib
import json
from pathlib import Path

from scripts.validate_kaspi_customer_chat_open_no_type_canary_result import (
    ACCEPTED_GATE,
    RESULT_GREEN_GATE,
    RESULT_MISSING_GATE,
    validate,
)


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _packet_dir(tmp_path: Path) -> Path:
    packet_dir = tmp_path / "packet"
    lock_path = packet_dir / "open_chat_no_type_packet_lock.json"
    lock = {
        "gate": "GREEN_OPEN_CHAT_NO_TYPE_CANARY_PACKET_READY_NO_SEND",
        "selected_order_ref": "sha256:order1",
        "selected_db_row_id": 36170,
        "selected_store_code": "ACMEWEAR",
        "selected_status_filter": "NEW",
        "expected_merchant_account_id": "30137883",
        "customer_send_allowed_now": False,
        "kaspi_chat_write_allowed_now": False,
        "raw_order_id_exported": False,
        "raw_customer_text_exported": False,
        "raw_phone_exported": False,
        "raw_session_material_exported": False,
        "blockers": [],
    }
    _write_json(lock_path, lock)
    _write_json(
        packet_dir / "manifest.json",
        {
            **lock,
            "approval_phrase_generated": True,
            "packet_manifest_path": str(lock_path.resolve()),
            "packet_manifest_sha256": hashlib.sha256(lock_path.read_bytes()).hexdigest(),
            "message_text_typed": False,
            "message_sent": False,
        },
    )
    return packet_dir


def _result(**overrides):
    payload = {
        "gate": RESULT_GREEN_GATE,
        "selected_order_ref": "sha256:order1",
        "selected_db_row_id": 36170,
        "selected_store_code": "ACMEWEAR",
        "selected_status_filter": "NEW",
        "expected_merchant_account_id": "30137883",
        "visible_merchant_selector_id": "30137883",
        "merchant_account_match_proven": True,
        "order_search_performed": True,
        "chat_opened": True,
        "message_text_typed": False,
        "message_sent": False,
        "customer_send_performed": False,
        "kaspi_chat_write_performed": False,
        "send_message_route_observed": False,
        "typing_send_text_route_observed": False,
        "start_chat_route_observed": False,
        "message_status_change_route_observed": False,
        "load_more_messages_route_observed": False,
        "browser_session_preserved": True,
        "other_customer_messages_sent": False,
        "raw_order_id_exported": False,
        "raw_customer_text_exported": False,
        "raw_phone_exported": False,
        "raw_session_material_exported": False,
        "cookie_token_session_exported": False,
    }
    payload.update(overrides)
    return payload


def _closeout(packet_dir: Path) -> None:
    (packet_dir / "open_chat_no_type_canary_closeout.md").write_text(
        "# Closeout\n\nGate: GREEN_OPEN_CHAT_NO_TYPE_SIDE_EFFECT_CANARY_COMPLETED_NO_SEND\n",
        encoding="utf-8",
    )


def _args(packet_dir: Path, *, output_json: Path | None = None) -> argparse.Namespace:
    return argparse.Namespace(
        packet_dir=packet_dir,
        result_json=None,
        closeout_md=None,
        output_json=output_json,
        require_green=False,
    )


def test_open_no_type_validator_waits_for_result(tmp_path):
    packet_dir = _packet_dir(tmp_path)

    validation = validate(_args(packet_dir))

    assert validation["gate"] == RESULT_MISSING_GATE
    assert "open_chat_no_type_result_missing" in validation["blockers"]


def test_open_no_type_validator_accepts_green_result(tmp_path):
    packet_dir = _packet_dir(tmp_path)
    _write_json(packet_dir / "open_chat_no_type_result_redacted.json", _result())
    _closeout(packet_dir)

    validation = validate(_args(packet_dir))

    assert validation["gate"] == ACCEPTED_GATE
    assert validation["accepted"] is True
    assert validation["checks"]["visible_merchant_selector_id"] == "30137883"
    assert validation["checks"]["unsafe_false_fields_true_or_missing"] == []


def test_open_no_type_validator_allows_read_side_effect_warnings(tmp_path):
    packet_dir = _packet_dir(tmp_path)
    _write_json(
        packet_dir / "open_chat_no_type_result_redacted.json",
        _result(message_status_change_route_observed=True, load_more_messages_route_observed=True),
    )
    _closeout(packet_dir)

    validation = validate(_args(packet_dir))

    assert validation["gate"] == ACCEPTED_GATE
    assert "message_status_change_route_observed" in validation["warnings"]
    assert "load_more_messages_route_observed" in validation["warnings"]


def test_open_no_type_validator_rejects_wrong_selector(tmp_path):
    packet_dir = _packet_dir(tmp_path)
    _write_json(
        packet_dir / "open_chat_no_type_result_redacted.json",
        _result(visible_merchant_selector_id="30000001"),
    )
    _closeout(packet_dir)

    validation = validate(_args(packet_dir))

    assert validation["gate"] == "RED_OPEN_CHAT_NO_TYPE_VISIBLE_MERCHANT_SELECTOR_MISMATCH"
    assert "visible_merchant_selector_id_mismatch" in validation["blockers"]


def test_open_no_type_validator_rejects_typed_or_sent(tmp_path):
    packet_dir = _packet_dir(tmp_path)
    _write_json(
        packet_dir / "open_chat_no_type_result_redacted.json",
        _result(message_text_typed=True, message_sent=True),
    )
    _closeout(packet_dir)

    validation = validate(_args(packet_dir))

    assert validation["gate"] == "RED_OPEN_CHAT_NO_TYPE_UNSAFE_FLAGS"
    assert "unsafe_flags" in validation["blockers"]
    assert "message_text_typed" in validation["checks"]["unsafe_false_fields_true_or_missing"]
    assert "message_sent" in validation["checks"]["unsafe_false_fields_true_or_missing"]


def test_open_no_type_validator_rejects_send_or_typing_routes(tmp_path):
    packet_dir = _packet_dir(tmp_path)
    _write_json(
        packet_dir / "open_chat_no_type_result_redacted.json",
        _result(send_message_route_observed=True, typing_send_text_route_observed=True),
    )
    _closeout(packet_dir)

    validation = validate(_args(packet_dir))

    assert validation["gate"] == "RED_OPEN_CHAT_NO_TYPE_UNSAFE_FLAGS"
    assert "send_message_route_observed" in validation["checks"]["unsafe_false_fields_true_or_missing"]
    assert "typing_send_text_route_observed" in validation["checks"]["unsafe_false_fields_true_or_missing"]


def test_open_no_type_validator_preserves_red_resident_gate_and_unsafe_blockers(tmp_path):
    packet_dir = _packet_dir(tmp_path)
    _write_json(
        packet_dir / "open_chat_no_type_result_redacted.json",
        _result(
            gate="RED_KASPI_CUSTOMER_CHAT_OPEN_CHAT_NO_TYPE_UNSAFE_NO_ACTION",
            chat_opened=False,
            merchant_account_match_proven=False,
            order_search_performed=False,
            browser_session_preserved=False,
            unsafe_blockers=["send_typing_or_start_chat_route_observed"],
        ),
    )
    _closeout(packet_dir)

    validation = validate(_args(packet_dir))

    assert validation["gate"] == "RED_OPEN_CHAT_NO_TYPE_RESULT_RED"
    assert "result_gate_red:RED_KASPI_CUSTOMER_CHAT_OPEN_CHAT_NO_TYPE_UNSAFE_NO_ACTION" in validation["blockers"]
    assert "resident_unsafe_blocker:send_typing_or_start_chat_route_observed" in validation["blockers"]


def test_open_no_type_validator_rejects_phone_like_text(tmp_path):
    packet_dir = _packet_dir(tmp_path)
    _write_json(
        packet_dir / "open_chat_no_type_result_redacted.json",
        _result(proof_note="+7 777 111 22 33"),
    )
    _closeout(packet_dir)

    validation = validate(_args(packet_dir))

    assert validation["gate"] == "RED_OPEN_CHAT_NO_TYPE_REDACTION_SCAN_FAILED"
    assert validation["violations"][0]["violation"] == "phone_like"
