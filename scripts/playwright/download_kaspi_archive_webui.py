#!/usr/bin/env python3
"""Manage WebUI archive download runs with immutable manifests."""

from __future__ import annotations

import argparse
from datetime import date, datetime
import json
import os
from pathlib import Path
import shutil
import sys
import time
from typing import Any

from dotenv import dotenv_values

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.export_kaspi_archive_ui_history import WINDOW_DAYS, plan_windows
from scripts.webui_archive_truth_utils import (
    DEFAULT_STORES_CONFIG,
    compute_sha256,
    find_webui_source_files,
    infer_store_code_from_path,
    infer_window_from_path,
    load_enabled_stores,
)

DEFAULT_OUTPUT_ROOT = PROJECT_ROOT / "exports" / "webui_archive_download_runs"
DEFAULT_ANCHOR = PROJECT_ROOT / "config" / "anchors" / "kaspi_webui_archive_downloads.json"
DEFAULT_SESSION_STATE = PROJECT_ROOT / "runtime" / "playwright" / "kaspi_webui_archive_session.json"
DEFAULT_DOTENV_PATH = PROJECT_ROOT / ".env"
DEFAULT_ARCHIVE_URL = "https://kaspi.kz/mc/#/orders-new?status=ARCHIVED"
WINDOW_PROVENANCE_MANIFEST = "source_window_provenance.json"
DEFAULT_LOGIN_URL = "https://idmc.shop.kaspi.kz/login"
DOWNLOAD_SELECTOR_CANDIDATES = [
    "button:has-text('Выгрузить в EXCEL')",
    "button:has-text('Выгрузить')",
    "button:has-text('Скачать Excel')",
    "button:has-text('Скачать')",
    "button:has-text('Экспорт')",
    "button:has-text('Excel')",
    "a:has-text('Выгрузить в EXCEL')",
    "a:has-text('Выгрузить')",
    "a:has-text('Скачать Excel')",
    "a:has-text('Скачать')",
    "a:has-text('Экспорт')",
    "a:has-text('Excel')",
    "[data-testid*='export']",
    "[data-testid*='download']",
    "[aria-label*='Excel']",
    "[aria-label*='Скачать']",
    "[title*='Excel']",
]
ARCHIVE_TAB_SELECTORS = [
    "text=Архив",
    "button:has-text('Архив')",
    "a:has-text('Архив')",
    "[role='tab']:has-text('Архив')",
]
EMAIL_TAB_SELECTORS = [
    "[role='tab']:has-text('Email')",
    "button:has-text('Email')",
    "a:has-text('Email')",
    "label:has-text('Email')",
]
PHONE_TAB_SELECTORS = [
    "[role='tab']:has-text('Телефон')",
    "button:has-text('Телефон')",
    "a:has-text('Телефон')",
    "label:has-text('Телефон')",
]


class WebuiArchiveDownloadError(RuntimeError):
    """Raised when a WebUI archive download run cannot be completed."""


def _default_run_id() -> str:
    return f"webui_archive_download_{datetime.now().strftime('%Y%m%d_%H%M%S')}"


def _parse_iso_date(value: str | None) -> date | None:
    text = str(value or "").strip()
    if not text:
        return None
    return date.fromisoformat(text)


def _ddmmyyyy(value: date) -> str:
    return value.strftime("%d.%m.%Y")


def _plan_archive_windows(since: date | None, until: date | None) -> list[tuple[date | None, date | None]]:
    if since is None and until is None:
        return [(None, None)]
    if since is None or until is None:
        raise WebuiArchiveDownloadError("--since and --until must be provided together")
    return [(ws, we) for ws, we in plan_windows(since, until, WINDOW_DAYS)]


def _write_anchor(run_root: Path, run_manifest: Path) -> None:
    payload = {
        "version": 1,
        "updated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "latest_run_root": str(run_root),
        "latest_run_manifest": str(run_manifest),
    }
    DEFAULT_ANCHOR.parent.mkdir(parents=True, exist_ok=True)
    DEFAULT_ANCHOR.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _resolve_target_stores(stores_config: Path, store_codes: list[str] | None) -> list[str]:
    enabled_stores = load_enabled_stores(stores_config)
    if not store_codes:
        return enabled_stores
    selected = [str(value).strip().upper() for value in store_codes if str(value).strip()]
    selected = list(dict.fromkeys(selected))
    invalid = [store for store in selected if store not in enabled_stores]
    if invalid:
        raise WebuiArchiveDownloadError(
            f"store_code not enabled or unknown: {', '.join(invalid)}"
        )
    return selected


