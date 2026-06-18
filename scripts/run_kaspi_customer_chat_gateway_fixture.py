#!/usr/bin/env python3
"""Local fixture gateway for future Kaspi customer-chat automation.

This script is deliberately not a live Kaspi client. It models the safety
contract that any future browser-resident indirect API sender must satisfy
before a real one-order canary is considered.

Default mode is no-send. Send-capable fixture branches require both:

- ``ENABLE_KASPI_CUSTOMER_CHAT_GATEWAY_FIXTURE_SEND=1``
- an approval phrase containing
  ``KASPI_CUSTOMER_CHAT_GATEWAY_FIXTURE_SEND_APPROVED``

Even in send fixture mode, no external network call is made and only redacted
artifacts are written.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sqlite3
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.ops.customer_size_request import DEFAULT_REQUEST_TEMPLATE, request_template_hash


SEND_ENV_GATE = "ENABLE_KASPI_CUSTOMER_CHAT_GATEWAY_FIXTURE_SEND"
APPROVAL_TOKEN = "KASPI_CUSTOMER_CHAT_GATEWAY_FIXTURE_SEND_APPROVED"
CHANNEL = "KASPI_MERCHANT_CHAT_BROWSER_RESIDENT_FIXTURE"
GREEN_NO_SEND_GATE = "GREEN_KASPI_CUSTOMER_CHAT_GATEWAY_FIXTURE_NO_SEND"
GREEN_SEND_GATE = "GREEN_KASPI_CUSTOMER_CHAT_GATEWAY_FIXTURE_SEND_SIMULATED"
GREEN_CASES_GATE = "GREEN_KASPI_CUSTOMER_CHAT_GATEWAY_FIXTURE_CASES_PASSED"
YELLOW_BLOCKED_GATE = "YELLOW_KASPI_CUSTOMER_CHAT_GATEWAY_FIXTURE_SEND_BLOCKED"
YELLOW_UNKNOWN_GATE = "YELLOW_KASPI_CUSTOMER_CHAT_GATEWAY_FIXTURE_UNKNOWN_SEND_OUTCOME"
YELLOW_METADATA_GATE = "YELLOW_CUSTOMER_CHAT_METADATA_CAPTURE_INCOMPLETE_NO_SEND"
RED_UNSAFE_GATE = "RED_KASPI_CUSTOMER_CHAT_GATEWAY_FIXTURE_UNSAFE_ARTIFACT"
RED_CASES_GATE = "RED_KASPI_CUSTOMER_CHAT_GATEWAY_FIXTURE_CASES_FAILED"
RED_METADATA_GATE = "RED_CUSTOMER_CHAT_METADATA_CAPTURE_UNSAFE"
BLOCKING_PRIOR_STATUSES = {
    "SEND_IN_PROGRESS",
    "REQUEST_SENT",
    "POLLING",
    "REPLY_OBSERVED",
    "REPLY_OBSERVED_NO_SIZE_SIGNAL",
    "CLASSIFICATION_READY",
    "SIZE_CONFIRMED",
    "UNKNOWN_SEND_OUTCOME",
}
DEFAULT_ORDER_REF = "sha256:fixture-order-ref"
FIXTURE_CASE_REQUIRED_KEYS = {
    "case_id",
    "stage",
    "target",
    "command_flags",
    "approval",
    "ledger_before",
    "transport_events",
    "expected",
}
ROUTE_RED_BLOCKERS = {
    "sendMessage": "send_message_route_observed",
    "messages/sendMessage": "send_message_route_observed",
    "send_message_write_risk": "send_message_route_observed",
    "typing/sendText": "typing_send_text_route_observed",
    "typing_write_risk": "typing_send_text_route_observed",
    "group/startChat": "start_chat_route_observed",
    "start_chat_write_risk": "start_chat_route_observed",
    "messageStatus/changeStatus": "message_status_change_route_observed_read_side_effect_unknown",
    "message_status_read_side_effect_risk": "message_status_change_route_observed_read_side_effect_unknown",
}
ROUTE_YELLOW_MARKERS = {
    "history/loadMoreMessages",
    "load_more_messages",
    "history_read_risk",
}

PHONE_RE = re.compile(
    r"(?<!\d)(?:\+?7|8)\D{0,3}\d{3}\D{0,3}\d{3}\D{0,3}\d{2}\D{0,3}\d{2}(?!\d)"
)
RAW_LONG_NUMBER_RE = re.compile(r"(?<!\d)\d{8,12}(?!\d)")
SECRET_VALUE_RE = re.compile(r"(bearer\s+[A-Za-z0-9._-]+|eyJ[A-Za-z0-9._-]+)", re.IGNORECASE)
FORBIDDEN_SECRET_KEYS = {
    "headers",
    "request_body",
    "response_body",
    "cookie",
    "cookie_value",
    "authorization",
    "auth_header",
    "auth_value",
    "bearer",
    "token",
    "csrf",
    "xsrf",
    "localStorage",
    "storage_state",
    "sessionStorage",
}


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _connect(path: Path) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS kaspi_customer_chat_gateway_fixture_ledger (
            order_ref TEXT NOT NULL,
            channel TEXT NOT NULL,
            template_hash TEXT NOT NULL,
            status TEXT NOT NULL,
            transport_shape_id TEXT NOT NULL,
            send_attempt_count INTEGER NOT NULL DEFAULT 0,
            last_gate TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            PRIMARY KEY (order_ref, template_hash)
        )
        """
    )
    return conn


