#!/usr/bin/env python3
"""Enqueue a local no-send command for the resident Kaspi chat controller."""

from __future__ import annotations

import argparse
import json
from datetime import date, datetime
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_RUN_DIR = PROJECT_ROOT / "exports" / "validation" / "kaspi_customer_chat_resident_no_send_controller_current"
GREEN_GATE = "GREEN_KASPI_CUSTOMER_CHAT_RESIDENT_COMMAND_ENQUEUED_NO_SEND"


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def build_command(args: argparse.Namespace) -> dict[str, Any]:
    command_id = args.command_id or f"ui_search_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    return {
        "command_id": command_id,
        "action": args.action,
        "queued_at": datetime.now().isoformat(timespec="seconds"),
        "target_date": args.target_date or date.today().isoformat(),
        "lookback_days": args.lookback_days,
        "stores": args.stores,
        "profile_store_code": args.profile_store_code,
        "max_candidates": args.max_candidates,
        "candidate_pool_limit": args.candidate_pool_limit,
        "extra_status_filters": args.extra_status_filters,
        "target_db_row_ids": args.target_db_row_ids,
        "target_order_refs": args.target_order_refs,
        "expected_merchant_account_id": str(getattr(args, "expected_merchant_account_id", "") or "").strip(),
        "timeout_ms": args.timeout_ms,
        "output_dir": str(args.output_dir) if args.output_dir else "",
        "messages_db": str(args.messages_db) if getattr(args, "messages_db", None) else "",
        "otp_audit_json": str(args.otp_audit_json) if getattr(args, "otp_audit_json", None) else "",
        "otp_window_minutes": getattr(args, "otp_window_minutes", 10),
        "otp_max_scan_rows": getattr(args, "otp_max_scan_rows", 50),
        "otp_submit_allowed": bool(getattr(args, "otp_submit_allowed", False)),
        "open_chat_packet_dir": str(args.open_chat_packet_dir)
        if getattr(args, "open_chat_packet_dir", None)
        else "",
        "open_chat_approval_text_file": str(args.open_chat_approval_text_file)
        if getattr(args, "open_chat_approval_text_file", None)
        else "",
        "customer_send_allowed": False,
        "kaspi_chat_write_allowed": False,
        "chat_open_allowed": bool(getattr(args, "chat_open_allowed", False)),
        "message_text_typed": False,
        "message_sent": False,
        "raw_order_id_exported": False,
        "raw_customer_text_exported": False,
        "raw_phone_exported": False,
        "raw_session_material_exported": False,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", type=Path, default=DEFAULT_RUN_DIR)
    parser.add_argument("--command-id")
    parser.add_argument(
        "--action",
        choices=[
            "ui_search_identity_no_send",
            "ui_chat_button_no_open",
            "metadata_capture_no_send",
            "login_sms_otp_no_secret",
            "ui_open_chat_no_type_canary",
            "ui_open_chat_selector_dom_diagnostic_no_click",
        ],
        default="ui_search_identity_no_send",
    )
    parser.add_argument("--target-date")
    parser.add_argument("--lookback-days", type=int, default=5)
    parser.add_argument("--stores", default="ACMEWEAR")
    parser.add_argument("--profile-store-code", default="ACMEWEAR")
    parser.add_argument("--max-candidates", type=int, default=6)
    parser.add_argument("--candidate-pool-limit", type=int, default=30)
    parser.add_argument(
        "--extra-status-filters",
        default="KASPI_DELIVERY_WAIT_FOR_COURIER,NEW,ACCEPTED_BY_MERCHANT",
    )
    parser.add_argument(
        "--target-db-row-ids",
        default="",
        help="Optional comma-separated DB row IDs to prove in the no-send resident session.",
    )
    parser.add_argument(
        "--target-order-refs",
        default="",
        help="Optional comma-separated redacted order refs to prove in the no-send resident session.",
    )
    parser.add_argument(
        "--expected-merchant-account-id",
        default="",
        help="Optional expected visible Kaspi merchant account ID, for example 30137883 for ACMEWEAR.",
    )
    parser.add_argument("--timeout-ms", type=int, default=30000)
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--messages-db", type=Path)
    parser.add_argument("--otp-audit-json", type=Path)
    parser.add_argument("--otp-window-minutes", type=int, default=10)
    parser.add_argument("--otp-max-scan-rows", type=int, default=50)
    parser.add_argument(
        "--otp-submit-allowed",
        action="store_true",
        help="For login_sms_otp_no_secret only: after filling OTP, click a visible login submit button if found.",
    )
    parser.add_argument("--open-chat-packet-dir", type=Path)
    parser.add_argument("--open-chat-approval-text-file", type=Path)
    parser.add_argument(
        "--chat-open-allowed",
        action="store_true",
        help=(
            "For ui_open_chat_no_type_canary only: acknowledge that the future exact canary "
            "may open one selected chat. This still does not type or send."
        ),
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    command = build_command(args)
    commands_dir = args.run_dir.resolve() / "command_queue"
    command_path = commands_dir / f"{command['command_id']}.json"
    _write_json(command_path, command)
    summary = {
        "gate": GREEN_GATE,
        "command_path": str(command_path),
        "commands_dir": str(commands_dir),
        "customer_send_allowed": False,
        "kaspi_chat_write_allowed": False,
        "raw_order_id_exported": False,
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
