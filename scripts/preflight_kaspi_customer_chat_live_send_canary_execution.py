#!/usr/bin/env python3
"""Fail-closed preflight for the one-order Kaspi live-send canary.

This script performs no browser action and sends no customer message. It checks
the exact artifacts that must be true before a future UI-capable helper can
execute the one-order canary:

- approval packet is GREEN;
- exact owner approval phrase is present and matches, when supplied;
- resident browser reuse gate is GREEN;
- current resident heartbeat is GREEN when provided;
- local duplicate ledger says this order/template has not already been sent.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

from scripts.probe_kaspi_customer_chat_ui_search_identity_no_send import (  # noqa: E402
    STORE_MERCHANT_ACCOUNT_IDS,
    merchant_account_id_for_store,
)


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_APPROVAL_DIR = (
    REPO_ROOT
    / "exports"
    / "validation"
    / "kaspi_customer_chat_live_send_canary_approval_AFTER_RESIDENT_GREEN_NO_SEND_20260617_1845"
)
DEFAULT_RESIDENT_REUSE_MANIFEST = (
    REPO_ROOT
    / "exports"
    / "validation"
    / "kaspi_customer_chat_resident_session_reuse_20260617_current"
    / "manifest.json"
)
DEFAULT_RESIDENT_HEARTBEAT = (
    REPO_ROOT
    / "exports"
    / "validation"
    / "kaspi_customer_chat_resident_no_send_controller_current"
    / "resident_controller_heartbeat.json"
)
DEFAULT_LEDGER_DB = (
    REPO_ROOT
    / "runtime"
    / "customer_size_request_ledger"
    / "no_send_customer_size_request_ledger.sqlite"
)
GREEN_GATE = "GREEN_LIVE_SEND_CANARY_EXECUTION_PREFLIGHT_READY_NO_SEND"
YELLOW_GATE = "YELLOW_LIVE_SEND_CANARY_EXECUTION_PREFLIGHT_AWAITING_OWNER_APPROVAL_NO_SEND"
BLOCKED_GATE = "YELLOW_LIVE_SEND_CANARY_EXECUTION_PREFLIGHT_BLOCKED_NO_SEND"
RED_GATE = "RED_LIVE_SEND_CANARY_EXECUTION_PREFLIGHT_UNSAFE_NO_SEND"
APPROVAL_GATE = "GREEN_LIVE_SEND_CANARY_APPROVAL_PACKET_READY_NO_SEND"
SESSION_REUSE_GATE = "GREEN_KASPI_CUSTOMER_CHAT_RESIDENT_SESSION_REUSE_READY_NO_SEND"
RESIDENT_HEARTBEAT_GATE = "GREEN_KASPI_CUSTOMER_CHAT_RESIDENT_NO_SEND_CONTROLLER_READY"
POST_SEND_OR_REPLY_STATUSES = {
    "REQUEST_SENT",
    "POLLING",
    "REPLY_OBSERVED",
    "REPLY_OBSERVED_NO_SIZE_SIGNAL",
    "CLASSIFICATION_READY",
    "SIZE_CONFIRMED",
    "UNKNOWN_SEND_OUTCOME",
    "SEND_IN_PROGRESS",
}


def _default_output_dir() -> Path:
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return REPO_ROOT / "exports" / "validation" / f"kaspi_live_send_canary_execution_preflight_{stamp}"


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


def _sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _load_expected_phrase(approval_dir: Path) -> tuple[str, Path]:
    phrase_path = approval_dir / "REQUIRED_EXACT_LIVE_SEND_CANARY_APPROVAL_PHRASE.txt"
    if not phrase_path.exists():
        return "", phrase_path
    return phrase_path.read_text(encoding="utf-8").strip(), phrase_path


def _load_supplied_phrase(args: argparse.Namespace) -> tuple[str, str]:
    if args.approval_text_file:
        return args.approval_text_file.read_text(encoding="utf-8").strip(), "file"
    if args.approval_from_stdin:
        return sys.stdin.read().strip(), "stdin"
    return "", "not_supplied"


def _read_ledger_match(
    ledger_db: Path,
    *,
    order_ref: str,
    template_hash: str,
) -> tuple[list[dict[str, Any]], list[str]]:
    blockers: list[str] = []
    if not ledger_db.exists():
        return [], ["ledger_db_missing"]
    try:
        conn = sqlite3.connect(f"file:{ledger_db.resolve()}?mode=ro", uri=True)
        conn.row_factory = sqlite3.Row
        try:
            rows = conn.execute(
                """
                SELECT ledger_key, order_ref, template_hash, status, db_row_id, store_code,
                       raw_order_id_exported, raw_reply_text_exported
                FROM customer_size_request_ledger
                WHERE order_ref = ?
                  AND template_hash = ?
                ORDER BY updated_at DESC, ledger_key
                """,
                (order_ref, template_hash),
            ).fetchall()
        finally:
            conn.close()
    except sqlite3.Error as exc:
        return [], [f"ledger_read_failed:{type(exc).__name__}"]
    result = [dict(row) for row in rows]
    if not result:
        blockers.append("ledger_row_missing_for_selected_order_template")
    return result, blockers


def _check_current_resident_heartbeat(
    resident_heartbeat_path: Path | None,
) -> tuple[dict[str, Any], list[str], list[str]]:
    """Validate the freshest resident controller state before a future send.

    The older session-reuse manifest proves a reusable profile existed. The
    current heartbeat proves the browser is presently on a safe, search-ready
    surface. Treat the heartbeat as a fail-closed freshness guard when supplied.
    """
    blockers: list[str] = []
    unsafe_blockers: list[str] = []
    if resident_heartbeat_path is None:
        return {}, blockers, unsafe_blockers
    if not resident_heartbeat_path.exists():
        return {}, ["resident_current_heartbeat_missing"], unsafe_blockers
    heartbeat = _read_json(resident_heartbeat_path)
    if heartbeat.get("gate") != RESIDENT_HEARTBEAT_GATE:
        blockers.append("resident_current_heartbeat_not_green")
    if heartbeat.get("browser_should_remain_open") is not True:
        blockers.append("resident_current_heartbeat_browser_should_remain_open_not_true")
    if heartbeat.get("persistent_profile_mode") is not True:
        blockers.append("resident_current_heartbeat_persistent_profile_mode_not_true")
    if heartbeat.get("orders_search_input_visible") is not True:
        blockers.append("resident_current_heartbeat_orders_search_input_not_visible")
    for key in [
        "customer_send_allowed",
        "kaspi_chat_write_allowed",
        "chat_opened",
        "message_text_typed",
        "message_sent",
        "raw_order_id_exported",
        "raw_customer_text_exported",
        "raw_phone_exported",
        "raw_session_material_exported",
    ]:
        if heartbeat.get(key) is not False:
            unsafe_blockers.append(f"resident_current_heartbeat_invariant_{key}_not_false")
    return heartbeat, blockers, unsafe_blockers


def build_preflight(
    *,
    approval_dir: Path,
    resident_reuse_manifest_path: Path,
    ledger_db: Path,
    output_dir: Path,
    supplied_approval_text: str,
    approval_source: str,
    resident_heartbeat_path: Path | None = None,
) -> dict[str, Any]:
    blockers: list[str] = []
    unsafe_blockers: list[str] = []
    approval_manifest_path = approval_dir / "manifest.json"
    expected_phrase, expected_phrase_path = _load_expected_phrase(approval_dir)

    approval_manifest: dict[str, Any] = {}
    if approval_manifest_path.exists():
        approval_manifest = _read_json(approval_manifest_path)
    else:
        blockers.append("approval_manifest_missing")

    resident_reuse: dict[str, Any] = {}
    if resident_reuse_manifest_path.exists():
        resident_reuse = _read_json(resident_reuse_manifest_path)
    else:
        blockers.append("resident_session_reuse_manifest_missing")
    resident_heartbeat, heartbeat_blockers, heartbeat_unsafe_blockers = _check_current_resident_heartbeat(
        resident_heartbeat_path
    )
    blockers.extend(heartbeat_blockers)
    unsafe_blockers.extend(heartbeat_unsafe_blockers)

    selected_order_ref = str(approval_manifest.get("selected_order_ref") or "")
    selected_store_code = str(approval_manifest.get("selected_store_code") or "")
    expected_merchant_account_id = merchant_account_id_for_store(selected_store_code)
    template_hash = str(approval_manifest.get("template_hash") or "")
    ledger_matches: list[dict[str, Any]] = []
    if selected_order_ref and template_hash:
        ledger_matches, ledger_blockers = _read_ledger_match(
            ledger_db,
            order_ref=selected_order_ref,
            template_hash=template_hash,
        )
        blockers.extend(ledger_blockers)
    elif approval_manifest:
        blockers.append("approval_manifest_missing_selected_order_ref_or_template_hash")

    if approval_manifest and approval_manifest.get("gate") != APPROVAL_GATE:
        blockers.append("approval_packet_not_green")
    if approval_manifest and approval_manifest.get("approval_phrase_generated") is not True:
        blockers.append("approval_phrase_not_generated")
    if not expected_phrase:
        blockers.append("expected_approval_phrase_file_missing_or_empty")
    if approval_manifest:
        if not expected_merchant_account_id:
            blockers.append("selected_store_has_no_known_merchant_account_id")
        manifest_expected = str(approval_manifest.get("expected_merchant_account_id") or "")
        if manifest_expected and manifest_expected != expected_merchant_account_id:
            unsafe_blockers.append("approval_manifest_expected_merchant_account_id_mismatch")
        if (
            approval_manifest.get("merchant_account_match_proven") is False
            or approval_manifest.get("requires_matching_merchant_account") is False
        ):
            unsafe_blockers.append("approval_manifest_does_not_require_proven_merchant_account_match")

    if resident_reuse and resident_reuse.get("gate") != SESSION_REUSE_GATE:
        blockers.append("resident_session_reuse_not_green")
    if resident_reuse:
        invariants = resident_reuse.get("no_send_invariants") or {}
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

    if ledger_matches:
        for row in ledger_matches:
            status = str(row.get("status") or "").strip().upper()
            if status in POST_SEND_OR_REPLY_STATUSES:
                unsafe_blockers.append(f"ledger_status_already_after_send_or_reply:{status}")
            if bool(row.get("raw_order_id_exported")):
                unsafe_blockers.append("ledger_raw_order_id_exported_true")
            if bool(row.get("raw_reply_text_exported")):
                unsafe_blockers.append("ledger_raw_reply_text_exported_true")

    phrase_supplied = bool(supplied_approval_text)
    phrase_matches = bool(expected_phrase and supplied_approval_text == expected_phrase)
    if phrase_supplied and not phrase_matches:
        unsafe_blockers.append("owner_approval_text_mismatch")

    gate = GREEN_GATE
    if unsafe_blockers:
        gate = RED_GATE
    elif blockers:
        gate = BLOCKED_GATE
    elif not phrase_matches:
        gate = YELLOW_GATE

    report = {
        "gate": gate,
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "approval_dir": str(approval_dir),
        "approval_manifest_path": str(approval_manifest_path),
        "resident_session_reuse_manifest_path": str(resident_reuse_manifest_path),
        "resident_current_heartbeat_path": str(resident_heartbeat_path) if resident_heartbeat_path else "",
        "resident_current_heartbeat_gate": resident_heartbeat.get("gate", ""),
        "resident_current_heartbeat_recorded_at": resident_heartbeat.get("recorded_at", ""),
        "resident_current_heartbeat_orders_search_input_visible": resident_heartbeat.get(
            "orders_search_input_visible"
        ),
        "resident_current_heartbeat_safe_current_url": resident_heartbeat.get("safe_current_url", ""),
        "ledger_db": str(ledger_db),
        "output_dir": str(output_dir),
        "selected_order_ref": selected_order_ref,
        "selected_db_row_id": approval_manifest.get("selected_db_row_id"),
        "selected_store_code": selected_store_code,
        "requires_matching_merchant_account": True,
        "expected_merchant_account_id": expected_merchant_account_id,
        "merchant_selector_map": STORE_MERCHANT_ACCOUNT_IDS,
        "template_hash": template_hash,
        "expected_approval_phrase_path": str(expected_phrase_path),
        "expected_approval_phrase_sha256": _sha256_text(expected_phrase) if expected_phrase else "",
        "owner_approval_text_source": approval_source,
        "owner_approval_text_supplied": phrase_supplied,
        "owner_approval_text_match": phrase_matches,
        "ledger_match_count": len(ledger_matches),
        "ledger_matches_redacted": ledger_matches,
        "blockers": blockers,
        "unsafe_blockers": unsafe_blockers,
        "customer_send_performed": False,
        "customer_send_allowed_by_this_preflight": False,
        "kaspi_chat_write_allowed_by_this_preflight": False,
        "google_board_write_allowed": False,
        "db_write_allowed": False,
        "telegram_send_allowed": False,
        "raw_order_id_exported": False,
        "raw_customer_text_exported": False,
        "raw_phone_exported": False,
        "raw_session_material_exported": False,
    }
    return report


def _build_closeout(report: dict[str, Any], manifest_path: Path) -> str:
    lines = [
        "# Kaspi Customer Size Live Send Canary Execution Preflight",
        "",
        f"Gate: {report['gate']}",
        "",
        "## Scope",
        "",
        "Read-only/no-send preflight for the already prepared one-order Kaspi customer-size live-send canary.",
        "",
        "## Checks",
        "",
        f"- Approval manifest: `{report['approval_manifest_path']}`",
        f"- Resident session reuse manifest: `{report['resident_session_reuse_manifest_path']}`",
        f"- Current resident heartbeat: `{report.get('resident_current_heartbeat_path')}`",
        f"- Current resident heartbeat gate: `{report.get('resident_current_heartbeat_gate')}`",
        f"- Current resident heartbeat recorded at: `{report.get('resident_current_heartbeat_recorded_at')}`",
        f"- Current resident order search visible: {str(report.get('resident_current_heartbeat_orders_search_input_visible')).lower()}",
        f"- Ledger DB: `{report['ledger_db']}`",
        f"- Selected store: `{report.get('selected_store_code')}`",
        f"- Required visible merchant selector ID: `{report.get('expected_merchant_account_id')}`",
        f"- Selected DB row: `{report.get('selected_db_row_id')}`",
        f"- Ledger match count: {report.get('ledger_match_count')}",
        f"- Owner approval supplied: {str(report.get('owner_approval_text_supplied')).lower()}",
        f"- Owner approval exact match: {str(report.get('owner_approval_text_match')).lower()}",
        f"- Exact approval phrase path: `{report.get('expected_approval_phrase_path')}`",
        "",
        "## Safety",
        "",
        "- Customer send performed: false",
        "- Kaspi chat write allowed by this preflight: false",
        "- Google Board/DB/Telegram writes allowed: false",
        "- Raw order IDs/customer text/phones/session material exported: false",
        "",
        "## Store Selector Map",
        "",
        *(
            f"- `{store} -> ID - {merchant_id}`"
            for store, merchant_id in sorted((report.get("merchant_selector_map") or {}).items())
        ),
        "",
        "## Evidence",
        "",
        f"- Manifest: `{manifest_path}`",
        "",
    ]
    blockers = [*(report.get("unsafe_blockers") or []), *(report.get("blockers") or [])]
    if blockers:
        lines.extend(["## Blockers", ""])
        lines.extend(f"- {blocker}" for blocker in blockers)
        lines.append("")
    return "\n".join(lines)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--approval-dir", type=Path, default=DEFAULT_APPROVAL_DIR)
    parser.add_argument("--resident-session-reuse-manifest", type=Path, default=DEFAULT_RESIDENT_REUSE_MANIFEST)
    parser.add_argument(
        "--resident-current-heartbeat",
        type=Path,
        default=DEFAULT_RESIDENT_HEARTBEAT,
        help=(
            "Fresh resident controller heartbeat. Pass an empty string only for "
            "unit tests or historical artifact validation; live preflight should "
            "use the default fail-closed current heartbeat."
        ),
    )
    parser.add_argument("--ledger-db", type=Path, default=DEFAULT_LEDGER_DB)
    parser.add_argument("--output-dir", type=Path, default=None)
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
        approval_dir=args.approval_dir.resolve(),
        resident_reuse_manifest_path=args.resident_session_reuse_manifest.resolve(),
        resident_heartbeat_path=(
            args.resident_current_heartbeat.resolve()
            if str(args.resident_current_heartbeat or "").strip()
            else None
        ),
        ledger_db=args.ledger_db.resolve(),
        output_dir=output_dir,
        supplied_approval_text=supplied_approval_text,
        approval_source=approval_source,
    )
    manifest_path = output_dir / "manifest.json"
    closeout_path = output_dir / "closeout.md"
    _write_json(manifest_path, report)
    _write_text(closeout_path, _build_closeout(report, manifest_path))
    print(json.dumps({"gate": report["gate"], "manifest_path": str(manifest_path), "closeout_path": str(closeout_path)}, ensure_ascii=False, indent=2, sort_keys=True))
    if report["gate"].startswith("RED_"):
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
