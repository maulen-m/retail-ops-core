#!/usr/bin/env python3
"""Record an owner/operator manual Kaspi customer-size action outcome.

This script updates only the local runtime customer-size ledger. It does not
open Kaspi, type, send, read customer replies, write Google Board, write the
production app DB, or send Telegram/WhatsApp.
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path
from typing import Any, Mapping

from core.ops.customer_size_request import (
    DEFAULT_REQUEST_TEMPLATE,
    record_manual_size_request_action,
    request_template_hash,
    sha256_file,
)


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_LEDGER_DB = (
    REPO_ROOT
    / "runtime"
    / "customer_size_request_ledger"
    / "no_send_customer_size_request_ledger.sqlite"
)


def _safe_sha(path: Path) -> str | None:
    return sha256_file(path) if path.exists() else None


def _default_output_dir() -> Path:
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return REPO_ROOT / "exports" / "validation" / f"kaspi_customer_size_manual_action_outcome_{stamp}"


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _render_closeout(manifest: Mapping[str, Any]) -> str:
    return "\n".join(
        [
            "# Kaspi Customer Size Manual Action Outcome",
            "",
            f"Gate: {manifest['gate']}",
            "",
            f"- Outcome: `{manifest['outcome']}`",
            f"- Status after: `{manifest.get('status_after') or ''}`",
            f"- Ledger changed: `{str(manifest['ledger_db_changed']).lower()}`",
            "",
            "No browser action, customer message send/type, endpoint replay, Google Board write, production DB write, Telegram/WhatsApp send, or scheduler change was performed by this helper.",
            "",
        ]
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ledger-db", type=Path, default=DEFAULT_LEDGER_DB)
    parser.add_argument("--order-ref", required=True)
    parser.add_argument("--template-hash", default=request_template_hash(DEFAULT_REQUEST_TEMPLATE))
    parser.add_argument(
        "--outcome",
        required=True,
        choices=[
            "sent_manual",
            "skipped",
            "not_found",
            "wrong_merchant",
            "unsafe",
            "already_size_present",
        ],
    )
    parser.add_argument("--operator-confirmed-manual-action", action="store_true")
    parser.add_argument("--confirm-no-auto-type", action="store_true")
    parser.add_argument("--confirm-no-raw-export", action="store_true")
    parser.add_argument("--output-dir", type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    output_dir = (args.output_dir or _default_output_dir()).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    ledger_path = args.ledger_db.resolve()
    ledger_sha_before = _safe_sha(ledger_path)
    stats, record = record_manual_size_request_action(
        ledger_path,
        order_ref=args.order_ref,
        template_hash=args.template_hash,
        outcome=args.outcome,
        operator_confirmed_manual_action=args.operator_confirmed_manual_action,
        confirm_no_auto_type=args.confirm_no_auto_type,
        confirm_no_raw_export=args.confirm_no_raw_export,
    )
    ledger_sha_after = _safe_sha(ledger_path)
    if stats.get("updated"):
        gate = "GREEN_MANUAL_SEND_OUTCOME_RECORDED_NO_EXTERNAL_WRITE"
    elif stats.get("blocked_missing_confirmation"):
        gate = "YELLOW_MANUAL_SEND_OUTCOME_BLOCKED_CONFIRMATION_REQUIRED_NO_WRITE"
    elif stats.get("already_after_send_or_reply"):
        gate = "YELLOW_MANUAL_SEND_OUTCOME_ALREADY_AFTER_SEND_OR_REPLY_NO_WRITE"
    elif stats.get("unmatched"):
        gate = "YELLOW_MANUAL_SEND_OUTCOME_LEDGER_ROW_NOT_FOUND_NO_WRITE"
    else:
        gate = "RED_MANUAL_SEND_OUTCOME_INVALID_NO_WRITE"
    manifest = {
        "gate": gate,
        "run_at": datetime.now().isoformat(timespec="seconds"),
        "output_dir": str(output_dir),
        "ledger_db_path": str(ledger_path),
        "ledger_db_sha256_before": ledger_sha_before,
        "ledger_db_sha256_after": ledger_sha_after,
        "ledger_db_changed": ledger_sha_before != ledger_sha_after,
        "order_ref": record.get("order_ref"),
        "template_hash": record.get("template_hash"),
        "outcome": args.outcome,
        "status_after": record.get("status_after"),
        "record_stats": stats,
        "record": record,
        "customer_send_performed_by_automation": False,
        "kaspi_chat_write_performed_by_automation": False,
        "browser_action_performed": False,
        "endpoint_replay_performed": False,
        "google_board_write_allowed": False,
        "db_write_allowed": False,
        "telegram_send_allowed": False,
        "raw_order_ids_exported": False,
        "raw_customer_text_exported": False,
        "raw_phone_exported": False,
        "raw_session_material_exported": False,
    }
    _write_json(output_dir / "manifest.json", manifest)
    _write_json(output_dir / "manual_action_record_redacted.json", record)
    (output_dir / "closeout.md").write_text(_render_closeout(manifest), encoding="utf-8")
    print(json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if gate.startswith(("GREEN_", "YELLOW_")) else 2


if __name__ == "__main__":
    raise SystemExit(main())
