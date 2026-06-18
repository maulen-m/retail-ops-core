#!/usr/bin/env python3
"""Build a no-send resident-session resume packet for Kaspi customer-size work."""

from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_RESIDENT_RUN_DIR = (
    REPO_ROOT
    / "exports"
    / "validation"
    / "kaspi_customer_chat_resident_no_send_controller_current"
)
DEFAULT_PRIORITY_COMMAND = (
    REPO_ROOT
    / "exports"
    / "validation"
    / "kaspi_customer_size_priority_resident_no_send_command_20260618_current"
    / "command_queue"
    / "priority_top_001_ui_chat_button_no_open_36170.json"
)
DEFAULT_OUTPUT_DIR = (
    REPO_ROOT
    / "exports"
    / "validation"
    / f"kaspi_customer_size_resident_resume_packet_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
)

GREEN_GATE = "GREEN_KASPI_CUSTOMER_SIZE_RESIDENT_RESUME_PACKET_READY_NO_BROWSER_TOUCH"
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


def _write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _load_command_summary(command_path: Path) -> dict[str, Any]:
    command = _read_json(command_path) if command_path.exists() else {}
    store_code = str(command.get("profile_store_code") or command.get("stores") or "").strip().upper()
    return {
        "command_exists": command_path.exists(),
        "command_id": command.get("command_id", ""),
        "action": command.get("action", ""),
        "profile_store_code": command.get("profile_store_code", ""),
        "stores": command.get("stores", ""),
        "expected_merchant_account_id": MERCHANT_SELECTOR_MAP.get(store_code, ""),
        "target_db_row_ids": command.get("target_db_row_ids", ""),
        "target_order_refs": command.get("target_order_refs", ""),
        "extra_status_filters": command.get("extra_status_filters", ""),
        "output_dir": command.get("output_dir", ""),
        "customer_send_allowed": bool(command.get("customer_send_allowed")),
        "kaspi_chat_write_allowed": bool(command.get("kaspi_chat_write_allowed")),
        "message_sent": bool(command.get("message_sent")),
    }


def _start_script(*, run_dir: Path, startup_status_filter: str, manual_login_timeout_seconds: int) -> str:
    return f"""#!/usr/bin/env bash
set -euo pipefail
cd "{REPO_ROOT}"
PYTHONPATH=. .venv/bin/python scripts/run_kaspi_customer_chat_resident_no_send_controller.py \\
  --run-dir "{run_dir}" \\
  --profile-store-code ACMEWEAR \\
  --startup-status-filter "{startup_status_filter}" \\
  --manual-login-timeout-seconds {manual_login_timeout_seconds} \\
  --poll-seconds 2 \\
  --enable-open-chat-no-type-canary
"""


def _enqueue_script(*, run_dir: Path, command_path: Path, output_dir: Path) -> str:
    return f"""#!/usr/bin/env bash
set -euo pipefail
cd "{REPO_ROOT}"
PYTHONPATH=. .venv/bin/python scripts/enqueue_kaspi_customer_chat_priority_if_resident_ready.py \\
  --run-dir "{run_dir}" \\
  --command-path "{command_path}" \\
  --output-dir "{output_dir}" \\
  --heartbeat-max-age-seconds 300 \\
  --enqueue
"""


def _followup_script(*, resident_manifest_path: Path, output_dir: Path) -> str:
    return f"""#!/usr/bin/env bash
set -euo pipefail
cd "{REPO_ROOT}"
PYTHONPATH=. .venv/bin/python scripts/run_kaspi_customer_size_resident_proof_followup.py \\
  --resident-button-manifest "{resident_manifest_path}" \\
  --expected-order-ref sha256:3a507903190c4097e2d211ee \\
  --expected-db-row-id 36170 \\
  --output-dir "{output_dir}" \\
  --timeout-seconds 300 \\
  --poll-seconds 2
"""


def _approval_script(*, resident_manifest_path: Path, output_dir: Path) -> str:
    return f"""#!/usr/bin/env bash
set -euo pipefail
cd "{REPO_ROOT}"
PYTHONPATH=. .venv/bin/python scripts/build_kaspi_customer_chat_live_send_canary_approval_packet.py \\
  --resident-button-manifest "{resident_manifest_path}" \\
  --output-dir "{output_dir}"
PYTHONPATH=. .venv/bin/python scripts/build_kaspi_customer_chat_live_send_canary_execution_handoff.py \\
  --approval-dir "{output_dir}" \\
  --output-dir "{output_dir}/live_send_execution_handoff"
"""


