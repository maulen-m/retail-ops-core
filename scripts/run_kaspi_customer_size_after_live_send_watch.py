#!/usr/bin/env python3
"""Validate a live-send result and run the local post-canary chain.

This helper is intentionally local-only. It does not open Kaspi, send/read
customer chats, write Google Board, write production DB, or send Telegram. It
waits for the UI helper's redacted one-order live-send result, validates it,
then runs the post-canary local ledger/reply-poll/Board-staging sequence with
the exact GREEN live-send preflight manifest.
"""
from __future__ import annotations

import argparse
import json
import time
from datetime import date, datetime
from pathlib import Path
from typing import Any

from core.ops.customer_size_request import sha256_file
from scripts.run_kaspi_customer_size_post_canary_sequence import (
    DEFAULT_DB,
    DEFAULT_LEDGER_DB,
    GREEN_SEQUENCE_GATE as POST_CANARY_GREEN_GATE,
    main as post_canary_sequence_main,
)
from scripts.validate_kaspi_customer_chat_live_send_canary_result import (
    ACCEPTED_GATE as LIVE_SEND_ACCEPTED_GATE,
    validate as validate_live_send_result,
)


REPO_ROOT = Path(__file__).resolve().parents[1]
GREEN_GATE = "GREEN_AFTER_LIVE_SEND_LOCAL_POST_CANARY_READY_NO_EXTERNAL_WRITE"
YELLOW_RESULT_NOT_READY_GATE = "YELLOW_AFTER_LIVE_SEND_RESULT_NOT_READY_NO_EXTERNAL_WRITE"
YELLOW_RESULT_NOT_GREEN_GATE = "YELLOW_AFTER_LIVE_SEND_RESULT_NOT_GREEN_NO_EXTERNAL_WRITE"
YELLOW_POST_CANARY_GATE = "YELLOW_AFTER_LIVE_SEND_POST_CANARY_SEQUENCE_REVIEW_NEEDED_NO_EXTERNAL_WRITE"


def _default_output_dir() -> Path:
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return REPO_ROOT / "exports" / "validation" / f"kaspi_customer_size_after_live_send_watch_{stamp}"


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _read_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"Expected object JSON at {path}")
    return payload


def _safe_sha(path: Path) -> str | None:
    return sha256_file(path) if path.exists() else None


def _wait_for_result_files(
    *,
    result_path: Path,
    closeout_path: Path,
    wait_seconds: float,
    poll_seconds: float,
) -> bool:
    deadline = time.time() + max(wait_seconds, 0.0)
    while True:
        if result_path.exists() and closeout_path.exists():
            return True
        if time.time() >= deadline:
            return False
        time.sleep(max(poll_seconds, 0.2))


