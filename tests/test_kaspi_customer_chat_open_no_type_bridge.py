import hashlib
import json
from argparse import Namespace
from datetime import datetime, timedelta
from pathlib import Path

from scripts.promote_kaspi_customer_chat_open_no_type_staged_command import ENV_GATE as PROMOTER_ENV_GATE
from scripts.run_kaspi_customer_chat_open_no_type_canary_bridge import (
    BRIDGE_APPLY_ENV_GATE,
    BRIDGE_APPLY_GATE,
    BRIDGE_READY_GATE,
    BRIDGE_YELLOW_GATE,
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


def _staged_command(tmp_path: Path, *, packet: Path, approval_text_file: Path) -> Path:
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
    return _write_json(command_path, command)


def _heartbeat(tmp_path: Path, *, recorded_at: datetime | None = None) -> Path:
    return _write_json(
        tmp_path / "heartbeat.json",
        {
            "gate": "GREEN_KASPI_CUSTOMER_CHAT_RESIDENT_NO_SEND_CONTROLLER_READY",
            "recorded_at": (recorded_at or datetime.now()).isoformat(timespec="seconds"),
            "orders_search_input_visible": True,
            "browser_should_remain_open": True,
            "safe_current_url": "https://kaspi.kz/mc/#/orders-new?[redacted]",
            "message_text_typed": False,
            "message_sent": False,
        },
    )


def _live_packet(tmp_path: Path, *, stale_heartbeat: bool = False) -> Path:
    packet, phrase = _packet_dir(tmp_path)
    command = _staged_command(tmp_path, packet=packet, approval_text_file=phrase)
    heartbeat = _heartbeat(
        tmp_path,
        recorded_at=datetime.now() - timedelta(minutes=20) if stale_heartbeat else None,
    )
    dry_run = {
        "gate": "GREEN_OPEN_CHAT_NO_TYPE_LIVE_ENQUEUE_PREFLIGHT_READY_DRY_RUN_NO_ACTION",
        "staged_command_path": str(command),
        "live_run_dir": str(tmp_path / "live"),
        "heartbeat_path": str(heartbeat),
        "approval_text_file": str(phrase),
        "expected_merchant_account_id": "30137883",
        "selected_db_row_id": "36170",
        "selected_order_ref": "sha256:3a507903190c4097e2d211ee",
        "resident_open_chat_no_type_preflight_gate": (
            "GREEN_KASPI_CUSTOMER_CHAT_OPEN_CHAT_NO_TYPE_PREFLIGHT_READY_NO_ACTION"
        ),
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
    dry_run_path = _write_json(tmp_path / "dry_run" / "manifest.json", dry_run)
    live_packet = {
        "gate": "GREEN_OPEN_CHAT_NO_TYPE_LIVE_ENQUEUE_PACKET_READY_NO_ACTION",
        "dry_run_manifest_path": str(dry_run_path),
        "dry_run_manifest_sha256": hashlib.sha256(dry_run_path.read_bytes()).hexdigest(),
        "approval_phrase_path": str(phrase),
        "approval_phrase_sha256": hashlib.sha256(phrase.read_text(encoding="utf-8").strip().encode()).hexdigest(),
        "selected_order_ref": "sha256:3a507903190c4097e2d211ee",
        "selected_db_row_id": "36170",
        "selected_store_code": "ACMEWEAR",
        "expected_merchant_account_id": "30137883",
        "apply_command": "echo apply",
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
    return _write_json(tmp_path / "live_packet" / "manifest.json", live_packet)


def _args(tmp_path: Path, *, packet: Path, apply: bool = False) -> Namespace:
    return Namespace(
        live_enqueue_packet_manifest=packet,
        output_dir=tmp_path / "bridge",
        heartbeat_max_age_seconds=300,
        apply=apply,
    )


def test_bridge_ready_no_action_with_fresh_packet_and_heartbeat(tmp_path):
    packet = _live_packet(tmp_path)

    report = run(_args(tmp_path, packet=packet))

    assert report["gate"] == BRIDGE_READY_GATE
    assert report["live_enqueue_performed"] is False
    assert report["chat_opened"] is False
    assert report["message_sent"] is False
    assert report["resident_heartbeat_age_seconds"] <= 300


def test_bridge_blocks_stale_heartbeat(tmp_path):
    packet = _live_packet(tmp_path, stale_heartbeat=True)

    report = run(_args(tmp_path, packet=packet))

    assert report["gate"] == BRIDGE_YELLOW_GATE
    assert any(blocker.startswith("resident_heartbeat_stale:") for blocker in report["blockers"])
    assert report["live_enqueue_performed"] is False


def test_bridge_apply_blocks_without_both_env_gates(tmp_path):
    packet = _live_packet(tmp_path)

    report = run(_args(tmp_path, packet=packet, apply=True), environ={})

    assert report["gate"] == BRIDGE_YELLOW_GATE
    assert f"{BRIDGE_APPLY_ENV_GATE}_not_1" in report["blockers"]
    assert f"{PROMOTER_ENV_GATE}_not_1" in report["blockers"]
    assert report["live_enqueue_performed"] is False


def test_bridge_apply_writes_only_command_when_all_gates_pass(tmp_path):
    packet = _live_packet(tmp_path)

    report = run(
        _args(tmp_path, packet=packet, apply=True),
        environ={BRIDGE_APPLY_ENV_GATE: "1", PROMOTER_ENV_GATE: "1"},
    )
    written = tmp_path / "live" / "command_queue" / "open_chat.json"
    written_payload = json.loads(written.read_text(encoding="utf-8"))

    assert report["gate"] == BRIDGE_APPLY_GATE
    assert report["live_enqueue_performed"] is True
    assert written_payload["action"] == "ui_open_chat_no_type_canary"
    assert written_payload["message_text_typed"] is False
    assert written_payload["message_sent"] is False
