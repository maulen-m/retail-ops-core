#!/usr/bin/env python3
"""Report readiness after the open-chat/no-type canary.

This is a local control-plane gate only. It does not open Kaspi, type, send,
read customer messages, write Google Board, write the production DB, or send
Telegram/WhatsApp. Its job is to keep the workflow from jumping directly from
"chat opened safely" to broader sends.
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path
from typing import Any

from scripts.validate_kaspi_customer_chat_open_no_type_canary_result import (
    ACCEPTED_GATE as OPEN_CHAT_ACCEPTED_GATE,
    validate as validate_open_chat_result,
)


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OPEN_CHAT_PACKET_DIR = (
    REPO_ROOT
    / "exports"
    / "validation"
    / "kaspi_customer_chat_open_no_type_canary_current_20260618_1549_no_send"
)
DEFAULT_LIVE_SEND_APPROVAL_MANIFEST = (
    REPO_ROOT
    / "exports"
    / "validation"
    / "kaspi_customer_size_resident_proof_followup_after_current_priority_green_20260618"
    / "live_send_approval"
    / "manifest.json"
)
DEFAULT_LIVE_SEND_PREFLIGHT_MANIFEST = (
    REPO_ROOT
    / "exports"
    / "validation"
    / "kaspi_customer_size_live_send_execution_preflight_current_20260618_1540_fresh_heartbeat_no_send"
    / "manifest.json"
)
DEFAULT_RESIDENT_HEARTBEAT = (
    REPO_ROOT
    / "exports"
    / "validation"
    / "kaspi_customer_chat_resident_no_send_controller_current"
    / "resident_controller_heartbeat.json"
)

LIVE_SEND_APPROVAL_GREEN_GATE = "GREEN_LIVE_SEND_CANARY_APPROVAL_PACKET_READY_NO_SEND"
LIVE_SEND_PREFLIGHT_GREEN_GATE = "GREEN_LIVE_SEND_CANARY_EXECUTION_PREFLIGHT_READY_NO_SEND"
RESIDENT_HEARTBEAT_GREEN_GATE = "GREEN_KASPI_CUSTOMER_CHAT_RESIDENT_NO_SEND_CONTROLLER_READY"

GREEN_GATE = "GREEN_POST_OPEN_CHAT_SEQUENCE_READY_FOR_ONE_ORDER_LIVE_SEND_APPROVAL_NO_EXTERNAL_WRITE"
YELLOW_OPEN_RESULT_GATE = (
    "YELLOW_POST_OPEN_CHAT_SEQUENCE_BLOCKED_OPEN_CHAT_RESULT_NOT_GREEN_NO_EXTERNAL_WRITE"
)
YELLOW_PREFLIGHT_GATE = (
    "YELLOW_POST_OPEN_CHAT_SEQUENCE_BLOCKED_LIVE_SEND_PREFLIGHT_NOT_READY_NO_EXTERNAL_WRITE"
)
RED_GATE = "RED_POST_OPEN_CHAT_SEQUENCE_UNSAFE_NO_EXTERNAL_WRITE"

TARGET_FIELDS = (
    "selected_order_ref",
    "selected_db_row_id",
    "selected_store_code",
    "template_hash",
    "expected_merchant_account_id",
)


def _default_output_dir() -> Path:
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return REPO_ROOT / "exports" / "validation" / f"kaspi_customer_size_post_open_chat_readiness_{stamp}"


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


def _safe_read_json(path: Path) -> tuple[dict[str, Any], list[str]]:
    if not path.exists():
        return {}, [f"missing:{path.name}"]
    try:
        return _read_json(path), []
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        return {}, [f"invalid_json:{path.name}:{type(exc).__name__}"]


def _target_values(payload: dict[str, Any]) -> dict[str, str]:
    return {field: str(payload.get(field) or "") for field in TARGET_FIELDS}


def _alignment_blockers(
    *,
    open_validation: dict[str, Any],
    approval: dict[str, Any],
    preflight: dict[str, Any],
    heartbeat: dict[str, Any],
) -> tuple[list[str], list[str]]:
    blockers: list[str] = []
    unsafe: list[str] = []

    if approval.get("gate") != LIVE_SEND_APPROVAL_GREEN_GATE:
        blockers.append(f"live_send_approval_not_green:{approval.get('gate') or 'MISSING'}")
    if preflight.get("gate") != LIVE_SEND_PREFLIGHT_GREEN_GATE:
        blockers.append(f"live_send_preflight_not_green:{preflight.get('gate') or 'MISSING'}")
    if heartbeat.get("gate") != RESIDENT_HEARTBEAT_GREEN_GATE:
        blockers.append(f"resident_heartbeat_not_green:{heartbeat.get('gate') or 'MISSING'}")
    if heartbeat and heartbeat.get("orders_search_input_visible") is not True:
        blockers.append("resident_orders_search_input_not_visible")
    if heartbeat and heartbeat.get("browser_should_remain_open") is not True:
        blockers.append("resident_browser_should_remain_open_not_true")

    invariant_false = [
        "customer_send_allowed",
        "kaspi_chat_write_allowed",
        "chat_opened",
        "message_text_typed",
        "message_sent",
        "raw_order_id_exported",
        "raw_customer_text_exported",
        "raw_phone_exported",
        "raw_session_material_exported",
    ]
    for key in invariant_false:
        if heartbeat and heartbeat.get(key) is not False:
            unsafe.append(f"resident_heartbeat_invariant_{key}_not_false")

    open_target = _target_values(open_validation)
    approval_target = _target_values(approval)
    preflight_target = _target_values(preflight)
    for field in TARGET_FIELDS:
        open_value = open_target.get(field, "")
        approval_value = approval_target.get(field, "")
        preflight_value = preflight_target.get(field, "")
        if open_value and approval_value and open_value != approval_value:
            unsafe.append(f"open_chat_live_send_approval_target_mismatch:{field}")
        if open_value and preflight_value and open_value != preflight_value:
            unsafe.append(f"open_chat_live_send_preflight_target_mismatch:{field}")
        if approval_value and preflight_value and approval_value != preflight_value:
            unsafe.append(f"approval_preflight_target_mismatch:{field}")
        if not approval_value:
            blockers.append(f"live_send_approval_missing_field:{field}")
        if not preflight_value:
            blockers.append(f"live_send_preflight_missing_field:{field}")

    return blockers, unsafe


def _closeout(manifest: dict[str, Any]) -> str:
    lines = [
        "# Kaspi Customer Size Post-Open-Chat Readiness",
        "",
        f"Gate: {manifest['gate']}",
        "",
        "## Scope",
        "",
        "Local-only gate after open-chat/no-type proof and before any one-order live-send canary.",
        "",
        "## Inputs",
        "",
        f"- Open-chat validation: `{manifest.get('open_chat_validation_path')}`",
        f"- Live-send approval manifest: `{manifest.get('live_send_approval_manifest_path')}`",
        f"- Live-send preflight manifest: `{manifest.get('live_send_preflight_manifest_path')}`",
        f"- Resident heartbeat: `{manifest.get('resident_heartbeat_path')}`",
        "",
        "## Safety",
        "",
        "- Customer send performed: false",
        "- Kaspi chat write performed: false",
        "- Browser action performed: false",
        "- Google Board write allowed: false",
        "- Production DB write allowed: false",
        "- Telegram/WhatsApp send allowed: false",
        "- Raw order IDs/customer text/phones/session material exported: false",
        "",
        "## Next Action",
        "",
        f"- {manifest.get('exact_next_action')}",
        "",
    ]
    blockers = [*(manifest.get("unsafe_blockers") or []), *(manifest.get("blockers") or [])]
    if blockers:
        lines.extend(["## Blockers", ""])
        lines.extend(f"- {blocker}" for blocker in blockers)
        lines.append("")
    return "\n".join(lines)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--open-chat-packet-dir", type=Path, default=DEFAULT_OPEN_CHAT_PACKET_DIR)
    parser.add_argument("--open-chat-validation-json", type=Path)
    parser.add_argument("--live-send-approval-manifest", type=Path, default=DEFAULT_LIVE_SEND_APPROVAL_MANIFEST)
    parser.add_argument("--live-send-preflight-manifest", type=Path, default=DEFAULT_LIVE_SEND_PREFLIGHT_MANIFEST)
    parser.add_argument("--resident-current-heartbeat", type=Path, default=DEFAULT_RESIDENT_HEARTBEAT)
    parser.add_argument("--output-dir", type=Path)
    return parser


def build_report(args: argparse.Namespace) -> dict[str, Any]:
    output_dir = (args.output_dir or _default_output_dir()).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    open_validation_path = (
        args.open_chat_validation_json.resolve()
        if args.open_chat_validation_json
        else output_dir / "open_chat_no_type_result_validation.json"
    )
    if args.open_chat_validation_json:
        open_validation, open_validation_errors = _safe_read_json(open_validation_path)
    else:
        validator_args = argparse.Namespace(
            packet_dir=args.open_chat_packet_dir.resolve(),
            result_json=None,
            closeout_md=None,
            output_json=None,
            require_green=False,
        )
        open_validation = validate_open_chat_result(validator_args)
        open_validation_errors = []
        _write_json(open_validation_path, open_validation)

    approval, approval_errors = _safe_read_json(args.live_send_approval_manifest.resolve())
    preflight, preflight_errors = _safe_read_json(args.live_send_preflight_manifest.resolve())
    heartbeat, heartbeat_errors = _safe_read_json(args.resident_current_heartbeat.resolve())

    blockers: list[str] = [
        *(f"open_chat_validation_{error}" for error in open_validation_errors),
        *(f"live_send_approval_{error}" for error in approval_errors),
        *(f"live_send_preflight_{error}" for error in preflight_errors),
        *(f"resident_heartbeat_{error}" for error in heartbeat_errors),
    ]
    unsafe: list[str] = []

    open_gate = str(open_validation.get("gate") or "MISSING")
    if open_gate.startswith("RED_"):
        unsafe.append(f"open_chat_validation_red:{open_gate}")
    elif open_gate != OPEN_CHAT_ACCEPTED_GATE:
        blockers.append(f"open_chat_result_not_accepted:{open_gate}")

    if not unsafe and open_gate == OPEN_CHAT_ACCEPTED_GATE:
        alignment_blockers, alignment_unsafe = _alignment_blockers(
            open_validation=open_validation,
            approval=approval,
            preflight=preflight,
            heartbeat=heartbeat,
        )
        blockers.extend(alignment_blockers)
        unsafe.extend(alignment_unsafe)

    if unsafe:
        gate = RED_GATE
        exact_next_action = "Stop. Inspect and resolve the unsafe post-open-chat blocker before any customer-send canary."
    elif blockers:
        if any(blocker.startswith("open_chat_result_not_accepted") for blocker in blockers):
            gate = YELLOW_OPEN_RESULT_GATE
            exact_next_action = (
                "Complete the owner-approved open-chat/no-type canary result first; do not type, send, "
                "or run the live-send canary yet."
            )
        else:
            gate = YELLOW_PREFLIGHT_GATE
            exact_next_action = (
                "Refresh the live-send approval/preflight and resident heartbeat until they align with "
                "the accepted open-chat proof; do not send yet."
            )
    else:
        gate = GREEN_GATE
        exact_next_action = (
            "Proceed only to the separately owner-approved one-order live-send canary preflight/execution "
            "for the same target; no bulk send or second order is authorized."
        )

    manifest = {
        "gate": gate,
        "run_at": datetime.now().isoformat(timespec="seconds"),
        "output_dir": str(output_dir),
        "open_chat_packet_dir": str(args.open_chat_packet_dir.resolve()),
        "open_chat_validation_path": str(open_validation_path),
        "open_chat_validation_gate": open_gate,
        "live_send_approval_manifest_path": str(args.live_send_approval_manifest.resolve()),
        "live_send_approval_gate": approval.get("gate", ""),
        "live_send_preflight_manifest_path": str(args.live_send_preflight_manifest.resolve()),
        "live_send_preflight_gate": preflight.get("gate", ""),
        "resident_heartbeat_path": str(args.resident_current_heartbeat.resolve()),
        "resident_heartbeat_gate": heartbeat.get("gate", ""),
        "resident_orders_search_input_visible": heartbeat.get("orders_search_input_visible"),
        "selected_order_ref": open_validation.get("selected_order_ref") or approval.get("selected_order_ref"),
        "selected_db_row_id": open_validation.get("selected_db_row_id") or approval.get("selected_db_row_id"),
        "selected_store_code": open_validation.get("selected_store_code") or approval.get("selected_store_code"),
        "expected_merchant_account_id": open_validation.get("expected_merchant_account_id")
        or approval.get("expected_merchant_account_id"),
        "template_hash": approval.get("template_hash") or preflight.get("template_hash"),
        "blockers": sorted(set(blockers)),
        "unsafe_blockers": sorted(set(unsafe)),
        "exact_next_action": exact_next_action,
        "customer_send_performed": False,
        "customer_send_allowed_by_this_gate": False,
        "kaspi_chat_write_performed": False,
        "browser_action_performed": False,
        "google_board_write_allowed": False,
        "db_write_allowed": False,
        "telegram_send_allowed": False,
        "raw_order_id_exported": False,
        "raw_customer_text_exported": False,
        "raw_phone_exported": False,
        "raw_session_material_exported": False,
    }
    _write_json(output_dir / "manifest.json", manifest)
    _write_text(output_dir / "closeout.md", _closeout(manifest))
    return manifest


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    manifest = build_report(args)
    print(json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True))
    if str(manifest.get("gate") or "").startswith("RED_"):
        return 2
    return 0 if manifest.get("gate") == GREEN_GATE else 1


if __name__ == "__main__":
    raise SystemExit(main())
