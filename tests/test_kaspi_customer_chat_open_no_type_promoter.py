import hashlib
import json
from argparse import Namespace
from pathlib import Path

from scripts.promote_kaspi_customer_chat_open_no_type_staged_command import (
    DEFAULT_LIVE_RUN_DIR,
    ENV_GATE,
    GREEN_APPLY_GATE,
    GREEN_DRY_RUN_GATE,
    RED_GATE,
    YELLOW_GATE,
    _resident_open_chat_runtime_blockers,
    run,
)


def _write_json(path: Path, payload: dict) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path


def _packet_dir(tmp_path: Path) -> tuple[Path, Path]:
    packet = tmp_path / "packet"
    lock_path = packet / "open_chat_no_type_packet_lock.json"
    lock = {
        "gate": "GREEN_OPEN_CHAT_NO_TYPE_CANARY_PACKET_READY_NO_SEND",
        "selected_order_ref": "sha256:3a507903190c4097e2d211ee",
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
    }
    _write_json(lock_path, lock)
    manifest = {
        **lock,
        "packet_manifest_path": str(lock_path),
        "packet_manifest_sha256": hashlib.sha256(lock_path.read_bytes()).hexdigest(),
        "approval_phrase_generated": True,
    }
    _write_json(packet / "manifest.json", manifest)
    phrase_path = packet / "REQUIRED_EXACT_OPEN_CHAT_NO_TYPE_APPROVAL_PHRASE.txt"
    phrase_path.write_text("I approve exact open-chat/no-type canary\n", encoding="utf-8")
    return packet, phrase_path


def _staged_command(
    tmp_path: Path,
    *,
    packet: Path,
    approval_text_file: Path,
) -> Path:
    command_path = tmp_path / "staged" / "command_queue" / "open_chat.json"
    command = {
        "command_id": "open_chat",
        "action": "ui_open_chat_no_type_canary",
        "target_date": "2026-06-18",
        "lookback_days": 5,
        "stores": "ACMEWEAR",
        "profile_store_code": "ACMEWEAR",
        "max_candidates": 1,
        "candidate_pool_limit": 30,
        "extra_status_filters": "NEW,KASPI_DELIVERY_WAIT_FOR_COURIER",
        "target_db_row_ids": "36170",
        "target_order_refs": "sha256:3a507903190c4097e2d211ee",
        "expected_merchant_account_id": "30137883",
        "timeout_ms": 30000,
        "output_dir": str(tmp_path / "expected_out"),
        "open_chat_packet_dir": str(packet),
        "open_chat_approval_text_file": str(approval_text_file),
        "customer_send_allowed": False,
        "kaspi_chat_write_allowed": False,
        "chat_open_allowed": True,
        "message_text_typed": False,
        "message_sent": False,
        "raw_order_id_exported": False,
        "raw_customer_text_exported": False,
        "raw_phone_exported": False,
        "raw_session_material_exported": False,
    }
    _write_json(command_path, command)
    return command_path


def _heartbeat(path: Path, *, green: bool = True) -> Path:
    payload = {
        "gate": "GREEN_KASPI_CUSTOMER_CHAT_RESIDENT_NO_SEND_CONTROLLER_READY"
        if green
        else "YELLOW_KASPI_CUSTOMER_CHAT_RESIDENT_NO_SEND_CONTROLLER_WAITING_FOR_LOGIN",
        "orders_search_input_visible": green,
        "browser_should_remain_open": True,
        "safe_current_url": (
            "https://kaspi.kz/mc/#/orders-new?[redacted]"
            if green
            else "https://idmc.shop.kaspi.kz/login"
        ),
        "message_text_typed": False,
        "message_sent": False,
    }
    _write_json(path, payload)
    return path


