#!/usr/bin/env python3
"""Build an approval packet for an open-chat/no-type Kaspi side-effect canary.

This builder performs no browser action. It prepares the next proof gate after a
selector-locked no-open button proof: open the one selected customer chat, type
nothing, send nothing, capture sanitized route metadata, then stop.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any

from scripts.probe_kaspi_customer_chat_ui_search_identity_no_send import (  # noqa: E402
    STORE_MERCHANT_ACCOUNT_IDS,
    merchant_account_id_for_store,
)


REPO_ROOT = Path(__file__).resolve().parents[1]
RESIDENT_BUTTON_GATE = "GREEN_KASPI_CUSTOMER_CHAT_MESSAGE_BUTTON_PROVEN_NO_SEND"
SELECTOR_DIAGNOSTIC_GATE = "GREEN_KASPI_CUSTOMER_CHAT_OPEN_SELECTOR_DOM_DIAGNOSTIC_NO_CLICK_READY"
PREFLIGHT_GATE = "GREEN_LIVE_SEND_CANARY_EXECUTION_PREFLIGHT_READY_NO_SEND"
HEARTBEAT_GATE = "GREEN_KASPI_CUSTOMER_CHAT_RESIDENT_NO_SEND_CONTROLLER_READY"
GREEN_GATE = "GREEN_OPEN_CHAT_NO_TYPE_CANARY_PACKET_READY_NO_SEND"
YELLOW_GATE = "YELLOW_OPEN_CHAT_NO_TYPE_CANARY_PACKET_BLOCKED_NO_SEND"
RAW_LONG_NUMBER_RE = re.compile(r"(?<!\d)\d{8,12}(?!\d)")
SAFE_SHA256_REF_RE = re.compile(r"sha256:[0-9a-f]{8,64}", re.IGNORECASE)
SAFE_HEX_DIGEST_RE = re.compile(r"\b[0-9a-f]{32,64}\b", re.IGNORECASE)


def _default_output_dir() -> Path:
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return REPO_ROOT / "exports" / "validation" / f"kaspi_customer_chat_open_no_type_canary_{stamp}"


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


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _selected_button_row(resident_manifest: dict[str, Any]) -> dict[str, Any] | None:
    for row in resident_manifest.get("results") or []:
        if not isinstance(row, dict):
            continue
        if (
            row.get("merchant_account_match_proven") is True
            and row.get("result_or_detail_reached") is True
            and row.get("chat_button_present") is True
            and row.get("chat_opened") is not True
            and row.get("message_text_typed") is not True
            and row.get("message_sent") is not True
            and row.get("raw_order_id_exported") is not True
            and row.get("raw_customer_text_exported") is not True
        ):
            return row
    return None


def _selected_selector_row(selector_manifest: dict[str, Any]) -> dict[str, Any] | None:
    diagnostic = selector_manifest.get("selector_dom_diagnostic") or {}
    if not isinstance(diagnostic, dict):
        return None
    if (
        selector_manifest.get("gate") == SELECTOR_DIAGNOSTIC_GATE
        and selector_manifest.get("merchant_account_match_proven") is True
        and selector_manifest.get("probe_result_or_detail_reached") is True
        and selector_manifest.get("probe_chat_button_present") is True
        and selector_manifest.get("chat_opened") is not True
        and selector_manifest.get("message_text_typed") is not True
        and selector_manifest.get("message_sent") is not True
        and selector_manifest.get("customer_send_performed") is not True
        and selector_manifest.get("kaspi_chat_write_performed") is not True
        and selector_manifest.get("raw_order_id_exported") is not True
        and selector_manifest.get("raw_customer_text_exported") is not True
        and selector_manifest.get("raw_phone_exported") is not True
        and selector_manifest.get("raw_session_material_exported") is not True
        and int(diagnostic.get("visible_enabled_click_target_count") or 0) == 1
        and str(diagnostic.get("recommended_click_selector") or "").strip()
    ):
        return {
            "db_row_id": selector_manifest.get("selected_db_row_id"),
            "order_ref": selector_manifest.get("selected_order_ref"),
            "store_code": selector_manifest.get("selected_store_code"),
            "status_filter": selector_manifest.get("selected_status_filter")
            or "NEW,KASPI_DELIVERY_WAIT_FOR_COURIER,ACCEPTED_BY_MERCHANT,KASPI_DELIVERY_CARGO_ASSEMBLY",
            "merchant_account_match_proven": True,
            "result_or_detail_reached": True,
            "chat_button_present": True,
            "chat_opened": False,
            "message_text_typed": False,
            "message_sent": False,
            "raw_order_id_exported": False,
            "raw_customer_text_exported": False,
            "proof_source": "selector_dom_diagnostic_no_click",
            "recommended_click_selector": diagnostic.get("recommended_click_selector"),
            "visible_enabled_click_target_count": diagnostic.get("visible_enabled_click_target_count"),
        }
    return None


def _unsafe_true_flags(payload: dict[str, Any], *, prefix: str) -> list[str]:
    blockers: list[str] = []
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
        if payload.get(key) is True:
            blockers.append(f"{prefix}_{key}_true")
    return blockers


def _redaction_blockers(payload: Any) -> list[str]:
    def strip_safe_fields(value: Any) -> Any:
        if isinstance(value, dict):
            return {
                key: strip_safe_fields(item)
                for key, item in value.items()
                if not (
                    key == "output_dir"
                    or key.endswith("_path")
                    or key.endswith("_paths")
                    or key.endswith("_sha256")
                )
            }
        if isinstance(value, list):
            return [strip_safe_fields(item) for item in value]
        return value

    text = json.dumps(strip_safe_fields(payload), ensure_ascii=False, sort_keys=True)
    text = SAFE_SHA256_REF_RE.sub("sha256:[redacted-hash]", text)
    text = SAFE_HEX_DIGEST_RE.sub("[redacted-hex-digest]", text)
    for merchant_id in STORE_MERCHANT_ACCOUNT_IDS.values():
        text = text.replace(str(merchant_id), "[merchant-account-id]")
    if RAW_LONG_NUMBER_RE.search(text):
        return ["raw_long_number_detected"]
    return []


def _approval_phrase(manifest: dict[str, Any]) -> str:
    return (
        "I approve KASPI_CUSTOMER_SIZE_OPEN_CHAT_NO_TYPE_SIDE_EFFECT_CANARY_ONE_ORDER_20260618: "
        "after the selector-aware no-open customer-message-button proof and fresh no-send "
        "execution preflight are GREEN, open the Kaspi merchant customer-message UI for exactly "
        "one selected redacted order only, type nothing, send nothing, capture only sanitized "
        "request/response/websocket route metadata, then stop. "
        f"Packet: {manifest['output_dir']}. "
        f"Packet manifest: {manifest['packet_manifest_path']}. "
        f"Packet manifest SHA256: {manifest['packet_manifest_sha256']}. "
        f"No-open selector/button proof SHA256: {manifest['no_open_proof_sha256']}. "
        f"Fresh preflight SHA256: {manifest['live_send_execution_preflight_sha256']}. "
        f"Selected order_ref: {manifest['selected_order_ref']}; "
        f"db_row_id: {manifest['selected_db_row_id']}; "
        f"store: {manifest['selected_store_code']}; "
        f"expected Kaspi merchant account ID: {manifest['expected_merchant_account_id']}; "
        f"merchant status filter: {manifest['selected_status_filter']}. "
        "The browser/helper may resolve the raw order ID only at action time from the local DB, "
        "must not export raw order ID/customer text/phone/address/cookies/tokens/session material, "
        "must prove the visible Kaspi store selector is on that exact merchant account ID before search, "
        "search the exact order, click/open the customer message UI only for that order, do not type, "
        "do not send, do not call direct Kaspi chat write endpoints, record whether any "
        "messageStatus/changeStatus, startChat, typing/sendText, sendMessage, or loadMoreMessages route "
        "appears, leave the resident session open, and stop. No bulk action, no second order, no Google "
        "Board write, no production DB write, no Telegram/WhatsApp send, no workbook write, no scheduler "
        "change, and no unrelated external action is approved."
    )


def build_packet(
    *,
    resident_button_manifest_path: Path | None,
    selector_diagnostic_manifest_path: Path | None,
    live_send_execution_preflight_manifest_path: Path,
    resident_heartbeat_path: Path,
    output_dir: Path,
) -> dict[str, Any]:
    output_dir = output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    blockers: list[str] = []

    resident_manifest = (
        _read_json(resident_button_manifest_path)
        if resident_button_manifest_path and resident_button_manifest_path.exists()
        else {}
    )
    selector_manifest = (
        _read_json(selector_diagnostic_manifest_path)
        if selector_diagnostic_manifest_path and selector_diagnostic_manifest_path.exists()
        else {}
    )
    preflight = (
        _read_json(live_send_execution_preflight_manifest_path)
        if live_send_execution_preflight_manifest_path.exists()
        else {}
    )
    heartbeat = _read_json(resident_heartbeat_path) if resident_heartbeat_path.exists() else {}
    selected = _selected_button_row(resident_manifest) if resident_manifest else None
    proof_source = "resident_button_manifest" if selected is not None else ""
    if selected is None and selector_manifest:
        selected = _selected_selector_row(selector_manifest)
        proof_source = "selector_diagnostic_manifest" if selected is not None else ""

    if not resident_manifest and not selector_manifest:
        blockers.append("no_open_proof_manifest_missing")
    if resident_button_manifest_path and not resident_manifest:
        blockers.append("resident_button_manifest_missing")
    if selector_diagnostic_manifest_path and not selector_manifest:
        blockers.append("selector_diagnostic_manifest_missing")

    if resident_manifest and resident_manifest.get("gate") != RESIDENT_BUTTON_GATE:
        blockers.append("resident_button_manifest_not_green")
    if resident_manifest and int(resident_manifest.get("unsafe_event_count") or 0) != 0:
        blockers.append("resident_button_manifest_has_unsafe_events")
    if resident_manifest:
        blockers.extend(_unsafe_true_flags(resident_manifest, prefix="resident_button_manifest"))

    if selector_manifest:
        if selector_manifest.get("gate") != SELECTOR_DIAGNOSTIC_GATE:
            blockers.append("selector_diagnostic_manifest_not_green")
        if selector_manifest.get("visible_merchant_selector_id") and str(
            selector_manifest.get("visible_merchant_selector_id")
        ) != str(selector_manifest.get("expected_merchant_account_id")):
            blockers.append("selector_diagnostic_visible_merchant_mismatch")
        blockers.extend(_unsafe_true_flags(selector_manifest, prefix="selector_diagnostic_manifest"))
        diagnostic = selector_manifest.get("selector_dom_diagnostic") or {}
        if int(diagnostic.get("visible_enabled_click_target_count") or 0) != 1:
            blockers.append("selector_diagnostic_click_target_count_not_one")
        if not str(diagnostic.get("recommended_click_selector") or "").strip():
            blockers.append("selector_diagnostic_recommended_click_selector_missing")

    if selected is None:
        blockers.append("no_open_proof_manifest_no_qualified_selected_result")

    if not preflight:
        blockers.append("live_send_execution_preflight_manifest_missing")
    elif preflight.get("gate") != PREFLIGHT_GATE:
        blockers.append("live_send_execution_preflight_not_green")
    if preflight:
        if preflight.get("customer_send_performed") is not False:
            blockers.append("preflight_customer_send_performed_not_false")
        if preflight.get("kaspi_chat_write_performed") not in {False, None}:
            blockers.append("preflight_kaspi_chat_write_performed_not_false")

    if not heartbeat:
        blockers.append("resident_heartbeat_missing")
    elif heartbeat.get("gate") != HEARTBEAT_GATE:
        blockers.append("resident_heartbeat_not_green")
    if heartbeat:
        if heartbeat.get("orders_search_input_visible") is not True:
            blockers.append("resident_heartbeat_orders_search_input_not_visible")
        blockers.extend(_unsafe_true_flags(heartbeat, prefix="resident_heartbeat"))

    selected_order_ref = str((selected or {}).get("order_ref") or "")
    selected_db_row_id = (selected or {}).get("db_row_id")
    selected_store_code = str((selected or {}).get("store_code") or "")
    selected_status_filter = str((selected or {}).get("status_filter") or "")
    expected_merchant_account_id = merchant_account_id_for_store(selected_store_code)

    if selected and preflight:
        if str(preflight.get("selected_order_ref") or "") != selected_order_ref:
            blockers.append("preflight_selected_order_ref_mismatch")
        if str(preflight.get("selected_db_row_id") or "") != str(selected_db_row_id):
            blockers.append("preflight_selected_db_row_id_mismatch")
        if str(preflight.get("selected_store_code") or "") != selected_store_code:
            blockers.append("preflight_selected_store_code_mismatch")
        if str(preflight.get("expected_merchant_account_id") or "") != expected_merchant_account_id:
            blockers.append("preflight_expected_merchant_account_id_mismatch")

    if selected and heartbeat and str(heartbeat.get("profile_store_code") or "") != selected_store_code:
        blockers.append("resident_heartbeat_profile_store_mismatch")

    no_open_proof_path = (
        selector_diagnostic_manifest_path
        if proof_source == "selector_diagnostic_manifest"
        else resident_button_manifest_path
    )
    manifest = {
        "gate": YELLOW_GATE,
        "run_at": datetime.now().isoformat(timespec="seconds"),
        "output_dir": str(output_dir),
        "proof_source": proof_source,
        "resident_button_manifest_path": str(resident_button_manifest_path.resolve())
        if resident_button_manifest_path
        else "",
        "resident_button_manifest_sha256": _sha256_file(resident_button_manifest_path)
        if resident_button_manifest_path and resident_button_manifest_path.exists()
        else "",
        "selector_diagnostic_manifest_path": str(selector_diagnostic_manifest_path.resolve())
        if selector_diagnostic_manifest_path
        else "",
        "selector_diagnostic_manifest_sha256": _sha256_file(selector_diagnostic_manifest_path)
        if selector_diagnostic_manifest_path and selector_diagnostic_manifest_path.exists()
        else "",
        "no_open_proof_path": str(no_open_proof_path.resolve()) if no_open_proof_path else "",
        "no_open_proof_sha256": _sha256_file(no_open_proof_path)
        if no_open_proof_path and no_open_proof_path.exists()
        else "",
        "live_send_execution_preflight_path": str(live_send_execution_preflight_manifest_path.resolve()),
        "live_send_execution_preflight_sha256": _sha256_file(live_send_execution_preflight_manifest_path)
        if live_send_execution_preflight_manifest_path.exists()
        else "",
        "resident_heartbeat_path": str(resident_heartbeat_path.resolve()),
        "resident_heartbeat_sha256": _sha256_file(resident_heartbeat_path)
        if resident_heartbeat_path.exists()
        else "",
        "selected_order_ref": selected_order_ref,
        "selected_db_row_id": selected_db_row_id,
        "selected_store_code": selected_store_code,
        "selected_status_filter": selected_status_filter,
        "expected_merchant_account_id": expected_merchant_account_id,
        "approval_phrase_generated": False,
        "customer_send_allowed_now": False,
        "kaspi_chat_write_allowed_now": False,
        "open_chat_future_action_requires_exact_approval": True,
        "read_status_side_effect_risk_acknowledged": True,
        "blockers": sorted(set(blockers)),
        "customer_send_performed": False,
        "kaspi_chat_write_performed": False,
        "chat_opened_by_this_builder": False,
        "message_text_typed": False,
        "message_sent": False,
        "raw_order_id_exported": False,
        "raw_customer_text_exported": False,
        "raw_phone_exported": False,
        "raw_session_material_exported": False,
    }
    manifest["blockers"].extend(_redaction_blockers(manifest))
    manifest["blockers"] = sorted(set(manifest["blockers"]))

    if not manifest["blockers"]:
        manifest["gate"] = GREEN_GATE
        manifest["approval_phrase_generated"] = True

    packet_manifest_path = output_dir / "open_chat_no_type_packet_lock.json"
    packet_manifest = {
        "gate": manifest["gate"],
        "selected_order_ref": selected_order_ref,
        "selected_db_row_id": selected_db_row_id,
        "selected_store_code": selected_store_code,
        "selected_status_filter": selected_status_filter,
        "expected_merchant_account_id": expected_merchant_account_id,
        "resident_button_manifest_path": manifest["resident_button_manifest_path"],
        "resident_button_manifest_sha256": manifest["resident_button_manifest_sha256"],
        "selector_diagnostic_manifest_path": manifest["selector_diagnostic_manifest_path"],
        "selector_diagnostic_manifest_sha256": manifest["selector_diagnostic_manifest_sha256"],
        "proof_source": manifest["proof_source"],
        "no_open_proof_path": manifest["no_open_proof_path"],
        "no_open_proof_sha256": manifest["no_open_proof_sha256"],
        "live_send_execution_preflight_path": manifest["live_send_execution_preflight_path"],
        "live_send_execution_preflight_sha256": manifest[
            "live_send_execution_preflight_sha256"
        ],
        "resident_heartbeat_path": manifest["resident_heartbeat_path"],
        "resident_heartbeat_sha256": manifest["resident_heartbeat_sha256"],
        "customer_send_allowed_now": False,
        "kaspi_chat_write_allowed_now": False,
        "future_action": "open_exactly_one_selected_chat_type_nothing_send_nothing_capture_sanitized_metadata",
        "read_status_side_effect_risk_acknowledged": True,
        "raw_order_id_exported": False,
        "raw_customer_text_exported": False,
        "raw_phone_exported": False,
        "raw_session_material_exported": False,
        "blockers": manifest["blockers"],
    }
    _write_json(packet_manifest_path, packet_manifest)
    manifest["packet_manifest_path"] = str(packet_manifest_path.resolve())
    manifest["packet_manifest_sha256"] = _sha256_file(packet_manifest_path)

    result_template = {
        "gate": "GREEN_OPEN_CHAT_NO_TYPE_SIDE_EFFECT_CANARY_COMPLETED_NO_SEND"
        if manifest["gate"] == GREEN_GATE
        else "YELLOW_OPEN_CHAT_NO_TYPE_SIDE_EFFECT_CANARY_NOT_READY",
        "selected_order_ref": selected_order_ref,
        "selected_db_row_id": selected_db_row_id,
        "selected_store_code": selected_store_code,
        "expected_merchant_account_id": expected_merchant_account_id,
        "merchant_account_match_proven": True,
        "order_search_performed": True,
        "chat_opened": True,
        "message_text_typed": False,
        "message_sent": False,
        "send_message_route_observed": False,
        "typing_send_text_route_observed": False,
        "start_chat_route_observed": False,
        "message_status_change_route_observed": False,
        "load_more_messages_route_observed": False,
        "sanitized_metadata_capture_path": "",
        "raw_order_id_exported": False,
        "raw_customer_text_exported": False,
        "raw_phone_exported": False,
        "raw_session_material_exported": False,
    }

    _write_json(output_dir / "manifest.json", manifest)
    _write_json(output_dir / "open_chat_no_type_result_template_redacted.json", result_template)
    if manifest["approval_phrase_generated"]:
        _write_text(output_dir / "REQUIRED_EXACT_OPEN_CHAT_NO_TYPE_APPROVAL_PHRASE.txt", _approval_phrase(manifest))
    _write_text(output_dir / "closeout.md", _render_closeout(manifest))
    return manifest


def _render_closeout(manifest: dict[str, Any]) -> str:
    blockers = manifest.get("blockers") or []
    lines = [
        "# Kaspi Customer Chat Open-Chat No-Type Canary Packet",
        "",
        f"Gate: {manifest['gate']}",
        "",
        "## Scope",
        "",
        "- This builder performed no browser action.",
        "- Future action, if separately approved: open exactly one selected customer-message UI, type nothing, send nothing, capture sanitized metadata, and stop.",
        f"- Store: `{manifest.get('selected_store_code')}`",
        f"- Required selector: `ID - {manifest.get('expected_merchant_account_id')}`",
        f"- DB row: `{manifest.get('selected_db_row_id')}`",
        f"- Order ref: `{manifest.get('selected_order_ref')}`",
        f"- Proof source: `{manifest.get('proof_source')}`",
        f"- No-open proof: `{manifest.get('no_open_proof_path')}`",
        "",
        "## Safety",
        "",
        "- Customer send performed: false",
        "- Kaspi chat write performed: false",
        "- Chat opened by this builder: false",
        "- Message text typed: false",
        "- Message sent: false",
        "- Raw order/customer/session material exported: false",
        "",
        "## Blockers",
        "",
    ]
    lines.extend([f"- {blocker}" for blocker in blockers] if blockers else ["- none"])
    lines.extend(
        [
            "",
            "## Next Gate",
            "",
            "- Do not execute the open-chat/no-type canary unless the exact approval phrase is provided.",
            "- If executed, treat any `messageStatus/changeStatus` route as a read-side-effect signal and record it explicitly.",
        ]
    )
    return "\n".join(lines) + "\n"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--resident-button-manifest", type=Path)
    parser.add_argument("--selector-diagnostic-manifest", type=Path)
    parser.add_argument("--live-send-execution-preflight-manifest", type=Path, required=True)
    parser.add_argument("--resident-heartbeat", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, default=None)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    manifest = build_packet(
        resident_button_manifest_path=args.resident_button_manifest,
        selector_diagnostic_manifest_path=args.selector_diagnostic_manifest,
        live_send_execution_preflight_manifest_path=args.live_send_execution_preflight_manifest,
        resident_heartbeat_path=args.resident_heartbeat,
        output_dir=args.output_dir or _default_output_dir(),
    )
    print(json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if manifest["gate"] == GREEN_GATE else 1


if __name__ == "__main__":
    raise SystemExit(main())