def _default_fixture_shapes() -> list[dict[str, Any]]:
    return [
        {
            "transport_shape_id": "fixture_start_chat_rest_v1",
            "purpose": "startChat",
            "method": "POST",
            "host": "mc.shop.kaspi.kz",
            "path_template": "/chats/api/mobile/api/v1/group/startChat",
            "content_type_family": "json",
            "field_names": ["orderRef", "chatType"],
        },
        {
            "transport_shape_id": "fixture_load_history_rest_v1",
            "purpose": "loadMoreMessages",
            "method": "POST",
            "host": "mc.shop.kaspi.kz",
            "path_template": "/chats/api/mobile/api/v1/history/loadMoreMessages",
            "content_type_family": "json",
            "field_names": ["groupRef", "cursor"],
        },
        {
            "transport_shape_id": "fixture_change_status_rest_v1",
            "purpose": "changeStatus",
            "method": "POST",
            "host": "mc.shop.kaspi.kz",
            "path_template": "/chats/api/mobile/api/v1/messageStatus/changeStatus",
            "content_type_family": "json",
            "field_names": ["groupRef", "status"],
            "read_side_effect_unknown": True,
        },
        {
            "transport_shape_id": "fixture_send_message_rest_v1",
            "purpose": "sendMessage",
            "method": "POST",
            "host": "mc.shop.kaspi.kz",
            "path_template": "/chats/api/mobile/api/v1/messages/sendMessage",
            "content_type_family": "json",
            "field_names": ["groupRef", "messageTextHash"],
            "send_capable": True,
        },
        {
            "transport_shape_id": "fixture_chat_websocket_v1",
            "purpose": "websocket",
            "method": "WEBSOCKET",
            "host": "mc.shop.kaspi.kz",
            "path_template": "/ws/chats/ws",
            "content_type_family": "",
            "field_names": ["groupRef"],
        },
        {
            "transport_shape_id": "fixture_expired_session_403",
            "purpose": "expiredSession",
            "method": "POST",
            "host": "mc.shop.kaspi.kz",
            "path_template": "/chats/api/mobile/api/v1/messages/sendMessage",
            "content_type_family": "json",
            "field_names": ["errorCode"],
            "status": 403,
            "send_capable": True,
        },
    ]


def _read_fixture_shapes(path: Path | None) -> list[dict[str, Any]]:
    if not path:
        return _default_fixture_shapes()
    data = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(data, dict):
        return list(data.get("shapes") or [])
    if isinstance(data, list):
        return data
    raise ValueError("fixture JSON must be a list or object with shapes")


