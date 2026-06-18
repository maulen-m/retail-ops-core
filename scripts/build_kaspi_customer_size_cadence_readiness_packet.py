#!/usr/bin/env python3
"""Build the no-apply cadence/readiness packet for Kaspi customer size requests.

This packet connects the already-built pieces into one operational sequence:

1. keep finding missing-size orders early,
2. prove/perform the Kaspi chat lane separately,
3. poll for replies,
4. turn reply classifications into Google Board MY_SIZE patch rows,
5. let the existing Google Board/waybill closeout gates resume shipping.

It does not send customer messages, install schedulers, write Google Sheets, write
the production app DB, or send Telegram/WhatsApp bundles.
"""
from __future__ import annotations

import argparse
import csv
import json
from datetime import date, datetime
from pathlib import Path
from typing import Any, Mapping

from core.ops.customer_size_request import (
    build_customer_size_next_actions,
    export_customer_size_ledger_snapshot,
    sha256_file,
    summarize_customer_size_ledger,
)


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DB = REPO_ROOT / "db" / "app.db"
DEFAULT_LEDGER_DB = (
    REPO_ROOT
    / "runtime"
    / "customer_size_request_ledger"
    / "no_send_customer_size_request_ledger.sqlite"
)
DEFAULT_REPLY_POLL_WINDOWS_MINUTES = (10, 30, 60, 120)
OPEN_CHAT_PACKET_GREEN_GATE = "GREEN_OPEN_CHAT_NO_TYPE_CANARY_PACKET_READY_NO_SEND"
OPEN_CHAT_RESULT_ACCEPTED_GATE = "GREEN_OPEN_CHAT_NO_TYPE_CANARY_RESULT_ACCEPTED_NO_SEND"


def _parse_date(value: str | None) -> date:
    if not value:
        return date.today()
    return datetime.strptime(value, "%Y-%m-%d").date()


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames: list[str] = []
    for row in rows:
        for key in row:
            if key not in fieldnames:
                fieldnames.append(key)
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


def _safe_sha(path: Path) -> str | None:
    return sha256_file(path) if path.exists() else None


def _default_output_dir(target_date: date) -> Path:
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return (
        REPO_ROOT
        / "exports"
        / "validation"
        / f"kaspi_customer_size_cadence_readiness_{target_date.isoformat()}_{stamp}"
    )


def _latest_matching_file(pattern: str) -> Path | None:
    matches = [path for path in REPO_ROOT.glob(pattern) if path.is_file()]
    if not matches:
        return None
    return max(matches, key=lambda path: path.stat().st_mtime)


def _load_json(path: Path | None) -> dict[str, Any] | None:
    if not path or not path.exists():
        return None
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"Expected object JSON at {path}")
    return data


def _manifest_count(manifest: Mapping[str, Any] | None, key: str) -> int:
    if not manifest:
        return 0
    try:
        return int(manifest.get(key) or 0)
    except (TypeError, ValueError):
        return 0


def _gate_is_green(value: Any) -> bool:
    return str(value or "").strip().upper().startswith("GREEN")


