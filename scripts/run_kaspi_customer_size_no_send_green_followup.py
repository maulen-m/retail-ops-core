#!/usr/bin/env python3
"""Run no-write follow-up after Kaspi customer-chat no-send proof turns GREEN."""
from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path
from typing import Any

from scripts.build_kaspi_customer_chat_live_send_canary_approval_packet import (
    main as live_send_approval_main,
)
from scripts.build_kaspi_customer_chat_live_send_canary_execution_handoff import (
    main as live_send_execution_handoff_main,
)
from scripts.build_kaspi_customer_size_automation_options_matrix import (
    main as automation_options_matrix_main,
)
from scripts.build_kaspi_customer_size_owner_dashboard import main as owner_dashboard_main
from scripts.build_kaspi_customer_size_workflow_readiness_packet import (
    main as workflow_readiness_main,
)
from scripts.validate_kaspi_customer_chat_live_canary_result import (
    DEFAULT_PACKET_DIR,
    main as validate_no_send_main,
)


REPO_ROOT = Path(__file__).resolve().parents[1]


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _latest(pattern: str) -> Path | None:
    matches = [path for path in REPO_ROOT.glob(pattern) if path.is_file()]
    if not matches:
        return None
    return max(matches, key=lambda path: path.stat().st_mtime)


