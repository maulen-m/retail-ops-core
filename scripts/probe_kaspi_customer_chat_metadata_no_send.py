#!/usr/bin/env python3
"""Capture or validate sanitized Kaspi customer-chat network metadata.

This helper is the next gate after the static indirect-API research wave. It is
designed to discover route shape without creating a replayable artifact:

- browser mode is opt-in via ``--run-live-browser``;
- request and response bodies are never read;
- cookies, storage-state, auth headers, CSRF/XSRF values, and raw customer data
  are never persisted;
- any observed chat write/read-side-effect route is blocked and turns the gate RED.

The safest first use is validate-only mode against a fixture or future sanitized
capture artifact. A live run should happen only after the owner explicitly
approves the no-send metadata capture lane for one selected redacted order.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import parse_qsl, urlsplit

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.resolve_kaspi_customer_chat_canary_runtime_secret import (
    DEFAULT_DB,
    ResolverError,
    resolve as resolve_runtime_secret,
)


DEFAULT_PACKET_DIR = (
    PROJECT_ROOT
    / "exports"
    / "validation"
    / "kaspi_customer_chat_live_canary_packet_2026-06-16_20260616_125511_final"
)
DEFAULT_PERSISTENT_PROFILE_DIR = (
    PROJECT_ROOT / "runtime" / "playwright" / "kaspi_customer_chat_profile_ACMEWEAR"
)
GREEN_GATE = "GREEN_CUSTOMER_CHAT_METADATA_CAPTURE_NO_SEND_NO_SECRET_EXPORT"
YELLOW_GATE = "YELLOW_CUSTOMER_CHAT_METADATA_CAPTURE_INCOMPLETE_NO_SEND"
RED_GATE = "RED_CUSTOMER_CHAT_METADATA_CAPTURE_UNSAFE"
SESSION_CLOSE_GUARD_BLOCKER = "session_close_requires_explicit_allow_session_close"
CHAT_BUTTON_SELECTOR = "button.init-chat-button.chat-section[type='CLIENT_SELLER_BY_ORDER']"

SEND_ROUTE_RE = re.compile(r"/messages/sendMessage(?:$|[/?#])", re.IGNORECASE)
TYPING_ROUTE_RE = re.compile(r"/typing/sendText(?:$|[/?#])", re.IGNORECASE)
START_CHAT_RE = re.compile(r"/group/startChat(?:$|[/?#])", re.IGNORECASE)
CHANGE_STATUS_RE = re.compile(r"/messageStatus/changeStatus(?:$|[/?#])", re.IGNORECASE)
LOAD_MORE_RE = re.compile(r"/history/loadMoreMessages(?:$|[/?#])", re.IGNORECASE)
CHAT_SEARCH_RE = re.compile(r"/chat/search(?:$|[/?#])", re.IGNORECASE)
GROUP_LOAD_RE = re.compile(r"/group/loadGroups/chat(?:$|[/?#])", re.IGNORECASE)
GROUP_DIFF_RE = re.compile(r"/group/getDiffGroups/chat(?:$|[/?#])", re.IGNORECASE)
CHAT_WEBSOCKET_RE = re.compile(r"/ws/chats/ws(?:$|[/?#])", re.IGNORECASE)
RAW_LONG_NUMBER_RE = re.compile(r"(?<!\d)\d{8,12}(?!\d)")
SAFE_SHA256_REF_RE = re.compile(r"sha256:[0-9a-f]{8,64}", re.IGNORECASE)
PHONE_RE = re.compile(
    r"(?<!\d)(?:\+?7|8)\D{0,3}\d{3}\D{0,3}\d{3}\D{0,3}\d{2}\D{0,3}\d{2}(?!\d)"
)
SECRET_WORD_RE = re.compile(
    r"(cookie|authorization|bearer|token|csrf|xsrf|localStorage|storage_state|sessionStorage)",
    re.IGNORECASE,
)
ALLOWED_EVENT_KEYS = {
    "kind",
    "observed_at",
    "method",
    "host",
    "scheme",
    "path_template",
    "query_keys",
    "resource_type",
    "status",
    "status_class",
    "content_type_family",
    "blocked_by_probe",
    "reason",
}


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def sanitize_url(url: str) -> dict[str, Any]:
    """Return a URL shape with query values stripped."""
    parsed = urlsplit(str(url or ""))
    query_keys = sorted({key for key, _value in parse_qsl(parsed.query, keep_blank_values=True)})
    path_template = re.sub(r"(?<=/)\d{6,12}(?=/|$)", "[redacted]", parsed.path or "/")
    return {
        "scheme": parsed.scheme,
        "host": parsed.netloc,
        "path_template": path_template,
        "query_keys": query_keys,
    }


def content_type_family(content_type: str | None) -> str:
    value = str(content_type or "").lower()
    if not value:
        return ""
    if "json" in value:
        return "json"
    if "html" in value:
        return "html"
    if "javascript" in value or "ecmascript" in value:
        return "javascript"
    if "text/" in value:
        return "text"
    if "image/" in value:
        return "image"
    return "other"


def build_request_event(*, method: str, url: str, resource_type: str = "") -> dict[str, Any]:
    safe = sanitize_url(url)
    return {
        "kind": "request",
        "observed_at": datetime.now().isoformat(timespec="seconds"),
        "method": str(method or "").upper(),
        "resource_type": str(resource_type or ""),
        **safe,
    }


def build_response_event(
    *,
    method: str,
    url: str,
    status: int | None,
    resource_type: str = "",
    content_type: str | None = None,
) -> dict[str, Any]:
    safe = sanitize_url(url)
    status_value = int(status or 0)
    return {
        "kind": "response",
        "observed_at": datetime.now().isoformat(timespec="seconds"),
        "method": str(method or "").upper(),
        "resource_type": str(resource_type or ""),
        "status": status_value,
        "status_class": f"{status_value // 100}xx" if status_value else "",
        "content_type_family": content_type_family(content_type),
        **safe,
    }


def build_websocket_event(*, url: str, reason: str = "opened") -> dict[str, Any]:
    safe = sanitize_url(url)
    return {
        "kind": "websocket",
        "observed_at": datetime.now().isoformat(timespec="seconds"),
        "method": "WEBSOCKET",
        "resource_type": "websocket",
        "reason": reason,
        **safe,
    }


def _event_path(event: dict[str, Any]) -> str:
    return str(event.get("path_template") or "")


def _event_host(event: dict[str, Any]) -> str:
    return str(event.get("host") or "")


def route_families(event: dict[str, Any]) -> list[str]:
    """Classify sanitized route metadata into non-secret customer-chat families."""
    path = _event_path(event)
    host = _event_host(event)
    families: list[str] = []
    if host == "msg-web.kaspi.kz" and path.startswith("/paychat"):
        families.append("paychat_frontend")
    if host == "mc.shop.kaspi.kz" and path.startswith("/chats/api/mobile"):
        families.append("chat_api_mobile")
    if CHAT_WEBSOCKET_RE.search(path):
        families.append("chat_websocket")
    if GROUP_LOAD_RE.search(path):
        families.append("group_load")
    if GROUP_DIFF_RE.search(path):
        families.append("group_diff")
    if CHAT_SEARCH_RE.search(path):
        families.append("chat_search")
    if LOAD_MORE_RE.search(path):
        families.append("load_more_messages")
    if START_CHAT_RE.search(path):
        families.append("start_chat_write_risk")
    if SEND_ROUTE_RE.search(path):
        families.append("send_message_write_risk")
    if TYPING_ROUTE_RE.search(path):
        families.append("typing_send_text_write_risk")
    if CHANGE_STATUS_RE.search(path):
        families.append("message_status_read_side_effect_risk")
    return families


def unsafe_route_block_reason(path: str) -> str:
    """Return the no-send block reason for routes that can mutate chat state."""
    if SEND_ROUTE_RE.search(path):
        return "send_message_route_blocked_no_send"
    if TYPING_ROUTE_RE.search(path):
        return "typing_send_text_route_blocked_no_send"
    if START_CHAT_RE.search(path):
        return "start_chat_route_blocked_no_send"
    if CHANGE_STATUS_RE.search(path):
        return "message_status_change_route_blocked_read_side_effect_unknown"
    return ""


def _without_safe_route_labels(payload: Any) -> Any:
    """Remove route metadata before scanning for forbidden secret-surface words.

    Kaspi uses harmless path names such as ``/oauth2/authorization/1`` and
    ``/script-cookie``. Query keys such as ``tToken`` are also useful route
    metadata after values are stripped. These labels are not leaked header,
    cookie, token, or storage values.
    """
    if isinstance(payload, dict):
        return {
            key: _without_safe_route_labels(value)
            for key, value in payload.items()
            if key not in {"path_template", "query_keys"}
        }
    if isinstance(payload, list):
        return [_without_safe_route_labels(item) for item in payload]
    return payload


def _without_safe_redacted_identity_tokens(payload: Any) -> Any:
    """Mask local redacted identity hashes before raw-number scanning.

    Evidence files intentionally use ``sha256:<hex>`` handles instead of raw
    order IDs. Hex digests can contain long digit-only runs by chance; those are
    safe local references, not exported Kaspi IDs or phone numbers.
    """
    if isinstance(payload, dict):
        return {
            key: _without_safe_redacted_identity_tokens(value)
            for key, value in payload.items()
        }
    if isinstance(payload, list):
        return [_without_safe_redacted_identity_tokens(item) for item in payload]
    if isinstance(payload, str):
        return SAFE_SHA256_REF_RE.sub("sha256:[redacted-hash]", payload)
    return payload


def _scan_for_unsafe_text(payload: Any) -> list[str]:
    text = json.dumps(
        _without_safe_route_labels(_without_safe_redacted_identity_tokens(payload)),
        ensure_ascii=False,
        sort_keys=True,
    )
    blockers: list[str] = []
    if PHONE_RE.search(text):
        blockers.append("phone_like_value_detected")
    if RAW_LONG_NUMBER_RE.search(text):
        blockers.append("raw_long_number_detected")
    for forbidden in [
        "headers",
        "request_body",
        "response_body",
        "cookie",
        "authorization",
        "bearer",
        "localStorage",
        "storage_state",
        "sessionStorage",
    ]:
        if forbidden.lower() in text.lower():
            blockers.append(f"forbidden_secret_surface_word:{forbidden}")
    return sorted(set(blockers))


def validate_capture(capture: dict[str, Any]) -> dict[str, Any]:
    events = list(capture.get("events") or [])
    blockers: list[str] = []
    warnings: list[str] = []
    route_family_counts: dict[str, int] = {}

    required_false = [
        "customer_send_allowed",
        "kaspi_chat_write_allowed",
        "chat_opened",
        "message_text_typed",
        "message_sent",
        "raw_order_id_exported",
        "raw_customer_text_exported",
        "raw_phone_exported",
        "raw_session_material_exported",
    ]
    for key in required_false:
        if capture.get(key) is not False:
            blockers.append(f"{key}_must_be_false")

    if not events:
        warnings.append("no_metadata_events_captured")
    for blocker in capture.get("blockers") or []:
        warnings.append(f"capture_incomplete:{blocker}")

    for index, event in enumerate(events):
        extra_keys = sorted(set(event) - ALLOWED_EVENT_KEYS)
        if extra_keys:
            blockers.append(f"event_{index}_has_forbidden_keys:{','.join(extra_keys)}")
        path = _event_path(event)
        for family in route_families(event):
            route_family_counts[family] = route_family_counts.get(family, 0) + 1
        if SEND_ROUTE_RE.search(path):
            blockers.append("send_message_route_observed")
        if TYPING_ROUTE_RE.search(path):
            blockers.append("typing_send_text_route_observed")
        if START_CHAT_RE.search(path):
            blockers.append("start_chat_route_observed")
        if CHANGE_STATUS_RE.search(path):
            blockers.append("message_status_change_route_observed_read_side_effect_unknown")
        if LOAD_MORE_RE.search(path):
            warnings.append("load_more_messages_route_observed_open_chat_risk")
        event_secret_scan_text = json.dumps(
            _without_safe_route_labels(event),
            ensure_ascii=False,
            sort_keys=True,
        )
        if SECRET_WORD_RE.search(event_secret_scan_text):
            blockers.append(f"event_{index}_contains_secret_surface_word")

    blockers.extend(_scan_for_unsafe_text(capture))
    blockers = sorted(set(blockers))
    warnings = sorted(set(warnings))

    if blockers:
        gate = RED_GATE
        accepted = False
    elif warnings:
        gate = YELLOW_GATE
        accepted = False
    else:
        gate = GREEN_GATE
        accepted = True

    return {
        "gate": gate,
        "accepted": accepted,
        "validated_at": datetime.now().isoformat(timespec="seconds"),
        "event_count": len(events),
        "blockers": blockers,
        "warnings": warnings,
        "route_family_counts": dict(sorted(route_family_counts.items())),
        "chat_route_families_observed": sorted(route_family_counts),
        "customer_send_allowed": False,
        "kaspi_chat_write_allowed": False,
        "raw_order_id_exported": False,
        "raw_customer_text_exported": False,
        "raw_session_material_exported": False,
    }


def build_closeout(capture: dict[str, Any], validation: dict[str, Any], capture_path: Path) -> str:
    lines = [
        "# Kaspi Customer Chat Metadata Capture No-Send",
        "",
        f"Gate: {validation['gate']}",
        "",
        "## Scope",
        "",
        f"- Capture path: `{capture_path}`",
        f"- Store: `{capture.get('store_code') or ''}`",
        f"- Selected order ref: `{capture.get('selected_order_ref') or ''}`",
        f"- Event count: {validation.get('event_count')}",
        "- Customer send allowed: false",
        "- Kaspi chat write allowed: false",
        "- Message text typed: false",
        "- Message sent: false",
        "- Raw order/customer/session export: false",
        "",
        "## Validation",
        "",
        f"- Accepted: {str(validation.get('accepted')).lower()}",
        f"- Blockers: {', '.join(validation.get('blockers') or []) or 'none'}",
        f"- Warnings: {', '.join(validation.get('warnings') or []) or 'none'}",
        f"- Chat route families observed: {', '.join(validation.get('chat_route_families_observed') or []) or 'none'}",
        "",
        "## Safety",
        "",
        "- Request/response bodies are not captured.",
        "- Header values, cookies, auth material, CSRF/XSRF values, localStorage, storage-state, raw order IDs, phones, customer names, addresses, and customer messages are not persisted.",
        "- Any future live use must remain no-send unless a separate one-order owner approval exists.",
        "",
    ]
    return "\n".join(lines)


def _default_capture_path(packet_dir: Path) -> Path:
    return packet_dir / "customer_chat_metadata_capture_redacted.json"


def _default_validation_path(packet_dir: Path) -> Path:
    return packet_dir / "customer_chat_metadata_capture_validation.json"


def _default_closeout_path(packet_dir: Path) -> Path:
    return packet_dir / "customer_chat_metadata_capture_closeout.md"


def _make_initial_capture(manifest: dict[str, Any], *, source: str) -> dict[str, Any]:
    return {
        "gate": "CAPTURE_PENDING",
        "captured_at": datetime.now().isoformat(timespec="seconds"),
        "source": source,
        "selected_order_ref": manifest.get("selected_order_ref"),
        "db_row_id": manifest.get("selected_db_row_id"),
        "store_code": manifest.get("selected_store_code"),
        "status_filter": manifest.get("selected_status_filter"),
        "events": [],
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


def run_live_browser_capture(args: argparse.Namespace) -> dict[str, Any]:
    try:
        from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        raise RuntimeError("Playwright is required for live browser capture") from exc

    packet_dir = args.packet_dir.resolve()
    manifest_path = packet_dir / "manifest.json"
    manifest = _read_json(manifest_path)
    capture = _make_initial_capture(manifest, source="playwright_metadata_no_send")
    events: list[dict[str, Any]] = capture["events"]
    blocked_send_route = False
    blocked_unsafe_route = False
    runtime_audit_path = packet_dir / "metadata_capture_runtime_secret_audit_redacted.json"

    resolver_args = argparse.Namespace(
        db=args.db,
        packet_manifest=manifest_path,
        db_row_id=None,
        target_date=None,
        lookback_days=None,
        audit_json=None,
        print_raw_order_id=False,
    )
    try:
        raw_order_id, runtime_audit = resolve_runtime_secret(resolver_args)
        _write_json(runtime_audit_path, runtime_audit)
    except ResolverError as exc:
        capture["gate"] = "YELLOW_METADATA_CAPTURE_RUNTIME_SECRET_BLOCKED"
        capture["blockers"] = [f"runtime_secret_resolver_blocked:{exc.gate}"]
        return capture

    status_filter = str(manifest.get("selected_status_filter") or "KASPI_DELIVERY_WAIT_FOR_COURIER")
    target_url = f"https://kaspi.kz/mc/#/orders-new?status={status_filter}"
    profile_dir = (args.persistent_profile_dir or DEFAULT_PERSISTENT_PROFILE_DIR).resolve()

    with sync_playwright() as p:
        profile_dir.mkdir(parents=True, exist_ok=True)
        context = p.chromium.launch_persistent_context(
            str(profile_dir),
            channel="chrome",
            headless=not args.headful,
        )

        def route_guard(route, request) -> None:  # type: ignore[no-untyped-def]
            nonlocal blocked_send_route, blocked_unsafe_route
            safe = build_request_event(
                method=request.method,
                url=request.url,
                resource_type=request.resource_type,
            )
            events.append(safe)
            block_reason = unsafe_route_block_reason(str(safe.get("path_template") or ""))
            if block_reason:
                blocked_unsafe_route = True
                if block_reason == "send_message_route_blocked_no_send":
                    blocked_send_route = True
                events.append(
                    {
                        **safe,
                        "kind": "request",
                        "blocked_by_probe": True,
                        "reason": block_reason,
                    }
                )
                route.abort()
                return
            route.continue_()

        context.route("**/*", route_guard)
        page = context.pages[0] if context.pages else context.new_page()

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

        page.on("response", on_response)
        page.on("websocket", on_websocket)
        try:
            page.goto(target_url, wait_until="domcontentloaded", timeout=args.timeout_ms)
            page.wait_for_timeout(3000)
            search_input = page.locator("input[placeholder='Номер заказа']").first
            search_input.wait_for(state="visible", timeout=args.timeout_ms)
            search_input.fill(raw_order_id)
            page.locator("button", has_text="Поиск").first.click(timeout=args.timeout_ms)
            page.wait_for_timeout(5000)
            capture["order_search_performed"] = True
            capture["chat_button_seen"] = page.locator(CHAT_BUTTON_SELECTOR).count() > 0
        except PlaywrightTimeoutError as exc:
            capture["gate"] = YELLOW_GATE
            capture["blockers"] = [
                "orders_search_input_not_visible_or_login_gate_before_timeout",
            ]
            capture["playwright_error_type"] = type(exc).__name__
        except Exception as exc:
            capture["gate"] = YELLOW_GATE
            capture["blockers"] = [f"browser_capture_incomplete:{type(exc).__name__}"]
        finally:
            capture["chat_opened"] = False
            capture["message_text_typed"] = False
            capture["message_sent"] = False
            capture["blocked_send_route"] = blocked_send_route
            capture["blocked_unsafe_route"] = blocked_unsafe_route
            context.close()

    if blocked_unsafe_route:
        capture["gate"] = RED_GATE
    elif capture.get("gate") == "CAPTURE_PENDING":
        capture["gate"] = GREEN_GATE
    return capture


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--packet-dir", type=Path, default=DEFAULT_PACKET_DIR)
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument("--capture-json", type=Path)
    parser.add_argument("--validation-json", type=Path)
    parser.add_argument("--closeout-md", type=Path)
    parser.add_argument("--validate-only", action="store_true")
    parser.add_argument("--run-live-browser", action="store_true")
    parser.add_argument("--persistent-profile-dir", type=Path)
    parser.add_argument("--headful", action="store_true")
    parser.add_argument(
        "--allow-session-close",
        action="store_true",
        help=(
            "Explicitly allow live-browser capture to close the Playwright persistent "
            "context it launches. Omit to preserve authenticated Kaspi sessions."
        ),
    )
    parser.add_argument("--timeout-ms", type=int, default=30000)
    parser.add_argument("--require-green", action="store_true")
    return parser


def run(args: argparse.Namespace) -> dict[str, Any]:
    packet_dir = args.packet_dir.resolve()
    capture_path = (args.capture_json or _default_capture_path(packet_dir)).resolve()
    validation_path = (args.validation_json or _default_validation_path(packet_dir)).resolve()
    closeout_path = (args.closeout_md or _default_closeout_path(packet_dir)).resolve()

    if args.run_live_browser and args.validate_only:
        raise ValueError("--run-live-browser and --validate-only are mutually exclusive")
    if args.run_live_browser and not args.allow_session_close:
        manifest_path = packet_dir / "manifest.json"
        manifest = _read_json(manifest_path) if manifest_path.exists() else {}
        capture = _make_initial_capture(
            manifest,
            source="playwright_metadata_no_send_blocked_session_preservation_guard",
        )
        capture["gate"] = YELLOW_GATE
        capture["blockers"] = [
            SESSION_CLOSE_GUARD_BLOCKER,
            "live_browser_capture_blocked_to_preserve_authenticated_session",
        ]
        _write_json(capture_path, capture)
        validation = validate_capture(capture)
        validation["gate"] = YELLOW_GATE
        validation["accepted"] = False
        validation["warnings"] = sorted(
            set(
                list(validation.get("warnings") or [])
                + ["live_browser_capture_blocked_to_preserve_authenticated_session"]
            )
        )
        _write_json(validation_path, validation)
        closeout_path.parent.mkdir(parents=True, exist_ok=True)
        closeout_path.write_text(build_closeout(capture, validation, capture_path), encoding="utf-8")
        return {
            "gate": validation["gate"],
            "accepted": validation["accepted"],
            "capture_path": str(capture_path),
            "validation_path": str(validation_path),
            "closeout_path": str(closeout_path),
            "customer_send_allowed": False,
            "kaspi_chat_write_allowed": False,
            "raw_order_id_exported": False,
            "raw_customer_text_exported": False,
            "raw_session_material_exported": False,
        }
    if args.run_live_browser:
        capture = run_live_browser_capture(args)
        _write_json(capture_path, capture)
    else:
        if not capture_path.exists():
            raise FileNotFoundError(
                f"capture JSON not found: {capture_path}; use --run-live-browser or provide --capture-json"
            )
        capture = _read_json(capture_path)

    validation = validate_capture(capture)
    _write_json(validation_path, validation)
    closeout_path.parent.mkdir(parents=True, exist_ok=True)
    closeout_path.write_text(build_closeout(capture, validation, capture_path), encoding="utf-8")
    return {
        "gate": validation["gate"],
        "accepted": validation["accepted"],
        "capture_path": str(capture_path),
        "validation_path": str(validation_path),
        "closeout_path": str(closeout_path),
        "customer_send_allowed": False,
        "kaspi_chat_write_allowed": False,
        "raw_order_id_exported": False,
        "raw_customer_text_exported": False,
        "raw_session_material_exported": False,
    }


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    summary = run(args)
    print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))
    if args.require_green and summary.get("gate") != GREEN_GATE:
        return 1
    if str(summary.get("gate") or "").startswith("RED_"):
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
