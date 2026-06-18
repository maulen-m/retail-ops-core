#!/usr/bin/env python3
"""Build selector-scoped resident-controller no-send commands from priority targets.

This script does not enqueue commands into the live resident browser controller.
It only converts the early-send priority packet into one redacted command file
per target, with the exact merchant selector ID attached to each command.
"""
from __future__ import annotations

import argparse
import csv
import json
from datetime import date, datetime
from pathlib import Path
from typing import Any, Iterable, Mapping

from scripts.probe_kaspi_customer_chat_ui_search_identity_no_send import (  # noqa: E402
    merchant_account_id_for_store,
)


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_ACTION = "ui_chat_button_no_open"
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


def _default_output_dir() -> Path:
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return (
        REPO_ROOT
        / "exports"
        / "validation"
        / f"kaspi_customer_chat_resident_no_send_command_packet_{stamp}"
    )


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    fieldnames: list[str] = []
    for row in rows:
        for key in row:
            if key not in fieldnames:
                fieldnames.append(key)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(
                {
                    key: json.dumps(value, ensure_ascii=False)
                    if isinstance(value, (dict, list))
                    else value
                    for key, value in row.items()
                }
            )


def _safe_token(value: Any, *, fallback: str = "unknown") -> str:
    text = str(value or "").strip().lower()
    if not text:
        return fallback
    result = []
    for char in text:
        if char.isalnum():
            result.append(char)
        elif char in {"_", "-"}:
            result.append(char)
        else:
            result.append("_")
    return "".join(result).strip("_") or fallback


def _command_id(row: Mapping[str, Any], *, action: str) -> str:
    sequence = str(row.get("sequence") or "x").zfill(3)
    store = _safe_token(row.get("store_code"), fallback="store")
    db_row_id = _safe_token(row.get("db_row_id"), fallback="row")
    return f"priority_{sequence}_{store}_{db_row_id}_{_safe_token(action)}"


def _target_status(row: Mapping[str, Any]) -> str:
    status = str(row.get("suggested_merchant_status_filter") or "").strip()
    return status if status and status != "UNKNOWN" else "NEW"


def _expected_merchant_id(row: Mapping[str, Any]) -> str:
    supplied = str(row.get("expected_merchant_account_id") or "").strip()
    if supplied:
        return supplied
    return merchant_account_id_for_store(str(row.get("store_code") or ""))


def build_command_from_priority_row(
    row: Mapping[str, Any],
    *,
    action: str,
    target_date: str,
    timeout_ms: int,
    output_root: Path,
) -> tuple[dict[str, Any], list[str]]:
    blockers: list[str] = []
    store_code = str(row.get("store_code") or "").strip().upper()
    expected_merchant_id = _expected_merchant_id(row)
    if not store_code:
        blockers.append("store_code_missing")
    if not expected_merchant_id:
        blockers.append("expected_merchant_account_id_missing")
    if not row.get("order_ref"):
        blockers.append("order_ref_missing")
    if not row.get("db_row_id"):
        blockers.append("db_row_id_missing")

    command_id = _command_id(row, action=action)
    command = {
        "command_id": command_id,
        "action": action,
        "queued_at": datetime.now().isoformat(timespec="seconds"),
        "target_date": target_date,
        "lookback_days": 5,
        "stores": store_code,
        "profile_store_code": store_code,
        "max_candidates": 1,
        "candidate_pool_limit": 30,
        "extra_status_filters": _target_status(row),
        "target_db_row_ids": str(row.get("db_row_id") or "").strip(),
        "target_order_refs": str(row.get("order_ref") or "").strip(),
        "timeout_ms": int(timeout_ms),
        "output_dir": str(output_root / "expected_command_output" / command_id),
        "expected_merchant_account_id": expected_merchant_id,
        "expected_merchant_selector_text": f"ID - {expected_merchant_id}" if expected_merchant_id else "",
        "requires_matching_merchant_account": True,
        "source_priority_sequence": row.get("sequence"),
        "source_priority_band": row.get("priority_band"),
        "source_priority_score": row.get("priority_score"),
        "source_ledger_status": row.get("ledger_status"),
        "source_template_hash": row.get("template_hash"),
        "store_scoped_selector_map_applied": True,
    }
    for flag in NO_SEND_FALSE_FLAGS:
        command[flag] = False
    return command, blockers