def _closeout(manifest: dict[str, Any]) -> str:
    lines = [
        "# Kaspi Customer Size After Live-Send Watch",
        "",
        f"Gate: {manifest['gate']}",
        "",
        "## Scope",
        "",
        "Local-only bridge after the one-order UI live-send canary. This helper does not open Kaspi, send/read customer chats, write Google Board, write production DB, send Telegram/WhatsApp, or change schedulers.",
        "",
        "## Evidence",
        "",
        f"- Approval dir: `{manifest.get('approval_dir')}`",
        f"- Live-send validation gate: `{manifest.get('live_send_validation_gate')}`",
        f"- Post-canary manifest: `{manifest.get('post_canary_manifest_path')}`",
        "",
        "## Safety",
        "",
        "- Customer send performed by this helper: false",
        "- Kaspi chat write allowed: false",
        "- Google Board write allowed: false",
        "- Production DB write allowed: false",
        "- Telegram/WhatsApp send allowed: false",
        "- Raw order IDs exported: false",
        "- Raw reply text exported: false",
        "",
    ]
    blockers = manifest.get("blockers") or []
    if blockers:
        lines.extend(["## Blockers", ""])
        lines.extend(f"- {blocker}" for blocker in blockers)
        lines.append("")
    lines.extend(["## Next Action", "", f"- {manifest.get('exact_next_action')}", ""])
    return "\n".join(lines)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--approval-dir", type=Path, required=True)
    parser.add_argument("--live-send-execution-preflight-manifest", type=Path, required=True)
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument("--ledger-db", type=Path, default=DEFAULT_LEDGER_DB)
    parser.add_argument("--target-date", default=date.today().isoformat())
    parser.add_argument("--lookback-days", type=int, default=3)
    parser.add_argument("--resident-session-reuse-manifest", type=Path)
    parser.add_argument("--resident-heartbeat-manifest", type=Path)
    parser.add_argument("--resident-button-manifest", type=Path)
    parser.add_argument("--open-chat-no-type-packet-manifest", type=Path)
    parser.add_argument("--open-chat-no-type-result-validation-json", type=Path)
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--wait-seconds", type=float, default=0.0)
    parser.add_argument("--poll-seconds", type=float, default=2.0)
    parser.add_argument("--result-json", type=Path)
    parser.add_argument("--closeout-md", type=Path)
    parser.add_argument(
        "--reply-poll-window-minutes",
        action="append",
        help="Comma-separated or repeated positive minute offsets for the post-canary sequence.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    approval_dir = args.approval_dir.resolve()
    preflight_manifest = args.live_send_execution_preflight_manifest.resolve()
    db_path = args.db.resolve()
    ledger_path = args.ledger_db.resolve()
    output_dir = (args.output_dir or _default_output_dir()).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    result_path = (args.result_json or approval_dir / "live_send_canary_result_redacted.json").resolve()
    closeout_path = (args.closeout_md or approval_dir / "live_send_canary_closeout.md").resolve()
    result_ready = _wait_for_result_files(
        result_path=result_path,
        closeout_path=closeout_path,
        wait_seconds=float(args.wait_seconds),
        poll_seconds=float(args.poll_seconds),
    )

    validation_args = argparse.Namespace(
        approval_dir=approval_dir,
        result_json=result_path,
        closeout_md=closeout_path,
        output_json=output_dir / "live_send_canary_result_validation.json",
        require_green=False,
    )
    validation = validate_live_send_result(validation_args)
    _write_json(output_dir / "live_send_canary_result_validation.json", validation)

    if not result_ready:
        manifest = {
            "gate": YELLOW_RESULT_NOT_READY_GATE,
            "run_at": datetime.now().isoformat(timespec="seconds"),
            "approval_dir": str(approval_dir),
            "live_send_execution_preflight_manifest_path": str(preflight_manifest),
            "result_json_path": str(result_path),
            "closeout_md_path": str(closeout_path),
            "result_ready": False,
            "live_send_validation_gate": validation.get("gate"),
            "post_canary_manifest_path": "",
            "post_canary_gate": "",
            "blockers": ["live_send_result_or_closeout_missing"],
            "exact_next_action": "Wait for the UI helper to write the redacted GREEN live-send result and closeout, then rerun this watch.",
            "customer_send_performed_by_this_helper": False,
            "kaspi_chat_write_allowed": False,
            "google_board_write_allowed": False,
            "db_write_allowed": False,
            "telegram_send_allowed": False,
            "raw_order_id_exported": False,
            "raw_reply_text_exported": False,
        }
        _write_json(output_dir / "manifest.json", manifest)
        _write_text(output_dir / "closeout.md", _closeout(manifest))
        print(json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True))
        return 1

    if validation.get("gate") != LIVE_SEND_ACCEPTED_GATE:
        manifest = {
            "gate": YELLOW_RESULT_NOT_GREEN_GATE,
            "run_at": datetime.now().isoformat(timespec="seconds"),
            "approval_dir": str(approval_dir),
            "live_send_execution_preflight_manifest_path": str(preflight_manifest),
            "result_json_path": str(result_path),
            "closeout_md_path": str(closeout_path),
            "result_ready": True,
            "live_send_validation_gate": validation.get("gate"),
            "post_canary_manifest_path": "",
            "post_canary_gate": "",
            "blockers": [f"live_send_validation_gate={validation.get('gate')}"],
            "exact_next_action": "Fix the redacted live-send result proof or stop; do not retry the customer send automatically.",
            "customer_send_performed_by_this_helper": False,
            "kaspi_chat_write_allowed": False,
            "google_board_write_allowed": False,
            "db_write_allowed": False,
            "telegram_send_allowed": False,
            "raw_order_id_exported": False,
            "raw_reply_text_exported": False,
        }
        _write_json(output_dir / "manifest.json", manifest)
        _write_text(output_dir / "closeout.md", _closeout(manifest))
        print(json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True))
        return 1

    post_canary_dir = output_dir / "post_canary_sequence"
    post_args = [
        "--approval-dir",
        str(approval_dir),
        "--live-send-execution-preflight-manifest",
        str(preflight_manifest),
        "--db",
        str(db_path),
        "--ledger-db",
        str(ledger_path),
        "--target-date",
        str(args.target_date),
        "--lookback-days",
        str(args.lookback_days),
        "--output-dir",
        str(post_canary_dir),
    ]
    if args.resident_session_reuse_manifest:
        post_args.extend(["--resident-session-reuse-manifest", str(args.resident_session_reuse_manifest.resolve())])
    if args.resident_heartbeat_manifest:
        post_args.extend(["--resident-heartbeat-manifest", str(args.resident_heartbeat_manifest.resolve())])
    if args.resident_button_manifest:
        post_args.extend(["--resident-button-manifest", str(args.resident_button_manifest.resolve())])
    if args.open_chat_no_type_packet_manifest:
        post_args.extend(
            ["--open-chat-no-type-packet-manifest", str(args.open_chat_no_type_packet_manifest.resolve())]
        )
    if args.open_chat_no_type_result_validation_json:
        post_args.extend(
            [
                "--open-chat-no-type-result-validation-json",
                str(args.open_chat_no_type_result_validation_json.resolve()),
            ]
        )
    for value in args.reply_poll_window_minutes or []:
        post_args.extend(["--reply-poll-window-minutes", str(value)])
    post_rc = post_canary_sequence_main(post_args)
    post_manifest_path = post_canary_dir / "manifest.json"
    post_manifest = _read_json(post_manifest_path) if post_manifest_path.exists() else {}
    post_gate = str(post_manifest.get("gate") or "MISSING")

    gate = GREEN_GATE if post_rc == 0 and post_gate == POST_CANARY_GREEN_GATE else YELLOW_POST_CANARY_GATE
    blockers = [] if gate == GREEN_GATE else [f"post_canary_gate={post_gate}", f"post_canary_rc={post_rc}"]
    manifest = {
        "gate": gate,
        "run_at": datetime.now().isoformat(timespec="seconds"),
        "approval_dir": str(approval_dir),
        "live_send_execution_preflight_manifest_path": str(preflight_manifest),
        "live_send_execution_preflight_manifest_sha256": _safe_sha(preflight_manifest),
        "result_json_path": str(result_path),
        "closeout_md_path": str(closeout_path),
        "result_ready": True,
        "live_send_validation_gate": validation.get("gate"),
        "post_canary_manifest_path": str(post_manifest_path),
        "post_canary_manifest_sha256": _safe_sha(post_manifest_path),
        "post_canary_gate": post_gate,
        "post_canary_return_code": post_rc,
        "blockers": blockers,
        "exact_next_action": (
            "Review the generated reply-polling approval phrase; no chat read is authorized until the owner approves it exactly."
            if gate == GREEN_GATE
            else "Inspect the post-canary sequence blocker before attempting reply polling or Board staging."
        ),
        "customer_send_performed_by_this_helper": False,
        "kaspi_chat_write_allowed": False,
        "google_board_write_allowed": False,
        "db_write_allowed": False,
        "telegram_send_allowed": False,
        "raw_order_id_exported": False,
        "raw_reply_text_exported": False,
    }
    _write_json(output_dir / "manifest.json", manifest)
    _write_text(output_dir / "closeout.md", _closeout(manifest))
    print(json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if gate == GREEN_GATE else 1


if __name__ == "__main__":
    raise SystemExit(main())
