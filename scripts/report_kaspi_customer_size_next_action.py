#!/usr/bin/env python3
"""Report the exact next safe action for the Kaspi customer-size workflow."""
from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
LIVE_UI_ACCEPTED_GATE = "GREEN_LIVE_UI_NO_SEND_CANARY_RESULT_ACCEPTED"
RESIDENT_BUTTON_GATE = "GREEN_KASPI_CUSTOMER_CHAT_MESSAGE_BUTTON_PROVEN_NO_SEND"
LIVE_SEND_APPROVAL_GREEN_GATE = "GREEN_LIVE_SEND_CANARY_APPROVAL_PACKET_READY_NO_SEND"
GOOGLE_BOARD_APPLY_GREEN_GATE = "GREEN_GOOGLE_BOARD_MY_SIZE_APPLY_HANDOFF_READY_NO_WRITE"
RESIDENT_RESUME_PACKET_GREEN_GATE = "GREEN_KASPI_CUSTOMER_SIZE_RESIDENT_RESUME_PACKET_READY_NO_BROWSER_TOUCH"
PRIORITY_ENQUEUE_DRY_RUN_GREEN_GATE = "GREEN_RESIDENT_READY_PRIORITY_COMMAND_NOT_ENQUEUED_DRY_RUN"
PRIORITY_ENQUEUE_ENQUEUED_GREEN_GATE = "GREEN_PRIORITY_COMMAND_ENQUEUED_TO_RESIDENT_NO_SEND"
RESIDENT_PROOF_FOLLOWUP_GREEN_GATE = "GREEN_RESIDENT_PROOF_FOLLOWUP_APPROVAL_READY_NO_SEND"
OPEN_CHAT_PACKET_GREEN_GATE = "GREEN_OPEN_CHAT_NO_TYPE_CANARY_PACKET_READY_NO_SEND"
OPEN_CHAT_RESULT_ACCEPTED_GATE = "GREEN_OPEN_CHAT_NO_TYPE_CANARY_RESULT_ACCEPTED_NO_SEND"
RESIDENT_HEARTBEAT_GREEN_GATE = "GREEN_KASPI_CUSTOMER_CHAT_RESIDENT_NO_SEND_CONTROLLER_READY"
HANDOFF_ROOT = (
    REPO_ROOT
    / "docs"
    / "agent_handoffs"
    / "KASPI_CUSTOMER_SIZE_LIVE_UI_NO_SEND_CANARY_EXECUTION_20260616"
)
MERCHANT_SELECTOR_MAP = {
    "UNIVERSAL": "30000001",
    "ACMEWEAR": "30137883",
    "STOREB": "30000002",
    "MELVIS": "30362323",
    "11KZ": "30290083",
}


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _read_json(path: Path | None) -> dict[str, Any] | None:
    if not path or not path.exists():
        return None
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"Expected object JSON at {path}")
    return payload


def _latest(pattern: str) -> Path | None:
    matches = [path for path in REPO_ROOT.glob(pattern) if path.is_file()]
    if not matches:
        return None
    return max(matches, key=lambda path: path.stat().st_mtime)


def _gate(payload: dict[str, Any] | None) -> str:
    return str((payload or {}).get("gate") or "MISSING")


def _path_string(path: Path | None) -> str:
    return str(path.resolve()) if path else ""


def _default_output_dir() -> Path:
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return REPO_ROOT / "exports" / "validation" / f"kaspi_customer_size_next_action_{stamp}"


