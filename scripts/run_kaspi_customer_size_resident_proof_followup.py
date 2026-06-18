#!/usr/bin/env python3
"""Watch a resident no-send proof and build the one-order approval packet."""

from __future__ import annotations

import argparse
import json
import time
from datetime import datetime
from pathlib import Path
from typing import Any

from scripts.build_kaspi_customer_chat_live_send_canary_approval_packet import (
    main as approval_packet_main,
)
from scripts.build_kaspi_customer_chat_live_send_canary_execution_handoff import (
    main as execution_handoff_main,
)


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_RESIDENT_MANIFEST = (
    REPO_ROOT
    / "exports"
    / "validation"
    / "kaspi_customer_chat_resident_no_send_controller_current"
    / "commands"
    / "priority_top_001_ui_chat_button_no_open_36170"
    / "manifest.json"
)
DEFAULT_OUTPUT_DIR = (
    REPO_ROOT
    / "exports"
    / "validation"
    / f"kaspi_customer_size_resident_proof_followup_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
)
EXPECTED_RESIDENT_GATE = "GREEN_KASPI_CUSTOMER_CHAT_MESSAGE_BUTTON_PROVEN_NO_SEND"
GREEN_GATE = "GREEN_RESIDENT_PROOF_FOLLOWUP_APPROVAL_READY_NO_SEND"
YELLOW_GATE = "YELLOW_RESIDENT_PROOF_FOLLOWUP_WAITING_OR_BLOCKED_NO_SEND"
RED_GATE = "RED_RESIDENT_PROOF_FOLLOWUP_UNSAFE_NO_SEND"


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _safe_bool(value: Any) -> bool:
    return bool(value)


def _matching_result(
    manifest: dict[str, Any],
    *,
    expected_order_ref: str,
    expected_db_row_id: str,
) -> dict[str, Any] | None:
    for row in manifest.get("results") or []:
        if not isinstance(row, dict):
            continue
        if expected_order_ref and str(row.get("order_ref") or "") != expected_order_ref:
            continue
        if expected_db_row_id and str(row.get("db_row_id") or "") != expected_db_row_id:
            continue
        if (
            row.get("merchant_account_match_proven") is True
            and row.get("chat_button_present") is True
            and row.get("result_or_detail_reached") is True
            and row.get("chat_opened") is not True
            and row.get("message_text_typed") is not True
            and row.get("message_sent") is not True
            and row.get("raw_order_id_exported") is not True
            and row.get("raw_customer_text_exported") is not True
        ):
            return row
    return None


def evaluate_resident_manifest(
    manifest_path: Path,
    *,
    expected_order_ref: str,
    expected_db_row_id: str,
) -> dict[str, Any]:
    blockers: list[str] = []
    unsafe_blockers: list[str] = []
    checks: dict[str, Any] = {
        "resident_manifest_path": str(manifest_path),
        "resident_manifest_exists": manifest_path.exists(),
    }
    manifest: dict[str, Any] = {}
    selected: dict[str, Any] | None = None
    if not manifest_path.exists():
        blockers.append("resident_button_manifest_missing")
    else:
        manifest = _read_json(manifest_path)
        checks["resident_gate"] = manifest.get("gate")
        checks["target_date"] = manifest.get("target_date")
        checks["profile_store_code"] = manifest.get("profile_store_code")
        checks["unsafe_event_count"] = int(manifest.get("unsafe_event_count") or 0)
        if manifest.get("gate") != EXPECTED_RESIDENT_GATE:
            blockers.append("resident_button_manifest_not_green")
        if int(manifest.get("unsafe_event_count") or 0) != 0:
            unsafe_blockers.append("resident_button_manifest_has_unsafe_events")
        for key in (
            "customer_send_allowed",
            "kaspi_chat_write_allowed",
            "chat_opened",
            "message_text_typed",
            "message_sent",
            "raw_order_id_exported",
            "raw_customer_text_exported",
            "raw_phone_exported",
            "raw_session_material_exported",
        ):
            if manifest.get(key) is True:
                unsafe_blockers.append(f"resident_button_manifest_{key}_true")
        selected = _matching_result(
            manifest,
            expected_order_ref=expected_order_ref,
            expected_db_row_id=expected_db_row_id,
        )
        if selected is None:
            blockers.append("resident_button_manifest_current_priority_target_not_proven")
    return {
        "resident_manifest": manifest,
        "selected_result": selected or {},
        "checks": checks,
        "blockers": blockers,
        "unsafe_blockers": unsafe_blockers,
        "ready": not blockers and not unsafe_blockers,
    }


def _wait_for_manifest(
    manifest_path: Path,
    *,
    timeout_seconds: float,
    poll_seconds: float,
    expected_order_ref: str,
    expected_db_row_id: str,
) -> dict[str, Any]:
    deadline = time.time() + max(timeout_seconds, 0.0)
    last = evaluate_resident_manifest(
        manifest_path,
        expected_order_ref=expected_order_ref,
        expected_db_row_id=expected_db_row_id,
    )
    while not last["ready"] and time.time() < deadline:
        time.sleep(max(poll_seconds, 0.1))
        last = evaluate_resident_manifest(
            manifest_path,
            expected_order_ref=expected_order_ref,
            expected_db_row_id=expected_db_row_id,
        )
    return last


