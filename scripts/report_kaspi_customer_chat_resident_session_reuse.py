#!/usr/bin/env python3
"""Report whether the resident Kaspi customer-chat session is safe to reuse.

This helper is deliberately read-only and browser-free. It exists so future
agents can check the already-authenticated resident controller instead of
closing/relaunching Playwright and forcing another SMS login.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_RESIDENT_RUN_DIR = (
    PROJECT_ROOT
    / "exports"
    / "validation"
    / "kaspi_customer_chat_resident_no_send_controller_current"
)
DEFAULT_HEARTBEAT = DEFAULT_RESIDENT_RUN_DIR / "resident_controller_heartbeat.json"
DEFAULT_LIVE_SEND_APPROVAL = (
    PROJECT_ROOT
    / "exports"
    / "validation"
    / "kaspi_customer_chat_live_send_canary_approval_AFTER_RESIDENT_GREEN_NO_SEND_20260617_1845"
    / "manifest.json"
)
GREEN_GATE = "GREEN_KASPI_CUSTOMER_CHAT_RESIDENT_SESSION_REUSE_READY_NO_SEND"
YELLOW_GATE = "YELLOW_KASPI_CUSTOMER_CHAT_RESIDENT_SESSION_REUSE_NOT_READY_NO_SEND"
RED_GATE = "RED_KASPI_CUSTOMER_CHAT_RESIDENT_SESSION_REUSE_UNSAFE_STATE"


def _default_output_dir() -> Path:
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return PROJECT_ROOT / "exports" / "validation" / f"kaspi_customer_chat_resident_session_reuse_{stamp}"


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _approval_summary(path: Path) -> dict[str, Any]:
    summary: dict[str, Any] = {
        "manifest_path": str(path),
        "manifest_exists": path.exists(),
        "approval_packet_ready_no_send": False,
        "approval_phrase_path": "",
        "selected_store_code": "",
        "selected_db_row_id": "",
        "customer_send_allowed_now": False,
    }
    if not path.exists():
        return summary
    manifest = _read_json(path)
    approval_phrase_path = str(manifest.get("approval_phrase_path") or "").strip()
    if not approval_phrase_path and manifest.get("approval_phrase_generated") is True:
        sidecar = path.parent / "REQUIRED_EXACT_LIVE_SEND_CANARY_APPROVAL_PHRASE.txt"
        if sidecar.exists():
            approval_phrase_path = str(sidecar)
    summary.update(
        {
            "gate": manifest.get("gate", ""),
            "approval_packet_ready_no_send": manifest.get("gate")
            == "GREEN_LIVE_SEND_CANARY_APPROVAL_PACKET_READY_NO_SEND",
            "approval_phrase_path": approval_phrase_path,
            "selected_store_code": manifest.get("selected_store_code", ""),
            "selected_db_row_id": manifest.get("selected_db_row_id", ""),
            "customer_send_allowed_now": bool(manifest.get("customer_send_allowed_now")),
        }
    )
    return summary


def build_report(
    *,
    heartbeat_path: Path,
    live_send_approval_manifest: Path | None,
    output_dir: Path,
) -> dict[str, Any]:
    blockers: list[str] = []
    unsafe_blockers: list[str] = []
    checks: dict[str, Any] = {
        "heartbeat_path": str(heartbeat_path),
        "heartbeat_exists": heartbeat_path.exists(),
        "output_dir": str(output_dir),
    }
    heartbeat: dict[str, Any] = {}
    if heartbeat_path.exists():
        heartbeat = _read_json(heartbeat_path)
    else:
        blockers.append("resident_heartbeat_missing")

    if heartbeat:
        for key in [
            "gate",
            "recorded_at",
            "run_dir",
            "profile_store_code",
            "persistent_profile_mode",
            "persistent_profile_dir_path",
            "commands_dir",
            "browser_should_remain_open",
            "orders_search_input_visible",
            "safe_current_url",
        ]:
            checks[key] = heartbeat.get(key)

        if str(heartbeat.get("gate") or "").startswith("RED_"):
            unsafe_blockers.append("resident_heartbeat_red")
        if heartbeat.get("message_sent") is True:
            unsafe_blockers.append("heartbeat_message_sent_true")
        if heartbeat.get("message_text_typed") is True:
            unsafe_blockers.append("heartbeat_message_text_typed_true")
        if heartbeat.get("chat_opened") is True:
            unsafe_blockers.append("heartbeat_chat_opened_true")
        if heartbeat.get("customer_send_allowed") is True:
            unsafe_blockers.append("heartbeat_customer_send_allowed_true")
        if heartbeat.get("kaspi_chat_write_allowed") is True:
            unsafe_blockers.append("heartbeat_kaspi_chat_write_allowed_true")
        for key in [
            "raw_order_id_exported",
            "raw_customer_text_exported",
            "raw_phone_exported",
            "raw_session_material_exported",
        ]:
            if heartbeat.get(key) is True:
                unsafe_blockers.append(f"heartbeat_{key}_true")

        if heartbeat.get("persistent_profile_mode") is not True:
            blockers.append("resident_not_using_persistent_profile")
        if heartbeat.get("browser_should_remain_open") is not True:
            blockers.append("resident_browser_should_remain_open_not_true")
        if heartbeat.get("orders_search_input_visible") is not True:
            blockers.append("orders_search_input_not_visible")
        safe_url = str(heartbeat.get("safe_current_url") or "").lower()
        if "idmc.shop.kaspi.kz/login" in safe_url or "merchant.kaspi.kz/new/account/entrance" in safe_url:
            blockers.append("resident_browser_at_login_route")

        commands_dir_value = heartbeat.get("commands_dir")
        commands_dir = Path(str(commands_dir_value)) if commands_dir_value else None
        pending_commands: list[str] = []
        if commands_dir and commands_dir.exists():
            pending_commands = sorted(
                path.name
                for path in commands_dir.glob("*.json")
                if not path.name.endswith(".done.json") and not path.name.endswith(".failed.json")
            )
        checks["pending_command_count"] = len(pending_commands)
        checks["pending_commands_redacted"] = pending_commands[:20]

    approval: dict[str, Any] = {}
    if live_send_approval_manifest:
        approval = _approval_summary(live_send_approval_manifest)

    gate = GREEN_GATE
    if unsafe_blockers:
        gate = RED_GATE
    elif blockers:
        gate = YELLOW_GATE

    next_action = (
        "reuse_resident_controller_queue_only_no_relaunch"
        if gate == GREEN_GATE
        else "repair_or_refresh_resident_session_without_customer_send"
    )
    if gate == GREEN_GATE and approval.get("approval_packet_ready_no_send"):
        next_action = "owner_may_review_exact_one_order_live_send_canary_phrase_no_send_yet"

    report = {
        "gate": gate,
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "blockers": blockers,
        "unsafe_blockers": unsafe_blockers,
        "checks": checks,
        "live_send_approval": approval,
        "next_action": next_action,
        "no_send_invariants": {
            "customer_send_allowed": False,
            "kaspi_chat_write_allowed": False,
            "chat_open_allowed": False,
            "message_text_typed": False,
            "message_sent": False,
            "raw_order_id_exported": False,
            "raw_customer_text_exported": False,
            "raw_phone_exported": False,
            "raw_session_material_exported": False,
        },
    }
    return report


def _build_closeout(report: dict[str, Any], manifest_path: Path) -> str:
    checks = report.get("checks") or {}
    approval = report.get("live_send_approval") or {}
    lines = [
        "# Kaspi Customer Chat Resident Session Reuse Report",
        "",
        f"Gate: {report['gate']}",
        "",
        "## Purpose",
        "",
        "Read-only status check for the already-authenticated resident Kaspi browser session. Future agents should run this before any customer-size browser work, and should not relaunch/close Playwright when this gate is GREEN.",
        "",
        "## Resident Session",
        "",
        f"- Heartbeat: `{checks.get('heartbeat_path')}`",
        f"- Recorded at: `{checks.get('recorded_at')}`",
        f"- Profile store: `{checks.get('profile_store_code')}`",
        f"- Persistent profile: `{checks.get('persistent_profile_dir_path')}`",
        f"- Browser should remain open: {str(checks.get('browser_should_remain_open')).lower()}",
        f"- Orders search visible: {str(checks.get('orders_search_input_visible')).lower()}",
        f"- Pending command count: {checks.get('pending_command_count', 0)}",
        "",
        "## Live Send Canary Packet",
        "",
        f"- Approval manifest: `{approval.get('manifest_path', '')}`",
        f"- Packet ready no-send: {str(approval.get('approval_packet_ready_no_send')).lower()}",
        f"- Approval phrase path: `{approval.get('approval_phrase_path', '')}`",
        "",
        "## Next Action",
        "",
        f"- `{report.get('next_action')}`",
        "",
        "## Safety",
        "",
        "- Customer send allowed: false",
        "- Kaspi chat write allowed: false",
        "- Chat open allowed by this report: false",
        "- Message typed/sent: false",
        "- Raw order IDs/customer text/phones/session material exported: false",
        "",
        "## Evidence",
        "",
        f"- Manifest: `{manifest_path}`",
        "",
    ]
    blockers = report.get("blockers") or []
    unsafe = report.get("unsafe_blockers") or []
    if blockers or unsafe:
        lines.extend(["## Blockers", ""])
        lines.extend(f"- {item}" for item in [*unsafe, *blockers])
        lines.append("")
    return "\n".join(lines)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--heartbeat", type=Path, default=DEFAULT_HEARTBEAT)
    parser.add_argument("--live-send-approval-manifest", type=Path, default=DEFAULT_LIVE_SEND_APPROVAL)
    parser.add_argument("--output-dir", type=Path, default=None)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    output_dir = (args.output_dir or _default_output_dir()).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = output_dir / "manifest.json"
    closeout_path = output_dir / "closeout.md"
    report = build_report(
        heartbeat_path=args.heartbeat.resolve(),
        live_send_approval_manifest=args.live_send_approval_manifest.resolve()
        if args.live_send_approval_manifest
        else None,
        output_dir=output_dir,
    )
    _write_json(manifest_path, report)
    closeout_path.write_text(_build_closeout(report, manifest_path), encoding="utf-8")
    print(json.dumps({"gate": report["gate"], "manifest_path": str(manifest_path), "closeout_path": str(closeout_path)}, ensure_ascii=False, indent=2, sort_keys=True))
    if report["gate"].startswith("RED_"):
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
