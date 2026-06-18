#!/usr/bin/env python3
"""Run a resident Kaspi merchant browser controller for diagnostics.

This helper exists to avoid repeated SMS logins. It opens one persistent
Playwright Chrome profile, keeps that browser alive, and processes local JSON
commands from a queue. Existing commands are no-send diagnostics. A future
one-order live-send canary command is disabled by default and must pass a
separate explicit controller flag plus command/preflight gates before any
transport work can be attempted. By default, even stop/once exit requests are
fail-closed so an agent cannot accidentally close the authenticated session;
pass --allow-session-close only for an intentional owner-approved teardown.

Safety boundary by default:
- no customer-message send capability;
- no chat-open action;
- no Google Board, DB, workbook, Telegram, WhatsApp, scheduler, price, stock,
  cash, supplier, or PO writes;
- no raw order IDs, customer text, phones, cookies, headers, localStorage, or
  session material are persisted.

The optional open-chat/no-type command is disabled unless both the controller
flag and an exact command/approval packet are present. That command may open
one selected chat only, but still never types or sends a customer message.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from datetime import date, datetime
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.ops.customer_size_request import load_missing_size_candidates  # noqa: E402
from scripts.probe_kaspi_customer_chat_metadata_no_send import (  # noqa: E402
    build_closeout as build_metadata_capture_closeout,
    build_request_event,
    build_response_event,
    build_websocket_event,
    route_families,
    unsafe_route_block_reason,
    validate_capture,
)
from scripts.probe_kaspi_customer_chat_ui_search_identity_no_send import (  # noqa: E402
    CHAT_BUTTON_SELECTOR,
    DEFAULT_DB,
    DEFAULT_PERSISTENT_PROFILE_DIR,
    _probe_one,
    _safe_url,
    _split_csv,
    _status_url,
    _today_from_arg,
    _write_json,
    build_payload,
    plan_probes,
)
from scripts.run_kaspi_customer_chat_open_no_type_canary_ui_executor import (  # noqa: E402
    RESULT_GREEN_GATE as OPEN_CHAT_RESULT_GREEN_GATE,
    build_observed_open_result,
)
from scripts.resolve_kaspi_login_sms_otp_no_secret import (  # noqa: E402
    DEFAULT_MESSAGES_DB,
    DEFAULT_OTP_REGEX,
    GREEN_RESOLVED_GATE as OTP_RESOLVED_GATE,
    resolve_runtime_otp,
)


GREEN_GATE = "GREEN_KASPI_CUSTOMER_CHAT_RESIDENT_NO_SEND_CONTROLLER_READY"
YELLOW_GATE = "YELLOW_KASPI_CUSTOMER_CHAT_RESIDENT_NO_SEND_CONTROLLER_WAITING_FOR_LOGIN"
RED_GATE = "RED_KASPI_CUSTOMER_CHAT_RESIDENT_NO_SEND_CONTROLLER_UNSAFE"
COMMAND_ACTION_UI_SEARCH = "ui_search_identity_no_send"
COMMAND_ACTION_UI_CHAT_BUTTON = "ui_chat_button_no_open"
COMMAND_ACTION_METADATA_CAPTURE = "metadata_capture_no_send"
COMMAND_ACTION_UI_LIVE_SEND_CANARY = "ui_live_send_one_order_canary"
COMMAND_ACTION_UI_OPEN_CHAT_NO_TYPE_CANARY = "ui_open_chat_no_type_canary"
COMMAND_ACTION_UI_OPEN_CHAT_SELECTOR_DOM_DIAGNOSTIC = "ui_open_chat_selector_dom_diagnostic_no_click"
COMMAND_ACTION_LOGIN_SMS_OTP = "login_sms_otp_no_secret"
COMMAND_ACTION_STOP = "stop"
DEFAULT_STATUS_FILTER = "KASPI_DELIVERY_CARGO_ASSEMBLY"
SESSION_CLOSE_GUARD_BLOCKER = "session_close_requires_explicit_allow_session_close"
LIVE_SEND_DISABLED_GATE = "YELLOW_KASPI_CUSTOMER_CHAT_LIVE_SEND_CANARY_DISABLED_NO_SEND"
LIVE_SEND_PREFLIGHT_READY_GATE = "GREEN_KASPI_CUSTOMER_CHAT_LIVE_SEND_CANARY_PREFLIGHT_READY_NO_SEND"
LIVE_SEND_PREFLIGHT_BLOCKED_GATE = "YELLOW_KASPI_CUSTOMER_CHAT_LIVE_SEND_CANARY_PREFLIGHT_BLOCKED_NO_SEND"
LIVE_SEND_TRANSPORT_PLAN_READY_GATE = (
    "GREEN_KASPI_CUSTOMER_CHAT_LIVE_SEND_CANARY_TRANSPORT_PLAN_READY_NO_SEND"
)
LIVE_SEND_TRANSPORT_PLAN_BLOCKED_GATE = (
    "YELLOW_KASPI_CUSTOMER_CHAT_LIVE_SEND_CANARY_TRANSPORT_PLAN_BLOCKED_NO_SEND"
)
LIVE_SEND_UNSAFE_GATE = "RED_KASPI_CUSTOMER_CHAT_LIVE_SEND_CANARY_UNSAFE_NO_SEND"
LOGIN_OTP_FILLED_GATE = "GREEN_KASPI_LOGIN_SMS_OTP_FILLED_NO_CUSTOMER_ACTION"
LOGIN_OTP_READY_GATE = "GREEN_KASPI_LOGIN_SMS_OTP_READY_TO_FILL_NO_CUSTOMER_ACTION"
LOGIN_OTP_BLOCKED_GATE = "YELLOW_KASPI_LOGIN_SMS_OTP_NOT_FILLED_NO_CUSTOMER_ACTION"
LOGIN_OTP_UNSAFE_GATE = "RED_KASPI_LOGIN_SMS_OTP_UNSAFE_NO_CUSTOMER_ACTION"
OPEN_CHAT_PACKET_GREEN_GATE = "GREEN_OPEN_CHAT_NO_TYPE_CANARY_PACKET_READY_NO_SEND"
OPEN_CHAT_PREFLIGHT_READY_GATE = "GREEN_KASPI_CUSTOMER_CHAT_OPEN_CHAT_NO_TYPE_PREFLIGHT_READY_NO_ACTION"
OPEN_CHAT_PREFLIGHT_BLOCKED_GATE = "YELLOW_KASPI_CUSTOMER_CHAT_OPEN_CHAT_NO_TYPE_PREFLIGHT_BLOCKED_NO_ACTION"
OPEN_CHAT_DISABLED_GATE = "YELLOW_KASPI_CUSTOMER_CHAT_OPEN_CHAT_NO_TYPE_DISABLED_NO_ACTION"
OPEN_CHAT_UNSAFE_GATE = "RED_KASPI_CUSTOMER_CHAT_OPEN_CHAT_NO_TYPE_UNSAFE_NO_ACTION"
OPEN_CHAT_TRANSPORT_PLAN_READY_GATE = "GREEN_KASPI_CUSTOMER_CHAT_OPEN_CHAT_NO_TYPE_TRANSPORT_PLAN_READY_NO_ACTION"
OPEN_CHAT_TRANSPORT_PLAN_BLOCKED_GATE = "YELLOW_KASPI_CUSTOMER_CHAT_OPEN_CHAT_NO_TYPE_TRANSPORT_PLAN_BLOCKED_NO_ACTION"
SELECTOR_DOM_DIAGNOSTIC_GREEN_GATE = (
    "GREEN_KASPI_CUSTOMER_CHAT_OPEN_SELECTOR_DOM_DIAGNOSTIC_NO_CLICK_READY"
)
SELECTOR_DOM_DIAGNOSTIC_YELLOW_GATE = (
    "YELLOW_KASPI_CUSTOMER_CHAT_OPEN_SELECTOR_DOM_DIAGNOSTIC_NO_CLICK_BLOCKED"
)
SELECTOR_DOM_DIAGNOSTIC_RED_GATE = (
    "RED_KASPI_CUSTOMER_CHAT_OPEN_SELECTOR_DOM_DIAGNOSTIC_UNSAFE"
)
APPROVAL_GREEN_GATE = "GREEN_LIVE_SEND_CANARY_APPROVAL_PACKET_READY_NO_SEND"
EXECUTION_PREFLIGHT_GREEN_GATE = "GREEN_LIVE_SEND_CANARY_EXECUTION_PREFLIGHT_READY_NO_SEND"
ORDER_SEARCH_INPUT_SELECTOR = "input[placeholder='Номер заказа']"
MESSAGE_INPUT_CANDIDATE_SELECTORS = [
    "textarea[placeholder*='Сообщ']",
    "textarea[placeholder*='сообщ']",
    "textarea",
    "[contenteditable='true'][role='textbox']",
    "[contenteditable='true']",
    "input[placeholder*='Сообщ']",
    "input[placeholder*='сообщ']",
]
OPEN_CHAT_BUTTON_CANDIDATE_SELECTORS = [
    CHAT_BUTTON_SELECTOR,
    "[class*='chat-section'][type='CLIENT_SELLER_BY_ORDER']",
    "[type='CLIENT_SELLER_BY_ORDER']",
    ".init-chat-button.chat-section",
    "[class*='init-chat-button'][class*='chat-section']",
    "button.chat-section[type='CLIENT_SELLER_BY_ORDER']",
    "button[type='CLIENT_SELLER_BY_ORDER']",
    "button.init-chat-button.chat-section",
    "button:has-text('Написать покупателю')",
    "button:has-text('Сообщение покупателю')",
    "button:has-text('Сообщения по заказу')",
    "xpath=//*[normalize-space()='Написать покупателю']",
    "xpath=//*[normalize-space()='Сообщение покупателю']",
    "xpath=//*[normalize-space()='Сообщения по заказу']",
    "[role='button']:has-text('Написать покупателю')",
    "[role='button']:has-text('Сообщение покупателю')",
    "[role='button']:has-text('Сообщения по заказу')",
]
SEND_BUTTON_CANDIDATE_SELECTORS = [
    "button:has-text('Отправить')",
    "button[type='submit']",
    "button[class*='send']",
    "[role='button']:has-text('Отправить')",
]
LOGIN_OTP_INPUT_CANDIDATE_SELECTORS = [
    "input[autocomplete='one-time-code']",
    "input[inputmode='numeric']",
    "input[type='tel']",
    "input[type='number']",
    "input[type='text']",
]
LOGIN_SUBMIT_CANDIDATE_SELECTORS = [
    "button:has-text('Продолжить')",
    "button:has-text('Подтвердить')",
    "button:has-text('Войти')",
    "button[type='submit']",
]
DEFAULT_RUN_DIR = (
    PROJECT_ROOT
    / "exports"
    / "validation"
    / f"kaspi_customer_chat_resident_no_send_controller_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
)


def _split_int_csv(values: str | None) -> list[int]:
    result: list[int] = []
    for value in _split_csv(values):
        try:
            result.append(int(value))
        except ValueError:
            continue
    return result


def _filter_candidates_for_command(
    candidates: list[Any],
    *,
    target_db_row_ids: list[int],
    target_order_refs: list[str],
) -> list[Any]:
    """Restrict a no-send command to redacted/DB-row targets when supplied."""
    if not target_db_row_ids and not target_order_refs:
        return candidates
    target_ids = {int(value) for value in target_db_row_ids}
    target_refs = {str(value).strip() for value in target_order_refs if str(value).strip()}
    filtered: list[Any] = []
    for candidate in candidates:
        if candidate.db_row_id is not None:
            try:
                if int(candidate.db_row_id) in target_ids:
                    filtered.append(candidate)
                    continue
            except (TypeError, ValueError):
                pass
        if candidate.order_ref in target_refs:
            filtered.append(candidate)
    return filtered


def _safe_now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _bool_from_payload(payload: dict[str, Any], key: str) -> bool:
    value = payload.get(key)
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "y"}
    return bool(value)


def _orders_search_visible(page) -> bool:
    try:
        locator = page.locator("input[placeholder='Номер заказа']").first
        return locator.count() > 0 and locator.is_visible(timeout=1000)
    except Exception:
        return False


def _page_safe_state(page) -> dict[str, Any]:
    try:
        current_url = str(page.url or "")
    except Exception:
        current_url = ""
    try:
        title_length = len(str(page.title() or ""))
    except Exception:
        title_length = 0
    return {
        "safe_current_url": _safe_url(current_url),
        "title_length": title_length,
        "orders_search_input_visible": _orders_search_visible(page),
    }


def _heartbeat_payload(
    *,
    gate: str,
    run_dir: Path,
    persistent_profile_dir: Path,
    profile_store_code: str,
    commands_dir: Path,
    page=None,
    blockers: list[str] | None = None,
    last_command: dict[str, Any] | None = None,
) -> dict[str, Any]:
    page_state = _page_safe_state(page) if page is not None else {}
    return {
        "gate": gate,
        "recorded_at": _safe_now(),
        "run_dir": str(run_dir),
        "profile_store_code": profile_store_code,
        "persistent_profile_mode": True,
        "persistent_profile_dir_path": str(persistent_profile_dir),
        "commands_dir": str(commands_dir),
        "browser_should_remain_open": True,
        "session_close_requires_explicit_allow_session_close": True,
        "customer_send_allowed": False,
        "kaspi_chat_write_allowed": False,
        "google_board_write_allowed": False,
        "chat_opened": False,
        "message_text_typed": False,
        "message_sent": False,
        "raw_order_id_exported": False,
        "raw_customer_text_exported": False,
        "raw_phone_exported": False,
        "raw_session_material_exported": False,
        "blockers": blockers or [],
        "last_command": last_command or {},
        **page_state,
    }


def _write_heartbeat(path: Path, payload: dict[str, Any]) -> None:
    _write_json(path, payload)


def normalize_command(
    payload: dict[str, Any],
    *,
    run_dir: Path,
    profile_store_code: str,
) -> dict[str, Any]:
    action = str(payload.get("action") or COMMAND_ACTION_UI_SEARCH).strip()
    command_id = str(payload.get("command_id") or f"cmd_{datetime.now().strftime('%Y%m%d_%H%M%S')}").strip()
    target_date_value = payload.get("target_date")
    target_date = _today_from_arg(str(target_date_value)) if target_date_value else date.today()
    lookback_days = int(payload.get("lookback_days") or 5)
    max_candidates = int(payload.get("max_candidates") or 6)
    candidate_pool_limit = int(payload.get("candidate_pool_limit") or 30)
    command_profile_store = str(payload.get("profile_store_code") or profile_store_code).strip().upper()
    stores = str(payload.get("stores") or command_profile_store).strip()
    extra_status_filters = str(payload.get("extra_status_filters") or "").strip()
    target_db_row_ids = str(payload.get("target_db_row_ids") or "").strip()
    target_order_refs = str(payload.get("target_order_refs") or "").strip()
    timeout_ms = int(payload.get("timeout_ms") or 30000)
    approval_dir = str(payload.get("approval_dir") or "").strip()
    live_send_execution_preflight_manifest = str(
        payload.get("live_send_execution_preflight_manifest") or ""
    ).strip()
    open_chat_packet_dir = str(payload.get("open_chat_packet_dir") or "").strip()
    open_chat_approval_text_file = str(payload.get("open_chat_approval_text_file") or "").strip()
    expected_merchant_account_id = str(payload.get("expected_merchant_account_id") or "").strip()
    template_hash = str(payload.get("template_hash") or "").strip()
    template_text = str(payload.get("template_text") or "").strip()
    messages_db = str(payload.get("messages_db") or DEFAULT_MESSAGES_DB).strip()
    otp_audit_json = str(
        payload.get("otp_audit_json")
        or run_dir / "commands" / command_id / "otp_audit_redacted.json"
    ).strip()
    otp_window_minutes = int(payload.get("otp_window_minutes") or 10)
    otp_max_scan_rows = int(payload.get("otp_max_scan_rows") or 50)
    otp_submit_allowed = _bool_from_payload(payload, "otp_submit_allowed")
    output_dir = Path(
        payload.get("output_dir")
        or run_dir / "commands" / command_id / f"{COMMAND_ACTION_UI_SEARCH}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    )
    return {
        "command_id": command_id,
        "action": action,
        "target_date": target_date.isoformat(),
        "lookback_days": lookback_days,
        "stores": stores,
        "profile_store_code": command_profile_store,
        "max_candidates": max_candidates,
        "candidate_pool_limit": candidate_pool_limit,
        "extra_status_filters": extra_status_filters,
        "target_db_row_ids": target_db_row_ids,
        "target_order_refs": target_order_refs,
        "timeout_ms": timeout_ms,
        "output_dir": str(output_dir),
        "approval_dir": approval_dir,
        "live_send_execution_preflight_manifest": live_send_execution_preflight_manifest,
        "open_chat_packet_dir": open_chat_packet_dir,
        "open_chat_approval_text_file": open_chat_approval_text_file,
        "expected_merchant_account_id": expected_merchant_account_id,
        "template_hash": template_hash,
        "template_text": template_text,
        "messages_db": messages_db,
        "otp_audit_json": otp_audit_json,
        "otp_window_minutes": otp_window_minutes,
        "otp_max_scan_rows": otp_max_scan_rows,
        "otp_submit_allowed": otp_submit_allowed,
        "allow_customer_send": _bool_from_payload(payload, "allow_customer_send"),
        "kaspi_chat_write_allowed": _bool_from_payload(payload, "kaspi_chat_write_allowed"),
        "chat_open_allowed": _bool_from_payload(payload, "chat_open_allowed"),
        "message_text_typed": _bool_from_payload(payload, "message_text_typed"),
        "message_sent": _bool_from_payload(payload, "message_sent"),
    }


def _page_mentions_login_otp_prompt(page) -> bool:
    try:
        body_text = str(page.locator("body").inner_text(timeout=1000) or "").casefold()
    except Exception:
        body_text = ""
    if not body_text:
        return False
    return any(value in body_text for value in ["код", "sms", "смс", "однораз", "подтверж"])


def _first_visible_locator(page, selectors: list[str]):
    for selector in selectors:
        try:
            locator = page.locator(selector).first
            if locator.count() > 0 and locator.is_visible(timeout=500):
                return selector, locator
        except Exception:
            continue
    return "", None


def _run_login_sms_otp_command(*, command: dict[str, Any], page) -> dict[str, Any]:
    output_dir = Path(command["output_dir"]).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    otp_audit_path = Path(command["otp_audit_json"]).resolve()
    if _orders_search_visible(page):
        result = {
            "gate": LOGIN_OTP_READY_GATE,
            "recorded_at": _safe_now(),
            "command_id": command.get("command_id"),
            "already_logged_in": True,
            "otp_runtime_secret_used": False,
            "otp_filled": False,
            "login_submit_attempted": False,
            "customer_send_performed": False,
            "kaspi_chat_write_performed": False,
            "chat_opened": False,
            "message_text_typed": False,
            "message_sent": False,
            "raw_otp_exported": False,
            "raw_sms_text_exported": False,
            "raw_sender_exported": False,
            "raw_order_id_exported": False,
            "raw_customer_text_exported": False,
            "raw_phone_exported": False,
            "raw_session_material_exported": False,
        }
        _write_json(output_dir / "login_sms_otp_result_redacted.json", result)
        result["manifest_path"] = str(output_dir / "login_sms_otp_result_redacted.json")
        return result

    page_state = _page_safe_state(page)
    safe_url = str(page_state.get("safe_current_url") or "")
    blockers: list[str] = []
    if "idmc.shop.kaspi.kz/login" not in safe_url:
        blockers.append("kaspi_login_page_not_visible")
    if not _page_mentions_login_otp_prompt(page):
        blockers.append("otp_prompt_text_not_visible")
    selector, input_locator = _first_visible_locator(page, LOGIN_OTP_INPUT_CANDIDATE_SELECTORS)
    if input_locator is None:
        blockers.append("otp_input_not_visible")
    if blockers:
        result = {
            "gate": LOGIN_OTP_BLOCKED_GATE,
            "recorded_at": _safe_now(),
            "command_id": command.get("command_id"),
            "blockers": blockers,
            "safe_current_url": safe_url,
            "otp_runtime_secret_used": False,
            "otp_filled": False,
            "login_submit_attempted": False,
            "customer_send_performed": False,
            "kaspi_chat_write_performed": False,
            "chat_opened": False,
            "message_text_typed": False,
            "message_sent": False,
            "raw_otp_exported": False,
            "raw_sms_text_exported": False,
            "raw_sender_exported": False,
            "raw_order_id_exported": False,
            "raw_customer_text_exported": False,
            "raw_phone_exported": False,
            "raw_session_material_exported": False,
        }
        _write_json(output_dir / "login_sms_otp_result_redacted.json", result)
        result["manifest_path"] = str(output_dir / "login_sms_otp_result_redacted.json")
        return result

    exit_code, otp_audit, otp = resolve_runtime_otp(
        messages_db=Path(command["messages_db"]).expanduser(),
        window_minutes=int(command["otp_window_minutes"]),
        max_scan_rows=int(command["otp_max_scan_rows"]),
        otp_regex=DEFAULT_OTP_REGEX,
        runtime_secret_to_caller_requested=True,
        copy_to_clipboard=False,
    )
    _write_json(otp_audit_path, otp_audit)
    if exit_code != 0 or not otp or otp_audit.get("gate") != OTP_RESOLVED_GATE:
        result = {
            "gate": LOGIN_OTP_BLOCKED_GATE,
            "recorded_at": _safe_now(),
            "command_id": command.get("command_id"),
            "blockers": ["otp_runtime_resolver_not_green"],
            "otp_resolver_gate": otp_audit.get("gate"),
            "otp_audit_json": str(otp_audit_path),
            "otp_runtime_secret_used": False,
            "otp_filled": False,
            "login_submit_attempted": False,
            "customer_send_performed": False,
            "kaspi_chat_write_performed": False,
            "chat_opened": False,
            "message_text_typed": False,
            "message_sent": False,
            "raw_otp_exported": False,
            "raw_sms_text_exported": False,
            "raw_sender_exported": False,
            "raw_order_id_exported": False,
            "raw_customer_text_exported": False,
            "raw_phone_exported": False,
            "raw_session_material_exported": False,
        }
        _write_json(output_dir / "login_sms_otp_result_redacted.json", result)
        result["manifest_path"] = str(output_dir / "login_sms_otp_result_redacted.json")
        return result

    try:
        input_locator.fill(str(otp), timeout=1000)
    except Exception as exc:
        result = {
            "gate": LOGIN_OTP_UNSAFE_GATE,
            "recorded_at": _safe_now(),
            "command_id": command.get("command_id"),
            "blockers": [f"otp_fill_failed:{type(exc).__name__}"],
            "otp_audit_json": str(otp_audit_path),
            "otp_input_selector_used": selector,
            "otp_runtime_secret_used": True,
            "otp_filled": False,
            "login_submit_attempted": False,
            "customer_send_performed": False,
            "kaspi_chat_write_performed": False,
            "chat_opened": False,
            "message_text_typed": False,
            "message_sent": False,
            "raw_otp_exported": False,
            "raw_sms_text_exported": False,
            "raw_sender_exported": False,
            "raw_order_id_exported": False,
            "raw_customer_text_exported": False,
            "raw_phone_exported": False,
            "raw_session_material_exported": False,
        }
        _write_json(output_dir / "login_sms_otp_result_redacted.json", result)
        result["manifest_path"] = str(output_dir / "login_sms_otp_result_redacted.json")
        return result

    submit_attempted = False
    if command.get("otp_submit_allowed") is True:
        submit_selector, submit_locator = _first_visible_locator(page, LOGIN_SUBMIT_CANDIDATE_SELECTORS)
        if submit_locator is not None:
            submit_locator.click(timeout=1000)
            submit_attempted = True
            try:
                page.wait_for_timeout(1500)
            except Exception:
                pass
        else:
            submit_selector = ""
    else:
        submit_selector = ""

    result = {
        "gate": LOGIN_OTP_FILLED_GATE,
        "recorded_at": _safe_now(),
        "command_id": command.get("command_id"),
        "otp_audit_json": str(otp_audit_path),
        "otp_input_selector_used": selector,
        "otp_submit_allowed": bool(command.get("otp_submit_allowed")),
        "otp_submit_selector_used": submit_selector,
        "otp_runtime_secret_used": True,
        "otp_filled": True,
        "login_submit_attempted": submit_attempted,
        "orders_search_input_visible_after": _orders_search_visible(page),
        "customer_send_performed": False,
        "kaspi_chat_write_performed": False,
        "chat_opened": False,
        "message_text_typed": False,
        "message_sent": False,
        "raw_otp_exported": False,
        "raw_sms_text_exported": False,
        "raw_sender_exported": False,
        "raw_order_id_exported": False,
        "raw_customer_text_exported": False,
        "raw_phone_exported": False,
        "raw_session_material_exported": False,
    }
    _write_json(output_dir / "login_sms_otp_result_redacted.json", result)
    result["manifest_path"] = str(output_dir / "login_sms_otp_result_redacted.json")
    return result


def _safe_read_json(path_text: str) -> tuple[dict[str, Any], str | None]:
    if not str(path_text or "").strip():
        return {}, "path_missing"
    path = Path(path_text).resolve()
    if not path.exists():
        return {}, "path_not_found"
    try:
        return _read_json(path), None
    except (OSError, json.JSONDecodeError) as exc:
        return {}, f"path_read_failed:{type(exc).__name__}"


def _safe_read_text(path_text: str) -> tuple[str, str | None]:
    if not str(path_text or "").strip():
        return "", "path_missing"
    path = Path(path_text).resolve()
    if not path.exists():
        return "", "path_not_found"
    try:
        return path.read_text(encoding="utf-8").strip(), None
    except OSError as exc:
        return "", f"path_read_failed:{type(exc).__name__}"


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _build_open_chat_no_type_preflight_result(
    *,
    command: dict[str, Any],
    enable_open_chat_no_type_canary: bool,
) -> dict[str, Any]:
    """Validate a future one-order open-chat/no-type command without UI action."""
    blockers: list[str] = []
    unsafe_blockers: list[str] = []

    if command.get("max_candidates") != 1:
        unsafe_blockers.append("open_chat_no_type_requires_max_candidates_1")
    if not command.get("target_db_row_ids") and not command.get("target_order_refs"):
        unsafe_blockers.append("open_chat_no_type_requires_exact_target_db_row_or_order_ref")

    if command.get("chat_open_allowed") is not True:
        unsafe_blockers.append("command_chat_open_allowed_not_true")
    forbidden_true = [
        ("allow_customer_send", "command_allow_customer_send_must_remain_false"),
        ("kaspi_chat_write_allowed", "command_kaspi_chat_write_allowed_must_remain_false"),
        ("message_text_typed", "command_message_text_typed_must_remain_false"),
        ("message_sent", "command_message_sent_must_remain_false"),
    ]
    for key, blocker in forbidden_true:
        if command.get(key) is not False:
            unsafe_blockers.append(blocker)

    if unsafe_blockers:
        return _open_chat_no_type_result(
            gate=OPEN_CHAT_UNSAFE_GATE,
            command=command,
            enable_open_chat_no_type_canary=enable_open_chat_no_type_canary,
            blockers=blockers,
            unsafe_blockers=unsafe_blockers,
            packet_manifest={},
        )

    if not enable_open_chat_no_type_canary:
        blockers.append("controller_open_chat_no_type_canary_not_enabled")
        return _open_chat_no_type_result(
            gate=OPEN_CHAT_DISABLED_GATE,
            command=command,
            enable_open_chat_no_type_canary=False,
            blockers=blockers,
            unsafe_blockers=unsafe_blockers,
            packet_manifest={},
        )

    packet_dir = str(command.get("open_chat_packet_dir") or "").strip()
    packet_manifest: dict[str, Any] = {}
    if packet_dir:
        packet_manifest_path = Path(packet_dir).resolve() / "manifest.json"
        packet_manifest, packet_error = _safe_read_json(str(packet_manifest_path))
        if packet_error:
            blockers.append(f"open_chat_packet_manifest_{packet_error}")
    else:
        blockers.append("open_chat_packet_dir_missing")

    packet_lock: dict[str, Any] = {}
    if packet_manifest:
        if packet_manifest.get("gate") != OPEN_CHAT_PACKET_GREEN_GATE:
            blockers.append(f"open_chat_packet_gate_not_green:{packet_manifest.get('gate')}")
        lock_path = Path(str(packet_manifest.get("packet_manifest_path") or ""))
        expected_lock_sha = str(packet_manifest.get("packet_manifest_sha256") or "")
        if not lock_path.exists():
            blockers.append("open_chat_packet_lock_missing")
        else:
            if expected_lock_sha and _sha256_file(lock_path) != expected_lock_sha:
                unsafe_blockers.append("open_chat_packet_lock_sha256_mismatch")
            packet_lock, lock_error = _safe_read_json(str(lock_path))
            if lock_error:
                blockers.append(f"open_chat_packet_lock_{lock_error}")
            elif packet_lock.get("gate") != OPEN_CHAT_PACKET_GREEN_GATE:
                blockers.append(f"open_chat_packet_lock_gate_not_green:{packet_lock.get('gate')}")
        for field in [
            "customer_send_allowed_now",
            "kaspi_chat_write_allowed_now",
            "raw_order_id_exported",
            "raw_customer_text_exported",
            "raw_phone_exported",
            "raw_session_material_exported",
        ]:
            if packet_manifest.get(field) is not False:
                unsafe_blockers.append(f"open_chat_packet_manifest_{field}_not_false")
            if packet_lock and packet_lock.get(field) is not False:
                unsafe_blockers.append(f"open_chat_packet_lock_{field}_not_false")

    expected_phrase = ""
    if packet_dir:
        expected_phrase, expected_phrase_error = _safe_read_text(
            str(Path(packet_dir).resolve() / "REQUIRED_EXACT_OPEN_CHAT_NO_TYPE_APPROVAL_PHRASE.txt")
        )
        if expected_phrase_error:
            blockers.append(f"open_chat_expected_approval_phrase_{expected_phrase_error}")
    supplied_phrase, supplied_phrase_error = _safe_read_text(
        str(command.get("open_chat_approval_text_file") or "")
    )
    if supplied_phrase_error:
        blockers.append(f"open_chat_supplied_approval_phrase_{supplied_phrase_error}")
    if expected_phrase and supplied_phrase and expected_phrase != supplied_phrase:
        unsafe_blockers.append("open_chat_owner_approval_text_mismatch")
    elif not expected_phrase or not supplied_phrase:
        blockers.append("open_chat_owner_exact_approval_not_supplied_or_not_matched")

    expected_pairs = [
        ("selected_order_ref", command.get("target_order_refs")),
        ("selected_db_row_id", command.get("target_db_row_ids")),
        ("selected_store_code", command.get("stores")),
        ("expected_merchant_account_id", command.get("expected_merchant_account_id")),
    ]
    for field, command_value in expected_pairs:
        command_text = str(command_value or "").strip()
        if not command_text:
            continue
        if packet_manifest and str(packet_manifest.get(field) or "").strip() != command_text:
            unsafe_blockers.append(f"open_chat_packet_{field}_mismatch")

    if unsafe_blockers:
        gate = OPEN_CHAT_UNSAFE_GATE
    elif blockers:
        gate = OPEN_CHAT_PREFLIGHT_BLOCKED_GATE
    else:
        gate = OPEN_CHAT_PREFLIGHT_READY_GATE
    return _open_chat_no_type_result(
        gate=gate,
        command=command,
        enable_open_chat_no_type_canary=True,
        blockers=blockers,
        unsafe_blockers=unsafe_blockers,
        packet_manifest=packet_manifest,
    )


def _open_chat_no_type_result(
    *,
    gate: str,
    command: dict[str, Any],
    enable_open_chat_no_type_canary: bool,
    blockers: list[str],
    unsafe_blockers: list[str],
    packet_manifest: dict[str, Any],
) -> dict[str, Any]:
    result = {
        "gate": gate,
        "recorded_at": _safe_now(),
        "command_id": command.get("command_id"),
        "action": command.get("action"),
        "selected_order_ref": command.get("target_order_refs"),
        "selected_db_row_id": command.get("target_db_row_ids"),
        "selected_store_code": command.get("stores"),
        "selected_status_filter": packet_manifest.get("selected_status_filter") or "",
        "expected_merchant_account_id": command.get("expected_merchant_account_id"),
        "open_chat_packet_dir": command.get("open_chat_packet_dir"),
        "open_chat_approval_text_file": command.get("open_chat_approval_text_file"),
        "controller_open_chat_no_type_canary_enabled": bool(enable_open_chat_no_type_canary),
        "blockers": blockers,
        "unsafe_blockers": unsafe_blockers,
        "customer_send_performed": False,
        "kaspi_chat_write_performed": False,
        "chat_opened": False,
        "message_text_typed": False,
        "message_sent": False,
        "raw_order_id_exported": False,
        "raw_customer_text_exported": False,
        "raw_phone_exported": False,
        "raw_session_material_exported": False,
    }
    result["transport_plan"] = _build_open_chat_no_type_transport_plan(
        command=command,
        preflight_result=result,
    )
    return result


def _build_open_chat_no_type_transport_plan(
    *,
    command: dict[str, Any],
    preflight_result: dict[str, Any],
) -> dict[str, Any]:
    if preflight_result.get("gate") != OPEN_CHAT_PREFLIGHT_READY_GATE:
        return {
            "gate": OPEN_CHAT_TRANSPORT_PLAN_BLOCKED_GATE,
            "blockers": ["open_chat_no_type_preflight_not_green"],
            "customer_send_performed": False,
            "kaspi_chat_write_performed": False,
            "chat_opened": False,
            "message_text_typed": False,
            "message_sent": False,
            "raw_order_id_exported": False,
            "raw_customer_text_exported": False,
            "raw_phone_exported": False,
            "raw_session_material_exported": False,
        }

    expected_merchant_id = str(command.get("expected_merchant_account_id") or "").strip()
    selected_status_filter = str(preflight_result.get("selected_status_filter") or "").strip()
    status_filter_candidates = [
        value
        for value in [
            selected_status_filter,
            *(_split_csv(command.get("extra_status_filters")) or []),
            DEFAULT_STATUS_FILTER,
        ]
        if value
    ]
    deduped_status_filters: list[str] = []
    for value in status_filter_candidates:
        if value not in deduped_status_filters:
            deduped_status_filters.append(value)

    blockers: list[str] = []
    if not expected_merchant_id:
        blockers.append("expected_merchant_account_id_missing")
    if not deduped_status_filters:
        blockers.append("status_filter_missing")

    gate = OPEN_CHAT_TRANSPORT_PLAN_BLOCKED_GATE if blockers else OPEN_CHAT_TRANSPORT_PLAN_READY_GATE
    return {
        "gate": gate,
        "recorded_at": _safe_now(),
        "blockers": blockers,
        "purpose": "deterministic_ui_transport_plan_for_one_order_open_chat_no_type_canary",
        "selected_order_ref": preflight_result.get("selected_order_ref"),
        "selected_db_row_id": preflight_result.get("selected_db_row_id"),
        "selected_store_code": preflight_result.get("selected_store_code"),
        "status_filter_candidates": deduped_status_filters,
        "expected_merchant_account_id": expected_merchant_id,
        "expected_merchant_selector_text": f"ID - {expected_merchant_id}" if expected_merchant_id else "",
        "chat_button_selector": CHAT_BUTTON_SELECTOR,
        "order_search_input_selector": ORDER_SEARCH_INPUT_SELECTOR,
        "runtime_only_values": [
            "raw_order_id",
            "current_visible_customer_chat_dom",
            "observed_route_flags",
        ],
        "steps": [
            "resolve_raw_order_id_runtime_only_from_db_row_or_order_ref",
            "navigate_to_candidate_status_url",
            "select_exact_merchant_account_before_search",
            "search_exact_raw_order_id",
            "prove_order_result_and_chat_button_for_selected_order",
            "open_customer_message_ui_for_selected_order_only",
            "type_nothing",
            "send_nothing",
            "record_redacted_open_chat_no_type_result",
            "validate_open_chat_no_type_result",
            "leave_resident_browser_session_open",
        ],
        "stoplines": [
            "visible_merchant_selector_not_exact_expected_id",
            "order_not_visible_in_target_store_status_filter",
            "chat_button_absent_for_selected_order",
            "message_input_autofocused_with_text",
            "send_or_typing_route_observed",
            "any_second_order_or_bulk_action_risk",
            "login_or_sms_gate_visible",
        ],
        "redaction_policy": {
            "raw_order_id_exported": False,
            "raw_customer_text_exported": False,
            "raw_phone_exported": False,
            "raw_session_material_exported": False,
        },
        "customer_send_performed": False,
        "kaspi_chat_write_performed": False,
        "chat_opened": False,
        "message_text_typed": False,
        "message_sent": False,
    }


def _route_flags_from_events(events: list[dict[str, Any]]) -> dict[str, bool]:
    families: set[str] = set()
    reasons: set[str] = set()
    for event in events:
        for family in route_families(event):
            families.add(family)
        reason = str(event.get("reason") or "")
        if reason:
            reasons.add(reason)
    return {
        "send_message_route_observed": "send_message_write_risk" in families
        or "send_message_route_blocked_no_send" in reasons,
        "typing_send_text_route_observed": "typing_send_text_write_risk" in families
        or "typing_send_text_route_blocked_no_send" in reasons,
        "start_chat_route_observed": "start_chat_write_risk" in families
        or "start_chat_route_blocked_no_send" in reasons,
        "message_status_change_route_observed": "message_status_read_side_effect_risk" in families
        or "message_status_change_route_blocked_read_side_effect_unknown" in reasons,
        "load_more_messages_route_observed": "load_more_messages" in families,
    }


def _open_chat_blocking_unsafe_route_observed(route_flags: dict[str, bool]) -> bool:
    return bool(
        route_flags.get("send_message_route_observed")
        or route_flags.get("typing_send_text_route_observed")
        or route_flags.get("start_chat_route_observed")
    )


def _message_input_state(page) -> dict[str, Any]:
    try:
        return page.evaluate(
            """(selectors) => {
                const nodes = [];
                for (const selector of selectors) {
                    for (const node of document.querySelectorAll(selector)) {
                        const rect = node.getBoundingClientRect();
                        const style = window.getComputedStyle(node);
                        const visible = !!(rect.width || rect.height) &&
                          style.visibility !== "hidden" &&
                          style.display !== "none";
                        if (!visible) continue;
                        const value = "value" in node ? (node.value || "") : (node.textContent || "");
                        nodes.push({selector, value_length: String(value || "").trim().length});
                    }
                }
                return {
                  message_input_present: nodes.length > 0,
                  message_input_has_text: nodes.some((node) => node.value_length > 0),
                  visible_message_input_count: nodes.length
                };
            }""",
            MESSAGE_INPUT_CANDIDATE_SELECTORS,
        )
    except Exception as exc:
        return {
            "message_input_present": False,
            "message_input_has_text": False,
            "visible_message_input_count": 0,
            "message_input_state_error": type(exc).__name__,
        }


def _visible_open_chat_button(page) -> tuple[str, Any] | tuple[str, None]:
    for selector in OPEN_CHAT_BUTTON_CANDIDATE_SELECTORS:
        try:
            locator = page.locator(selector).first
            if locator.count() <= 0:
                continue
            if not locator.is_visible(timeout=1000):
                continue
            return selector, locator
        except Exception:
            continue
    return "", None


def _selector_list_sha256() -> str:
    return hashlib.sha256(
        json.dumps(OPEN_CHAT_BUTTON_CANDIDATE_SELECTORS, ensure_ascii=False, sort_keys=True).encode(
            "utf-8"
        )
    ).hexdigest()


def _selector_dom_diagnostic(page) -> dict[str, Any]:
    """Return sanitized customer-message control metadata without clicking."""
    css_selectors = [
        selector for selector in OPEN_CHAT_BUTTON_CANDIDATE_SELECTORS if not selector.startswith("xpath=")
    ]
    markers = ["Написать покупателю", "Сообщение покупателю", "Сообщения по заказу"]
    try:
        return page.evaluate(
            """(args) => {
                const cssSelectors = args.cssSelectors || [];
                const markers = args.markers || [];
                const candidates = [];
                const clickTargets = [];
                const targetIndex = new Map();
                const classBuckets = (node) => {
                    const classText = String(node.getAttribute("class") || "").toLowerCase();
                    return {
                        has_init_chat_button: classText.includes("init-chat-button"),
                        has_chat_section: classText.includes("chat-section"),
                        has_chat_token: classText.includes("chat"),
                        has_button_token: classText.includes("button"),
                        has_message_token: classText.includes("message") || classText.includes("msg")
                    };
                };
                const fingerprint = (node) => {
                    if (!node) return null;
                    const tag = String(node.tagName || "").toLowerCase();
                    const role = String(node.getAttribute("role") || "");
                    const type = String(node.getAttribute("type") || "");
                    const aria = String(node.getAttribute("aria-label") || "");
                    const title = String(node.getAttribute("title") || "");
                    return {
                        tag_name: tag,
                        role_bucket: role ? "present" : "missing",
                        type_bucket: type === "CLIENT_SELLER_BY_ORDER" ? "client_seller_by_order" : (type ? "other" : "missing"),
                        class_buckets: classBuckets(node),
                        aria_label_bucket: aria ? "present_redacted" : "missing",
                        title_bucket: title ? "present_redacted" : "missing"
                    };
                };
                const containmentBucket = (node) => (
                    node && node.closest("tr,[class*='order'],[class*='delivery'],[class*='card'],[class*='section']")
                ) ? "near_order_like_container" : "unknown";
                const isVisible = (node) => {
                    const rect = node.getBoundingClientRect();
                    const style = window.getComputedStyle(node);
                    return !!(rect.width || rect.height) &&
                        style.visibility !== "hidden" &&
                        style.display !== "none" &&
                        style.opacity !== "0";
                };
                const isEnabled = (node) => !node.disabled && node.getAttribute("aria-disabled") !== "true";
                const isUnsafeControl = (node) => {
                    if (!node) return false;
                    const classText = String(node.getAttribute("class") || "").toLowerCase();
                    const aria = String(node.getAttribute("aria-label") || "").toLowerCase();
                    const title = String(node.getAttribute("title") || "").toLowerCase();
                    const type = String(node.getAttribute("type") || "").toLowerCase();
                    const joined = `${classText} ${aria} ${title} ${type}`;
                    return joined.includes("send") ||
                        joined.includes("typing") ||
                        joined.includes("status") ||
                        joined.includes("history") ||
                        joined.includes("upload") ||
                        joined.includes("file") ||
                        joined.includes("attach");
                };
                const isSafeChatClickable = (node) => {
                    if (!node) return false;
                    const tag = String(node.tagName || "").toLowerCase();
                    const role = String(node.getAttribute("role") || "").toLowerCase();
                    const type = String(node.getAttribute("type") || "");
                    const classText = String(node.getAttribute("class") || "").toLowerCase();
                    if (isUnsafeControl(node)) return false;
                    const hasChatAction =
                        type === "CLIENT_SELLER_BY_ORDER" ||
                        tag === "init-chat-button" ||
                        classText.includes("init-chat-button") ||
                        classText.includes("chat-section");
                    if (!hasChatAction) return false;
                    return tag === "button" ||
                        tag === "init-chat-button" ||
                        role === "button" ||
                        type === "CLIENT_SELLER_BY_ORDER" ||
                        classText.includes("init-chat-button") ||
                        classText.includes("chat-section");
                };
                const nearestSafeClickable = (node) => {
                    let current = node;
                    for (let depth = 0; current && depth <= 6; depth += 1, current = current.parentElement) {
                        if (isSafeChatClickable(current)) return {depth, node: current};
                    }
                    return {depth: null, node: null};
                };
                const buildSafeSelector = (node) => {
                    if (!node) return "";
                    const tag = String(node.tagName || "").toLowerCase();
                    const type = String(node.getAttribute("type") || "");
                    const classText = String(node.getAttribute("class") || "").toLowerCase();
                    const classes = [];
                    if (classText.includes("init-chat-button")) classes.push("init-chat-button");
                    if (classText.includes("chat-section")) classes.push("chat-section");
                    const typeSuffix = type === "CLIENT_SELLER_BY_ORDER" ? "[type='CLIENT_SELLER_BY_ORDER']" : "";
                    const classSuffix = classes.length ? `.${classes.join(".")}` : "";
                    if (tag === "init-chat-button" && typeSuffix) return `${tag}${typeSuffix}`;
                    if (tag && (classSuffix || typeSuffix)) return `${tag}${classSuffix}${typeSuffix}`;
                    return "";
                };
                const addClickTarget = (node, source, depth) => {
                    if (!node) return null;
                    const visible = isVisible(node);
                    const enabled = isEnabled(node);
                    const containment = containmentBucket(node);
                    const eligible = visible && enabled && containment === "near_order_like_container";
                    let target = targetIndex.get(node);
                    if (target === undefined) {
                        target = {
                            source_buckets: [],
                            raw_anchor_count: 0,
                            min_clickable_ancestor_depth: depth,
                            max_clickable_ancestor_depth: depth,
                            clickable_fingerprint: fingerprint(node),
                            recommended_click_selector: buildSafeSelector(node),
                            selected_order_containment_bucket: containment,
                            visible,
                            enabled,
                            visible_enabled: visible && enabled,
                            eligible_click_target: eligible
                        };
                        targetIndex.set(node, target);
                        clickTargets.push(target);
                    }
                    target.source_buckets.push(source);
                    target.raw_anchor_count += 1;
                    if (depth !== null) {
                        target.min_clickable_ancestor_depth = Math.min(target.min_clickable_ancestor_depth, depth);
                        target.max_clickable_ancestor_depth = Math.max(target.max_clickable_ancestor_depth, depth);
                    }
                    return target;
                };
                const addCandidate = (node, source) => {
                    if (!node) return;
                    const nearest = nearestSafeClickable(node);
                    const clickableNode = nearest.node || node;
                    const visible = isVisible(clickableNode);
                    const enabled = isEnabled(clickableNode);
                    const clickTarget = nearest.node ? addClickTarget(nearest.node, source, nearest.depth) : null;
                    candidates.push({
                        source_bucket: source,
                        node_fingerprint: fingerprint(node),
                        clickable_ancestor_depth: nearest.depth,
                        clickable_fingerprint: fingerprint(clickableNode),
                        eligible_click_target: !!(clickTarget && clickTarget.eligible_click_target),
                        visible,
                        enabled,
                        visible_enabled: visible && enabled,
                        selected_order_containment_bucket: containmentBucket(clickableNode)
                    });
                };
                for (const selector of cssSelectors) {
                    try {
                        for (const node of document.querySelectorAll(selector)) {
                            addCandidate(node, `css:${selector}`);
                        }
                    } catch (error) {
                        // Ignore unsupported CSS selectors; Playwright-only selectors are filtered before this script.
                    }
                }
                const walker = document.createTreeWalker(document.body || document.documentElement, NodeFilter.SHOW_ELEMENT);
                while (walker.nextNode()) {
                    const node = walker.currentNode;
                    const text = String(node.innerText || node.textContent || "");
                    if (!text) continue;
                    for (let index = 0; index < markers.length; index += 1) {
                        if (text.includes(markers[index])) {
                            addCandidate(node, `text_marker:${index}`);
                            break;
                        }
                    }
                }
                const visibleEnabled = candidates.filter((item) => item.visible_enabled);
                const visibleEnabledClickTargets = clickTargets.filter((item) => item.eligible_click_target);
                const recommended = visibleEnabledClickTargets.length === 1 ? visibleEnabledClickTargets[0] : null;
                return {
                    selector_code_sha256: args.selectorCodeSha256,
                    candidate_count: candidates.length,
                    visible_enabled_candidate_count: visibleEnabled.length,
                    click_target_count: clickTargets.length,
                    visible_enabled_click_target_count: visibleEnabledClickTargets.length,
                    recommended_click_selector: recommended ? recommended.recommended_click_selector : "",
                    recommended_selector_family: recommended ? recommended.clickable_fingerprint.tag_name : "",
                    click_targets: clickTargets.slice(0, 10),
                    candidates: candidates.slice(0, 25),
                    raw_html_exported: false,
                    raw_text_exported: false,
                    raw_href_exported: false,
                    raw_order_id_exported: false,
                    raw_customer_text_exported: false,
                    raw_phone_exported: false,
                    raw_session_material_exported: false
                };
            }""",
            {
                "cssSelectors": css_selectors,
                "markers": markers,
                "selectorCodeSha256": _selector_list_sha256(),
            },
        )
    except Exception as exc:
        return {
            "selector_code_sha256": _selector_list_sha256(),
            "candidate_count": 0,
            "visible_enabled_candidate_count": 0,
            "click_target_count": 0,
            "visible_enabled_click_target_count": 0,
            "recommended_click_selector": "",
            "recommended_selector_family": "",
            "click_targets": [],
            "candidates": [],
            "diagnostic_error": type(exc).__name__,
            "raw_html_exported": False,
            "raw_text_exported": False,
            "raw_href_exported": False,
            "raw_order_id_exported": False,
            "raw_customer_text_exported": False,
            "raw_phone_exported": False,
            "raw_session_material_exported": False,
        }


def _write_open_chat_result_closeout(path: Path, result_payload: dict[str, Any]) -> None:
    path.write_text(
        "\n".join(
            [
                "# Kaspi Open-Chat No-Type Side-Effect Canary Closeout",
                "",
                f"Gate: {OPEN_CHAT_RESULT_GREEN_GATE}",
                "",
                f"- Selected order ref: {result_payload.get('selected_order_ref')}",
                f"- Store: {result_payload.get('selected_store_code')}",
                f"- Visible merchant selector ID: {result_payload.get('visible_merchant_selector_id')}",
                "- Source: resident_controller",
                "- Chat opened: true",
                "- Message text typed: false",
                "- Message sent: false",
                "- Raw order ID/customer text/phone/session material exported: false",
                "",
            ]
        ),
        encoding="utf-8",
    )


def _run_open_chat_no_type_command(
    *,
    command: dict[str, Any],
    page,
    persistent_profile_dir: Path,
    unsafe_events: list[dict[str, Any]],
    db_path: Path,
    enable_open_chat_no_type_canary: bool,
) -> dict[str, Any]:
    output_dir = Path(command["output_dir"]).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    preflight = _build_open_chat_no_type_preflight_result(
        command=command,
        enable_open_chat_no_type_canary=enable_open_chat_no_type_canary,
    )
    preflight_path = output_dir / "open_chat_no_type_preflight.json"
    _write_json(preflight_path, preflight)
    if preflight.get("gate") != OPEN_CHAT_PREFLIGHT_READY_GATE:
        result = {
            **preflight,
            "manifest_path": str(preflight_path),
            "customer_send_performed": False,
            "kaspi_chat_write_performed": False,
            "chat_opened": False,
            "message_text_typed": False,
            "message_sent": False,
            "raw_order_id_exported": False,
        }
        return result

    blockers: list[str] = []
    unsafe_blockers: list[str] = []
    packet_dir = Path(str(command.get("open_chat_packet_dir") or "")).resolve()
    packet_manifest = _read_json(packet_dir / "manifest.json")
    result_path = packet_dir / "open_chat_no_type_result_redacted.json"
    result_closeout_path = packet_dir / "open_chat_no_type_canary_closeout.md"
    if result_path.exists() or result_closeout_path.exists():
        blockers.append("open_chat_no_type_result_or_closeout_already_exists")

    target_date = _today_from_arg(command["target_date"])
    stores = _split_csv(command["stores"]) or [command["profile_store_code"]]
    extra_status_filters = _split_csv(command["extra_status_filters"])
    candidates = load_missing_size_candidates(
        db_path,
        target_date=target_date,
        lookback_days=int(command["lookback_days"]),
        stores=stores,
        limit=int(command["candidate_pool_limit"]),
    )
    candidates = _filter_candidates_for_command(
        candidates,
        target_db_row_ids=_split_int_csv(command.get("target_db_row_ids")),
        target_order_refs=_split_csv(command.get("target_order_refs")),
    )
    plans = plan_probes(
        candidates,
        profile_store_code=command["profile_store_code"],
        max_candidates=int(command["max_candidates"]),
        extra_status_filters=extra_status_filters,
    )
    if len(plans) != 1:
        blockers.append(f"expected_exactly_one_plan_found_{len(plans)}")

    probe_result: dict[str, Any] = {}
    visible_merchant_selector_id = ""
    chat_button_clicked = False
    chat_button_click_selector = ""
    click_events: list[dict[str, Any]] = []
    command_unsafe_start = len(unsafe_events)
    message_input_state: dict[str, Any] = {}

    if not blockers and plans:
        probe_result = _probe_one(
            page,
            plans[0],
            profile_store_code=command["profile_store_code"],
            timeout_ms=int(command["timeout_ms"]),
            expand_order_result=True,
        )
        after_ids = probe_result.get("observed_merchant_account_ids_after") or []
        if after_ids:
            visible_merchant_selector_id = str(after_ids[0])
        if probe_result.get("merchant_account_match_proven") is not True:
            blockers.append("merchant_account_match_not_proven")
        if probe_result.get("result_or_detail_reached") is not True:
            blockers.append("selected_order_result_not_reached")
        if probe_result.get("chat_button_present") is not True:
            blockers.append("chat_button_not_present_for_selected_order")

    def on_request(request) -> None:  # type: ignore[no-untyped-def]
        click_events.append(
            build_request_event(
                method=request.method,
                url=request.url,
                resource_type=request.resource_type,
            )
        )

    if not blockers:
        page.on("request", on_request)
        try:
            chat_button_click_selector, chat_button = _visible_open_chat_button(page)
            if chat_button is None:
                blockers.append("chat_button_locator_missing_at_click_time")
            else:
                chat_button.click(timeout=min(int(command["timeout_ms"]), 5000))
                chat_button_clicked = True
                page.wait_for_timeout(1500)
                message_input_state = _message_input_state(page)
                if message_input_state.get("message_input_present") is not True:
                    blockers.append("message_input_not_visible_after_open_click")
                if message_input_state.get("message_input_has_text") is True:
                    unsafe_blockers.append("message_input_has_text_after_open")
        except Exception as exc:
            blockers.append(f"chat_button_click_failed:{type(exc).__name__}")
        finally:
            try:
                page.remove_listener("request", on_request)
            except Exception:
                pass

    command_unsafe_events = unsafe_events[command_unsafe_start:]
    route_flags = _route_flags_from_events([*click_events, *command_unsafe_events])
    if _open_chat_blocking_unsafe_route_observed(route_flags):
        unsafe_blockers.append("send_typing_or_start_chat_route_observed")

    result_payload: dict[str, Any] | None = None
    if not blockers and not unsafe_blockers and chat_button_clicked:
        result_payload = build_observed_open_result(
            manifest=packet_manifest,
            visible_merchant_selector_id=visible_merchant_selector_id,
            proof_source="resident_controller_observed",
            proof_note="redacted_open_only_no_type_no_send",
            route_flags=route_flags,
        )
        if result_payload.get("merchant_account_match_proven") is not True:
            unsafe_blockers.append("visible_merchant_selector_mismatch")

    gate = (
        OPEN_CHAT_RESULT_GREEN_GATE
        if result_payload is not None and not blockers and not unsafe_blockers
        else OPEN_CHAT_UNSAFE_GATE
        if unsafe_blockers
        else OPEN_CHAT_TRANSPORT_PLAN_BLOCKED_GATE
    )
    if result_payload is not None and gate == OPEN_CHAT_RESULT_GREEN_GATE:
        _write_json(result_path, result_payload)
        _write_open_chat_result_closeout(result_closeout_path, result_payload)

    manifest = {
        "gate": gate,
        "recorded_at": _safe_now(),
        "command_id": command.get("command_id"),
        "action": command.get("action"),
        "packet_dir": str(packet_dir),
        "packet_result_path": str(result_path),
        "packet_closeout_path": str(result_closeout_path),
        "preflight_path": str(preflight_path),
        "selected_order_ref": command.get("target_order_refs"),
        "selected_db_row_id": command.get("target_db_row_ids"),
        "selected_store_code": command.get("stores"),
        "expected_merchant_account_id": command.get("expected_merchant_account_id"),
        "visible_merchant_selector_id": visible_merchant_selector_id,
        "persistent_profile_dir_path": str(persistent_profile_dir),
        "probe_result_or_detail_reached": bool(probe_result.get("result_or_detail_reached")),
        "probe_chat_button_present": bool(probe_result.get("chat_button_present")),
        "chat_button_clicked": chat_button_clicked,
        "chat_button_click_selector": chat_button_click_selector,
        "chat_button_candidate_selectors": OPEN_CHAT_BUTTON_CANDIDATE_SELECTORS,
        "chat_opened": gate == OPEN_CHAT_RESULT_GREEN_GATE,
        "message_input_state": message_input_state,
        "route_flags": route_flags,
        "blockers": blockers,
        "unsafe_blockers": unsafe_blockers,
        "customer_send_performed": False,
        "kaspi_chat_write_performed": False,
        "message_text_typed": False,
        "message_sent": False,
        "raw_order_id_exported": False,
        "raw_customer_text_exported": False,
        "raw_phone_exported": False,
        "raw_session_material_exported": False,
    }
    manifest_path = output_dir / "open_chat_no_type_resident_result.json"
    closeout_path = output_dir / "open_chat_no_type_resident_closeout.md"
    _write_json(manifest_path, manifest)
    closeout_path.write_text(
        "\n".join(
            [
                "# Resident Kaspi Open-Chat No-Type Command",
                "",
                f"Gate: {gate}",
                "",
                f"- Manifest: `{manifest_path}`",
                f"- Packet result: `{result_path}`",
                f"- Chat button clicked: {str(chat_button_clicked).lower()}",
                "- Message text typed: false",
                "- Message sent: false",
                "- Raw order/customer/session material exported: false",
                "",
            ]
        ),
        encoding="utf-8",
    )
    return {
        **manifest,
        "manifest_path": str(manifest_path),
        "closeout_path": str(closeout_path),
    }


def _run_open_chat_selector_dom_diagnostic_command(
    *,
    command: dict[str, Any],
    page,
    persistent_profile_dir: Path,
    unsafe_events: list[dict[str, Any]],
    db_path: Path,
) -> dict[str, Any]:
    output_dir = Path(command["output_dir"]).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    blockers: list[str] = []
    unsafe_blockers: list[str] = []
    target_date = _today_from_arg(command["target_date"])
    stores = _split_csv(command["stores"]) or [command["profile_store_code"]]
    extra_status_filters = _split_csv(command["extra_status_filters"])
    candidates = load_missing_size_candidates(
        db_path,
        target_date=target_date,
        lookback_days=int(command["lookback_days"]),
        stores=stores,
        limit=int(command["candidate_pool_limit"]),
    )
    candidates = _filter_candidates_for_command(
        candidates,
        target_db_row_ids=_split_int_csv(command.get("target_db_row_ids")),
        target_order_refs=_split_csv(command.get("target_order_refs")),
    )
    plans = plan_probes(
        candidates,
        profile_store_code=command["profile_store_code"],
        max_candidates=int(command["max_candidates"]),
        extra_status_filters=extra_status_filters,
    )
    if len(plans) != 1:
        blockers.append(f"expected_exactly_one_plan_found_{len(plans)}")

    probe_result: dict[str, Any] = {}
    visible_merchant_selector_id = ""
    command_unsafe_start = len(unsafe_events)
    diagnostic: dict[str, Any] = {
        "selector_code_sha256": _selector_list_sha256(),
        "candidate_count": 0,
        "visible_enabled_candidate_count": 0,
        "click_target_count": 0,
        "visible_enabled_click_target_count": 0,
        "recommended_click_selector": "",
        "recommended_selector_family": "",
        "click_targets": [],
        "candidates": [],
        "raw_html_exported": False,
        "raw_text_exported": False,
        "raw_href_exported": False,
        "raw_order_id_exported": False,
        "raw_customer_text_exported": False,
        "raw_phone_exported": False,
        "raw_session_material_exported": False,
    }

    if not blockers and plans:
        probe_result = _probe_one(
            page,
            plans[0],
            profile_store_code=command["profile_store_code"],
            timeout_ms=int(command["timeout_ms"]),
            expand_order_result=True,
        )
        after_ids = probe_result.get("observed_merchant_account_ids_after") or []
        if after_ids:
            visible_merchant_selector_id = str(after_ids[0])
        if probe_result.get("merchant_account_match_proven") is not True:
            blockers.append("merchant_account_match_not_proven")
        if probe_result.get("result_or_detail_reached") is not True:
            blockers.append("selected_order_result_not_reached")
        if probe_result.get("chat_button_present") is not True:
            blockers.append("chat_button_not_present_for_selected_order")

    if not blockers:
        diagnostic = _selector_dom_diagnostic(page)
        if diagnostic.get("raw_html_exported") is not False:
            unsafe_blockers.append("diagnostic_raw_html_exported_not_false")
        if diagnostic.get("raw_text_exported") is not False:
            unsafe_blockers.append("diagnostic_raw_text_exported_not_false")
        if diagnostic.get("raw_href_exported") is not False:
            unsafe_blockers.append("diagnostic_raw_href_exported_not_false")
        if diagnostic.get("raw_order_id_exported") is not False:
            unsafe_blockers.append("diagnostic_raw_order_id_exported_not_false")
        if diagnostic.get("raw_customer_text_exported") is not False:
            unsafe_blockers.append("diagnostic_raw_customer_text_exported_not_false")
        if diagnostic.get("raw_phone_exported") is not False:
            unsafe_blockers.append("diagnostic_raw_phone_exported_not_false")
        if diagnostic.get("raw_session_material_exported") is not False:
            unsafe_blockers.append("diagnostic_raw_session_material_exported_not_false")
        visible_enabled_click_targets = int(diagnostic.get("visible_enabled_click_target_count") or 0)
        if visible_enabled_click_targets != 1:
            blockers.append(
                f"visible_enabled_click_target_count_not_one:{visible_enabled_click_targets}"
            )
        if visible_enabled_click_targets == 1 and not str(
            diagnostic.get("recommended_click_selector") or ""
        ).strip():
            blockers.append("recommended_click_selector_missing")

    command_unsafe_events = unsafe_events[command_unsafe_start:]
    route_flags = _route_flags_from_events(command_unsafe_events)
    if any(route_flags.values()):
        unsafe_blockers.append("unexpected_route_observed_during_no_click_diagnostic")

    if unsafe_blockers:
        gate = SELECTOR_DOM_DIAGNOSTIC_RED_GATE
    elif blockers:
        gate = SELECTOR_DOM_DIAGNOSTIC_YELLOW_GATE
    else:
        gate = SELECTOR_DOM_DIAGNOSTIC_GREEN_GATE

    manifest = {
        "gate": gate,
        "recorded_at": _safe_now(),
        "action": command["action"],
        "command_id": command["command_id"],
        "output_dir": str(output_dir),
        "target_date": target_date.isoformat(),
        "selected_order_ref": command.get("target_order_refs"),
        "selected_db_row_id": command.get("target_db_row_ids"),
        "selected_store_code": command.get("stores"),
        "expected_merchant_account_id": command.get("expected_merchant_account_id"),
        "visible_merchant_selector_id": visible_merchant_selector_id,
        "merchant_account_match_proven": probe_result.get("merchant_account_match_proven") is True,
        "probe_result_or_detail_reached": probe_result.get("result_or_detail_reached") is True,
        "probe_chat_button_present": probe_result.get("chat_button_present") is True,
        "selector_dom_diagnostic": diagnostic,
        "route_flags": route_flags,
        "blockers": blockers,
        "unsafe_blockers": unsafe_blockers,
        "customer_send_performed": False,
        "kaspi_chat_write_performed": False,
        "chat_opened": False,
        "message_text_typed": False,
        "message_sent": False,
        "raw_order_id_exported": False,
        "raw_customer_text_exported": False,
        "raw_phone_exported": False,
        "raw_session_material_exported": False,
        "persistent_profile_dir_path": str(persistent_profile_dir),
    }
    manifest_path = output_dir / "open_chat_selector_dom_diagnostic_result.json"
    closeout_path = output_dir / "open_chat_selector_dom_diagnostic_closeout.md"
    _write_json(manifest_path, manifest)
    closeout_path.write_text(
        "\n".join(
            [
                "# Resident Kaspi Open-Chat Selector DOM Diagnostic",
                "",
                f"Gate: {gate}",
                "",
                f"- Manifest: `{manifest_path}`",
                f"- Visible merchant selector ID: `{visible_merchant_selector_id}`",
                f"- Visible enabled candidate count: {diagnostic.get('visible_enabled_candidate_count')}",
                f"- Visible enabled click target count: {diagnostic.get('visible_enabled_click_target_count')}",
                f"- Recommended click selector: `{diagnostic.get('recommended_click_selector') or ''}`",
                "- Chat opened: false",
                "- Message text typed: false",
                "- Message sent: false",
                "- Raw HTML/text/href/order/customer/session material exported: false",
                "",
            ]
        ),
        encoding="utf-8",
    )
    return {
        **manifest,
        "manifest_path": str(manifest_path),
        "closeout_path": str(closeout_path),
    }


def _build_live_send_preflight_result(
    *,
    command: dict[str, Any],
    enable_live_send_canary: bool,
) -> dict[str, Any]:
    """Validate a future live-send command without performing UI transport."""
    blockers: list[str] = []
    unsafe_blockers: list[str] = []

    if command.get("max_candidates") != 1:
        unsafe_blockers.append("live_send_requires_max_candidates_1")
    if not command.get("target_db_row_ids") and not command.get("target_order_refs"):
        unsafe_blockers.append("live_send_requires_exact_target_db_row_or_order_ref")

    required_true = [
        ("allow_customer_send", "command_allow_customer_send_not_true"),
        ("kaspi_chat_write_allowed", "command_kaspi_chat_write_allowed_not_true"),
        ("chat_open_allowed", "command_chat_open_allowed_not_true"),
        ("message_text_typed", "command_message_text_typed_not_true"),
        ("message_sent", "command_message_sent_not_true"),
    ]
    for key, blocker in required_true:
        if command.get(key) is not True:
            unsafe_blockers.append(blocker)

    if unsafe_blockers:
        gate = LIVE_SEND_UNSAFE_GATE
        return {
            "gate": gate,
            "recorded_at": _safe_now(),
            "command_id": command.get("command_id"),
            "action": command.get("action"),
            "selected_order_ref": command.get("target_order_refs"),
            "selected_db_row_id": command.get("target_db_row_ids"),
            "selected_store_code": command.get("stores"),
            "expected_merchant_account_id": command.get("expected_merchant_account_id"),
            "template_hash": command.get("template_hash"),
            "approval_dir": command.get("approval_dir"),
            "live_send_execution_preflight_manifest": command.get("live_send_execution_preflight_manifest"),
            "controller_live_send_canary_enabled": bool(enable_live_send_canary),
            "blockers": blockers,
            "unsafe_blockers": unsafe_blockers,
            "customer_send_performed": False,
            "kaspi_chat_write_performed": False,
            "chat_opened": False,
            "message_text_typed": False,
            "message_sent": False,
            "raw_order_id_exported": False,
            "raw_customer_text_exported": False,
            "raw_phone_exported": False,
            "raw_session_material_exported": False,
        }

    if not enable_live_send_canary:
        blockers.append("controller_live_send_canary_not_enabled")
        gate = LIVE_SEND_DISABLED_GATE
        return {
            "gate": gate,
            "recorded_at": _safe_now(),
            "command_id": command.get("command_id"),
            "action": command.get("action"),
            "selected_order_ref": command.get("target_order_refs"),
            "selected_db_row_id": command.get("target_db_row_ids"),
            "selected_store_code": command.get("stores"),
            "expected_merchant_account_id": command.get("expected_merchant_account_id"),
            "template_hash": command.get("template_hash"),
            "approval_dir": command.get("approval_dir"),
            "live_send_execution_preflight_manifest": command.get("live_send_execution_preflight_manifest"),
            "controller_live_send_canary_enabled": False,
            "blockers": blockers,
            "unsafe_blockers": unsafe_blockers,
            "customer_send_performed": False,
            "kaspi_chat_write_performed": False,
            "chat_opened": False,
            "message_text_typed": False,
            "message_sent": False,
            "raw_order_id_exported": False,
            "raw_customer_text_exported": False,
            "raw_phone_exported": False,
            "raw_session_material_exported": False,
        }

    approval_dir = str(command.get("approval_dir") or "").strip()
    approval_manifest: dict[str, Any] = {}
    if approval_dir:
        approval_manifest, approval_error = _safe_read_json(str(Path(approval_dir) / "manifest.json"))
        if approval_error:
            blockers.append(f"approval_manifest_{approval_error}")
    else:
        blockers.append("approval_dir_missing")

    preflight_manifest, preflight_error = _safe_read_json(
        str(command.get("live_send_execution_preflight_manifest") or "")
    )
    if preflight_error:
        blockers.append(f"execution_preflight_manifest_{preflight_error}")

    if approval_manifest and approval_manifest.get("gate") != APPROVAL_GREEN_GATE:
        blockers.append(f"approval_manifest_gate_not_green:{approval_manifest.get('gate')}")
    if preflight_manifest and preflight_manifest.get("gate") != EXECUTION_PREFLIGHT_GREEN_GATE:
        blockers.append(f"execution_preflight_gate_not_green:{preflight_manifest.get('gate')}")
    if preflight_manifest and preflight_manifest.get("owner_approval_text_match") is not True:
        blockers.append("execution_preflight_owner_approval_text_not_matched")

    expected_pairs = [
        ("selected_order_ref", command.get("target_order_refs")),
        ("selected_db_row_id", command.get("target_db_row_ids")),
        ("selected_store_code", command.get("stores")),
        ("expected_merchant_account_id", command.get("expected_merchant_account_id")),
        ("template_hash", command.get("template_hash")),
    ]
    for field, command_value in expected_pairs:
        command_text = str(command_value or "").strip()
        if not command_text:
            continue
        if approval_manifest and str(approval_manifest.get(field) or "").strip() != command_text:
            unsafe_blockers.append(f"approval_manifest_{field}_mismatch")
        if preflight_manifest and str(preflight_manifest.get(field) or "").strip() != command_text:
            unsafe_blockers.append(f"execution_preflight_{field}_mismatch")

    if unsafe_blockers:
        gate = LIVE_SEND_UNSAFE_GATE
    elif blockers:
        gate = LIVE_SEND_DISABLED_GATE if blockers == ["controller_live_send_canary_not_enabled"] else LIVE_SEND_PREFLIGHT_BLOCKED_GATE
    else:
        gate = LIVE_SEND_PREFLIGHT_READY_GATE

    result = {
        "gate": gate,
        "recorded_at": _safe_now(),
        "command_id": command.get("command_id"),
        "action": command.get("action"),
        "selected_order_ref": command.get("target_order_refs"),
        "selected_db_row_id": command.get("target_db_row_ids"),
        "selected_store_code": command.get("stores"),
        "selected_status_filter": approval_manifest.get("selected_status_filter")
        or preflight_manifest.get("selected_status_filter")
        or "",
        "expected_merchant_account_id": command.get("expected_merchant_account_id"),
        "template_hash": command.get("template_hash"),
        "approval_dir": approval_dir,
        "live_send_execution_preflight_manifest": command.get("live_send_execution_preflight_manifest"),
        "controller_live_send_canary_enabled": bool(enable_live_send_canary),
        "blockers": blockers,
        "unsafe_blockers": unsafe_blockers,
        "customer_send_performed": False,
        "kaspi_chat_write_performed": False,
        "chat_opened": False,
        "message_text_typed": False,
        "message_sent": False,
        "raw_order_id_exported": False,
        "raw_customer_text_exported": False,
        "raw_phone_exported": False,
        "raw_session_material_exported": False,
    }
    result["transport_plan"] = _build_live_send_transport_plan(command=command, preflight_result=result)
    return result


def _build_live_send_transport_plan(
    *,
    command: dict[str, Any],
    preflight_result: dict[str, Any],
) -> dict[str, Any]:
    """Return deterministic UI transport instructions, but never touch the page.

    This keeps the dangerous part explicit and testable. A future write-enabled
    controller/helper can follow this plan only after the preflight gate is green.
    """
    if preflight_result.get("gate") != LIVE_SEND_PREFLIGHT_READY_GATE:
        return {
            "gate": LIVE_SEND_TRANSPORT_PLAN_BLOCKED_GATE,
            "blockers": ["live_send_preflight_not_green"],
            "customer_send_performed": False,
            "kaspi_chat_write_performed": False,
            "chat_opened": False,
            "message_text_typed": False,
            "message_sent": False,
            "raw_order_id_exported": False,
            "raw_customer_text_exported": False,
            "raw_phone_exported": False,
            "raw_session_material_exported": False,
        }

    expected_merchant_id = str(command.get("expected_merchant_account_id") or "").strip()
    template_hash = str(command.get("template_hash") or "").strip()
    selected_status_filter = str(preflight_result.get("selected_status_filter") or "").strip()
    status_filter_candidates = [
        value
        for value in [
            selected_status_filter,
            *(_split_csv(command.get("extra_status_filters")) or []),
            DEFAULT_STATUS_FILTER,
        ]
        if value
    ]
    deduped_status_filters: list[str] = []
    for value in status_filter_candidates:
        if value not in deduped_status_filters:
            deduped_status_filters.append(value)

    blockers: list[str] = []
    if not expected_merchant_id:
        blockers.append("expected_merchant_account_id_missing")
    if not template_hash:
        blockers.append("template_hash_missing")
    if not deduped_status_filters:
        blockers.append("status_filter_missing")

    gate = LIVE_SEND_TRANSPORT_PLAN_BLOCKED_GATE if blockers else LIVE_SEND_TRANSPORT_PLAN_READY_GATE
    return {
        "gate": gate,
        "recorded_at": _safe_now(),
        "blockers": blockers,
        "purpose": "deterministic_ui_transport_plan_for_future_exact_one_order_canary",
        "selected_order_ref": preflight_result.get("selected_order_ref"),
        "selected_db_row_id": preflight_result.get("selected_db_row_id"),
        "selected_store_code": preflight_result.get("selected_store_code"),
        "status_filter_candidates": deduped_status_filters,
        "expected_merchant_account_id": expected_merchant_id,
        "expected_merchant_selector_text": f"ID - {expected_merchant_id}" if expected_merchant_id else "",
        "chat_button_selector": CHAT_BUTTON_SELECTOR,
        "order_search_input_selector": ORDER_SEARCH_INPUT_SELECTOR,
        "message_input_candidate_selectors": MESSAGE_INPUT_CANDIDATE_SELECTORS,
        "send_button_candidate_selectors": SEND_BUTTON_CANDIDATE_SELECTORS,
        "runtime_only_values": [
            "raw_order_id",
            "current_visible_customer_chat_dom",
            "customer_chat_send_confirmation",
        ],
        "steps": [
            "resolve_raw_order_id_runtime_only_from_db_row_or_order_ref",
            "navigate_to_candidate_status_url",
            "select_exact_merchant_account_before_search",
            "search_exact_raw_order_id",
            "prove_order_result_and_chat_button_for_selected_order",
            "open_customer_message_ui_for_selected_order_only",
            "type_exact_template_text_once",
            "send_once",
            "record_redacted_result_via_live_send_ui_executor",
            "leave_resident_browser_session_open",
        ],
        "stoplines": [
            "visible_merchant_selector_not_exact_expected_id",
            "order_not_visible_in_target_store_status_filter",
            "chat_button_absent_for_selected_order",
            "message_input_not_identified",
            "send_button_not_identified",
            "send_confirmation_not_observed",
            "any_second_order_or_bulk_send_risk",
            "login_or_sms_gate_visible",
        ],
        "redaction_policy": {
            "raw_order_id_exported": False,
            "raw_customer_text_exported": False,
            "raw_phone_exported": False,
            "raw_session_material_exported": False,
        },
        "customer_send_performed": False,
        "kaspi_chat_write_performed": False,
        "chat_opened": False,
        "message_text_typed": False,
        "message_sent": False,
    }


def _pending_command_files(commands_dir: Path) -> list[Path]:
    return sorted(
        path
        for path in commands_dir.glob("*.json")
        if not path.name.endswith(".done.json") and not path.name.endswith(".failed.json")
    )


def _mark_command(path: Path, command: dict[str, Any], result: dict[str, Any]) -> None:
    payload = {
        **command,
        "status": "done" if not str(result.get("gate") or "").startswith("RED_") else "failed",
        "completed_at": _safe_now(),
        "result": result,
    }
    suffix = ".done.json" if payload["status"] == "done" else ".failed.json"
    destination = path.with_name(path.stem + suffix)
    _write_json(destination, payload)
    try:
        path.unlink()
    except FileNotFoundError:
        pass


def _run_ui_search_command(
    *,
    command: dict[str, Any],
    page,
    persistent_profile_dir: Path,
    unsafe_events: list[dict[str, Any]],
    db_path: Path,
    expand_order_result: bool = False,
    require_chat_button: bool = False,
) -> dict[str, Any]:
    output_dir = Path(command["output_dir"]).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    target_date = _today_from_arg(command["target_date"])
    stores = _split_csv(command["stores"]) or [command["profile_store_code"]]
    extra_status_filters = _split_csv(command["extra_status_filters"])
    candidates = load_missing_size_candidates(
        db_path,
        target_date=target_date,
        lookback_days=int(command["lookback_days"]),
        stores=stores,
        limit=int(command["candidate_pool_limit"]),
    )
    candidates = _filter_candidates_for_command(
        candidates,
        target_db_row_ids=_split_int_csv(command.get("target_db_row_ids")),
        target_order_refs=_split_csv(command.get("target_order_refs")),
    )
    plans = plan_probes(
        candidates,
        profile_store_code=command["profile_store_code"],
        max_candidates=int(command["max_candidates"]),
        extra_status_filters=extra_status_filters,
    )
    raw_order_ids = [plan.candidate.raw_order_id for plan in plans]
    command_unsafe_start = len(unsafe_events)
    results: list[dict[str, Any]] = []
    for plan in plans:
        results.append(
            _probe_one(
                page,
                plan,
                profile_store_code=command["profile_store_code"],
                timeout_ms=int(command["timeout_ms"]),
                expand_order_result=expand_order_result,
            )
        )
        if len(unsafe_events) > command_unsafe_start:
            break
    command_unsafe_events = unsafe_events[command_unsafe_start:]
    payload = build_payload(
        output_dir=output_dir,
        target_date=target_date,
        lookback_days=int(command["lookback_days"]),
        profile_store_code=command["profile_store_code"],
        persistent_profile_dir=persistent_profile_dir,
        plans=plans,
        results=results,
        unsafe_events=command_unsafe_events,
        raw_order_ids=raw_order_ids,
        require_chat_button=require_chat_button,
    )
    manifest_path = output_dir / "manifest.json"
    results_path = output_dir / "ui_search_identity_results_redacted.json"
    closeout_path = output_dir / "closeout.md"
    _write_json(manifest_path, payload)
    _write_json(results_path, {"results": payload["results"]})
    closeout_path.write_text(_build_resident_command_closeout(payload, manifest_path, results_path), encoding="utf-8")
    return {
        "gate": payload["gate"],
        "manifest_path": str(manifest_path),
        "results_path": str(results_path),
        "closeout_path": str(closeout_path),
        "found_result_count": payload["found_result_count"],
        "chat_button_found_count": payload["chat_button_found_count"],
        "candidates_scanned": payload["candidates_scanned"],
        "customer_send_allowed": False,
        "kaspi_chat_write_allowed": False,
        "chat_opened": False,
        "message_text_typed": False,
        "message_sent": False,
        "raw_order_id_exported": False,
    }


def _run_metadata_capture_command(
    *,
    command: dict[str, Any],
    page,
    persistent_profile_dir: Path,
    db_path: Path,
) -> dict[str, Any]:
    """Run a resident no-send metadata capture around order search only."""
    output_dir = Path(command["output_dir"]).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    target_date = _today_from_arg(command["target_date"])
    stores = _split_csv(command["stores"]) or [command["profile_store_code"]]
    extra_status_filters = _split_csv(command["extra_status_filters"])
    candidates = load_missing_size_candidates(
        db_path,
        target_date=target_date,
        lookback_days=int(command["lookback_days"]),
        stores=stores,
        limit=int(command["candidate_pool_limit"]),
    )
    candidates = _filter_candidates_for_command(
        candidates,
        target_db_row_ids=_split_int_csv(command.get("target_db_row_ids")),
        target_order_refs=_split_csv(command.get("target_order_refs")),
    )
    plans = plan_probes(
        candidates,
        profile_store_code=command["profile_store_code"],
        max_candidates=int(command["max_candidates"]),
        extra_status_filters=extra_status_filters,
    )
    events: list[dict[str, Any]] = []

    def on_request(request) -> None:  # type: ignore[no-untyped-def]
        events.append(
            build_request_event(
                method=request.method,
                url=request.url,
                resource_type=request.resource_type,
            )
        )

    def on_response(response) -> None:  # type: ignore[no-untyped-def]
        request = response.request
        content_type = ""
        try:
            content_type = response.headers.get("content-type", "")
        except Exception:
            content_type = ""
        events.append(
            build_response_event(
                method=request.method,
                url=response.url,
                status=response.status,
                resource_type=request.resource_type,
                content_type=content_type,
            )
        )

    def on_websocket(ws) -> None:  # type: ignore[no-untyped-def]
        events.append(build_websocket_event(url=ws.url))

    page.on("request", on_request)
    page.on("response", on_response)
    page.on("websocket", on_websocket)
    results: list[dict[str, Any]] = []
    try:
        for plan in plans:
            results.append(
                _probe_one(
                    page,
                    plan,
                    profile_store_code=command["profile_store_code"],
                    timeout_ms=int(command["timeout_ms"]),
                    expand_order_result=False,
                )
            )
            if any(unsafe_route_block_reason(str(event.get("path_template") or "")) for event in events):
                break
    finally:
        for event_name, handler in (
            ("request", on_request),
            ("response", on_response),
            ("websocket", on_websocket),
        ):
            try:
                page.remove_listener(event_name, handler)
            except Exception:
                pass

    capture = {
        "gate": "CAPTURE_PENDING",
        "captured_at": _safe_now(),
        "source": "resident_controller_metadata_no_send",
        "target_date": target_date.isoformat(),
        "lookback_days": int(command["lookback_days"]),
        "store_code": command["stores"],
        "profile_store_code": command["profile_store_code"],
        "persistent_profile_mode": True,
        "persistent_profile_dir_path": str(persistent_profile_dir),
        "selected_order_refs": [row.get("order_ref") for row in results if row.get("order_ref")],
        "candidates_planned": len(plans),
        "candidates_scanned": len(results),
        "order_search_performed": any(row.get("search_performed") for row in results),
        "merchant_account_match_count": sum(1 for row in results if row.get("merchant_account_match_proven")),
        "chat_button_seen": any(row.get("chat_button_present") for row in results),
        "events": events,
        "customer_send_allowed": False,
        "kaspi_chat_write_allowed": False,
        "chat_opened": False,
        "message_text_typed": False,
        "message_sent": False,
        "raw_order_id_exported": False,
        "raw_customer_text_exported": False,
        "raw_phone_exported": False,
        "raw_session_material_exported": False,
    }
    validation = validate_capture(capture)
    capture["gate"] = validation["gate"]
    capture_path = output_dir / "customer_chat_metadata_capture_redacted.json"
    validation_path = output_dir / "customer_chat_metadata_capture_validation.json"
    closeout_path = output_dir / "customer_chat_metadata_capture_closeout.md"
    _write_json(capture_path, capture)
    _write_json(validation_path, validation)
    closeout_path.write_text(
        build_metadata_capture_closeout(capture, validation, capture_path),
        encoding="utf-8",
    )
    return {
        "gate": validation["gate"],
        "capture_path": str(capture_path),
        "validation_path": str(validation_path),
        "closeout_path": str(closeout_path),
        "event_count": validation["event_count"],
        "candidates_scanned": len(results),
        "customer_send_allowed": False,
        "kaspi_chat_write_allowed": False,
        "raw_order_id_exported": False,
    }


def _build_resident_command_closeout(payload: dict[str, Any], manifest_path: Path, results_path: Path) -> str:
    return "\n".join(
        [
            "# Resident Kaspi Customer Chat UI Search Identity No-Send Command",
            "",
            f"Gate: {payload['gate']}",
            "",
            "## Scope",
            "",
            "- Controller mode: resident browser session; browser remains open after command.",
            f"- Profile store: {payload.get('profile_store_code')}",
            f"- Candidates scanned: {payload.get('candidates_scanned')}",
            f"- Found result count: {payload.get('found_result_count')}",
            f"- Chat button found count: {payload.get('chat_button_found_count')}",
            f"- Require chat button: {str(payload.get('require_chat_button')).lower()}",
            f"- Manifest: `{manifest_path}`",
            f"- Redacted results: `{results_path}`",
            "",
            "## Safety",
            "",
            "- Customer send allowed: false",
            "- Kaspi chat write allowed: false",
            "- Google Board write allowed: false",
            "- Chat opened: false",
            "- Message text typed: false",
            "- Message sent: false",
            "- Raw order IDs/customer text/phones/session material exported: false",
            "",
            "## Blockers",
            "",
            ", ".join(payload.get("blockers") or ["none"]),
            "",
        ]
    )


def _build_controller_closeout(heartbeat: dict[str, Any], heartbeat_path: Path) -> str:
    return "\n".join(
        [
            "# Kaspi Customer Chat Resident No-Send Controller",
            "",
            f"Gate: {heartbeat['gate']}",
            "",
            "## Scope",
            "",
            f"- Profile store: `{heartbeat['profile_store_code']}`",
            f"- Persistent profile dir: `{heartbeat['persistent_profile_dir_path']}`",
            f"- Commands dir: `{heartbeat['commands_dir']}`",
            f"- Heartbeat: `{heartbeat_path}`",
            "- Browser should remain open: true",
            "",
            "## Safety",
            "",
            "- Customer send allowed: false",
            "- Kaspi chat write allowed: false",
            "- Google Board write allowed: false",
            "- Chat opened: false",
            "- Message text typed: false",
            "- Message sent: false",
            "- Raw order IDs/customer text/phones/session material exported: false",
            "",
            "## Operator Note",
            "",
            "Leave this controller running while doing no-send diagnostics. Stop/once exits require `--allow-session-close`; without that explicit flag, the controller preserves the authenticated browser session.",
            "",
        ]
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument("--run-dir", type=Path, default=DEFAULT_RUN_DIR)
    parser.add_argument("--persistent-profile-dir", type=Path, default=DEFAULT_PERSISTENT_PROFILE_DIR)
    parser.add_argument("--profile-store-code", default="ACMEWEAR")
    parser.add_argument("--startup-status-filter", default=DEFAULT_STATUS_FILTER)
    parser.add_argument("--manual-login-timeout-seconds", type=float, default=900.0)
    parser.add_argument("--poll-seconds", type=float, default=2.0)
    parser.add_argument(
        "--idle-heartbeat-seconds",
        type=float,
        default=60.0,
        help="Refresh the safe heartbeat while idle so a preserved resident session does not look stale.",
    )
    parser.add_argument("--headless", action="store_true")
    parser.add_argument(
        "--once",
        action="store_true",
        help="Process pending commands once, then exit. Requires --allow-session-close to avoid accidental session teardown.",
    )
    parser.add_argument(
        "--allow-session-close",
        action="store_true",
        help="Explicitly allow this controller invocation to close the resident browser session on stop/once/exit.",
    )
    parser.add_argument(
        "--enable-live-send-canary",
        action="store_true",
        help=(
            "Enable validation of one-order live-send canary commands. "
            "Default is false; this flag alone still does not send without "
            "a command-level approval/preflight match."
        ),
    )
    parser.add_argument(
        "--enable-open-chat-no-type-canary",
        action="store_true",
        help=(
            "Enable one-order open-chat/no-type canary commands. Default is false; "
            "this flag alone does not open chat, and even a matched command may only "
            "open the selected chat, type nothing, and send nothing."
        ),
    )
    return parser


def run(args: argparse.Namespace) -> dict[str, Any]:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        raise RuntimeError("Playwright is required for the resident controller") from exc

    run_dir = args.run_dir.resolve()
    commands_dir = run_dir / "command_queue"
    heartbeat_path = run_dir / "resident_controller_heartbeat.json"
    closeout_path = run_dir / "resident_controller_closeout.md"
    run_dir.mkdir(parents=True, exist_ok=True)
    commands_dir.mkdir(parents=True, exist_ok=True)
    profile_store_code = str(args.profile_store_code or "ACMEWEAR").strip().upper()
    persistent_profile_dir = args.persistent_profile_dir.resolve()
    persistent_profile_dir.mkdir(parents=True, exist_ok=True)
    target_url = _status_url(str(args.startup_status_filter or DEFAULT_STATUS_FILTER).strip())
    unsafe_events: list[dict[str, Any]] = []
    last_command: dict[str, Any] | None = None

    if args.once and not args.allow_session_close:
        heartbeat = _heartbeat_payload(
            gate=YELLOW_GATE,
            run_dir=run_dir,
            persistent_profile_dir=persistent_profile_dir,
            profile_store_code=profile_store_code,
            commands_dir=commands_dir,
            blockers=[SESSION_CLOSE_GUARD_BLOCKER, "once_mode_blocked_to_preserve_resident_session"],
            last_command={"action": "once", "gate": "SESSION_CLOSE_GUARDED"},
        )
        _write_heartbeat(heartbeat_path, heartbeat)
        closeout_path.write_text(_build_controller_closeout(heartbeat, heartbeat_path), encoding="utf-8")
        return {
            "gate": heartbeat["gate"],
            "heartbeat_path": str(heartbeat_path),
            "closeout_path": str(closeout_path),
            "commands_dir": str(commands_dir),
            "browser_closed_by_controller_exit": False,
            "blockers": heartbeat["blockers"],
        }

    with sync_playwright() as p:
        context = p.chromium.launch_persistent_context(
            str(persistent_profile_dir),
            channel="chrome",
            headless=bool(args.headless),
        )

        def route_guard(route) -> None:
            request = route.request
            event = build_request_event(
                method=request.method,
                url=request.url,
                resource_type=request.resource_type,
            )
            reason = unsafe_route_block_reason(str(event.get("path_template") or ""))
            if reason:
                event["blocked_by_probe"] = True
                event["reason"] = reason
                unsafe_events.append(event)
                route.abort()
                return
            route.continue_()

        context.route("**/*", route_guard)
        page = context.pages[0] if context.pages else context.new_page()
        page.goto(target_url, wait_until="domcontentloaded", timeout=30000)
        deadline = time.time() + max(float(args.manual_login_timeout_seconds), 0.0)
        ready = _orders_search_visible(page)
        while not ready and time.time() < deadline:
            heartbeat = _heartbeat_payload(
                gate=YELLOW_GATE,
                run_dir=run_dir,
                persistent_profile_dir=persistent_profile_dir,
                profile_store_code=profile_store_code,
                commands_dir=commands_dir,
                page=page,
                blockers=["orders_search_input_not_visible_yet_owner_login_may_be_required"],
                last_command=last_command,
            )
            _write_heartbeat(heartbeat_path, heartbeat)
            closeout_path.write_text(_build_controller_closeout(heartbeat, heartbeat_path), encoding="utf-8")
            page.wait_for_timeout(int(max(args.poll_seconds, 0.5) * 1000))
            ready = _orders_search_visible(page)

        gate = GREEN_GATE if ready else YELLOW_GATE
        blockers = [] if ready else ["orders_search_input_not_visible_after_timeout"]
        heartbeat = _heartbeat_payload(
            gate=gate,
            run_dir=run_dir,
            persistent_profile_dir=persistent_profile_dir,
            profile_store_code=profile_store_code,
            commands_dir=commands_dir,
            page=page,
            blockers=blockers,
            last_command=last_command,
        )
        _write_heartbeat(heartbeat_path, heartbeat)
        closeout_path.write_text(_build_controller_closeout(heartbeat, heartbeat_path), encoding="utf-8")

        last_idle_heartbeat_at = time.time()
        while True:
            processed_command = False
            for command_path in _pending_command_files(commands_dir):
                processed_command = True
                raw_command = _read_json(command_path)
                command = normalize_command(raw_command, run_dir=run_dir, profile_store_code=profile_store_code)
                if command["action"] == COMMAND_ACTION_STOP:
                    if not args.allow_session_close:
                        result = {
                            "gate": YELLOW_GATE,
                            "blockers": [
                                SESSION_CLOSE_GUARD_BLOCKER,
                                "stop_command_ignored_to_preserve_resident_session",
                            ],
                            "browser_closed_by_controller_exit": False,
                        }
                        last_command = {
                            "command_id": command["command_id"],
                            "action": COMMAND_ACTION_STOP,
                            "gate": result["gate"],
                        }
                        _mark_command(command_path, command, result)
                        heartbeat = _heartbeat_payload(
                            gate=YELLOW_GATE,
                            run_dir=run_dir,
                            persistent_profile_dir=persistent_profile_dir,
                            profile_store_code=profile_store_code,
                            commands_dir=commands_dir,
                            page=page,
                            blockers=result["blockers"],
                            last_command=last_command,
                        )
                        _write_heartbeat(heartbeat_path, heartbeat)
                        closeout_path.write_text(_build_controller_closeout(heartbeat, heartbeat_path), encoding="utf-8")
                        continue
                    last_command = {
                        "command_id": command["command_id"],
                        "action": COMMAND_ACTION_STOP,
                        "gate": "STOP_REQUESTED",
                    }
                    _mark_command(command_path, command, last_command)
                    heartbeat = _heartbeat_payload(
                        gate=YELLOW_GATE,
                        run_dir=run_dir,
                        persistent_profile_dir=persistent_profile_dir,
                        profile_store_code=profile_store_code,
                        commands_dir=commands_dir,
                        page=page,
                        blockers=["stop_command_received"],
                        last_command=last_command,
                    )
                    _write_heartbeat(heartbeat_path, heartbeat)
                    closeout_path.write_text(_build_controller_closeout(heartbeat, heartbeat_path), encoding="utf-8")
                    return {
                        "gate": heartbeat["gate"],
                        "heartbeat_path": str(heartbeat_path),
                        "closeout_path": str(closeout_path),
                        "commands_dir": str(commands_dir),
                        "browser_closed_by_controller_exit": True,
                    }
                if command["action"] not in {
                    COMMAND_ACTION_UI_SEARCH,
                    COMMAND_ACTION_UI_CHAT_BUTTON,
                    COMMAND_ACTION_METADATA_CAPTURE,
                    COMMAND_ACTION_UI_LIVE_SEND_CANARY,
                    COMMAND_ACTION_UI_OPEN_CHAT_NO_TYPE_CANARY,
                    COMMAND_ACTION_UI_OPEN_CHAT_SELECTOR_DOM_DIAGNOSTIC,
                    COMMAND_ACTION_LOGIN_SMS_OTP,
                }:
                    result = {
                        "gate": RED_GATE,
                        "blockers": [f"unsupported_command_action:{command['action']}"],
                    }
                elif command["action"] == COMMAND_ACTION_UI_LIVE_SEND_CANARY:
                    result = _build_live_send_preflight_result(
                        command=command,
                        enable_live_send_canary=bool(args.enable_live_send_canary),
                    )
                elif command["action"] == COMMAND_ACTION_UI_OPEN_CHAT_NO_TYPE_CANARY:
                    result = _run_open_chat_no_type_command(
                        command=command,
                        page=page,
                        persistent_profile_dir=persistent_profile_dir,
                        unsafe_events=unsafe_events,
                        db_path=args.db.resolve(),
                        enable_open_chat_no_type_canary=bool(args.enable_open_chat_no_type_canary),
                    )
                elif command["action"] == COMMAND_ACTION_UI_OPEN_CHAT_SELECTOR_DOM_DIAGNOSTIC:
                    result = _run_open_chat_selector_dom_diagnostic_command(
                        command=command,
                        page=page,
                        persistent_profile_dir=persistent_profile_dir,
                        unsafe_events=unsafe_events,
                        db_path=args.db.resolve(),
                    )
                elif command["action"] == COMMAND_ACTION_LOGIN_SMS_OTP:
                    result = _run_login_sms_otp_command(command=command, page=page)
                elif command["action"] == COMMAND_ACTION_METADATA_CAPTURE:
                    result = _run_metadata_capture_command(
                        command=command,
                        page=page,
                        persistent_profile_dir=persistent_profile_dir,
                        db_path=args.db.resolve(),
                    )
                else:
                    require_chat_button = command["action"] == COMMAND_ACTION_UI_CHAT_BUTTON
                    result = _run_ui_search_command(
                        command=command,
                        page=page,
                        persistent_profile_dir=persistent_profile_dir,
                        unsafe_events=unsafe_events,
                        db_path=args.db.resolve(),
                        expand_order_result=require_chat_button,
                        require_chat_button=require_chat_button,
                    )
                last_command = {
                    "command_id": command["command_id"],
                    "action": command["action"],
                    "gate": result.get("gate"),
                    "manifest_path": result.get("manifest_path", ""),
                }
                _mark_command(command_path, command, result)
                heartbeat = _heartbeat_payload(
                    gate=GREEN_GATE if _orders_search_visible(page) else YELLOW_GATE,
                    run_dir=run_dir,
                    persistent_profile_dir=persistent_profile_dir,
                    profile_store_code=profile_store_code,
                    commands_dir=commands_dir,
                    page=page,
                    blockers=[] if _orders_search_visible(page) else ["orders_search_input_not_visible"],
                    last_command=last_command,
                )
                open_chat_read_only_events_allowed = (
                    command["action"] == COMMAND_ACTION_UI_OPEN_CHAT_NO_TYPE_CANARY
                    and result.get("gate") == OPEN_CHAT_RESULT_GREEN_GATE
                    and not _open_chat_blocking_unsafe_route_observed(
                        _route_flags_from_events(unsafe_events)
                    )
                )
                if unsafe_events and not open_chat_read_only_events_allowed:
                    heartbeat["gate"] = RED_GATE
                    heartbeat["blockers"] = ["unsafe_route_observed_or_blocked"]
                _write_heartbeat(heartbeat_path, heartbeat)
                closeout_path.write_text(_build_controller_closeout(heartbeat, heartbeat_path), encoding="utf-8")
            if args.once:
                return {
                    "gate": heartbeat["gate"],
                    "heartbeat_path": str(heartbeat_path),
                    "closeout_path": str(closeout_path),
                    "commands_dir": str(commands_dir),
                    "browser_closed_by_controller_exit": True,
                }
            if not processed_command and time.time() - last_idle_heartbeat_at >= max(
                float(args.idle_heartbeat_seconds),
                5.0,
            ):
                heartbeat = _heartbeat_payload(
                    gate=GREEN_GATE if _orders_search_visible(page) else YELLOW_GATE,
                    run_dir=run_dir,
                    persistent_profile_dir=persistent_profile_dir,
                    profile_store_code=profile_store_code,
                    commands_dir=commands_dir,
                    page=page,
                    blockers=[] if _orders_search_visible(page) else ["orders_search_input_not_visible"],
                    last_command=last_command,
                )
                _write_heartbeat(heartbeat_path, heartbeat)
                closeout_path.write_text(_build_controller_closeout(heartbeat, heartbeat_path), encoding="utf-8")
                last_idle_heartbeat_at = time.time()
            page.wait_for_timeout(int(max(args.poll_seconds, 0.5) * 1000))


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    summary = run(args)
    print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))
    if str(summary.get("gate") or "").startswith("RED_"):
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