def _build_after_green_command(packet_dir: Path, resident_button_manifest: Path | None = None) -> str:
    if resident_button_manifest:
        return (
            "cd ~/Docs/Autonomous_business && "
            "PYTHONPATH=. .venv/bin/python "
            "scripts/build_kaspi_customer_chat_live_send_canary_approval_packet.py "
            f"--resident-button-manifest {resident_button_manifest} "
            "--output-dir exports/validation/kaspi_customer_chat_live_send_canary_approval_AFTER_RESIDENT_GREEN_NO_SEND"
        )
    return (
        "cd ~/Docs/Autonomous_business && "
        "PYTHONPATH=. .venv/bin/python scripts/run_kaspi_customer_size_no_send_green_followup.py "
        f"--packet-dir {packet_dir} "
        "--db db/app.db "
        "--ledger-db runtime/customer_size_request_ledger/no_send_customer_size_request_ledger.sqlite "
        "--output-root exports/validation/kaspi_customer_size_no_send_green_followup_AFTER_GREEN_NO_SEND"
    )


def _approval_phrase_path(live_send_path: Path | None) -> Path | None:
    if not live_send_path:
        return None
    return live_send_path.resolve().parent / "REQUIRED_EXACT_LIVE_SEND_CANARY_APPROVAL_PHRASE.txt"


def _execution_handoff_path(live_send_path: Path | None) -> Path | None:
    if not live_send_path:
        return None
    return (
        live_send_path.resolve().parent
        / "live_send_execution_handoff"
        / "KASPI_CUSTOMER_SIZE_LIVE_SEND_CANARY_EXECUTION_HANDOFF.md"
    )


def _execution_starter_prompt_path(live_send_path: Path | None) -> Path | None:
    if not live_send_path:
        return None
    return live_send_path.resolve().parent / "live_send_execution_handoff" / "ONE_SENTENCE_STARTER_PROMPT.txt"


def _open_chat_approval_phrase_path(open_chat_packet_path: Path | None) -> Path | None:
    if not open_chat_packet_path:
        return None
    return open_chat_packet_path.resolve().parent / "REQUIRED_EXACT_OPEN_CHAT_NO_TYPE_APPROVAL_PHRASE.txt"


def _manifest_path_from_dir(path_text: str) -> Path | None:
    path_text = str(path_text or "").strip()
    if not path_text:
        return None
    return Path(path_text).resolve() / "manifest.json"


def _priority_store(resident_resume: dict[str, Any] | None, enqueue: dict[str, Any] | None) -> str:
    command = (resident_resume or {}).get("priority_command")
    if isinstance(command, dict):
        store = str(command.get("profile_store_code") or command.get("stores") or "").strip().upper()
        if store:
            return store
    return str(
        (enqueue or {}).get("command_profile_store_code")
        or (enqueue or {}).get("command_stores")
        or ""
    ).strip().upper()


def _resident_heartbeat_next_action(
    *,
    resident_heartbeat: dict[str, Any] | None,
    resident_resume: dict[str, Any] | None,
) -> str:
    safe_url = str((resident_heartbeat or {}).get("safe_current_url") or "").strip()
    resume_script = _script_path(resident_resume, "enqueue_script_path")
    prefix = (
        "Complete Kaspi login/SMS once in the already-open resident browser, keep that browser open, "
        "verify the orders search input is visible, and verify the visible merchant selector matches the target store"
    )
    if safe_url:
        prefix += f" (current safe URL: {safe_url})"
    if resume_script:
        return f"{prefix}; then rerun the guarded priority enqueue script `{resume_script}`. Do not start a second browser, open chat, type, or send."
    return f"{prefix}. Do not start a second browser, open chat, type, or send."


def _expected_selector_id(store_code: str) -> str:
    return MERCHANT_SELECTOR_MAP.get(str(store_code or "").strip().upper(), "")


def _script_path(manifest: dict[str, Any] | None, key: str) -> str:
    return str((manifest or {}).get(key) or "")


