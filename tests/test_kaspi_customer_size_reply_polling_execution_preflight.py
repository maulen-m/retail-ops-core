import json
import sqlite3
from pathlib import Path

from core.ops.customer_size_request import (
    DEFAULT_REQUEST_TEMPLATE,
    init_customer_size_request_ledger,
    request_template_hash,
)
from scripts.preflight_kaspi_customer_size_reply_polling_execution import (
    GREEN_GATE,
    RED_GATE,
    YELLOW_AWAITING_APPROVAL_GATE,
    YELLOW_NO_TARGETS_GATE,
    build_preflight,
)


def _write_json(path: Path, payload: dict) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path


def _resident_reuse_manifest(tmp_path: Path, *, unsafe: bool = False) -> Path:
    return _write_json(
        tmp_path / "reuse" / "manifest.json",
        {
            "gate": "GREEN_KASPI_CUSTOMER_CHAT_RESIDENT_SESSION_REUSE_READY_NO_SEND",
            "no_send_invariants": {
                "customer_send_allowed": False,
                "kaspi_chat_write_allowed": False,
                "chat_open_allowed": False if not unsafe else True,
                "message_text_typed": False,
                "message_sent": False,
                "raw_order_id_exported": False,
                "raw_customer_text_exported": False,
                "raw_phone_exported": False,
                "raw_session_material_exported": False,
            },
        },
    )


def _ledger(tmp_path: Path, *, status: str = "REQUEST_SENT", store_code: str = "ACMEWEAR") -> Path:
    ledger_db = tmp_path / "ledger.sqlite"
    ledger_db.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(ledger_db)
    try:
        init_customer_size_request_ledger(conn)
        conn.execute(
            """
            INSERT INTO customer_size_request_ledger (
                ledger_key, order_ref, db_row_id, store_code, sku_key, sku_id,
                channel, template_hash, status, request_planned_at, request_sent_at,
                last_observed_at, send_allowed, raw_order_id_exported,
                raw_reply_text_exported, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, 0, 0, ?)
            """,
            (
                "ledger1",
                "sha256:order1",
                36189,
                store_code,
                "CL_LINE31_TEST",
                "CL_LINE31_TEST_M",
                "KASPI_MERCHANT_CHAT_UI",
                request_template_hash(DEFAULT_REQUEST_TEMPLATE),
                status,
                "2026-06-17T10:00:00",
                "2026-06-17T10:02:00",
                "",
                "2026-06-17T10:02:00",
            ),
        )
        conn.commit()
    finally:
        conn.close()
    return ledger_db


def test_reply_polling_preflight_yellow_when_no_pollable_rows(tmp_path):
    report = build_preflight(
        ledger_db=_ledger(tmp_path, status="SEND_PLANNED_NO_SEND"),
        resident_reuse_manifest=_resident_reuse_manifest(tmp_path),
        output_dir=tmp_path / "out",
        supplied_approval_text="",
        approval_source="not_supplied",
    )

    assert report["gate"] == YELLOW_NO_TARGETS_GATE
    assert report["poll_target_count"] == 0
    assert report["approval_phrase_generated"] is False
    assert report["customer_send_performed"] is False
    assert report["chat_open_allowed_by_this_preflight"] is False


def test_reply_polling_preflight_generates_phrase_and_waits_for_owner_approval(tmp_path):
    report = build_preflight(
        ledger_db=_ledger(tmp_path),
        resident_reuse_manifest=_resident_reuse_manifest(tmp_path),
        output_dir=tmp_path / "out",
        supplied_approval_text="",
        approval_source="not_supplied",
    )

    assert report["gate"] == YELLOW_AWAITING_APPROVAL_GATE
    assert report["poll_target_count"] == 1
    assert report["approval_phrase_generated"] is True
    assert report["poll_targets_redacted"][0]["store_code"] == "ACMEWEAR"
    assert report["poll_targets_redacted"][0]["requires_matching_merchant_account"] is True
    assert report["poll_targets_redacted"][0]["expected_merchant_account_id"] == "30137883"
    phrase = report["_expected_approval_phrase"]
    assert "expected_merchant_account_id before searching or opening chat" in phrase
    assert "stop without searching that order" in phrase
    assert report["raw_order_id_exported"] is False
    assert report["raw_reply_text_exported"] is False


def test_reply_polling_preflight_green_with_exact_phrase(tmp_path):
    ledger_db = _ledger(tmp_path)
    resident_manifest = _resident_reuse_manifest(tmp_path)
    first = build_preflight(
        ledger_db=ledger_db,
        resident_reuse_manifest=resident_manifest,
        output_dir=tmp_path / "out",
        supplied_approval_text="",
        approval_source="not_supplied",
    )
    phrase = first["_expected_approval_phrase"]

    report = build_preflight(
        ledger_db=ledger_db,
        resident_reuse_manifest=resident_manifest,
        output_dir=tmp_path / "out",
        supplied_approval_text=phrase,
        approval_source="file",
    )

    assert report["gate"] == GREEN_GATE
    assert report["owner_approval_text_match"] is True
    assert report["customer_send_allowed_by_this_preflight"] is False
    assert report["kaspi_chat_write_allowed_by_this_preflight"] is False


def test_reply_polling_preflight_red_on_phrase_mismatch(tmp_path):
    report = build_preflight(
        ledger_db=_ledger(tmp_path),
        resident_reuse_manifest=_resident_reuse_manifest(tmp_path),
        output_dir=tmp_path / "out",
        supplied_approval_text="wrong",
        approval_source="file",
    )

    assert report["gate"] == RED_GATE
    assert "owner_approval_text_mismatch" in report["unsafe_blockers"]


def test_reply_polling_preflight_red_on_unknown_store_selector(tmp_path):
    report = build_preflight(
        ledger_db=_ledger(tmp_path, store_code="UNKNOWN"),
        resident_reuse_manifest=_resident_reuse_manifest(tmp_path),
        output_dir=tmp_path / "out",
        supplied_approval_text="",
        approval_source="not_supplied",
    )

    assert report["gate"] == RED_GATE
    assert "target_store_has_no_known_merchant_account_id" in report["unsafe_blockers"]


def test_reply_polling_preflight_red_on_unsafe_resident_invariant(tmp_path):
    report = build_preflight(
        ledger_db=_ledger(tmp_path),
        resident_reuse_manifest=_resident_reuse_manifest(tmp_path, unsafe=True),
        output_dir=tmp_path / "out",
        supplied_approval_text="",
        approval_source="not_supplied",
    )

    assert report["gate"] == RED_GATE
    assert "resident_reuse_invariant_chat_open_allowed_not_false" in report["unsafe_blockers"]
