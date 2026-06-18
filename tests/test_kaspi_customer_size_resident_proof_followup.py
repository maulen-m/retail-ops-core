import json
from pathlib import Path

from scripts.run_kaspi_customer_size_resident_proof_followup import (
    GREEN_GATE,
    YELLOW_GATE,
    evaluate_resident_manifest,
    main,
)


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _green_manifest(path: Path, *, db_row_id: int = 36170, order_ref: str = "sha256:3a507903190c4097e2d211ee") -> None:
    result = {
        "db_row_id": db_row_id,
        "order_ref": order_ref,
        "store_code": "ACMEWEAR",
        "profile_store_code": "ACMEWEAR",
        "status_filter": "NEW",
        "merchant_account_match_proven": True,
        "expected_merchant_account_id": "30137883",
        "result_or_detail_reached": True,
        "chat_button_present": True,
        "chat_opened": False,
        "message_text_typed": False,
        "message_sent": False,
        "raw_order_id_exported": False,
        "raw_customer_text_exported": False,
        "raw_phone_exported": False,
        "raw_session_material_exported": False,
    }
    _write_json(
        path,
        {
            "gate": "GREEN_KASPI_CUSTOMER_CHAT_MESSAGE_BUTTON_PROVEN_NO_SEND",
            "target_date": "2026-06-18",
            "lookback_days": 3,
            "profile_store_code": "ACMEWEAR",
            "unsafe_event_count": 0,
            "results": [result],
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


def test_resident_proof_followup_missing_manifest_is_yellow(tmp_path):
    output_dir = tmp_path / "out"

    rc = main(
        [
            "--resident-button-manifest",
            str(tmp_path / "missing.json"),
            "--output-dir",
            str(output_dir),
            "--timeout-seconds",
            "0",
        ]
    )

    manifest = json.loads((output_dir / "manifest.json").read_text(encoding="utf-8"))
    assert rc == 1
    assert manifest["gate"] == YELLOW_GATE
    assert "resident_button_manifest_missing" in manifest["blockers"]
    assert manifest["message_sent"] is False


def test_resident_proof_followup_rejects_old_wrong_target_green(tmp_path):
    resident_manifest = tmp_path / "resident_manifest.json"
    _green_manifest(
        resident_manifest,
        db_row_id=36189,
        order_ref="sha256:cba0caf7e8bf1d8dfe12b866",
    )

    evaluation = evaluate_resident_manifest(
        resident_manifest,
        expected_order_ref="sha256:3a507903190c4097e2d211ee",
        expected_db_row_id="36170",
    )

    assert evaluation["ready"] is False
    assert "resident_button_manifest_current_priority_target_not_proven" in evaluation["blockers"]


def test_resident_proof_followup_green_builds_approval_and_handoff(tmp_path):
    resident_manifest = tmp_path / "resident_manifest.json"
    output_dir = tmp_path / "out"
    _green_manifest(resident_manifest)

    rc = main(
        [
            "--resident-button-manifest",
            str(resident_manifest),
            "--output-dir",
            str(output_dir),
            "--expected-order-ref",
            "sha256:3a507903190c4097e2d211ee",
            "--expected-db-row-id",
            "36170",
        ]
    )

    manifest = json.loads((output_dir / "manifest.json").read_text(encoding="utf-8"))
    approval_manifest = json.loads((output_dir / "live_send_approval" / "manifest.json").read_text(encoding="utf-8"))
    handoff_manifest = json.loads(
        (output_dir / "live_send_approval" / "live_send_execution_handoff" / "manifest.json").read_text(
            encoding="utf-8"
        )
    )
    phrase_path = output_dir / "live_send_approval" / "REQUIRED_EXACT_LIVE_SEND_CANARY_APPROVAL_PHRASE.txt"

    assert rc == 0
    assert manifest["gate"] == GREEN_GATE
    assert approval_manifest["gate"] == "GREEN_LIVE_SEND_CANARY_APPROVAL_PACKET_READY_NO_SEND"
    assert handoff_manifest["gate"] == "GREEN_LIVE_SEND_EXECUTION_HANDOFF_READY_NO_SEND_PERFORMED"
    assert phrase_path.exists()
    assert "expected Kaspi merchant account ID: 30137883" in phrase_path.read_text(encoding="utf-8")
    assert manifest["customer_send_allowed"] is False
    assert manifest["message_sent"] is False
