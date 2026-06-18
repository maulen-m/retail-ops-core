#!/usr/bin/env python3
"""Fail-closed enqueue of a priority no-send command into a live resident controller."""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_RUN_DIR = (
    PROJECT_ROOT
    / "exports"
    / "validation"
    / "kaspi_customer_chat_resident_no_send_controller_current"
)
DEFAULT_COMMAND = (
    PROJECT_ROOT
    / "exports"
    / "validation"
    / "kaspi_customer_size_priority_resident_no_send_command_20260618_current"
    / "command_queue"
    / "priority_top_001_ui_chat_button_no_open_36170.json"
)
DEFAULT_OUTPUT_DIR = (
    PROJECT_ROOT
    / "exports"
    / "validation"
    / f"kaspi_customer_size_priority_enqueue_readiness_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
)

GREEN_DRY_RUN_GATE = "GREEN_RESIDENT_READY_PRIORITY_COMMAND_NOT_ENQUEUED_DRY_RUN"
GREEN_ENQUEUED_GATE = "GREEN_PRIORITY_COMMAND_ENQUEUED_TO_RESIDENT_NO_SEND"
YELLOW_GATE = "YELLOW_PRIORITY_COMMAND_NOT_ENQUEUED_RESIDENT_NOT_READY"
MERCHANT_SELECTOR_MAP = {
    "UNIVERSAL": "30000001",
    "ACMEWEAR": "30137883",
    "STOREB": "30000002",
    "MELVIS": "30362323",
    "11KZ": "30290083",
}


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _parse_dt(value: str) -> datetime | None:
    value = str(value or "").strip()
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _age_seconds(as_of: datetime, recorded_at: datetime) -> float:
    if as_of.tzinfo is None and recorded_at.tzinfo is not None:
        recorded_at = recorded_at.replace(tzinfo=None)
    elif as_of.tzinfo is not None and recorded_at.tzinfo is None:
        as_of = as_of.replace(tzinfo=None)
    return (as_of - recorded_at).total_seconds()