def _default_output_root() -> Path:
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return (
        REPO_ROOT
        / "exports"
        / "validation"
        / f"kaspi_customer_size_no_send_green_followup_{stamp}"
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--packet-dir", type=Path, default=DEFAULT_PACKET_DIR)
    parser.add_argument("--db", type=Path)
    parser.add_argument("--ledger-db", type=Path)
    parser.add_argument("--output-root", type=Path)
    parser.add_argument("--chrome-reconnect-manifest", type=Path)
    parser.add_argument("--google-board-patch-manifest", type=Path)
    parser.add_argument("--cadence-manifest", type=Path)
    parser.add_argument("--resident-heartbeat-manifest", type=Path)
    parser.add_argument("--resident-button-manifest", type=Path)
    parser.add_argument("--open-chat-no-type-packet-manifest", type=Path)
    parser.add_argument("--open-chat-no-type-result-validation-json", type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    packet_dir = args.packet_dir.resolve()
    output_root = (args.output_root or _default_output_root()).resolve()
    output_root.mkdir(parents=True, exist_ok=True)

    validation_path = packet_dir / "live_ui_canary_result_validation.json"
    validate_rc = validate_no_send_main(
        [
            "--packet-dir",
            str(packet_dir),
            "--output-json",
            str(validation_path),
            "--require-green",
        ]
    )
    validation = _read_json(validation_path) if validation_path.exists() else {}
    if validate_rc != 0:
        manifest = {
            "gate": "YELLOW_NO_SEND_GREEN_FOLLOWUP_BLOCKED_VALIDATION_NOT_GREEN",
            "run_at": datetime.now().isoformat(timespec="seconds"),
            "packet_dir": str(packet_dir),
            "live_ui_validation_json": str(validation_path),
            "live_ui_validation_gate": validation.get("gate"),
            "approval_packet_generated": False,
            "customer_send_allowed": False,
            "kaspi_chat_write_allowed": False,
            "google_board_write_allowed": False,
            "db_write_allowed": False,
            "telegram_send_allowed": False,
            "raw_order_id_exported": False,
            "raw_customer_text_exported": False,
        }
        _write_json(output_root / "manifest.json", manifest)
        (output_root / "closeout.md").write_text(
            "\n".join(
                [
                    "# Kaspi Customer Size No-Send Green Follow-Up",
                    "",
                    f"Gate: {manifest['gate']}",
                    "",
                    f"- Packet: {packet_dir}",
                    f"- Live UI validation gate: {validation.get('gate')}",
                    "- Approval packet generated: false",
                    "",
                    "No customer message, Kaspi write, Google Board write, DB write, Telegram send,",
                    "or external write happened.",
                    "",
                ]
            ),
            encoding="utf-8",
        )
        print(json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True))
        return 1

    approval_dir = output_root / "live_send_approval"
    live_send_approval_main(
        [
            "--packet-dir",
            str(packet_dir),
            "--live-ui-validation-json",
            str(validation_path),
            "--output-dir",
            str(approval_dir),
        ]
    )
    execution_handoff_dir = output_root / "live_send_execution_handoff"
    live_send_execution_handoff_main(
        [
            "--approval-dir",
            str(approval_dir),
            "--output-dir",
            str(execution_handoff_dir),
        ]
    )

    chrome_manifest = args.chrome_reconnect_manifest or _latest(
        "exports/validation/kaspi_customer_chat_chrome_reconnect*/chrome_reconnect_preflight_manifest.json"
    )
    patch_manifest = args.google_board_patch_manifest or _latest(
        "exports/validation/kaspi_customer_size_google_board_patch_packet_*/manifest.json"
    )
    cadence_manifest = args.cadence_manifest or _latest(
        "exports/validation/kaspi_customer_size_cadence_readiness_*/manifest.json"
    )
    workflow_dir = output_root / "workflow_readiness"
    workflow_args = [
        "--live-ui-validation-json",
        str(validation_path),
        "--live-send-approval-manifest",
        str(approval_dir / "manifest.json"),
        "--output-dir",
        str(workflow_dir),
    ]
    if args.db:
        workflow_args.extend(["--db", str(args.db)])
    if args.ledger_db:
        workflow_args.extend(["--ledger-db", str(args.ledger_db)])
    if args.resident_heartbeat_manifest:
        workflow_args.extend(["--resident-heartbeat-manifest", str(args.resident_heartbeat_manifest)])
    if args.resident_button_manifest:
        workflow_args.extend(["--resident-button-manifest", str(args.resident_button_manifest)])
    if args.open_chat_no_type_packet_manifest:
        workflow_args.extend(
            ["--open-chat-no-type-packet-manifest", str(args.open_chat_no_type_packet_manifest)]
        )
    if args.open_chat_no_type_result_validation_json:
        workflow_args.extend(
            [
                "--open-chat-no-type-result-validation-json",
                str(args.open_chat_no_type_result_validation_json),
            ]
        )
    if chrome_manifest:
        workflow_args.extend(["--chrome-reconnect-manifest", str(chrome_manifest)])
    if patch_manifest:
        workflow_args.extend(["--google-board-patch-manifest", str(patch_manifest)])
    if cadence_manifest:
        workflow_args.extend(["--cadence-manifest", str(cadence_manifest)])
    workflow_readiness_main(workflow_args)
    owner_dashboard_main(
        [
            "--workflow-dir",
            str(workflow_dir),
            "--live-send-approval-dir",
            str(approval_dir),
            "--output-dir",
            str(workflow_dir / "owner_dashboard"),
        ]
    )
    automation_options_matrix_main(
        [
            "--workflow-dir",
            str(workflow_dir),
            "--output-dir",
            str(workflow_dir / "automation_options_matrix"),
        ]
    )

    workflow_manifest = _read_json(workflow_dir / "manifest.json")
    approval_manifest = _read_json(approval_dir / "manifest.json")
    execution_handoff_manifest = _read_json(execution_handoff_dir / "manifest.json")
    manifest = {
        "gate": "GREEN_NO_SEND_GREEN_FOLLOWUP_READY_FOR_OWNER_LIVE_SEND_APPROVAL",
        "run_at": datetime.now().isoformat(timespec="seconds"),
        "packet_dir": str(packet_dir),
        "live_ui_validation_json": str(validation_path),
        "live_ui_validation_gate": validation.get("gate"),
        "live_send_approval_dir": str(approval_dir),
        "live_send_approval_gate": approval_manifest.get("gate"),
        "live_send_execution_handoff_dir": str(execution_handoff_dir),
        "live_send_execution_handoff_gate": execution_handoff_manifest.get("gate"),
        "workflow_dir": str(workflow_dir),
        "workflow_gate": workflow_manifest.get("gate"),
        "owner_dashboard_dir": str(workflow_dir / "owner_dashboard"),
        "automation_options_matrix_dir": str(workflow_dir / "automation_options_matrix"),
        "approval_phrase_generated": approval_manifest.get("approval_phrase_generated") is True,
        "customer_send_allowed_now": False,
        "requires_exact_owner_approval_before_send": True,
        "kaspi_chat_write_allowed": False,
        "google_board_write_allowed": False,
        "db_write_allowed": False,
        "telegram_send_allowed": False,
        "raw_order_id_exported": False,
        "raw_customer_text_exported": False,
    }
    _write_json(output_root / "manifest.json", manifest)
    (output_root / "closeout.md").write_text(
        "\n".join(
            [
                "# Kaspi Customer Size No-Send Green Follow-Up",
                "",
                f"Gate: {manifest['gate']}",
                "",
                f"- Packet: {packet_dir}",
                f"- Live UI validation gate: {validation.get('gate')}",
                f"- Live-send approval gate: {approval_manifest.get('gate')}",
                f"- Live-send execution handoff gate: {execution_handoff_manifest.get('gate')}",
                f"- Workflow gate: {workflow_manifest.get('gate')}",
                f"- Approval phrase generated: {manifest['approval_phrase_generated']}",
                "",
                "No customer message, Kaspi write, Google Board write, DB write, Telegram send,",
                "or external write happened. The next send remains exact-owner-approval gated.",
                "",
            ]
        ),
        encoding="utf-8",
    )
    print(json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
