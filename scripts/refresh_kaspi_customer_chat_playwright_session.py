#!/usr/bin/env python3
"""Refresh a Kaspi merchant Playwright storage state for customer-chat probes.

This helper opens a headed browser for owner/manual login only, waits until the
merchant orders search page is reachable, and saves a refreshed storage state.
It never searches an order, opens chat, types a message, or sends anything.
"""

from __future__ import annotations

import argparse
import json
import time
from datetime import datetime
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_STORE = "ACMEWEAR"
DEFAULT_STATUS_FILTER = "KASPI_DELIVERY_WAIT_FOR_COURIER"
GREEN_GATE = "GREEN_KASPI_CUSTOMER_CHAT_PLAYWRIGHT_SESSION_READY_NO_SEND"
YELLOW_GATE = "YELLOW_KASPI_CUSTOMER_CHAT_PLAYWRIGHT_SESSION_NOT_READY_NO_SEND"
LOGIN_URL = "https://idmc.shop.kaspi.kz/login"


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


def _target_url(status_filter: str) -> str:
    return f"https://kaspi.kz/mc/#/orders-new?status={status_filter}"


def _default_output_dir() -> Path:
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return PROJECT_ROOT / "exports" / "validation" / f"kaspi_customer_chat_session_refresh_{stamp}"


def _default_storage_state(store_code: str) -> Path:
    store = str(store_code or DEFAULT_STORE).strip().upper()
    return PROJECT_ROOT / "runtime" / "playwright" / f"kaspi_webui_archive_session_{store}.json"


def _default_persistent_profile_dir(store_code: str) -> Path:
    store = str(store_code or DEFAULT_STORE).strip().upper()
    return PROJECT_ROOT / "runtime" / "playwright" / f"kaspi_customer_chat_profile_{store}"


def _login_state_from_url(url: str) -> str:
    url_lower = str(url or "").lower()
    if "idmc.shop.kaspi.kz/login" in url_lower:
        return "login"
    if "merchant.kaspi.kz/new/account/entrance" in url_lower:
        return "login"
    return "unknown_or_logged_in"


def _orders_search_visible(page) -> bool:
    try:
        locator = page.locator("input[placeholder='Номер заказа']").first
        return locator.count() > 0 and locator.is_visible(timeout=1000)
    except Exception:
        return False


def _body_login_hint_visible(page) -> bool:
    try:
        body = str(page.locator("body").inner_text(timeout=1500) or "").lower()
    except Exception:
        return True
    return any(token in body for token in ["войти", "авторизация", "sms", "смс", "код"])


def _diagnostics(
    *,
    page,
    storage_state: Path,
    persistent_profile_dir: Path | None,
    store_code: str,
    status_filter: str,
) -> dict[str, Any]:
    current_url = ""
    title = ""
    try:
        current_url = str(page.url or "")
        title = str(page.title() or "")
    except Exception:
        pass
    return {
        "run_at": datetime.now().isoformat(timespec="seconds"),
        "store_code": store_code,
        "status_filter": status_filter,
        "safe_current_url": _safe_url(current_url),
        "page_title": title[:160],
        "login_state_from_url": _login_state_from_url(current_url),
        "orders_search_input_visible": _orders_search_visible(page),
        "body_login_hint_visible": _body_login_hint_visible(page),
        "storage_state_path": str(storage_state.resolve()),
        "storage_state_exists": storage_state.exists(),
        "persistent_profile_mode": persistent_profile_dir is not None,
        "persistent_profile_dir_path": str(persistent_profile_dir.resolve())
        if persistent_profile_dir
        else "",
        "persistent_profile_dir_exists": persistent_profile_dir.exists()
        if persistent_profile_dir
        else False,
        "raw_order_id_exported": False,
        "raw_customer_text_exported": False,
        "raw_phone_exported": False,
        "raw_session_material_exported": False,
        "customer_send_allowed": False,
        "kaspi_chat_write_allowed": False,
        "order_search_performed": False,
        "chat_opened": False,
        "message_text_typed": False,
        "message_sent": False,
    }


