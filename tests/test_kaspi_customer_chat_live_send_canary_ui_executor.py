import argparse
import json
import sqlite3
from datetime import datetime
from pathlib import Path

from core.ops.customer_size_request import (
    DEFAULT_REQUEST_TEMPLATE,
    init_customer_size_request_ledger,
    request_template_hash,
)
from scripts.run_kaspi_customer_chat_live_send_canary_ui_executor import (
    ENV_GATE,
    READY_NO_SEND_GATE,
    RESULT_GREEN_GATE,
    TRANSPORT_BLOCKED_GATE,
    UNSAFE_GATE,
    run as run_executor,
)


def _write_json(path: Path, payload: dict) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path


def _ledger(tmp_path: Path, *, status: str = "SEND_PLANNED_NO_SEND") -> Path:
    ledger_db = tmp_path / "ledger.sqlite"
    with sqlite3.connect(ledger_db) as conn:
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
                36170,
                "ACMEWEAR",
                "sku",
                "sku-id",
                "KASPI_MERCHANT_CHAT_UI",
                request_template_hash(DEFAULT_REQUEST_TEMPLATE),
                status,
                "2026-06-18T10:00:00",
                "2026-06-18T10:00:00",
            ),
        )
        conn.commit()
    return ledger_db


def _surfaces(tmp_path: Path, *, ledger_status: str = "SEND_PLANNED_NO_SEND") -> tuple[Path, Path]:
    approval_dir = tmp_path / "approval"
    approval_dir.mkdir(parents=True)
    template_hash = request_template_hash(DEFAULT_REQUEST_TEMPLATE)
    approval = {
        "gate": "GREEN_LIVE_SEND_CANARY_APPROVAL_PACKET_READY_NO_SEND",
        "approval_phrase_generated": True,
        "selected_order_ref": "sha256:order1",
        "selected_db_row_id": 36170,
        "selected_store_code": "ACMEWEAR",
        "selected_status_filter": "NEW",
        "template_hash": template_hash,
        "expected_merchant_account_id": "30137883",
    }
    _write_json(approval_dir / "manifest.json", approval)
    _write_json(
        tmp_path / "heartbeat.json",
        {
            "gate": "GREEN_KASPI_CUSTOMER_CHAT_RESIDENT_NO_SEND_CONTROLLER_READY",
            "recorded_at": datetime.now().isoformat(timespec="seconds"),
            "browser_should_remain_open": True,
            "orders_search_input_visible": True,
        },
    )
    ledger_db = _ledger(tmp_path, status=ledger_status)
    preflight = {
        **approval,
        "gate": "GREEN_LIVE_SEND_CANARY_EXECUTION_PREFLIGHT_READY_NO_SEND",
        "owner_approval_text_match": True,
        "resident_current_heartbeat_path": str(tmp_path / "heartbeat.json"),
        "ledger_db": str(ledger_db),
    }
    preflight_path = _write_json(tmp_path / "preflight" / "manifest.json", preflight)
    return approval_dir, preflight_path


def _args(
    tmp_path: Path,
    *,
    approval_dir: Path,
    preflight_path: Path,
    apply: bool = False,
    record: bool = False,
    selector_id: str = "30137883",
) -> argparse.Namespace:
    return argparse.Namespace(
        approval_dir=approval_dir,
        live_send_execution_preflight_manifest=preflight_path,
        output_dir=tmp_path / "out",
        apply=apply,
        heartbeat_max_age_seconds=999999.0,
        record_observed_send_result=record,
        visible_merchant_selector_id=selector_id,
        proof_source="test_ui_helper",
        proof_note="redacted test proof",
    )


def test_live_send_ui_executor_ready_no_send_without_apply(tmp_path):
    approval_dir, preflight_path = _surfaces(tmp_path)

    manifest = run_executor(_args(tmp_path, approval_dir=approval_dir, preflight_path=preflight_path))

    assert manifest["gate"] == READY_NO_SEND_GATE
    assert manifest["blockers"] == []
    assert manifest["pending_actions"] == ["apply_not_requested"]
    assert manifest["customer_send_performed_by_this_script"] is False
    assert manifest["result_recorded"] is False
    assert not (approval_dir / "live_send_canary_result_redacted.json").exists()


def test_live_send_ui_executor_blocks_apply_without_env_gate(tmp_path):
    approval_dir, preflight_path = _surfaces(tmp_path)

    manifest = run_executor(
        _args(tmp_path, approval_dir=approval_dir, preflight_path=preflight_path, apply=True),
        environ={},
    )

    assert manifest["gate"] == TRANSPORT_BLOCKED_GATE
    assert f"{ENV_GATE}_not_1" in manifest["blockers"]
    assert manifest["result_recorded"] is False


def test_live_send_ui_executor_records_observed_selector_locked_result(tmp_path):
    approval_dir, preflight_path = _surfaces(tmp_path)

    manifest = run_executor(
        _args(
            tmp_path,
            approval_dir=approval_dir,
            preflight_path=preflight_path,
            apply=True,
            record=True,
        ),
        environ={ENV_GATE: "1"},
    )
    result = json.loads((approval_dir / "live_send_canary_result_redacted.json").read_text())
    closeout = (approval_dir / "live_send_canary_closeout.md").read_text(encoding="utf-8")

    assert manifest["gate"] == RESULT_GREEN_GATE
    assert manifest["result_recorded"] is True
    assert result["gate"] == RESULT_GREEN_GATE
    assert result["selected_order_ref"] == "sha256:order1"
    assert result["visible_merchant_selector_id"] == "30137883"
    assert result["sent_count"] == 1
    assert result["raw_order_id_exported"] is False
    assert "Gate: GREEN_LIVE_SIZE_REQUEST_TEMPLATE_SENT_ONE_ORDER" in closeout
    assert "938710" not in json.dumps(result, ensure_ascii=False)


def test_live_send_ui_executor_rejects_observed_wrong_merchant_selector(tmp_path):
    approval_dir, preflight_path = _surfaces(tmp_path)

    manifest = run_executor(
        _args(
            tmp_path,
            approval_dir=approval_dir,
            preflight_path=preflight_path,
            apply=True,
            record=True,
            selector_id="30000001",
        ),
        environ={ENV_GATE: "1"},
    )

    assert manifest["gate"] == UNSAFE_GATE
    assert "observed_visible_merchant_selector_mismatch" in manifest["unsafe_blockers"]
    assert not (approval_dir / "live_send_canary_result_redacted.json").exists()


def test_live_send_ui_executor_rejects_current_ledger_after_send_status(tmp_path):
    approval_dir, preflight_path = _surfaces(tmp_path, ledger_status="REQUEST_SENT")

    manifest = run_executor(
        _args(
            tmp_path,
            approval_dir=approval_dir,
            preflight_path=preflight_path,
            apply=True,
            record=True,
        ),
        environ={ENV_GATE: "1"},
    )

    assert manifest["gate"] == UNSAFE_GATE
    assert "current_ledger_status_not_send_planned_no_send:REQUEST_SENT" in manifest["unsafe_blockers"]
