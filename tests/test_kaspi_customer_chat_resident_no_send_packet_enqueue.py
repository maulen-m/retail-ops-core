import json
from datetime import datetime
from pathlib import Path

from scripts.enqueue_kaspi_customer_chat_resident_no_send_command_packet import (
    GREEN_DRY_RUN_GATE,
    GREEN_ENQUEUED_GATE,
    RED_GATE,
    YELLOW_GATE,
    evaluate_packet_enqueue_readiness,
    main,
)


def _write_json(path: Path, payload: dict | list) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _heartbeat(run_dir: Path, *, store: str = "ACMEWEAR", recorded_at: str = "2026-06-18T10:00:00") -> None:
    _write_json(
        run_dir / "resident_controller_heartbeat.json",
        {
            "gate": "GREEN_KASPI_CUSTOMER_CHAT_RESIDENT_NO_SEND_CONTROLLER_READY",
            "recorded_at": recorded_at,
            "profile_store_code": store,
            "commands_dir": str(run_dir / "command_queue"),
            "browser_should_remain_open": True,
            "orders_search_input_visible": True,
            "customer_send_allowed": False,
            "kaspi_chat_write_allowed": False,
            "message_text_typed": False,
            "message_sent": False,
        },
    )


def _yellow_heartbeat_on_detail_page(
    run_dir: Path,
    *,
    store: str = "ACMEWEAR",
    recorded_at: str = "2026-06-18T10:00:00",
) -> None:
    _write_json(
        run_dir / "resident_controller_heartbeat.json",
        {
            "gate": "YELLOW_KASPI_CUSTOMER_CHAT_RESIDENT_NO_SEND_CONTROLLER_WAITING_FOR_LOGIN",
            "recorded_at": recorded_at,
            "profile_store_code": store,
            "commands_dir": str(run_dir / "command_queue"),
            "browser_should_remain_open": True,
            "orders_search_input_visible": False,
            "safe_current_url": "https://kaspi.kz/mc/#/orders/[redacted]?[redacted]",
            "customer_send_allowed": False,
            "kaspi_chat_write_allowed": False,
            "message_text_typed": False,
            "message_sent": False,
        },
    )


def _command_packet(packet_dir: Path) -> None:
    commands_dir = packet_dir / "command_queue"
    acmewear_command = {
        "command_id": "priority_001_acmewear_36170_ui_chat_button_no_open",
        "action": "ui_chat_button_no_open",
        "stores": "ACMEWEAR",
        "profile_store_code": "ACMEWEAR",
        "target_db_row_ids": "36170",
        "target_order_refs": "sha256:acmewear",
        "expected_merchant_account_id": "30137883",
        "requires_matching_merchant_account": True,
        "customer_send_allowed": False,
        "kaspi_chat_write_allowed": False,
        "chat_open_allowed": False,
        "message_text_typed": False,
        "message_sent": False,
        "raw_order_id_exported": False,
        "raw_customer_text_exported": False,
        "raw_phone_exported": False,
        "raw_session_material_exported": False,
    }
    storeb_command = {
        **acmewear_command,
        "command_id": "priority_002_storeb_36196_ui_chat_button_no_open",
        "stores": "STOREB",
        "profile_store_code": "STOREB",
        "target_db_row_ids": "36196",
        "target_order_refs": "sha256:storeb",
        "expected_merchant_account_id": "30000002",
    }
    acmewear_path = commands_dir / f"{acmewear_command['command_id']}.json"
    storeb_path = commands_dir / f"{storeb_command['command_id']}.json"
    _write_json(acmewear_path, acmewear_command)
    _write_json(storeb_path, storeb_command)
    _write_json(
        packet_dir / "command_index_redacted.json",
        [
            {
                "command_id": acmewear_command["command_id"],
                "command_path": str(acmewear_path),
                "store_code": "ACMEWEAR",
                "expected_merchant_account_id": "30137883",
            },
            {
                "command_id": storeb_command["command_id"],
                "command_path": str(storeb_path),
                "store_code": "STOREB",
                "expected_merchant_account_id": "30000002",
            },
        ],
    )