def _order_detail_button_proof(tmp_path: Path, *, db_row_id: int = 36170) -> Path:
    return _write_json(
        tmp_path / "proof" / "manifest.json",
        {
            "gate": "GREEN_KASPI_CUSTOMER_CHAT_MESSAGE_BUTTON_PROVEN_NO_SEND",
            "chat_opened": False,
            "message_text_typed": False,
            "message_sent": False,
            "results": [
                {
                    "db_row_id": db_row_id,
                    "order_ref": "sha256:3a507903190c4097e2d211ee",
                    "store_code": "ACMEWEAR",
                    "expected_merchant_account_id": "30137883",
                    "chat_button_present": True,
                    "merchant_account_match_proven": True,
                    "result_or_detail_reached": True,
                }
            ],
        },
    )


def _order_detail_heartbeat(path: Path, proof_path: Path) -> Path:
    return _write_json(
        path,
        {
            "gate": "YELLOW_KASPI_CUSTOMER_CHAT_RESIDENT_NO_SEND_CONTROLLER_WAITING_FOR_LOGIN",
            "orders_search_input_visible": False,
            "browser_should_remain_open": True,
            "safe_current_url": "https://kaspi.kz/mc/#/orders/[redacted]?[redacted]",
            "last_command": {
                "action": "ui_chat_button_no_open",
                "gate": "GREEN_KASPI_CUSTOMER_CHAT_MESSAGE_BUTTON_PROVEN_NO_SEND",
                "manifest_path": str(proof_path),
            },
            "message_text_typed": False,
            "message_sent": False,
        },
    )


def _args(tmp_path: Path, *, command: Path, heartbeat: Path, approval: Path, apply: bool = False):
    return Namespace(
        staged_command=command,
        live_run_dir=tmp_path / "live",
        heartbeat_json=heartbeat,
        approval_text_file=approval,
        output_dir=tmp_path / "out",
        apply=apply,
    )


def test_promoter_rejects_placeholder_approval_without_live_enqueue(tmp_path):
    packet, _phrase = _packet_dir(tmp_path)
    placeholder = tmp_path / "placeholder.txt"
    placeholder.write_text("placeholder\n", encoding="utf-8")
    command = _staged_command(tmp_path, packet=packet, approval_text_file=placeholder)
    heartbeat = _heartbeat(tmp_path / "heartbeat.json", green=True)

    report = run(_args(tmp_path, command=command, heartbeat=heartbeat, approval=placeholder))

    assert report["gate"] == RED_GATE
    assert "open_chat_owner_approval_text_mismatch" in report["unsafe_blockers"]
    assert report["live_enqueue_performed"] is False
    assert report["message_sent"] is False


def test_promoter_green_dry_run_with_exact_approval_and_ready_resident(tmp_path):
    packet, phrase = _packet_dir(tmp_path)
    command = _staged_command(tmp_path, packet=packet, approval_text_file=phrase)
    heartbeat = _heartbeat(tmp_path / "heartbeat.json", green=True)

    report = run(_args(tmp_path, command=command, heartbeat=heartbeat, approval=phrase))

    assert report["gate"] == GREEN_DRY_RUN_GATE
    assert report["resident_open_chat_no_type_preflight_gate"] == (
        "GREEN_KASPI_CUSTOMER_CHAT_OPEN_CHAT_NO_TYPE_PREFLIGHT_READY_NO_ACTION"
    )
    assert report["live_enqueue_performed"] is False
    assert report["expected_merchant_account_id"] == "30137883"
    assert not (tmp_path / "live" / "command_queue" / "open_chat.json").exists()


def test_promoter_blocks_apply_without_env_gate(tmp_path):
    packet, phrase = _packet_dir(tmp_path)
    command = _staged_command(tmp_path, packet=packet, approval_text_file=phrase)
    heartbeat = _heartbeat(tmp_path / "heartbeat.json", green=True)

    report = run(_args(tmp_path, command=command, heartbeat=heartbeat, approval=phrase, apply=True), environ={})

    assert report["gate"] == YELLOW_GATE
    assert f"{ENV_GATE}_not_1" in report["blockers"]
    assert report["live_enqueue_performed"] is False


