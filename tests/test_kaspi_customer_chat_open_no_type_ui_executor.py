import argparse
import hashlib
import json
from pathlib import Path

from scripts.run_kaspi_customer_chat_open_no_type_canary_ui_executor import (
    AWAITING_APPROVAL_GATE,
    ENV_GATE,
    READY_GATE,
    RESULT_GREEN_GATE,
    UNSAFE_GATE,
    run,
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
        "future_action": "open_exactly_one_selected_chat_type_nothing_send_nothing_capture_sanitized_metadata",
        "raw_order_id_exported": False,
        "raw_customer_text_exported": False,
        "raw_phone_exported": False,
        "raw_session_material_exported": False,
        "blockers": [],
    }
    _write_json(lock_path, lock)
    manifest = {
        **lock,
        "output_dir": str(packet_dir.resolve()),
        "approval_phrase_generated": True,
        "packet_manifest_path": str(lock_path.resolve()),
        "packet_manifest_sha256": hashlib.sha256(lock_path.read_bytes()).hexdigest(),
        "chat_opened_by_this_builder": False,
        "customer_send_performed": False,
        "kaspi_chat_write_performed": False,
        "message_text_typed": False,
        "message_sent": False,
    }
    _write_json(packet_dir / "manifest.json", manifest)
    phrase = (
        "I approve KASPI_CUSTOMER_SIZE_OPEN_CHAT_NO_TYPE_SIDE_EFFECT_CANARY_ONE_ORDER_20260618: "
        "open exactly one chat, type nothing, send nothing."
    )
    (packet_dir / "REQUIRED_EXACT_OPEN_CHAT_NO_TYPE_APPROVAL_PHRASE.txt").write_text(
        phrase + "\n",
        encoding="utf-8",
    )
    return packet_dir


def _approval_text_file(tmp_path: Path, packet_dir: Path, *, text: str | None = None) -> Path:
    phrase = (
        packet_dir / "REQUIRED_EXACT_OPEN_CHAT_NO_TYPE_APPROVAL_PHRASE.txt"
    ).read_text(encoding="utf-8")
    path = tmp_path / "owner_approval.txt"
    path.write_text(text if text is not None else phrase, encoding="utf-8")
    return path


def _args(
    tmp_path: Path,
    *,
    packet_dir: Path,
    approval_text_file: Path | None = None,
    apply: bool = False,
    record: bool = False,
    selector_id: str = "30137883",
    send_route: bool = False,
) -> argparse.Namespace:
    return argparse.Namespace(
        packet_dir=packet_dir,
        output_dir=tmp_path / "out",
        approval_text_file=approval_text_file,
        approval_from_stdin=False,
        apply=apply,
        record_observed_open_result=record,
        visible_merchant_selector_id=selector_id,
        proof_source="test_ui_helper",
        proof_note="redacted proof",
        send_message_route_observed=send_route,
        typing_send_text_route_observed=False,
        start_chat_route_observed=False,
        message_status_change_route_observed=False,
        load_more_messages_route_observed=False,
    )


def test_open_no_type_executor_waits_for_exact_approval(tmp_path):
    packet_dir = _packet_dir(tmp_path)

    manifest = run(_args(tmp_path, packet_dir=packet_dir))

    assert manifest["gate"] == AWAITING_APPROVAL_GATE
    assert manifest["owner_approval_text_supplied"] is False
    assert manifest["message_sent"] is False
    assert not (packet_dir / "open_chat_no_type_result_redacted.json").exists()


def test_open_no_type_executor_ready_with_exact_approval_no_action(tmp_path):
    packet_dir = _packet_dir(tmp_path)
    approval = _approval_text_file(tmp_path, packet_dir)

    manifest = run(_args(tmp_path, packet_dir=packet_dir, approval_text_file=approval))

    assert manifest["gate"] == READY_GATE
    assert manifest["owner_approval_text_match"] is True
    assert manifest["customer_send_performed_by_this_script"] is False
    assert manifest["message_text_typed"] is False
    assert manifest["message_sent"] is False


def test_open_no_type_executor_records_observed_open_without_send(tmp_path):
    packet_dir = _packet_dir(tmp_path)
    approval = _approval_text_file(tmp_path, packet_dir)

    manifest = run(
        _args(
            tmp_path,
            packet_dir=packet_dir,
            approval_text_file=approval,
            apply=True,
            record=True,
        ),
        environ={ENV_GATE: "1"},
    )
    result = json.loads((packet_dir / "open_chat_no_type_result_redacted.json").read_text())
    closeout = (packet_dir / "open_chat_no_type_canary_closeout.md").read_text(encoding="utf-8")

    assert manifest["gate"] == RESULT_GREEN_GATE
    assert manifest["result_recorded"] is True
    assert result["gate"] == RESULT_GREEN_GATE
    assert result["chat_opened"] is True
    assert result["message_text_typed"] is False
    assert result["message_sent"] is False
    assert result["visible_merchant_selector_id"] == "30137883"
    assert "Gate: GREEN_OPEN_CHAT_NO_TYPE_SIDE_EFFECT_CANARY_COMPLETED_NO_SEND" in closeout
    assert "938710" not in json.dumps(result, ensure_ascii=False)


def test_open_no_type_executor_rejects_wrong_selector(tmp_path):
    packet_dir = _packet_dir(tmp_path)
    approval = _approval_text_file(tmp_path, packet_dir)

    manifest = run(
        _args(
            tmp_path,
            packet_dir=packet_dir,
            approval_text_file=approval,
            apply=True,
            record=True,
            selector_id="30000001",
        ),
        environ={ENV_GATE: "1"},
    )

    assert manifest["gate"] == UNSAFE_GATE
    assert "visible_merchant_selector_mismatch" in manifest["unsafe_blockers"]
    assert not (packet_dir / "open_chat_no_type_result_redacted.json").exists()


def test_open_no_type_executor_rejects_send_route_observed(tmp_path):
    packet_dir = _packet_dir(tmp_path)
    approval = _approval_text_file(tmp_path, packet_dir)

    manifest = run(
        _args(
            tmp_path,
            packet_dir=packet_dir,
            approval_text_file=approval,
            apply=True,
            record=True,
            send_route=True,
        ),
        environ={ENV_GATE: "1"},
    )

    assert manifest["gate"] == UNSAFE_GATE
    assert "send_message_route_observed_not_false" in manifest["unsafe_blockers"]
    assert not (packet_dir / "open_chat_no_type_result_redacted.json").exists()


def test_open_no_type_executor_blocks_apply_without_env_gate(tmp_path):
    packet_dir = _packet_dir(tmp_path)
    approval = _approval_text_file(tmp_path, packet_dir)

    manifest = run(
        _args(
            tmp_path,
            packet_dir=packet_dir,
            approval_text_file=approval,
            apply=True,
            record=True,
        ),
        environ={},
    )

    assert manifest["gate"] == "YELLOW_OPEN_CHAT_NO_TYPE_CANARY_UI_EXECUTOR_BLOCKED_NO_ACTION"
    assert f"{ENV_GATE}_not_1" in manifest["blockers"]
    assert not (packet_dir / "open_chat_no_type_result_redacted.json").exists()
