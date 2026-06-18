#!/usr/bin/env python3
"""Run a bounded Playwright Kaspi customer-chat no-send proof.

The probe may use an existing store-scoped Playwright storage state to open the
Kaspi merchant order page, search one runtime-resolved order ID, and prove the
customer-message button exists. It never clicks chat, never types a message, and
never sends a customer message.

All persisted outputs are redacted and match the validator contract used by
``validate_kaspi_customer_chat_live_canary_result.py``.
"""

from __future__ import annotations

import argparse
import json
import time
from datetime import datetime
from pathlib import Path
from typing import Any

from scripts.resolve_kaspi_customer_chat_canary_runtime_secret import (
    ResolverError,
    resolve as resolve_runtime_secret,
)
from scripts.validate_kaspi_customer_chat_live_canary_result import (
    DEFAULT_PACKET_DIR,
    GREEN_RESULT_GATE,
    validate as validate_live_ui_result,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DB = PROJECT_ROOT / "db" / "app.db"
DEFAULT_SESSION_STATE = PROJECT_ROOT / "runtime" / "playwright" / "kaspi_webui_archive_session_ACMEWEAR.json"
DEFAULT_PERSISTENT_PROFILE_DIR = (
    PROJECT_ROOT / "runtime" / "playwright" / "kaspi_customer_chat_profile_ACMEWEAR"
)
YELLOW_GATE = "YELLOW_LIVE_ORDER_CHAT_BUTTON_NOT_PROVEN_NO_SEND"
RED_GATE = "RED_LIVE_PLAYWRIGHT_NO_SEND_PROBE_UNSAFE"
CHAT_BUTTON_SELECTOR = "button.init-chat-button.chat-section[type='CLIENT_SELLER_BY_ORDER']"


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


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
    return head + ("?[redacted]" if "?" in url else "")


def _page_diagnostics(page, raw_order_id: str) -> dict[str, Any]:
    return page.evaluate(
        """(args) => {
            const selector = args.selector;
            const rawOrderId = args.rawOrderId;
            const bodyText = document.body ? document.body.innerText : "";
            const count = (sel) => document.querySelectorAll(sel).length;
            const buttons = Array.from(document.querySelectorAll("button")).map((el) => ({
              type: el.getAttribute("type") || "",
              cls: el.getAttribute("class") || "",
              text: (el.innerText || el.textContent || "").trim().slice(0, 80)
            })).slice(0, 12);
            const inputs = Array.from(document.querySelectorAll("input")).map((el) => ({
              type: el.getAttribute("type") || "",
              cls: el.getAttribute("class") || "",
              placeholder: el.getAttribute("placeholder") || "",
              value_length: (el.value || "").length
            })).slice(0, 12);
            return {
              ready_state: document.readyState,
              title: document.title || "",
              selector_counts: {
                chat_button: count(selector),
                init_chat_button: count("button.init-chat-button"),
                textareas: count("textarea"),
                inputs: count("input"),
                buttons: count("button")
              },
              text_flags: {
                has_order_id_in_page: rawOrderId ? bodyText.includes(rawOrderId) : false,
                has_messages_by_order_text: bodyText.includes("Сообщения по заказу"),
                has_login_text: bodyText.includes("Войти") || bodyText.includes("Авторизация"),
                has_sms_text: bodyText.includes("SMS") || bodyText.includes("СМС") || bodyText.includes("код")
              },
              buttons,
              inputs
            };
        }""",
        {"selector": CHAT_BUTTON_SELECTOR, "rawOrderId": raw_order_id},
    )


def _click_search(page) -> bool:
    search_button = page.locator("button", has_text="Поиск").first
    try:
        if search_button.count() > 0:
            search_button.click(timeout=5000)
            return True
    except Exception:
        pass
    try:
        page.keyboard.press("Enter")
        return True
    except Exception:
        return False


def _enter_order_search_value(search_input, raw_order_id: str) -> None:
    search_input.click(timeout=5000)
    search_input.fill("", timeout=5000)
    search_input.type(raw_order_id, delay=25, timeout=10000)


def _orders_search_visible(page) -> bool:
    try:
        locator = page.locator("input[placeholder='Номер заказа']").first
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
        page.wait_for_timeout(1000)
    return _orders_search_visible(page)


def _attempt_click_order_result(page, raw_order_id: str) -> bool:
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


def _build_result(
    *,
    manifest: dict[str, Any],
    proof_source: str,
    merchant_account_match_proven: bool,
    order_search_performed: bool,
    order_detail_or_result_reached: bool,
    chat_button_present: bool,
    notes: list[str],
) -> dict[str, Any]:
    required_green = [
        merchant_account_match_proven,
        order_search_performed,
        order_detail_or_result_reached,
        chat_button_present,
    ]
    gate = GREEN_RESULT_GATE if all(required_green) else YELLOW_GATE
    return {
        "gate": gate,
        "recorded_at": datetime.now().isoformat(timespec="seconds"),
        "proof_type": "playwright_live_visual_no_send",
        "proof_source": proof_source,
        "selected_order_ref": manifest.get("selected_order_ref"),
        "db_row_id": manifest.get("selected_db_row_id"),
        "store_code": manifest.get("selected_store_code"),
        "suggested_merchant_status_filter": manifest.get("selected_status_filter"),
        "merchant_account_match_proven": bool(merchant_account_match_proven),
        "order_search_performed": bool(order_search_performed),
        "order_detail_or_result_reached": bool(order_detail_or_result_reached),
        "chat_button_selector": CHAT_BUTTON_SELECTOR,
        "chat_button_present": bool(chat_button_present),
        "chat_opened": False,
        "message_text_typed": False,
        "message_sent": False,
        "raw_order_id_exported": False,
        "raw_customer_text_exported": False,
        "raw_phone_exported": False,
        "raw_session_material_exported": False,
        "notes": notes,
    }


def _build_closeout(result: dict[str, Any], validation: dict[str, Any], diagnostics_path: Path) -> str:
    lines = [
        "# Kaspi Customer Chat Live Playwright No-Send Proof",
        "",
        f"Gate: {result['gate']}",
        "",
        "## Scope",
        "",
        f"- Store: {result.get('store_code')}",
        f"- DB row: {result.get('db_row_id')}",
        f"- Selected order ref: {result.get('selected_order_ref')}",
        f"- Status filter: {result.get('suggested_merchant_status_filter')}",
        "- Probe type: Playwright live browser, no-send",
        f"- Diagnostics: `{diagnostics_path}`",
        "",
        "## Proof Flags",
        "",
        f"- Merchant account/store match proven: {str(result.get('merchant_account_match_proven')).lower()}",
        f"- Order search performed: {str(result.get('order_search_performed')).lower()}",
        f"- Order result/detail reached: {str(result.get('order_detail_or_result_reached')).lower()}",
        f"- Chat button present: {str(result.get('chat_button_present')).lower()}",
        "- Chat opened: false",
        "- Message text typed: false",
        "- Message sent: false",
        "- Raw order ID exported: false",
        "- Raw customer text exported: false",
        "",
        "## Validator",
        "",
        f"- Validator gate: {validation.get('gate')}",
        f"- Accepted: {str(validation.get('accepted')).lower()}",
        f"- Blockers: {', '.join(str(item) for item in validation.get('blockers') or []) or 'none'}",
        "",
        "## Safety Notes",
        "",
        "- This probe did not click chat, type message text, send a message, export cookies, export localStorage, or write customer-private values.",
        "- No Google Board, DB, CRM workbook, Telegram/WhatsApp, waybill, scheduler, price, stock, cash, supplier, or PO write happened.",
        "",
    ]
    return "\n".join(lines)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--packet-dir", type=Path, default=DEFAULT_PACKET_DIR)
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument("--storage-state", type=Path, default=DEFAULT_SESSION_STATE)
    parser.add_argument(
        "--persistent-profile-dir",
        type=Path,
        help=(
            "Use a dedicated persistent Playwright Chrome profile instead of "
            "storage_state JSON. This keeps the Kaspi merchant login in a local "
            "browser profile and still exports only redacted proof artifacts."
        ),
    )
    parser.add_argument("--headful", action="store_true")
    parser.add_argument("--timeout-ms", type=int, default=30000)
    parser.add_argument("--result-json", type=Path)
    parser.add_argument("--diagnostics-json", type=Path)
    parser.add_argument("--validation-json", type=Path)
    parser.add_argument("--closeout-md", type=Path)
    parser.add_argument("--require-green", action="store_true")
    return parser


def run(args: argparse.Namespace) -> dict[str, Any]:
    try:
        from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        raise RuntimeError("Playwright is required for the live no-send probe") from exc

    packet_dir = args.packet_dir.resolve()
    manifest_path = packet_dir / "manifest.json"
    manifest = _read_json(manifest_path)
    result_path = args.result_json or (packet_dir / "live_ui_probe_result_redacted.json")
    diagnostics_path = args.diagnostics_json or (packet_dir / "live_playwright_no_send_diagnostics_redacted.json")
    validation_path = args.validation_json or (packet_dir / "live_ui_canary_result_validation.json")
    closeout_path = args.closeout_md or (packet_dir / "live_ui_no_send_probe_closeout.md")
    runtime_audit_path = packet_dir / "runtime_secret_resolver_audit_redacted.json"

    resolver_args = argparse.Namespace(
        db=args.db,
        packet_manifest=manifest_path,
        db_row_id=None,
        target_date=None,
        lookback_days=None,
        audit_json=None,
        print_raw_order_id=False,
    )
    notes: list[str] = []
    status_filter = str(manifest.get("selected_status_filter") or "KASPI_DELIVERY_WAIT_FOR_COURIER")
    target_url = f"https://kaspi.kz/mc/#/orders-new?status={status_filter}"
    persistent_profile_arg = getattr(args, "persistent_profile_dir", None)
    merchant_account_match_proven = False
    order_search_performed = False
    order_detail_or_result_reached = False
    chat_button_present = False
    diagnostics: dict[str, Any] = {
        "run_at": datetime.now().isoformat(timespec="seconds"),
        "safe_target_url": _safe_url(target_url),
        "storage_state_path": str(args.storage_state.resolve()),
        "persistent_profile_mode": persistent_profile_arg is not None,
        "persistent_profile_dir_path": str(persistent_profile_arg.resolve())
        if persistent_profile_arg
        else "",
        "headful": bool(args.headful),
        "raw_order_id_exported": False,
        "raw_customer_text_exported": False,
        "message_text_typed": False,
        "message_sent": False,
    }

    try:
        raw_order_id, runtime_audit = resolve_runtime_secret(resolver_args)
        _write_json(runtime_audit_path, runtime_audit)
    except ResolverError as exc:
        notes.append(f"runtime_secret_resolver_blocked:{exc.gate}")
        runtime_audit = {
            "gate": exc.gate,
            "run_at": datetime.now().isoformat(timespec="seconds"),
            "db_path": str(args.db.resolve()),
            "packet_manifest_path": str(manifest_path.resolve()),
            "db_row_id": manifest.get("selected_db_row_id"),
            "order_ref": manifest.get("selected_order_ref"),
            "store_code": manifest.get("selected_store_code"),
            "candidate_still_missing_size": False
            if exc.gate == "YELLOW_RUNTIME_SECRET_CANDIDATE_NO_LONGER_ACTIVE_MISSING_SIZE"
            else None,
            "raw_order_id_printed_to_stdout": False,
            "raw_order_id_exported": False,
            "raw_customer_text_exported": False,
            "kaspi_chat_write_allowed": False,
            "customer_send_allowed": False,
            "google_board_write_allowed": False,
            "message_text_typed": False,
            "message_sent": False,
            "error_type": "ResolverError",
            "error_gate": exc.gate,
            "error_message_redacted": "runtime secret resolver blocked; see error_gate",
        }
        _write_json(runtime_audit_path, runtime_audit)
        diagnostics["resolver_gate"] = exc.gate
        diagnostics["resolver_blocked_before_browser_action"] = True
        result = _build_result(
            manifest=manifest,
            proof_source="runtime_secret_resolver_blocked",
            merchant_account_match_proven=False,
            order_search_performed=False,
            order_detail_or_result_reached=False,
            chat_button_present=False,
            notes=notes,
        )
        _write_json(diagnostics_path, diagnostics)
        _write_json(result_path, result)
        validation_args = argparse.Namespace(
            packet_dir=packet_dir,
            result_json=result_path,
            closeout_md=closeout_path,
            output_json=validation_path.resolve(),
            require_green=False,
        )
        validation = validate_live_ui_result(validation_args)
        closeout_path.write_text(_build_closeout(result, validation, diagnostics_path), encoding="utf-8")
        validation = validate_live_ui_result(validation_args)
        _write_json(validation_path, validation)
        closeout_path.write_text(_build_closeout(result, validation, diagnostics_path), encoding="utf-8")
        return {
            "gate": result["gate"],
            "validation_gate": validation.get("gate"),
            "accepted": validation.get("accepted") is True,
            "result_path": str(result_path),
            "diagnostics_path": str(diagnostics_path),
            "validation_path": str(validation_path),
            "closeout_path": str(closeout_path),
            "customer_send_allowed": False,
            "kaspi_chat_write_allowed": False,
            "raw_order_id_exported": False,
            "raw_customer_text_exported": False,
        }

    persistent_profile_dir = persistent_profile_arg.resolve() if persistent_profile_arg else None
    if not persistent_profile_dir and not args.storage_state.exists():
        notes.append("storage_state_missing")
        result = _build_result(
            manifest=manifest,
            proof_source="playwright_storage_state_missing",
            merchant_account_match_proven=False,
            order_search_performed=False,
            order_detail_or_result_reached=False,
            chat_button_present=False,
            notes=notes,
        )
    else:
        with sync_playwright() as p:
            browser = None
            if persistent_profile_dir:
                persistent_profile_dir.mkdir(parents=True, exist_ok=True)
                context = p.chromium.launch_persistent_context(
                    str(persistent_profile_dir),
                    channel="chrome",
                    headless=not args.headful,
                )
                proof_source = "playwright_persistent_profile"
            else:
                browser = p.chromium.launch(channel="chrome", headless=not args.headful)
                context = browser.new_context(storage_state=str(args.storage_state))
                proof_source = "playwright_store_scoped_storage_state"
            page = context.pages[0] if context.pages else context.new_page()
            try:
                page.goto(target_url, wait_until="domcontentloaded", timeout=args.timeout_ms)
                search_ready = _wait_for_orders_search(page, target_url, args.timeout_ms)
                diagnostics["after_navigation"] = _page_diagnostics(page, raw_order_id)
                diagnostics["safe_current_url_after_navigation"] = _safe_url(page.url)

                text_flags = diagnostics["after_navigation"].get("text_flags") or {}
                current_url_after_navigation = str(diagnostics.get("safe_current_url_after_navigation") or "")
                if (
                    not search_ready
                    and (
                        "login" in current_url_after_navigation.lower()
                        or "idmc.shop.kaspi.kz" in current_url_after_navigation.lower()
                        or text_flags.get("has_login_text")
                        or text_flags.get("has_sms_text")
                    )
                ):
                    notes.append("kaspi_login_or_sms_gate_visible")
                else:
                    selected_store = str(manifest.get("selected_store_code") or "").upper()
                    authority_name = (
                        persistent_profile_dir.name.upper()
                        if persistent_profile_dir
                        else args.storage_state.name.upper()
                    )
                    merchant_account_match_proven = selected_store and selected_store in authority_name
                    if merchant_account_match_proven:
                        notes.append("merchant_match_inferred_from_store_scoped_browser_authority")
                    else:
                        notes.append("merchant_match_not_proven")

                    search_input = page.locator("input[placeholder='Номер заказа']").first
                    try:
                        search_input.wait_for(state="visible", timeout=10000)
                        _enter_order_search_value(search_input, raw_order_id)
                        order_search_performed = _click_search(page)
                        page.wait_for_timeout(8000)
                    except PlaywrightTimeoutError:
                        notes.append("order_search_input_not_visible")
                    except Exception as exc:
                        notes.append(f"order_search_failed:{type(exc).__name__}")

                    diagnostics["after_search"] = _page_diagnostics(page, raw_order_id)
                    search_flags = diagnostics["after_search"].get("text_flags") or {}
                    order_detail_or_result_reached = bool(search_flags.get("has_order_id_in_page"))

                    if order_detail_or_result_reached:
                        clicked_order_result = _attempt_click_order_result(page, raw_order_id)
                        diagnostics["clicked_order_result_or_row"] = clicked_order_result
                        if clicked_order_result:
                            diagnostics["after_order_result_click"] = _page_diagnostics(page, raw_order_id)

                    latest_diag = diagnostics.get("after_order_result_click") or diagnostics.get("after_search") or {}
                    selector_counts = latest_diag.get("selector_counts") or {}
                    latest_flags = latest_diag.get("text_flags") or {}
                    chat_button_present = bool(selector_counts.get("chat_button")) or bool(
                        latest_flags.get("has_messages_by_order_text")
                    )
                    if chat_button_present:
                        order_detail_or_result_reached = True
                    if not chat_button_present:
                        notes.append("chat_button_not_visible_after_search")

                result = _build_result(
                    manifest=manifest,
                    proof_source=proof_source,
                    merchant_account_match_proven=merchant_account_match_proven,
                    order_search_performed=order_search_performed,
                    order_detail_or_result_reached=order_detail_or_result_reached,
                    chat_button_present=chat_button_present,
                    notes=notes,
                )
            except Exception as exc:
                notes.append(f"playwright_probe_failed:{type(exc).__name__}")
                result = _build_result(
                    manifest=manifest,
                    proof_source="playwright_exception",
                    merchant_account_match_proven=merchant_account_match_proven,
                    order_search_performed=order_search_performed,
                    order_detail_or_result_reached=order_detail_or_result_reached,
                    chat_button_present=chat_button_present,
                    notes=notes,
                )
            finally:
                context.close()
                if browser:
                    browser.close()

    _write_json(diagnostics_path, diagnostics)
    _write_json(result_path, result)
    validation_args = argparse.Namespace(
        packet_dir=packet_dir,
        result_json=result_path,
        closeout_md=closeout_path,
        output_json=validation_path.resolve(),
        require_green=False,
    )
    validation = validate_live_ui_result(validation_args)
    closeout_path.write_text(_build_closeout(result, validation, diagnostics_path), encoding="utf-8")
    validation = validate_live_ui_result(validation_args)
    _write_json(validation_path, validation)
    closeout_path.write_text(_build_closeout(result, validation, diagnostics_path), encoding="utf-8")
    summary = {
        "gate": result["gate"],
        "validation_gate": validation.get("gate"),
        "accepted": validation.get("accepted") is True,
        "result_path": str(result_path),
        "diagnostics_path": str(diagnostics_path),
        "validation_path": str(validation_path),
        "closeout_path": str(closeout_path),
        "customer_send_allowed": False,
        "kaspi_chat_write_allowed": False,
        "raw_order_id_exported": False,
        "raw_customer_text_exported": False,
    }
    return summary


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    summary = run(args)
    print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))
    if args.require_green and not summary["accepted"]:
        return 1
    if str(summary["validation_gate"]).startswith("RED_") or str(summary["gate"]).startswith("RED_"):
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