def test_promoter_apply_writes_only_command_when_all_gates_pass(tmp_path):
    packet, phrase = _packet_dir(tmp_path)
    command = _staged_command(tmp_path, packet=packet, approval_text_file=phrase)
    heartbeat = _heartbeat(tmp_path / "heartbeat.json", green=True)

    report = run(
        _args(tmp_path, command=command, heartbeat=heartbeat, approval=phrase, apply=True),
        environ={ENV_GATE: "1"},
    )
    written = tmp_path / "live" / "command_queue" / "open_chat.json"
    written_payload = json.loads(written.read_text(encoding="utf-8"))

    assert report["gate"] == GREEN_APPLY_GATE
    assert report["live_enqueue_performed"] is True
    assert written_payload["action"] == "ui_open_chat_no_type_canary"
    assert written_payload["expected_merchant_account_id"] == "30137883"
    assert written_payload["message_text_typed"] is False
    assert written_payload["message_sent"] is False


def test_promoter_keeps_login_yellow_blocked_without_order_detail_proof(tmp_path):
    packet, phrase = _packet_dir(tmp_path)
    command = _staged_command(tmp_path, packet=packet, approval_text_file=phrase)
    heartbeat = _heartbeat(tmp_path / "heartbeat.json", green=False)

    report = run(_args(tmp_path, command=command, heartbeat=heartbeat, approval=phrase))

    assert report["gate"] == YELLOW_GATE
    assert report["resident_order_detail_proof_accepted"] is False
    assert "resident_orders_search_input_not_visible" in report["blockers"]
    assert "resident_not_on_order_detail_url" in report["blockers"]
    assert report["live_enqueue_performed"] is False


def test_promoter_allows_preserved_order_detail_with_matching_button_proof(tmp_path):
    packet, phrase = _packet_dir(tmp_path)
    command = _staged_command(tmp_path, packet=packet, approval_text_file=phrase)
    proof = _order_detail_button_proof(tmp_path)
    heartbeat = _order_detail_heartbeat(tmp_path / "heartbeat.json", proof)

    report = run(_args(tmp_path, command=command, heartbeat=heartbeat, approval=phrase))

    assert report["gate"] == GREEN_DRY_RUN_GATE
    assert report["resident_order_detail_proof_accepted"] is True
    assert report["resident_orders_search_input_visible"] is False
    assert report["live_enqueue_performed"] is False


def test_promoter_rejects_preserved_order_detail_with_wrong_button_proof_target(tmp_path):
    packet, phrase = _packet_dir(tmp_path)
    command = _staged_command(tmp_path, packet=packet, approval_text_file=phrase)
    proof = _order_detail_button_proof(tmp_path, db_row_id=99999)
    heartbeat = _order_detail_heartbeat(tmp_path / "heartbeat.json", proof)

    report = run(_args(tmp_path, command=command, heartbeat=heartbeat, approval=phrase))

    assert report["gate"] == YELLOW_GATE
    assert report["resident_order_detail_proof_accepted"] is False
    assert "resident_last_command_manifest_no_matching_button_proof" in report["blockers"]
    assert report["live_enqueue_performed"] is False


def test_current_resident_runtime_guard_blocks_missing_open_chat_flag():
    blockers = _resident_open_chat_runtime_blockers(
        live_run_dir=DEFAULT_LIVE_RUN_DIR,
        process_lines=[
            (
                "python scripts/run_kaspi_customer_chat_resident_no_send_controller.py "
                f"--run-dir {DEFAULT_LIVE_RUN_DIR}"
            )
        ],
    )

    assert blockers == ["resident_controller_missing_enable_open_chat_no_type_canary_flag"]


def test_current_resident_runtime_guard_accepts_open_chat_flag():
    blockers = _resident_open_chat_runtime_blockers(
        live_run_dir=DEFAULT_LIVE_RUN_DIR,
        process_lines=[
            (
                "python scripts/run_kaspi_customer_chat_resident_no_send_controller.py "
                f"--run-dir {DEFAULT_LIVE_RUN_DIR} --enable-open-chat-no-type-canary"
            )
        ],
    )

    assert blockers == []


def test_non_current_resident_runtime_guard_does_not_block_tmp_run_dir(tmp_path):
    blockers = _resident_open_chat_runtime_blockers(
        live_run_dir=tmp_path / "live",
        process_lines=[],
    )

    assert blockers == []
