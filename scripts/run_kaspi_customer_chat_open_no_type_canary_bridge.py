#!/usr/bin/env python3
"""Guarded bridge for the current Kaspi open-chat/no-type canary.

Default mode is no-action: validate the current live-enqueue packet, approval
phrase, dry-run promoter evidence, and resident heartbeat freshness. Applying
only writes one prevalidated command into the resident queue; the resident
controller is the only component that may later open exactly one chat.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from scripts.promote_kaspi_customer_chat_open_no_type_staged_command import (
    ENV_GATE as PROMOTER_ENV_GATE,
    GREEN_APPLY_GATE as PROMOTER_GREEN_APPLY_GATE,
    GREEN_DRY_RUN_GATE as PROMOTER_GREEN_DRY_RUN_GATE,
    run as promoter_run,
)


REPO_ROOT = Path(__file__).resolve().parents[1]
LIVE_PACKET_GREEN_GATE = "GREEN_OPEN_CHAT_NO_TYPE_LIVE_ENQUEUE_PACKET_READY_NO_ACTION"
BRIDGE_READY_GATE = "GREEN_OPEN_CHAT_NO_TYPE_BRIDGE_READY_NO_ACTION"
BRIDGE_APPLY_GATE = "GREEN_OPEN_CHAT_NO_TYPE_BRIDGE_COMMAND_ENQUEUED_NO_SEND"
BRIDGE_YELLOW_GATE = "YELLOW_OPEN_CHAT_NO_TYPE_BRIDGE_BLOCKED_NO_ACTION"
BRIDGE_RED_GATE = "RED_OPEN_CHAT_NO_TYPE_BRIDGE_UNSAFE_NO_ACTION"
BRIDGE_APPLY_ENV_GATE = "ENABLE_KASPI_CUSTOMER_CHAT_OPEN_NO_TYPE_BRIDGE_APPLY"
RESIDENT_GREEN_GATE = "GREEN_KASPI_CUSTOMER_CHAT_RESIDENT_NO_SEND_CONTROLLER_READY"


def _latest(pattern: str) -> Path | None:
    matches = [path for path in REPO_ROOT.glob(pattern) if path.is_file()]
    if not matches:
        return None
    return max(matches, key=lambda path: path.stat().st_mtime)


def _read_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"Expected object JSON at {path}")
    return payload


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _safe_sha256_file(path: Path | None) -> str:
    if not path or not path.exists() or not path.is_file():
        return ""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _path_from_text(text: Any) -> Path | None:
    value = str(text or "").strip()
    if not value:
        return None
    path = Path(value)
    return path if path.is_absolute() else (REPO_ROOT / path).resolve()


def _parse_recorded_at(value: Any) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return datetime.fromisoformat(text)
    except ValueError:
        return None


def _heartbeat_age_seconds(heartbeat: dict[str, Any]) -> int | None:
    recorded_at = _parse_recorded_at(
        heartbeat.get("recorded_at") or heartbeat.get("run_at") or heartbeat.get("recordedAt")
    )
    if not recorded_at:
        return None
    return max(0, int((datetime.now() - recorded_at).total_seconds()))


def _default_output_dir() -> Path:
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return REPO_ROOT / "exports" / "validation" / f"kaspi_customer_chat_open_no_type_bridge_{stamp}"


def _closeout(report: dict[str, Any]) -> str:
    lines = [
        "# Kaspi Open-Chat No-Type Canary Bridge",
        "",
        f"Gate: {report['gate']}",
        "",
        "## Scope",
        "",
        "This bridge validates the current open-chat/no-type canary path. By default",
        "it performs no queue write, browser action, chat open, typing, send, DB write,",
        "Google Board write, Telegram send, or WhatsApp send.",
        "",
        "## Evidence",
        "",
        f"- Live enqueue packet: `{report.get('live_enqueue_packet_manifest_path')}`",
        f"- Live enqueue packet gate: `{report.get('live_enqueue_packet_gate')}`",
        f"- Dry-run promoter manifest: `{report.get('dry_run_manifest_path')}`",
        f"- Dry-run promoter gate: `{report.get('dry_run_gate')}`",
        f"- Approval phrase file: `{report.get('approval_phrase_path')}`",
        f"- Resident heartbeat: `{report.get('heartbeat_path')}`",
        f"- Resident heartbeat gate: `{report.get('resident_heartbeat_gate')}`",
        f"- Resident heartbeat age seconds: `{report.get('resident_heartbeat_age_seconds')}`",
        "",
        "## Target",
        "",
        f"- Store: `{report.get('selected_store_code')}`",
        f"- DB row: `{report.get('selected_db_row_id')}`",
        f"- Order ref: `{report.get('selected_order_ref')}`",
        f"- Expected merchant account ID: `{report.get('expected_merchant_account_id')}`",
        "",
        "## Safety",
        "",
        f"- Apply requested: {str(report.get('apply_requested')).lower()}",
        f"- Bridge env gate enabled: {str(report.get('bridge_env_gate_enabled')).lower()}",
        f"- Promoter env gate enabled: {str(report.get('promoter_env_gate_enabled')).lower()}",
        f"- Live enqueue performed: {str(report.get('live_enqueue_performed')).lower()}",
        "- Browser action performed by bridge: false",
        "- Chat opened by bridge: false",
        "- Message text typed: false",
        "- Message sent: false",
        "",
    ]
    blockers = [*(report.get("blockers") or []), *(report.get("unsafe_blockers") or [])]
    if blockers:
        lines.extend(["## Blockers", ""])
        lines.extend(f"- {blocker}" for blocker in blockers)
        lines.append("")
    if report.get("apply_command"):
        lines.extend(["## Apply Command", "", "```bash", str(report["apply_command"]), "```", ""])
    return "\n".join(lines)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live-enqueue-packet-manifest", type=Path)
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--heartbeat-max-age-seconds", type=int, default=300)
    parser.add_argument("--apply", action="store_true")
    return parser


def run(args: argparse.Namespace, *, environ: dict[str, str] | None = None) -> dict[str, Any]:
    environ = dict(os.environ if environ is None else environ)
    output_dir = (args.output_dir or _default_output_dir()).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    blockers: list[str] = []
    unsafe: list[str] = []

    packet_path = args.live_enqueue_packet_manifest or _latest(
        "exports/validation/kaspi_customer_chat_open_no_type_live_enqueue_packet_*/manifest.json"
    )
    packet_path = packet_path.resolve() if packet_path else None
    packet: dict[str, Any] = {}
    if not packet_path or not packet_path.exists():
        blockers.append("live_enqueue_packet_manifest_missing")
    else:
        packet = _read_json(packet_path)

    dry_run_path = _path_from_text(packet.get("dry_run_manifest_path")) if packet else None
    dry_run: dict[str, Any] = {}
    if packet and not dry_run_path:
        blockers.append("dry_run_manifest_path_missing")
    elif dry_run_path and not dry_run_path.exists():
        blockers.append("dry_run_manifest_missing")
    elif dry_run_path:
        dry_run = _read_json(dry_run_path)

    approval_path = _path_from_text(packet.get("approval_phrase_path")) if packet else None
    approval_text = ""
    if packet and not approval_path:
        blockers.append("approval_phrase_path_missing")
    elif approval_path and not approval_path.exists():
        blockers.append("approval_phrase_file_missing")
    elif approval_path:
        approval_text = approval_path.read_text(encoding="utf-8").strip()
        if not approval_text:
            blockers.append("approval_phrase_file_empty")

    heartbeat_path = _path_from_text(dry_run.get("heartbeat_path")) if dry_run else None
    heartbeat: dict[str, Any] = {}
    heartbeat_age = None
    if dry_run and not heartbeat_path:
        blockers.append("resident_heartbeat_path_missing")
    elif heartbeat_path and not heartbeat_path.exists():
        blockers.append("resident_heartbeat_missing")
    elif heartbeat_path:
        heartbeat = _read_json(heartbeat_path)
        heartbeat_age = _heartbeat_age_seconds(heartbeat)

    if packet:
        if packet.get("gate") != LIVE_PACKET_GREEN_GATE:
            blockers.append(f"live_enqueue_packet_not_green:{packet.get('gate') or 'MISSING'}")
        if packet.get("dry_run_manifest_sha256") and dry_run_path:
            if _safe_sha256_file(dry_run_path) != packet.get("dry_run_manifest_sha256"):
                unsafe.append("dry_run_manifest_sha_mismatch")
        if packet.get("approval_phrase_sha256") and approval_text:
            if _sha256_text(approval_text) != packet.get("approval_phrase_sha256"):
                unsafe.append("approval_phrase_sha_mismatch")
        for key in [
            "live_enqueue_performed",
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
            if packet.get(key) is not False:
                unsafe.append(f"packet_{key}_not_false")

    if dry_run:
        if dry_run.get("gate") != PROMOTER_GREEN_DRY_RUN_GATE:
            blockers.append(f"dry_run_not_green:{dry_run.get('gate') or 'MISSING'}")
        for key in [
            "live_enqueue_performed",
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

    if heartbeat:
        if heartbeat.get("gate") != RESIDENT_GREEN_GATE:
            blockers.append(f"resident_heartbeat_not_green:{heartbeat.get('gate') or 'MISSING'}")
        if heartbeat.get("orders_search_input_visible") is not True:
            blockers.append("resident_orders_search_input_not_visible")
        if heartbeat_age is None:
            blockers.append("resident_heartbeat_recorded_at_missing_or_invalid")
        elif heartbeat_age > int(args.heartbeat_max_age_seconds):
            blockers.append(
                f"resident_heartbeat_stale:{heartbeat_age}s>{int(args.heartbeat_max_age_seconds)}s"
            )
        for key in ["message_text_typed", "message_sent"]:
            if heartbeat.get(key) is not False:
                unsafe.append(f"resident_heartbeat_{key}_not_false")

    apply_requested = bool(args.apply)
    bridge_env_gate_enabled = environ.get(BRIDGE_APPLY_ENV_GATE) == "1"
    promoter_env_gate_enabled = environ.get(PROMOTER_ENV_GATE) == "1"
    if apply_requested and not bridge_env_gate_enabled:
        blockers.append(f"{BRIDGE_APPLY_ENV_GATE}_not_1")
    if apply_requested and not promoter_env_gate_enabled:
        blockers.append(f"{PROMOTER_ENV_GATE}_not_1")

    promoter_report: dict[str, Any] = {}
    live_enqueue_performed = False
    if unsafe:
        gate = BRIDGE_RED_GATE
    elif blockers:
        gate = BRIDGE_YELLOW_GATE
    elif apply_requested:
        promoter_args = SimpleNamespace(
            staged_command=_path_from_text(dry_run.get("staged_command_path")),
            live_run_dir=_path_from_text(dry_run.get("live_run_dir")),
            heartbeat_json=heartbeat_path,
            approval_text_file=approval_path,
            output_dir=output_dir / "apply_result",
            apply=True,
        )
        promoter_report = promoter_run(promoter_args, environ=environ)
        live_enqueue_performed = bool(promoter_report.get("live_enqueue_performed"))
        gate = (
            BRIDGE_APPLY_GATE
            if promoter_report.get("gate") == PROMOTER_GREEN_APPLY_GATE
            else BRIDGE_YELLOW_GATE
        )
        if gate != BRIDGE_APPLY_GATE:
            blockers.extend(str(value) for value in promoter_report.get("blockers") or [])
            unsafe.extend(str(value) for value in promoter_report.get("unsafe_blockers") or [])
    else:
        gate = BRIDGE_READY_GATE

    report = {
        "gate": gate,
        "run_at": datetime.now().isoformat(timespec="seconds"),
        "live_enqueue_packet_manifest_path": str(packet_path) if packet_path else "",
        "live_enqueue_packet_gate": packet.get("gate", ""),
        "dry_run_manifest_path": str(dry_run_path) if dry_run_path else "",
        "dry_run_gate": dry_run.get("gate", ""),
        "approval_phrase_path": str(approval_path) if approval_path else "",
        "approval_phrase_sha256": _sha256_text(approval_text) if approval_text else "",
        "heartbeat_path": str(heartbeat_path) if heartbeat_path else "",
        "resident_heartbeat_gate": heartbeat.get("gate", ""),
        "resident_heartbeat_recorded_at": heartbeat.get("recorded_at", ""),
        "resident_heartbeat_age_seconds": heartbeat_age,
        "heartbeat_max_age_seconds": int(args.heartbeat_max_age_seconds),
        "selected_store_code": packet.get("selected_store_code", "ACMEWEAR"),
        "selected_db_row_id": packet.get("selected_db_row_id", ""),
        "selected_order_ref": packet.get("selected_order_ref", ""),
        "expected_merchant_account_id": packet.get("expected_merchant_account_id", ""),
        "apply_requested": apply_requested,
        "bridge_env_gate_name": BRIDGE_APPLY_ENV_GATE,
        "bridge_env_gate_enabled": bridge_env_gate_enabled,
        "promoter_env_gate_name": PROMOTER_ENV_GATE,
        "promoter_env_gate_enabled": promoter_env_gate_enabled,
        "promoter_report_gate": promoter_report.get("gate", ""),
        "promoter_report_path": str((output_dir / "apply_result" / "manifest.json").resolve())
        if promoter_report
        else "",
        "apply_command": packet.get("apply_command", "") if packet else "",
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
        "unsafe_blockers": sorted(set(unsafe)),
    }
    _write_json(output_dir / "manifest.json", report)
    (output_dir / "closeout.md").write_text(_closeout(report), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    return report


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    report = run(args)
    if str(report.get("gate") or "").startswith("RED_"):
        return 2
    if args.apply and report.get("gate") != BRIDGE_APPLY_GATE:
        return 1
    return 0 if report.get("gate") == BRIDGE_READY_GATE else 1


if __name__ == "__main__":
    raise SystemExit(main())
