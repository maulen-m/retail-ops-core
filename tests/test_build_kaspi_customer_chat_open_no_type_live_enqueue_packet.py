import argparse
import json
from pathlib import Path

from scripts.build_kaspi_customer_chat_open_no_type_live_enqueue_packet import (
    GREEN_GATE,
    RED_GATE,
    YELLOW_GATE,
    build_packet,
)


def _write_json(path: Path, payload: dict) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path


def _dry_run(tmp_path: Path, **overrides) -> Path:
    payload = {
        "gate": "GREEN_OPEN_CHAT_NO_TYPE_LIVE_ENQUEUE_PREFLIGHT_READY_DRY_RUN_NO_ACTION",
        "staged_command_path": str(tmp_path / "staged.json"),
        "live_run_dir": str(tmp_path / "live"),
        "heartbeat_path": str(tmp_path / "heartbeat.json"),
        "approval_text_file": str(tmp_path / "approval.txt"),
        "expected_merchant_account_id": "30137883",
        "selected_db_row_id": "36170",
        "selected_order_ref": "sha256:3a507903190c4097e2d211ee",
        "resident_open_chat_no_type_preflight_gate": (
            "GREEN_KASPI_CUSTOMER_CHAT_OPEN_CHAT_NO_TYPE_PREFLIGHT_READY_NO_ACTION"
        ),
        "resident_order_detail_proof_accepted": True,
        "resident_order_detail_proof_path": str(tmp_path / "proof.json"),
        "live_enqueue_performed": False,
        "browser_action_performed": False,
        "chat_opened": False,
        "customer_send_performed": False,
        "kaspi_chat_write_performed": False,
        "message_text_typed": False,
        "message_sent": False,
        "raw_order_id_exported": False,
        "raw_customer_text_exported": False,
        "raw_phone_exported": False,
        "raw_session_material_exported": False,
    }
    payload.update(overrides)
    return _write_json(tmp_path / "dry_run.json", payload)


def _approval(tmp_path: Path, text: str = "I approve exact open chat") -> Path:
    path = tmp_path / "approval.txt"
    path.write_text(text + "\n", encoding="utf-8")
    return path


def _args(tmp_path: Path, *, dry_run: Path, approval: Path) -> argparse.Namespace:
    return argparse.Namespace(
        dry_run_manifest=dry_run,
        approval_phrase_file=approval,
        output_dir=tmp_path / "out",
    )


def test_live_enqueue_packet_green_for_clean_dry_run(tmp_path):
    manifest = build_packet(_args(tmp_path, dry_run=_dry_run(tmp_path), approval=_approval(tmp_path)))

    assert manifest["gate"] == GREEN_GATE
    assert manifest["live_enqueue_performed"] is False
    assert manifest["browser_action_performed"] is False
    assert manifest["message_sent"] is False
    assert "--apply" in manifest["apply_command"]
    assert "ENABLE_KASPI_CUSTOMER_CHAT_OPEN_NO_TYPE_LIVE_ENQUEUE=1" in manifest["apply_command"]
    assert (tmp_path / "out" / "APPLY_COMMAND.sh").exists()


def test_live_enqueue_packet_green_for_search_ready_resident_without_order_detail_proof(tmp_path):
    manifest = build_packet(
        _args(
            tmp_path,
            dry_run=_dry_run(
                tmp_path,
                resident_order_detail_proof_accepted=False,
                resident_heartbeat_gate="GREEN_KASPI_CUSTOMER_CHAT_RESIDENT_NO_SEND_CONTROLLER_READY",
                resident_orders_search_input_visible=True,
            ),
            approval=_approval(tmp_path),
        )
    )

    assert manifest["gate"] == GREEN_GATE
    assert manifest["blockers"] == []
    assert "--apply" in manifest["apply_command"]


def test_live_enqueue_packet_blocks_when_dry_run_not_green(tmp_path):
    manifest = build_packet(
        _args(
            tmp_path,
            dry_run=_dry_run(
                tmp_path,
                gate="YELLOW_OPEN_CHAT_NO_TYPE_LIVE_ENQUEUE_PREFLIGHT_BLOCKED_NO_ACTION",
                blockers=["resident_controller_missing_enable_open_chat_no_type_canary_flag"],
            ),
            approval=_approval(tmp_path),
        )
    )

    assert manifest["gate"] == YELLOW_GATE
    assert "dry_run_gate_not_green:YELLOW_OPEN_CHAT_NO_TYPE_LIVE_ENQUEUE_PREFLIGHT_BLOCKED_NO_ACTION" in manifest[
        "blockers"
    ]
    assert "resident_controller_missing_enable_open_chat_no_type_canary_flag" in manifest["blockers"]
    assert manifest["live_enqueue_performed"] is False
    assert manifest["apply_command"] == ""


def test_live_enqueue_packet_red_when_dry_run_contains_side_effect(tmp_path):
    manifest = build_packet(
        _args(
            tmp_path,
            dry_run=_dry_run(tmp_path, live_enqueue_performed=True, chat_opened=True),
            approval=_approval(tmp_path),
        )
    )

    assert manifest["gate"] == RED_GATE
    assert "dry_run_live_enqueue_performed_not_false" in manifest["unsafe_blockers"]
    assert "dry_run_chat_opened_not_false" in manifest["unsafe_blockers"]


def test_live_enqueue_packet_blocks_without_approval_phrase(tmp_path):
    missing = tmp_path / "missing.txt"
    manifest = build_packet(_args(tmp_path, dry_run=_dry_run(tmp_path), approval=missing))

    assert manifest["gate"] == YELLOW_GATE
    assert "approval_phrase_file_missing" in manifest["blockers"]
    assert manifest["apply_command"] == ""