def _runbook(manifest: dict[str, Any]) -> str:
    return "\n".join(
        [
            "# Kaspi Customer Size Resident Resume Runbook",
            "",
            f"Gate: {manifest['gate']}",
            "",
            "## Purpose",
            "",
            "Resume the customer-size Kaspi chat workflow without repeated SMS/login churn. This packet does not start Chrome, does not enqueue by itself, does not open chat, and does not send a customer message.",
            "",
            "## Hard Safety",
            "",
            "- Do not use `--once` for the resident controller.",
            "- Do not use `--allow-session-close` unless the owner separately approves teardown.",
            "- If Kaspi asks for SMS/login, the owner can complete it once, then leave the resident browser open.",
            "- Do not close the resident browser after proof. The controller is meant to stay alive.",
            "- The merchant dropdown must show the order's own store ID before search.",
            "",
            "## Merchant Selector Map",
            "",
            "- `UNIVERSAL -> ID - 30000001`",
            "- `ACMEWEAR -> ID - 30137883`",
            "- `STOREB -> ID - 30000002`",
            "- `MELVIS -> ID - 30362323`",
            "- `11KZ -> ID - 30290083`",
            "",
            "## Step 1: Start Resident Controller",
            "",
            f"Run: `{manifest['start_script_path']}`",
            "",
            "Expected GREEN heartbeat:",
            "",
            f"`{manifest['heartbeat_path']}`",
            "",
            "## Step 2: Guarded Enqueue",
            "",
            f"Run only after the heartbeat is fresh/GREEN: `{manifest['enqueue_script_path']}`",
            "",
            "This helper fails closed if the controller is stale, not running, wrong-store, or command flags are not no-send.",
            "",
            "## Step 3: Resident No-Send Proof",
            "",
            "Wait for the resident controller to process the command. Expected proof manifest:",
            "",
            f"`{manifest['expected_resident_button_manifest_path']}`",
            "",
            "Required proof gate:",
            "",
            "`GREEN_KASPI_CUSTOMER_CHAT_MESSAGE_BUTTON_PROVEN_NO_SEND`",
            "",
            "## Step 4: Build Owner Approval Packet",
            "",
            f"After guarded enqueue, run the watcher/follow-up: `{manifest['proof_followup_script_path']}`",
            "",
            "The watcher waits for the current priority proof, rejects old/wrong-target GREEN proofs, and then generates the exact one-order approval phrase plus execution handoff. It still does not send.",
            "",
            "Optional direct approval builder if you already manually verified the proof manifest is GREEN:",
            "",
            f"`{manifest['build_approval_script_path']}`",
            "",
            "## Current Priority Target",
            "",
            f"- Command ID: `{manifest['priority_command']['command_id']}`",
            f"- Action: `{manifest['priority_command']['action']}`",
            f"- Store: `{manifest['priority_command']['profile_store_code'] or manifest['priority_command']['stores']}`",
            f"- Required merchant selector ID: `{manifest['priority_command']['expected_merchant_account_id']}`",
            f"- DB row IDs: `{manifest['priority_command']['target_db_row_ids']}`",
            f"- Order refs: `{manifest['priority_command']['target_order_refs']}`",
            f"- Status filters: `{manifest['priority_command']['extra_status_filters']}`",
            "",
            "## No-Send Invariants",
            "",
            "- Customer send allowed: false",
            "- Kaspi chat write allowed: false",
            "- Chat open allowed by this packet: false",
            "- Message typed: false",
            "- Message sent: false",
            "- Raw order/customer/session export: false",
            "",
        ]
    )


