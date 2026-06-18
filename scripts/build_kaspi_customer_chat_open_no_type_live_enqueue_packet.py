#!/usr/bin/env python3
"""Build the final local packet before open-chat/no-type live enqueue.

This script performs no browser action, opens no chat, types nothing, sends
nothing, and does not write to the resident command queue. It converts a GREEN
dry-run promoter manifest into an auditable one-switch packet for the next
operator/agent step.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DRY_RUN_MANIFEST = (
    REPO_ROOT
    / "exports"
    / "validation"
    / "kaspi_customer_chat_open_no_type_live_enqueue_preflight_current_20260618_order_detail_ready_dry_run_no_action"
    / "manifest.json"
)
DEFAULT_APPROVAL_PHRASE = (
    REPO_ROOT
    / "exports"
    / "validation"
    / "kaspi_customer_chat_open_no_type_canary_current_20260618_1549_no_send"
    / "REQUIRED_EXACT_OPEN_CHAT_NO_TYPE_APPROVAL_PHRASE.txt"
)
GREEN_DRY_RUN_GATE = "GREEN_OPEN_CHAT_NO_TYPE_LIVE_ENQUEUE_PREFLIGHT_READY_DRY_RUN_NO_ACTION"
GREEN_GATE = "GREEN_OPEN_CHAT_NO_TYPE_LIVE_ENQUEUE_PACKET_READY_NO_ACTION"
YELLOW_GATE = "YELLOW_OPEN_CHAT_NO_TYPE_LIVE_ENQUEUE_PACKET_BLOCKED_NO_ACTION"
RED_GATE = "RED_OPEN_CHAT_NO_TYPE_LIVE_ENQUEUE_PACKET_UNSAFE_NO_ACTION"


def _default_output_dir() -> Path:
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return REPO_ROOT / "exports" / "validation" / f"kaspi_customer_chat_open_no_type_live_enqueue_packet_{stamp}"


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


def _shell_quote(path: Path) -> str:
    text = str(path)
    return "'" + text.replace("'", "'\"'\"'") + "'"


def _apply_command(*, dry_run_manifest: dict[str, Any], approval_phrase_path: Path, output_dir: Path) -> str:
    staged_command = _shell_quote(Path(str(dry_run_manifest.get("staged_command_path") or "")))
    live_run_dir = _shell_quote(Path(str(dry_run_manifest.get("live_run_dir") or "")))
    heartbeat = _shell_quote(Path(str(dry_run_manifest.get("heartbeat_path") or "")))
    approval = _shell_quote(approval_phrase_path)
    apply_output = _shell_quote(output_dir / "apply_result")
    return (
        "cd ~/Docs/Autonomous_business && "
        "ENABLE_KASPI_CUSTOMER_CHAT_OPEN_NO_TYPE_LIVE_ENQUEUE=1 "
        "PYTHONPATH=. .venv/bin/python "
        "scripts/promote_kaspi_customer_chat_open_no_type_staged_command.py "
        f"--staged-command {staged_command} "
        f"--live-run-dir {live_run_dir} "
        f"--heartbeat-json {heartbeat} "
        f"--approval-text-file {approval} "
        f"--output-dir {apply_output} "
        "--apply"
    )


def _closeout(manifest: dict[str, Any]) -> str:
    lines = [
        "# Kaspi Open-Chat No-Type Live Enqueue Packet",
        "",
        f"Gate: {manifest['gate']}",
        "",
        "## Scope",
        "",
        "Local readiness packet for writing exactly one open-chat/no-type command into the resident queue.",
        "This packet itself performs no queue write, browser action, chat open, typing, send, DB write, Google Board write, or Telegram action.",
        "",
        "## Target",
        "",
        f"- Store: `{manifest.get('selected_store_code') or 'ACMEWEAR'}`",
        f"- Selected DB row: `{manifest.get('selected_db_row_id')}`",
        f"- Selected order ref: `{manifest.get('selected_order_ref')}`",
        f"- Expected merchant account ID: `{manifest.get('expected_merchant_account_id')}`",
        f"- Resident order-detail proof accepted: {str(manifest.get('resident_order_detail_proof_accepted')).lower()}",
        "",
        "## Apply Command",
        "",
        "Run only when the owner deliberately approves opening exactly this one chat and typing/sending nothing:",
        "",
        "```bash",
        str(manifest.get("apply_command") or ""),
        "```",
        "",
        "## Safety",
        "",
        "- Customer send performed: false",
        "- Kaspi chat write performed: false",
        "- Browser action performed by packet builder: false",
        "- Live enqueue performed by packet builder: false",
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
    return "\n".join(lines)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run-manifest", type=Path, default=DEFAULT_DRY_RUN_MANIFEST)
    parser.add_argument("--approval-phrase-file", type=Path, default=DEFAULT_APPROVAL_PHRASE)
    parser.add_argument("--output-dir", type=Path)
    return parser


def build_packet(args: argparse.Namespace) -> dict[str, Any]:
    output_dir = (args.output_dir or _default_output_dir()).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    dry_run_path = args.dry_run_manifest.resolve()
    approval_path = args.approval_phrase_file.resolve()
    blockers: list[str] = []
    unsafe: list[str] = []
    dry_run: dict[str, Any] = {}
    approval_phrase = ""

    if not dry_run_path.exists():
        blockers.append("dry_run_manifest_missing")
    else:
        dry_run = _read_json(dry_run_path)

    if not approval_path.exists():
        blockers.append("approval_phrase_file_missing")
    else:
        approval_phrase = approval_path.read_text(encoding="utf-8").strip()
        if not approval_phrase:
            blockers.append("approval_phrase_file_empty")

    if dry_run:
        if dry_run.get("gate") != GREEN_DRY_RUN_GATE:
            blockers.append(f"dry_run_gate_not_green:{dry_run.get('gate') or 'MISSING'}")
            blockers.extend(str(value) for value in dry_run.get("blockers") or [])
        if dry_run.get("live_enqueue_performed") is not False:
            unsafe.append("dry_run_live_enqueue_performed_not_false")
        for key in [
            "browser_action_performed",
            "chat_opened",
            "customer_send_performed",
            "kaspi_chat_write_performed",
            "message_text_typed",
            "message_sent",
            "raw_order_id_exported",
            "raw_customer_text_exported",
            "raw_phone_exported",
            "raw_session_material_exported",
        ]:
            if dry_run.get(key) is not False:
                unsafe.append(f"dry_run_{key}_not_false")
        if dry_run.get("resident_open_chat_no_type_preflight_gate") != (
            "GREEN_KASPI_CUSTOMER_CHAT_OPEN_CHAT_NO_TYPE_PREFLIGHT_READY_NO_ACTION"
        ):
            blockers.append("resident_open_chat_no_type_preflight_not_green")
        resident_search_ready = (
            dry_run.get("resident_heartbeat_gate")
            == "GREEN_KASPI_CUSTOMER_CHAT_RESIDENT_NO_SEND_CONTROLLER_READY"
            and dry_run.get("resident_orders_search_input_visible") is True
        )
        if dry_run.get("resident_order_detail_proof_accepted") is not True and not resident_search_ready:
            blockers.append("resident_order_detail_or_search_ready_not_accepted")
        if not str(dry_run.get("expected_merchant_account_id") or "").strip():
            blockers.append("expected_merchant_account_id_missing")
        if not str(dry_run.get("selected_db_row_id") or "").strip():
            blockers.append("selected_db_row_id_missing")
        if not str(dry_run.get("selected_order_ref") or "").strip():
            blockers.append("selected_order_ref_missing")

    gate = GREEN_GATE
    if unsafe:
        gate = RED_GATE
    elif blockers:
        gate = YELLOW_GATE

    apply_command = _apply_command(
        dry_run_manifest=dry_run,
        approval_phrase_path=approval_path,
        output_dir=output_dir,
    ) if gate == GREEN_GATE and dry_run and approval_path.exists() else ""
    manifest = {
        "gate": gate,
        "run_at": datetime.now().isoformat(timespec="seconds"),
        "dry_run_manifest_path": str(dry_run_path),
        "dry_run_manifest_sha256": _sha256_file(dry_run_path) if dry_run_path.exists() else "",
        "dry_run_gate": dry_run.get("gate", ""),
        "approval_phrase_path": str(approval_path),
        "approval_phrase_sha256": hashlib.sha256(approval_phrase.encode("utf-8")).hexdigest()
        if approval_phrase
        else "",
        "output_dir": str(output_dir),
        "apply_command": apply_command,
        "selected_order_ref": dry_run.get("selected_order_ref", ""),
        "selected_db_row_id": dry_run.get("selected_db_row_id", ""),
        "selected_store_code": "ACMEWEAR",
        "expected_merchant_account_id": dry_run.get("expected_merchant_account_id", ""),
        "resident_order_detail_proof_accepted": dry_run.get("resident_order_detail_proof_accepted"),
        "resident_order_detail_proof_path": dry_run.get("resident_order_detail_proof_path", ""),
        "live_enqueue_performed": False,
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
        "unsafe_blockers": sorted(set(unsafe)),
        "exact_next_action": (
            "Run the apply command only when deliberately ready to enqueue one open-chat/no-type command; the resident controller may then open exactly one selected customer chat, type nothing, and send nothing."
            if gate == GREEN_GATE
            else "Resolve blockers before any live queue enqueue."
        ),
    }
    _write_json(output_dir / "manifest.json", manifest)
    _write_text(output_dir / "closeout.md", _closeout(manifest))
    _write_text(output_dir / "APPLY_COMMAND.sh", apply_command + "\n" if apply_command else "")
    return manifest


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    manifest = build_packet(args)
    print(json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True))
    if str(manifest.get("gate") or "").startswith("RED_"):
        return 2
    return 0 if manifest.get("gate") == GREEN_GATE else 1


if __name__ == "__main__":
    raise SystemExit(main())
