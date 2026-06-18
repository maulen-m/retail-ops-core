#!/usr/bin/env python3
"""Build a unified no-write readiness packet for the Kaspi customer-size workflow."""
from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path
from typing import Any

from core.ops.customer_size_request import (
    build_customer_size_next_actions,
    export_customer_size_ledger_snapshot,
    sha256_file,
    summarize_customer_size_ledger,
)


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_LEDGER_DB = (
    REPO_ROOT
    / "runtime"
    / "customer_size_request_ledger"
    / "no_send_customer_size_request_ledger.sqlite"
)
DEFAULT_DB = REPO_ROOT / "db" / "app.db"
LIVE_UI_ACCEPTED_GATE = "GREEN_LIVE_UI_NO_SEND_CANARY_RESULT_ACCEPTED"
RESIDENT_BUTTON_GATE = "GREEN_KASPI_CUSTOMER_CHAT_MESSAGE_BUTTON_PROVEN_NO_SEND"
RESIDENT_HEARTBEAT_GREEN_GATE = "GREEN_KASPI_CUSTOMER_CHAT_RESIDENT_NO_SEND_CONTROLLER_READY"
OPEN_CHAT_PACKET_GREEN_GATE = "GREEN_OPEN_CHAT_NO_TYPE_CANARY_PACKET_READY_NO_SEND"
OPEN_CHAT_RESULT_ACCEPTED_GATE = "GREEN_OPEN_CHAT_NO_TYPE_CANARY_RESULT_ACCEPTED_NO_SEND"


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _safe_sha(path: Path) -> str | None:
    return sha256_file(path) if path.exists() else None


def _load_json(path: Path | None) -> dict[str, Any] | None:
    if not path or not path.exists():
        return None
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"Expected object JSON at {path}")
    return data


def _latest(pattern: str) -> Path | None:
    matches = [path for path in REPO_ROOT.glob(pattern) if path.is_file()]
    if not matches:
        return None
    return max(matches, key=lambda path: path.stat().st_mtime)


def _gate(data: dict[str, Any] | None) -> str:
    return str((data or {}).get("gate") or "MISSING")


def _green(data: dict[str, Any] | None) -> bool:
    return _gate(data).startswith("GREEN")


def _int(data: dict[str, Any] | None, key: str) -> int:
    try:
        return int((data or {}).get(key) or 0)
    except (TypeError, ValueError):
        return 0


def _default_output_dir() -> Path:
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return REPO_ROOT / "exports" / "validation" / f"kaspi_customer_size_workflow_readiness_{stamp}"


def _path_str(path: Path | None) -> str:
    return str(path) if path else ""


def _open_chat_approval_phrase_path(open_chat_packet_path: Path | None) -> Path | None:
    if not open_chat_packet_path:
        return None
    return open_chat_packet_path.resolve().parent / "REQUIRED_EXACT_OPEN_CHAT_NO_TYPE_APPROVAL_PHRASE.txt"