def _resident_priority_next_action(
    *,
    resident_resume: dict[str, Any] | None,
    priority_enqueue: dict[str, Any] | None,
    enqueue_gate: str,
) -> str:
    enqueue = priority_enqueue or {}
    blockers = set(str(blocker) for blocker in (enqueue.get("blockers") or []))
    if (
        int(enqueue.get("resident_process_count") or 0) > 0
        and (
            "resident_heartbeat_gate_not_green" in blockers
            or "resident_orders_search_input_not_visible" in blockers
        )
    ):
        return (
            "Complete Kaspi login/SMS once in the already-open resident browser, leave the controller/browser "
            "running, then rerun the guarded priority enqueue script; do not start a second browser or close this session."
        )
    if enqueue_gate == PRIORITY_ENQUEUE_ENQUEUED_GREEN_GATE:
        script = _script_path(resident_resume, "proof_followup_script_path")
        return (
            f"Run the resident proof watcher `{script}` to wait for the current priority no-send proof "
            "and build the approval packet; do not send or open chat."
        )
    if enqueue_gate == PRIORITY_ENQUEUE_DRY_RUN_GREEN_GATE:
        script = _script_path(resident_resume, "enqueue_script_path")
        return (
            f"Run the guarded priority enqueue script `{script}`; it must fail closed unless the live "
            "resident session is fresh, GREEN, and on the matching store."
        )
    script = _script_path(resident_resume, "start_script_path")
    return (
        f"Start or restore the resident controller with `{script}`, preserve the browser session, "
        "then rerun guarded enqueue; do not close/relogin unless owner explicitly approves."
    )


def _resident_priority_command(
    *,
    resident_resume: dict[str, Any] | None,
    priority_enqueue: dict[str, Any] | None,
    enqueue_gate: str,
) -> str:
    enqueue = priority_enqueue or {}
    blockers = set(str(blocker) for blocker in (enqueue.get("blockers") or []))
    if (
        int(enqueue.get("resident_process_count") or 0) > 0
        and (
            "resident_heartbeat_gate_not_green" in blockers
            or "resident_orders_search_input_not_visible" in blockers
        )
    ):
        return _script_path(resident_resume, "enqueue_script_path")
    if enqueue_gate == PRIORITY_ENQUEUE_ENQUEUED_GREEN_GATE:
        return _script_path(resident_resume, "proof_followup_script_path")
    if enqueue_gate == PRIORITY_ENQUEUE_DRY_RUN_GREEN_GATE:
        return _script_path(resident_resume, "enqueue_script_path")
    return _script_path(resident_resume, "start_script_path")


def _current_approval_review_command(live_send_path: Path | None) -> str:
    phrase_path = _approval_phrase_path(live_send_path)
    if phrase_path and phrase_path.exists():
        return f"cat {phrase_path}"
    return ""


def _select_helper_prompt(runtime_control_probe: str) -> Path:
    probe = str(runtime_control_probe or "").lower()
    if "login" in probe or "session" in probe or "storage_state" in probe:
        return HANDOFF_ROOT / "AGENT_0_SESSION_REFRESH_THEN_NO_SEND_PROOF_20260616.md"
    return HANDOFF_ROOT / "AGENT_1_LIVE_UI_NO_SEND_CANARY_CURRENT_REFRESH_20260616.md"


def _exact_live_ui_next_action(runtime_control_probe: str) -> str:
    probe = str(runtime_control_probe or "").lower()
    if "order_search" in probe or "no_visible_row" in probe or "search_no_result" in probe:
        return (
            "Run a redacted no-send UI-search identity diagnostic across current candidate rows/status buckets; "
            "prove a visible order row first, then prove the customer-message button without opening chat, typing, or sending."
        )
    if "login" in probe or "session" in probe or "storage_state" in probe or "persistent_profile" in probe:
        return (
            "Run the Agent 0 headed persistent-profile Kaspi session refresh; "
            "the owner completes login/SMS in that browser, then rerun the "
            "no-send proof without opening chat, typing, or sending."
        )
    return (
        "Use a helper runtime with real Computer Use or repaired logged-in Chrome control "
        "to prove the selected Kaspi order customer-message button without typing or sending."
    )


