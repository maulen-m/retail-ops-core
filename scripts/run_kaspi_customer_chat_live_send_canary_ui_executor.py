#!/usr/bin/env python3
"""Gate and record the one-order Kaspi customer-size live-send canary.

This script is intentionally narrow. It does not automate Kaspi UI clicks yet;
instead it guards the exact preflight and provides one canonical way for a UI
helper/browser agent to record the redacted result after it has actually sent
the one approved message.

Default mode is no-send. Apply mode requires:
- --apply
- ENABLE_KASPI_CUSTOMER_CHAT_LIVE_SEND_CANARY=1
- a GREEN live-send execution preflight
- current selector/order/template alignment
- a fresh GREEN resident heartbeat
- current ledger status still SEND_PLANNED_NO_SEND

It never writes raw order IDs, customer text, phones, cookies, or session data.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_APPROVAL_DIR = (
    REPO_ROOT
    / "exports"
    / "validation"
    / "kaspi_customer_size_resident_proof_followup_after_current_priority_green_20260618"
    / "live_send_approval"
)
DEFAULT_PREFLIGHT_MANIFEST = (
    REPO_ROOT
    / "exports"
    / "validation"
    / "kaspi_customer_size_live_send_execution_preflight_current_20260618_after_all_priority_restore_green"
    / "manifest.json"
)
ENV_GATE = "ENABLE_KASPI_CUSTOMER_CHAT_LIVE_SEND_CANARY"
PREFLIGHT_GREEN_GATE = "GREEN_LIVE_SEND_CANARY_EXECUTION_PREFLIGHT_READY_NO_SEND"
APPROVAL_GREEN_GATE = "GREEN_LIVE_SEND_CANARY_APPROVAL_PACKET_READY_NO_SEND"
RESIDENT_HEARTBEAT_GREEN_GATE = "GREEN_KASPI_CUSTOMER_CHAT_RESIDENT_NO_SEND_CONTROLLER_READY"
RESULT_GREEN_GATE = "GREEN_LIVE_SIZE_REQUEST_TEMPLATE_SENT_ONE_ORDER"
READY_NO_SEND_GATE = "GREEN_LIVE_SEND_CANARY_UI_EXECUTOR_READY_NO_SEND"
NO_APPLY_GATE = "YELLOW_LIVE_SEND_CANARY_UI_EXECUTOR_AWAITING_APPLY_NO_SEND"
TRANSPORT_BLOCKED_GATE = "YELLOW_LIVE_SEND_CANARY_UI_EXECUTOR_TRANSPORT_NOT_PROVIDED_NO_SEND"
RESULT_EXISTS_GATE = "YELLOW_LIVE_SEND_CANARY_UI_EXECUTOR_RESULT_ALREADY_EXISTS_NO_SEND"
UNSAFE_GATE = "RED_LIVE_SEND_CANARY_UI_EXECUTOR_UNSAFE_NO_SEND"
POST_SEND_OR_REPLY_STATUSES = {
    "REQUEST_SENT",
    "POLLING",
    "REPLY_OBSERVED",
    "REPLY_OBSERVED_NO_SIZE_SIGNAL",
    "CLASSIFICATION_READY",
    "SIZE_CONFIRMED",
    "UNKNOWN_SEND_OUTCOME",
    "SEND_IN_PROGRESS",
}


def _default_output_dir() -> Path:
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return REPO_ROOT / "exports" / "validation" / f"kaspi_customer_chat_live_send_ui_executor_{stamp}"


def _read_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"Expected JSON object at {path}")
    return payload


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _parse_dt(value: Any) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return datetime.fromisoformat(text)
    except ValueError:
        return None


def _age_seconds(value: Any) -> float | None:
    parsed = _parse_dt(value)
    if parsed is None:
        return None
    return max((datetime.now() - parsed).total_seconds(), 0.0)


def _read_current_ledger_rows(
    ledger_db: Path,
    *,
    order_ref: str,
    template_hash: str,
) -> tuple[list[dict[str, Any]], list[str]]:
    if not ledger_db.exists():
        return [], ["ledger_db_missing"]
    try:
        conn = sqlite3.connect(f"file:{ledger_db.resolve()}?mode=ro", uri=True)
        conn.row_factory = sqlite3.Row
        try:
            rows = conn.execute(
                """
                SELECT ledger_key, order_ref, template_hash, status, db_row_id, store_code,
                       raw_order_id_exported, raw_reply_text_exported
                FROM customer_size_request_ledger
                WHERE order_ref = ?
                  AND template_hash = ?
                ORDER BY updated_at DESC, ledger_key
                """,
                (order_ref, template_hash),
            ).fetchall()
        finally:
            conn.close()
    except sqlite3.Error as exc:
        return [], [f"ledger_read_failed:{type(exc).__name__}"]
    return [dict(row) for row in rows], []


def _redaction_scan(payload: dict[str, Any]) -> list[str]:
    text = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    blockers: list[str] = []
    phone_pattern = re.compile(
        r"(?<!\d)(?:\+?7|8)\D{0,3}\d{3}\D{0,3}\d{3}\D{0,3}\d{2}\D{0,3}\d{2}(?!\d)"
    )
    if phone_pattern.search(text):
        blockers.append("phone_like_value_detected")
    # `cookie_token_session_exported: false` is a required downstream safety
    # flag, so do not treat that label itself as leaked session material.
    label_safe_text = text.replace("cookie_token_session_exported", "safe_session_export_flag")
    for forbidden in ["cookie", "authorization", "bearer", "localStorage", "sessionStorage"]:
        if forbidden.lower() in label_safe_text.lower():
            blockers.append(f"forbidden_session_label_detected:{forbidden}")
    return blockers


def _load_surfaces(args: argparse.Namespace) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    preflight = _read_json(args.live_send_execution_preflight_manifest.resolve())
    approval_dir = args.approval_dir.resolve()
    approval = _read_json(approval_dir / "manifest.json")
    heartbeat_path_value = str(preflight.get("resident_current_heartbeat_path") or "").strip()
    heartbeat = _read_json(Path(heartbeat_path_value)) if heartbeat_path_value else {}
    return preflight, approval, heartbeat


def _alignment_blockers(
    *,
    preflight: dict[str, Any],
    approval: dict[str, Any],
    heartbeat: dict[str, Any],
    heartbeat_max_age_seconds: float,
) -> tuple[list[str], list[str], list[dict[str, Any]]]:
    blockers: list[str] = []
    unsafe: list[str] = []
    ledger_rows: list[dict[str, Any]] = []

    if preflight.get("gate") != PREFLIGHT_GREEN_GATE:
        blockers.append(f"preflight_gate_not_green:{preflight.get('gate')}")
    if approval.get("gate") != APPROVAL_GREEN_GATE:
        blockers.append(f"approval_gate_not_green:{approval.get('gate')}")
    if preflight.get("owner_approval_text_match") is not True:
        blockers.append("preflight_owner_approval_text_not_matched")

    fields = [
        "selected_order_ref",
        "selected_db_row_id",
        "selected_store_code",
        "template_hash",
        "expected_merchant_account_id",
    ]
    for field in fields:
        if str(preflight.get(field) or "") != str(approval.get(field) or ""):
            unsafe.append(f"preflight_approval_{field}_mismatch")

    if heartbeat.get("gate") != RESIDENT_HEARTBEAT_GREEN_GATE:
        blockers.append(f"resident_heartbeat_not_green:{heartbeat.get('gate')}")
    if heartbeat.get("browser_should_remain_open") is not True:
        blockers.append("resident_heartbeat_browser_should_remain_open_not_true")
    if heartbeat.get("orders_search_input_visible") is not True:
        blockers.append("resident_heartbeat_orders_search_input_not_visible")
    heartbeat_age = _age_seconds(heartbeat.get("recorded_at"))
    if heartbeat_age is None:
        blockers.append("resident_heartbeat_recorded_at_missing_or_invalid")
    elif heartbeat_age > heartbeat_max_age_seconds:
        blockers.append("resident_heartbeat_stale")

    ledger_db = Path(str(preflight.get("ledger_db") or ""))
    order_ref = str(preflight.get("selected_order_ref") or "")
    template_hash = str(preflight.get("template_hash") or "")
    if order_ref and template_hash:
        ledger_rows, ledger_blockers = _read_current_ledger_rows(
            ledger_db,
            order_ref=order_ref,
            template_hash=template_hash,
        )
        blockers.extend(ledger_blockers)
        if not ledger_rows:
            blockers.append("current_ledger_row_missing_for_target")
        for row in ledger_rows:
            status = str(row.get("status") or "").strip().upper()
            if status != "SEND_PLANNED_NO_SEND":
                unsafe.append(f"current_ledger_status_not_send_planned_no_send:{status}")
            if status in POST_SEND_OR_REPLY_STATUSES:
                unsafe.append(f"current_ledger_already_after_send_or_reply:{status}")
            if bool(row.get("raw_order_id_exported")):
                unsafe.append("current_ledger_raw_order_id_exported_true")
            if bool(row.get("raw_reply_text_exported")):
                unsafe.append("current_ledger_raw_reply_text_exported_true")
    else:
        blockers.append("preflight_missing_order_ref_or_template_hash")
    return blockers, unsafe, ledger_rows


def build_observed_send_result(
    *,
    approval: dict[str, Any],
    visible_merchant_selector_id: str,
    proof_source: str,
    proof_note: str = "",
) -> dict[str, Any]:
    return {
        "gate": RESULT_GREEN_GATE,
        "recorded_at": datetime.now().isoformat(timespec="seconds"),
        "proof_source": proof_source,
        "proof_note": proof_note,
        "selected_order_ref": approval.get("selected_order_ref"),
        "selected_db_row_id": approval.get("selected_db_row_id"),
        "selected_store_code": approval.get("selected_store_code"),
        "selected_status_filter": approval.get("selected_status_filter"),
        "template_hash": approval.get("template_hash"),
        "merchant_account_match_proven": (
            str(visible_merchant_selector_id).strip()
            == str(approval.get("expected_merchant_account_id") or "").strip()
        ),
        "visible_merchant_selector_id": str(visible_merchant_selector_id).strip(),
        "store_scoped_selector_map_applied": True,
        "browser_session_preserved": True,
        "order_search_performed": True,
        "chat_opened": True,
        "message_text_typed": True,
        "message_sent": True,
        "send_confirmation_observed": True,
        "sent_count": 1,
        "other_customer_messages_sent": False,
        "raw_order_id_exported": False,
        "raw_customer_text_exported": False,
        "raw_phone_exported": False,
        "cookie_token_session_exported": False,
    }


def _build_closeout(manifest: dict[str, Any]) -> str:
    lines = [
        "# Kaspi Customer Chat Live Send Canary UI Executor",
        "",
        f"Gate: {manifest['gate']}",
        "",
        "## Scope",
        "",
        "Guarded one-order customer-size live-send canary executor/recorder. Default mode performs no customer send.",
        "",
        "## Target",
        "",
        f"- Approval dir: `{manifest.get('approval_dir')}`",
        f"- Preflight manifest: `{manifest.get('live_send_execution_preflight_manifest')}`",
        f"- Selected order ref: `{manifest.get('selected_order_ref')}`",
        f"- Selected DB row: `{manifest.get('selected_db_row_id')}`",
        f"- Store: `{manifest.get('selected_store_code')}`",
        f"- Expected merchant selector ID: `{manifest.get('expected_merchant_account_id')}`",
        "",
        "## Safety",
        "",
        f"- Apply requested: {str(manifest.get('apply_requested')).lower()}",
        f"- Env gate enabled: {str(manifest.get('env_gate_enabled')).lower()}",
        f"- Customer send performed by this script: {str(manifest.get('customer_send_performed_by_this_script')).lower()}",
        f"- Result recorded: {str(manifest.get('result_recorded')).lower()}",
        "- Raw order IDs/customer text/phones/session material exported: false",
        "",
    ]
    blockers = [*(manifest.get("unsafe_blockers") or []), *(manifest.get("blockers") or [])]
    if blockers:
        lines.extend(["## Blockers", ""])
        lines.extend(f"- {blocker}" for blocker in blockers)
        lines.append("")
    lines.extend(["## Next Action", "", f"- {manifest.get('exact_next_action')}", ""])
    return "\n".join(lines)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--approval-dir", type=Path, default=DEFAULT_APPROVAL_DIR)
    parser.add_argument(
        "--live-send-execution-preflight-manifest",
        type=Path,
        default=DEFAULT_PREFLIGHT_MANIFEST,
    )
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--heartbeat-max-age-seconds", type=float, default=1800.0)
    parser.add_argument(
        "--record-observed-send-result",
        action="store_true",
        help="Record a redacted result after a separate UI/browser helper truly sent the one approved message.",
    )
    parser.add_argument("--visible-merchant-selector-id", default="")
    parser.add_argument("--proof-source", default="ui_helper_observed")
    parser.add_argument("--proof-note", default="")
    return parser


def run(args: argparse.Namespace, *, environ: dict[str, str] | None = None) -> dict[str, Any]:
    environ = dict(os.environ if environ is None else environ)
    output_dir = (args.output_dir or _default_output_dir()).resolve()
    approval_dir = args.approval_dir.resolve()
    result_path = approval_dir / "live_send_canary_result_redacted.json"
    result_closeout_path = approval_dir / "live_send_canary_closeout.md"
    preflight, approval, heartbeat = _load_surfaces(args)
    blockers, unsafe, ledger_rows = _alignment_blockers(
        preflight=preflight,
        approval=approval,
        heartbeat=heartbeat,
        heartbeat_max_age_seconds=float(args.heartbeat_max_age_seconds),
    )

    apply_requested = bool(args.apply)
    env_gate_enabled = environ.get(ENV_GATE) == "1"
    if apply_requested and not env_gate_enabled:
        blockers.append(f"{ENV_GATE}_not_1")

    result_already_exists = result_path.exists() or result_closeout_path.exists()
    if result_already_exists:
        blockers.append("live_send_result_or_closeout_already_exists")

    result_payload: dict[str, Any] | None = None
    result_recorded = False
    if args.record_observed_send_result:
        if not str(args.visible_merchant_selector_id or "").strip():
            unsafe.append("visible_merchant_selector_id_required_for_observed_result")
        result_payload = build_observed_send_result(
            approval=approval,
            visible_merchant_selector_id=str(args.visible_merchant_selector_id or "").strip(),
            proof_source=str(args.proof_source or "ui_helper_observed"),
            proof_note=str(args.proof_note or ""),
        )
        if result_payload.get("merchant_account_match_proven") is not True:
            unsafe.append("observed_visible_merchant_selector_mismatch")
        unsafe.extend(_redaction_scan(result_payload))
    elif apply_requested and env_gate_enabled:
        blockers.append("record_observed_send_result_not_supplied")

    if unsafe:
        gate = UNSAFE_GATE
    elif result_already_exists:
        gate = RESULT_EXISTS_GATE
    elif not apply_requested and not blockers:
        gate = READY_NO_SEND_GATE
    elif blockers:
        gate = NO_APPLY_GATE if not apply_requested else TRANSPORT_BLOCKED_GATE
    else:
        gate = RESULT_GREEN_GATE
        if result_payload is not None:
            _write_json(result_path, result_payload)
            _write_text(
                result_closeout_path,
                "\n".join(
                    [
                        "# Kaspi Customer Size Live Send Canary Closeout",
                        "",
                        f"Gate: {RESULT_GREEN_GATE}",
                        "",
                        f"- Selected order ref: {result_payload.get('selected_order_ref')}",
                        f"- Store: {result_payload.get('selected_store_code')}",
                        f"- Visible merchant selector ID: {result_payload.get('visible_merchant_selector_id')}",
                        "- Sent count: 1",
                        "- Raw order ID/customer text/phone/session material exported: false",
                        "",
                    ]
                ),
            )
            result_recorded = True

    manifest = {
        "gate": gate,
        "run_at": datetime.now().isoformat(timespec="seconds"),
        "approval_dir": str(approval_dir),
        "live_send_execution_preflight_manifest": str(
            args.live_send_execution_preflight_manifest.resolve()
        ),
        "output_dir": str(output_dir),
        "selected_order_ref": approval.get("selected_order_ref"),
        "selected_db_row_id": approval.get("selected_db_row_id"),
        "selected_store_code": approval.get("selected_store_code"),
        "expected_merchant_account_id": approval.get("expected_merchant_account_id"),
        "template_hash": approval.get("template_hash"),
        "preflight_gate": preflight.get("gate"),
        "approval_gate": approval.get("gate"),
        "resident_heartbeat_gate": heartbeat.get("gate"),
        "resident_heartbeat_recorded_at": heartbeat.get("recorded_at"),
        "resident_heartbeat_age_seconds": _age_seconds(heartbeat.get("recorded_at")),
        "current_ledger_rows_redacted": ledger_rows,
        "apply_requested": apply_requested,
        "env_gate_name": ENV_GATE,
        "env_gate_enabled": env_gate_enabled,
        "record_observed_send_result": bool(args.record_observed_send_result),
        "result_json_path": str(result_path),
        "result_closeout_path": str(result_closeout_path),
        "result_recorded": result_recorded,
        "customer_send_performed_by_this_script": False,
        "customer_send_result_recorded_from_external_ui_helper": result_recorded,
        "kaspi_chat_write_performed_by_this_script": False,
        "google_board_write_allowed": False,
        "db_write_allowed": False,
        "telegram_send_allowed": False,
        "raw_order_id_exported": False,
        "raw_customer_text_exported": False,
        "raw_phone_exported": False,
        "raw_session_material_exported": False,
        "blockers": sorted(set(blockers)),
        "pending_actions": [] if apply_requested else ["apply_not_requested"],
        "unsafe_blockers": sorted(set(unsafe)),
        "exact_next_action": (
            "Run validate_kaspi_customer_chat_live_send_canary_result.py, then run after-live-send watch."
            if result_recorded
            else "Use a browser/UI helper to perform the one approved selector-locked send, then rerun this script with --apply --record-observed-send-result and the visible merchant selector ID."
        ),
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    _write_json(output_dir / "manifest.json", manifest)
    _write_text(output_dir / "closeout.md", _build_closeout(manifest))
    return manifest


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    manifest = run(args)
    print(json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True))
    if str(manifest.get("gate") or "").startswith("RED_"):
        return 2
    if manifest.get("gate") == RESULT_GREEN_GATE:
        return 0
    return 1 if args.apply else 0


if __name__ == "__main__":
    raise SystemExit(main())
