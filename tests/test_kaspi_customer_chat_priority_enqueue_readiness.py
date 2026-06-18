import json
from datetime import datetime
from pathlib import Path

from scripts.enqueue_kaspi_customer_chat_priority_if_resident_ready import (
    GREEN_DRY_RUN_GATE,
    GREEN_ENQUEUED_GATE,
    YELLOW_GATE,
    evaluate_readiness,
    main,
)


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _command(path: Path) -> None:
    _write_json(
        path,
        {
            "command_id": "priority_top_001_ui_chat_button_no_open_36170",
            "action": "ui_chat_button_no_open",
            "profile_store_code": "ACMEWEAR",
            "stores": "ACMEWEAR",
            "target_db_row_ids": "36170",
            "target_order_refs": "sha256:3a507903190c4097e2d211ee",
            "customer_send_allowed": False,
            "kaspi_chat_write_allowed": False,
            "chat_open_allowed": False,
            "message_text_typed": False,
            "message_sent": False,
            "raw_order_id_exported": False,
            "raw_customer_text_exported": False,
            "raw_phone_exported": False,
            "raw_session_material_exported": False,
        },
    )


def _heartbeat(run_dir: Path, *, recorded_at: str = "2026-06-18T09:30:00", store: str = "ACMEWEAR") -> None:
    _write_json(
        run_dir / "resident_controller_heartbeat.json",
        {
            "gate": "GREEN_KASPI_CUSTOMER_CHAT_RESIDENT_NO_SEND_CONTROLLER_READY",
            "recorded_at": recorded_at,
            "run_dir": str(run_dir),
            "profile_store_code": store,
            "commands_dir": str(run_dir / "command_queue"),
            "browser_should_remain_open": True,
            "orders_search_input_visible": True,
            "customer_send_allowed": False,
            "kaspi_chat_write_allowed": False,
            "message_sent": False,
        },
    )


def test_priority_enqueue_readiness_blocks_stale_heartbeat_without_copy(tmp_path):
    run_dir = tmp_path / "resident"
    command_path = tmp_path / "command.json"
    _command(command_path)
    _heartbeat(run_dir, recorded_at="2026-06-18T09:00:00")

    manifest = evaluate_readiness(
        run_dir=run_dir,
        command_path=command_path,
        heartbeat_max_age_seconds=300,
        as_of=datetime(2026, 6, 18, 9, 30, 0),
        skip_process_check=True,
    )

    assert manifest["gate"] == YELLOW_GATE
    assert "resident_heartbeat_stale" in manifest["blockers"]
    assert manifest["message_sent"] is False


def test_priority_enqueue_readiness_green_dry_run_does_not_enqueue(tmp_path):
    run_dir = tmp_path / "resident"
    output_dir = tmp_path / "out"
    command_path = tmp_path / "command.json"
    _command(command_path)
    _heartbeat(run_dir)

    rc = main(
        [
            "--run-dir",
            str(run_dir),
            "--command-path",
            str(command_path),
            "--output-dir",
            str(output_dir),
            "--as-of",
            "2026-06-18T09:31:00",
            "--skip-process-check",
        ]
    )

    manifest = json.loads((output_dir / "manifest.json").read_text(encoding="utf-8"))
    assert rc == 0
    assert manifest["gate"] == GREEN_DRY_RUN_GATE
    assert manifest["expected_merchant_account_id"] == "30137883"
    assert not (run_dir / "command_queue" / "priority_top_001_ui_chat_button_no_open_36170.json").exists()


def test_priority_enqueue_readiness_enqueue_copies_no_send_command(tmp_path):
    run_dir = tmp_path / "resident"
    output_dir = tmp_path / "out"
    command_path = tmp_path / "command.json"
    _command(command_path)
    _heartbeat(run_dir)

    rc = main(
        [
            "--run-dir",
            str(run_dir),
            "--command-path",
            str(command_path),
            "--output-dir",
            str(output_dir),
            "--as-of",
            "2026-06-18T09:31:00",
            "--skip-process-check",
            "--enqueue",
        ]
    )

    destination = run_dir / "command_queue" / "priority_top_001_ui_chat_button_no_open_36170.json"
    manifest = json.loads((output_dir / "manifest.json").read_text(encoding="utf-8"))
    enqueued = json.loads(destination.read_text(encoding="utf-8"))
    assert rc == 0
    assert manifest["gate"] == GREEN_ENQUEUED_GATE
    assert destination.exists()
    assert enqueued["customer_send_allowed"] is False
    assert enqueued["message_sent"] is False
    assert enqueued["target_order_refs"] == "sha256:3a507903190c4097e2d211ee"


def test_priority_enqueue_readiness_blocks_wrong_store_selector_context(tmp_path):
    run_dir = tmp_path / "resident"
    command_path = tmp_path / "command.json"
    _command(command_path)
    _heartbeat(run_dir, store="STOREB")

    manifest = evaluate_readiness(
        run_dir=run_dir,
        command_path=command_path,
        heartbeat_max_age_seconds=300,
        as_of=datetime(2026, 6, 18, 9, 31, 0),
        skip_process_check=True,
    )

    assert manifest["gate"] == YELLOW_GATE
    assert "priority_command_store_mismatch_with_resident_profile" in manifest["blockers"]