def test_packet_enqueue_readiness_selects_only_resident_store(tmp_path):
    run_dir = tmp_path / "resident"
    packet_dir = tmp_path / "packet"
    _heartbeat(run_dir, store="ACMEWEAR")
    _command_packet(packet_dir)

    manifest = evaluate_packet_enqueue_readiness(
        run_dir=run_dir,
        packet_dir=packet_dir,
        heartbeat_max_age_seconds=300,
        as_of=datetime(2026, 6, 18, 10, 2, 0),
        skip_process_check=True,
    )

    assert manifest["gate"] == GREEN_DRY_RUN_GATE
    assert manifest["resident_profile_store_code"] == "ACMEWEAR"
    assert manifest["selected_command_count"] == 1
    assert manifest["selected_commands_redacted"][0]["store_code"] == "ACMEWEAR"
    assert manifest["selected_commands_redacted"][0]["expected_merchant_account_id"] == "30137883"
    assert manifest["skipped_commands_redacted"][0]["store_code"] == "STOREB"
    assert manifest["message_sent"] is False


def test_packet_enqueue_readiness_blocks_stale_heartbeat_without_override(tmp_path):
    run_dir = tmp_path / "resident"
    packet_dir = tmp_path / "packet"
    _heartbeat(run_dir, recorded_at="2026-06-18T09:00:00")
    _command_packet(packet_dir)

    manifest = evaluate_packet_enqueue_readiness(
        run_dir=run_dir,
        packet_dir=packet_dir,
        heartbeat_max_age_seconds=300,
        as_of=datetime(2026, 6, 18, 10, 0, 0),
        skip_process_check=True,
    )

    assert manifest["gate"] == YELLOW_GATE
    assert "resident_heartbeat_stale" in manifest["blockers"]


def test_packet_enqueue_readiness_allows_stale_idle_heartbeat_when_process_running(tmp_path):
    run_dir = tmp_path / "resident"
    packet_dir = tmp_path / "packet"
    _heartbeat(run_dir, recorded_at="2026-06-18T09:00:00")
    _command_packet(packet_dir)

    manifest = evaluate_packet_enqueue_readiness(
        run_dir=run_dir,
        packet_dir=packet_dir,
        heartbeat_max_age_seconds=300,
        as_of=datetime(2026, 6, 18, 10, 0, 0),
        allow_stale_idle_heartbeat_if_process_running=True,
        skip_process_check=True,
        process_lines=["123 run_kaspi_customer_chat_resident_no_send_controller.py"],
    )

    assert manifest["gate"] == GREEN_DRY_RUN_GATE
    assert manifest["heartbeat_stale_allowed_because_idle_process_running"] is True
    assert manifest["message_sent"] is False


def test_packet_enqueue_readiness_blocks_requested_cross_store(tmp_path):
    run_dir = tmp_path / "resident"
    packet_dir = tmp_path / "packet"
    _heartbeat(run_dir, store="ACMEWEAR")
    _command_packet(packet_dir)

    manifest = evaluate_packet_enqueue_readiness(
        run_dir=run_dir,
        packet_dir=packet_dir,
        heartbeat_max_age_seconds=300,
        as_of=datetime(2026, 6, 18, 10, 2, 0),
        store="STOREB",
        skip_process_check=True,
    )

    assert manifest["gate"] == RED_GATE
    assert "requested_store_does_not_match_resident_profile" in manifest["unsafe_blockers"]
    assert manifest["message_sent"] is False