def _load_env(dotenv_path: Path | None) -> dict[str, str]:
    env: dict[str, str] = {}
    path = dotenv_path.expanduser().resolve() if dotenv_path is not None else DEFAULT_DOTENV_PATH
    if path.exists():
        for key, value in dotenv_values(path).items():
            if key and value is not None:
                env[str(key)] = str(value)
    for key, value in os.environ.items():
        env[str(key)] = str(value)
    return env


def _first_nonblank(mapping: dict[str, str], keys: list[str]) -> str:
    for key in keys:
        value = str(mapping.get(key) or "").strip()
        if value:
            return value
    return ""


def _phone_candidates(value: str) -> list[str]:
    text = str(value or "").strip()
    digits = "".join(ch for ch in text if ch.isdigit())
    candidates: list[str] = []
    for candidate in [
        text,
        digits,
        f"+7{digits[-10:]}" if len(digits) >= 10 else "",
        f"7{digits[-10:]}" if len(digits) >= 10 else "",
    ]:
        candidate = str(candidate or "").strip()
        if candidate and candidate not in candidates:
            candidates.append(candidate)
    return candidates


def _resolve_store_credentials(store_code: str, env: dict[str, str]) -> dict[str, str]:
    store = str(store_code).strip().upper()
    return {
        "email": _first_nonblank(
            env,
            [
                f"{store}_ACCOUNT_EMAIL",
                f"{store}_KASPI_ACCOUNT_EMAIL",
                f"{store}_EMAIL",
                f"{store}_LOGIN_EMAIL",
            ],
        ),
        "email_password": _first_nonblank(
            env,
            [
                f"{store}_ACCOUNT_PASSWORD",
                f"{store}_KASPI_ACCOUNT_PASSWORD",
                f"{store}_PASSWORD",
                f"{store}_LOGIN_PASSWORD",
            ],
        ),
        "phone": _first_nonblank(
            env,
            [
                f"Kaspi_marketing_login_{store}",
                f"KASPI_MARKETING_LOGIN_{store}",
                f"{store}_ACCOUNT_PHONE",
                f"{store}_PHONE",
                f"{store}_LOGIN_PHONE",
            ],
        ),
        "phone_password": _first_nonblank(
            env,
            [
                f"Kaspi_marketing_Password_{store}",
                f"KASPI_MARKETING_PASSWORD_{store}",
                f"{store}_PHONE_PASSWORD",
                f"{store}_ACCOUNT_PHONE_PASSWORD",
            ],
        ),
    }


def _run_session_check(
    *,
    run_root: Path,
    session_state: Path,
    strict: bool,
) -> dict[str, Any]:
    exists = session_state.exists() and session_state.stat().st_size > 0
    payload = {
        "mode": "session-check",
        "session_state_path": str(session_state),
        "session_state_present": exists,
        "status": "PASS" if exists else "FAIL",
        "ok": exists,
        "store_results": [],
        "target_stores": [],
    }
    if strict and not exists:
        raise WebuiArchiveDownloadError(f"session state missing or empty: {session_state}")
    return payload