def build_stages(
    *,
    ledger_summary: dict[str, Any],
    resident_heartbeat: dict[str, Any] | None,
    live_ui_validation: dict[str, Any] | None,
    resident_button: dict[str, Any] | None,
    chrome_reconnect: dict[str, Any] | None,
    live_send_approval: dict[str, Any] | None,
    open_chat_no_type_packet: dict[str, Any] | None,
    open_chat_no_type_result: dict[str, Any] | None,
    live_send_execution_preflight: dict[str, Any] | None,
    after_live_send_watch: dict[str, Any] | None,
    reply_polling_preflight: dict[str, Any] | None,
    reply_observation: dict[str, Any] | None,
    google_board_patch: dict[str, Any] | None,
    google_board_apply: dict[str, Any] | None,
    after_board_apply_readiness: dict[str, Any] | None,
    cadence: dict[str, Any] | None,
    reply_commands_exists: bool,
) -> list[dict[str, Any]]:
    live_ui_green = _gate(live_ui_validation) == LIVE_UI_ACCEPTED_GATE
    resident_button_green = _gate(resident_button) == RESIDENT_BUTTON_GATE
    no_send_proof_green = live_ui_green or resident_button_green
    open_chat_gate = _gate(open_chat_no_type_packet)
    open_chat_result_gate = _gate(open_chat_no_type_result)
    open_chat_gate_required = bool(open_chat_no_type_packet)
    open_chat_allowed = (
        not open_chat_gate_required
        or open_chat_result_gate == OPEN_CHAT_RESULT_ACCEPTED_GATE
    )
    send_approval_green = _green(live_send_approval)
    patch_rows = _int(google_board_patch, "patch_rows_count")
    patch_blockers = _int(google_board_patch, "blockers_count")
    reply_ready_rows = _int(reply_observation, "classification_ready_rows")
    ledger_rows = int(ledger_summary.get("ledger_rows") or 0)
    pending_send = int(ledger_summary.get("pending_live_send_canary_count") or 0)
    board_ready = int(ledger_summary.get("google_board_size_fill_ready_count") or 0)

    return [
        {
            "sequence": 10,
            "stage": "missing_size_detection_and_local_ledger",
            "gate": "GREEN_LEDGER_HAS_ROWS" if ledger_rows else "YELLOW_LEDGER_EMPTY",
            "current_count": ledger_rows,
            "allowed_now": True,
            "external_write_allowed": False,
        },
        {
            "sequence": 20,
            "stage": "chrome_or_computer_use_access",
            "gate": _gate(chrome_reconnect),
            "current_count": 1 if chrome_reconnect else 0,
            "allowed_now": False,
            "external_write_allowed": False,
            "next_action": (
                "paste_exact_chrome_reconnect_approval_phrase"
                if _gate(chrome_reconnect) == "YELLOW_CHROME_RECONNECT_APPROVAL_REQUIRED_NO_UI_ACTION"
                else "use_manual_computer_use_visual_proof_or_rebuild_reconnect_packet"
            ),
        },
        {
            "sequence": 25,
            "stage": "resident_session_heartbeat",
            "gate": _gate(resident_heartbeat),
            "current_count": 1 if resident_heartbeat else 0,
            "allowed_now": _gate(resident_heartbeat) == RESIDENT_HEARTBEAT_GREEN_GATE,
            "external_write_allowed": False,
            "orders_search_input_visible": bool((resident_heartbeat or {}).get("orders_search_input_visible")),
            "browser_should_remain_open": bool((resident_heartbeat or {}).get("browser_should_remain_open")),
            "next_action": "preserve_resident_session_and_stop_if_heartbeat_not_green",
        },
        {
            "sequence": 30,
            "stage": "live_ui_no_send_proof",
            "gate": _gate(live_ui_validation) if live_ui_green else _gate(resident_button),
            "live_ui_gate": _gate(live_ui_validation),
            "resident_button_gate": _gate(resident_button),
            "current_count": pending_send,
            "allowed_now": no_send_proof_green,
            "external_write_allowed": False,
            "next_action": "prove_merchant_order_chat_button_without_typing_or_sending",
        },
        {
            "sequence": 40,
            "stage": "open_chat_no_type_side_effect_canary",
            "gate": open_chat_result_gate if open_chat_gate_required else "NOT_REQUIRED_NO_PACKET_PRESENT",
            "packet_gate": open_chat_gate,
            "current_count": 1 if open_chat_no_type_packet else 0,
            "allowed_now": open_chat_allowed,
            "external_write_allowed": False,
            "next_action": (
                "run_or_validate_exact_one_order_open_chat_no_type_canary_before_live_send"
                if open_chat_gate_required and not open_chat_allowed
                else "open_chat_no_type_canary_already_accepted_or_not_required"
            ),
        },
        {
            "sequence": 45,
            "stage": "single_order_live_send_canary_approval_packet",
            "gate": _gate(live_send_approval),
            "current_count": pending_send,
            "allowed_now": send_approval_green and open_chat_allowed,
            "external_write_allowed": False,
            "next_action": "generate_exact_owner_approval_after_no_send_green",
        },
        {
            "sequence": 48,
            "stage": "single_order_live_send_canary_execution_preflight",
            "gate": _gate(live_send_execution_preflight),
            "current_count": pending_send,
            "allowed_now": _green(live_send_execution_preflight) and open_chat_allowed,
            "external_write_allowed": False,
            "next_action": "supply_exact_owner_approval_phrase_then_execute_one_order_canary_only",
        },
        {
            "sequence": 50,
            "stage": "after_live_send_watch",
            "gate": _gate(after_live_send_watch),
            "current_count": 1 if after_live_send_watch else 0,
            "allowed_now": _green(after_live_send_watch),
            "external_write_allowed": False,
            "next_action": "after_ui_helper_writes_green_send_result_run_local_post_canary_watch",
        },
        {
            "sequence": 55,
            "stage": "reply_polling_preflight",
            "gate": _gate(reply_polling_preflight),
            "current_count": _int(reply_polling_preflight, "poll_target_count"),
            "allowed_now": _green(reply_polling_preflight),
            "external_write_allowed": False,
            "next_action": "poll_replies_only_after_a_request_sent_row_exists_and_owner_approval_matches",
        },
        {
            "sequence": 60,
            "stage": "reply_observation_and_size_classification",
            "gate": (
                _gate(reply_observation)
                if reply_observation
                else "READY_FOR_FUTURE_REPLY_OBSERVATION_NO_EXTERNAL_WRITE"
                if reply_commands_exists
                else "YELLOW_REPLY_OBSERVATION_COMMANDS_MISSING"
            ),
            "current_count": reply_ready_rows,
            "allowed_now": reply_commands_exists,
            "external_write_allowed": False,
            "next_action": "record_future_customer_replies_from_transient_csv_after_approved_send",
        },
        {
            "sequence": 65,
            "stage": "google_board_my_size_patch_packet",
            "gate": _gate(google_board_patch),
            "current_count": patch_rows,
            "allowed_now": patch_rows > 0 and patch_blockers == 0,
            "external_write_allowed": False,
            "board_ready_ledger_rows": board_ready,
            "next_action": "review_or_apply_existing_google_board_writeback_gate_after_owner_approval",
        },
        {
            "sequence": 70,
            "stage": "google_board_my_size_apply",
            "gate": _gate(google_board_apply),
            "current_count": _int(google_board_apply, "patch_rows_count"),
            "allowed_now": _gate(google_board_apply)
            in {
                "GREEN_GOOGLE_BOARD_MY_SIZE_PATCH_APPLIED_AND_READBACK_VERIFIED",
                "GREEN_GOOGLE_BOARD_MY_SIZE_PATCH_ALREADY_CURRENT_NO_WRITE",
            },
            "external_write_allowed": False,
            "next_action": "only_after_exact_owner_approval_apply_my_size_cells_then_verify_readback",
        },
        {
            "sequence": 75,
            "stage": "after_google_board_apply_closeout_resume_readiness",
            "gate": _gate(after_board_apply_readiness),
            "current_count": 1 if after_board_apply_readiness else 0,
            "allowed_now": _green(after_board_apply_readiness),
            "external_write_allowed": False,
            "next_action": "if_green_use_generated_exact_phrase_for_existing_closeout_resume",
        },
        {
            "sequence": 80,
            "stage": "cadence_scheduler_preflight",
            "gate": _gate(cadence),
            "current_count": _int(cadence, "cadence_slot_rows"),
            "allowed_now": _green(cadence),
            "external_write_allowed": False,
            "next_action": "install_or_enable_scheduler_only_after_separate_approval",
        },
        {
            "sequence": 90,
            "stage": "telegram_pdf_waybill_resume",
            "gate": "BLOCKED_UNTIL_NO_BLANK_MY_SIZE_AND_GOOGLE_BOARD_READY",
            "current_count": 0,
            "allowed_now": False,
            "external_write_allowed": False,
            "next_action": "resume_existing_waybill_workflow_after_sizing_gate_green",
        },
    ]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument("--ledger-db", type=Path, default=DEFAULT_LEDGER_DB)
    parser.add_argument("--resident-heartbeat-manifest", type=Path)
    parser.add_argument("--live-ui-validation-json", type=Path)
    parser.add_argument("--resident-button-manifest", type=Path)
    parser.add_argument("--chrome-reconnect-manifest", type=Path)
    parser.add_argument("--live-send-approval-manifest", type=Path)
    parser.add_argument("--open-chat-no-type-packet-manifest", type=Path)
    parser.add_argument("--open-chat-no-type-result-validation-json", type=Path)
    parser.add_argument("--live-send-execution-preflight-manifest", type=Path)
    parser.add_argument("--after-live-send-watch-manifest", type=Path)
    parser.add_argument("--reply-polling-preflight-manifest", type=Path)
    parser.add_argument("--reply-observation-manifest", type=Path)
    parser.add_argument("--google-board-patch-manifest", type=Path)
    parser.add_argument("--google-board-apply-manifest", type=Path)
    parser.add_argument("--after-board-apply-readiness-manifest", type=Path)
    parser.add_argument("--cadence-manifest", type=Path)
    parser.add_argument("--output-dir", type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    output_dir = args.output_dir or _default_output_dir()
    output_dir.mkdir(parents=True, exist_ok=True)
    db_path = args.db.resolve()
    ledger_path = args.ledger_db.resolve()
    db_sha_before = _safe_sha(db_path)
    ledger_sha_before = _safe_sha(ledger_path)

    resident_heartbeat_path = args.resident_heartbeat_manifest or _latest(
        "exports/validation/kaspi_customer_chat_resident_no_send_controller_current/resident_controller_heartbeat.json"
    )
    live_ui_path = args.live_ui_validation_json or _latest(
        "exports/validation/kaspi_customer_chat_live_canary_packet_*/live_ui_canary_result_validation*.json"
    )
    resident_button_path = args.resident_button_manifest or _latest(
        "exports/validation/kaspi_customer_chat_resident_no_send_controller_current/commands/*/ui_search_identity_no_send_*/manifest.json"
    )
    chrome_path = args.chrome_reconnect_manifest or _latest(
        "exports/validation/kaspi_customer_chat_chrome_reconnect_*/chrome_reconnect_preflight_manifest.json"
    )
    send_path = args.live_send_approval_manifest or _latest(
        "exports/validation/kaspi_customer_chat_live_send_canary_approval_*/manifest.json"
    )
    open_chat_packet_path = args.open_chat_no_type_packet_manifest or _latest(
        "exports/validation/kaspi_customer_chat_open_no_type_canary_*/manifest.json"
    )
    open_chat_result_path = args.open_chat_no_type_result_validation_json or _latest(
        "exports/validation/kaspi_customer_chat_open_no_type_result_validation_*/open_chat_no_type_result_validation.json"
    )
    send_execution_path = args.live_send_execution_preflight_manifest or _latest(
        "exports/validation/kaspi_customer_size_live_send_execution_preflight_*/manifest.json"
    )
    after_live_send_watch_path = args.after_live_send_watch_manifest or _latest(
        "exports/validation/kaspi_customer_size_after_live_send_watch_*/manifest.json"
    )
    reply_polling_preflight_path = args.reply_polling_preflight_manifest or _latest(
        "exports/validation/kaspi_reply_polling_execution_preflight_*/manifest.json"
    )
    reply_path = args.reply_observation_manifest or _latest(
        "exports/validation/kaspi_customer_size_reply_observations_*/manifest.json"
    )
    patch_path = args.google_board_patch_manifest or _latest(
        "exports/validation/kaspi_customer_size_google_board_patch_packet_*/manifest.json"
    )
    google_board_apply_path = args.google_board_apply_manifest or _latest(
        "exports/validation/kaspi_customer_size_google_board_my_size_apply_*/manifest.json"
    )
    after_board_apply_readiness_path = args.after_board_apply_readiness_manifest or _latest(
        "exports/validation/kaspi_customer_size_after_board_apply_readiness_*/manifest.json"
    )
    cadence_path = args.cadence_manifest or _latest(
        "exports/validation/kaspi_customer_size_cadence_readiness_*/manifest.json"
    )

    resident_heartbeat = _load_json(resident_heartbeat_path)
    live_ui = _load_json(live_ui_path)
    resident_button = _load_json(resident_button_path)
    chrome = _load_json(chrome_path)
    send = _load_json(send_path)
    open_chat_packet = _load_json(open_chat_packet_path)
    open_chat_result = _load_json(open_chat_result_path)
    send_execution = _load_json(send_execution_path)
    after_live_send_watch = _load_json(after_live_send_watch_path)
    reply_polling_preflight = _load_json(reply_polling_preflight_path)
    reply = _load_json(reply_path)
    patch = _load_json(patch_path)
    google_board_apply = _load_json(google_board_apply_path)
    after_board_apply_readiness = _load_json(after_board_apply_readiness_path)
    cadence = _load_json(cadence_path)
    ledger_snapshot = export_customer_size_ledger_snapshot(ledger_path)
    ledger_summary = summarize_customer_size_ledger(ledger_snapshot)
    next_actions = build_customer_size_next_actions(ledger_snapshot)
    reply_commands = (
        REPO_ROOT
        / "docs"
        / "agent_handoffs"
        / "KASPI_CUSTOMER_SIZE_LIVE_UI_NO_SEND_CANARY_EXECUTION_20260616"
        / "REPLY_OBSERVATION_COMMANDS.md"
    )
    stages = build_stages(
        ledger_summary=ledger_summary,
        resident_heartbeat=resident_heartbeat,
        live_ui_validation=live_ui,
        resident_button=resident_button,
        chrome_reconnect=chrome,
        live_send_approval=send,
        open_chat_no_type_packet=open_chat_packet,
        open_chat_no_type_result=open_chat_result,
        live_send_execution_preflight=send_execution,
        after_live_send_watch=after_live_send_watch,
        reply_polling_preflight=reply_polling_preflight,
        reply_observation=reply,
        google_board_patch=patch,
        google_board_apply=google_board_apply,
        after_board_apply_readiness=after_board_apply_readiness,
        cadence=cadence,
        reply_commands_exists=reply_commands.exists(),
    )
    live_ui_green = _gate(live_ui) == LIVE_UI_ACCEPTED_GATE
    resident_button_green = _gate(resident_button) == RESIDENT_BUTTON_GATE
    no_send_proof_green = live_ui_green or resident_button_green
    open_chat_gate_required = bool(open_chat_packet)
    open_chat_accepted = _gate(open_chat_result) == OPEN_CHAT_RESULT_ACCEPTED_GATE
    resident_heartbeat_gate = _gate(resident_heartbeat)
    resident_heartbeat_blocks_browser_action = (
        bool(resident_heartbeat)
        and resident_heartbeat_gate != RESIDENT_HEARTBEAT_GREEN_GATE
    )
    downstream_pending_stages = [
        {
            "sequence": row.get("sequence"),
            "stage": row.get("stage"),
            "gate": row.get("gate"),
            "next_action": row.get("next_action"),
        }
        for row in stages
        if int(row.get("sequence") or 0) >= 40 and not bool(row.get("allowed_now"))
    ]
    if resident_heartbeat_blocks_browser_action:
        critical_next_stage = "resident_session_heartbeat"
    elif (
        (not open_chat_gate_required or open_chat_accepted)
        and _green(send)
        and _green(send_execution)
        and not _green(after_live_send_watch)
    ):
        critical_next_stage = "execute_exact_one_order_ui_live_send_canary"
    else:
        critical_next_stage = downstream_pending_stages[0]["stage"] if downstream_pending_stages else "none"
    post_send_chain_complete = not downstream_pending_stages

    blockers = [
        {
            "stage": "live_ui_no_send_proof",
            "blocker": "live_ui_no_send_not_green",
            "live_ui_gate": _gate(live_ui),
            "resident_button_gate": _gate(resident_button),
        }
    ] if not no_send_proof_green else []
    if _gate(chrome) == "YELLOW_CHROME_RECONNECT_APPROVAL_REQUIRED_NO_UI_ACTION" and not no_send_proof_green:
        blockers.append(
            {
                "stage": "chrome_or_computer_use_access",
                "blocker": "chrome_reconnect_approval_required",
                "approval_phrase_file": _path_str(
                    (chrome_path or Path()).parent
                    / "REQUIRED_EXACT_CHROME_RECONNECT_APPROVAL_PHRASE.txt"
                    if chrome_path
                    else None
                ),
            }
        )
    elif chrome and not _green(chrome) and not no_send_proof_green:
        blockers.append(
            {
                "stage": "chrome_or_computer_use_access",
                "blocker": "chrome_or_computer_use_access_not_green",
                "gate": _gate(chrome),
            }
        )
    if not reply_commands.exists():
        blockers.append({"stage": "reply_observation_and_size_classification", "blocker": "reply_commands_missing"})
    if resident_heartbeat_blocks_browser_action:
        blockers.append(
            {
                "stage": "resident_session_heartbeat",
                "blocker": "resident_heartbeat_not_green",
                "gate": resident_heartbeat_gate,
                "orders_search_input_visible": bool(
                    (resident_heartbeat or {}).get("orders_search_input_visible")
                ),
                "safe_current_url": str((resident_heartbeat or {}).get("safe_current_url") or ""),
            }
        )
    if open_chat_gate_required and not open_chat_accepted:
        blockers.append(
            {
                "stage": "open_chat_no_type_side_effect_canary",
                "blocker": "open_chat_no_type_result_not_accepted",
                "packet_gate": _gate(open_chat_packet),
                "result_gate": _gate(open_chat_result),
                "approval_phrase_file": _path_str(
                    _open_chat_approval_phrase_path(open_chat_packet_path)
                ),
            }
        )

    gate = (
        "GREEN_CUSTOMER_SIZE_WORKFLOW_READY_FOR_OWNER_SEND_APPROVAL"
        if not blockers and _green(send)
        else "YELLOW_CUSTOMER_SIZE_WORKFLOW_READY_WITH_RETAINED_BLOCKERS_NO_EXTERNAL_WRITE"
    )
    manifest = {
        "gate": gate,
        "run_at": datetime.now().isoformat(timespec="seconds"),
        "db_path": str(db_path),
        "db_sha256_before": db_sha_before,
        "db_sha256_after": _safe_sha(db_path),
        "db_unchanged": db_sha_before == _safe_sha(db_path),
        "ledger_db_path": str(ledger_path),
        "ledger_sha256_before": ledger_sha_before,
        "ledger_sha256_after": _safe_sha(ledger_path),
        "source_manifests": {
            "resident_heartbeat_manifest": _path_str(resident_heartbeat_path),
            "live_ui_validation_json": _path_str(live_ui_path),
            "resident_button_manifest": _path_str(resident_button_path),
            "chrome_reconnect_manifest": _path_str(chrome_path),
            "live_send_approval_manifest": _path_str(send_path),
            "open_chat_no_type_packet_manifest": _path_str(open_chat_packet_path),
            "open_chat_no_type_result_validation_json": _path_str(open_chat_result_path),
            "live_send_execution_preflight_manifest": _path_str(send_execution_path),
            "after_live_send_watch_manifest": _path_str(after_live_send_watch_path),
            "reply_polling_preflight_manifest": _path_str(reply_polling_preflight_path),
            "reply_observation_manifest": _path_str(reply_path),
            "google_board_patch_manifest": _path_str(patch_path),
            "google_board_apply_manifest": _path_str(google_board_apply_path),
            "after_board_apply_readiness_manifest": _path_str(after_board_apply_readiness_path),
            "cadence_manifest": _path_str(cadence_path),
        },
        "ledger_summary": ledger_summary,
        "stage_count": len(stages),
        "blockers_count": len(blockers),
        "workflow_complete": False,
        "completion_scope": "ready_for_owner_send_approval_only",
        "post_send_chain_complete": post_send_chain_complete,
        "downstream_pending_stage_count": len(downstream_pending_stages),
        "critical_next_stage": critical_next_stage,
        "customer_send_allowed": False,
        "kaspi_chat_write_allowed": False,
        "google_board_write_allowed": False,
        "db_write_allowed": False,
        "telegram_send_allowed": False,
        "scheduler_change_allowed": False,
        "raw_order_id_exported": False,
        "raw_reply_text_exported": False,
    }
    _write_json(output_dir / "manifest.json", manifest)
    _write_json(output_dir / "workflow_stages.json", stages)
    _write_json(output_dir / "retained_blockers.json", blockers)
    _write_json(output_dir / "downstream_pending_stages.json", downstream_pending_stages)
    _write_json(output_dir / "next_actions_redacted.json", next_actions)
    closeout_lines = [
        "# Kaspi Customer Size Workflow Readiness",
        "",
        f"Gate: {gate}",
        "",
        f"- Output folder: {output_dir}",
        f"- Ledger rows: {ledger_summary.get('ledger_rows')}",
        f"- Pending live-send canary rows: {ledger_summary.get('pending_live_send_canary_count')}",
        f"- Board-ready size rows: {ledger_summary.get('google_board_size_fill_ready_count')}",
        f"- Blockers: {len(blockers)}",
        f"- Workflow complete: {manifest['workflow_complete']}",
        f"- Completion scope: {manifest['completion_scope']}",
        f"- Critical next stage: {critical_next_stage}",
        f"- Downstream pending stages: {len(downstream_pending_stages)}",
        "",
        "No customer messages, Kaspi UI/API writes, Google Board writes,",
        "production DB writes, Telegram/WhatsApp sends, workbook writes,",
        "scheduler changes, cookie/session inspection, or external writes happened.",
        "",
    ]
    if blockers:
        closeout_lines.extend(["## Retained Blockers", ""])
        closeout_lines.extend(f"- {row['stage']}: {row['blocker']}" for row in blockers)
        closeout_lines.append("")
    (output_dir / "closeout.md").write_text("\n".join(closeout_lines), encoding="utf-8")
    print(json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