def _build_closeout(manifest: dict[str, Any]) -> str:
    lines = [
        "# Kaspi Customer Size Resident Proof Follow-Up",
        "",
        f"Gate: {manifest['gate']}",
        "",
        "## Result",
        "",
    ]
    if manifest["gate"] == GREEN_GATE:
        lines.append("The current priority resident no-send proof is GREEN, and the exact live-send approval packet plus execution handoff were generated.")
    elif manifest["gate"] == RED_GATE:
        lines.append("The resident proof follow-up stopped because unsafe proof flags were present.")
    else:
        lines.append("The resident proof follow-up did not generate approval because the current priority proof is not GREEN yet.")
    lines.extend(
        [
            "",
            "## Evidence",
            "",
            f"- Resident manifest: `{manifest['resident_manifest_path']}`",
            f"- Expected order ref: `{manifest['expected_order_ref']}`",
            f"- Expected DB row ID: `{manifest['expected_db_row_id']}`",
            f"- Approval dir: `{manifest.get('approval_dir', '')}`",
            f"- Execution handoff dir: `{manifest.get('execution_handoff_dir', '')}`",
            "",
            "## Blockers",
            "",
        ]
    )
    blockers = [*manifest.get("unsafe_blockers", []), *manifest.get("blockers", [])]
    if blockers:
        lines.extend(f"- `{blocker}`" for blocker in blockers)
    else:
        lines.append("- none")
    lines.extend(
        [
            "",
            "## Safety",
            "",
            "- Customer send allowed: false",
            "- Kaspi chat write allowed: false",
            "- Chat open allowed by this follow-up: false",
            "- Message typed: false",
            "- Message sent: false",
            "- Google Board write allowed: false",
            "- Telegram send allowed: false",
            "- Raw order/customer/session export allowed: false",
            "",
        ]
    )
    return "\n".join(lines)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--resident-button-manifest", type=Path, default=DEFAULT_RESIDENT_MANIFEST)
    parser.add_argument("--expected-order-ref", default="sha256:3a507903190c4097e2d211ee")
    parser.add_argument("--expected-db-row-id", default="36170")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--timeout-seconds", type=float, default=0.0)
    parser.add_argument("--poll-seconds", type=float, default=2.0)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    output_dir = args.output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    resident_manifest_path = args.resident_button_manifest.resolve()
    evaluation = _wait_for_manifest(
        resident_manifest_path,
        timeout_seconds=float(args.timeout_seconds),
        poll_seconds=float(args.poll_seconds),
        expected_order_ref=str(args.expected_order_ref),
        expected_db_row_id=str(args.expected_db_row_id),
    )

    approval_dir = output_dir / "live_send_approval"
    handoff_dir = approval_dir / "live_send_execution_handoff"
    gate = YELLOW_GATE
    approval_gate = ""
    execution_handoff_gate = ""
    if evaluation["unsafe_blockers"]:
        gate = RED_GATE
    elif evaluation["ready"]:
        approval_packet_main(
            [
                "--resident-button-manifest",
                str(resident_manifest_path),
                "--output-dir",
                str(approval_dir),
            ]
        )
        execution_handoff_main(
            [
                "--approval-dir",
                str(approval_dir),
                "--output-dir",
                str(handoff_dir),
            ]
        )
        approval_manifest_path = approval_dir / "manifest.json"
        handoff_manifest_path = handoff_dir / "manifest.json"
        approval_gate = _read_json(approval_manifest_path).get("gate", "") if approval_manifest_path.exists() else ""
        execution_handoff_gate = _read_json(handoff_manifest_path).get("gate", "") if handoff_manifest_path.exists() else ""
        if (
            approval_gate == "GREEN_LIVE_SEND_CANARY_APPROVAL_PACKET_READY_NO_SEND"
            and execution_handoff_gate == "GREEN_LIVE_SEND_EXECUTION_HANDOFF_READY_NO_SEND_PERFORMED"
        ):
            gate = GREEN_GATE
        else:
            gate = YELLOW_GATE
            evaluation["blockers"].append("approval_or_execution_handoff_not_green")

    manifest = {
        "gate": gate,
        "run_at": datetime.now().isoformat(timespec="seconds"),
        "resident_manifest_path": str(resident_manifest_path),
        "expected_order_ref": str(args.expected_order_ref),
        "expected_db_row_id": str(args.expected_db_row_id),
        "output_dir": str(output_dir),
        "approval_dir": str(approval_dir) if approval_gate else "",
        "execution_handoff_dir": str(handoff_dir) if execution_handoff_gate else "",
        "approval_gate": approval_gate,
        "execution_handoff_gate": execution_handoff_gate,
        "checks": evaluation["checks"],
        "selected_result": evaluation["selected_result"],
        "blockers": evaluation["blockers"],
        "unsafe_blockers": evaluation["unsafe_blockers"],
        "customer_send_allowed": False,
        "kaspi_chat_write_allowed": False,
        "chat_open_allowed": False,
        "message_text_typed": False,
        "message_sent": False,
        "google_board_write_allowed": False,
        "telegram_send_allowed": False,
        "raw_order_id_exported": False,
        "raw_customer_text_exported": False,
        "raw_phone_exported": False,
        "raw_session_material_exported": False,
    }
    _write_json(output_dir / "manifest.json", manifest)
    (output_dir / "closeout.md").write_text(_build_closeout(manifest), encoding="utf-8")
    print(json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True))
    if gate == GREEN_GATE:
        return 0
    if gate == RED_GATE:
        return 2
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