def build_packet(
    *,
    output_dir: Path,
    run_dir: Path,
    priority_command_path: Path,
    startup_status_filter: str,
    manual_login_timeout_seconds: int,
) -> dict[str, Any]:
    output_dir = output_dir.resolve()
    run_dir = run_dir.resolve()
    priority_command_path = priority_command_path.resolve()
    heartbeat_path = run_dir / "resident_controller_heartbeat.json"
    priority_command_summary = _load_command_summary(priority_command_path)
    command_output_dir = str(priority_command_summary.get("output_dir") or "").strip()
    expected_resident_manifest_path = (
        (REPO_ROOT / command_output_dir).resolve() / "manifest.json"
        if command_output_dir
        else run_dir / "commands" / "priority_top_001_ui_chat_button_no_open_36170" / "manifest.json"
    )
    enqueue_output_dir = output_dir / "priority_enqueue_readiness_after_resident_green"
    approval_output_dir = output_dir / "live_send_approval_after_resident_green"
    proof_followup_output_dir = output_dir / "resident_proof_followup_after_enqueue"
    start_script_path = output_dir / "01_start_resident_controller_preserve_session.sh"
    enqueue_script_path = output_dir / "02_guarded_enqueue_priority_no_send.sh"
    followup_script_path = output_dir / "03_watch_resident_proof_and_build_approval.sh"
    approval_script_path = output_dir / "04_build_live_send_approval_after_green_proof.sh"

    manifest = {
        "gate": GREEN_GATE,
        "run_at": datetime.now().isoformat(timespec="seconds"),
        "output_dir": str(output_dir),
        "resident_run_dir": str(run_dir),
        "heartbeat_path": str(heartbeat_path),
        "priority_command_path": str(priority_command_path),
        "priority_command": priority_command_summary,
        "merchant_selector_map": MERCHANT_SELECTOR_MAP,
        "expected_resident_button_manifest_path": str(expected_resident_manifest_path),
        "enqueue_readiness_output_dir": str(enqueue_output_dir),
        "proof_followup_output_dir": str(proof_followup_output_dir),
        "live_send_approval_output_dir": str(approval_output_dir),
        "start_script_path": str(start_script_path),
        "enqueue_script_path": str(enqueue_script_path),
        "proof_followup_script_path": str(followup_script_path),
        "build_approval_script_path": str(approval_script_path),
        "startup_status_filter": startup_status_filter,
        "manual_login_timeout_seconds": manual_login_timeout_seconds,
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
    _write_text(
        start_script_path,
        _start_script(
            run_dir=run_dir,
            startup_status_filter=startup_status_filter,
            manual_login_timeout_seconds=manual_login_timeout_seconds,
        ),
    )
    _write_text(enqueue_script_path, _enqueue_script(run_dir=run_dir, command_path=priority_command_path, output_dir=enqueue_output_dir))
    _write_text(followup_script_path, _followup_script(resident_manifest_path=expected_resident_manifest_path, output_dir=proof_followup_output_dir))
    _write_text(
        approval_script_path,
        _approval_script(
            resident_manifest_path=expected_resident_manifest_path,
            output_dir=approval_output_dir,
        ),
    )
    for path in [start_script_path, enqueue_script_path, followup_script_path, approval_script_path]:
        path.chmod(0o755)
    runbook = _runbook(manifest)
    _write_text(output_dir / "RUNBOOK.md", runbook)
    _write_text(
        output_dir / "closeout.md",
        "\n".join(
            [
                "# Kaspi Customer Size Resident Resume Packet",
                "",
                f"Gate: {manifest['gate']}",
                "",
                f"- Output folder: `{output_dir}`",
                f"- Resident run dir: `{run_dir}`",
                f"- Priority command: `{priority_command_path}`",
                f"- Runbook: `{output_dir / 'RUNBOOK.md'}`",
                f"- Start script: `{start_script_path}`",
                f"- Guarded enqueue script: `{enqueue_script_path}`",
                f"- Proof follow-up script: `{followup_script_path}`",
                f"- Approval packet script: `{approval_script_path}`",
                "",
                "No browser was touched. No customer message, Kaspi chat write, Google Board write, production DB write, Telegram send, or external write was performed.",
                "",
            ]
        ),
    )
    return manifest


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--run-dir", type=Path, default=DEFAULT_RESIDENT_RUN_DIR)
    parser.add_argument("--priority-command-path", type=Path, default=DEFAULT_PRIORITY_COMMAND)
    parser.add_argument("--startup-status-filter", default="NEW")
    parser.add_argument("--manual-login-timeout-seconds", type=int, default=900)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    manifest = build_packet(
        output_dir=args.output_dir,
        run_dir=args.run_dir,
        priority_command_path=args.priority_command_path,
        startup_status_filter=str(args.startup_status_filter),
        manual_login_timeout_seconds=int(args.manual_login_timeout_seconds),
    )
    print(json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
