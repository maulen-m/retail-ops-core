import json
import sqlite3
from pathlib import Path

from core.ops.customer_size_request import (
    DEFAULT_REQUEST_TEMPLATE,
    init_customer_size_request_ledger,
    request_template_hash,
)
from scripts.preflight_kaspi_customer_chat_live_send_canary_execution import (
    BLOCKED_GATE,
    GREEN_GATE,
    RED_GATE,
    YELLOW_GATE,
    build_preflight,
)


def _write_json(path: Path, payload: dict) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path


def _approval_dir(tmp_path: Path) -> Path:
    approval_dir = tmp_path / "approval"
    approval_dir.mkdir(parents=True, exist_ok=True)
    phrase = "I approve KASPI one order exact"
    (approval_dir / "REQUIRED_EXACT_LIVE_SEND_CANARY_APPROVAL_PHRASE.txt").write_text(
        phrase + "\n",
        encoding="utf-8",
    )
    _write_json(
        approval_dir / "manifest.json",
        {
            "gate": "GREEN_LIVE_SEND_CANARY_APPROVAL_PACKET_READY_NO_SEND",
            "approval_phrase_generated": True,
            "selected_order_ref": "sha256:order1",
            "selected_db_row_id": 36189,
            "selected_store_code": "ACMEWEAR",
            "requires_matching_merchant_account": True,
            "expected_merchant_account_id": "30137883",
            "merchant_account_match_proven": True,
            "template_hash": request_template_hash(DEFAULT_REQUEST_TEMPLATE),
            "customer_send_allowed_now": False,
        },
    )
    return approval_dir


