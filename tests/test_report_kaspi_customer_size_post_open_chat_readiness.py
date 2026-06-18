import argparse
import json
from pathlib import Path

from scripts.report_kaspi_customer_size_post_open_chat_readiness import (
    GREEN_GATE,
    RED_GATE,
    YELLOW_OPEN_RESULT_GATE,
    build_report,
)


def _write_json(path: Path, payload: dict) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path


def _validation(tmp_path: Path, *, gate: str) -> Path:
    payload = {
        "gate": gate,
        "selected_order_ref": "sha256:order1",
        "selected_db_row_id": 36170,
        "selected_store_code": "ACMEWEAR",
        "expected_merchant_account_id": "30137883",
        "accepted": gate == "GREEN_OPEN_CHAT_NO_TYPE_CANARY_RESULT_ACCEPTED_NO_SEND",
        "raw_order_id_exported": False,
        "raw_customer_text_exported": False,
        "raw_phone_exported": False,
        "raw_session_material_exported": False,
        "message_text_typed": False,
        "message_sent": False,
    }
    return _write_json(tmp_path / "open_validation.json", payload)


def _approval(tmp_path: Path) -> Path:
    return _write_json(
        tmp_path / "approval" / "manifest.json",
        {
            "gate": "GREEN_LIVE_SEND_CANARY_APPROVAL_PACKET_READY_NO_SEND",
            "selected_order_ref": "sha256:order1",
            "selected_db_row_id": 36170,
            "selected_store_code": "ACMEWEAR",
            "template_hash": "template-hash",
            "expected_merchant_account_id": "30137883",
        },
    )


def _preflight(tmp_path: Path) -> Path:
    return _write_json(
        tmp_path / "preflight" / "manifest.json",
        {
            "gate": "GREEN_LIVE_SEND_CANARY_EXECUTION_PREFLIGHT_READY_NO_SEND",
            "selected_order_ref": "sha256:order1",
            "selected_db_row_id": 36170,
            "selected_store_code": "ACMEWEAR",
            "template_hash": "template-hash",
            "expected_merchant_account_id": "30137883",
        },
    )


def _heartbeat(tmp_path: Path, *, green: bool = True) -> Path:
    return _write_json(
        tmp_path / "heartbeat.json",
        {
            "gate": (
                "GREEN_KASPI_CUSTOMER_CHAT_RESIDENT_NO_SEND_CONTROLLER_READY"
                if green
                else "YELLOW_KASPI_CUSTOMER_CHAT_RESIDENT_NO_SEND_CONTROLLER_WAITING_FOR_LOGIN"
            ),
            "orders_search_input_visible": green,
            "browser_should_remain_open": True,
            "customer_send_allowed": False,
            "kaspi_chat_write_allowed": False,
            "chat_opened": False,
            "message_text_typed": False,
            "message_sent": False,
            "raw_order_id_exported": False,
            "raw_customer_text_exported": False,
            "raw_phone_exported": False,
            "raw_session_material_exported": False,
        },
    )


def _args(
    tmp_path: Path,
    *,
    validation_gate: str,
    heartbeat_green: bool = True,
) -> argparse.Namespace:
    return argparse.Namespace(
        open_chat_packet_dir=tmp_path / "packet",
        open_chat_validation_json=_validation(tmp_path, gate=validation_gate),
        live_send_approval_manifest=_approval(tmp_path),
        live_send_preflight_manifest=_preflight(tmp_path),
        resident_current_heartbeat=_heartbeat(tmp_path, green=heartbeat_green),
        output_dir=tmp_path / "out",
    )


def test_post_open_chat_readiness_blocks_until_open_result_is_accepted(tmp_path):
    manifest = build_report(
        _args(
            tmp_path,
            validation_gate="YELLOW_OPEN_CHAT_NO_TYPE_CANARY_RESULT_MISSING",
        )
    )

    assert manifest["gate"] == YELLOW_OPEN_RESULT_GATE
    assert "open_chat_result_not_accepted:YELLOW_OPEN_CHAT_NO_TYPE_CANARY_RESULT_MISSING" in manifest["blockers"]
    assert manifest["customer_send_performed"] is False
    assert manifest["browser_action_performed"] is False


def test_post_open_chat_readiness_green_when_all_target_surfaces_align(tmp_path):
    manifest = build_report(
        _args(
            tmp_path,
            validation_gate="GREEN_OPEN_CHAT_NO_TYPE_CANARY_RESULT_ACCEPTED_NO_SEND",
        )
    )

    assert manifest["gate"] == GREEN_GATE
    assert manifest["selected_db_row_id"] == 36170
    assert manifest["expected_merchant_account_id"] == "30137883"
    assert manifest["customer_send_allowed_by_this_gate"] is False


def test_post_open_chat_readiness_red_when_open_result_validator_is_red(tmp_path):
    manifest = build_report(
        _args(
            tmp_path,
            validation_gate="RED_OPEN_CHAT_NO_TYPE_UNSAFE_FLAGS",
        )
    )

    assert manifest["gate"] == RED_GATE
    assert "open_chat_validation_red:RED_OPEN_CHAT_NO_TYPE_UNSAFE_FLAGS" in manifest["unsafe_blockers"]


def test_post_open_chat_readiness_blocks_when_current_heartbeat_is_not_green(tmp_path):
    manifest = build_report(
        _args(
            tmp_path,
            validation_gate="GREEN_OPEN_CHAT_NO_TYPE_CANARY_RESULT_ACCEPTED_NO_SEND",
            heartbeat_green=False,
        )
    )

    assert manifest["gate"] == (
        "YELLOW_POST_OPEN_CHAT_SEQUENCE_BLOCKED_LIVE_SEND_PREFLIGHT_NOT_READY_NO_EXTERNAL_WRITE"
    )
    assert "resident_heartbeat_not_green:YELLOW_KASPI_CUSTOMER_CHAT_RESIDENT_NO_SEND_CONTROLLER_WAITING_FOR_LOGIN" in manifest["blockers"]
    assert "resident_orders_search_input_not_visible" in manifest["blockers"]