def _build_closeout(manifest: dict[str, Any]) -> str:
    lines = [
        "# Kaspi Customer Size Current Next Action",
        "",
        f"Gate: {manifest['gate']}",
        "",
        "## Current Stopline",
        "",
        f"- Critical stage: `{manifest['critical_stage']}`",
        f"- Exact next action: {manifest['exact_next_action']}",
        f"- Runtime control probe: `{manifest.get('runtime_control_probe') or 'not_recorded'}`",
        "",
        "## Evidence",
        "",
        f"- Live UI validation: `{manifest['source_paths']['live_ui_validation_json']}`",
        f"- Resident selector/button proof: `{manifest['source_paths']['resident_button_manifest']}`",
        f"- Chrome reconnect manifest: `{manifest['source_paths']['chrome_reconnect_manifest']}`",
        f"- Live-send approval manifest: `{manifest['source_paths']['live_send_approval_manifest']}`",
        f"- Reply-polling handoff manifest: `{manifest['source_paths']['reply_polling_manifest']}`",
        f"- Google Board apply handoff manifest: `{manifest['source_paths']['google_board_apply_manifest']}`",
        f"- Resident resume manifest: `{manifest['source_paths']['resident_resume_manifest']}`",
        f"- Priority enqueue readiness manifest: `{manifest['source_paths']['priority_enqueue_readiness_manifest']}`",
        f"- Resident proof follow-up manifest: `{manifest['source_paths']['resident_proof_followup_manifest']}`",
        f"- Open-chat/no-type packet manifest: `{manifest['source_paths']['open_chat_no_type_packet_manifest']}`",
        f"- Open-chat/no-type result validation: `{manifest['source_paths']['open_chat_no_type_result_validation_json']}`",
        "",
        "## Merchant Selector Hard Gate",
        "",
        f"- Current priority store: `{manifest.get('current_priority_store') or ''}`",
        f"- Required visible merchant selector ID: `{manifest.get('current_priority_expected_merchant_account_id') or ''}`",
        "- Full selector map:",
        "",
    ]
    lines.extend(
        f"  - `{store} -> ID - {selector}`"
        for store, selector in (manifest.get("merchant_selector_map") or {}).items()
    )
    lines.extend(
        [
        "",
        "## Helper",
        "",
        f"- Resident start script: `{manifest['resident_resume_scripts']['start']}`",
        f"- Guarded priority enqueue script: `{manifest['resident_resume_scripts']['guarded_enqueue']}`",
        f"- Resident proof watcher script: `{manifest['resident_resume_scripts']['watch_proof_and_build_approval']}`",
        f"- No-send helper prompt: `{manifest['helper_prompt_path']}`",
        f"- After-GREEN follow-up command: `{manifest['after_green_followup_command']}`",
        f"- Live-send approval phrase: `{manifest['live_send_approval_phrase_path']}`",
        f"- Live-send execution handoff: `{manifest['live_send_execution_handoff_path']}`",
        f"- Live-send execution starter prompt: `{manifest['live_send_execution_starter_prompt_path']}`",
        f"- Open-chat/no-type approval phrase: `{manifest['open_chat_no_type_approval_phrase_path']}`",
        "",
        "## Parallel Safe Item",
        "",
        f"- Google Board apply approval phrase: `{manifest['google_board_apply_approval_phrase_path']}`",
        f"- Google Board apply rows ready: `{manifest['google_board_apply_rows_ready']}`",
        "",
        "## Safety",
        "",
        "- Customer send allowed now: false",
        "- Kaspi chat write allowed now: false",
        "- Google Board write allowed now: false",
        "- Production DB write allowed now: false",
        "- Telegram/WhatsApp send allowed now: false",
        "- Raw order IDs exported: false",
        "- Raw reply text exported: false",
        "",
        ]
    )
    blockers = manifest.get("blockers") or []
    if blockers:
        lines.extend(["## Blockers", ""])
        lines.extend(f"- {blocker}" for blocker in blockers)
        lines.append("")
    return "\n".join(lines)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--resident-heartbeat-manifest", type=Path)
    parser.add_argument("--live-ui-validation-json", type=Path)
    parser.add_argument("--resident-button-manifest", type=Path)
    parser.add_argument("--chrome-reconnect-manifest", type=Path)
    parser.add_argument("--live-send-approval-manifest", type=Path)
    parser.add_argument("--reply-polling-manifest", type=Path)
    parser.add_argument("--google-board-apply-manifest", type=Path)
    parser.add_argument("--resident-resume-manifest", type=Path)
    parser.add_argument("--resident-priority-enqueue-readiness-manifest", type=Path)
    parser.add_argument("--resident-proof-followup-manifest", type=Path)
    parser.add_argument("--open-chat-no-type-packet-manifest", type=Path)
    parser.add_argument("--open-chat-no-type-result-validation-json", type=Path)
    parser.add_argument("--runtime-control-probe", default="")
    parser.add_argument("--output-dir", type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    output_dir = args.output_dir or _default_output_dir()
    output_dir.mkdir(parents=True, exist_ok=True)

    live_ui_path = args.live_ui_validation_json or _latest(
        "exports/validation/kaspi_customer_chat_live_canary_packet_*/live_ui_canary_result_validation.json"
    )
    resident_button_path = args.resident_button_manifest or _latest(
        "exports/validation/kaspi_customer_chat_resident_no_send_controller_current/commands/*/ui_search_identity_no_send_*/manifest.json"
    )
    chrome_path = args.chrome_reconnect_manifest or _latest(
        "exports/validation/kaspi_customer_chat_chrome_reconnect*/chrome_reconnect_preflight_manifest.json"
    )
    live_send_path = args.live_send_approval_manifest or _latest(
        "exports/validation/kaspi_customer_chat_live_send_canary_approval_*/manifest.json"
    )
    reply_polling_path = args.reply_polling_manifest or _latest(
        "exports/validation/kaspi_customer_size_reply_polling_handoff_*/manifest.json"
    )
    board_apply_path = args.google_board_apply_manifest or _latest(
        "exports/validation/kaspi_customer_size_google_board_apply_handoff_*/manifest.json"
    )
    resident_resume_path = args.resident_resume_manifest or _latest(
        "exports/validation/kaspi_customer_size_resident_resume_packet_*/manifest.json"
    )
    priority_enqueue_path = args.resident_priority_enqueue_readiness_manifest or _latest(
        "exports/validation/kaspi_customer_size_priority_enqueue_readiness_*/manifest.json"
    )
    resident_proof_followup_path = args.resident_proof_followup_manifest or _latest(
        "exports/validation/kaspi_customer_size_resident_proof_followup_*/manifest.json"
    )
    open_chat_packet_path = args.open_chat_no_type_packet_manifest or _latest(
        "exports/validation/kaspi_customer_chat_open_no_type_canary_*/manifest.json"
    )
    open_chat_result_path = args.open_chat_no_type_result_validation_json or _latest(
        "exports/validation/kaspi_customer_chat_open_no_type_result_validation_*/open_chat_no_type_result_validation.json"
    )
    resident_heartbeat_path = args.resident_heartbeat_manifest

    resident_heartbeat = _read_json(resident_heartbeat_path)
    live_ui = _read_json(live_ui_path)
    resident_button = _read_json(resident_button_path)
    chrome = _read_json(chrome_path)
    live_send = _read_json(live_send_path)
    reply_polling = _read_json(reply_polling_path)
    board_apply = _read_json(board_apply_path)
    resident_resume = _read_json(resident_resume_path)
    priority_enqueue = _read_json(priority_enqueue_path)
    resident_proof_followup = _read_json(resident_proof_followup_path)
    open_chat_packet = _read_json(open_chat_packet_path)
    open_chat_result = _read_json(open_chat_result_path)

    followup_gate = _gate(resident_proof_followup)
    followup_approval_manifest = _manifest_path_from_dir(
        str((resident_proof_followup or {}).get("approval_dir") or "")
    )
    if followup_gate == RESIDENT_PROOF_FOLLOWUP_GREEN_GATE and followup_approval_manifest and followup_approval_manifest.exists():
        live_send_path = followup_approval_manifest
        live_send = _read_json(live_send_path)

    packet_dir = (
        live_ui_path.parent
        if live_ui_path
        else REPO_ROOT
        / "exports"
        / "validation"
        / "kaspi_customer_chat_live_canary_packet_2026-06-16_20260616_125511_final"
    )
    helper_prompt = _select_helper_prompt(args.runtime_control_probe)

    live_ui_gate = _gate(live_ui)
    resident_button_gate = _gate(resident_button)
    live_send_gate = _gate(live_send)
    board_apply_gate = _gate(board_apply)
    resident_resume_gate = _gate(resident_resume)
    priority_enqueue_gate = _gate(priority_enqueue)
    open_chat_packet_gate = _gate(open_chat_packet)
    open_chat_result_gate = _gate(open_chat_result)
    resident_heartbeat_gate = _gate(resident_heartbeat)
    resident_heartbeat_safe_url = str((resident_heartbeat or {}).get("safe_current_url") or "")
    resident_heartbeat_on_login = "idmc.shop.kaspi.kz/login" in resident_heartbeat_safe_url
    resident_heartbeat_blocks_browser_action = (
        bool(resident_heartbeat)
        and resident_heartbeat_gate != RESIDENT_HEARTBEAT_GREEN_GATE
        and (
            resident_heartbeat_on_login
            or resident_button_gate != RESIDENT_BUTTON_GATE
        )
    )
    priority_store = _priority_store(resident_resume, priority_enqueue)
    expected_selector_id = _expected_selector_id(priority_store)
    current_priority_pending = (
        resident_resume_gate == RESIDENT_RESUME_PACKET_GREEN_GATE
        and followup_gate != RESIDENT_PROOF_FOLLOWUP_GREEN_GATE
        and resident_button_gate != RESIDENT_BUTTON_GATE
    )
    no_send_proof_green = (
        not current_priority_pending
        and (
            followup_gate == RESIDENT_PROOF_FOLLOWUP_GREEN_GATE
            or live_ui_gate == LIVE_UI_ACCEPTED_GATE
            or resident_button_gate == RESIDENT_BUTTON_GATE
        )
    )
    blockers: list[str] = []

    if resident_heartbeat_blocks_browser_action:
        gate = "YELLOW_CUSTOMER_SIZE_NEXT_ACTION_RESIDENT_SESSION_REQUIRED_NO_EXTERNAL_WRITE"
        critical_stage = "resident_session_heartbeat"
        exact_next_action = _resident_heartbeat_next_action(
            resident_heartbeat=resident_heartbeat,
            resident_resume=resident_resume,
        )
        blockers.append(f"resident_heartbeat_gate={resident_heartbeat_gate}")
        blockers.append(
            f"resident_orders_search_input_visible={bool((resident_heartbeat or {}).get('orders_search_input_visible'))}"
        )
        safe_url = str((resident_heartbeat or {}).get("safe_current_url") or "")
        if safe_url:
            blockers.append(f"resident_safe_current_url={safe_url}")
        if priority_store:
            blockers.append(f"required_merchant_selector={priority_store}->ID-{expected_selector_id}")
    elif current_priority_pending:
        gate = "YELLOW_CUSTOMER_SIZE_NEXT_ACTION_RESIDENT_PRIORITY_PROOF_REQUIRED_NO_EXTERNAL_WRITE"
        critical_stage = "resident_priority_no_send_proof"
        exact_next_action = _resident_priority_next_action(
            resident_resume=resident_resume,
            priority_enqueue=priority_enqueue,
            enqueue_gate=priority_enqueue_gate,
        )
        blockers.append(f"resident_proof_followup_gate={followup_gate}")
        blockers.append(f"priority_enqueue_gate={priority_enqueue_gate}")
        blockers.extend(
            f"priority_enqueue_blocker={blocker}" for blocker in (priority_enqueue or {}).get("blockers", [])
        )
        if priority_store:
            blockers.append(f"required_merchant_selector={priority_store}->ID-{expected_selector_id}")
    elif not no_send_proof_green:
        gate = "YELLOW_CUSTOMER_SIZE_NEXT_ACTION_UI_PROOF_REQUIRED_NO_EXTERNAL_WRITE"
        critical_stage = "live_ui_no_send_proof"
        exact_next_action = _exact_live_ui_next_action(args.runtime_control_probe)
        blockers.append(f"live_ui_gate={live_ui_gate}")
        blockers.append(f"resident_button_gate={resident_button_gate}")
        if _gate(chrome) != "GREEN_LIVE_UI_NO_SEND_ALREADY_ACCEPTED_NO_RECONNECT_NEEDED":
            blockers.append(f"chrome_or_computer_use_gate={_gate(chrome)}")
        if args.runtime_control_probe:
            blockers.append(f"runtime_control_probe={args.runtime_control_probe}")
    elif open_chat_packet and open_chat_result_gate != OPEN_CHAT_RESULT_ACCEPTED_GATE:
        gate = "YELLOW_CUSTOMER_SIZE_NEXT_ACTION_OPEN_CHAT_NO_TYPE_REQUIRED_NO_EXTERNAL_WRITE"
        critical_stage = "open_chat_no_type_side_effect_canary"
        exact_next_action = (
            "Run or validate the exact one-order open-chat/no-type canary first; "
            "open only the selected order chat, type nothing, send nothing, and keep the resident session open."
        )
        blockers.append(f"open_chat_no_type_packet_gate={open_chat_packet_gate}")
        blockers.append(f"open_chat_no_type_result_gate={open_chat_result_gate}")
        for blocker in (open_chat_result or {}).get("blockers", []):
            blockers.append(f"open_chat_no_type_result_blocker={blocker}")
    elif live_send_gate != LIVE_SEND_APPROVAL_GREEN_GATE:
        gate = "YELLOW_CUSTOMER_SIZE_NEXT_ACTION_BUILD_SEND_APPROVAL_NO_EXTERNAL_WRITE"
        critical_stage = "single_order_live_send_canary_approval_packet"
        exact_next_action = "Run the no-send GREEN follow-up command to build the exact one-order live-send approval packet."
        blockers.append(f"live_send_approval_gate={live_send_gate}")
    else:
        gate = "GREEN_CUSTOMER_SIZE_NEXT_ACTION_READY_FOR_OWNER_SEND_APPROVAL_NO_WRITE"
        critical_stage = "owner_live_send_canary_approval"
        exact_next_action = "Owner may review the exact one-order live-send approval phrase; no send is authorized by this report."

    board_rows = int((board_apply or {}).get("patch_rows_count") or 0)
    board_approval_path = str((board_apply or {}).get("approval_phrase_path") or "")
    board_ready = board_apply_gate == GOOGLE_BOARD_APPLY_GREEN_GATE and board_rows > 0
    live_send_approval_phrase_path = _approval_phrase_path(live_send_path)
    live_send_execution_handoff_path = _execution_handoff_path(live_send_path)
    live_send_execution_starter_prompt_path = _execution_starter_prompt_path(live_send_path)
    if resident_heartbeat_blocks_browser_action:
        after_green_followup_command = _script_path(resident_resume, "enqueue_script_path")
    elif current_priority_pending:
        after_green_followup_command = _resident_priority_command(
            resident_resume=resident_resume,
            priority_enqueue=priority_enqueue,
            enqueue_gate=priority_enqueue_gate,
        )
    elif open_chat_packet and open_chat_result_gate != OPEN_CHAT_RESULT_ACCEPTED_GATE:
        approval_path = _open_chat_approval_phrase_path(open_chat_packet_path)
        after_green_followup_command = f"cat {approval_path}" if approval_path else ""
    elif live_send_gate == LIVE_SEND_APPROVAL_GREEN_GATE:
        after_green_followup_command = _current_approval_review_command(live_send_path)
    else:
        after_green_followup_command = _build_after_green_command(
            packet_dir.resolve(),
            resident_button_path.resolve()
            if resident_button_path and resident_button_gate == RESIDENT_BUTTON_GATE
            else None,
        )

    manifest = {
        "gate": gate,
        "run_at": datetime.now().isoformat(timespec="seconds"),
        "critical_stage": critical_stage,
        "exact_next_action": exact_next_action,
        "runtime_control_probe": args.runtime_control_probe,
        "source_gates": {
            "live_ui_validation": live_ui_gate,
            "resident_button": resident_button_gate,
            "chrome_reconnect": _gate(chrome),
            "live_send_approval": live_send_gate,
            "reply_polling": _gate(reply_polling),
            "google_board_apply": board_apply_gate,
            "resident_resume_packet": resident_resume_gate,
            "priority_enqueue_readiness": priority_enqueue_gate,
            "resident_proof_followup": followup_gate,
            "open_chat_no_type_packet": open_chat_packet_gate,
            "open_chat_no_type_result": open_chat_result_gate,
            "resident_heartbeat": resident_heartbeat_gate,
        },
        "source_paths": {
            "resident_heartbeat_manifest": _path_string(resident_heartbeat_path),
            "live_ui_validation_json": _path_string(live_ui_path),
            "resident_button_manifest": _path_string(resident_button_path),
            "chrome_reconnect_manifest": _path_string(chrome_path),
            "live_send_approval_manifest": _path_string(live_send_path),
            "reply_polling_manifest": _path_string(reply_polling_path),
            "google_board_apply_manifest": _path_string(board_apply_path),
            "resident_resume_manifest": _path_string(resident_resume_path),
            "priority_enqueue_readiness_manifest": _path_string(priority_enqueue_path),
            "resident_proof_followup_manifest": _path_string(resident_proof_followup_path),
            "open_chat_no_type_packet_manifest": _path_string(open_chat_packet_path),
            "open_chat_no_type_result_validation_json": _path_string(open_chat_result_path),
        },
        "merchant_selector_map": MERCHANT_SELECTOR_MAP,
        "current_priority_store": priority_store,
        "current_priority_expected_merchant_account_id": expected_selector_id,
        "resident_resume_scripts": {
            "start": _script_path(resident_resume, "start_script_path"),
            "guarded_enqueue": _script_path(resident_resume, "enqueue_script_path"),
            "watch_proof_and_build_approval": _script_path(resident_resume, "proof_followup_script_path"),
            "direct_build_approval": _script_path(resident_resume, "build_approval_script_path"),
        },
        "helper_prompt_path": str(helper_prompt),
        "after_green_followup_command": after_green_followup_command,
        "live_send_approval_phrase_path": _path_string(live_send_approval_phrase_path),
        "live_send_execution_handoff_path": _path_string(live_send_execution_handoff_path),
        "live_send_execution_starter_prompt_path": _path_string(live_send_execution_starter_prompt_path),
        "open_chat_no_type_approval_phrase_path": _path_string(
            _open_chat_approval_phrase_path(open_chat_packet_path)
        ),
        "google_board_apply_rows_ready": board_rows,
        "google_board_apply_ready_no_write": board_ready,
        "google_board_apply_approval_phrase_path": board_approval_path,
        "customer_send_allowed": False,
        "kaspi_chat_write_allowed": False,
        "google_board_write_allowed": False,
        "db_write_allowed": False,
        "telegram_send_allowed": False,
        "raw_order_id_exported": False,
        "raw_reply_text_exported": False,
        "blockers": blockers,
    }

    _write_json(output_dir / "manifest.json", manifest)
    (output_dir / "closeout.md").write_text(_build_closeout(manifest), encoding="utf-8")
    (output_dir / "ONE_SENTENCE_NEXT_ACTION.txt").write_text(
        exact_next_action + "\n",
        encoding="utf-8",
    )
    print(json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
