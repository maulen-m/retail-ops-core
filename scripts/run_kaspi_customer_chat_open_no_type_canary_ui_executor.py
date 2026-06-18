#!/usr/bin/env python3
"""Gate and record the Kaspi open-chat/no-type side-effect canary.

This script does not automate Kaspi UI clicks. It validates the approval packet
and gives a UI/browser helper one canonical redacted result format after the
helper has opened exactly one selected customer-message UI, typed nothing, sent
nothing, and preserved the browser session.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
from datetime import datetime
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
CURRENT_PACKET_DIR = (
    REPO_ROOT
    / "exports"
    / "validation"
    / "kaspi_customer_chat_open_no_type_canary_current_20260618_1549_no_send"
)
ENV_GATE = "ENABLE_KASPI_CUSTOMER_CHAT_OPEN_NO_TYPE_CANARY"
PACKET_GREEN_GATE = "GREEN_OPEN_CHAT_NO_TYPE_CANARY_PACKET_READY_NO_SEND"
READY_GATE = "GREEN_OPEN_CHAT_NO_TYPE_CANARY_UI_EXECUTOR_READY_NO_ACTION"
AWAITING_APPROVAL_GATE = "YELLOW_OPEN_CHAT_NO_TYPE_CANARY_UI_EXECUTOR_AWAITING_EXACT_APPROVAL_NO_ACTION"
BLOCKED_GATE = "YELLOW_OPEN_CHAT_NO_TYPE_CANARY_UI_EXECUTOR_BLOCKED_NO_ACTION"
UNSAFE_GATE = "RED_OPEN_CHAT_NO_TYPE_CANARY_UI_EXECUTOR_UNSAFE_NO_ACTION"
RESULT_GREEN_GATE = "GREEN_OPEN_CHAT_NO_TYPE_SIDE_EFFECT_CANARY_COMPLETED_NO_SEND"


def _default_output_dir() -> Path:
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return REPO_ROOT / "exports" / "validation" / f"kaspi_customer_chat_open_no_type_ui_executor_{stamp}"


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


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _load_expected_phrase(packet_dir: Path) -> tuple[str, Path]:
    path = packet_dir / "REQUIRED_EXACT_OPEN_CHAT_NO_TYPE_APPROVAL_PHRASE.txt"
    if not path.exists():
        return "", path
    return path.read_text(encoding="utf-8").strip(), path


def _load_supplied_phrase(args: argparse.Namespace) -> tuple[str, str]:
    if args.approval_text_file:
        return args.approval_text_file.read_text(encoding="utf-8").strip(), "file"
    if args.approval_from_stdin:
        import sys

        return sys.stdin.read().strip(), "stdin"
    return "", "not_supplied"


def _safe_text_scan(payload: dict[str, Any]) -> list[str]:
    text = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    blockers: list[str] = []
    phone_pattern = re.compile(
        r"(?<!\d)(?:\+?7|8)\D{0,3}\d{3}\D{0,3}\d{3}\D{0,3}\d{2}\D{0,3}\d{2}(?!\d)"
    )
    if phone_pattern.search(text):
        blockers.append("phone_like_value_detected")
    label_safe_text = (
        text.replace("raw_session_material_exported", "safe_session_export_flag")
        .replace("cookie_token_session_exported", "safe_session_export_flag")
        .replace("session_material", "safe_session_label")
    )
    for forbidden in ["authorization", "bearer", "localStorage", "sessionStorage", "cookie"]:
        if forbidden.lower() in label_safe_text.lower():
            blockers.append(f"forbidden_session_label_detected:{forbidden}")
    return blockers


def _load_surfaces(packet_dir: Path) -> tuple[dict[str, Any], dict[str, Any], Path]:
    manifest_path = packet_dir / "manifest.json"
    if not manifest_path.exists():
        return {}, {}, manifest_path
    manifest = _read_json(manifest_path)
    lock_path = Path(str(manifest.get("packet_manifest_path") or packet_dir / "open_chat_no_type_packet_lock.json"))
    lock = _read_json(lock_path) if lock_path.exists() else {}
    return manifest, lock, manifest_path


def _packet_blockers(
    *,
    packet_dir: Path,
    manifest: dict[str, Any],
    lock: dict[str, Any],
) -> tuple[list[str], list[str]]:
    blockers: list[str] = []
    unsafe: list[str] = []
    if not manifest:
        blockers.append("packet_manifest_missing")
        return blockers, unsafe
    if manifest.get("gate") != PACKET_GREEN_GATE:
        blockers.append(f"packet_manifest_gate_not_green:{manifest.get('gate')}")
    lock_path = Path(str(manifest.get("packet_manifest_path") or ""))
    expected_lock_sha = str(manifest.get("packet_manifest_sha256") or "")
    if not lock_path.exists():
        blockers.append("packet_lock_missing")
    elif expected_lock_sha and _sha256_file(lock_path) != expected_lock_sha:
        unsafe.append("packet_lock_sha256_mismatch")
    if not lock:
        blockers.append("packet_lock_json_missing")
    elif lock.get("gate") != PACKET_GREEN_GATE:
        blockers.append(f"packet_lock_gate_not_green:{lock.get('gate')}")
    required_false = [
        "customer_send_allowed_now",
        "kaspi_chat_write_allowed_now",
        "raw_order_id_exported",
        "raw_customer_text_exported",
        "raw_phone_exported",
        "raw_session_material_exported",
    ]
    for key in required_false:
        if manifest.get(key) is not False:
            unsafe.append(f"packet_manifest_{key}_not_false")
        if lock and lock.get(key) is not False:
            unsafe.append(f"packet_lock_{key}_not_false")
    if manifest.get("approval_phrase_generated") is not True:
        blockers.append("packet_approval_phrase_not_generated")
    if not (packet_dir / "REQUIRED_EXACT_OPEN_CHAT_NO_TYPE_APPROVAL_PHRASE.txt").exists():
        blockers.append("required_approval_phrase_file_missing")
    return blockers, unsafe


def build_observed_open_result(
    *,
    manifest: dict[str, Any],
    visible_merchant_selector_id: str,
    proof_source: str,
    proof_note: str,
    route_flags: dict[str, bool],
) -> dict[str, Any]:
    expected_selector = str(manifest.get("expected_merchant_account_id") or "").strip()
    visible_selector = str(visible_merchant_selector_id or "").strip()
    return {
        "gate": RESULT_GREEN_GATE,
        "recorded_at": datetime.now().isoformat(timespec="seconds"),
        "proof_source": proof_source,
        "proof_note": proof_note,
        "selected_order_ref": manifest.get("selected_order_ref"),
        "selected_db_row_id": manifest.get("selected_db_row_id"),
        "selected_store_code": manifest.get("selected_store_code"),
        "selected_status_filter": manifest.get("selected_status_filter"),
        "expected_merchant_account_id": expected_selector,
        "visible_merchant_selector_id": visible_selector,
        "merchant_account_match_proven": bool(expected_selector and visible_selector == expected_selector),
        "order_search_performed": True,
        "chat_opened": True,
        "message_text_typed": False,
        "message_sent": False,
        "customer_send_performed": False,
        "kaspi_chat_write_performed": False,
        "send_message_route_observed": bool(route_flags.get("send_message_route_observed")),
        "typing_send_text_route_observed": bool(route_flags.get("typing_send_text_route_observed")),
        "start_chat_route_observed": bool(route_flags.get("start_chat_route_observed")),
        "message_status_change_route_observed": bool(
            route_flags.get("message_status_change_route_observed")
        ),
        "load_more_messages_route_observed": bool(route_flags.get("load_more_messages_route_observed")),
        "browser_session_preserved": True,
        "other_customer_messages_sent": False,
        "raw_order_id_exported": False,
        "raw_customer_text_exported": False,
        "raw_phone_exported": False,
        "raw_session_material_exported": False,
        "cookie_token_session_exported": False,
    }


def _route_flags_from_args(args: argparse.Namespace) -> dict[str, bool]:
    return {
        "send_message_route_observed": bool(args.send_message_route_observed),
        "typing_send_text_route_observed": bool(args.typing_send_text_route_observed),
        "start_chat_route_observed": bool(args.start_chat_route_observed),
        "message_status_change_route_observed": bool(args.message_status_change_route_observed),
        "load_more_messages_route_observed": bool(args.load_more_messages_route_observed),
    }


def _result_unsafe_blockers(result: dict[str, Any]) -> list[str]:
    unsafe: list[str] = []
    if result.get("merchant_account_match_proven") is not True:
        unsafe.append("visible_merchant_selector_mismatch")
    if result.get("chat_opened") is not True:
        unsafe.append("chat_opened_not_true")
    for key in [
        "message_text_typed",
        "message_sent",
        "customer_send_performed",
        "kaspi_chat_write_performed",
        "send_message_route_observed",
        "typing_send_text_route_observed",
        "start_chat_route_observed",
        "raw_order_id_exported",
        "raw_customer_text_exported",
        "raw_phone_exported",
        "raw_session_material_exported",
        "cookie_token_session_exported",
        "other_customer_messages_sent",
    ]:
        if result.get(key) is not False:
            unsafe.append(f"{key}_not_false")
    unsafe.extend(_safe_text_scan(result))
    return unsafe


def _render_closeout(manifest: dict[str, Any]) -> str:
    lines = [
        "# Kaspi Customer Chat Open-Chat No-Type UI Executor",
        "",
        f"Gate: {manifest['gate']}",
        "",
        "## Scope",
        "",
        "- Guarded recorder for exactly one open-chat/no-type side-effect canary.",
        "- This script performs no browser UI clicks and sends no customer message.",
        "",
        "## Target",
        "",
        f"- Packet dir: `{manifest.get('packet_dir')}`",
        f"- Selected order ref: `{manifest.get('selected_order_ref')}`",
        f"- Selected DB row: `{manifest.get('selected_db_row_id')}`",
        f"- Store: `{manifest.get('selected_store_code')}`",
        f"- Expected merchant selector ID: `{manifest.get('expected_merchant_account_id')}`",
        "",
        "## Safety",
        "",
        f"- Apply requested: {str(manifest.get('apply_requested')).lower()}",
        f"- Env gate enabled: {str(manifest.get('env_gate_enabled')).lower()}",
        f"- Result recorded: {str(manifest.get('result_recorded')).lower()}",
        "- Message text typed: false",
        "- Message sent: false",
        "- Raw order/customer/session material exported: false",
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
    parser.add_argument("--packet-dir", type=Path, default=CURRENT_PACKET_DIR)
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--approval-text-file", type=Path)
    parser.add_argument("--approval-from-stdin", action="store_true")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--record-observed-open-result", action="store_true")
    parser.add_argument("--visible-merchant-selector-id", default="")
    parser.add_argument("--proof-source", default="ui_helper_observed")
    parser.add_argument("--proof-note", default="")
    parser.add_argument("--send-message-route-observed", action="store_true")
    parser.add_argument("--typing-send-text-route-observed", action="store_true")
    parser.add_argument("--start-chat-route-observed", action="store_true")
    parser.add_argument("--message-status-change-route-observed", action="store_true")
    parser.add_argument("--load-more-messages-route-observed", action="store_true")
    return parser


def run(args: argparse.Namespace, *, environ: dict[str, str] | None = None) -> dict[str, Any]:
    environ = dict(os.environ if environ is None else environ)
    packet_dir = args.packet_dir.resolve()
    output_dir = (args.output_dir or _default_output_dir()).resolve()
    manifest, lock, packet_manifest_path = _load_surfaces(packet_dir)
    blockers, unsafe = _packet_blockers(packet_dir=packet_dir, manifest=manifest, lock=lock)
    expected_phrase, expected_phrase_path = _load_expected_phrase(packet_dir)
    supplied_phrase, approval_source = _load_supplied_phrase(args)
    phrase_supplied = bool(supplied_phrase)
    phrase_matches = bool(expected_phrase and supplied_phrase == expected_phrase)
    if expected_phrase and supplied_phrase and not phrase_matches:
        unsafe.append("owner_approval_text_mismatch")
    if not expected_phrase:
        blockers.append("expected_approval_phrase_missing")
    if not phrase_matches:
        blockers.append("owner_exact_approval_not_supplied_or_not_matched")

    apply_requested = bool(args.apply)
    env_gate_enabled = environ.get(ENV_GATE) == "1"
    if apply_requested and not env_gate_enabled:
        blockers.append(f"{ENV_GATE}_not_1")
    result_path = packet_dir / "open_chat_no_type_result_redacted.json"
    closeout_path = packet_dir / "open_chat_no_type_canary_closeout.md"
    if result_path.exists() or closeout_path.exists():
        blockers.append("open_chat_no_type_result_or_closeout_already_exists")

    result_payload: dict[str, Any] | None = None
    result_recorded = False
    if args.record_observed_open_result:
        if not str(args.visible_merchant_selector_id or "").strip():
            unsafe.append("visible_merchant_selector_id_required_for_observed_result")
        result_payload = build_observed_open_result(
            manifest=manifest,
            visible_merchant_selector_id=args.visible_merchant_selector_id,
            proof_source=str(args.proof_source or "ui_helper_observed"),
            proof_note=str(args.proof_note or ""),
            route_flags=_route_flags_from_args(args),
        )
        unsafe.extend(_result_unsafe_blockers(result_payload))
    elif apply_requested and env_gate_enabled:
        blockers.append("record_observed_open_result_not_supplied")

    if unsafe:
        gate = UNSAFE_GATE
    elif blockers:
        gate = AWAITING_APPROVAL_GATE if blockers == ["owner_exact_approval_not_supplied_or_not_matched"] else BLOCKED_GATE
    elif not apply_requested:
        gate = READY_GATE
    else:
        gate = RESULT_GREEN_GATE
        if result_payload is not None:
            _write_json(result_path, result_payload)
            _write_text(
                closeout_path,
                "\n".join(
                    [
                        "# Kaspi Open-Chat No-Type Side-Effect Canary Closeout",
                        "",
                        f"Gate: {RESULT_GREEN_GATE}",
                        "",
                        f"- Selected order ref: {result_payload.get('selected_order_ref')}",
                        f"- Store: {result_payload.get('selected_store_code')}",
                        f"- Visible merchant selector ID: {result_payload.get('visible_merchant_selector_id')}",
                        "- Chat opened: true",
                        "- Message text typed: false",
                        "- Message sent: false",
                        "- Raw order ID/customer text/phone/session material exported: false",
                        "",
                    ]
                ),
            )
            result_recorded = True

    report = {
        "gate": gate,
        "run_at": datetime.now().isoformat(timespec="seconds"),
        "packet_dir": str(packet_dir),
        "packet_manifest_path": str(packet_manifest_path),
        "packet_lock_path": str(manifest.get("packet_manifest_path") or ""),
        "packet_lock_sha256": str(manifest.get("packet_manifest_sha256") or ""),
        "output_dir": str(output_dir),
        "selected_order_ref": manifest.get("selected_order_ref"),
        "selected_db_row_id": manifest.get("selected_db_row_id"),
        "selected_store_code": manifest.get("selected_store_code"),
        "selected_status_filter": manifest.get("selected_status_filter"),
        "expected_merchant_account_id": manifest.get("expected_merchant_account_id"),
        "expected_approval_phrase_path": str(expected_phrase_path),
        "expected_approval_phrase_sha256": _sha256_text(expected_phrase) if expected_phrase else "",
        "owner_approval_text_source": approval_source,
        "owner_approval_text_supplied": phrase_supplied,
        "owner_approval_text_match": phrase_matches,
        "apply_requested": apply_requested,
        "env_gate_name": ENV_GATE,
        "env_gate_enabled": env_gate_enabled,
        "record_observed_open_result": bool(args.record_observed_open_result),
        "result_json_path": str(result_path),
        "result_closeout_path": str(closeout_path),
        "result_recorded": result_recorded,
        "customer_send_performed_by_this_script": False,
        "kaspi_chat_write_performed_by_this_script": False,
        "message_text_typed": False,
        "message_sent": False,
        "google_board_write_allowed": False,
        "db_write_allowed": False,
        "telegram_send_allowed": False,
        "raw_order_id_exported": False,
        "raw_customer_text_exported": False,
        "raw_phone_exported": False,
        "raw_session_material_exported": False,
        "blockers": sorted(set(blockers)),
        "unsafe_blockers": sorted(set(unsafe)),
        "exact_next_action": (
            "Run the result validator / post-canary sequence after reviewing observed side-effect routes."
            if result_recorded
            else "Provide exact owner approval, perform the one-order UI open-chat/no-type canary, then rerun with --apply --record-observed-open-result."
        ),
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    _write_json(output_dir / "manifest.json", report)
    _write_text(output_dir / "closeout.md", _render_closeout(report))
    return report


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    manifest = run(args)
    print(json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True))
    if str(manifest.get("gate") or "").startswith("RED_"):
        return 2
    if args.apply and manifest.get("gate") != RESULT_GREEN_GATE:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
