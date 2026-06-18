import json
from pathlib import Path

from scripts.build_kaspi_customer_size_resident_resume_packet import (
    GREEN_GATE,
    build_packet,
    main,
)


def _write_command(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "command_id": "priority_top_001_ui_chat_button_no_open_36170",
                "action": "ui_chat_button_no_open",
                "profile_store_code": "ACMEWEAR",
                "stores": "ACMEWEAR",
                "target_db_row_ids": "36170",
                "target_order_refs": "sha256:3a507903190c4097e2d211ee",
                "extra_status_filters": "NEW",
                "output_dir": "exports/validation/kaspi_customer_size_priority_resident_no_send_command_20260618_current/expected_command_output/priority_top_001_ui_chat_button_no_open_36170",
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
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )


def test_resident_resume_packet_generates_operator_scripts_without_send(tmp_path):
    run_dir = tmp_path / "resident"
    command_path = tmp_path / "command_queue" / "priority.json"
    output_dir = tmp_path / "packet"
    _write_command(command_path)

    manifest = build_packet(
        output_dir=output_dir,
        run_dir=run_dir,
        priority_command_path=command_path,
        startup_status_filter="NEW",
        manual_login_timeout_seconds=900,
    )

    runbook = (output_dir / "RUNBOOK.md").read_text(encoding="utf-8")
    start_script = Path(manifest["start_script_path"]).read_text(encoding="utf-8")
    enqueue_script = Path(manifest["enqueue_script_path"]).read_text(encoding="utf-8")
    followup_script = Path(manifest["proof_followup_script_path"]).read_text(encoding="utf-8")
    approval_script = Path(manifest["build_approval_script_path"]).read_text(encoding="utf-8")

    assert manifest["gate"] == GREEN_GATE
    assert manifest["customer_send_allowed"] is False
    assert manifest["kaspi_chat_write_allowed"] is False
    assert manifest["message_sent"] is False
    assert manifest["priority_command"]["expected_merchant_account_id"] == "30137883"
    assert manifest["merchant_selector_map"]["ACMEWEAR"] == "30137883"
    assert manifest["expected_resident_button_manifest_path"].endswith(
        "expected_command_output/priority_top_001_ui_chat_button_no_open_36170/manifest.json"
    )
    assert "run_kaspi_customer_chat_resident_no_send_controller.py" in start_script
    assert "--once" not in start_script
    assert "--allow-session-close" not in start_script
    assert "--enable-open-chat-no-type-canary" in start_script
    assert "enqueue_kaspi_customer_chat_priority_if_resident_ready.py" in enqueue_script
    assert "--enqueue" in enqueue_script
    assert "run_kaspi_customer_size_resident_proof_followup.py" in followup_script
    assert "--expected-db-row-id 36170" in followup_script
    assert "--timeout-seconds 300" in followup_script
    assert "build_kaspi_customer_chat_live_send_canary_approval_packet.py" in approval_script
    assert "--resident-button-manifest" in approval_script
    assert "30137883" in runbook
    assert "Required merchant selector ID: `30137883`" in runbook
    assert "rejects old/wrong-target GREEN proofs" in runbook
    assert "Customer send allowed: false" in runbook


def test_resident_resume_packet_cli_writes_manifest_and_closeout(tmp_path):
    run_dir = tmp_path / "resident"
    command_path = tmp_path / "command_queue" / "priority.json"
    output_dir = tmp_path / "packet"
    _write_command(command_path)

    rc = main(
        [
            "--output-dir",
            str(output_dir),
            "--run-dir",
            str(run_dir),
            "--priority-command-path",
            str(command_path),
            "--startup-status-filter",
            "NEW",
        ]
    )

    manifest = json.loads((output_dir / "manifest.json").read_text(encoding="utf-8"))
    closeout = (output_dir / "closeout.md").read_text(encoding="utf-8")
    assert rc == 0
    assert manifest["gate"] == GREEN_GATE
    assert (output_dir / "RUNBOOK.md").exists()
    assert "Gate: GREEN_KASPI_CUSTOMER_SIZE_RESIDENT_RESUME_PACKET_READY_NO_BROWSER_TOUCH" in closeout
    assert "No browser was touched" in closeout