def _find_resident_processes() -> list[str]:
    result = subprocess.run(
        ["pgrep", "-af", "[r]un_kaspi_customer_chat_resident_no_send_controller.py"],
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode not in (0, 1):
        return []
    return [line.strip() for line in result.stdout.splitlines() if line.strip()]


def _command_is_no_send(command: dict[str, Any]) -> bool:
    expected_false = (
        "customer_send_allowed",
        "kaspi_chat_write_allowed",
        "chat_open_allowed",
        "message_text_typed",
        "message_sent",
        "raw_order_id_exported",
        "raw_customer_text_exported",
        "raw_phone_exported",
        "raw_session_material_exported",
    )
    return all(command.get(key) is False for key in expected_false)


def evaluate_readiness(
    *,
    run_dir: Path,
    command_path: Path,
    heartbeat_max_age_seconds: int,
    as_of: datetime,
    skip_process_check: bool = False,
    process_lines: list[str] | None = None,
) -> dict[str, Any]:
    blockers: list[str] = []
    run_dir = run_dir.resolve()
    command_path = command_path.resolve()
    heartbeat_path = run_dir / "resident_controller_heartbeat.json"
    commands_dir = run_dir / "command_queue"
    command: dict[str, Any] = {}
    heartbeat: dict[str, Any] = {}

    if not command_path.exists():
        blockers.append("priority_command_path_missing")
    else:
        command = _read_json(command_path)
        if not _command_is_no_send(command):
            blockers.append("priority_command_not_no_send_safe")

    if not heartbeat_path.exists():
        blockers.append("resident_heartbeat_missing")
    else:
        heartbeat = _read_json(heartbeat_path)
        if heartbeat.get("gate") != "GREEN_KASPI_CUSTOMER_CHAT_RESIDENT_NO_SEND_CONTROLLER_READY":
            blockers.append("resident_heartbeat_gate_not_green")
        if heartbeat.get("browser_should_remain_open") is not True:
            blockers.append("resident_heartbeat_does_not_preserve_browser")
        if heartbeat.get("orders_search_input_visible") is not True:
            blockers.append("resident_orders_search_input_not_visible")
        recorded_at = _parse_dt(str(heartbeat.get("recorded_at") or ""))
        if recorded_at is None:
            blockers.append("resident_heartbeat_recorded_at_invalid")
        else:
            age_seconds = _age_seconds(as_of, recorded_at)
            if age_seconds < 0:
                blockers.append("resident_heartbeat_recorded_at_in_future")
            elif age_seconds > heartbeat_max_age_seconds:
                blockers.append("resident_heartbeat_stale")
        heartbeat_commands_dir = Path(str(heartbeat.get("commands_dir") or "")).resolve()
        if heartbeat_commands_dir != commands_dir:
            blockers.append("resident_heartbeat_commands_dir_mismatch")

    expected_store = str(command.get("profile_store_code") or command.get("stores") or "").strip().upper()
    heartbeat_store = str(heartbeat.get("profile_store_code") or "").strip().upper()
    if command and heartbeat and expected_store and heartbeat_store and expected_store != heartbeat_store:
        blockers.append("priority_command_store_mismatch_with_resident_profile")

    if not skip_process_check:
        process_lines = _find_resident_processes()
        if not process_lines:
            blockers.append("resident_controller_process_not_running")
    else:
        process_lines = process_lines or []

    return {
        "gate": YELLOW_GATE if blockers else GREEN_DRY_RUN_GATE,
        "blockers": blockers,
        "blockers_count": len(blockers),
        "run_dir": str(run_dir),
        "commands_dir": str(commands_dir),
        "heartbeat_path": str(heartbeat_path),
        "command_path": str(command_path),
        "command_id": command.get("command_id", ""),
        "command_action": command.get("action", ""),
        "command_profile_store_code": command.get("profile_store_code", ""),
        "command_stores": command.get("stores", ""),
        "expected_merchant_account_id": MERCHANT_SELECTOR_MAP.get(expected_store, ""),
        "command_target_db_row_ids": command.get("target_db_row_ids", ""),
        "command_target_order_refs": command.get("target_order_refs", ""),
        "resident_profile_store_code": heartbeat.get("profile_store_code", ""),
        "heartbeat_recorded_at": heartbeat.get("recorded_at", ""),
        "heartbeat_max_age_seconds": heartbeat_max_age_seconds,
        "process_check_skipped": skip_process_check,
        "resident_process_count": len(process_lines or []),
        "customer_send_allowed": False,
        "kaspi_chat_write_allowed": False,
        "chat_open_allowed": False,
        "message_text_typed": False,
        "message_sent": False,
        "raw_order_id_exported": False,
        "raw_customer_text_exported": False,
        "raw_phone_exported": False,
        "raw_session_material_exported": False,
    }


def _build_closeout(manifest: dict[str, Any], *, enqueued_path: str = "") -> str:
    lines = [
        "# Kaspi Customer Size Priority Enqueue Readiness",
        "",
        f"Gate: {manifest['gate']}",
        "",
        "## Result",
        "",
    ]
    if manifest["gate"] == GREEN_ENQUEUED_GATE:
        lines.append("The priority no-send command was enqueued into the live resident controller queue.")
    elif manifest["gate"] == GREEN_DRY_RUN_GATE:
        lines.append("The resident controller appears ready, but `--enqueue` was not provided, so no command was copied.")
    else:
        lines.append("The priority no-send command was not enqueued because the resident controller is not ready.")
    lines.extend(
        [
            "",
            "## Evidence",
            "",
            f"- Run dir: `{manifest['run_dir']}`",
            f"- Commands dir: `{manifest['commands_dir']}`",
            f"- Heartbeat path: `{manifest['heartbeat_path']}`",
            f"- Source command path: `{manifest['command_path']}`",
            f"- Enqueued command path: `{enqueued_path}`" if enqueued_path else "- Enqueued command path: not enqueued",
            f"- Command ID: `{manifest['command_id']}`",
            f"- Command action: `{manifest['command_action']}`",
            f"- Command store: `{manifest['command_profile_store_code'] or manifest['command_stores']}`",
            f"- Required merchant selector ID: `{manifest['expected_merchant_account_id']}`",
            f"- Resident store: `{manifest['resident_profile_store_code']}`",
            f"- Heartbeat recorded at: `{manifest['heartbeat_recorded_at']}`",
            f"- Resident process count: `{manifest['resident_process_count']}`",
            "",
            "## Blockers",
            "",
        ]
    )
    if manifest["blockers"]:
        lines.extend(f"- `{blocker}`" for blocker in manifest["blockers"])
    else:
        lines.append("- none")
    lines.extend(
        [
            "",
            "## Safety",
            "",
            "- Customer send allowed: false",
            "- Kaspi chat write allowed: false",
            "- Chat open allowed: false",
            "- Message typed: false",
            "- Message sent: false",
            "- Raw order/customer/session export allowed: false",
        ]
    )
    return "\n".join(lines) + "\n"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", type=Path, default=DEFAULT_RUN_DIR)
    parser.add_argument("--command-path", type=Path, default=DEFAULT_COMMAND)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--heartbeat-max-age-seconds", type=int, default=300)
    parser.add_argument("--as-of", help="ISO timestamp for deterministic tests/evidence.")
    parser.add_argument("--enqueue", action="store_true", help="Copy command into the resident command queue if ready.")
    parser.add_argument("--replace-existing", action="store_true", help="Replace an existing queued command with same ID.")
    parser.add_argument(
        "--skip-process-check",
        action="store_true",
        help="Test-only escape hatch; live use should require the resident controller process.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    as_of = _parse_dt(args.as_of or "") or datetime.now()
    output_dir = args.output_dir.resolve()
    manifest = evaluate_readiness(
        run_dir=args.run_dir,
        command_path=args.command_path,
        heartbeat_max_age_seconds=args.heartbeat_max_age_seconds,
        as_of=as_of,
        skip_process_check=bool(args.skip_process_check),
    )
    enqueued_path = ""
    if not manifest["blockers"] and args.enqueue:
        command = _read_json(args.command_path.resolve())
        command_id = str(command.get("command_id") or args.command_path.stem).strip()
        destination = Path(manifest["commands_dir"]) / f"{command_id}.json"
        if destination.exists() and not args.replace_existing:
            manifest["gate"] = YELLOW_GATE
            manifest["blockers"] = ["resident_command_already_queued"]
            manifest["blockers_count"] = 1
        else:
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(args.command_path.resolve(), destination)
            enqueued_path = str(destination)
            manifest["gate"] = GREEN_ENQUEUED_GATE
            manifest["enqueued_command_path"] = enqueued_path
    output_dir.mkdir(parents=True, exist_ok=True)
    _write_json(output_dir / "manifest.json", manifest)
    (output_dir / "closeout.md").write_text(_build_closeout(manifest, enqueued_path=enqueued_path), encoding="utf-8")
    print(json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if manifest["gate"].startswith("GREEN_") else 1


if __name__ == "__main__":
    raise SystemExit(main())
