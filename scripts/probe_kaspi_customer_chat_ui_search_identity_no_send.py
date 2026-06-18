#!/usr/bin/env python3
"""Probe Kaspi merchant order-search identity without opening customer chat.

This is a redacted no-send diagnostic for the current Kaspi customer-size
workflow. It uses runtime-only order IDs from the local DB to search the logged
in merchant UI, then persists only booleans and redacted order refs.

Safety boundary:
- never click/open customer chat;
- never type or send a customer message;
- never export raw order IDs, customer text, phone numbers, cookies, headers,
  storage state, localStorage, or session material;
- abort if a chat write/read-side-effect route is observed.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any, Iterable

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.ops.customer_size_request import (  # noqa: E402
    OrderCandidate,
    load_missing_size_candidates,
    suggest_merchant_status_filter,
)
from scripts.probe_kaspi_customer_chat_metadata_no_send import (  # noqa: E402
    build_request_event,
    unsafe_route_block_reason,
)


DEFAULT_DB = PROJECT_ROOT / "db" / "app.db"
DEFAULT_PERSISTENT_PROFILE_DIR = (
    PROJECT_ROOT / "runtime" / "playwright" / "kaspi_customer_chat_profile_ACMEWEAR"
)
DEFAULT_OUTPUT_DIR = (
    PROJECT_ROOT
    / "exports"
    / "validation"
    / f"kaspi_customer_chat_ui_search_identity_no_send_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
)

GREEN_GATE = "GREEN_KASPI_CUSTOMER_CHAT_UI_SEARCH_IDENTITY_FOUND_NO_SEND"
GREEN_CHAT_BUTTON_GATE = "GREEN_KASPI_CUSTOMER_CHAT_MESSAGE_BUTTON_PROVEN_NO_SEND"
YELLOW_GATE = "YELLOW_KASPI_CUSTOMER_CHAT_UI_SEARCH_IDENTITY_NOT_FOUND_NO_SEND"
YELLOW_CHAT_BUTTON_GATE = "YELLOW_KASPI_CUSTOMER_CHAT_MESSAGE_BUTTON_NOT_PROVEN_NO_SEND"
YELLOW_SESSION_PRESERVATION_GATE = (
    "YELLOW_KASPI_CUSTOMER_CHAT_UI_PROBE_BLOCKED_TO_PRESERVE_SESSION_NO_SEND"
)
RED_GATE = "RED_KASPI_CUSTOMER_CHAT_UI_SEARCH_IDENTITY_UNSAFE"
CHAT_BUTTON_SELECTOR = "button.init-chat-button.chat-section[type='CLIENT_SELLER_BY_ORDER']"
SESSION_CLOSE_GUARD_BLOCKER = "session_close_requires_explicit_allow_session_close"
STORE_MERCHANT_ACCOUNT_IDS = {
    "UNIVERSAL": "30000001",
    "ACMEWEAR": "30137883",
    "STOREB": "30000002",
    "MELVIS": "30362323",
    "11KZ": "30290083",
}
MERCHANT_ACCOUNT_ID_RE = re.compile(r"\bID\s*-\s*(\d{6,12})\b")


@dataclass(frozen=True)
class PlannedProbe:
    candidate: OrderCandidate
    status_filter: str
    target_url: str


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _safe_url(url: str) -> str:
    if not url:
        return ""
    head = url.split("?", 1)[0]
    if "#/" in url:
        head = url.split("#/", 1)[0] + "#/" + url.split("#/", 1)[1].split("?", 1)[0]
    head = re.sub(r"(/orders/)\d{6,}", r"\1[redacted]", head)
    return head + ("?[redacted]" if "?" in url else "")


def _status_url(status_filter: str) -> str:
    return f"https://kaspi.kz/mc/#/orders-new?status={status_filter}"


def _today_from_arg(value: str | None) -> date:
    if value:
        return date.fromisoformat(value)
    return date.today()


def _split_csv(values: str | None) -> list[str]:
    if not values:
        return []
    return [value.strip() for value in values.split(",") if value.strip()]


def merchant_account_id_for_store(store_code: str | None) -> str:
    return STORE_MERCHANT_ACCOUNT_IDS.get(str(store_code or "").strip().upper(), "")


def _visible_merchant_account_ids(page) -> list[str]:
    try:
        body_text = page.locator("body").inner_text(timeout=1500)
    except Exception:
        body_text = ""
    seen: list[str] = []
    for merchant_id in MERCHANT_ACCOUNT_ID_RE.findall(body_text):
        if merchant_id not in seen:
            seen.append(merchant_id)
    return seen


def _click_merchant_selector(page) -> bool:
    selectors = [
        "text=/ID\\s*-\\s*\\d{6,12}/",
        "[role='button']",
        "button",
    ]
    for selector in selectors:
        try:
            locator = page.locator(selector).first
            if locator.count() <= 0:
                continue
            locator.click(timeout=3000)
            page.wait_for_timeout(500)
            return True
        except Exception:
            continue
    return False


def ensure_merchant_account_selected(page, store_code: str | None) -> dict[str, Any]:
    """Best-effort read-only merchant-account selector alignment."""
    expected_id = merchant_account_id_for_store(store_code)
    result: dict[str, Any] = {
        "expected_merchant_account_id": expected_id,
        "observed_merchant_account_ids_before": [],
        "observed_merchant_account_ids_after": [],
        "merchant_account_selector_attempted": False,
        "merchant_account_selector_matched": False,
        "merchant_account_selection_succeeded": False,
        "merchant_account_selection_notes": [],
    }
    if not expected_id:
        result["merchant_account_selection_notes"].append("no_expected_merchant_account_id_for_store")
        return result

    before = _visible_merchant_account_ids(page)
    result["observed_merchant_account_ids_before"] = before
    if before and before[0] == expected_id:
        result["observed_merchant_account_ids_after"] = before
        result["merchant_account_selector_matched"] = True
        result["merchant_account_selection_succeeded"] = True
        result["merchant_account_selection_notes"].append("merchant_account_already_selected")
        return result

    result["merchant_account_selector_attempted"] = True
    if not _click_merchant_selector(page):
        result["merchant_account_selection_notes"].append("merchant_account_selector_not_clickable")
        return result

    try:
        option = page.get_by_text(f"ID - {expected_id}", exact=True).first
        if option.count() > 0:
            option.click(timeout=5000)
            page.wait_for_timeout(1500)
        else:
            result["merchant_account_selection_notes"].append("expected_merchant_account_option_not_found")
    except Exception as exc:
        result["merchant_account_selection_notes"].append(
            f"merchant_account_selection_exception:{type(exc).__name__}"
        )

    after = _visible_merchant_account_ids(page)
    result["observed_merchant_account_ids_after"] = after
    result["merchant_account_selector_matched"] = bool(after and after[0] == expected_id)
    result["merchant_account_selection_succeeded"] = result["merchant_account_selector_matched"]
    if result["merchant_account_selector_matched"]:
        result["merchant_account_selection_notes"].append("merchant_account_selected")
    elif expected_id in after:
        result["merchant_account_selection_notes"].append("expected_merchant_account_visible_but_not_first")
    else:
        result["merchant_account_selection_notes"].append("expected_merchant_account_not_visible_after_attempt")
    return result


def plan_probes(
    candidates: Iterable[OrderCandidate],
    *,
    profile_store_code: str,
    max_candidates: int,
    extra_status_filters: Iterable[str] = (),
) -> list[PlannedProbe]:
    """Create runtime-only probe work without serializing raw order IDs."""
    plans: list[PlannedProbe] = []
    for candidate in candidates:
        filters = [suggest_merchant_status_filter(candidate)]
        for status_filter in extra_status_filters:
            if status_filter and status_filter not in filters:
                filters.append(status_filter)
        for status_filter in filters:
            if status_filter == "UNKNOWN":
                continue
            plans.append(
                PlannedProbe(
                    candidate=candidate,
                    status_filter=status_filter,
                    target_url=_status_url(status_filter),
                )
            )
            if len(plans) >= max_candidates:
                return plans
    return plans


def _candidate_base(plan: PlannedProbe, *, profile_store_code: str) -> dict[str, Any]:
    candidate = plan.candidate
    return {
        "db_row_id": candidate.db_row_id,
        "order_ref": candidate.order_ref,
        "store_code": candidate.store_code,
        "profile_store_code": profile_store_code,
        "sku_key": candidate.sku_key,
        "sku_id": candidate.sku_id,
        "product_type": candidate.product_type,
        "internal_status": candidate.internal_status,
        "kaspi_status": candidate.kaspi_status,
        "status_filter": plan.status_filter,
        "safe_target_url": _safe_url(plan.target_url),
        "requires_matching_merchant_account": True,
        "expected_merchant_account_id": merchant_account_id_for_store(candidate.store_code),
        "observed_merchant_account_ids_before": [],
        "observed_merchant_account_ids_after": [],
        "merchant_account_selector_attempted": False,
        "merchant_account_selector_matched": False,
        "merchant_account_selection_succeeded": False,
        "merchant_account_match_proven": str(candidate.store_code or "").upper()
        == str(profile_store_code or "").upper(),
        "search_performed": False,
        "search_input_value_length": 0,
        "order_ref_visible": False,
        "result_or_detail_reached": False,
        "chat_button_present": False,
        "chat_button_selector_counts": {},
        "messages_by_order_text_present": False,
        "write_customer_text_present": False,
        "customer_message_text_present": False,
        "buttons_count": 0,
        "order_result_expand_attempted": False,
        "order_result_expand_succeeded": False,
        "chat_opened": False,
        "message_text_typed": False,
        "message_sent": False,
        "raw_order_id_exported": False,
        "raw_customer_text_exported": False,
        "raw_phone_exported": False,
        "raw_session_material_exported": False,
        "notes": [],
    }


def _search_input(page):
    return page.locator("input[placeholder='Номер заказа']").first


def _orders_search_visible(page) -> bool:
    try:
        locator = _search_input(page)
        return locator.count() > 0 and locator.is_visible(timeout=1000)
    except Exception:
        return False


def _wait_for_orders_search(page, target_url: str, timeout_ms: int) -> bool:
    deadline = time.time() + max(float(timeout_ms) / 1000.0, 1.0)
    while time.time() < deadline:
        if _orders_search_visible(page):
            return True
        current_url = str(page.url or "")
        if "idmc.shop.kaspi.kz/login" not in current_url.lower():
            try:
                page.goto(target_url, wait_until="domcontentloaded", timeout=10000)
            except Exception:
                pass
        page.wait_for_timeout(750)
    return _orders_search_visible(page)


def _click_search(page) -> bool:
    try:
        button = page.locator("button", has_text="Поиск").first
        if button.count() > 0:
            button.click(timeout=5000)
            return True
    except Exception:
        pass
    try:
        page.keyboard.press("Enter")
        return True
    except Exception:
        return False


def _page_search_flags(page, raw_order_id: str) -> dict[str, Any]:
    return page.evaluate(
        """(args) => {
            const rawOrderId = args.rawOrderId;
            const chatButtonSelector = args.chatButtonSelector;
            const bodyText = document.body ? document.body.innerText : "";
            const searchInput = document.querySelector("input[placeholder='Номер заказа']");
            const chatButtons = document.querySelectorAll(chatButtonSelector);
            const count = (selector) => document.querySelectorAll(selector).length;
            return {
              ready_state: document.readyState,
              title_length: (document.title || "").length,
              safe_current_url: window.location.href.split("?")[0] + (window.location.href.includes("?") ? "?[redacted]" : ""),
              search_input_visible: !!searchInput,
              search_input_value_length: searchInput && searchInput.value ? searchInput.value.length : 0,
              order_ref_visible: rawOrderId ? bodyText.includes(rawOrderId) : false,
              chat_button_present: chatButtons.length > 0,
              chat_button_selector_counts: {
                required_chat_button: chatButtons.length,
                init_chat_button: count("button.init-chat-button"),
                chat_section_button: count("button.chat-section"),
                client_seller_by_order: count("[type='CLIENT_SELLER_BY_ORDER']"),
                any_chat_class_button: count("button[class*='chat']")
              },
              messages_by_order_text_present: bodyText.includes("Сообщения по заказу"),
              write_customer_text_present: bodyText.includes("Написать покупателю"),
              customer_message_text_present: bodyText.includes("Сообщение покупателю"),
              buttons_count: document.querySelectorAll("button").length,
              login_text_present: bodyText.includes("Войти") || bodyText.includes("Авторизация"),
              sms_text_present: bodyText.includes("SMS") || bodyText.includes("СМС") || bodyText.includes("код")
            };
        }""",
        {"rawOrderId": raw_order_id, "chatButtonSelector": CHAT_BUTTON_SELECTOR},
    )


def _attempt_click_order_result(page, raw_order_id: str) -> bool:
    """Expand or open the visible order row, but never click the chat button."""
    candidates = [
        page.locator("a", has_text=raw_order_id).first,
        page.locator("tr", has_text=raw_order_id).first,
        page.locator("text=" + raw_order_id).first,
    ]
    for locator in candidates:
        try:
            if locator.count() <= 0:
                continue
            locator.click(timeout=5000)
            page.wait_for_timeout(2500)
            return True
        except Exception:
            continue
    return False


def _apply_search_flags(row: dict[str, Any], flags: dict[str, Any]) -> None:
    selector_counts = flags.get("chat_button_selector_counts") or {}
    row["search_input_value_length"] = int(flags.get("search_input_value_length") or 0)
    row["order_ref_visible"] = bool(flags.get("order_ref_visible"))
    row["messages_by_order_text_present"] = bool(flags.get("messages_by_order_text_present"))
    row["write_customer_text_present"] = bool(flags.get("write_customer_text_present"))
    row["customer_message_text_present"] = bool(flags.get("customer_message_text_present"))
    row["chat_button_selector_counts"] = {
        str(key): int(value or 0) for key, value in selector_counts.items()
    }
    row["chat_button_present"] = bool(
        flags.get("chat_button_present")
        or row["messages_by_order_text_present"]
        or row["write_customer_text_present"]
        or row["customer_message_text_present"]
        or row["chat_button_selector_counts"].get("client_seller_by_order")
    )
    row["buttons_count"] = int(flags.get("buttons_count") or 0)
    row["result_or_detail_reached"] = bool(row["order_ref_visible"])
    row["diagnostic_flags"] = {
        "search_input_visible": bool(flags.get("search_input_visible")),
        "login_text_present": bool(flags.get("login_text_present")),
        "sms_text_present": bool(flags.get("sms_text_present")),
        "title_length": int(flags.get("title_length") or 0),
    }


def _probe_one(
    page,
    plan: PlannedProbe,
    *,
    profile_store_code: str,
    timeout_ms: int,
    expand_order_result: bool = False,
) -> dict[str, Any]:
    row = _candidate_base(plan, profile_store_code=profile_store_code)
    try:
        page.goto(plan.target_url, wait_until="domcontentloaded", timeout=timeout_ms)
        if not _wait_for_orders_search(page, plan.target_url, timeout_ms):
            flags = _page_search_flags(page, "")
            row["notes"].append("orders_search_input_not_ready")
            if flags.get("login_text_present") or flags.get("sms_text_present"):
                row["notes"].append("login_or_sms_gate_visible")
            row["diagnostic_flags"] = {
                "search_input_visible": bool(flags.get("search_input_visible")),
                "login_text_present": bool(flags.get("login_text_present")),
                "sms_text_present": bool(flags.get("sms_text_present")),
            }
            return row

        search_input = _search_input(page)
        selector_result = ensure_merchant_account_selected(page, plan.candidate.store_code)
        for key, value in selector_result.items():
            row[key] = value
        row["merchant_account_match_proven"] = bool(selector_result.get("merchant_account_selector_matched"))
        if not row["merchant_account_match_proven"]:
            row["notes"].append("merchant_account_selector_not_matched")

        if selector_result.get("merchant_account_selector_attempted"):
            try:
                page.goto(plan.target_url, wait_until="domcontentloaded", timeout=timeout_ms)
                _wait_for_orders_search(page, plan.target_url, timeout_ms)
            except Exception:
                row["notes"].append("post_merchant_selection_navigation_failed")

        search_input = _search_input(page)
        search_input.click(timeout=5000)
        search_input.fill("", timeout=5000)
        search_input.type(plan.candidate.raw_order_id, delay=20, timeout=10000)
        row["search_performed"] = _click_search(page)
        page.wait_for_timeout(5000)
        flags = _page_search_flags(page, plan.candidate.raw_order_id)
        _apply_search_flags(row, flags)
        if row["result_or_detail_reached"] and expand_order_result and not row["chat_button_present"]:
            row["order_result_expand_attempted"] = True
            row["order_result_expand_succeeded"] = _attempt_click_order_result(
                page,
                plan.candidate.raw_order_id,
            )
            if row["order_result_expand_succeeded"]:
                flags = _page_search_flags(page, plan.candidate.raw_order_id)
                _apply_search_flags(row, flags)
                row["result_or_detail_reached"] = True
        if not row["result_or_detail_reached"]:
            row["notes"].append("search_completed_no_visible_order_result")
        if expand_order_result and not row["chat_button_present"]:
            row["notes"].append("chat_button_not_proven_no_open")
    except Exception as exc:
        row["notes"].append(f"probe_exception:{type(exc).__name__}")
    return row


def validate_redacted_payload(payload: dict[str, Any], raw_order_ids: Iterable[str]) -> list[str]:
    """Return blockers if persisted output leaks forbidden material."""
    text = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    blockers: list[str] = []
    for raw_order_id in raw_order_ids:
        value = str(raw_order_id or "").strip()
        if value and value in text:
            blockers.append("raw_order_id_value_detected")
            break
    forbidden_keys = [
        "raw_order_id",
        "customer_text",
        "phone",
        "cookie",
        "authorization",
        "bearer",
        "localStorage",
        "sessionStorage",
        "storage_state",
        "headers",
        "request_body",
        "response_body",
    ]
    lowered = text.lower()
    for forbidden in forbidden_keys:
        if forbidden.lower() in lowered and forbidden not in {
            "raw_order_id",
            "customer_text",
            "phone",
        }:
            blockers.append(f"forbidden_surface_label_detected:{forbidden}")
    if '"raw_order_id_exported": false' not in lowered:
        blockers.append("raw_order_id_export_flag_missing_or_true")
    if '"message_sent": false' not in lowered:
        blockers.append("message_sent_flag_missing_or_true")
    if '"chat_opened": false' not in lowered:
        blockers.append("chat_opened_flag_missing_or_true")
    if payload.get("customer_send_allowed") is not False:
        blockers.append("customer_send_allowed_not_false")
    if payload.get("kaspi_chat_write_allowed") is not False:
        blockers.append("kaspi_chat_write_allowed_not_false")
    return sorted(set(blockers))


def build_payload(
    *,
    output_dir: Path,
    target_date: date,
    lookback_days: int,
    profile_store_code: str,
    persistent_profile_dir: Path,
    plans: list[PlannedProbe],
    results: list[dict[str, Any]],
    unsafe_events: list[dict[str, Any]],
    raw_order_ids: Iterable[str],
    require_chat_button: bool = False,
) -> dict[str, Any]:
    blockers: list[str] = []
    if unsafe_events:
        blockers.append("unsafe_chat_route_observed_or_blocked")
    qualified_found_results = [
        row
        for row in results
        if row.get("result_or_detail_reached") and row.get("merchant_account_match_proven")
    ]
    unqualified_found_results = [
        row
        for row in results
        if row.get("result_or_detail_reached") and not row.get("merchant_account_match_proven")
    ]
    chat_button_results = [
        row
        for row in qualified_found_results
        if row.get("chat_button_present") and row.get("merchant_account_match_proven")
    ]
    unqualified_chat_button_results = [
        row for row in results if row.get("result_or_detail_reached") and row.get("chat_button_present")
    ]
    if require_chat_button:
        gate = GREEN_CHAT_BUTTON_GATE if chat_button_results and not blockers else YELLOW_CHAT_BUTTON_GATE
    else:
        gate = GREEN_GATE if qualified_found_results and not blockers else YELLOW_GATE
    payload = {
        "gate": gate,
        "recorded_at": datetime.now().isoformat(timespec="seconds"),
        "target_date": target_date.isoformat(),
        "lookback_days": lookback_days,
        "profile_store_code": profile_store_code,
        "persistent_profile_mode": True,
        "persistent_profile_dir_path": str(persistent_profile_dir),
        "candidates_planned": len(plans),
        "candidates_scanned": len(results),
        "found_result_count": len(qualified_found_results),
        "unqualified_found_result_count": len(unqualified_found_results),
        "chat_button_found_count": len(chat_button_results),
        "unqualified_chat_button_found_count": len(unqualified_chat_button_results),
        "require_chat_button": bool(require_chat_button),
        "unsafe_event_count": len(unsafe_events),
        "unsafe_events_redacted": unsafe_events[:10],
        "results": results,
        "blockers": blockers,
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
        "output_dir": str(output_dir),
    }
    redaction_blockers = validate_redacted_payload(payload, raw_order_ids)
    if redaction_blockers:
        payload["gate"] = RED_GATE
        payload["blockers"] = sorted(set(payload["blockers"] + redaction_blockers))
    elif blockers:
        payload["gate"] = RED_GATE
    return payload


def _build_closeout(payload: dict[str, Any], manifest_path: Path, results_path: Path) -> str:
    lines = [
        "# Kaspi Customer Chat UI Search Identity No-Send Diagnostic",
        "",
        f"Gate: {payload['gate']}",
        "",
        "## Scope",
        "",
        "- Purpose: prove whether current missing-size order identities surface in the merchant UI search before any chat action.",
        f"- Profile store: {payload.get('profile_store_code')}",
        f"- Target date: {payload.get('target_date')}",
        f"- Lookback days: {payload.get('lookback_days')}",
        f"- Candidates planned: {payload.get('candidates_planned')}",
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
    if payload["gate"] == YELLOW_SESSION_PRESERVATION_GATE:
        lines.extend(
            [
                "## Interpretation",
                "",
                "Direct persistent-profile probing was intentionally blocked so the authenticated Kaspi browser session stays open. Use the resident no-send controller command queue for normal diagnostics, or pass `--allow-session-close` only when the owner explicitly accepts closing this Playwright-launched context.",
                "",
            ]
        )
    elif payload["gate"] == YELLOW_GATE:
        lines.extend(
            [
                "## Interpretation",
                "",
                "The browser session can be used for no-send diagnostics, but none of the scanned current candidates became a visible order result. The next move is to compare UI search mechanics/status buckets or use a human-visible Computer Use proof before any chat/open/send path.",
                "",
            ]
        )
    elif payload["gate"] == GREEN_GATE:
        lines.extend(
            [
                "## Interpretation",
                "",
                "At least one current missing-size candidate surfaced in merchant UI search without opening chat. The next gate can focus on proving the message button selector for that visible order, still no-send.",
                "",
            ]
        )
    return "\n".join(lines)


def build_session_preservation_guard_payload(
    *,
    output_dir: Path,
    target_date: date,
    lookback_days: int,
    profile_store_code: str,
    persistent_profile_dir: Path,
    require_chat_button: bool = False,
) -> dict[str, Any]:
    return {
        "gate": YELLOW_SESSION_PRESERVATION_GATE,
        "recorded_at": datetime.now().isoformat(timespec="seconds"),
        "target_date": target_date.isoformat(),
        "lookback_days": lookback_days,
        "profile_store_code": profile_store_code,
        "persistent_profile_mode": True,
        "persistent_profile_dir_path": str(persistent_profile_dir),
        "browser_context_launched": False,
        "browser_closed_by_probe": False,
        "session_close_requires_explicit_allow_session_close": True,
        "candidates_planned": 0,
        "candidates_scanned": 0,
        "found_result_count": 0,
        "unqualified_found_result_count": 0,
        "chat_button_found_count": 0,
        "unqualified_chat_button_found_count": 0,
        "require_chat_button": bool(require_chat_button),
        "unsafe_event_count": 0,
        "unsafe_events_redacted": [],
        "results": [],
        "blockers": [
            SESSION_CLOSE_GUARD_BLOCKER,
            "direct_probe_blocked_to_preserve_authenticated_kaspi_session",
            "use_resident_no_send_controller_command_queue_instead",
        ],
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
        "output_dir": str(output_dir),
    }


def run(args: argparse.Namespace) -> dict[str, Any]:
    output_dir = args.output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    target_date = _today_from_arg(args.target_date)
    persistent_profile_dir = args.persistent_profile_dir.resolve()
    if not args.allow_session_close:
        payload = build_session_preservation_guard_payload(
            output_dir=output_dir,
            target_date=target_date,
            lookback_days=args.lookback_days,
            profile_store_code=args.profile_store_code,
            persistent_profile_dir=persistent_profile_dir,
            require_chat_button=bool(getattr(args, "require_chat_button", False)),
        )
        manifest_path = output_dir / "manifest.json"
        results_path = output_dir / "ui_search_identity_results_redacted.json"
        closeout_path = output_dir / "closeout.md"
        _write_json(manifest_path, payload)
        _write_json(results_path, {"results": []})
        closeout_path.write_text(_build_closeout(payload, manifest_path, results_path), encoding="utf-8")
        return {
            "gate": payload["gate"],
            "manifest_path": str(manifest_path),
            "results_path": str(results_path),
            "closeout_path": str(closeout_path),
            "found_result_count": 0,
            "candidates_scanned": 0,
            "customer_send_allowed": False,
            "kaspi_chat_write_allowed": False,
            "raw_order_id_exported": False,
            "browser_context_launched": False,
            "browser_closed_by_probe": False,
            "blockers": payload["blockers"],
        }

    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        raise RuntimeError("Playwright is required for UI search identity diagnostics") from exc

    stores = _split_csv(args.stores) or [args.profile_store_code]
    extra_status_filters = _split_csv(args.extra_status_filters)
    candidates = load_missing_size_candidates(
        args.db,
        target_date=target_date,
        lookback_days=args.lookback_days,
        stores=stores,
        limit=args.candidate_pool_limit,
    )
    plans = plan_probes(
        candidates,
        profile_store_code=args.profile_store_code,
        max_candidates=args.max_candidates,
        extra_status_filters=extra_status_filters,
    )
    raw_order_ids = [plan.candidate.raw_order_id for plan in plans]
    unsafe_events: list[dict[str, Any]] = []
    results: list[dict[str, Any]] = []

    with sync_playwright() as p:
        persistent_profile_dir.mkdir(parents=True, exist_ok=True)
        context = p.chromium.launch_persistent_context(
            str(persistent_profile_dir),
            channel="chrome",
            headless=not args.headful,
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
        for existing_page in list(context.pages):
            try:
                existing_page.close()
            except Exception:
                pass
        page = context.new_page()
        try:
            for plan in plans:
                results.append(
                    _probe_one(
                        page,
                        plan,
                        profile_store_code=args.profile_store_code,
                        timeout_ms=args.timeout_ms,
                    )
                )
                if unsafe_events:
                    break
        finally:
            context.close()

    payload = build_payload(
        output_dir=output_dir,
        target_date=target_date,
        lookback_days=args.lookback_days,
        profile_store_code=args.profile_store_code,
        persistent_profile_dir=persistent_profile_dir,
        plans=plans,
        results=results,
        unsafe_events=unsafe_events,
        raw_order_ids=raw_order_ids,
    )
    manifest_path = output_dir / "manifest.json"
    results_path = output_dir / "ui_search_identity_results_redacted.json"
    closeout_path = output_dir / "closeout.md"
    _write_json(manifest_path, payload)
    _write_json(results_path, {"results": payload["results"]})
    closeout_path.write_text(_build_closeout(payload, manifest_path, results_path), encoding="utf-8")
    return {
        "gate": payload["gate"],
        "manifest_path": str(manifest_path),
        "results_path": str(results_path),
        "closeout_path": str(closeout_path),
        "found_result_count": payload["found_result_count"],
        "candidates_scanned": payload["candidates_scanned"],
        "customer_send_allowed": False,
        "kaspi_chat_write_allowed": False,
        "raw_order_id_exported": False,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--target-date")
    parser.add_argument("--lookback-days", type=int, default=5)
    parser.add_argument("--stores", default="ACMEWEAR")
    parser.add_argument("--profile-store-code", default="ACMEWEAR")
    parser.add_argument("--candidate-pool-limit", type=int, default=50)
    parser.add_argument("--max-candidates", type=int, default=6)
    parser.add_argument("--extra-status-filters", default="")
    parser.add_argument("--persistent-profile-dir", type=Path, default=DEFAULT_PERSISTENT_PROFILE_DIR)
    parser.add_argument("--timeout-ms", type=int, default=30000)
    parser.add_argument("--headful", action="store_true")
    parser.add_argument(
        "--allow-session-close",
        action="store_true",
        help=(
            "Explicitly allow this direct probe to close the Playwright persistent "
            "context it launches. Omit to preserve the authenticated Kaspi session; "
            "normal diagnostics should use the resident no-send controller instead."
        ),
    )
    parser.add_argument("--require-green", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    summary = run(args)
    print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))
    if args.require_green and summary["gate"] != GREEN_GATE:
        return 1
    if summary["gate"] == RED_GATE:
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