def _run_import_existing(
    *,
    run_root: Path,
    source_root: Path,
    stores_config: Path,
    target_stores: list[str],
    since: date | None,
    until: date | None,
) -> dict[str, Any]:
    source_files = find_webui_source_files(source_root)
    by_store = {str(infer_store_code_from_path(path) or "").upper(): path for path in source_files}
    downloads_root = run_root / "downloads"
    downloads_root.mkdir(parents=True, exist_ok=True)

    store_results: list[dict[str, Any]] = []
    provenance_files: list[dict[str, Any]] = []
    requested_since = since.isoformat() if since else None
    requested_until = until.isoformat() if until else None
    for store in target_stores:
        source_file = by_store.get(store)
        if source_file is None:
            store_results.append({"store_code": store, "status": "FAIL", "error": "MISSING_SOURCE_FILE"})
            continue
        target_dir = downloads_root / f"store_{store}"
        target_dir.mkdir(parents=True, exist_ok=True)
        source_window_since, source_window_until = infer_window_from_path(source_file)
        if source_window_since and source_window_until:
            window_since = source_window_since
            window_until = source_window_until
            window_provenance = "source_path"
        elif requested_since and requested_until:
            window_since = requested_since
            window_until = requested_until
            window_provenance = "requested_cli_with_source_file_hash"
        else:
            window_since = None
            window_until = None
            window_provenance = ""
        if window_since and window_until:
            target_path = target_dir / f"ArchiveOrders_{store}_{window_since}_to_{window_until}{source_file.suffix}"
        else:
            target_path = target_dir / source_file.name
        if target_path.exists():
            target_path = target_dir / f"{target_path.stem}_{datetime.now().strftime('%H%M%S')}{target_path.suffix}"
        source_sha = compute_sha256(source_file)
        shutil.copy2(source_file, target_path)
        copied_sha = compute_sha256(target_path)
        provenance_row = {
            "store_code": store,
            "source_file": str(source_file),
            "copied_file": str(target_path.relative_to(downloads_root)),
            "source_file_sha256": source_sha,
            "copied_file_sha256": copied_sha,
            "window_since": window_since,
            "window_until": window_until,
            "window_provenance": window_provenance,
            "requested_since": requested_since,
            "requested_until": requested_until,
        }
        provenance_files.append(provenance_row)
        store_results.append(
            {
                "store_code": store,
                "status": "PASS",
                "source_file": str(source_file),
                "copied_file": str(target_path),
                "sha256": copied_sha,
                "source_file_sha256": source_sha,
                "copied_file_sha256": copied_sha,
                "window_since": window_since,
                "window_until": window_until,
                "window_provenance": window_provenance,
                "requested_since": requested_since,
                "requested_until": requested_until,
                "download_trigger": "import-existing",
            }
        )

    ok = all(item["status"] == "PASS" for item in store_results)
    provenance_manifest_path = downloads_root / WINDOW_PROVENANCE_MANIFEST
    provenance_manifest = {
        "schema_version": "webui_archive_source_window_provenance.v1",
        "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "mode": "import-existing",
        "source_root": str(source_root),
        "downloads_root": str(downloads_root),
        "requested_since": requested_since,
        "requested_until": requested_until,
        "files": provenance_files,
    }
    provenance_manifest_path.write_text(
        json.dumps(provenance_manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return {
        "mode": "import-existing",
        "source_root": str(source_root),
        "requested_since": requested_since,
        "requested_until": requested_until,
        "status": "PASS" if ok else "FAIL",
        "ok": ok,
        "store_results": store_results,
        "target_stores": target_stores,
        "source_window_provenance_json": str(provenance_manifest_path),
    }


def _safe_body_text(page, limit: int = 4000) -> str:
    try:
        return str(page.locator("body").inner_text() or "")[:limit]
    except Exception:
        return ""


def _login_required(page) -> bool:
    try:
        url = str(page.url or "").lower()
    except Exception:
        return True
    if "idmc.shop.kaspi.kz/login" in url or "merchant.kaspi.kz/new/account/entrance" in url:
        return True
    body = _safe_body_text(page, limit=1200).lower()
    if "кабинет продавца" in body and "продолжить" in body and ("телефон" in body or "email" in body):
        return True
    return False


def _wait_for_login(page, timeout_seconds: float) -> bool:
    deadline = time.time() + max(timeout_seconds, 1.0)
    while time.time() < deadline:
        if not _login_required(page):
            return True
        page.wait_for_timeout(1000)
    return not _login_required(page)


def _click_first_visible(page, selectors: list[str], timeout_ms: int = 3000) -> bool:
    for selector in selectors:
        try:
            locator = page.locator(selector).first
            if locator.count() == 0:
                continue
            if not locator.is_visible():
                continue
            locator.click(timeout=timeout_ms)
            return True
        except Exception:
            continue
    return False


def _choose_login_method(page, method: str) -> None:
    method_norm = str(method or "").strip().lower()
    if method_norm == "email":
        _click_first_visible(page, EMAIL_TAB_SELECTORS, timeout_ms=2500)
        page.wait_for_timeout(500)
    elif method_norm == "phone":
        _click_first_visible(page, PHONE_TAB_SELECTORS, timeout_ms=2500)
        page.wait_for_timeout(500)


def _attempt_email_login(page, email: str, password: str) -> dict[str, Any]:
    if not email or not password:
        return {"ok": False, "error": "EMAIL_CREDENTIALS_MISSING"}
    page.goto(DEFAULT_LOGIN_URL, wait_until="domcontentloaded", timeout=30000)
    page.wait_for_timeout(2000)
    _choose_login_method(page, "email")
    username_locator = page.locator("input[name='username']").first
    username_locator.fill(email)
    page.locator("button:has-text('Продолжить')").click(timeout=5000)
    page.wait_for_timeout(1500)
    if page.locator("input[type='password']").count() == 0:
        return {"ok": False, "error": "PASSWORD_FIELD_NOT_PRESENT"}
    page.locator("input[type='password']").first.fill(password)
    page.locator("button:has-text('Продолжить')").click(timeout=5000)
    page.wait_for_timeout(4000)
    body = _safe_body_text(page)
    if "неверные почта или пароль" in body.lower():
        return {"ok": False, "error": "INVALID_EMAIL_PASSWORD"}
    return {"ok": not _login_required(page), "error": "LOGIN_STILL_REQUIRED" if _login_required(page) else ""}


def _attempt_phone_login(page, phone: str, password: str) -> dict[str, Any]:
    if not phone:
        return {"ok": False, "error": "PHONE_CREDENTIALS_MISSING"}
    page.goto(DEFAULT_LOGIN_URL, wait_until="domcontentloaded", timeout=30000)
    page.wait_for_timeout(2000)
    _choose_login_method(page, "phone")
    locator = page.locator("input").first
    last_error = "PHONE_INPUT_REJECTED"
    for candidate in _phone_candidates(phone):
        locator.fill(candidate)
        page.locator("button:has-text('Продолжить')").click(timeout=5000)
        page.wait_for_timeout(1500)
        if page.locator("input[type='password']").count() > 0:
            if not password:
                return {"ok": False, "error": "PHONE_PASSWORD_MISSING"}
            page.locator("input[type='password']").first.fill(password)
            page.locator("button:has-text('Продолжить')").click(timeout=5000)
            page.wait_for_timeout(4000)
            body = _safe_body_text(page)
            if "неверный пароль" in body.lower():
                last_error = "INVALID_PHONE_PASSWORD"
                continue
            return {"ok": not _login_required(page), "error": "LOGIN_STILL_REQUIRED" if _login_required(page) else ""}
        body = _safe_body_text(page)
        if "код" in body.lower() and "sms" in body.lower():
            return {"ok": False, "error": "PHONE_REQUIRES_SMS"}
        if "введите номер телефона" in body.lower():
            last_error = "PHONE_INPUT_REJECTED"
            continue
    return {"ok": False, "error": last_error}


def _ensure_login(
    *,
    page,
    store_code: str,
    credentials: dict[str, str],
    manual_login: bool,
    login_timeout: float,
) -> dict[str, Any]:
    page.goto(DEFAULT_ARCHIVE_URL, wait_until="domcontentloaded", timeout=30000)
    page.wait_for_timeout(3000)
    if not _login_required(page):
        return {"ok": True, "auth_method": "session_state", "session_reused": True}

    if manual_login:
        page.goto(DEFAULT_LOGIN_URL, wait_until="domcontentloaded", timeout=30000)
        page.wait_for_timeout(2000)
        if credentials.get("email"):
            _choose_login_method(page, "email")
        logged_in = _wait_for_login(page, login_timeout)
        if not logged_in:
            return {"ok": False, "error": "MANUAL_LOGIN_TIMEOUT"}
        page.goto(DEFAULT_ARCHIVE_URL, wait_until="domcontentloaded", timeout=30000)
        page.wait_for_timeout(4000)
        return {
            "ok": not _login_required(page),
            "auth_method": "manual_login",
            "session_reused": False,
            "error": "LOGIN_STILL_REQUIRED" if _login_required(page) else "",
        }

    email_attempt = _attempt_email_login(page, credentials.get("email", ""), credentials.get("email_password", ""))
    if email_attempt.get("ok"):
        page.goto(DEFAULT_ARCHIVE_URL, wait_until="domcontentloaded", timeout=30000)
        page.wait_for_timeout(4000)
        return {"ok": True, "auth_method": "email_password", "session_reused": False}

    phone_attempt = _attempt_phone_login(page, credentials.get("phone", ""), credentials.get("phone_password", ""))
    if phone_attempt.get("ok"):
        page.goto(DEFAULT_ARCHIVE_URL, wait_until="domcontentloaded", timeout=30000)
        page.wait_for_timeout(4000)
        return {"ok": True, "auth_method": "phone_password", "session_reused": False}

    return {
        "ok": False,
        "error": str(phone_attempt.get("error") or email_attempt.get("error") or "LOGIN_FAILED"),
    }


def _collect_visible_controls(page) -> list[dict[str, str]]:
    controls: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for selector, kind in [("button", "button"), ("a", "link"), ("[role='button']", "role_button")]:
        try:
            count = min(page.locator(selector).count(), 100)
        except Exception:
            continue
        for idx in range(count):
            try:
                loc = page.locator(selector).nth(idx)
                if not loc.is_visible():
                    continue
                text = str(loc.inner_text() or "").strip()
                label = str(loc.get_attribute("aria-label") or "").strip()
                title = str(loc.get_attribute("title") or "").strip()
                entry = (kind, text or label or title)
                if entry in seen:
                    continue
                seen.add(entry)
                controls.append({"kind": kind, "text": text, "aria_label": label, "title": title})
            except Exception:
                continue
    return controls


def _save_download(
    download,
    target_dir: Path,
    store_code: str,
    *,
    window_since: str | None,
    window_until: str | None,
) -> Path:
    suggested = str(download.suggested_filename or "").strip()
    suffix = Path(suggested).suffix or ".xlsx"
    if window_since and window_until:
        target_name = f"ArchiveOrders_{store_code}_{window_since}_to_{window_until}{suffix}"
    else:
        target_name = suggested or f"ArchiveOrders_{store_code}{suffix}"
    target_path = target_dir / target_name
    if target_path.exists():
        target_path = target_dir / f"{target_path.stem}_{datetime.now().strftime('%H%M%S')}{target_path.suffix}"
    download.save_as(str(target_path))
    return target_path


def _wait_for_any_download(page, timeout_seconds: float):
    holder: dict[str, Any] = {}

    def _capture(download) -> None:
        holder["download"] = download

    page.on("download", _capture)
    deadline = time.time() + max(timeout_seconds, 1.0)
    while time.time() < deadline:
        if "download" in holder:
            return holder["download"]
        page.wait_for_timeout(1000)
    return None


def _find_datepicker(page, placeholder: str):
    picker = page.locator(".datepicker").filter(has=page.locator(f"input[placeholder='{placeholder}']")).first
    if picker.count() == 0:
        raise WebuiArchiveDownloadError(f"missing archive datepicker for placeholder={placeholder}")
    return picker


def _set_archive_date(page, placeholder: str, target_date: date) -> None:
    picker = _find_datepicker(page, placeholder)
    input_locator = picker.locator(f"input[placeholder='{placeholder}']").first
    input_locator.click(timeout=5000)
    page.wait_for_timeout(300)

    selects = picker.locator("select")
    if selects.count() < 2:
        raise WebuiArchiveDownloadError(f"datepicker selects unavailable for placeholder={placeholder}")
    selects.nth(1).select_option(str(target_date.year))
    page.wait_for_timeout(200)
    selects.nth(0).select_option(str(target_date.month - 1))
    page.wait_for_timeout(400)

    day_cells = picker.locator("a.is-selectable.datepicker-cell")
    clicked = False
    for idx in range(day_cells.count()):
        cell = day_cells.nth(idx)
        try:
            if not cell.is_visible():
                continue
            if str(cell.inner_text() or "").strip() != str(target_date.day):
                continue
            cell.click(timeout=5000)
            clicked = True
            break
        except Exception:
            continue
    if not clicked:
        raise WebuiArchiveDownloadError(
            f"unable to select date {target_date.isoformat()} for placeholder={placeholder}"
        )
    page.wait_for_timeout(500)

    actual = str(input_locator.input_value() or "").strip()
    expected = _ddmmyyyy(target_date)
    if actual != expected:
        raise WebuiArchiveDownloadError(
            f"datepicker value mismatch for {placeholder}: expected {expected} got {actual or '<blank>'}"
        )


def _apply_archive_window(page, since: date | None, until: date | None) -> tuple[str | None, str | None]:
    if since is None and until is None:
        return None, None
    if since is None or until is None:
        raise WebuiArchiveDownloadError("archive window requires both since and until")
    _set_archive_date(page, "Дата От", since)
    _set_archive_date(page, "Дата До", until)
    page.locator("button:has-text('Применить')").click(timeout=5000)
    try:
        page.wait_for_load_state("networkidle", timeout=5000)
    except Exception:
        pass
    page.wait_for_timeout(4000)
    actual_since = str(page.locator("input[placeholder='Дата От']").first.input_value() or "").strip()
    actual_until = str(page.locator("input[placeholder='Дата До']").first.input_value() or "").strip()
    expected_since = _ddmmyyyy(since)
    expected_until = _ddmmyyyy(until)
    if actual_since != expected_since or actual_until != expected_until:
        raise WebuiArchiveDownloadError(
            "archive date filter mismatch after apply: "
            f"expected={expected_since}->{expected_until} got={actual_since or '<blank>'}->{actual_until or '<blank>'}"
        )
    return since.isoformat(), until.isoformat()


def _attempt_archive_download(
    *,
    page,
    store_code: str,
    target_dir: Path,
    diagnostics_dir: Path,
    download_timeout: float,
    allow_manual_download: bool,
    window_since: str | None,
    window_until: str | None,
) -> dict[str, Any]:
    diagnostics_dir.mkdir(parents=True, exist_ok=True)
    _click_first_visible(page, ARCHIVE_TAB_SELECTORS, timeout_ms=2500)
    page.wait_for_timeout(3000)

    controls = _collect_visible_controls(page)
    controls_path = diagnostics_dir / "visible_controls.json"
    controls_path.write_text(json.dumps(controls, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    screenshot_path = diagnostics_dir / "archive_page.png"
    try:
        page.screenshot(path=str(screenshot_path), full_page=True)
    except Exception:
        screenshot_path = diagnostics_dir / "archive_page_unavailable.txt"
        screenshot_path.write_text("screenshot unavailable\n", encoding="utf-8")

    for selector in DOWNLOAD_SELECTOR_CANDIDATES:
        try:
            locator = page.locator(selector).first
            if locator.count() == 0 or not locator.is_visible():
                continue
            with page.expect_download(timeout=int(download_timeout * 1000)) as download_info:
                locator.click(timeout=5000)
            download = download_info.value
            target_path = _save_download(
                download,
                target_dir,
                store_code,
                window_since=window_since,
                window_until=window_until,
            )
            return {
                "ok": True,
                "copied_file": str(target_path),
                "sha256": compute_sha256(target_path),
                "download_trigger": selector,
                "visible_controls_json": str(controls_path),
                "archive_page_screenshot": str(screenshot_path),
            }
        except Exception:
            continue

    if allow_manual_download:
        download = _wait_for_any_download(page, timeout_seconds=download_timeout)
        if download is not None:
            target_path = _save_download(
                download,
                target_dir,
                store_code,
                window_since=window_since,
                window_until=window_until,
            )
            return {
                "ok": True,
                "copied_file": str(target_path),
                "sha256": compute_sha256(target_path),
                "download_trigger": "manual_download_fallback",
                "visible_controls_json": str(controls_path),
                "archive_page_screenshot": str(screenshot_path),
            }

    return {
        "ok": False,
        "error": "DOWNLOAD_CONTROL_NOT_FOUND",
        "visible_controls_json": str(controls_path),
        "archive_page_screenshot": str(screenshot_path),
    }


def _run_live_download(
    *,
    run_root: Path,
    stores_config: Path,
    target_stores: list[str],
    session_state: Path,
    strict: bool,
    headful: bool,
    manual_login: bool,
    login_timeout: float,
    download_timeout: float,
    archive_url: str,
    dotenv_path: Path | None,
    allow_manual_download: bool,
    since: date | None,
    until: date | None,
) -> dict[str, Any]:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        raise WebuiArchiveDownloadError("Playwright is required. Install via: pip install playwright") from exc

    env = _load_env(dotenv_path)
    downloads_root = run_root / "downloads"
    diagnostics_root = run_root / "diagnostics"
    downloads_root.mkdir(parents=True, exist_ok=True)
    diagnostics_root.mkdir(parents=True, exist_ok=True)
    planned_windows = _plan_archive_windows(since, until)

    store_results: list[dict[str, Any]] = []
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="chrome", headless=not headful)
        try:
            for store_code in target_stores:
                target_dir = downloads_root / f"store_{store_code}"
                target_dir.mkdir(parents=True, exist_ok=True)
                diagnostics_dir = diagnostics_root / f"store_{store_code}"
                diagnostics_dir.mkdir(parents=True, exist_ok=True)
                credentials = _resolve_store_credentials(store_code, env)

                context_kwargs: dict[str, Any] = {"accept_downloads": True}
                if session_state.exists() and session_state.stat().st_size > 0:
                    context_kwargs["storage_state"] = str(session_state)
                context = browser.new_context(**context_kwargs)
                page = context.new_page()
                try:
                    auth = _ensure_login(
                        page=page,
                        store_code=store_code,
                        credentials=credentials,
                        manual_login=manual_login,
                        login_timeout=login_timeout,
                    )
                    if not auth.get("ok"):
                        store_results.append(
                            {
                                "store_code": store_code,
                                "status": "FAIL",
                                "error": str(auth.get("error") or "LOGIN_FAILED"),
                                "auth_method": auth.get("auth_method", "unknown"),
                            }
                        )
                        continue

                    session_state.parent.mkdir(parents=True, exist_ok=True)
                    context.storage_state(path=str(session_state))

                    for window_start, window_end in planned_windows:
                        page.goto(archive_url, wait_until="domcontentloaded", timeout=30000)
                        page.wait_for_timeout(5000)
                        applied_since, applied_until = _apply_archive_window(page, window_start, window_end)
                        window_label = (
                            f"{applied_since}_to_{applied_until}"
                            if applied_since and applied_until
                            else "current_view"
                        )
                        download_report = _attempt_archive_download(
                            page=page,
                            store_code=store_code,
                            target_dir=target_dir,
                            diagnostics_dir=diagnostics_dir / window_label,
                            download_timeout=download_timeout,
                            allow_manual_download=allow_manual_download,
                            window_since=applied_since,
                            window_until=applied_until,
                        )
                        if not download_report.get("ok"):
                            store_results.append(
                                {
                                    "store_code": store_code,
                                    "status": "FAIL",
                                    "error": str(download_report.get("error") or "DOWNLOAD_FAILED"),
                                    "auth_method": auth.get("auth_method", "unknown"),
                                    "window_since": applied_since,
                                    "window_until": applied_until,
                                    "visible_controls_json": download_report.get("visible_controls_json"),
                                    "archive_page_screenshot": download_report.get("archive_page_screenshot"),
                                }
                            )
                            continue

                        copied_file = Path(str(download_report["copied_file"]))
                        window_since, window_until = infer_window_from_path(copied_file)
                        store_results.append(
                            {
                                "store_code": store_code,
                                "status": "PASS",
                                "copied_file": str(copied_file),
                                "sha256": str(download_report["sha256"]),
                                "window_since": window_since,
                                "window_until": window_until,
                                "auth_method": auth.get("auth_method", "unknown"),
                                "download_trigger": download_report.get("download_trigger"),
                                "visible_controls_json": download_report.get("visible_controls_json"),
                                "archive_page_screenshot": download_report.get("archive_page_screenshot"),
                                "session_state_path": str(session_state),
                            }
                        )
                finally:
                    context.close()
        finally:
            browser.close()

    ok = all(item["status"] == "PASS" for item in store_results)
    payload = {
        "mode": "live-download",
        "archive_url": archive_url,
        "session_state_path": str(session_state),
        "headful": bool(headful),
        "manual_login": bool(manual_login),
        "allow_manual_download": bool(allow_manual_download),
        "login_timeout": login_timeout,
        "download_timeout": download_timeout,
        "requested_since": since.isoformat() if since else None,
        "requested_until": until.isoformat() if until else None,
        "window_days": WINDOW_DAYS,
        "planned_windows": [
            {
                "window_since": ws.isoformat() if ws else None,
                "window_until": we.isoformat() if we else None,
            }
            for ws, we in planned_windows
        ],
        "target_stores": target_stores,
        "status": "PASS" if ok else "FAIL",
        "ok": ok,
        "store_results": store_results,
    }
    return payload


def download_kaspi_archive_webui(
    *,
    mode: str,
    run_id: str | None,
    output_root: Path,
    stores_config: Path,
    session_state: Path,
    source_root: Path | None,
    strict: bool,
    store_codes: list[str] | None = None,
    headful: bool = False,
    manual_login: bool = False,
    login_timeout: float = 300.0,
    download_timeout: float = 120.0,
    archive_url: str = DEFAULT_ARCHIVE_URL,
    dotenv_path: Path | None = DEFAULT_DOTENV_PATH,
    allow_manual_download: bool = False,
    since: date | None = None,
    until: date | None = None,
    write_anchor: bool = True,
) -> dict[str, Any]:
    run_root = output_root.resolve() / str(run_id or _default_run_id())
    run_root.mkdir(parents=True, exist_ok=True)
    target_stores = _resolve_target_stores(stores_config, store_codes)
    if mode == "session-check":
        payload = _run_session_check(run_root=run_root, session_state=session_state, strict=strict)
    elif mode == "import-existing":
        if source_root is None:
            raise WebuiArchiveDownloadError("--source-root is required for --mode import-existing")
        payload = _run_import_existing(
            run_root=run_root,
            source_root=source_root.expanduser().resolve(),
            stores_config=stores_config,
            target_stores=target_stores,
            since=since,
            until=until,
        )
    elif mode == "live-download":
        payload = _run_live_download(
            run_root=run_root,
            stores_config=stores_config,
            target_stores=target_stores,
            session_state=session_state.expanduser().resolve(),
            strict=bool(strict),
            headful=bool(headful),
            manual_login=bool(manual_login),
            login_timeout=float(login_timeout),
            download_timeout=float(download_timeout),
            archive_url=str(archive_url),
            dotenv_path=dotenv_path.expanduser().resolve() if dotenv_path else None,
            allow_manual_download=bool(allow_manual_download),
            since=since,
            until=until,
        )
    else:
        raise WebuiArchiveDownloadError(f"unsupported mode: {mode}")

    payload.update(
        {
            "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
            "run_id": run_root.name,
            "run_root": str(run_root),
            "stores_config": str(stores_config),
            "strict": bool(strict),
            "target_stores": target_stores,
            "anchor_written": bool(write_anchor),
            "anchor_path": str(DEFAULT_ANCHOR),
        }
    )
    run_manifest = run_root / "run_manifest.json"
    download_log = run_root / "download_log.md"
    run_manifest.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    lines = [
        "# WebUI Archive Download Run",
        "",
        f"- run_id: `{run_root.name}`",
        f"- mode: `{mode}`",
        f"- status: `{payload['status']}`",
        f"- strict: `{str(bool(strict)).lower()}`",
        f"- target_stores: `{', '.join(target_stores)}`",
        f"- requested_since: `{payload.get('requested_since') or ''}`",
        f"- requested_until: `{payload.get('requested_until') or ''}`",
        "",
        "| store_code | window_since | window_until | status | copied_file | auth_method | download_trigger | error |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for row in payload.get("store_results", []):
        lines.append(
            f"| `{row.get('store_code', '')}` | `{row.get('window_since', '')}` | `{row.get('window_until', '')}` | `{row.get('status', '')}` | "
            f"`{row.get('copied_file', '')}` | `{row.get('auth_method', '')}` | "
            f"`{row.get('download_trigger', '')}` | `{row.get('error', '')}` |"
        )
    download_log.write_text("\n".join(lines) + "\n", encoding="utf-8")
    if write_anchor:
        _write_anchor(run_root, run_manifest)
    payload["run_manifest_json"] = str(run_manifest)
    payload["download_log_md"] = str(download_log)
    if strict and not bool(payload.get("ok", False)):
        failures = ", ".join(
            f"{row.get('store_code', '')}:{row.get('error', 'FAIL')}"
            for row in payload.get("store_results", [])
            if str(row.get("status", "")).upper() != "PASS"
        )
        raise WebuiArchiveDownloadError(f"{mode} run failed: {failures or 'strict gate red'}")
    return payload


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Manage WebUI archive download runs")
    parser.add_argument("--mode", choices=["session-check", "import-existing", "live-download"], required=True)
    parser.add_argument("--run-id", default=None)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--stores-config", type=Path, default=DEFAULT_STORES_CONFIG)
    parser.add_argument("--session-state", type=Path, default=DEFAULT_SESSION_STATE)
    parser.add_argument("--source-root", type=Path, default=None)
    parser.add_argument("--store-code", action="append", default=None)
    parser.add_argument("--headful", action="store_true")
    parser.add_argument("--manual-login", action="store_true")
    parser.add_argument("--login-timeout", type=float, default=300.0)
    parser.add_argument("--download-timeout", type=float, default=120.0)
    parser.add_argument("--archive-url", default=DEFAULT_ARCHIVE_URL)
    parser.add_argument("--dotenv-path", type=Path, default=DEFAULT_DOTENV_PATH)
    parser.add_argument("--allow-manual-download", action="store_true")
    parser.add_argument("--since", default=None)
    parser.add_argument("--until", default=None)
    parser.add_argument("--no-anchor-write", action="store_true")
    parser.add_argument("--strict", action="store_true")
    return parser


def main() -> int:
    args = _build_parser().parse_args()
    try:
        report = download_kaspi_archive_webui(
            mode=str(args.mode),
            run_id=args.run_id,
            output_root=args.output_root,
            stores_config=args.stores_config,
            session_state=args.session_state,
            source_root=args.source_root,
            strict=bool(args.strict),
            store_codes=list(args.store_code or []),
            headful=bool(args.headful),
            manual_login=bool(args.manual_login),
            login_timeout=float(args.login_timeout),
            download_timeout=float(args.download_timeout),
            archive_url=str(args.archive_url),
            dotenv_path=args.dotenv_path,
            allow_manual_download=bool(args.allow_manual_download),
            since=_parse_iso_date(args.since),
            until=_parse_iso_date(args.until),
            write_anchor=not bool(args.no_anchor_write),
        )
    except WebuiArchiveDownloadError as exc:
        print("status=FAIL")
        print("error_code=WEBUI_ARCHIVE_DOWNLOAD_FAIL")
        print(f"message={exc}")
        return 1

    print(f"run_manifest_json={report['run_manifest_json']}")
    print(f"download_log_md={report['download_log_md']}")
    print(f"status={report['status']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