def _resident_reuse_manifest(tmp_path: Path) -> Path:
    return _write_json(
        tmp_path / "reuse" / "manifest.json",
        {
            "gate": "GREEN_KASPI_CUSTOMER_CHAT_RESIDENT_SESSION_REUSE_READY_NO_SEND",
            "no_send_invariants": {
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
        },
    )


def _resident_heartbeat(tmp_path: Path, *, green: bool = True) -> Path:
    return _write_json(
        tmp_path / "resident" / "resident_controller_heartbeat.json",
        {
            "gate": (
                "GREEN_KASPI_CUSTOMER_CHAT_RESIDENT_NO_SEND_CONTROLLER_READY"
                if green
                else "YELLOW_KASPI_CUSTOMER_CHAT_RESIDENT_NO_SEND_CONTROLLER_WAITING_FOR_LOGIN"
            ),
            "recorded_at": "2026-06-18T10:00:00",
            "persistent_profile_mode": True,
            "browser_should_remain_open": True,
            "orders_search_input_visible": green,
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
            "blockers": [] if green else ["orders_search_input_not_visible"],
        },
    )


def _ledger(tmp_path: Path, *, status: str = "SEND_PLANNED_NO_SEND") -> Path:
    ledger_db = tmp_path / "ledger.sqlite"
    ledger_db.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(ledger_db)
    try:
        init_customer_size_request_ledger(conn)
        conn.execute(
            """
            INSERT INTO customer_size_request_ledger (
                ledger_key, order_ref, db_row_id, store_code, sku_key, sku_id,
                channel, template_hash, status, request_planned_at,
                send_allowed, raw_order_id_exported, raw_reply_text_exported, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, 0, 0, ?)
            """,
            (
                "ledger1",
                "sha256:order1",
                36189,
                "ACMEWEAR",
                "sku",
                "sku-id",
                "KASPI_MERCHANT_CHAT_UI",
                request_template_hash(DEFAULT_REQUEST_TEMPLATE),
                status,
                "2026-06-17T10:00:00",
                "2026-06-17T10:00:00",
            ),
        )
        conn.commit()
    finally:
        conn.close()
    return ledger_db


def test_live_send_execution_preflight_waits_for_exact_owner_phrase(tmp_path):
    report = build_preflight(
        approval_dir=_approval_dir(tmp_path),
        resident_reuse_manifest_path=_resident_reuse_manifest(tmp_path),
        ledger_db=_ledger(tmp_path),
        output_dir=tmp_path / "out",
        supplied_approval_text="",
        approval_source="not_supplied",
    )

    assert report["gate"] == YELLOW_GATE
    assert report["owner_approval_text_supplied"] is False
    assert report["owner_approval_text_match"] is False
    assert report["expected_merchant_account_id"] == "30137883"
    assert report["merchant_selector_map"]["ACMEWEAR"] == "30137883"
    assert report["merchant_selector_map"]["UNIVERSAL"] == "30000001"
    assert report["requires_matching_merchant_account"] is True
    assert report["ledger_match_count"] == 1
    assert report["customer_send_performed"] is False
    assert report["raw_order_id_exported"] is False


def test_live_send_execution_preflight_green_with_exact_phrase_no_send(tmp_path):
    approval_dir = _approval_dir(tmp_path)
    phrase = (approval_dir / "REQUIRED_EXACT_LIVE_SEND_CANARY_APPROVAL_PHRASE.txt").read_text(
        encoding="utf-8"
    ).strip()

    report = build_preflight(
        approval_dir=approval_dir,
        resident_reuse_manifest_path=_resident_reuse_manifest(tmp_path),
        ledger_db=_ledger(tmp_path),
        output_dir=tmp_path / "out",
        supplied_approval_text=phrase,
        approval_source="file",
    )

    assert report["gate"] == GREEN_GATE
    assert report["owner_approval_text_match"] is True
    assert report["customer_send_allowed_by_this_preflight"] is False
    assert report["kaspi_chat_write_allowed_by_this_preflight"] is False


def test_live_send_execution_preflight_green_with_fresh_green_heartbeat(tmp_path):
    approval_dir = _approval_dir(tmp_path)
    phrase = (approval_dir / "REQUIRED_EXACT_LIVE_SEND_CANARY_APPROVAL_PHRASE.txt").read_text(
        encoding="utf-8"
    ).strip()

    report = build_preflight(
        approval_dir=approval_dir,
        resident_reuse_manifest_path=_resident_reuse_manifest(tmp_path),
        resident_heartbeat_path=_resident_heartbeat(tmp_path, green=True),
        ledger_db=_ledger(tmp_path),
        output_dir=tmp_path / "out",
        supplied_approval_text=phrase,
        approval_source="file",
    )

    assert report["gate"] == GREEN_GATE
    assert report["resident_current_heartbeat_gate"] == (
        "GREEN_KASPI_CUSTOMER_CHAT_RESIDENT_NO_SEND_CONTROLLER_READY"
    )
    assert report["resident_current_heartbeat_orders_search_input_visible"] is True


def test_live_send_execution_preflight_blocks_with_fresh_yellow_heartbeat(tmp_path):
    approval_dir = _approval_dir(tmp_path)
    phrase = (approval_dir / "REQUIRED_EXACT_LIVE_SEND_CANARY_APPROVAL_PHRASE.txt").read_text(
        encoding="utf-8"
    ).strip()

    report = build_preflight(
        approval_dir=approval_dir,
        resident_reuse_manifest_path=_resident_reuse_manifest(tmp_path),
        resident_heartbeat_path=_resident_heartbeat(tmp_path, green=False),
        ledger_db=_ledger(tmp_path),
        output_dir=tmp_path / "out",
        supplied_approval_text=phrase,
        approval_source="file",
    )

    assert report["gate"] == BLOCKED_GATE
    assert "resident_current_heartbeat_not_green" in report["blockers"]
    assert "resident_current_heartbeat_orders_search_input_not_visible" in report["blockers"]
    assert report["owner_approval_text_match"] is True
    assert report["customer_send_performed"] is False


def test_live_send_execution_preflight_red_if_ledger_already_sent(tmp_path):
    approval_dir = _approval_dir(tmp_path)
    phrase = (approval_dir / "REQUIRED_EXACT_LIVE_SEND_CANARY_APPROVAL_PHRASE.txt").read_text(
        encoding="utf-8"
    ).strip()

    report = build_preflight(
        approval_dir=approval_dir,
        resident_reuse_manifest_path=_resident_reuse_manifest(tmp_path),
        ledger_db=_ledger(tmp_path, status="REQUEST_SENT"),
        output_dir=tmp_path / "out",
        supplied_approval_text=phrase,
        approval_source="file",
    )

    assert report["gate"] == RED_GATE
    assert "ledger_status_already_after_send_or_reply:REQUEST_SENT" in report["unsafe_blockers"]


def test_live_send_execution_preflight_rejects_wrong_expected_merchant_id(tmp_path):
    approval_dir = _approval_dir(tmp_path)
    manifest_path = approval_dir / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["expected_merchant_account_id"] = "30000001"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    phrase = (approval_dir / "REQUIRED_EXACT_LIVE_SEND_CANARY_APPROVAL_PHRASE.txt").read_text(
        encoding="utf-8"
    ).strip()

    report = build_preflight(
        approval_dir=approval_dir,
        resident_reuse_manifest_path=_resident_reuse_manifest(tmp_path),
        ledger_db=_ledger(tmp_path),
        output_dir=tmp_path / "out",
        supplied_approval_text=phrase,
        approval_source="file",
    )

    assert report["gate"] == RED_GATE
    assert "approval_manifest_expected_merchant_account_id_mismatch" in report["unsafe_blockers"]


def test_live_send_execution_preflight_blocks_when_artifacts_missing(tmp_path):
    report = build_preflight(
        approval_dir=tmp_path / "missing_approval",
        resident_reuse_manifest_path=tmp_path / "missing_reuse.json",
        ledger_db=tmp_path / "missing.sqlite",
        output_dir=tmp_path / "out",
        supplied_approval_text="",
        approval_source="not_supplied",
    )

    assert report["gate"] == BLOCKED_GATE
    assert "approval_manifest_missing" in report["blockers"]
    assert "resident_session_reuse_manifest_missing" in report["blockers"]
