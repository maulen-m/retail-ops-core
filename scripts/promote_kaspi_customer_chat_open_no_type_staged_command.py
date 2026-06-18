#!/usr/bin/env python3
"""Promote a staged Kaspi open-chat/no-type command into the live resident queue.

Default behavior is dry-run only. A live queue write requires:

- exact owner approval text match;
- resident open-chat/no-type command preflight GREEN;
- resident heartbeat GREEN and orders search visible, or a preserved order-detail
  heartbeat backed by a GREEN selector-locked message-button proof for the same
  target;
- --apply plus ENABLE_KASPI_CUSTOMER_CHAT_OPEN_NO_TYPE_LIVE_ENQUEUE=1.

This script never opens the browser, never types, and never sends a customer
message. It only copies a prevalidated command JSON into the resident command
queue when all gates are green.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.run_kaspi_customer_chat_resident_no_send_controller import (
    COMMAND_ACTION_UI_OPEN_CHAT_NO_TYPE_CANARY,
    GREEN_GATE as RESIDENT_GREEN_GATE,
    OPEN_CHAT_PREFLIGHT_READY_GATE,
    _build_open_chat_no_type_preflight_result,
    normalize_command,
)


DEFAULT_STAGED_COMMAND = (
    REPO_ROOT
    / "exports"
    / "validation"
    / "kaspi_customer_chat_open_no_type_resident_command_staged_20260618_1815_no_live_enqueue"
    / "command_queue"
    / "staged_open_chat_no_type_acmewear_36170.json"
)
DEFAULT_LIVE_RUN_DIR = (
    REPO_ROOT / "exports" / "validation" / "kaspi_customer_chat_resident_no_send_controller_current"
)
DEFAULT_HEARTBEAT = DEFAULT_LIVE_RUN_DIR / "resident_controller_heartbeat.json"
DEFAULT_OUTPUT_DIR = (
    REPO_ROOT
    / "exports"
    / "validation"
    / f"kaspi_customer_chat_open_no_type_live_enqueue_preflight_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
)
ENV_GATE = "ENABLE_KASPI_CUSTOMER_CHAT_OPEN_NO_TYPE_LIVE_ENQUEUE"
GREEN_DRY_RUN_GATE = "GREEN_OPEN_CHAT_NO_TYPE_LIVE_ENQUEUE_PREFLIGHT_READY_DRY_RUN_NO_ACTION"
GREEN_APPLY_GATE = "GREEN_OPEN_CHAT_NO_TYPE_COMMAND_ENQUEUED_TO_RESIDENT_QUEUE_NO_SEND"
YELLOW_GATE = "YELLOW_OPEN_CHAT_NO_TYPE_LIVE_ENQUEUE_PREFLIGHT_BLOCKED_NO_ACTION"
RED_GATE = "RED_OPEN_CHAT_NO_TYPE_LIVE_ENQUEUE_UNSAFE_NO_ACTION"
ORDER_DETAIL_PROOF_GATE = "GREEN_KASPI_CUSTOMER_CHAT_MESSAGE_BUTTON_PROVEN_NO_SEND"
ORDER_DETAIL_PROOF_ACTION = "ui_chat_button_no_open"


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


def _safe_read_text(path: Path | None) -> str:
    if path is None:
        return ""
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8").strip()


def _relative_or_absolute(path_text: str, *, base_dir: Path) -> Path:
    path = Path(path_text)
    if path.is_absolute():
        return path
    return (base_dir / path).resolve()


def _is_order_detail_url(url: str) -> bool:
    text = str(url or "").lower()
    if "idmc.shop.kaspi.kz/login" in text or "/login" in text:
        return False
    return "/mc/#/orders/" in text or "/#/orders/" in text


def _target_set(value: Any) -> set[str]:
    return {part.strip() for part in str(value or "").split(",") if part.strip()}


def _last_button_proof_acceptance(
    *,
    heartbeat: dict[str, Any],
    command: dict[str, Any],
) -> tuple[bool, dict[str, Any], list[str]]:
    """Allow open-chat enqueue from an already-proven order-detail page.

    The normal green heartbeat means the orders search input is visible. After a
    successful no-open message-button proof, the preserved browser can be on the
    order detail page instead. This fallback is intentionally strict: it must
    point at a GREEN proof for the same row/order/store/merchant before the
    promoter treats the session as usable.
    """
    blockers: list[str] = []
    last_command = heartbeat.get("last_command") if isinstance(heartbeat.get("last_command"), dict) else {}
    proof_path_text = str(last_command.get("manifest_path") or "").strip()
    proof_path = Path(proof_path_text) if proof_path_text else Path()
    proof: dict[str, Any] = {}

    if not _is_order_detail_url(str(heartbeat.get("safe_current_url") or "")):
        blockers.append("resident_not_on_order_detail_url")
    if heartbeat.get("browser_should_remain_open") is not True:
        blockers.append("resident_heartbeat_does_not_preserve_browser")
    if last_command.get("action") != ORDER_DETAIL_PROOF_ACTION:
        blockers.append("resident_last_command_not_chat_button_no_open")
    if last_command.get("gate") != ORDER_DETAIL_PROOF_GATE:
        blockers.append(f"resident_last_command_gate_not_green:{last_command.get('gate') or 'MISSING'}")
    if not proof_path_text:
        blockers.append("resident_last_command_manifest_path_missing")
    elif not proof_path.exists() or not proof_path.is_file():
        blockers.append("resident_last_command_manifest_missing")
    else:
        proof = _read_json(proof_path)

    if proof:
        if proof.get("gate") != ORDER_DETAIL_PROOF_GATE:
            blockers.append(f"resident_last_command_manifest_gate_not_green:{proof.get('gate') or 'MISSING'}")
        if proof.get("chat_opened") is not False:
            blockers.append("resident_last_command_manifest_chat_opened_not_false")
        if proof.get("message_text_typed") is not False:
            blockers.append("resident_last_command_manifest_message_text_typed_not_false")
        if proof.get("message_sent") is not False:
            blockers.append("resident_last_command_manifest_message_sent_not_false")

        expected_rows = _target_set(command.get("target_db_row_ids"))
        expected_order_refs = _target_set(command.get("target_order_refs"))
        expected_store = str(command.get("profile_store_code") or command.get("stores") or "").strip().upper()
        expected_merchant = str(command.get("expected_merchant_account_id") or "").strip()
        matching_rows = []
        for row in proof.get("results") or []:
            row_id = str(row.get("db_row_id") or "").strip()
            order_ref = str(row.get("order_ref") or "").strip()
            store = str(row.get("store_code") or row.get("profile_store_code") or "").strip().upper()
            merchant = str(row.get("expected_merchant_account_id") or "").strip()
            if expected_rows and row_id not in expected_rows:
                continue
            if expected_order_refs and order_ref not in expected_order_refs:
                continue
            if expected_store and store != expected_store:
                continue
            if expected_merchant and merchant != expected_merchant:
                continue
            if row.get("chat_button_present") is not True:
                continue
            if row.get("merchant_account_match_proven") is not True:
                continue
            if row.get("result_or_detail_reached") is not True:
                continue
            matching_rows.append(row)
        if not matching_rows:
            blockers.append("resident_last_command_manifest_no_matching_button_proof")

    return not blockers, proof, blockers


def _resident_open_chat_runtime_blockers(
    *,
    live_run_dir: Path,
    process_lines: list[str] | None = None,
) -> list[str]:
    """Block current-run enqueue when the live resident lacks the enable flag."""
    if live_run_dir.resolve() != DEFAULT_LIVE_RUN_DIR.resolve():
        return []
    if process_lines is None:
        try:
            completed = subprocess.run(
                ["ps", "-axo", "command"],
                check=False,
                capture_output=True,
                text=True,
            )
        except OSError:
            return ["resident_controller_process_scan_failed"]
        process_lines = completed.stdout.splitlines()

    run_dir_text = str(live_run_dir.resolve())
    controller_lines = [
        line
        for line in process_lines
        if "run_kaspi_customer_chat_resident_no_send_controller.py" in line
        and run_dir_text in line
    ]
    if not controller_lines:
        return ["resident_controller_process_not_found_for_current_run_dir"]
    if not any("--enable-open-chat-no-type-canary" in line for line in controller_lines):
        return ["resident_controller_missing_enable_open_chat_no_type_canary_flag"]
    return []


def _render_closeout(report: dict[str, Any]) -> str:
    lines = [
        "# Kaspi Open-Chat No-Type Live Enqueue Preflight",
        "",
        f"Gate: {report['gate']}",
        "",
        "## Scope",
        "",
        "- Promote one staged resident command into the live resident command queue only after all guards pass.",
        "- This script performs no browser action, opens no chat, types nothing, and sends nothing.",
        "",
        "## Command",
        "",
        f"- Staged command: `{report.get('staged_command_path')}`",
        f"- Live command path: `{report.get('live_command_path') or ''}`",
        f"- Expected merchant account ID: `{report.get('expected_merchant_account_id')}`",
        f"- Target DB row: `{report.get('selected_db_row_id')}`",
        f"- Target order ref: `{report.get('selected_order_ref')}`",
        f"- Resident order-detail proof accepted: {str(report.get('resident_order_detail_proof_accepted')).lower()}",
        f"- Resident order-detail proof path: `{report.get('resident_order_detail_proof_path') or ''}`",
        "",
        "## Safety",
        "",
        f"- Apply requested: {str(report.get('apply_requested')).lower()}",
        f"- Env gate enabled: {str(report.get('env_gate_enabled')).lower()}",
        f"- Live enqueue performed: {str(report.get('live_enqueue_performed')).lower()}",
        "- Customer send allowed: false",
        "- Kaspi chat write allowed: false",
        "- Message text typed: false",
        "- Message sent: false",
        "- Raw order/customer/session material exported: false",
        "",
    ]
    blockers = [*(report.get("blockers") or []), *(report.get("unsafe_blockers") or [])]
    if blockers:
        lines.extend(["## Blockers", ""])
        lines.extend(f"- {blocker}" for blocker in blockers)
        lines.append("")
    return "\n".join(lines)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--staged-command", type=Path, default=DEFAULT_STAGED_COMMAND)
    parser.add_argument("--live-run-dir", type=Path, default=DEFAULT_LIVE_RUN_DIR)
    parser.add_argument("--heartbeat-json", type=Path, default=DEFAULT_HEARTBEAT)
    parser.add_argument("--approval-text-file", type=Path)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--apply", action="store_true")
    return parser


def run(args: argparse.Namespace, *, environ: dict[str, str] | None = None) -> dict[str, Any]:
    environ = dict(os.environ if environ is None else environ)
    output_dir = args.output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    staged_command_path = args.staged_command.resolve()
    live_run_dir = args.live_run_dir.resolve()
    live_commands_dir = live_run_dir / "command_queue"
    heartbeat_path = args.heartbeat_json.resolve()
    blockers: list[str] = []
    unsafe_blockers: list[str] = []

    command_payload: dict[str, Any] = {}
    if not staged_command_path.exists():
        blockers.append("staged_command_missing")
    else:
        command_payload = _read_json(staged_command_path)

    if command_payload:
        if command_payload.get("action") != COMMAND_ACTION_UI_OPEN_CHAT_NO_TYPE_CANARY:
            unsafe_blockers.append(f"unexpected_command_action:{command_payload.get('action')}")
        for key in [
            "customer_send_allowed",
            "kaspi_chat_write_allowed",
            "message_text_typed",
            "message_sent",
            "raw_order_id_exported",
            "raw_customer_text_exported",
            "raw_phone_exported",
            "raw_session_material_exported",
        ]:
            if command_payload.get(key) is not False:
                unsafe_blockers.append(f"command_{key}_not_false")
        if command_payload.get("chat_open_allowed") is not True:
            unsafe_blockers.append("command_chat_open_allowed_not_true")
        if not str(command_payload.get("expected_merchant_account_id") or "").strip():
            unsafe_blockers.append("expected_merchant_account_id_missing")

    command_for_preflight = dict(command_payload)
    if args.approval_text_file:
        command_for_preflight["open_chat_approval_text_file"] = str(args.approval_text_file.resolve())
    elif command_for_preflight.get("open_chat_approval_text_file"):
        command_for_preflight["open_chat_approval_text_file"] = str(
            _relative_or_absolute(
                str(command_for_preflight["open_chat_approval_text_file"]),
                base_dir=REPO_ROOT,
            )
        )
    if command_for_preflight.get("open_chat_packet_dir"):
        command_for_preflight["open_chat_packet_dir"] = str(
            _relative_or_absolute(str(command_for_preflight["open_chat_packet_dir"]), base_dir=REPO_ROOT)
        )

    normalized_command: dict[str, Any] = {}
    preflight: dict[str, Any] = {}
    if command_for_preflight and not unsafe_blockers:
        normalized_command = normalize_command(
            command_for_preflight,
            run_dir=live_run_dir,
            profile_store_code=str(command_for_preflight.get("profile_store_code") or "ACMEWEAR"),
        )
        preflight = _build_open_chat_no_type_preflight_result(
            command=normalized_command,
            enable_open_chat_no_type_canary=True,
        )
        _write_json(output_dir / "resident_open_chat_no_type_preflight.json", preflight)
        if preflight.get("gate") != OPEN_CHAT_PREFLIGHT_READY_GATE:
            blockers.append(f"resident_open_chat_no_type_preflight_not_green:{preflight.get('gate')}")
        unsafe_blockers.extend(str(value) for value in preflight.get("unsafe_blockers") or [])
        blockers.extend(str(value) for value in preflight.get("blockers") or [])

    heartbeat: dict[str, Any] = {}
    resident_order_detail_proof_accepted = False
    resident_order_detail_proof_blockers: list[str] = []
    resident_order_detail_proof_path = ""
    if not heartbeat_path.exists():
        blockers.append("resident_heartbeat_missing")
    else:
        heartbeat = _read_json(heartbeat_path)
        if heartbeat.get("gate") == RESIDENT_GREEN_GATE and heartbeat.get("orders_search_input_visible") is True:
            resident_order_detail_proof_accepted = False
        else:
            (
                resident_order_detail_proof_accepted,
                resident_order_detail_proof,
                resident_order_detail_proof_blockers,
            ) = _last_button_proof_acceptance(
                heartbeat=heartbeat,
                command=normalized_command or command_payload,
            )
            resident_order_detail_proof_path = str(
                (heartbeat.get("last_command") or {}).get("manifest_path") or ""
            )
            if not resident_order_detail_proof_accepted:
                blockers.append(f"resident_heartbeat_not_green:{heartbeat.get('gate')}")
                if heartbeat.get("orders_search_input_visible") is not True:
                    blockers.append("resident_orders_search_input_not_visible")
                blockers.extend(resident_order_detail_proof_blockers)
        if heartbeat.get("message_sent") is not False:
            unsafe_blockers.append("resident_heartbeat_message_sent_not_false")
        if heartbeat.get("message_text_typed") is not False:
            unsafe_blockers.append("resident_heartbeat_message_text_typed_not_false")

    blockers.extend(_resident_open_chat_runtime_blockers(live_run_dir=live_run_dir))

    apply_requested = bool(args.apply)
    env_gate_enabled = environ.get(ENV_GATE) == "1"
    if apply_requested and not env_gate_enabled:
        blockers.append(f"{ENV_GATE}_not_1")

    live_enqueue_performed = False
    live_command_path = ""
    if unsafe_blockers:
        gate = RED_GATE
    elif blockers:
        gate = YELLOW_GATE
    elif apply_requested:
        live_commands_dir.mkdir(parents=True, exist_ok=True)
        live_command_path = str((live_commands_dir / staged_command_path.name).resolve())
        command_to_write = dict(command_payload)
        command_to_write["open_chat_approval_text_file"] = normalized_command.get(
            "open_chat_approval_text_file",
            command_to_write.get("open_chat_approval_text_file", ""),
        )
        command_to_write["open_chat_packet_dir"] = normalized_command.get(
            "open_chat_packet_dir",
            command_to_write.get("open_chat_packet_dir", ""),
        )
        _write_json(Path(live_command_path), command_to_write)
        live_enqueue_performed = True
        gate = GREEN_APPLY_GATE
    else:
        gate = GREEN_DRY_RUN_GATE

    report = {
        "gate": gate,
        "recorded_at": datetime.now().isoformat(timespec="seconds"),
        "staged_command_path": str(staged_command_path),
        "live_run_dir": str(live_run_dir),
        "live_commands_dir": str(live_commands_dir),
        "live_command_path": live_command_path,
        "heartbeat_path": str(heartbeat_path),
        "resident_heartbeat_gate": heartbeat.get("gate", ""),
        "resident_orders_search_input_visible": heartbeat.get("orders_search_input_visible"),
        "resident_order_detail_proof_accepted": resident_order_detail_proof_accepted,
        "resident_order_detail_proof_path": resident_order_detail_proof_path,
        "resident_order_detail_proof_blockers": sorted(set(resident_order_detail_proof_blockers)),
        "resident_open_chat_no_type_preflight_gate": preflight.get("gate", ""),
        "approval_text_file": str(args.approval_text_file.resolve()) if args.approval_text_file else str(
            normalized_command.get("open_chat_approval_text_file", "")
        ),
        "approval_text_supplied": bool(
            _safe_read_text(args.approval_text_file)
            if args.approval_text_file
            else _safe_read_text(Path(str(normalized_command.get("open_chat_approval_text_file", ""))))
            if normalized_command.get("open_chat_approval_text_file")
            else ""
        ),
        "expected_merchant_account_id": normalized_command.get("expected_merchant_account_id", ""),
        "selected_db_row_id": normalized_command.get("target_db_row_ids", ""),
        "selected_order_ref": normalized_command.get("target_order_refs", ""),
        "apply_requested": apply_requested,
        "env_gate_name": ENV_GATE,
        "env_gate_enabled": env_gate_enabled,
        "live_enqueue_performed": live_enqueue_performed,
        "browser_action_performed": False,
        "chat_opened": False,
        "customer_send_performed": False,
        "kaspi_chat_write_performed": False,
        "message_text_typed": False,
        "message_sent": False,
        "raw_order_id_exported": False,
        "raw_customer_text_exported": False,
        "raw_phone_exported": False,
        "raw_session_material_exported": False,
        "blockers": sorted(set(blockers)),
        "unsafe_blockers": sorted(set(unsafe_blockers)),
    }
    _write_json(output_dir / "manifest.json", report)
    (output_dir / "closeout.md").write_text(_render_closeout(report), encoding="utf-8")
    return report


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    report = run(args)
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    if str(report.get("gate") or "").startswith("RED_"):
        return 2
    if args.apply and report.get("gate") != GREEN_APPLY_GATE:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
