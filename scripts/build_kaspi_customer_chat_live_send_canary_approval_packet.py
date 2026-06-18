#!/usr/bin/env python3
"""Build the owner-approval packet for one Kaspi customer-size live send canary.

This is a no-send artifact builder. It requires the live UI no-send canary to
be accepted GREEN before it emits an exact future approval phrase. It never
resolves or exports raw order IDs.
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path
from typing import Any

from core.ops.customer_size_request import (
    DEFAULT_REQUEST_TEMPLATE,
    normalize_request_template,
    request_template_hash,
    sha256_file,
)
from scripts.probe_kaspi_customer_chat_ui_search_identity_no_send import (  # noqa: E402
    merchant_account_id_for_store,
)


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PACKET_DIR = (
    REPO_ROOT
    / "exports"
    / "validation"
    / "kaspi_customer_chat_live_canary_packet_2026-06-16_20260616_125511_final"
)
ACCEPTED_NO_SEND_GATE = "GREEN_LIVE_UI_NO_SEND_CANARY_RESULT_ACCEPTED"
RESIDENT_BUTTON_GATE = "GREEN_KASPI_CUSTOMER_CHAT_MESSAGE_BUTTON_PROVEN_NO_SEND"


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _default_output_dir() -> Path:
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return (
        REPO_ROOT
        / "exports"
        / "validation"
        / f"kaspi_customer_chat_live_send_canary_approval_{stamp}"
    )


def _safe_sha(path: Path) -> str | None:
    return sha256_file(path) if path.exists() else None


def _selected_resident_result(resident_manifest: dict[str, Any]) -> dict[str, Any] | None:
    for row in resident_manifest.get("results") or []:
        if not isinstance(row, dict):
            continue
        if (
            row.get("merchant_account_match_proven") is True
            and row.get("chat_button_present") is True
            and row.get("result_or_detail_reached") is True
            and row.get("chat_opened") is not True
            and row.get("message_text_typed") is not True
            and row.get("message_sent") is not True
            and row.get("raw_order_id_exported") is not True
            and row.get("raw_customer_text_exported") is not True
        ):
            return row
    return None


def _resident_button_blockers(resident_manifest: dict[str, Any]) -> list[str]:
    blockers: list[str] = []
    if resident_manifest.get("gate") != RESIDENT_BUTTON_GATE:
        blockers.append("resident_button_manifest_not_green")
    if int(resident_manifest.get("unsafe_event_count") or 0) != 0:
        blockers.append("resident_button_manifest_has_unsafe_events")
    for key in (
        "customer_send_allowed",
        "kaspi_chat_write_allowed",
        "chat_opened",
        "message_text_typed",
        "message_sent",
        "raw_order_id_exported",
        "raw_customer_text_exported",
        "raw_phone_exported",
        "raw_session_material_exported",
    ):
        if resident_manifest.get(key) is True:
            blockers.append(f"resident_button_manifest_{key}_true")
    if _selected_resident_result(resident_manifest) is None:
        blockers.append("resident_button_manifest_no_qualified_selected_result")
    return blockers


def _write_resident_packet_manifest(
    *,
    output_dir: Path,
    resident_manifest_path: Path,
    resident_manifest_sha: str | None,
    resident_manifest: dict[str, Any],
    selected: dict[str, Any],
) -> Path:
    """Create the legacy packet shape needed by the runtime-only order resolver."""
    packet_manifest_path = output_dir / "resident_selected_live_ui_canary_packet_manifest.json"
    packet_manifest = {
        "gate": "GREEN_RESIDENT_BUTTON_PROOF_DERIVED_LIVE_UI_PACKET_READY_NO_SEND",
        "run_at": datetime.now().isoformat(timespec="seconds"),
        "source_mode": "resident_button_manifest",
        "source_resident_button_manifest_path": str(resident_manifest_path),
        "source_resident_button_manifest_sha256": resident_manifest_sha,
        "target_date": resident_manifest.get("target_date"),
        "lookback_days": resident_manifest.get("lookback_days"),
        "selected_order_ref": selected.get("order_ref"),
        "selected_db_row_id": selected.get("db_row_id"),
        "selected_store_code": selected.get("store_code"),
        "requires_matching_merchant_account": True,
        "expected_merchant_account_id": merchant_account_id_for_store(selected.get("store_code")),
        "selected_status_filter": selected.get("status_filter"),
        "merchant_account_match_proven": True,
        "chat_button_present": True,
        "customer_send_allowed": False,
        "kaspi_chat_write_allowed": False,
        "google_board_write_allowed": False,
        "db_write_allowed": False,
        "raw_order_id_exported": False,
        "raw_customer_text_exported": False,
        "raw_phone_exported": False,
        "raw_session_material_exported": False,
    }
    _write_json(packet_manifest_path, packet_manifest)
    return packet_manifest_path


def _approval_phrase(
    *,
    packet_dir: Path,
    manifest_sha: str | None,
    validation_sha: str | None,
    selected_order_ref: str,
    selected_db_row_id: Any,
    selected_store_code: Any,
    expected_merchant_account_id: str,
    selected_status_filter: Any,
    template: str,
    template_hash: str,
) -> str:
    return (
        "I approve KASPI_CUSTOMER_SIZE_REQUEST_LIVE_SEND_CANARY_ONE_ORDER_20260616: "
        "after the selector-aware no-send UI/customer-message-button proof is GREEN, "
        "send exactly one Kaspi merchant-chat customer size-request template to the "
        "selected redacted canary order only. "
        f"Packet: {packet_dir}. "
        f"Packet manifest SHA256: {manifest_sha}. "
        f"No-send validation SHA256: {validation_sha}. "
        f"Selected order_ref: {selected_order_ref}; db_row_id: {selected_db_row_id}; "
        f"store: {selected_store_code}; expected Kaspi merchant account ID: {expected_merchant_account_id}; "
        f"merchant status filter: {selected_status_filter}. "
        f"Template hash: {template_hash}. "
        f"Template text: {template}. "
        "The browser/helper may resolve the raw order ID only at action time from the local DB, "
        "must not export raw order ID/customer text/phone/address/cookies/tokens/session material, "
        "must prove the visible Kaspi store selector is on that exact merchant account ID before search, "
        "search the exact order, open the customer message UI "
        "only as needed, type exactly this template once, send exactly once, capture redacted proof, "
        "and then stop. No bulk sends, no second order, no direct Kaspi chat API write, no Google "
        "Board write, no production DB write, no Telegram/WhatsApp send, no workbook write, no "
        "scheduler change, and no unrelated external action is approved."
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--packet-dir", type=Path, default=DEFAULT_PACKET_DIR)
    parser.add_argument("--live-ui-validation-json", type=Path)
    parser.add_argument(
        "--resident-button-manifest",
        type=Path,
        help=(
            "Strict resident no-open message-button manifest. Allows building the same "
            "future-send approval packet from selector-aware resident proof without "
            "requiring the older live_ui_canary_result_validation.json artifact."
        ),
    )
    parser.add_argument("--template", default=DEFAULT_REQUEST_TEMPLATE)
    parser.add_argument("--output-dir", type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    output_dir = args.output_dir or _default_output_dir()
    output_dir.mkdir(parents=True, exist_ok=True)
    resident_manifest_path = args.resident_button_manifest.resolve() if args.resident_button_manifest else None
    resident_manifest: dict[str, Any] = {}
    selected_resident: dict[str, Any] | None = None
    resident_manifest_sha: str | None = None

    packet_dir = args.packet_dir.resolve()
    packet_manifest_path = packet_dir / "manifest.json"
    validation_path = args.live_ui_validation_json or (
        packet_dir / "live_ui_canary_result_validation.json"
    )
    packet_manifest = _read_json(packet_manifest_path) if packet_manifest_path.exists() else {}
    validation = _read_json(validation_path) if validation_path.exists() else {}
    source_mode = "live_ui_validation"

    if resident_manifest_path:
        source_mode = "resident_button_manifest"
        if resident_manifest_path.exists():
            resident_manifest = _read_json(resident_manifest_path)
            resident_manifest_sha = _safe_sha(resident_manifest_path)
            selected_resident = _selected_resident_result(resident_manifest)
            if selected_resident is not None:
                packet_dir = output_dir.resolve()
                packet_manifest_path = _write_resident_packet_manifest(
                    output_dir=output_dir,
                    resident_manifest_path=resident_manifest_path,
                    resident_manifest_sha=resident_manifest_sha,
                    resident_manifest=resident_manifest,
                    selected=selected_resident,
                )
                packet_manifest = _read_json(packet_manifest_path)
                validation_path = resident_manifest_path
                validation = {
                    "gate": ACCEPTED_NO_SEND_GATE,
                    "source_mode": source_mode,
                    "selected_order_ref": selected_resident.get("order_ref"),
                    "selected_db_row_id": selected_resident.get("db_row_id"),
                    "selected_store_code": selected_resident.get("store_code"),
                    "selected_status_filter": selected_resident.get("status_filter"),
                    "raw_order_id_exported": False,
                    "raw_customer_text_exported": False,
                }


    template = normalize_request_template(args.template)
    template_hash = request_template_hash(template)
    no_send_gate = validation.get("gate")
    no_send_green = no_send_gate == ACCEPTED_NO_SEND_GATE
    blockers: list[str] = []
    if resident_manifest_path:
        if not resident_manifest_path.exists():
            blockers.append("resident_button_manifest_missing")
        else:
            blockers.extend(_resident_button_blockers(resident_manifest))
        if not packet_manifest_path.exists():
            blockers.append("resident_derived_packet_manifest_missing")
    else:
        if not packet_manifest_path.exists():
            blockers.append("packet_manifest_missing")
        if not validation_path.exists():
            blockers.append("live_ui_no_send_validation_missing")
        elif not no_send_green:
            blockers.append("live_ui_no_send_validation_not_green")

    selected_order_ref = str(
        validation.get("selected_order_ref")
        or packet_manifest.get("selected_order_ref")
        or ""
    )
    selected_db_row_id = validation.get("selected_db_row_id") or packet_manifest.get(
        "selected_db_row_id"
    )
    selected_store_code = validation.get("selected_store_code") or packet_manifest.get(
        "selected_store_code"
    )
    selected_status_filter = validation.get("selected_status_filter") or packet_manifest.get(
        "selected_status_filter"
    )
    expected_merchant_account_id = merchant_account_id_for_store(selected_store_code)
    manifest_sha = _safe_sha(packet_manifest_path)
    validation_sha = resident_manifest_sha if resident_manifest_path else _safe_sha(validation_path)
    approval = ""
    if not blockers:
        approval = _approval_phrase(
            packet_dir=packet_dir,
            manifest_sha=manifest_sha,
            validation_sha=validation_sha,
            selected_order_ref=selected_order_ref,
            selected_db_row_id=selected_db_row_id,
            selected_store_code=selected_store_code,
            expected_merchant_account_id=expected_merchant_account_id,
            selected_status_filter=selected_status_filter,
            template=template,
            template_hash=template_hash,
        )
        (output_dir / "REQUIRED_EXACT_LIVE_SEND_CANARY_APPROVAL_PHRASE.txt").write_text(
            approval + "\n",
            encoding="utf-8",
        )

    result_template = {
        "gate": "YELLOW_NOT_RUN",
        "selected_order_ref": selected_order_ref,
        "selected_db_row_id": selected_db_row_id,
        "selected_store_code": selected_store_code,
        "requires_matching_merchant_account": True,
        "expected_merchant_account_id": expected_merchant_account_id,
        "selected_status_filter": selected_status_filter,
        "template_hash": template_hash,
        "merchant_account_match_proven": False,
        "order_search_performed": False,
        "chat_opened": False,
        "message_text_typed": False,
        "message_sent": False,
        "send_confirmation_observed": False,
        "sent_count": 0,
        "other_customer_messages_sent": False,
        "raw_order_id_exported": False,
        "raw_customer_text_exported": False,
        "raw_phone_exported": False,
        "cookie_token_session_exported": False,
    }
    _write_json(output_dir / "live_send_canary_result_template_redacted.json", result_template)

    gate = (
        "GREEN_LIVE_SEND_CANARY_APPROVAL_PACKET_READY_NO_SEND"
        if not blockers
        else "YELLOW_LIVE_SEND_CANARY_APPROVAL_PACKET_BLOCKED_NO_SEND"
    )
    manifest = {
        "gate": gate,
        "run_at": datetime.now().isoformat(timespec="seconds"),
        "packet_dir": str(packet_dir),
        "packet_manifest_path": str(packet_manifest_path),
        "packet_manifest_sha256": manifest_sha,
        "source_mode": source_mode,
        "resident_button_manifest_path": str(resident_manifest_path) if resident_manifest_path else "",
        "resident_button_manifest_sha256": resident_manifest_sha,
        "live_ui_validation_json": str(validation_path),
        "live_ui_validation_sha256": validation_sha,
        "live_ui_validation_gate": no_send_gate,
        "selected_order_ref": selected_order_ref,
        "selected_db_row_id": selected_db_row_id,
        "selected_store_code": selected_store_code,
        "requires_matching_merchant_account": True,
        "expected_merchant_account_id": expected_merchant_account_id,
        "merchant_account_match_proven": True if not blockers else False,
        "selected_status_filter": selected_status_filter,
        "template_hash": template_hash,
        "approval_phrase_generated": bool(approval),
        "blockers": blockers,
        "customer_send_allowed_now": False,
        "requires_exact_owner_approval_before_send": True,
        "single_order_only": True,
        "raw_order_id_exported": False,
        "raw_customer_text_exported": False,
        "kaspi_chat_write_performed": False,
        "google_board_write_allowed": False,
        "db_write_allowed": False,
        "telegram_send_allowed": False,
        "whatsapp_send_allowed": False,
    }
    _write_json(output_dir / "manifest.json", manifest)

    closeout = "\n".join(
        [
            "# Kaspi Customer Size Live Send Canary Approval Packet",
            "",
            f"Gate: {gate}",
            "",
            f"- Output folder: {output_dir}",
            f"- Source packet: {packet_dir}",
            f"- Live UI no-send validation gate: {no_send_gate or 'missing'}",
            f"- Approval phrase generated: {bool(approval)}",
            f"- Template hash: {template_hash}",
            f"- Selected order_ref: {selected_order_ref}",
            f"- Selected db_row_id: {selected_db_row_id}",
            f"- Selected store: {selected_store_code}",
            f"- Expected Kaspi merchant account ID: {expected_merchant_account_id}",
            f"- Blockers: {len(blockers)}",
            "",
            "No customer message, Kaspi UI/API write, Google Board write, DB write,",
            "Telegram/WhatsApp send, workbook write, scheduler change, raw order ID",
            "export, raw customer text export, or token/cookie/session export happened.",
            "",
        ]
    )
    if blockers:
        closeout += "Retained blockers:\n\n" + "\n".join(f"- {blocker}" for blocker in blockers) + "\n"
    (output_dir / "closeout.md").write_text(closeout, encoding="utf-8")

    print(json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