def _build_manifest(
    *,
    gate: str,
    store_code: str,
    status_filter: str,
    target_url: str,
    storage_state: Path,
    persistent_profile_dir: Path | None,
    diagnostics_path: Path,
    blockers: list[str],
    manual_login_timeout_seconds: float,
) -> dict[str, Any]:
    return {
        "gate": gate,
        "run_at": datetime.now().isoformat(timespec="seconds"),
        "store_code": store_code,
        "status_filter": status_filter,
        "safe_target_url": _safe_url(target_url),
        "storage_state_path": str(storage_state.resolve()),
        "persistent_profile_mode": persistent_profile_dir is not None,
        "persistent_profile_dir_path": str(persistent_profile_dir.resolve())
        if persistent_profile_dir
        else "",
        "diagnostics_path": str(diagnostics_path.resolve()),
        "manual_login_timeout_seconds": manual_login_timeout_seconds,
        "customer_send_allowed": False,
        "kaspi_chat_write_allowed": False,
        "order_search_allowed": False,
        "order_search_performed": False,
        "chat_opened": False,
        "message_text_typed": False,
        "message_sent": False,
        "raw_order_id_exported": False,
        "raw_customer_text_exported": False,
        "raw_phone_exported": False,
        "raw_session_material_exported": False,
        "blockers": blockers,
    }


def _build_closeout(manifest: dict[str, Any]) -> str:
    lines = [
        "# Kaspi Customer Chat Playwright Session Refresh",
        "",
        f"Gate: {manifest['gate']}",
        "",
        "## Scope",
        "",
        f"- Store: `{manifest['store_code']}`",
        f"- Status filter: `{manifest['status_filter']}`",
        f"- Storage state: `{manifest['storage_state_path']}`",
        f"- Persistent profile mode: {str(manifest.get('persistent_profile_mode')).lower()}",
        f"- Persistent profile dir: `{manifest.get('persistent_profile_dir_path') or 'n/a'}`",
        f"- Diagnostics: `{manifest['diagnostics_path']}`",
        "",
        "## Safety",
        "",
        "- Customer send allowed: false",
        "- Kaspi chat write allowed: false",
        "- Order search performed: false",
        "- Chat opened: false",
        "- Message text typed: false",
        "- Message sent: false",
        "- Raw order ID exported: false",
        "- Raw customer text exported: false",
        "- Raw phone exported: false",
        "- Raw cookies/localStorage/session material exported: false",
        "",
    ]
    blockers = manifest.get("blockers") or []
    if blockers:
        lines.extend(["## Blockers", ""])
        lines.extend(f"- {blocker}" for blocker in blockers)
        lines.append("")
    return "\n".join(lines)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--store", default=DEFAULT_STORE)
    parser.add_argument("--status-filter", default=DEFAULT_STATUS_FILTER)
    parser.add_argument("--storage-state", type=Path)
    parser.add_argument(
        "--persistent-profile-dir",
        type=Path,
        help=(
            "Use a dedicated persistent Playwright Chrome profile instead of a "
            "throwaway browser context. This is safer for long-lived Kaspi "
            "merchant sessions because the owner can log in once and reuse the "
            "local profile without exporting cookies into evidence."
        ),
    )
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--manual-login-timeout-seconds", type=float, default=900.0)
    parser.add_argument("--headless", action="store_true")
    parser.add_argument("--poll-seconds", type=float, default=2.0)
    return parser


