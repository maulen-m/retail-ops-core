#!/usr/bin/env python3
"""Fail-closed preflight for Kaspi customer-size reply polling.

This script does not open Kaspi, read chats, type, or send messages. It creates
the execution checkpoint for the post-send reply-polling phase:

- local ledger must contain already-sent/pollable rows;
- resident browser reuse gate must be GREEN;
- an exact owner approval phrase is generated and optionally matched.

Opening a Kaspi chat can have customer-visible/read-status side effects, so
reply polling is intentionally approval-gated even though it never sends.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

from scripts.probe_kaspi_customer_chat_ui_search_identity_no_send import (  # noqa: E402
    merchant_account_id_for_store,
)


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_LEDGER_DB = (
    REPO_ROOT
    / "runtime"
    / "customer_size_request_ledger"
    / "no_send_customer_size_request_ledger.sqlite"
)
DEFAULT_RESIDENT_REUSE_MANIFEST = (
    REPO_ROOT
    / "exports"
    / "validation"
    / "kaspi_customer_chat_resident_session_reuse_20260617_current"
    / "manifest.json"
)
POLLABLE_STATUSES = {"REQUEST_SENT", "POLLING"}
GREEN_GATE = "GREEN_REPLY_POLLING_EXECUTION_PREFLIGHT_READY_NO_SEND"
YELLOW_NO_TARGETS_GATE = "YELLOW_REPLY_POLLING_EXECUTION_PREFLIGHT_NO_POLLABLE_ROWS_NO_SEND"
YELLOW_AWAITING_APPROVAL_GATE = "YELLOW_REPLY_POLLING_EXECUTION_PREFLIGHT_AWAITING_OWNER_APPROVAL_NO_SEND"
BLOCKED_GATE = "YELLOW_REPLY_POLLING_EXECUTION_PREFLIGHT_BLOCKED_NO_SEND"
RED_GATE = "RED_REPLY_POLLING_EXECUTION_PREFLIGHT_UNSAFE_NO_SEND"
SESSION_REUSE_GATE = "GREEN_KASPI_CUSTOMER_CHAT_RESIDENT_SESSION_REUSE_READY_NO_SEND"


def _default_output_dir() -> Path:
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return REPO_ROOT / "exports" / "validation" / f"kaspi_reply_polling_execution_preflight_{stamp}"


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _sha256_json(payload: Any) -> str:
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return _sha256_text(raw)


def _load_supplied_phrase(args: argparse.Namespace) -> tuple[str, str]:
    if args.approval_text_file:
        return args.approval_text_file.read_text(encoding="utf-8").strip(), "file"
    if args.approval_from_stdin:
        return sys.stdin.read().strip(), "stdin"
    return "", "not_supplied"


def _load_ledger_targets(ledger_db: Path, *, limit: int | None) -> tuple[list[dict[str, Any]], list[str]]:
    try:
        from core.ops.customer_size_request import export_customer_size_ledger_snapshot
    except ImportError as exc:  # pragma: no cover - import failure is environment-specific
        return [], [f"customer_size_module_import_failed:{type(exc).__name__}"]

    if not ledger_db.exists():
        return [], ["ledger_db_missing"]
    rows = export_customer_size_ledger_snapshot(ledger_db)
    targets = [
        row
        for row in rows
        if str(row.get("status") or "").strip().upper() in POLLABLE_STATUSES
    ]
    targets.sort(
        key=lambda row: (
            str(row.get("request_sent_at") or row.get("updated_at") or ""),
            str(row.get("store_code") or ""),
            str(row.get("order_ref") or ""),
        )
    )
    if limit is not None:
        targets = targets[: max(0, limit)]
    redacted: list[dict[str, Any]] = []
    for index, row in enumerate(targets, start=1):
        store_code = row.get("store_code")
        redacted.append(
            {
                "sequence": index,
                "ledger_key": row.get("ledger_key"),
                "order_ref": row.get("order_ref"),
                "db_row_id": row.get("db_row_id"),
                "store_code": store_code,
                "requires_matching_merchant_account": True,
                "expected_merchant_account_id": merchant_account_id_for_store(store_code),
                "sku_key": row.get("sku_key"),
                "sku_id": row.get("sku_id"),
                "status": row.get("status"),
                "request_sent_at": row.get("request_sent_at"),
                "last_observed_at": row.get("last_observed_at"),
                "raw_order_id_exported": False,
                "raw_reply_text_exported": False,
                "customer_send_allowed": False,
                "kaspi_chat_write_allowed": False,
                "google_board_write_allowed": False,
                "db_write_allowed": False,
                "telegram_send_allowed": False,
            }
        )
    return redacted, []


def _approval_phrase(*, target_count: int, targets_sha256: str, resident_manifest: Path, ledger_db: Path) -> str:
    return (
        "I approve KASPI_CUSTOMER_SIZE_REPLY_POLLING_EXECUTION_NO_SEND: open/read only "
        f"{target_count} already-sent Kaspi customer-size chat target(s) from the redacted poll target packet, "
        "using the resident authenticated Kaspi browser session, solely to observe customer replies and feed "
        "transient reply text into the local parser. For each target, select or confirm the visible Kaspi "
        "merchant-account dropdown exactly matches that target's expected_merchant_account_id before searching "
        "or opening chat; if the dropdown does not match, stop without searching that order. Do not type or send any customer message, do not call direct "
        "Kaspi chat write endpoints, do not export raw order IDs/customer text/phones/addresses/cookies/tokens/"
        "session material, do not write Google Board/production DB/CRM/workbook, do not send Telegram/WhatsApp, "
        "and stop after local redacted evidence. "
        f"Poll target SHA256: {targets_sha256}. "
        f"Resident session reuse manifest: {resident_manifest}. "
        f"Ledger DB: {ledger_db}."
    )


def build_preflight(
    *,
    ledger_db: Path,
    resident_reuse_manifest: Path,
    output_dir: Path,
    supplied_approval_text: str,
    approval_source: str,
    limit: int | None = None,
) -> dict[str, Any]:
    blockers: list[str] = []
    unsafe_blockers: list[str] = []
    resident: dict[str, Any] = {}
    if resident_reuse_manifest.exists():
        resident = _read_json(resident_reuse_manifest)
    else:
        blockers.append("resident_session_reuse_manifest_missing")

    if resident and resident.get("gate") != SESSION_REUSE_GATE:
        blockers.append("resident_session_reuse_not_green")
    if resident:
        invariants = resident.get("no_send_invariants") or {}
        for key in [
            "customer_send_allowed",
            "kaspi_chat_write_allowed",
            "chat_open_allowed",
            "message_text_typed",
            "message_sent",
            "raw_order_id_exported",
            "raw_customer_text_exported",
            "raw_phone_exported",
            "raw_session_material_exported",
        ]:
            if invariants.get(key) is not False:
                unsafe_blockers.append(f"resident_reuse_invariant_{key}_not_false")

    targets, ledger_blockers = _load_ledger_targets(ledger_db, limit=limit)
    blockers.extend(ledger_blockers)
    targets_sha = _sha256_json(targets)
    expected_phrase = (
        _approval_phrase(
            target_count=len(targets),
            targets_sha256=targets_sha,
            resident_manifest=resident_reuse_manifest,
            ledger_db=ledger_db,
        )
        if targets
        else ""
    )
    phrase_supplied = bool(supplied_approval_text)
    phrase_matches = bool(expected_phrase and supplied_approval_text == expected_phrase)
    if phrase_supplied and not phrase_matches:
        unsafe_blockers.append("owner_approval_text_mismatch")

    for row in targets:
        if not row.get("expected_merchant_account_id"):
            unsafe_blockers.append("target_store_has_no_known_merchant_account_id")
        if row.get("raw_order_id_exported") is not False:
            unsafe_blockers.append("target_raw_order_id_exported_not_false")
        if row.get("raw_reply_text_exported") is not False:
            unsafe_blockers.append("target_raw_reply_text_exported_not_false")

    gate = GREEN_GATE
    if unsafe_blockers:
        gate = RED_GATE
    elif blockers:
        gate = BLOCKED_GATE
    elif not targets:
        gate = YELLOW_NO_TARGETS_GATE
    elif not phrase_matches:
        gate = YELLOW_AWAITING_APPROVAL_GATE

    return {
        "gate": gate,
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "ledger_db": str(ledger_db),
        "resident_session_reuse_manifest": str(resident_reuse_manifest),
        "output_dir": str(output_dir),
        "poll_target_count": len(targets),
        "poll_targets_sha256": targets_sha,
        "poll_targets_redacted": targets,
        "approval_phrase_generated": bool(expected_phrase),
        "approval_phrase_sha256": _sha256_text(expected_phrase) if expected_phrase else "",
        "owner_approval_text_source": approval_source,
        "owner_approval_text_supplied": phrase_supplied,
        "owner_approval_text_match": phrase_matches,
        "blockers": blockers,
        "unsafe_blockers": unsafe_blockers,
        "customer_send_performed": False,
        "customer_send_allowed_by_this_preflight": False,
        "chat_open_allowed_by_this_preflight": False,
        "kaspi_chat_write_allowed_by_this_preflight": False,
        "google_board_write_allowed": False,
        "db_write_allowed": False,
        "telegram_send_allowed": False,
        "raw_order_id_exported": False,
        "raw_reply_text_exported": False,
        "raw_phone_exported": False,
        "raw_session_material_exported": False,
        "_expected_approval_phrase": expected_phrase,
    }


def _build_closeout(report: dict[str, Any], manifest_path: Path, phrase_path: Path | None) -> str:
    lines = [
        "# Kaspi Customer Size Reply Polling Execution Preflight",
        "",
        f"Gate: {report['gate']}",
        "",
        "## Scope",
        "",
        "Read-only/no-send preflight for polling replies after size-request messages have already been sent. This preflight does not open Kaspi or read chats.",
        "",
        "## Checks",
        "",
        f"- Resident session reuse manifest: `{report['resident_session_reuse_manifest']}`",
        f"- Ledger DB: `{report['ledger_db']}`",
        f"- Poll target count: {report['poll_target_count']}",
        f"- Poll target SHA256: `{report['poll_targets_sha256']}`",
        f"- Owner approval supplied: {str(report['owner_approval_text_supplied']).lower()}",
        f"- Owner approval exact match: {str(report['owner_approval_text_match']).lower()}",
        "",
    ]
    if phrase_path:
        lines.extend(["## Required Exact Owner Approval", "", f"- Phrase path: `{phrase_path}`", ""])
    lines.extend(
        [
            "## Safety",
            "",
            "- Customer send performed: false",
            "- Customer send allowed by this preflight: false",
            "- Chat open allowed by this preflight: false",
            "- Kaspi chat write allowed by this preflight: false",
            "- Google Board/DB/Telegram writes allowed: false",
            "- Raw order IDs/customer replies/phones/session material exported: false",
            "",
            "## Evidence",
            "",
            f"- Manifest: `{manifest_path}`",
            "",
        ]
    )
    blockers = [*(report.get("unsafe_blockers") or []), *(report.get("blockers") or [])]
    if blockers:
        lines.extend(["## Blockers", ""])
        lines.extend(f"- {blocker}" for blocker in blockers)
        lines.append("")
    return "\n".join(lines)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ledger-db", type=Path, default=DEFAULT_LEDGER_DB)
    parser.add_argument("--resident-session-reuse-manifest", type=Path, default=DEFAULT_RESIDENT_REUSE_MANIFEST)
    parser.add_argument("--output-dir", type=Path, default=None)
    parser.add_argument("--limit", type=int)
    approval_group = parser.add_mutually_exclusive_group()
    approval_group.add_argument("--approval-text-file", type=Path)
    approval_group.add_argument("--approval-from-stdin", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    output_dir = (args.output_dir or _default_output_dir()).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    supplied_approval_text, approval_source = _load_supplied_phrase(args)
    report = build_preflight(
        ledger_db=args.ledger_db.resolve(),
        resident_reuse_manifest=args.resident_session_reuse_manifest.resolve(),
        output_dir=output_dir,
        supplied_approval_text=supplied_approval_text,
        approval_source=approval_source,
        limit=args.limit,
    )
    expected_phrase = str(report.pop("_expected_approval_phrase", "") or "")
    phrase_path: Path | None = None
    if expected_phrase:
        phrase_path = output_dir / "REQUIRED_EXACT_REPLY_POLLING_APPROVAL_PHRASE.txt"
        _write_text(phrase_path, expected_phrase + "\n")
    _write_json(output_dir / "reply_poll_targets_redacted.json", report["poll_targets_redacted"])
    manifest_path = output_dir / "manifest.json"
    closeout_path = output_dir / "closeout.md"
    _write_json(manifest_path, report)
    _write_text(closeout_path, _build_closeout(report, manifest_path, phrase_path))
    print(json.dumps({"gate": report["gate"], "manifest_path": str(manifest_path), "closeout_path": str(closeout_path)}, ensure_ascii=False, indent=2, sort_keys=True))
    if report["gate"].startswith("RED_"):
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