def build_cadence_slots(
    *,
    summary: Mapping[str, Any],
    patch_manifest: Mapping[str, Any] | None,
    live_ui_validation: Mapping[str, Any] | None,
    open_chat_packet: Mapping[str, Any] | None,
    open_chat_result_validation: Mapping[str, Any] | None,
    cadence_minutes: int,
    reply_poll_windows_minutes: tuple[int, ...],
) -> list[dict[str, Any]]:
    patch_rows = _manifest_count(patch_manifest, "patch_rows_count")
    patch_blockers = _manifest_count(patch_manifest, "blockers_count")
    classification_ready = int(summary.get("google_board_size_fill_ready_count") or 0)
    pending_live_send = int(summary.get("pending_live_send_canary_count") or 0)
    reply_poll_pending = int(summary.get("reply_poll_pending_count") or 0)
    manual_review_required = int(summary.get("manual_review_required_count") or 0)
    live_ui_gate = str((live_ui_validation or {}).get("gate") or "MISSING")
    live_ui_ready = _gate_is_green(live_ui_gate)
    open_chat_packet_gate = str((open_chat_packet or {}).get("gate") or "MISSING")
    open_chat_result_gate = str((open_chat_result_validation or {}).get("gate") or "MISSING")
    open_chat_ready = open_chat_result_gate == OPEN_CHAT_RESULT_ACCEPTED_GATE
    patch_gate = str((patch_manifest or {}).get("gate") or "MISSING")

    slots: list[dict[str, Any]] = [
        {
            "sequence": 10,
            "stage": "missing_size_detection_refresh",
            "cadence": f"every_{cadence_minutes}_minutes_during_active_order_windows",
            "current_count": int(summary.get("ledger_rows") or 0),
            "status": "READY_NO_APPLY",
            "allowed_now": True,
            "external_write_allowed": False,
            "command_hint": "scripts/run_kaspi_customer_size_request_scheduler_preflight.py",
            "purpose": "refresh local redacted ledger for new missing-size orders early",
        },
        {
            "sequence": 20,
            "stage": "live_ui_no_send_canary",
            "cadence": "before_first_customer_send_lane",
            "current_count": pending_live_send,
            "status": "READY_PROVEN_NO_SEND" if live_ui_ready else "WAITING_ON_LIVE_UI_NO_SEND_PROOF",
            "allowed_now": live_ui_ready,
            "external_write_allowed": False,
            "evidence_gate": live_ui_gate,
            "purpose": "prove selected Kaspi order customer-message button without typing or sending",
        },
        {
            "sequence": 30,
            "stage": "open_chat_no_type_side_effect_canary",
            "cadence": "after_live_ui_no_send_proof_before_any_send_lane",
            "current_count": 1 if open_chat_packet else 0,
            "status": (
                "ACCEPTED_NO_SEND"
                if open_chat_ready
                else "WAITING_ON_OPEN_CHAT_NO_TYPE_RESULT"
                if open_chat_packet
                else "PACKET_MISSING"
            ),
            "allowed_now": open_chat_ready,
            "external_write_allowed": False,
            "packet_gate": open_chat_packet_gate,
            "result_gate": open_chat_result_gate,
            "required_result_gate": OPEN_CHAT_RESULT_ACCEPTED_GATE,
            "purpose": (
                "prove opening exactly one selected Kaspi customer chat creates no typing/send "
                "drift and record any read-status/history side effects before the send lane"
            ),
        },
        {
            "sequence": 40,
            "stage": "customer_size_request_send_lane",
            "cadence": "as_early_as_possible_after_order_detection_after_separate_owner_approval",
            "current_count": pending_live_send,
            "status": (
                "BLOCKED_NO_LIVE_SEND_APPROVAL"
                if open_chat_ready
                else "BLOCKED_OPEN_CHAT_NO_TYPE_RESULT_NOT_ACCEPTED"
            ),
            "allowed_now": False,
            "external_write_allowed": False,
            "required_future_approval": (
                "exact live-send approval phrase plus proven no-send UI/API gate plus accepted "
                "open-chat/no-type result"
            ),
            "required_prerequisites": [
                "live_ui_no_send_canary_green",
                "open_chat_no_type_result_accepted",
            ],
            "open_chat_no_type_result_gate": open_chat_result_gate,
            "template_hash_only": True,
            "purpose": "send size-request template through approved Kaspi customer chat lane",
        },
        {
            "sequence": 50,
            "stage": "reply_polling_windows",
            "cadence": ",".join(f"T+{minute}m" for minute in reply_poll_windows_minutes),
            "current_count": reply_poll_pending,
            "status": "READY_AFTER_REQUEST_SENT" if reply_poll_pending else "IDLE_UNTIL_REQUEST_SENT",
            "allowed_now": bool(reply_poll_pending),
            "external_write_allowed": False,
            "purpose": "repeat result gathers after send so customer replies can be captured before shipping",
        },
        {
            "sequence": 60,
            "stage": "reply_classification_and_size_decision",
            "cadence": "after_each_reply_poll",
            "current_count": classification_ready,
            "status": "READY_ROWS_PRESENT" if classification_ready else "IDLE_UNTIL_REPLY_CLASSIFIED",
            "allowed_now": bool(classification_ready),
            "external_write_allowed": False,
            "purpose": "convert reply facts to internal size using existing size table without raw reply export",
        },
        {
            "sequence": 70,
            "stage": "google_board_my_size_patch_packet",
            "cadence": "after_classification_ready_rows",
            "current_count": patch_rows,
            "status": (
                "READY_NO_WRITE_PATCH_ROWS"
                if patch_rows and patch_blockers == 0
                else "HAS_BLOCKERS_NO_WRITE"
                if patch_blockers
                else "NO_READY_PATCH_ROWS"
            ),
            "allowed_now": patch_rows > 0 and patch_blockers == 0,
            "external_write_allowed": False,
            "evidence_gate": patch_gate,
            "purpose": "produce operator/agent patch rows for SalesRaw_Today.MY_SIZE",
        },
        {
            "sequence": 80,
            "stage": "google_ops_board_size_writeback",
            "cadence": "existing_scheduled_windows_or_manual_after_board_cell_fill",
            "current_count": patch_rows,
            "status": "WAITING_FOR_BOARD_CELL_WRITE_AND_EXISTING_APPLY_GATE",
            "allowed_now": False,
            "external_write_allowed": False,
            "command_hint": "scripts/run_google_ops_board_size_writeback_scheduler.py",
            "purpose": "sync filled SalesRaw_Today.MY_SIZE into fact_orders_kaspi.assigned_size under existing gate",
        },
        {
            "sequence": 90,
            "stage": "telegram_pdf_waybill_closeout",
            "cadence": "after_no_blank_my_size_and_run_control_ready",
            "current_count": 0,
            "status": "BLOCKED_UNTIL_GOOGLE_BOARD_SIZING_GREEN",
            "allowed_now": False,
            "external_write_allowed": False,
            "purpose": "resume existing waybill/PDF Telegram workflow only after sizing gate is green",
        },
    ]

    if manual_review_required:
        slots.append(
            {
                "sequence": 55,
                "stage": "manual_reply_review_no_size_signal",
                "cadence": "after_each_reply_poll",
                "current_count": manual_review_required,
                "status": "MANUAL_REVIEW_REQUIRED",
                "allowed_now": False,
                "external_write_allowed": False,
                "purpose": "handle replies that lack usable height, weight, or explicit size",
            }
        )
    return sorted(slots, key=lambda row: int(row["sequence"]))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument("--ledger-db", type=Path, default=DEFAULT_LEDGER_DB)
    parser.add_argument("--target-date", help="YYYY-MM-DD. Defaults to today.")
    parser.add_argument("--recommended-cadence-minutes", type=int, default=10)
    parser.add_argument(
        "--reply-poll-windows-minutes",
        default=",".join(str(value) for value in DEFAULT_REPLY_POLL_WINDOWS_MINUTES),
        help="Comma-separated post-send poll windows, e.g. 10,30,60,120.",
    )
    parser.add_argument("--live-ui-validation-json", type=Path)
    parser.add_argument("--open-chat-no-type-packet-manifest", type=Path)
    parser.add_argument("--open-chat-no-type-result-validation-json", type=Path)
    parser.add_argument("--google-board-patch-manifest", type=Path)
    parser.add_argument("--output-dir", type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    target_date = _parse_date(args.target_date)
    output_dir = args.output_dir or _default_output_dir(target_date)
    output_dir.mkdir(parents=True, exist_ok=True)

    db_path = args.db.resolve()
    ledger_path = args.ledger_db.resolve()
    db_sha_before = _safe_sha(db_path)
    ledger_sha_before = _safe_sha(ledger_path)

    live_validation_path = args.live_ui_validation_json
    if live_validation_path is None:
        live_validation_path = _latest_matching_file(
            "exports/validation/kaspi_customer_chat_live_canary_packet_*/live_ui_canary_result_validation*.json"
        )
    open_chat_packet_path = args.open_chat_no_type_packet_manifest
    if open_chat_packet_path is None:
        open_chat_packet_path = _latest_matching_file(
            "exports/validation/kaspi_customer_chat_open_no_type_canary_*/manifest.json"
        )
    open_chat_result_validation_path = args.open_chat_no_type_result_validation_json
    if open_chat_result_validation_path is None:
        open_chat_result_validation_path = _latest_matching_file(
            "exports/validation/kaspi_customer_chat_open_no_type_result_validation_*/"
            "open_chat_no_type_result_validation.json"
        )
    patch_manifest_path = args.google_board_patch_manifest
    if patch_manifest_path is None:
        patch_manifest_path = _latest_matching_file(
            "exports/validation/kaspi_customer_size_google_board_patch_packet_*/manifest.json"
        )

    live_ui_validation = _load_json(live_validation_path)
    open_chat_packet = _load_json(open_chat_packet_path)
    open_chat_result_validation = _load_json(open_chat_result_validation_path)
    patch_manifest = _load_json(patch_manifest_path)
    ledger_snapshot_rows = export_customer_size_ledger_snapshot(ledger_path)
    next_actions = build_customer_size_next_actions(ledger_snapshot_rows)
    summary = summarize_customer_size_ledger(ledger_snapshot_rows)
    reply_windows = tuple(
        int(value.strip())
        for value in str(args.reply_poll_windows_minutes or "").split(",")
        if value.strip()
    )
    cadence_slots = build_cadence_slots(
        summary=summary,
        patch_manifest=patch_manifest,
        live_ui_validation=live_ui_validation,
        open_chat_packet=open_chat_packet,
        open_chat_result_validation=open_chat_result_validation,
        cadence_minutes=args.recommended_cadence_minutes,
        reply_poll_windows_minutes=reply_windows or DEFAULT_REPLY_POLL_WINDOWS_MINUTES,
    )

    blockers: list[dict[str, Any]] = []
    if not live_ui_validation:
        blockers.append({"blocker": "live_ui_no_send_canary_validation_missing"})
    elif not _gate_is_green(live_ui_validation.get("gate")):
        blockers.append(
            {
                "blocker": "live_ui_no_send_canary_not_green",
                "gate": live_ui_validation.get("gate"),
            }
        )
    if not open_chat_packet:
        blockers.append({"blocker": "open_chat_no_type_packet_missing"})
    elif open_chat_packet.get("gate") != OPEN_CHAT_PACKET_GREEN_GATE:
        blockers.append(
            {
                "blocker": "open_chat_no_type_packet_not_green",
                "gate": open_chat_packet.get("gate"),
            }
        )
    if not open_chat_result_validation:
        blockers.append({"blocker": "open_chat_no_type_result_validation_missing"})
    elif open_chat_result_validation.get("gate") != OPEN_CHAT_RESULT_ACCEPTED_GATE:
        blockers.append(
            {
                "blocker": "open_chat_no_type_result_not_accepted",
                "gate": open_chat_result_validation.get("gate"),
            }
        )
    if patch_manifest and _manifest_count(patch_manifest, "blockers_count"):
        blockers.append(
            {
                "blocker": "google_board_patch_packet_has_blockers",
                "blockers_count": _manifest_count(patch_manifest, "blockers_count"),
                "gate": patch_manifest.get("gate"),
            }
        )

    db_sha_after = _safe_sha(db_path)
    ledger_sha_after = _safe_sha(ledger_path)
    gate = (
        "YELLOW_CUSTOMER_SIZE_CADENCE_READY_WITH_RETAINED_BLOCKERS_NO_APPLY"
        if blockers
        else "GREEN_CUSTOMER_SIZE_CADENCE_PACKET_READY_NO_APPLY"
    )

    _write_json(output_dir / "ledger_summary.json", summary)
    _write_json(output_dir / "next_actions_redacted.json", next_actions)
    _write_json(output_dir / "cadence_slots_no_apply.json", cadence_slots)
    _write_csv(output_dir / "cadence_slots_no_apply.csv", cadence_slots)
    _write_json(output_dir / "retained_blockers.json", blockers)

    manifest = {
        "gate": gate,
        "run_at": datetime.now().isoformat(timespec="seconds"),
        "target_date": target_date.isoformat(),
        "recommended_cadence_minutes": args.recommended_cadence_minutes,
        "reply_poll_windows_minutes": list(reply_windows or DEFAULT_REPLY_POLL_WINDOWS_MINUTES),
        "db_path": str(db_path),
        "db_sha256_before": db_sha_before,
        "db_sha256_after": db_sha_after,
        "db_unchanged": db_sha_before == db_sha_after,
        "ledger_db_path": str(ledger_path),
        "ledger_sha256_before": ledger_sha_before,
        "ledger_sha256_after": ledger_sha_after,
        "ledger_snapshot_rows": len(ledger_snapshot_rows),
        "next_action_rows": len(next_actions),
        "cadence_slot_rows": len(cadence_slots),
        "ledger_summary": summary,
        "live_ui_validation_json": str(live_validation_path) if live_validation_path else None,
        "live_ui_validation_gate": (live_ui_validation or {}).get("gate"),
        "open_chat_no_type_packet_manifest": str(open_chat_packet_path)
        if open_chat_packet_path
        else None,
        "open_chat_no_type_packet_gate": (open_chat_packet or {}).get("gate"),
        "open_chat_no_type_result_validation_json": str(open_chat_result_validation_path)
        if open_chat_result_validation_path
        else None,
        "open_chat_no_type_result_gate": (open_chat_result_validation or {}).get("gate"),
        "open_chat_no_type_required_result_gate": OPEN_CHAT_RESULT_ACCEPTED_GATE,
        "google_board_patch_manifest": str(patch_manifest_path) if patch_manifest_path else None,
        "google_board_patch_gate": (patch_manifest or {}).get("gate"),
        "google_board_patch_rows_count": _manifest_count(patch_manifest, "patch_rows_count"),
        "google_board_patch_blockers_count": _manifest_count(patch_manifest, "blockers_count"),
        "retained_blockers_count": len(blockers),
        "scheduler_installed": False,
        "scheduler_change_allowed": False,
        "customer_send_allowed": False,
        "kaspi_chat_write_allowed": False,
        "google_board_write_allowed": False,
        "db_write_allowed": False,
        "telegram_send_allowed": False,
        "whatsapp_send_allowed": False,
        "raw_order_ids_exported": False,
        "raw_reply_text_exported": False,
    }
    _write_json(output_dir / "manifest.json", manifest)

    closeout_lines = [
        "# Kaspi Customer Size Cadence Readiness Packet",
        "",
        f"Gate: {gate}",
        "",
        f"- Output folder: {output_dir}",
        f"- Ledger rows: {len(ledger_snapshot_rows)}",
        f"- Next actions: {len(next_actions)}",
        f"- Cadence slots: {len(cadence_slots)}",
        f"- Live UI validation gate: {(live_ui_validation or {}).get('gate') or 'missing'}",
        f"- Open-chat/no-type packet gate: {(open_chat_packet or {}).get('gate') or 'missing'}",
        f"- Open-chat/no-type result gate: {(open_chat_result_validation or {}).get('gate') or 'missing'}",
        f"- Google Board patch gate: {(patch_manifest or {}).get('gate') or 'missing'}",
        f"- Google Board patch rows: {_manifest_count(patch_manifest, 'patch_rows_count')}",
        f"- Retained blockers: {len(blockers)}",
        f"- App DB unchanged: {db_sha_before == db_sha_after}",
        "",
        "No customer messages, Kaspi UI/API writes, Google Board writes, DB writes,",
        "Telegram/WhatsApp sends, workbook writes, scheduler changes, raw order ID",
        "exports, or raw reply text exports happened.",
        "",
    ]
    if blockers:
        closeout_lines.extend(["Retained blockers:", ""])
        for blocker in blockers:
            closeout_lines.append(f"- {blocker['blocker']}")
        closeout_lines.append("")
    (output_dir / "closeout.md").write_text("\n".join(closeout_lines), encoding="utf-8")

    print(json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
