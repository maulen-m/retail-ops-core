#!/usr/bin/env python3
"""Safely enqueue selector-scoped no-send command packets to a resident controller.

This script only copies prebuilt no-send command JSON files into the resident
controller command queue. It refuses cross-store commands by default and never
creates customer-send commands.
"""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable, Mapping

from scripts.probe_kaspi_customer_chat_ui_search_identity_no_send import (  # noqa: E402
    merchant_account_id_for_store,
)


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_RUN_DIR = (
    REPO_ROOT
    / "exports"
    / "validation"
    / "kaspi_customer_chat_resident_no_send_controller_current"
)
DEFAULT_PACKET_DIR = (
    REPO_ROOT
    / "exports"
    / "validation"
    / "kaspi_customer_chat_resident_no_send_command_packet_20260618_current"
)
NO_SEND_ACTIONS = {
    "ui_search_identity_no_send",
    "ui_chat_button_no_open",
    "metadata_capture_no_send",
}
NO_SEND_FALSE_FLAGS = (
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
GREEN_DRY_RUN_GATE = "GREEN_RESIDENT_NO_SEND_COMMAND_PACKET_ENQUEUE_READY_DRY_RUN"
GREEN_ENQUEUED_GATE = "GREEN_RESIDENT_NO_SEND_COMMAND_PACKET_ENQUEUED"
YELLOW_GATE = "YELLOW_RESIDENT_NO_SEND_COMMAND_PACKET_NOT_ENQUEUED"
RED_GATE = "RED_RESIDENT_NO_SEND_COMMAND_PACKET_UNSAFE"


def _default_output_dir() -> Path:
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return (
        REPO_ROOT
        / "exports"
        / "validation"
        / f"kaspi_customer_chat_resident_no_send_packet_enqueue_{stamp}"
    )


def _read_json(path: Path) -> dict[str, Any] | list[Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _parse_dt(value: Any) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00"))
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


def _command_is_no_send(command: Mapping[str, Any]) -> bool:
    if str(command.get("action") or "") not in NO_SEND_ACTIONS:
        return False
    return all(command.get(flag) is False for flag in NO_SEND_FALSE_FLAGS)


def _command_store(command: Mapping[str, Any]) -> str:
    return str(command.get("profile_store_code") or command.get("stores") or "").strip().upper()


def _load_command_rows(packet_dir: Path) -> list[dict[str, Any]]:
    index_path = packet_dir / "command_index_redacted.json"
    rows = _read_json(index_path)
    if not isinstance(rows, list):
        raise ValueError(f"Expected list at {index_path}")
    return [dict(row) for row in rows]


def _candidate_commands(
    *,
    packet_dir: Path,
    rows: Iterable[Mapping[str, Any]],
    store: str,
    max_commands: int | None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[str]]:
    selected: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    unsafe: list[str] = []
    for row in rows:
        command_path = Path(str(row.get("command_path") or ""))
        if not command_path.is_absolute():
            command_path = packet_dir / command_path
        if not command_path.exists():
            unsafe.append("command_path_missing")
            skipped.append({**dict(row), "reason": "command_path_missing"})
            continue
        command = _read_json(command_path)
        if not isinstance(command, dict):
            unsafe.append("command_not_json_object")
            skipped.append({**dict(row), "reason": "command_not_json_object"})
            continue
        command_store = _command_store(command)
        if store and command_store != store:
            skipped.append({**dict(row), "reason": "store_does_not_match_resident"})
            continue
        expected_id = str(command.get("expected_merchant_account_id") or "").strip()
        if expected_id != merchant_account_id_for_store(command_store):
            unsafe.append("command_expected_merchant_account_id_mismatch")
            skipped.append({**dict(row), "reason": "expected_merchant_account_id_mismatch"})
            continue
        if not _command_is_no_send(command):
            unsafe.append("command_not_no_send_safe")
            skipped.append({**dict(row), "reason": "command_not_no_send_safe"})
            continue
        selected.append(
            {
                **dict(row),
                "command_path": str(command_path),
                "command_id": str(command.get("command_id") or row.get("command_id") or command_path.stem),
                "store_code": command_store,
                "expected_merchant_account_id": expected_id,
            }
        )
        if max_commands is not None and len(selected) >= max(0, int(max_commands)):
            break
    return selected, skipped, sorted(set(unsafe))


def evaluate_packet_enqueue_readiness(
    *,
    run_dir: Path,
    packet_dir: Path,
    heartbeat_max_age_seconds: int,
    as_of: datetime,
    store: str | None = None,
    max_commands: int | None = None,
    allow_stale_idle_heartbeat_if_process_running: bool = False,
    allow_selector_switch_across_store: bool = False,
    allow_resident_page_recovery_if_process_running: bool = False,
    skip_process_check: bool = False,
    process_lines: list[str] | None = None,
) -> dict[str, Any]:
    blockers: list[str] = []
    unsafe: list[str] = []
    run_dir = run_dir.resolve()
    packet_dir = packet_dir.resolve()
    commands_dir = run_dir / "command_queue"
    heartbeat_path = run_dir / "resident_controller_heartbeat.json"
    heartbeat: dict[str, Any] = {}

    if not heartbeat_path.exists():
        blockers.append("resident_heartbeat_missing")
    else:
        loaded_heartbeat = _read_json(heartbeat_path)
        heartbeat = loaded_heartbeat if isinstance(loaded_heartbeat, dict) else {}
        if heartbeat.get("gate") != "GREEN_KASPI_CUSTOMER_CHAT_RESIDENT_NO_SEND_CONTROLLER_READY":
            blockers.append("resident_heartbeat_gate_not_green")
        if heartbeat.get("browser_should_remain_open") is not True:
            blockers.append("resident_heartbeat_does_not_preserve_browser")
        if heartbeat.get("orders_search_input_visible") is not True:
            blockers.append("resident_orders_search_input_not_visible")
        for flag in ("message_sent", "message_text_typed", "kaspi_chat_write_allowed", "customer_send_allowed"):
            if heartbeat.get(flag) is True:
                unsafe.append(f"resident_heartbeat_{flag}_true")
        recorded_at = _parse_dt(heartbeat.get("recorded_at"))
        if recorded_at is None:
            blockers.append("resident_heartbeat_recorded_at_invalid")
        else:
            age = _age_seconds(as_of, recorded_at)
            if age < 0:
                blockers.append("resident_heartbeat_recorded_at_in_future")
            elif age > heartbeat_max_age_seconds:
                blockers.append("resident_heartbeat_stale")
        if Path(str(heartbeat.get("commands_dir") or "")).resolve() != commands_dir:
            blockers.append("resident_heartbeat_commands_dir_mismatch")

    if not skip_process_check:
        process_lines = _find_resident_processes()
        if not process_lines:
            blockers.append("resident_controller_process_not_running")
    else:
        process_lines = process_lines or []

    resident_store = str(heartbeat.get("profile_store_code") or "").strip().upper()
    requested_store = str(store or resident_store or "").strip().upper()
    if not requested_store:
        blockers.append("resident_or_requested_store_missing")
    if resident_store and requested_store and resident_store != requested_store:
        if not (allow_selector_switch_across_store and process_lines):
            unsafe.append("requested_store_does_not_match_resident_profile")

    rows: list[dict[str, Any]] = []
    selected: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    if not packet_dir.exists():
        blockers.append("packet_dir_missing")
    else:
        try:
            rows = _load_command_rows(packet_dir)
            selected, skipped, command_unsafe = _candidate_commands(
                packet_dir=packet_dir,
                rows=rows,
                store=requested_store,
                max_commands=max_commands,
            )
            unsafe.extend(command_unsafe)
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            blockers.append(f"packet_read_failed:{type(exc).__name__}")

    stale_allowed = False
    if "resident_heartbeat_stale" in blockers and allow_stale_idle_heartbeat_if_process_running and process_lines:
        blockers.remove("resident_heartbeat_stale")
        stale_allowed = True

    page_recovery_allowed = False
    recoverable_page_blockers = {
        "resident_heartbeat_gate_not_green",
        "resident_orders_search_input_not_visible",
    }
    if (
        (allow_selector_switch_across_store or allow_resident_page_recovery_if_process_running)
        and process_lines
        and set(blockers).issubset(recoverable_page_blockers)
    ):
        blockers = []
        page_recovery_allowed = True

    if rows and not selected and not unsafe:
        blockers.append("no_matching_no_send_commands_for_resident_store")

    gate = RED_GATE if unsafe else YELLOW_GATE if blockers else GREEN_DRY_RUN_GATE
    return {
        "gate": gate,
        "run_at": datetime.now().isoformat(timespec="seconds"),
        "run_dir": str(run_dir),
        "packet_dir": str(packet_dir),
        "commands_dir": str(commands_dir),
        "heartbeat_path": str(heartbeat_path),
        "heartbeat_recorded_at": heartbeat.get("recorded_at", ""),
        "heartbeat_max_age_seconds": heartbeat_max_age_seconds,
        "heartbeat_stale_allowed_because_idle_process_running": stale_allowed,
        "selector_switch_across_store_allowed": bool(
            allow_selector_switch_across_store
            and resident_store
            and requested_store
            and resident_store != requested_store
        ),
        "resident_page_recovery_allowed_because_process_running": page_recovery_allowed,
        "resident_page_recovery_explicitly_allowed": bool(
            allow_resident_page_recovery_if_process_running
        ),
        "resident_profile_store_code": resident_store,
        "requested_store": requested_store,
        "expected_merchant_account_id": merchant_account_id_for_store(requested_store),
        "packet_command_count": len(rows),
        "selected_command_count": len(selected),
        "skipped_command_count": len(skipped),
        "selected_commands_redacted": selected,
        "skipped_commands_redacted": skipped,
        "process_check_skipped": skip_process_check,
        "resident_process_count": len(process_lines or []),
        "blockers": sorted(set(blockers)),
        "unsafe_blockers": sorted(set(unsafe)),
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


def _render_closeout(manifest: Mapping[str, Any]) -> str:
    lines = [
        "# Kaspi Customer Chat Resident No-Send Packet Enqueue",
        "",
        f"Gate: {manifest['gate']}",
        "",
        f"- Packet dir: `{manifest['packet_dir']}`",
        f"- Resident run dir: `{manifest['run_dir']}`",
        f"- Commands dir: `{manifest['commands_dir']}`",
        f"- Resident store: `{manifest['resident_profile_store_code']}`",
        f"- Requested store: `{manifest['requested_store']}`",
        f"- Selected command count: `{manifest['selected_command_count']}`",
        f"- Enqueued command count: `{manifest.get('enqueued_command_count', 0)}`",
        f"- Stale idle heartbeat allowed: `{str(manifest['heartbeat_stale_allowed_because_idle_process_running']).lower()}`",
        f"- Selector switch across store allowed: `{str(manifest.get('selector_switch_across_store_allowed', False)).lower()}`",
        f"- Resident page recovery allowed: `{str(manifest.get('resident_page_recovery_allowed_because_process_running', False)).lower()}`",
        "",
        "## Safety",
        "",
        "- Customer send allowed: false",
        "- Kaspi chat write allowed: false",
        "- Chat open allowed: false",
        "- Message text typed: false",
        "- Message sent: false",
        "- Raw order/customer/phone/session export allowed: false",
        "",
        "## Blockers",
        "",
    ]
    blockers = [*(manifest.get("unsafe_blockers") or []), *(manifest.get("blockers") or [])]
    lines.extend(f"- `{blocker}`" for blocker in blockers or ["none"])
    return "\n".join(lines) + "\n"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", type=Path, default=DEFAULT_RUN_DIR)
    parser.add_argument("--packet-dir", type=Path, default=DEFAULT_PACKET_DIR)
    parser.add_argument("--output-dir", type=Path, default=None)
    parser.add_argument("--store", help="Store to enqueue. Defaults to resident heartbeat profile store.")
    parser.add_argument("--max-commands", type=int)
    parser.add_argument("--heartbeat-max-age-seconds", type=int, default=300)
    parser.add_argument("--as-of", help="ISO timestamp for deterministic evidence.")
    parser.add_argument("--enqueue", action="store_true")
    parser.add_argument("--replace-existing", action="store_true")
    parser.add_argument(
        "--allow-stale-idle-heartbeat-if-process-running",
        action="store_true",
        help="Allow stale heartbeat only when the resident process is still running and all no-send safety flags are clean.",
    )
    parser.add_argument(
        "--allow-selector-switch-across-store",
        action="store_true",
        help=(
            "Allow selected no-send commands for a different store to be queued "
            "into the resident session only when the process is alive and the "
            "command carries the correct store merchant-account selector ID."
        ),
    )
    parser.add_argument(
        "--allow-resident-page-recovery-if-process-running",
        action="store_true",
        help=(
            "Allow no-send command enqueue when the resident process is alive "
            "but the heartbeat is yellow only because it is on a recoverable "
            "detail page without the order-list search input visible."
        ),
    )
    parser.add_argument("--skip-process-check", action="store_true", help="Test-only escape hatch.")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    as_of = _parse_dt(args.as_of) or datetime.now()
    output_dir = (args.output_dir or _default_output_dir()).resolve()
    manifest = evaluate_packet_enqueue_readiness(
        run_dir=args.run_dir,
        packet_dir=args.packet_dir,
        heartbeat_max_age_seconds=int(args.heartbeat_max_age_seconds),
        as_of=as_of,
        store=args.store,
        max_commands=args.max_commands,
        allow_stale_idle_heartbeat_if_process_running=bool(
            args.allow_stale_idle_heartbeat_if_process_running
        ),
        allow_selector_switch_across_store=bool(args.allow_selector_switch_across_store),
        allow_resident_page_recovery_if_process_running=bool(
            args.allow_resident_page_recovery_if_process_running
        ),
        skip_process_check=bool(args.skip_process_check),
    )

    enqueued: list[dict[str, Any]] = []
    if manifest["gate"] == GREEN_DRY_RUN_GATE and args.enqueue:
        for row in manifest["selected_commands_redacted"]:
            source = Path(str(row["command_path"])).resolve()
            destination = Path(str(manifest["commands_dir"])) / source.name
            if destination.exists() and not args.replace_existing:
                manifest["gate"] = YELLOW_GATE
                manifest["blockers"] = ["resident_command_already_queued"]
                break
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, destination)
            enqueued.append({**row, "enqueued_command_path": str(destination)})
        if manifest["gate"] == GREEN_DRY_RUN_GATE:
            manifest["gate"] = GREEN_ENQUEUED_GATE

    manifest["apply_requested"] = bool(args.enqueue)
    manifest["enqueued_command_count"] = len(enqueued)
    manifest["enqueued_commands_redacted"] = enqueued
    output_dir.mkdir(parents=True, exist_ok=True)
    _write_json(output_dir / "manifest.json", manifest)
    (output_dir / "closeout.md").write_text(_render_closeout(manifest), encoding="utf-8")
    print(json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if str(manifest.get("gate") or "").startswith("GREEN_") else 1


if __name__ == "__main__":
    raise SystemExit(main())
