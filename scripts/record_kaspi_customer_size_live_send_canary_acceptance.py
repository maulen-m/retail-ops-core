#!/usr/bin/env python3
"""Record local ledger state after a one-order Kaspi live-send canary is GREEN.

This script does not send messages. It validates the redacted live-send canary
result, stamps the matching local ledger row as REQUEST_SENT, and emits a
redacted reply-poll schedule.
"""
from __future__ import annotations

import argparse
import json
from argparse import Namespace
from datetime import datetime
from pathlib import Path
from typing import Any

from core.ops.customer_size_request import (
    export_customer_size_ledger_snapshot,
    record_live_send_canary_acceptance,
    summarize_customer_size_ledger,
)
from scripts.validate_kaspi_customer_chat_live_send_canary_result import (
    ACCEPTED_GATE,
    validate as validate_live_send_canary_result,
)


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_LEDGER_DB = (
    REPO_ROOT
    / "runtime"
    / "customer_size_request_ledger"
    / "no_send_customer_size_request_ledger.sqlite"
)
DEFAULT_REPLY_POLL_WINDOWS_MINUTES = (10, 30, 60, 120)


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _default_output_dir() -> Path:
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return (
        REPO_ROOT
        / "exports"
        / "validation"
        / f"kaspi_customer_size_post_live_send_canary_{stamp}"
    )


def _parse_windows(values: list[str] | None) -> tuple[int, ...]:
    if not values:
        return DEFAULT_REPLY_POLL_WINDOWS_MINUTES
    parsed: list[int] = []
    for value in values:
        for token in str(value).split(","):
            token = token.strip()
            if not token:
                continue
            minutes = int(token)
            if minutes <= 0:
                raise ValueError("reply poll windows must be positive minutes")
            parsed.append(minutes)
    return tuple(parsed) or DEFAULT_REPLY_POLL_WINDOWS_MINUTES


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--approval-dir", type=Path, required=True)
    parser.add_argument("--ledger-db", type=Path, default=DEFAULT_LEDGER_DB)
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--result-json", type=Path)
    parser.add_argument("--closeout-md", type=Path)
    parser.add_argument(
        "--reply-poll-window-minutes",
        action="append",
        help="Comma-separated or repeated positive minute offsets. Default: 10,30,60,120.",
    )
    return parser


def _build_validation(args: argparse.Namespace) -> dict[str, Any]:
    validation_args = Namespace(
        approval_dir=args.approval_dir.resolve(),
        result_json=args.result_json,
        closeout_md=args.closeout_md,
        output_json=None,
        require_green=False,
    )
    return validate_live_send_canary_result(validation_args)


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    approval_dir = args.approval_dir.resolve()
    ledger_path = args.ledger_db.resolve()
    output_dir = (args.output_dir or _default_output_dir()).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    poll_windows = _parse_windows(args.reply_poll_window_minutes)

    validation = _build_validation(args)
    _write_json(output_dir / "live_send_canary_result_validation_redacted.json", validation)
    if validation.get("gate") != ACCEPTED_GATE:
        manifest = {
            "gate": "YELLOW_LIVE_SEND_CANARY_ACCEPTANCE_BLOCKED_RESULT_NOT_GREEN",
            "run_at": datetime.now().isoformat(timespec="seconds"),
            "approval_dir": str(approval_dir),
            "ledger_db": str(ledger_path),
            "live_send_validation_gate": validation.get("gate"),
            "blockers": ["live_send_canary_result_not_green"],
            "ledger_updated": False,
            "reply_poll_schedule_generated": False,
            "customer_send_allowed": False,
            "kaspi_chat_write_allowed": False,
            "google_board_write_allowed": False,
            "db_write_allowed": False,
            "telegram_send_allowed": False,
            "raw_order_id_exported": False,
            "raw_customer_text_exported": False,
        }
        _write_json(output_dir / "manifest.json", manifest)
        _write_text(
            output_dir / "closeout.md",
            "\n".join(
                [
                    "# Kaspi Customer Size Post Live-Send Canary Bridge",
                    "",
                    f"Gate: {manifest['gate']}",
                    "",
                    f"- Approval dir: {approval_dir}",
                    f"- Live-send validation gate: {validation.get('gate')}",
                    "- Ledger updated: false",
                    "- Reply poll schedule generated: false",
                    "",
                    "No customer message, Kaspi write, Google Board write, production DB write,",
                    "Telegram send, scheduler change, or external write happened.",
                    "",
                ]
            ),
        )
        print(json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True))
        return 1

    stats, schedule = record_live_send_canary_acceptance(
        ledger_path,
        validation,
        reply_poll_windows_minutes=poll_windows,
    )
    snapshot = export_customer_size_ledger_snapshot(ledger_path)
    summary = summarize_customer_size_ledger(snapshot)
    _write_json(output_dir / "reply_poll_schedule_redacted.json", schedule)
    _write_json(output_dir / "ledger_snapshot_after_redacted.json", snapshot)
    _write_json(output_dir / "ledger_summary_after.json", summary)

    gate = (
        "GREEN_LIVE_SEND_CANARY_ACCEPTANCE_RECORDED_REPLY_POLL_READY_NO_EXTERNAL_WRITE"
        if stats.get("matched") == 1 and schedule
        else "YELLOW_LIVE_SEND_CANARY_ACCEPTANCE_NOT_MATCHED_NO_EXTERNAL_WRITE"
    )
    manifest = {
        "gate": gate,
        "run_at": datetime.now().isoformat(timespec="seconds"),
        "approval_dir": str(approval_dir),
        "ledger_db": str(ledger_path),
        "live_send_validation_gate": validation.get("gate"),
        "selected_order_ref": validation.get("selected_order_ref"),
        "selected_db_row_id": validation.get("selected_db_row_id"),
        "selected_store_code": validation.get("selected_store_code"),
        "record_stats": stats,
        "reply_poll_schedule_count": len(schedule),
        "reply_poll_windows_minutes": list(poll_windows),
        "ledger_summary_after": summary,
        "ledger_updated": stats.get("updated_to_request_sent") == 1,
        "reply_poll_schedule_generated": bool(schedule),
        "customer_send_allowed": False,
        "kaspi_chat_write_allowed": False,
        "google_board_write_allowed": False,
        "db_write_allowed": False,
        "telegram_send_allowed": False,
        "raw_order_id_exported": False,
        "raw_customer_text_exported": False,
    }
    _write_json(output_dir / "manifest.json", manifest)
    _write_text(
        output_dir / "closeout.md",
        "\n".join(
            [
                "# Kaspi Customer Size Post Live-Send Canary Bridge",
                "",
                f"Gate: {manifest['gate']}",
                "",
                f"- Approval dir: {approval_dir}",
                f"- Live-send validation gate: {validation.get('gate')}",
                f"- Ledger updated: {manifest['ledger_updated']}",
                f"- Reply poll schedule rows: {len(schedule)}",
                f"- Reply poll pending count: {summary.get('reply_poll_pending_count')}",
                "",
                "No customer message, Kaspi write, Google Board write, production DB write,",
                "Telegram send, scheduler change, or external write happened.",
                "",
            ]
        ),
    )
    print(json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if gate.startswith("GREEN_") else 1


if __name__ == "__main__":
    raise SystemExit(main())