def _read_fixture_cases(path: Path) -> list[dict[str, Any]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(data, dict):
        return list(data.get("cases") or [])
    if isinstance(data, list):
        return data
    raise ValueError("fixture cases JSON must be a list or object with cases")


def _iter_forbidden_keys(payload: Any, path: str = "") -> list[str]:
    hits: list[str] = []
    if isinstance(payload, dict):
        for key, value in payload.items():
            key_text = str(key)
            child_path = f"{path}.{key_text}" if path else key_text
            if key_text in FORBIDDEN_SECRET_KEYS:
                hits.append(child_path)
            hits.extend(_iter_forbidden_keys(value, child_path))
    elif isinstance(payload, list):
        for index, value in enumerate(payload):
            hits.extend(_iter_forbidden_keys(value, f"{path}[{index}]"))
    return hits


def _payload_for_value_scan(payload: Any) -> Any:
    """Drop known redacted hash/status fields before raw-number scanning."""
    if isinstance(payload, dict):
        safe: dict[str, Any] = {}
        for key, value in payload.items():
            if key in {
                "order_ref",
                "template_hash",
                "channel",
                "db_row_id",
                "expected_merchant_account_id",
                "visible_merchant_account_id",
                "send_attempt_count",
                "run_at",
                "created_at",
                "updated_at",
                "last_gate",
                "gate",
                "blockers",
            }:
                continue
            safe[key] = _payload_for_value_scan(value)
        return safe
    if isinstance(payload, list):
        return [_payload_for_value_scan(value) for value in payload]
    return payload


def _scan_redaction(payload: Any) -> list[str]:
    text = json.dumps(_payload_for_value_scan(payload), ensure_ascii=False, sort_keys=True)
    blockers: list[str] = []
    if PHONE_RE.search(text):
        blockers.append("phone_like_value_detected")
    if RAW_LONG_NUMBER_RE.search(text):
        blockers.append("raw_long_number_detected")
    if SECRET_VALUE_RE.search(text):
        blockers.append("secret_like_value_detected")
    for key_path in _iter_forbidden_keys(payload):
        blockers.append(f"forbidden_key_detected:{key_path}")
    return sorted(set(blockers))


def validate_fixture_shapes(shapes: list[dict[str, Any]]) -> dict[str, Any]:
    blockers: list[str] = []
    required_keys = {"transport_shape_id", "purpose", "method", "host", "path_template", "field_names"}
    for index, shape in enumerate(shapes):
        missing = sorted(required_keys - set(shape))
        if missing:
            blockers.append(f"shape_{index}_missing:{','.join(missing)}")
        for forbidden in ["url", "headers", "request_body", "response_body", "raw_order_id", "message_text"]:
            if forbidden in shape:
                blockers.append(f"shape_{index}_forbidden_key:{forbidden}")
    blockers.extend(_scan_redaction(shapes))
    gate = RED_UNSAFE_GATE if blockers else "GREEN_KASPI_CUSTOMER_CHAT_GATEWAY_FIXTURE_SHAPES_SAFE"
    return {
        "gate": gate,
        "shape_count": len(shapes),
        "blockers": sorted(set(blockers)),
        "raw_order_id_exported": False,
        "raw_customer_text_exported": False,
        "raw_session_material_exported": False,
    }


def _redaction_flags() -> dict[str, bool]:
    return {
        "raw_order_id_exported": False,
        "raw_customer_text_exported": False,
        "raw_phone_exported": False,
        "raw_session_material_exported": False,
        "cookie_token_session_exported": False,
    }


def _route_risk_for_events(events: list[dict[str, Any]]) -> tuple[list[str], bool]:
    blockers: list[str] = []
    yellow = False
    for event in events:
        searchable = " ".join(
            str(event.get(key) or "")
            for key in ("route_family", "path_template", "purpose", "reason")
        )
        for marker, blocker in ROUTE_RED_BLOCKERS.items():
            if marker in searchable:
                blockers.append(blocker)
        if any(marker in searchable for marker in ROUTE_YELLOW_MARKERS):
            yellow = True
    return sorted(set(blockers)), yellow


def _case_stage_green_gate(stage: str) -> str:
    if stage == "command_build":
        return "GREEN_RESIDENT_NO_SEND_COMMAND_PACKET_READY"
    if stage == "metadata_capture":
        return "GREEN_CUSTOMER_CHAT_METADATA_CAPTURE_NO_SEND_NO_SECRET_EXPORT"
    if stage == "no_click_selector":
        return "GREEN_KASPI_CUSTOMER_CHAT_OPEN_SELECTOR_DOM_DIAGNOSTIC_NO_CLICK_READY"
    if stage == "open_no_type":
        return "GREEN_OPEN_CHAT_NO_TYPE_CANARY_RESULT_NO_SEND"
    if stage in {"send_simulated", "timeout_simulated"}:
        return GREEN_SEND_GATE
    return GREEN_NO_SEND_GATE


def evaluate_fixture_case(case: dict[str, Any]) -> dict[str, Any]:
    """Evaluate one sanitized fixture case without touching live systems."""
    blockers: list[str] = []
    warnings: list[str] = []
    missing = sorted(FIXTURE_CASE_REQUIRED_KEYS - set(case))
    if missing:
        blockers.append(f"case_missing:{','.join(missing)}")

    stage = str(case.get("stage") or "")
    target = case.get("target") if isinstance(case.get("target"), dict) else {}
    flags = case.get("command_flags") if isinstance(case.get("command_flags"), dict) else {}
    approval = case.get("approval") if isinstance(case.get("approval"), dict) else {}
    ledger_before = case.get("ledger_before") if isinstance(case.get("ledger_before"), dict) else {}
    events = case.get("transport_events") if isinstance(case.get("transport_events"), list) else []

    blockers.extend(_scan_redaction(case))

    expected_merchant = str(target.get("expected_merchant_account_id") or "")
    visible_merchant = str(target.get("visible_merchant_account_id") or expected_merchant)
    if expected_merchant and visible_merchant and expected_merchant != visible_merchant:
        blockers.append("visible_merchant_selector_id_mismatch")

    if flags.get("message_text_typed"):
        blockers.append("message_text_typed_true")
    if flags.get("message_sent"):
        blockers.append("message_sent_true")
    if flags.get("customer_send_allowed") and stage not in {"send_simulated", "timeout_simulated"}:
        blockers.append("customer_send_allowed_true_without_send_stage")
    if flags.get("kaspi_chat_write_allowed") and stage not in {"send_simulated", "timeout_simulated"}:
        blockers.append("kaspi_chat_write_allowed_true_without_send_stage")
    if flags.get("chat_open_allowed") and stage not in {"open_no_type", "send_simulated", "timeout_simulated"}:
        blockers.append("chat_open_allowed_true_without_open_stage")

    route_blockers, route_yellow = _route_risk_for_events(events)
    blockers.extend(route_blockers)
    if route_yellow:
        warnings.append("history_load_more_messages_route_observed_open_chat_read_risk")

    prior_status = str(ledger_before.get("status") or "NONE").upper()
    if prior_status in BLOCKING_PRIOR_STATUSES and stage in {"send_simulated", "timeout_simulated"}:
        blockers.append(f"prior_status_blocks_send:{prior_status}")

    if stage in {"send_simulated", "timeout_simulated"} and not blockers:
        if not approval.get("env_gate_enabled"):
            blockers.append(f"missing_env_gate:{SEND_ENV_GATE}")
        if not approval.get("exact_approval_marker_present"):
            blockers.append(f"missing_approval_marker:{APPROVAL_TOKEN}")

    sent_count = 0
    ledger_status_after = "SEND_PLANNED_NO_SEND"
    gate = _case_stage_green_gate(stage)
    if blockers:
        if stage == "metadata_capture" and route_blockers:
            gate = RED_METADATA_GATE
        elif any(blocker.startswith("prior_status_blocks_send:") for blocker in blockers) or any(
            blocker.startswith("missing_env_gate:") or blocker.startswith("missing_approval_marker:")
            for blocker in blockers
        ):
            gate = YELLOW_BLOCKED_GATE
        else:
            gate = RED_UNSAFE_GATE
    elif route_yellow and stage == "metadata_capture":
        gate = YELLOW_METADATA_GATE
    elif stage == "send_simulated":
        sent_count = 1
        ledger_status_after = "REQUEST_SENT"
        gate = GREEN_SEND_GATE
    elif stage == "timeout_simulated":
        ledger_status_after = "UNKNOWN_SEND_OUTCOME"
        gate = YELLOW_UNKNOWN_GATE
        blockers.append("simulated_timeout_unknown_outcome_no_retry")

    actual = {
        "case_id": case.get("case_id", ""),
        "stage": stage,
        "gate": gate,
        "ledger_status_after": ledger_status_after,
        "sent_count": sent_count,
        "blockers": sorted(set(blockers)),
        "warnings": sorted(set(warnings)),
        "external_network_performed": False,
        **_redaction_flags(),
    }

    expected = case.get("expected") if isinstance(case.get("expected"), dict) else {}
    mismatches: list[str] = []
    for key in ("gate", "ledger_status_after", "sent_count"):
        if key in expected and actual.get(key) != expected.get(key):
            mismatches.append(f"{key}:expected={expected.get(key)!r}:actual={actual.get(key)!r}")
    if "blockers" in expected and sorted(expected.get("blockers") or []) != actual["blockers"]:
        mismatches.append(
            "blockers:expected="
            f"{sorted(expected.get('blockers') or [])!r}:actual={actual['blockers']!r}"
        )
    expected_redaction = expected.get("redaction") if isinstance(expected.get("redaction"), dict) else {}
    for key, expected_value in expected_redaction.items():
        if actual.get(key) != expected_value:
            mismatches.append(f"{key}:expected={expected_value!r}:actual={actual.get(key)!r}")
    actual["expectation_mismatches"] = mismatches
    return actual


def run_fixture_cases(args: argparse.Namespace) -> dict[str, Any]:
    cases = _read_fixture_cases(args.fixture_cases_json)
    case_results = [evaluate_fixture_case(case) for case in cases]
    failed_cases = [
        result["case_id"]
        for result in case_results
        if result["expectation_mismatches"]
        or (
            not next(
                (
                    case.get("expected")
                    for case in cases
                    if case.get("case_id", "") == result["case_id"]
                ),
                None,
            )
            and str(result["gate"]).startswith("RED_")
        )
    ]
    gate = GREEN_CASES_GATE if not failed_cases else RED_CASES_GATE
    return {
        "gate": gate,
        "run_at": datetime.now().isoformat(timespec="seconds"),
        "mode": "fixture-cases",
        "case_count": len(case_results),
        "failed_cases": failed_cases,
        "case_results": case_results,
        "customer_send_allowed": False,
        "kaspi_chat_write_allowed": False,
        "external_network_performed": False,
        **_redaction_flags(),
    }


def _load_prior(conn: sqlite3.Connection, order_ref: str, template_hash: str) -> sqlite3.Row | None:
    return conn.execute(
        """
        SELECT *
        FROM kaspi_customer_chat_gateway_fixture_ledger
        WHERE order_ref = ? AND template_hash = ?
        """,
        (order_ref, template_hash),
    ).fetchone()


def _upsert_status(
    conn: sqlite3.Connection,
    *,
    order_ref: str,
    template_hash: str,
    status: str,
    transport_shape_id: str,
    gate: str,
    increment_attempt: bool = False,
) -> None:
    now = datetime.now().isoformat(timespec="seconds")
    prior = _load_prior(conn, order_ref, template_hash)
    attempts = int(prior["send_attempt_count"]) if prior else 0
    if increment_attempt:
        attempts += 1
    conn.execute(
        """
        INSERT INTO kaspi_customer_chat_gateway_fixture_ledger (
            order_ref, channel, template_hash, status, transport_shape_id,
            send_attempt_count, last_gate, created_at, updated_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(order_ref, template_hash) DO UPDATE SET
            status = excluded.status,
            transport_shape_id = excluded.transport_shape_id,
            send_attempt_count = excluded.send_attempt_count,
            last_gate = excluded.last_gate,
            updated_at = excluded.updated_at
        """,
        (
            order_ref,
            CHANNEL,
            template_hash,
            status,
            transport_shape_id,
            attempts,
            gate,
            prior["created_at"] if prior else now,
            now,
        ),
    )
    conn.commit()


def _approval_ok(approval_phrase: str) -> bool:
    return APPROVAL_TOKEN in str(approval_phrase or "")


def _result_payload(
    *,
    gate: str,
    mode: str,
    order_ref: str,
    template_hash: str,
    transport_shape_id: str,
    status: str,
    sent_count: int,
    blockers: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "gate": gate,
        "run_at": datetime.now().isoformat(timespec="seconds"),
        "mode": mode,
        "order_ref": order_ref,
        "channel": CHANNEL,
        "template_hash": template_hash,
        "transport_shape_id": transport_shape_id,
        "ledger_status": status,
        "sent_count": sent_count,
        "blockers": blockers or [],
        "customer_send_allowed": False,
        "kaspi_chat_write_allowed": False,
        "external_network_performed": False,
        "raw_order_id_exported": False,
        "raw_customer_text_exported": False,
        "raw_phone_exported": False,
        "raw_session_material_exported": False,
        "cookie_token_session_exported": False,
    }


def run_fixture(args: argparse.Namespace) -> dict[str, Any]:
    shapes = _read_fixture_shapes(args.fixture_json)
    shape_validation = validate_fixture_shapes(shapes)
    if shape_validation["gate"] != "GREEN_KASPI_CUSTOMER_CHAT_GATEWAY_FIXTURE_SHAPES_SAFE":
        return {
            **_result_payload(
                gate=RED_UNSAFE_GATE,
                mode=args.mode,
                order_ref=args.order_ref,
                template_hash=request_template_hash(args.template_text),
                transport_shape_id=args.transport_shape_id,
                status="STOPLINE",
                sent_count=0,
                blockers=list(shape_validation["blockers"]),
            ),
            "shape_validation": shape_validation,
        }

    template_hash = request_template_hash(args.template_text)
    ledger_path = args.ledger_db.resolve()
    with _connect(ledger_path) as conn:
        prior = _load_prior(conn, args.order_ref, template_hash)
        prior_status = str(prior["status"] if prior else "").upper()
        if prior_status in BLOCKING_PRIOR_STATUSES:
            return _result_payload(
                gate=YELLOW_BLOCKED_GATE,
                mode=args.mode,
                order_ref=args.order_ref,
                template_hash=template_hash,
                transport_shape_id=args.transport_shape_id,
                status=prior_status,
                sent_count=0,
                blockers=[f"prior_status_blocks_send:{prior_status}"],
            )

        if args.mode == "no-send":
            _upsert_status(
                conn,
                order_ref=args.order_ref,
                template_hash=template_hash,
                status="SEND_PLANNED_NO_SEND",
                transport_shape_id=args.transport_shape_id,
                gate=GREEN_NO_SEND_GATE,
            )
            return _result_payload(
                gate=GREEN_NO_SEND_GATE,
                mode=args.mode,
                order_ref=args.order_ref,
                template_hash=template_hash,
                transport_shape_id=args.transport_shape_id,
                status="SEND_PLANNED_NO_SEND",
                sent_count=0,
            )

        blockers: list[str] = []
        if os.environ.get(SEND_ENV_GATE) != "1":
            blockers.append(f"missing_env_gate:{SEND_ENV_GATE}")
        if not _approval_ok(args.approval_phrase):
            blockers.append(f"missing_approval_marker:{APPROVAL_TOKEN}")
        if blockers:
            _upsert_status(
                conn,
                order_ref=args.order_ref,
                template_hash=template_hash,
                status="SEND_PLANNED_NO_SEND",
                transport_shape_id=args.transport_shape_id,
                gate=YELLOW_BLOCKED_GATE,
            )
            return _result_payload(
                gate=YELLOW_BLOCKED_GATE,
                mode=args.mode,
                order_ref=args.order_ref,
                template_hash=template_hash,
                transport_shape_id=args.transport_shape_id,
                status="SEND_PLANNED_NO_SEND",
                sent_count=0,
                blockers=blockers,
            )

        _upsert_status(
            conn,
            order_ref=args.order_ref,
            template_hash=template_hash,
            status="SEND_IN_PROGRESS",
            transport_shape_id=args.transport_shape_id,
            gate="LOCAL_FIXTURE_SEND_IN_PROGRESS",
            increment_attempt=True,
        )

        if args.mode == "timeout-simulated":
            _upsert_status(
                conn,
                order_ref=args.order_ref,
                template_hash=template_hash,
                status="UNKNOWN_SEND_OUTCOME",
                transport_shape_id=args.transport_shape_id,
                gate=YELLOW_UNKNOWN_GATE,
            )
            return _result_payload(
                gate=YELLOW_UNKNOWN_GATE,
                mode=args.mode,
                order_ref=args.order_ref,
                template_hash=template_hash,
                transport_shape_id=args.transport_shape_id,
                status="UNKNOWN_SEND_OUTCOME",
                sent_count=0,
                blockers=["simulated_timeout_unknown_outcome_no_retry"],
            )

        _upsert_status(
            conn,
            order_ref=args.order_ref,
            template_hash=template_hash,
            status="REQUEST_SENT",
            transport_shape_id=args.transport_shape_id,
            gate=GREEN_SEND_GATE,
        )
        return _result_payload(
            gate=GREEN_SEND_GATE,
            mode=args.mode,
            order_ref=args.order_ref,
            template_hash=template_hash,
            transport_shape_id=args.transport_shape_id,
            status="REQUEST_SENT",
            sent_count=1,
        )


def _build_closeout(result: dict[str, Any], result_path: Path, ledger_path: Path) -> str:
    return "\n".join(
        [
            "# Kaspi Customer Chat Gateway Fixture",
            "",
            f"Gate: {result['gate']}",
            "",
            "## Scope",
            "",
            "- Local fixture only; no live Kaspi endpoint call.",
            f"- Result JSON: `{result_path}`",
            f"- Fixture ledger: `{ledger_path}`",
            f"- Mode: `{result.get('mode')}`",
            f"- Order ref: `{result.get('order_ref')}`",
            f"- Template hash: `{result.get('template_hash')}`",
            f"- Ledger status: `{result.get('ledger_status')}`",
            f"- Sent count: {result.get('sent_count')}",
            "",
            "## Safety",
            "",
            "- Customer send allowed: false",
            "- Kaspi chat write allowed: false",
            "- External network performed: false",
            "- Raw order ID exported: false",
            "- Raw customer text exported: false",
            "- Raw session material exported: false",
            "- No Google Board, production DB, CRM workbook, Telegram, WhatsApp, scheduler, price, stock, cash, supplier, or PO write happened.",
            "- Fixture case mode never performs external network actions.",
            "",
            "## Blockers",
            "",
            *(f"- {blocker}" for blocker in (result.get("blockers") or ["none"])),
            "",
        ]
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ledger-db", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--fixture-json", type=Path)
    parser.add_argument("--fixture-cases-json", type=Path)
    parser.add_argument("--schema-json", type=Path, help="Reserved for schema artifact traceability; validation is built in.")
    parser.add_argument("--order-ref", default=DEFAULT_ORDER_REF)
    parser.add_argument("--template-text", default=DEFAULT_REQUEST_TEMPLATE)
    parser.add_argument("--transport-shape-id", default="fixture_send_message_rest_v1")
    parser.add_argument(
        "--mode",
        choices=["no-send", "send-simulated", "timeout-simulated"],
        default="no-send",
    )
    parser.add_argument("--approval-phrase", default="")
    parser.add_argument("--require-green", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    output_dir = args.output_dir.resolve()
    result_path = output_dir / "gateway_fixture_result_redacted.json"
    closeout_path = output_dir / "gateway_fixture_closeout.md"
    result = run_fixture_cases(args) if args.fixture_cases_json else run_fixture(args)
    redaction_blockers = _scan_redaction(result)
    if redaction_blockers:
        result["gate"] = RED_UNSAFE_GATE
        result["blockers"] = sorted(set((result.get("blockers") or []) + redaction_blockers))
    _write_json(result_path, result)
    closeout_path.parent.mkdir(parents=True, exist_ok=True)
    closeout_path.write_text(_build_closeout(result, result_path, args.ledger_db.resolve()), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    if args.require_green and not str(result.get("gate") or "").startswith("GREEN_"):
        return 1
    if str(result.get("gate") or "").startswith("RED_"):
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