def build_packet(
    *,
    priority_rows: Iterable[Mapping[str, Any]],
    action: str,
    target_date: str,
    output_dir: Path,
    max_targets: int | None,
    timeout_ms: int,
) -> dict[str, Any]:
    output_dir = output_dir.resolve()
    commands_dir = output_dir / "command_queue"
    command_rows: list[dict[str, Any]] = []
    blockers: list[str] = []

    rows = list(priority_rows)
    if max_targets is not None:
        rows = rows[: max(0, int(max_targets))]

    for row in rows:
        command, row_blockers = build_command_from_priority_row(
            row,
            action=action,
            target_date=target_date,
            timeout_ms=timeout_ms,
            output_root=output_dir,
        )
        blockers.extend(row_blockers)
        command_path = commands_dir / f"{command['command_id']}.json"
        _write_json(command_path, command)
        command_rows.append(
            {
                "sequence": command.get("source_priority_sequence"),
                "command_id": command["command_id"],
                "command_path": str(command_path),
                "store_code": command["stores"],
                "expected_merchant_account_id": command["expected_merchant_account_id"],
                "expected_merchant_selector_text": command["expected_merchant_selector_text"],
                "target_order_refs": command["target_order_refs"],
                "target_db_row_ids": command["target_db_row_ids"],
                "action": command["action"],
                "requires_matching_merchant_account": True,
                "customer_send_allowed": False,
                "kaspi_chat_write_allowed": False,
                "message_sent": False,
                "raw_order_id_exported": False,
            }
        )

    command_text = json.dumps(command_rows, ensure_ascii=False, sort_keys=True)
    for row in rows:
        if str(row.get("raw_order_id") or "").strip() and str(row.get("raw_order_id")) in command_text:
            blockers.append("raw_order_id_value_detected")
            break

    gate = (
        "GREEN_RESIDENT_NO_SEND_COMMAND_PACKET_READY"
        if command_rows and not blockers
        else "YELLOW_RESIDENT_NO_SEND_COMMAND_PACKET_BLOCKED"
        if blockers
        else "YELLOW_RESIDENT_NO_SEND_COMMAND_PACKET_NO_TARGETS"
    )
    manifest = {
        "gate": gate,
        "run_at": datetime.now().isoformat(timespec="seconds"),
        "output_dir": str(output_dir),
        "commands_dir": str(commands_dir),
        "target_date": target_date,
        "action": action,
        "command_count": len(command_rows),
        "max_targets": max_targets,
        "command_index_path": str(output_dir / "command_index_redacted.json"),
        "blockers": sorted(set(blockers)),
        "blockers_count": len(set(blockers)),
        "customer_send_allowed": False,
        "kaspi_chat_write_allowed": False,
        "chat_open_allowed": False,
        "message_text_typed": False,
        "message_sent": False,
        "raw_order_id_exported": False,
        "raw_customer_text_exported": False,
        "raw_phone_exported": False,
        "raw_session_material_exported": False,
        "requires_matching_merchant_account": True,
    }
    _write_json(output_dir / "command_index_redacted.json", command_rows)
    _write_csv(output_dir / "command_index_redacted.csv", command_rows)
    _write_json(output_dir / "manifest.json", manifest)
    (output_dir / "closeout.md").write_text(_render_closeout(manifest), encoding="utf-8")
    return manifest


def _render_closeout(manifest: Mapping[str, Any]) -> str:
    return "\n".join(
        [
            "# Kaspi Customer Chat Resident No-Send Command Packet",
            "",
            f"Gate: {manifest['gate']}",
            "",
            f"- Output folder: `{manifest['output_dir']}`",
            f"- Commands dir: `{manifest['commands_dir']}`",
            f"- Command count: `{manifest['command_count']}`",
            f"- Action: `{manifest['action']}`",
            f"- Blockers: `{manifest['blockers_count']}`",
            "",
            "Each command is store-scoped and carries the expected Kaspi merchant",
            "selector ID. The packet is not enqueued into the resident browser",
            "controller and no customer message is sent.",
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
        ]
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--priority-targets", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, default=None)
    parser.add_argument("--target-date", default=date.today().isoformat())
    parser.add_argument(
        "--action",
        choices=("ui_search_identity_no_send", "ui_chat_button_no_open", "metadata_capture_no_send"),
        default=DEFAULT_ACTION,
    )
    parser.add_argument("--max-targets", type=int)
    parser.add_argument("--timeout-ms", type=int, default=30000)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    priority_rows = _read_json(args.priority_targets.resolve())
    if not isinstance(priority_rows, list):
        raise SystemExit("--priority-targets must point to a JSON list")
    output_dir = args.output_dir or _default_output_dir()
    manifest = build_packet(
        priority_rows=priority_rows,
        action=args.action,
        target_date=args.target_date,
        output_dir=output_dir,
        max_targets=args.max_targets,
        timeout_ms=args.timeout_ms,
    )
    print(json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if str(manifest.get("gate") or "").startswith("GREEN_") else 1


if __name__ == "__main__":
    raise SystemExit(main())