def test_packet_enqueue_readiness_allows_explicit_selector_switch_cross_store(tmp_path):
    run_dir = tmp_path / "resident"
    packet_dir = tmp_path / "packet"
    _heartbeat(run_dir, store="ACMEWEAR")
    _command_packet(packet_dir)

    manifest = evaluate_packet_enqueue_readiness(
        run_dir=run_dir,
        packet_dir=packet_dir,
        heartbeat_max_age_seconds=300,
        as_of=datetime(2026, 6, 18, 10, 2, 0),
        store="STOREB",
        allow_selector_switch_across_store=True,
        skip_process_check=True,
        process_lines=["123 run_kaspi_customer_chat_resident_no_send_controller.py"],
    )

    assert manifest["gate"] == GREEN_DRY_RUN_GATE
    assert manifest["resident_profile_store_code"] == "ACMEWEAR"
    assert manifest["requested_store"] == "STOREB"
    assert manifest["selector_switch_across_store_allowed"] is True
    assert manifest["selected_command_count"] == 1
    assert manifest["selected_commands_redacted"][0]["store_code"] == "STOREB"
    assert manifest["selected_commands_redacted"][0]["expected_merchant_account_id"] == "30000002"
    assert manifest["message_sent"] is False


def test_packet_enqueue_readiness_allows_selector_switch_page_recovery_if_process_running(tmp_path):
    run_dir = tmp_path / "resident"
    packet_dir = tmp_path / "packet"
    _yellow_heartbeat_on_detail_page(run_dir, store="ACMEWEAR")
    _command_packet(packet_dir)

    manifest = evaluate_packet_enqueue_readiness(
        run_dir=run_dir,
        packet_dir=packet_dir,
        heartbeat_max_age_seconds=300,
        as_of=datetime(2026, 6, 18, 10, 2, 0),
        store="STOREB",
        allow_selector_switch_across_store=True,
        skip_process_check=True,
        process_lines=["123 run_kaspi_customer_chat_resident_no_send_controller.py"],
    )

    assert manifest["gate"] == GREEN_DRY_RUN_GATE
    assert manifest["resident_page_recovery_allowed_because_process_running"] is True
    assert manifest["selected_command_count"] == 1
    assert manifest["message_sent"] is False


def test_packet_enqueue_readiness_allows_same_store_page_recovery_if_process_running(tmp_path):
    run_dir = tmp_path / "resident"
    packet_dir = tmp_path / "packet"
    _yellow_heartbeat_on_detail_page(run_dir, store="ACMEWEAR")
    _command_packet(packet_dir)

    manifest = evaluate_packet_enqueue_readiness(
        run_dir=run_dir,
        packet_dir=packet_dir,
        heartbeat_max_age_seconds=300,
        as_of=datetime(2026, 6, 18, 10, 2, 0),
        store="ACMEWEAR",
        allow_resident_page_recovery_if_process_running=True,
        skip_process_check=True,
        process_lines=["123 run_kaspi_customer_chat_resident_no_send_controller.py"],
    )

    assert manifest["gate"] == GREEN_DRY_RUN_GATE
    assert manifest["resident_page_recovery_allowed_because_process_running"] is True
    assert manifest["resident_page_recovery_explicitly_allowed"] is True
    assert manifest["selected_command_count"] == 1
    assert manifest["selected_commands_redacted"][0]["store_code"] == "ACMEWEAR"
    assert manifest["message_sent"] is False


def test_packet_enqueue_main_copies_selected_no_send_commands(tmp_path):
    run_dir = tmp_path / "resident"
    packet_dir = tmp_path / "packet"
    output_dir = tmp_path / "out"
    _heartbeat(run_dir)
    _command_packet(packet_dir)

    rc = main(
        [
            "--run-dir",
            str(run_dir),
            "--packet-dir",
            str(packet_dir),
            "--output-dir",
            str(output_dir),
            "--as-of",
            "2026-06-18T10:02:00",
            "--skip-process-check",
            "--enqueue",
        ]
    )

    manifest = json.loads((output_dir / "manifest.json").read_text(encoding="utf-8"))
    queued = run_dir / "command_queue" / "priority_001_acmewear_36170_ui_chat_button_no_open.json"

    assert rc == 0
    assert manifest["gate"] == GREEN_ENQUEUED_GATE
    assert manifest["enqueued_command_count"] == 1
    assert queued.exists()
    assert json.loads(queued.read_text(encoding="utf-8"))["message_sent"] is False
