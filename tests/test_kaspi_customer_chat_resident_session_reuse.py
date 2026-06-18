import json
from pathlib import Path

from scripts.report_kaspi_customer_chat_resident_session_reuse import (
    GREEN_GATE,
    RED_GATE,
    YELLOW_GATE,
    build_report,
)


def _write_json(path: Path, payload: dict) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path


def _green_heartbeat(tmp_path: Path, **overrides) -> Path:
    payload = {
        "gate": "GREEN_KASPI_CUSTOMER_CHAT_RESIDENT_NO_SEND_CONTROLLER_READY",
        "recorded_at": "2026-06-17T18:10:00",
        "run_dir": str(tmp_path / "run"),
        "profile_store_code": "ACMEWEAR",
        "persistent_profile_mode": True,
        "persistent_profile_dir_path": str(tmp_path / "profile"),
        "commands_dir": str(tmp_path / "run" / "command_queue"),
        "browser_should_remain_open": True,
        "orders_search_input_visible": True,
        "safe_current_url": "https://kaspi.kz/mc/#/orders-new?[redacted]",
        "customer_send_allowed": False,
        "kaspi_chat_write_allowed": False,
        "chat_opened": False,
        "message_text_typed": False,
        "message_sent": False,
        "raw_order_id_exported": False,
        "raw_customer_text_exported": False,
        "raw_phone_exported": False,
        "raw_session_material_exported": False,
    }
    payload.update(overrides)
    Path(payload["commands_dir"]).mkdir(parents=True, exist_ok=True)
    return _write_json(tmp_path / "heartbeat.json", payload)


def test_resident_session_reuse_report_is_green_for_visible_persistent_session(tmp_path):
    heartbeat = _green_heartbeat(tmp_path)
    phrase = tmp_path / "approval" / "REQUIRED_EXACT_LIVE_SEND_CANARY_APPROVAL_PHRASE.txt"
    phrase.parent.mkdir(parents=True, exist_ok=True)
    phrase.write_text("I approve exact canary\n", encoding="utf-8")
    approval = _write_json(
        tmp_path / "approval" / "manifest.json",
        {
            "gate": "GREEN_LIVE_SEND_CANARY_APPROVAL_PACKET_READY_NO_SEND",
            "approval_phrase_generated": True,
            "selected_store_code": "ACMEWEAR",
            "selected_db_row_id": 36189,
            "customer_send_allowed_now": False,
        },
    )

    report = build_report(
        heartbeat_path=heartbeat,
        live_send_approval_manifest=approval,
        output_dir=tmp_path / "out",
    )

    assert report["gate"] == GREEN_GATE
    assert report["checks"]["orders_search_input_visible"] is True
    assert report["live_send_approval"]["approval_packet_ready_no_send"] is True
    assert report["live_send_approval"]["approval_phrase_path"] == str(phrase)
    assert report["next_action"] == "owner_may_review_exact_one_order_live_send_canary_phrase_no_send_yet"
    assert report["no_send_invariants"]["message_sent"] is False


def test_resident_session_reuse_report_is_yellow_for_login_or_missing_search(tmp_path):
    heartbeat = _green_heartbeat(
        tmp_path,
        orders_search_input_visible=False,
        safe_current_url="https://idmc.shop.kaspi.kz/login",
    )

    report = build_report(
        heartbeat_path=heartbeat,
        live_send_approval_manifest=None,
        output_dir=tmp_path / "out",
    )

    assert report["gate"] == YELLOW_GATE
    assert "orders_search_input_not_visible" in report["blockers"]
    assert "resident_browser_at_login_route" in report["blockers"]
    assert report["no_send_invariants"]["raw_session_material_exported"] is False


def test_resident_session_reuse_report_is_red_for_any_send_or_raw_leak_flag(tmp_path):
    heartbeat = _green_heartbeat(
        tmp_path,
        message_sent=True,
        raw_session_material_exported=True,
    )

    report = build_report(
        heartbeat_path=heartbeat,
        live_send_approval_manifest=None,
        output_dir=tmp_path / "out",
    )

    assert report["gate"] == RED_GATE
    assert "heartbeat_message_sent_true" in report["unsafe_blockers"]
    assert "heartbeat_raw_session_material_exported_true" in report["unsafe_blockers"]