def run(args: argparse.Namespace) -> dict[str, Any]:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        raise RuntimeError("Playwright is required for Kaspi session refresh") from exc

    store_code = str(args.store or DEFAULT_STORE).strip().upper()
    status_filter = str(args.status_filter or DEFAULT_STATUS_FILTER).strip()
    storage_state = (args.storage_state or _default_storage_state(store_code)).resolve()
    persistent_profile_dir = args.persistent_profile_dir.resolve() if args.persistent_profile_dir else None
    output_dir = (args.output_dir or _default_output_dir()).resolve()
    diagnostics_path = output_dir / "session_refresh_diagnostics_redacted.json"
    manifest_path = output_dir / "manifest.json"
    closeout_path = output_dir / "closeout.md"
    output_dir.mkdir(parents=True, exist_ok=True)

    target_url = _target_url(status_filter)
    blockers: list[str] = []
    ready = False
    diagnostics: dict[str, Any] = {
        "run_at": datetime.now().isoformat(timespec="seconds"),
        "store_code": store_code,
        "status_filter": status_filter,
        "safe_current_url": "",
        "page_title": "",
        "login_state_from_url": "not_started",
        "orders_search_input_visible": False,
        "body_login_hint_visible": False,
        "storage_state_path": str(storage_state.resolve()),
        "storage_state_exists": storage_state.exists(),
        "storage_state_saved": False,
        "persistent_profile_mode": persistent_profile_dir is not None,
        "persistent_profile_dir_path": str(persistent_profile_dir.resolve())
        if persistent_profile_dir
        else "",
        "persistent_profile_dir_exists": persistent_profile_dir.exists()
        if persistent_profile_dir
        else False,
        "raw_order_id_exported": False,
        "raw_customer_text_exported": False,
        "raw_phone_exported": False,
        "raw_session_material_exported": False,
        "customer_send_allowed": False,
        "kaspi_chat_write_allowed": False,
        "order_search_performed": False,
        "chat_opened": False,
        "message_text_typed": False,
        "message_sent": False,
    }

    with sync_playwright() as p:
        browser = None
        if persistent_profile_dir:
            persistent_profile_dir.mkdir(parents=True, exist_ok=True)
            context = p.chromium.launch_persistent_context(
                str(persistent_profile_dir),
                channel="chrome",
                headless=bool(args.headless),
            )
        else:
            browser = p.chromium.launch(channel="chrome", headless=bool(args.headless))
            context_kwargs: dict[str, Any] = {}
            if storage_state.exists() and storage_state.stat().st_size > 0:
                context_kwargs["storage_state"] = str(storage_state)
            context = browser.new_context(**context_kwargs)
        page = context.pages[0] if context.pages else context.new_page()
        try:
            try:
                page.goto(target_url, wait_until="domcontentloaded", timeout=30000)
                deadline = time.time() + max(float(args.manual_login_timeout_seconds), 1.0)
                while time.time() < deadline:
                    if _orders_search_visible(page):
                        ready = True
                        break
                    if _login_state_from_url(str(page.url or "")) == "login" and args.headless:
                        blockers.append("login_required_but_headless_mode")
                        break
                    if _login_state_from_url(str(page.url or "")) != "login":
                        try:
                            page.goto(target_url, wait_until="domcontentloaded", timeout=15000)
                        except Exception:
                            pass
                    page.wait_for_timeout(int(max(float(args.poll_seconds), 0.5) * 1000))
            except Exception as exc:
                blockers.append(f"browser_navigation_failed:{type(exc).__name__}")
            finally:
                diagnostics = _diagnostics(
                    page=page,
                    storage_state=storage_state,
                    persistent_profile_dir=persistent_profile_dir,
                    store_code=store_code,
                    status_filter=status_filter,
                )
            if ready:
                storage_state.parent.mkdir(parents=True, exist_ok=True)
                context.storage_state(path=str(storage_state))
                diagnostics["storage_state_exists_after_save"] = storage_state.exists()
                diagnostics["storage_state_saved"] = True
                diagnostics["persistent_profile_dir_exists_after_run"] = persistent_profile_dir.exists() if persistent_profile_dir else False
            else:
                if not blockers:
                    blockers.append("orders_search_page_not_ready_before_timeout")
                diagnostics["storage_state_saved"] = False
        finally:
            context.close()
            if browser:
                browser.close()

    gate = GREEN_GATE if ready and storage_state.exists() else YELLOW_GATE
    manifest = _build_manifest(
        gate=gate,
        store_code=store_code,
        status_filter=status_filter,
        target_url=target_url,
        storage_state=storage_state,
        persistent_profile_dir=persistent_profile_dir,
        diagnostics_path=diagnostics_path,
        blockers=blockers,
        manual_login_timeout_seconds=float(args.manual_login_timeout_seconds),
    )
    _write_json(diagnostics_path, diagnostics)
    _write_json(manifest_path, manifest)
    closeout_path.write_text(_build_closeout(manifest), encoding="utf-8")
    return {
        "gate": gate,
        "manifest_path": str(manifest_path),
        "diagnostics_path": str(diagnostics_path),
        "closeout_path": str(closeout_path),
        "storage_state_path": str(storage_state),
        "customer_send_allowed": False,
        "kaspi_chat_write_allowed": False,
    }


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    summary = run(args)
    print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if summary["gate"] == GREEN_GATE else 1


if __name__ == "__main__":
    raise SystemExit(main())
