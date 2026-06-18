#!/usr/bin/env python3
"""Record a redacted manual/Computer-Use Kaspi chat no-send proof.

This script is deliberately not a browser automation tool and has no customer
send capability. It records an operator-confirmed visual proof into the same
redacted result files validated by `validate_kaspi_customer_chat_live_canary_result.py`.
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path
from typing import Any

from scripts.validate_kaspi_customer_chat_live_canary_result import (
    DEFAULT_PACKET_DIR,
    GREEN_RESULT_GATE,
    validate as validate_live_ui_result,
)


YELLOW_GATE = "YELLOW_MANUAL_LIVE_ORDER_CHAT_BUTTON_PROOF_INCOMPLETE_NO_SEND"
RED_GATE = "RED_MANUAL_LIVE_ORDER_CHAT_BUTTON_PROOF_UNSAFE"


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _bool_arg(parser: argparse.ArgumentParser, name: str, *, help_text: str) -> None:
    parser.add_argument(name, action="store_true", help=help_text)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--packet-dir", type=Path, default=DEFAULT_PACKET_DIR)
    parser.add_argument(
        "--proof-source",
        choices=["owner_manual_visual", "computer_use_visual", "working_chrome_visual"],
        default="owner_manual_visual",
        help="Redacted proof source. Do not include raw order IDs or customer data.",
    )
    _bool_arg(
        parser,
        "--merchant-account-match-proven",
        help_text="The visible Kaspi merchant account/store matched the packet store.",
    )
    _bool_arg(
        parser,
        "--order-search-performed",
        help_text="The order ID was searched only in the live UI; the raw value is not exported.",
    )
    _bool_arg(
        parser,
        "--order-detail-or-result-reached",
        help_text="The selected order result/detail was visually reached.",
    )
    _bool_arg(
        parser,
        "--chat-button-present",
        help_text="The customer-message button was visually present for the selected order.",
    )
    _bool_arg(
        parser,
        "--chat-opened",
        help_text="Set only if the chat panel was opened for visibility proof.",
    )
    _bool_arg(
        parser,
        "--message-text-typed",
        help_text="Unsafe flag. If set, the proof records RED and validation fails.",
    )
    _bool_arg(
        parser,
        "--message-sent",
        help_text="Unsafe flag. If set, the proof records RED and validation fails.",
    )
    _bool_arg(
        parser,
        "--owner-confirmed-no-send",
        help_text="Operator confirms no customer message text was typed and no send happened.",
    )
    parser.add_argument(
        "--note",
        action="append",
        default=[],
        help="Optional redacted note. Do not include order IDs, phones, addresses, or message text.",
    )
    parser.add_argument(
        "--validation-json",
        type=Path,
        help="Optional validation output path. Defaults to packet live_ui_canary_result_validation.json.",
    )
    parser.add_argument(
        "--require-green",
        action="store_true",
        help="Exit nonzero unless the manual proof validates GREEN.",
    )
    return parser


def _result_gate(args: argparse.Namespace) -> str:
    if args.message_text_typed or args.message_sent:
        return RED_GATE
    required_true = [
        args.owner_confirmed_no_send,
        args.merchant_account_match_proven,
        args.order_search_performed,
        args.order_detail_or_result_reached,
        args.chat_button_present,
    ]
    if all(required_true):
        return GREEN_RESULT_GATE
    return YELLOW_GATE


def _build_closeout(result: dict[str, Any], validation: dict[str, Any]) -> str:
    lines = [
        "# Kaspi Customer Chat Manual Live UI No-Send Proof Closeout",
        "",
        f"Gate: {result['gate']}",
        "",
        "## Scope",
        "",
        f"- Store: {result.get('store_code')}",
        f"- DB row: {result.get('db_row_id')}",
        f"- Selected order ref: {result.get('selected_order_ref')}",
        f"- Status filter: {result.get('suggested_merchant_status_filter')}",
        f"- Proof source: {result.get('proof_source')}",
        "",
        "## Visual Proof Flags",
        "",
        f"- Owner confirmed no send: {str(result.get('owner_confirmed_no_send')).lower()}",
        f"- Merchant account/store match proven: {str(result.get('merchant_account_match_proven')).lower()}",
        f"- Order search performed: {str(result.get('order_search_performed')).lower()}",
        f"- Order result/detail reached: {str(result.get('order_detail_or_result_reached')).lower()}",
        f"- Chat button present: {str(result.get('chat_button_present')).lower()}",
        f"- Chat opened: {str(result.get('chat_opened')).lower()}",
        f"- Message text typed: {str(result.get('message_text_typed')).lower()}",
        f"- Message sent: {str(result.get('message_sent')).lower()}",
        f"- Raw order ID exported: {str(result.get('raw_order_id_exported')).lower()}",
        f"- Raw customer text exported: {str(result.get('raw_customer_text_exported')).lower()}",
        "",
        "## Validator",
        "",
        f"- Validator gate: {validation.get('gate')}",
        f"- Accepted: {str(validation.get('accepted')).lower()}",
    ]
    blockers = validation.get("blockers") or []
    if blockers:
        lines.append(f"- Validator blockers: {'; '.join(str(item) for item in blockers)}")
    lines.extend(
        [
            "",
            "## Safety Notes",
            "",
            "- This artifact is a redacted operator/Computer-Use visual proof only.",
            "- It does not authorize or perform a customer send.",
            "- It must not contain raw order IDs, phone numbers, addresses, customer text, cookies, tokens, or session material.",
            "",
        ]
    )
    return "\n".join(lines)


def record(args: argparse.Namespace) -> dict[str, Any]:
    packet_dir = args.packet_dir.resolve()
    manifest_path = packet_dir / "manifest.json"
    if not manifest_path.exists():
        raise FileNotFoundError(f"Missing packet manifest: {manifest_path}")
    manifest = _read_json(manifest_path)
    result_path = packet_dir / "live_ui_probe_result_redacted.json"
    closeout_path = packet_dir / "live_ui_no_send_probe_closeout.md"
    validation_path = args.validation_json or (packet_dir / "live_ui_canary_result_validation.json")

    gate = _result_gate(args)
    result = {
        "gate": gate,
        "recorded_at": datetime.now().isoformat(timespec="seconds"),
        "proof_type": "manual_or_computer_use_visual_no_send",
        "proof_source": args.proof_source,
        "selected_order_ref": manifest.get("selected_order_ref"),
        "db_row_id": manifest.get("selected_db_row_id"),
        "store_code": manifest.get("selected_store_code"),
        "suggested_merchant_status_filter": manifest.get("selected_status_filter"),
        "merchant_account_match_proven": bool(args.merchant_account_match_proven),
        "order_search_performed": bool(args.order_search_performed),
        "order_detail_or_result_reached": bool(args.order_detail_or_result_reached),
        "chat_button_selector": "button.init-chat-button.chat-section[type='CLIENT_SELLER_BY_ORDER']",
        "chat_button_present": bool(args.chat_button_present),
        "chat_opened": bool(args.chat_opened),
        "message_text_typed": bool(args.message_text_typed),
        "message_sent": bool(args.message_sent),
        "owner_confirmed_no_send": bool(args.owner_confirmed_no_send),
        "raw_order_id_exported": False,
        "raw_customer_text_exported": False,
        "raw_phone_exported": False,
        "raw_session_material_exported": False,
        "notes": list(args.note or []),
    }
    _write_json(result_path, result)

    validation_args = argparse.Namespace(
        packet_dir=packet_dir,
        result_json=result_path,
        closeout_md=closeout_path,
        output_json=validation_path.resolve(),
        require_green=False,
    )
    validation = validate_live_ui_result(validation_args)
    closeout_path.write_text(_build_closeout(result, validation), encoding="utf-8")
    validation = validate_live_ui_result(validation_args)
    _write_json(validation_path, validation)
    return {
        "result_path": str(result_path),
        "closeout_path": str(closeout_path),
        "validation_path": str(validation_path),
        "result_gate": result.get("gate"),
        "validation_gate": validation.get("gate"),
        "accepted": validation.get("accepted") is True,
        "customer_send_allowed": False,
        "kaspi_chat_write_allowed": False,
        "raw_order_id_exported": False,
        "raw_customer_text_exported": False,
    }


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    summary = record(args)
    print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))
    if args.require_green and not summary["accepted"]:
        return 1
    if str(summary["validation_gate"]).startswith("RED_"):
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
