#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Phase 12: WhatsApp PDF Sender for Waybills

Sends waybill PDFs to a specific WhatsApp chat using WhatsApp Web automation.

Key behavior:
- Uses MERGED bundles first (fallback to PER_STORE/legacy)
- Orders files by category, then by contiguous SKU blocks with size-rising order
- Tracks sent files in sent_pdfs.json to avoid duplicates
- Strict chat safety gate: only send to configured chat title
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import re
import shutil
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional
from zoneinfo import ZoneInfo

# Add project root to path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from core.ops.waybill_send_batch import (
    LEDGER_STATES,
    SEND_BATCH_MANIFEST_FILE,
    SEND_LEDGER_FILE,
    SEND_STOPLINE_FILE,
    load_send_ledger as core_load_send_ledger,
    resolve_unsure_ledger_entry as core_resolve_unsure_ledger_entry,
    resolve_manifest_entry_path as core_resolve_manifest_entry_path,
    save_send_ledger as core_save_send_ledger,
    select_manifest_entries_for_send as core_select_manifest_entries_for_send,
    transition_send_ledger_entry as core_transition_send_ledger_entry,
)


# =============================================================================
# CONFIGURATION
# =============================================================================

DEFAULT_WHATSAPP_CHAT_TITLE = "Заказы"
BLOCKED_CHAT_TITLES_DEFAULT = ("order 2",)

# Browser profile used for WhatsApp Web session
DEFAULT_CHROME_USER_DATA_DIR = Path.home() / "Library" / "Application Support" / "Google" / "Chrome"
DEFAULT_WHATSAPP_AUTOMATION_USER_DATA_DIR = (
    Path.home() / "Library" / "Application Support" / "Google" / "Chrome-WhatsAppDebug"
)
DEFAULT_CHROME_PROFILE_NAME = "Universal"
DEFAULT_CHROME_PROFILE_DIR = "Profile 2"
DEFAULT_CDP_ENDPOINT = "http://127.0.0.1:9222"
DEFAULT_CDP_ENDPOINT_IPV6 = "http://[::1]:9222"
BROWSER_MODE_ATTACH = "attach"
BROWSER_MODE_LAUNCH = "launch-temp"
BROWSER_MODE_CHOICES = [BROWSER_MODE_ATTACH, BROWSER_MODE_LAUNCH]
DEFAULT_BROWSER_MODE = BROWSER_MODE_ATTACH
DEFAULT_WHATSAPP_CHAT_IDENTITY_FILE = (
    PROJECT_ROOT / "config" / "identity" / "whatsapp_chat_fingerprints.json"
)

# Copy profile to temp to avoid Chrome singleton lock when user's Chrome is open
COPY_PROFILE_TO_TEMP = True

# Default paths
TODAY_FOLDER = PROJECT_ROOT / "excel_ui" / "Kaspi_orders" / "Today"
SENT_TRACKER_FILE = "sent_pdfs.json"
# PDF sending order (priority high to low)
PDF_CATEGORIES = [
    "SPECIAL_multi_line",
    "SPECIAL_multi_qty",
    "NORMAL_singles",
]
CATEGORY_PRIORITY = {name: idx for idx, name in enumerate(PDF_CATEGORIES)}

# Source roots under Today
SOURCE_AUTO = "auto"
SOURCE_MERGED = "merged"
SOURCE_PER_STORE = "per-store"
SOURCE_LEGACY = "legacy"
SOURCE_CHOICES = [SOURCE_AUTO, SOURCE_MERGED, SOURCE_PER_STORE, SOURCE_LEGACY]
MERGED_SEND_ROOT_NAME = "SEND"
ALMATY_TZ = ZoneInfo("Asia/Almaty")
WHATSAPP_DIAGNOSTICS_DIR_NAME = "whatsapp_diagnostics"

STORE_DISPLAY = {
    "STOREB": "STORE-B",
    "STORE-B": "STORE-B",
    "ACMEWEAR": "AcmeWear",
    "UNIVERSAL": "Universal",
    "MELVIS": "Store-C",
    "11KZ": "11KZ",
    "MERGED": "MERGED",
}

# Size ordering for send priority
SIZE_ORDER = {
    # Kids
    "22": 1,
    "24": 2,
    "26": 3,
    "28": 4,
    "30": 5,
    # Adult
    "S": 10,
    "M": 11,
    "L": 12,
    "XL": 13,
    "2XL": 14,
    "3XL": 15,
    "4XL": 16,
}
SIZE_TOKEN_RE = re.compile(r"(22|24|26|28|30|2XL|3XL|4XL|XL|S|M|L)", re.IGNORECASE)
TRAILING_SIZE_RE = re.compile(
    r"_(22|24|26|28|30|2XL|3XL|4XL|XL|S|M|L)-\d+$",
    re.IGNORECASE,
)
MESSY_MULTI_SIZE_RE = re.compile(
    r"-(22|24|26|28|30|2XL|3XL|4XL|XL|S|M|L)-\d+\(",
    re.IGNORECASE,
)
COLOR_TOKENS = {
    "BLACK", "WHITE", "GRAY", "GREY", "RED", "BLUE", "GREEN", "BROWN", "BEIGE",
    "PINK", "PURPLE", "YELLOW", "ORANGE",
    "ЧЕРНЫЙ", "ЧЕРНАЯ", "БЕЛЫЙ", "БЕЛАЯ", "СЕРЫЙ", "СЕРАЯ", "КРАСНЫЙ", "СИНИЙ",
    "ЗЕЛЕНЫЙ", "КОРИЧНЕВЫЙ", "БЕЖЕВЫЙ", "РОЗОВЫЙ", "ФИОЛЕТОВЫЙ", "ЖЕЛТЫЙ",
}
NOISE_TOKENS = {
    "CL", "NEW", "CLO", "MEN", "MAN", "WOMEN", "WOMAN", "KID", "KIDS",
    "MESTOVAYA", "PROD", "SKU", "COLOR", "SIZE", "PP1",
}

# Delay between sends (seconds)
SEND_DELAY = 0.4
DEFAULT_DELIVERY_PROBE_MESSAGE_PREFIX = "[WA delivery probe]"
DEFAULT_DELIVERY_PROBE_REPEAT_COUNT = 2
DEFAULT_DELIVERY_PROBE_INTERVAL_SECONDS = 300.0
DEFAULT_DELIVERY_PROBE_TIMEOUT_SECONDS = 120.0
DOCUMENT_APPEAR_TIMEOUT_MS = 20_000
DOCUMENT_SETTLE_TIMEOUT_MS = 30_000
DOCUMENT_POLL_INTERVAL_MS = 250
TEXT_SETTLE_TIMEOUT_MS = 20_000
UNSURE_REASON_PREFIX = "UNSURE:"
DOCUMENT_INPUT_SELECTORS = [
    "input[type='file'][accept='*']",
    "input[type='file'][accept='*/*']",
    "input[type='file']:not([accept])",
]
ATTACH_BUTTON_SELECTORS = [
    "button[aria-label='Attach']",
    "button[aria-label='Прикрепить']",
]
DOCUMENT_MENU_SELECTORS = [
    "button[aria-label='Document']",
    "button[aria-label='Документ']",
    "div[role='button'][aria-label='Document']",
    "div[role='button'][aria-label='Документ']",
    "div[role='menuitem'][aria-label='Document']",
    "div[role='menuitem'][aria-label='Документ']",
]

WHATSAPP_WEB_URL = "https://web.whatsapp.com"
CHAT_OPEN_TIMEOUT_MS = 90_000
ACTION_TIMEOUT_MS = 45_000
WHATSAPP_DEBUG_CHROME_HELPER = PROJECT_ROOT / "excel_ui" / "start_whatsapp_debug_chrome.command"


# =============================================================================
# TRACKER
# =============================================================================


def load_sent_tracker(tracker_path: Path) -> Dict[str, Any]:
    """Load the sent PDFs tracker file."""
    if tracker_path.exists():
        try:
            with open(tracker_path, "r", encoding="utf-8") as f:
                payload = json.load(f)
                if isinstance(payload, dict) and isinstance(payload.get("sent", []), list):
                    return payload
        except (json.JSONDecodeError, IOError):
            pass
    return {"sent": [], "last_updated": None}


def save_sent_tracker(tracker_path: Path, tracker: Dict[str, Any]) -> None:
    """Save the sent PDFs tracker file atomically."""
    tracker["last_updated"] = datetime.now().isoformat()
    temp_path = tracker_path.with_suffix(".tmp")
    with open(temp_path, "w", encoding="utf-8") as f:
        json.dump(tracker, f, indent=2, ensure_ascii=False)
    temp_path.replace(tracker_path)


# =============================================================================
# MANIFEST / LEDGER
# =============================================================================


FINAL_LEDGER_STATES = {"confirmed", "unsure", "failed"}


def _hash_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _looks_like_sha256(value: Any) -> bool:
    return bool(re.fullmatch(r"[0-9a-fA-F]{64}", str(value or "").strip()))


def _manifest_batch_hash(entries: List[Dict[str, Any]]) -> str:
    digest = hashlib.sha256()
    stable_entries = []
    for entry in sorted(entries, key=lambda x: str(x.get("pdf_key") or "")):
        stable_entries.append(
            {
                "pdf_key": entry.get("pdf_key", ""),
                "relative_output_path": entry.get("relative_output_path", ""),
                "sha256": entry.get("sha256", ""),
                "file_size": int(entry.get("file_size", 0) or 0),
                "mtime": entry.get("mtime", ""),
                "logical_group_type": entry.get("logical_group_type", ""),
                "order_ids": list(entry.get("order_ids") or []),
                "source_row_ids": list(entry.get("source_row_ids") or []),
                "product_family_key": entry.get("product_family_key", ""),
                "color_key": entry.get("color_key", ""),
                "product_color_key": entry.get("product_color_key", ""),
                "size_token": entry.get("size_token", ""),
                "size_rank": int(entry.get("size_rank", 0) or 0),
                "send_sequence": int(entry.get("send_sequence", 0) or 0),
            }
        )
    digest.update(json.dumps(stable_entries, ensure_ascii=False, sort_keys=True).encode("utf-8"))
    return digest.hexdigest()


def _resolve_batch_folder(today_folder: Path, source_mode: str = SOURCE_AUTO) -> Path:
    source_root = resolve_send_root(today_folder, source_mode=source_mode)
    if (source_root / SEND_BATCH_MANIFEST_FILE).exists():
        return source_root

    batch_folders = sorted(
        [
            item
            for item in source_root.iterdir()
            if item.is_dir() and (item / SEND_BATCH_MANIFEST_FILE).exists()
        ],
        key=lambda path: path.name,
    ) if source_root.exists() else []

    if not batch_folders:
        batch_folders = [
            folder
            for folder in _collect_store_folders(source_root)
            if (folder / SEND_BATCH_MANIFEST_FILE).exists()
        ]
    if not batch_folders:
        raise FileNotFoundError(f"No batch folders found under {source_root}")
    if len(batch_folders) == 1:
        return batch_folders[0]

    def _manifest_sort_key(path: Path) -> tuple[float, str]:
        manifest_path = path / SEND_BATCH_MANIFEST_FILE
        try:
            manifest_mtime = manifest_path.stat().st_mtime
        except OSError:
            manifest_mtime = 0.0
        return (manifest_mtime, path.name)

    return sorted(batch_folders, key=_manifest_sort_key)[-1]


def _resolve_manifest_entry_path(batch_root: Path, entry: Dict[str, Any]) -> Path:
    return core_resolve_manifest_entry_path(batch_root, entry)


def load_send_batch_manifest(today_folder: Path, source_mode: str = SOURCE_AUTO) -> Dict[str, Any]:
    batch_root = _resolve_batch_folder(today_folder, source_mode=source_mode)
    manifest_path = batch_root / SEND_BATCH_MANIFEST_FILE
    if not manifest_path.exists():
        raise FileNotFoundError(f"Missing send batch manifest: {manifest_path}")

    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    entries = list(payload.get("entries") or [])
    hydrated_entries: List[Dict[str, Any]] = []
    for raw_entry in entries:
        entry = dict(raw_entry)
        entry["path"] = _resolve_manifest_entry_path(batch_root, entry)
        if not Path(entry["path"]).exists():
            _recover_missing_pdf_path(entry, today_folder)
        hydrated_entries.append(entry)
    payload["entries"] = hydrated_entries
    payload["manifest_path"] = str(manifest_path)
    payload["batch_root"] = str(batch_root)
    return payload


def load_send_ledger(ledger_path: Path, manifest: Dict[str, Any]) -> Dict[str, Any]:
    return core_load_send_ledger(ledger_path, manifest)


def save_send_ledger(ledger_path: Path, ledger: Dict[str, Any]) -> None:
    core_save_send_ledger(ledger_path, ledger)


def transition_send_ledger_entry(
    ledger: Dict[str, Any],
    pdf_key: str,
    new_state: str,
    *,
    allow_unsure_resume: bool = False,
    note: Optional[str] = None,
) -> Dict[str, Any]:
    return core_transition_send_ledger_entry(
        ledger,
        pdf_key,
        new_state,
        allow_unsure_resume=allow_unsure_resume,
        note=note or "",
    )


def resolve_unsure_ledger_entry(
    manifest: Dict[str, Any],
    ledger: Dict[str, Any],
    *,
    filename: str,
    resolution: str,
    note: str = "",
) -> str:
    return core_resolve_unsure_ledger_entry(
        manifest,
        ledger,
        filename=filename,
        resolution=resolution,
        note=note,
    )


def select_manifest_entries_for_send(
    manifest: Dict[str, Any],
    ledger: Dict[str, Any],
    *,
    allow_unsure_resume: bool = False,
) -> List[Dict[str, Any]]:
    return core_select_manifest_entries_for_send(
        manifest,
        ledger,
        allow_unsure_resume=allow_unsure_resume,
    )


def _write_send_stopline(today_folder: Path, payload: Dict[str, Any]) -> Path:
    output_path = today_folder / SEND_STOPLINE_FILE
    output_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return output_path


def _default_recovery_ladder(chat_title: str, batch_root: Optional[Path]) -> List[Dict[str, str]]:
    batch_label = batch_root.name if batch_root else "current SEND batch"
    return [
        {
            "code": "playwright_retry",
            "detail": (
                "Retry the sender after confirming WhatsApp Web is logged in and the target chat is open. "
                "The sender already retries one layer automatically before this point."
            ),
        },
        {
            "code": "chrome_existing_tab",
            "detail": (
                f"If Playwright still drifts, inspect the already-open Google Chrome WhatsApp Web tab, "
                f"select chat '{chat_title}', and verify the document attach controls are visible for batch {batch_label}."
            ),
        },
        {
            "code": "macos_whatsapp_fallback",
            "detail": (
                f"If Web UI remains blocked, use the macOS WhatsApp app as the final manual recovery surface "
                f"to verify the batch tail and post the final status for {batch_label}."
            ),
        },
    ]


def capture_sender_failure_diagnostics(
    sender: Any,
    *,
    today_folder: Path,
    failure_code: str,
    batch_root: Optional[Path],
    manifest_path: Optional[Path],
    pdf_filename: Optional[str],
    detail: str,
) -> Dict[str, Any]:
    timestamp = datetime.now(ALMATY_TZ).strftime("%Y%m%d_%H%M%S")
    diagnostics_dir = today_folder / WHATSAPP_DIAGNOSTICS_DIR_NAME / f"{timestamp}_{failure_code.lower()}"
    diagnostics_dir.mkdir(parents=True, exist_ok=True)

    try:
        page = sender.page
    except Exception:
        page = None
    screenshot_path = diagnostics_dir / "page.png"
    html_path = diagnostics_dir / "page.html"
    summary_path = diagnostics_dir / "dom_summary.json"
    context_path = diagnostics_dir / "failure_context.json"

    summary: Dict[str, Any] = {
        "failure_code": failure_code,
        "detail": detail,
        "pdf_filename": pdf_filename or "",
        "manifest_path": str(manifest_path or ""),
        "batch_root": str(batch_root or ""),
        "captured_at": datetime.now(ALMATY_TZ).isoformat(),
        "browser_mode": str(getattr(sender, "browser_mode", "") or ""),
        "profile_name": str(getattr(sender, "profile_name", "") or ""),
        "profile_directory": str(getattr(sender, "profile_directory", "") or ""),
        "cdp_endpoint": str(getattr(sender, "cdp_endpoint", "") or ""),
        "ui_invalidated": bool(getattr(sender, "_ui_invalidated", False)),
        "ui_invalidation_reason": str(getattr(sender, "_ui_invalidation_reason", "") or ""),
        "document_send_inflight": bool(getattr(sender, "_document_send_inflight", False)),
        "document_send_filename": str(getattr(sender, "_document_send_filename", "") or ""),
    }

    if page is not None:
        try:
            page.screenshot(path=str(screenshot_path), full_page=True)
            summary["screenshot_path"] = str(screenshot_path)
        except Exception as exc:
            summary["screenshot_error"] = str(exc)

        try:
            html = page.content()
            html_path.write_text(str(html), encoding="utf-8")
            summary["html_path"] = str(html_path)
        except Exception as exc:
            summary["html_error"] = str(exc)

        try:
            dom_summary = page.evaluate(
                f"""
                () => {{
                  const activeTitle = (() => {{
                    const selectedRow = document.querySelector("div[aria-label='Chat list'] [aria-selected='true']");
                    if (selectedRow) {{
                      const rowName = selectedRow.querySelector("span[title], span[dir='auto']");
                      if (rowName) {{
                        return String(rowName.getAttribute?.('title') || rowName.textContent || '').trim();
                      }}
                    }}
                    const headers = Array.from(document.querySelectorAll('header')).reverse();
                    for (const header of headers) {{
                      const nodes = [
                        ...header.querySelectorAll("span[dir='auto']"),
                        ...header.querySelectorAll('span[title]'),
                        ...header.querySelectorAll('h1, h2'),
                      ];
                      for (const node of nodes) {{
                        const text = String(node.getAttribute?.('title') || node.textContent || '').trim();
                        if (text) return text;
                      }}
                    }}
                    return '';
                  }})();
                  return {{
                    document_title: document.title || '',
                    url: location.href || '',
                    active_chat_title: activeTitle,
                    chat_home_visible: document.body?.innerText?.includes('Download WhatsApp for Mac') || false,
                    chat_list_visible: !!document.querySelector("div[aria-label='Chat list']"),
                    composer_visible: !!document.querySelector("footer div[contenteditable='true'][role='textbox'], footer div[contenteditable='true'][data-lexical-editor='true'], div[contenteditable='true'][aria-label='Type a message'], div[contenteditable='true'][aria-label^='Type to group'], footer div[contenteditable='true']"),
                    attach_button_visible: !!document.querySelector("{ATTACH_BUTTON_SELECTORS[0]}, {ATTACH_BUTTON_SELECTORS[1]}"),
                    document_controls_visible: !!document.querySelector("{DOCUMENT_INPUT_SELECTORS[0]}, {DOCUMENT_INPUT_SELECTORS[1]}, {DOCUMENT_INPUT_SELECTORS[2]}, {', '.join(DOCUMENT_MENU_SELECTORS)}"),
                  }};
                }}
                """
            )
            if isinstance(dom_summary, dict):
                summary.update(dom_summary)
        except Exception as exc:
            summary["dom_summary_error"] = str(exc)

        try:
            active_fingerprint = getattr(sender, "_active_chat_fingerprint", lambda: {})()
            if isinstance(active_fingerprint, dict) and active_fingerprint:
                summary["active_chat_fingerprint"] = active_fingerprint
        except Exception as exc:
            summary["active_chat_fingerprint_error"] = str(exc)

    recovery_ladder = _default_recovery_ladder(getattr(sender, "chat_title", ""), batch_root)
    summary["recovery_ladder"] = recovery_ladder

    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    context_path.write_text(
        json.dumps(
            {
                "failure_code": failure_code,
                "detail": detail,
                "pdf_filename": pdf_filename or "",
                "manifest_path": str(manifest_path or ""),
                "batch_root": str(batch_root or ""),
                "diagnostics_dir": str(diagnostics_dir),
                "browser_mode": str(getattr(sender, "browser_mode", "") or ""),
                "profile_name": str(getattr(sender, "profile_name", "") or ""),
                "profile_directory": str(getattr(sender, "profile_directory", "") or ""),
                "cdp_endpoint": str(getattr(sender, "cdp_endpoint", "") or ""),
                "ui_invalidated": bool(getattr(sender, "_ui_invalidated", False)),
                "ui_invalidation_reason": str(getattr(sender, "_ui_invalidation_reason", "") or ""),
                "document_send_inflight": bool(getattr(sender, "_document_send_inflight", False)),
                "document_send_filename": str(getattr(sender, "_document_send_filename", "") or ""),
                "recovery_ladder": recovery_ladder,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    return {
        "diagnostics_dir": str(diagnostics_dir),
        "screenshot_path": str(screenshot_path) if screenshot_path.exists() else "",
        "html_path": str(html_path) if html_path.exists() else "",
        "dom_summary_path": str(summary_path),
        "recovery_ladder": recovery_ladder,
    }


def verify_send_batch_preflight(
    today_folder: Path,
    source_mode: str = SOURCE_AUTO,
    *,
    allow_unsure_resume: bool = False,
    expected_target_date: Optional[date] = None,
    allow_stale_batch: bool = False,
) -> Dict[str, Any]:
    issues: List[Dict[str, Any]] = []
    try:
        manifest = load_send_batch_manifest(today_folder, source_mode=source_mode)
    except Exception as exc:
        return {
            "ok": False,
            "issues": [{"code": "manifest_unavailable", "detail": str(exc)}],
        }

    computed_hash = _manifest_batch_hash(list(manifest.get("entries") or []))
    manifest_batch_hash = str(manifest.get("batch_hash") or "")
    if _looks_like_sha256(manifest_batch_hash) and computed_hash != manifest_batch_hash:
        issues.append(
            {
                "code": "batch_hash_mismatch",
                "detail": f"manifest={manifest_batch_hash} computed={computed_hash}",
            }
        )

    issues.extend(_validate_manifest_order_consistency(manifest))

    manifest_target_raw = str(manifest.get("target_date") or "").strip()
    manifest_target_date: Optional[date] = None
    if manifest_target_raw:
        try:
            manifest_target_date = date.fromisoformat(manifest_target_raw)
        except ValueError:
            issues.append(
                {
                    "code": "target_date_invalid",
                    "detail": manifest_target_raw,
                }
            )
    elif expected_target_date is not None and not allow_stale_batch:
        issues.append(
            {
                "code": "target_date_missing",
                "detail": "manifest target_date is empty",
            }
        )

    if (
        expected_target_date is not None
        and manifest_target_date is not None
        and manifest_target_date != expected_target_date
        and not allow_stale_batch
    ):
        issues.append(
            {
                "code": "target_date_mismatch",
                "detail": (
                    f"manifest={manifest_target_date.isoformat()} "
                    f"expected={expected_target_date.isoformat()}"
                ),
            }
        )

    overdue_order_ids = set(manifest.get("overdue_order_ids") or [])
    send_order_ids = set(manifest.get("send_order_ids") or [])
    if not send_order_ids:
        for entry in manifest.get("entries") or []:
            send_order_ids.update(entry.get("order_ids") or [])
    missing_overdue = sorted(overdue_order_ids - send_order_ids)
    if missing_overdue:
        issues.append(
            {
                "code": "overdue_missing_from_send",
                "detail": ",".join(missing_overdue),
            }
        )

    if not bool(manifest.get("terminal_orders_excluded")):
        issues.append(
            {
                "code": "terminal_pollution_check_failed",
                "detail": "terminal_orders_excluded=false",
            }
        )

    ledger_path = Path(manifest["batch_root"]) / SEND_LEDGER_FILE
    ledger = load_send_ledger(ledger_path, manifest)
    save_send_ledger(ledger_path, ledger)
    if str(ledger.get("batch_hash") or "") not in {"", str(manifest.get("batch_hash") or "")}:
        issues.append(
            {
                "code": "ledger_batch_hash_mismatch",
                "detail": f"ledger={ledger.get('batch_hash')} manifest={manifest.get('batch_hash')}",
            }
        )

    for pdf_key, entry in ledger.get("entries", {}).items():
        state = str(entry.get("state") or "pending")
        if state not in LEDGER_STATES:
            issues.append(
                {
                    "code": "ledger_invalid_state",
                    "detail": f"{pdf_key}:{state}",
                }
            )
        elif state in {"opened", "clicked"}:
            issues.append(
                {
                    "code": "ledger_in_progress_state",
                    "detail": f"{pdf_key}:{state}",
                }
            )
        elif state == "unsure" and not allow_unsure_resume:
            issues.append(
                {
                    "code": "ledger_unsure_resume_blocked",
                    "detail": pdf_key,
                }
            )

    return {
        "ok": not issues,
        "issues": issues,
        "manifest_path": manifest["manifest_path"],
        "batch_root": manifest["batch_root"],
        "batch_hash": manifest.get("batch_hash", ""),
        "target_date": manifest_target_date.isoformat() if manifest_target_date else manifest_target_raw,
        "expected_target_date": expected_target_date.isoformat() if expected_target_date else None,
        "send_pdf_count": int(manifest.get("counts", {}).get("pdfs", 0) or 0),
        "send_order_count": int(manifest.get("counts", {}).get("orders", 0) or 0),
    }


def run_sender_smoke_check(
    *,
    today_folder: Path,
    chat_title: str,
    bundle_source: str,
    chrome_user_data_dir: Path,
    chrome_profile_directory: str,
    chrome_profile_name: Optional[str] = DEFAULT_CHROME_PROFILE_NAME,
    cdp_endpoint: str = DEFAULT_CDP_ENDPOINT,
    browser_mode: str = DEFAULT_BROWSER_MODE,
    blocked_chat_titles: Iterable[str] = BLOCKED_CHAT_TITLES_DEFAULT,
    expected_target_date: Optional[date] = None,
    allow_stale_batch: bool = False,
    verbose: bool = False,
) -> Dict[str, Any]:
    preflight = verify_send_batch_preflight(
        today_folder,
        source_mode=bundle_source,
        expected_target_date=expected_target_date,
        allow_stale_batch=allow_stale_batch,
    )
    if not preflight.get("ok"):
        return preflight

    batch_root = Path(str(preflight.get("batch_root") or "")) if preflight.get("batch_root") else None
    manifest_path = Path(str(preflight.get("manifest_path") or "")) if preflight.get("manifest_path") else None

    if not check_playwright():
        return {
            "ok": False,
            "issues": [{"code": "playwright_unavailable", "detail": "Playwright is not installed"}],
            "manifest_path": str(manifest_path or ""),
            "batch_root": str(batch_root or ""),
            "batch_hash": preflight.get("batch_hash", ""),
            "target_date": preflight.get("target_date"),
            "recovery_ladder": _default_recovery_ladder(chat_title, batch_root),
        }

    sender = WhatsAppSender(
        chat_title=chat_title,
        user_data_dir=Path(chrome_user_data_dir),
        profile_directory=chrome_profile_directory,
        profile_name=chrome_profile_name,
        cdp_endpoint=cdp_endpoint,
        browser_mode=browser_mode,
        blocked_chat_titles=blocked_chat_titles,
        action_timeout_ms=ACTION_TIMEOUT_MS,
        verbose=verbose,
    )
    try:
        with sender:
            sender.assert_document_send_ready()
            return {
                "ok": True,
                "issues": [],
                "manifest_path": str(manifest_path or ""),
                "batch_root": str(batch_root or ""),
                "batch_hash": preflight.get("batch_hash", ""),
                "target_date": preflight.get("target_date"),
                "active_chat_title": sender._active_chat_title(),
                "recovery_ladder": _default_recovery_ladder(chat_title, batch_root),
            }
    except Exception as exc:
        diagnostics = capture_sender_failure_diagnostics(
            sender,
            today_folder=today_folder,
            failure_code="SMOKE_CHECK_FAILED",
            batch_root=batch_root,
            manifest_path=manifest_path,
            pdf_filename=None,
            detail=str(exc),
        )
        return {
            "ok": False,
            "issues": [{"code": "smoke_check_failed", "detail": str(exc)}],
            "manifest_path": str(manifest_path or ""),
            "batch_root": str(batch_root or ""),
            "batch_hash": preflight.get("batch_hash", ""),
            "target_date": preflight.get("target_date"),
            "diagnostics_dir": diagnostics.get("diagnostics_dir", ""),
            "recovery_ladder": diagnostics.get("recovery_ladder", []),
        }


# =============================================================================
# PDF COLLECTION
# =============================================================================


def _collect_store_folders(scan_root: Path) -> List[Path]:
    """Collect store folders under a specific root."""
    if not scan_root.exists():
        return []

    def collect_from(base: Path) -> List[Path]:
        found: List[Path] = []
        for item in base.iterdir():
            if item.is_dir() and not item.name.startswith("."):
                if any(item.glob("manifest_*.csv")):
                    found.append(item)
        return found

    partitions = [scan_root / "TODAY", scan_root / "OVERDUE"]
    if any(p.exists() for p in partitions):
        folders: List[Path] = []
        for partition in partitions:
            if partition.exists():
                folders.extend(collect_from(partition))
    else:
        folders = collect_from(scan_root)

    return sorted(folders, key=lambda x: x.name)


def _has_store_folders(scan_root: Path) -> bool:
    return bool(_collect_store_folders(scan_root))


def _has_send_batch_manifest(scan_root: Path) -> bool:
    if not scan_root.exists():
        return False
    if (scan_root / SEND_BATCH_MANIFEST_FILE).exists():
        return True
    return any(item.is_dir() and (item / SEND_BATCH_MANIFEST_FILE).exists() for item in scan_root.iterdir())


def resolve_send_root(today_folder: Path, source_mode: str = SOURCE_AUTO) -> Path:
    """Resolve which bundle root to use under Today/."""
    merged_root = today_folder / "MERGED"
    merged_send_root = merged_root / MERGED_SEND_ROOT_NAME
    per_store_root = today_folder / "PER_STORE"

    if source_mode == SOURCE_MERGED:
        return merged_send_root
    if source_mode == SOURCE_PER_STORE:
        return per_store_root
    if source_mode == SOURCE_LEGACY:
        return today_folder

    for candidate in (merged_send_root, merged_root, per_store_root, today_folder):
        if _has_store_folders(candidate) or _has_send_batch_manifest(candidate):
            return candidate
    return today_folder


def find_store_folders(today_folder: Path, source_mode: str = SOURCE_AUTO) -> List[Path]:
    """Find all store folders in Today directory for selected source mode."""
    scan_root = resolve_send_root(today_folder, source_mode=source_mode)
    return _collect_store_folders(scan_root)


def _store_label_from_folder_name(folder_name: str) -> str:
    match = re.match(r"^\d{2}\.\d{2}\.\d{2}_(.+?)_qnt\d+$", folder_name)
    if match:
        return match.group(1)
    return folder_name


def collect_pdfs_from_category(store_folder: Path, category: str) -> List[Path]:
    """Collect PDFs from a specific category folder."""
    category_path = store_folder / category
    if not category_path.exists():
        return []
    return sorted(
        category_path.rglob("*.pdf"),
        key=lambda x: (
            str(x.parent).lower(),
            x.name.lower(),
        ),
    )


def _build_manifest_output_index(
    store_folder: Path,
) -> tuple[Dict[str, Dict[str, Any]], Dict[str, List[Dict[str, Any]]]]:
    """
    Build lookup maps from manifest output paths to row metadata.

    Returns:
      - exact output path map: "NORMAL_singles/file.pdf" -> row
      - basename map: "file.pdf" -> [rows...]
    """
    exact_map: Dict[str, Dict[str, Any]] = {}
    basename_map: Dict[str, List[Dict[str, Any]]] = defaultdict(list)

    for manifest_path in sorted(store_folder.glob("manifest_*.csv")):
        with manifest_path.open("r", encoding="utf-8", newline="") as f:
            reader = csv.DictReader(f)
            for row in reader:
                output_raw = str(row.get("output") or "").strip()
                if not output_raw:
                    continue
                output_norm = output_raw.replace("\\", "/").lstrip("./")
                row_meta: Dict[str, Any] = {
                    "sku_key": str(row.get("sku_key") or "").strip(),
                    "sku_id": str(row.get("sku_id") or "").strip(),
                    "store": str(row.get("store") or "").strip(),
                    "order_ids": _split_order_ids(str(row.get("order_id") or "")),
                }
                exact_map[output_norm] = row_meta
                basename_map[Path(output_norm).name].append(row_meta)

    return exact_map, basename_map


def collect_all_pdfs(
    today_folder: Path,
    source_mode: str = SOURCE_AUTO,
    order_store_map: Optional[Dict[str, str]] = None,
) -> List[Dict[str, Any]]:
    """
    Collect all PDFs in correct sending order.

    Returns list of dicts with:
    - path: Path to PDF
    - store: Store folder name
    - category: Category (SPECIAL_multi_line, etc.)
    - filename: Just the filename
    """
    all_pdfs: List[Dict[str, Any]] = []
    order_store_map = dict(order_store_map or {})
    source_root = resolve_send_root(today_folder, source_mode=source_mode)
    store_folders = _collect_store_folders(source_root)

    for store_folder in store_folders:
        output_exact_map, output_basename_map = _build_manifest_output_index(store_folder)
        try:
            batch_label = str(store_folder.relative_to(source_root)).replace("\\", "/")
        except Exception:
            batch_label = store_folder.name
        for category in PDF_CATEGORIES:
            for pdf_path in collect_pdfs_from_category(store_folder, category):
                rel_store_path = str(pdf_path.relative_to(store_folder)).replace("\\", "/")
                row_meta: Optional[Dict[str, Any]] = output_exact_map.get(rel_store_path)
                if row_meta is None:
                    by_name = output_basename_map.get(pdf_path.name, [])
                    if len(by_name) == 1:
                        row_meta = by_name[0]
                    else:
                        row_meta = {}

                item_core = _extract_item_core(pdf_path.name)
                family_key = _family_key(item_core)
                sku_key = str(row_meta.get("sku_key") or "").strip() or family_key
                order_ids = list(row_meta.get("order_ids") or [])
                row_store = str(row_meta.get("store") or "").strip()
                fallback_store = _store_label_from_folder_name(store_folder.name)
                order_counts_by_store = _derive_order_store_counts(
                    order_ids=order_ids,
                    row_store=row_store,
                    fallback_store=fallback_store,
                    order_store_map=order_store_map,
                )

                all_pdfs.append(
                    {
                        "path": pdf_path,
                        "store": store_folder.name,
                        "store_label": _store_label_from_folder_name(store_folder.name),
                        "batch_label": batch_label,
                        "category": category,
                        "filename": pdf_path.name,
                        "item_core": item_core,
                        "size_token": _extract_size_token(pdf_path.name),
                        "size_rank": _size_rank(_extract_size_token(pdf_path.name)),
                        "family_key": family_key,
                        "sku_key": sku_key,
                        "sku_id": str(row_meta.get("sku_id") or "").strip(),
                        "order_ids": order_ids,
                        "order_counts_by_store": order_counts_by_store,
                        "relative": _relative_for_tracker(pdf_path, today_folder),
                    }
                )

    return all_pdfs


def _relative_for_tracker(pdf_path: Path, today_folder: Path) -> str:
    """
    Build a stable tracker key.

    Prefer paths relative to Today root so PER_STORE files are namespaced as
    PER_STORE/... and do not collide with legacy layout entries.
    """
    try:
        return str(pdf_path.relative_to(today_folder))
    except Exception:
        return pdf_path.name


def _recover_missing_pdf_path(
    pdf_entry: Dict[str, Any],
    today_folder: Path,
) -> Optional[Path]:
    """
    Recover a moved PDF by filename inside the same store/category tree.

    This handles real-world cases where operators manually re-folder bundles
    (e.g., "New Folder With Items") after build, without changing filenames.
    """
    target_name = str(pdf_entry.get("filename") or "").strip()
    if not target_name:
        return None

    original_path = pdf_entry.get("path")
    if not isinstance(original_path, Path):
        return None

    # Find store root by folder name token captured at collection time.
    store_name = str(pdf_entry.get("store") or "").strip()
    store_root: Optional[Path] = None
    if store_name:
        for parent in original_path.parents:
            if parent.name == store_name:
                store_root = parent
                break
    if store_root is None:
        return None

    category = str(pdf_entry.get("category") or "").strip()
    category_root = store_root / category if category else store_root
    if not category_root.exists():
        category_root = store_root

    matches = sorted(category_root.rglob(target_name), key=lambda p: str(p).lower())
    if not matches:
        return None

    recovered = matches[0]
    pdf_entry["path"] = recovered
    pdf_entry["relative"] = _relative_for_tracker(recovered, today_folder)
    return recovered


def filter_unsent_pdfs(all_pdfs: List[Dict[str, Any]], sent_list: List[str]) -> List[Dict[str, Any]]:
    """Filter out PDFs that have already been sent."""
    sent_set = set(sent_list)
    return [pdf for pdf in all_pdfs if pdf["relative"] not in sent_set]


def _extract_size_token(filename: str) -> str:
    stem = Path(filename).stem.upper()

    trailing = TRAILING_SIZE_RE.search(stem)
    if trailing:
        return trailing.group(1).upper()

    messy = MESSY_MULTI_SIZE_RE.search(stem)
    if messy:
        return messy.group(1).upper()

    any_match = SIZE_TOKEN_RE.search(stem)
    if any_match:
        return any_match.group(1).upper()

    return ""


def _size_rank(size_token: str) -> int:
    if not size_token:
        return 999
    return SIZE_ORDER.get(size_token.upper(), 999)


def _extract_item_core(filename: str) -> str:
    stem = Path(filename).stem
    stem = re.sub(r"^Местовая-\d+\)_", "", stem, flags=re.IGNORECASE)
    stem = re.sub(r"^Местовая-\d+_", "", stem, flags=re.IGNORECASE)
    stem = TRAILING_SIZE_RE.sub("", stem)
    return stem


def _family_key(item_core: str) -> str:
    text = re.sub(r"[^0-9A-Za-zА-Яа-я]+", "_", item_core).strip("_").upper()
    if not text:
        return "UNKNOWN"

    tokens = [tok for tok in re.split(r"[_\-]+", text) if tok]
    cleaned: List[str] = []
    for tok in tokens:
        if tok in COLOR_TOKENS or tok in NOISE_TOKENS or tok == "PRO":
            continue
        cleaned.append(tok)

    if not cleaned:
        return text
    return "_".join(cleaned[:3])


def _order_category_entries_by_sku(entries: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Order one category by SKU blocks.

    Once a SKU block starts, all its sizes are sent contiguously in rising
    size order before moving to next SKU.
    """
    grouped: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    first_seen: Dict[str, int] = {}
    for idx, entry in enumerate(entries):
        sku_key = str(entry.get("sku_key") or entry.get("family_key") or "UNKNOWN")
        grouped[sku_key].append(entry)
        if sku_key not in first_seen:
            first_seen[sku_key] = idx

    for sku_key, items in grouped.items():
        items.sort(
            key=lambda x: (
                int(x.get("size_rank", 999)),
                str(x.get("size_token", "")).upper(),
                str(x.get("filename", "")).lower(),
            )
        )

    ordered_skus = sorted(grouped.keys(), key=lambda key: (first_seen[key], key))
    result: List[Dict[str, Any]] = []
    for sku_key in ordered_skus:
        result.extend(grouped[sku_key])
    return result


def _category_rank(category: str) -> int:
    """
    Stable category priority for sending sequence.

    Rule: all multi-line and multi-qty bundles are sent before normal singles.
    """
    raw = str(category or "").strip()
    if not raw:
        return 99

    normalized = re.sub(r"[^a-z0-9]+", "_", raw.lower()).strip("_")
    if "multi_line" in normalized:
        return 0
    if "multi_qty" in normalized:
        return 1
    if "normal" in normalized and "single" in normalized:
        return 2
    return CATEGORY_PRIORITY.get(raw, 99)


def order_pdfs_for_sending(pdfs: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Order PDFs by category, then by contiguous SKU blocks with rising sizes.
    """
    if pdfs:
        parsed_sequences: List[tuple[int, Dict[str, Any]]] = []
        all_have_sequence = True
        for pdf in pdfs:
            raw_sequence = pdf.get("send_sequence")
            try:
                sequence = int(raw_sequence)
                if sequence <= 0:
                    raise ValueError
            except (TypeError, ValueError):
                all_have_sequence = False
                break
            parsed_sequences.append((sequence, pdf))
        if all_have_sequence and len({sequence for sequence, _ in parsed_sequences}) == len(pdfs):
            return [pdf for sequence, pdf in sorted(parsed_sequences, key=lambda item: item[0])]

    category_groups: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for pdf in pdfs:
        category_groups[str(pdf.get("category", ""))].append(pdf)

    ordered: List[Dict[str, Any]] = []
    for category in sorted(category_groups.keys(), key=lambda c: (_category_rank(c), c.lower())):
        ordered.extend(_order_category_entries_by_sku(category_groups[category]))

    return ordered


def _split_order_ids(raw_order_ids: str) -> List[str]:
    return [token.strip() for token in (raw_order_ids or "").split(";") if token.strip()]


def _normalize_store_label(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return "UNKNOWN"
    key = re.sub(r"[^A-Za-z0-9]+", "", text).upper()
    if key == "STOREB":
        return "STORE-B"
    if key in STORE_DISPLAY:
        return STORE_DISPLAY[key]
    return text


def _selection_cache_path(today_folder: Path) -> Path:
    return (today_folder.parent.parent / "ActiveOrders" / "waybills" / "_waybill_selection_orders.json").resolve()


def load_order_store_map_from_selection(today_folder: Path) -> Dict[str, str]:
    """
    Load order_id -> display store mapping from waybill selection cache.
    """
    path = _selection_cache_path(today_folder)
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    stores = payload.get("stores")
    if not isinstance(stores, dict):
        return {}

    order_store: Dict[str, str] = {}
    for store_code, order_ids in stores.items():
        store_name = _normalize_store_label(store_code)
        if not isinstance(order_ids, list):
            continue
        for oid in order_ids:
            order_id = str(oid or "").strip()
            if order_id:
                order_store[order_id] = store_name
    return order_store


def _derive_order_store_counts(
    order_ids: List[str],
    row_store: str,
    fallback_store: str,
    order_store_map: Dict[str, str],
) -> Dict[str, int]:
    counts: Dict[str, int] = Counter()
    for order_id in order_ids:
        store = order_store_map.get(order_id)
        if not store:
            if row_store and row_store.upper() != "MERGED":
                store = _normalize_store_label(row_store)
            elif fallback_store and fallback_store.upper() != "MERGED":
                store = _normalize_store_label(fallback_store)
            else:
                store = "UNKNOWN"
        counts[_normalize_store_label(store)] += 1
    return dict(counts)


def collect_store_order_bundle_stats(
    store_folders: List[Path],
    order_store_map: Optional[Dict[str, str]] = None,
) -> Dict[str, Dict[str, int]]:
    """
    Build per-store order target/ready stats from manifests + selection cache.

    Returns:
      {
        "StoreName": {"orders_target": int, "orders_ready": int}
      }
    """
    order_store_map = dict(order_store_map or {})
    target_sets: Dict[str, set[str]] = defaultdict(set)
    for order_id, store in order_store_map.items():
        target_sets[_normalize_store_label(store)].add(str(order_id))

    ready_sets: Dict[str, set[str]] = defaultdict(set)
    for store_folder in store_folders:
        fallback_store = _store_label_from_folder_name(store_folder.name)
        manifest_files = sorted(store_folder.glob("manifest_*.csv"))
        for manifest_path in manifest_files:
            with manifest_path.open("r", encoding="utf-8", newline="") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    row_store = str(row.get("store") or "").strip()
                    order_ids = _split_order_ids(str(row.get("order_id") or ""))
                    if not order_ids:
                        continue
                    order_counts = _derive_order_store_counts(
                        order_ids=order_ids,
                        row_store=row_store,
                        fallback_store=fallback_store,
                        order_store_map=order_store_map,
                    )
                    for store_name in order_counts:
                        for order_id in order_ids:
                            mapped = order_store_map.get(order_id)
                            if mapped:
                                if _normalize_store_label(mapped) == store_name:
                                    ready_sets[store_name].add(order_id)
                            elif store_name != "UNKNOWN":
                                ready_sets[store_name].add(order_id)

    stores = sorted(set(target_sets.keys()) | set(ready_sets.keys()))
    finalized: Dict[str, Dict[str, int]] = {}
    for store_name in stores:
        finalized[store_name] = {
            "orders_target": len(target_sets.get(store_name, set())),
            "orders_ready": len(ready_sets.get(store_name, set())),
        }
    return finalized


def _build_ascii_table(headers: List[str], rows: List[List[str]]) -> str:
    all_rows = [headers] + rows
    widths = [max(len(str(row[col])) for row in all_rows) for col in range(len(headers))]

    def fmt_row(cells: List[str]) -> str:
        padded = [str(cells[idx]).ljust(widths[idx]) for idx in range(len(widths))]
        return "| " + " | ".join(padded) + " |"

    sep = "+" + "+".join("-" * (width + 2) for width in widths) + "+"

    lines = [sep, fmt_row(headers), sep]
    for row in rows:
        lines.append(fmt_row(row))
    lines.append(sep)
    return "\n".join(lines)


def format_pre_send_status_table(
    store_stats: Dict[str, Dict[str, int]],
    bundles_target: int,
) -> str:
    ordered_stores = sorted(store_stats)
    rows: List[List[str]] = []
    total_orders_target = 0
    total_orders_ready = 0

    for store in ordered_stores:
        orders_target = int(store_stats[store].get("orders_target", 0))
        orders_ready = int(store_stats[store].get("orders_ready", 0))
        total_orders_target += orders_target
        total_orders_ready += orders_ready
        rows.append([store, str(orders_target), str(orders_ready)])

    rows.append(["TOTAL", str(total_orders_target), str(total_orders_ready)])
    table = _build_ascii_table(["STORE", "Orders Target", "Orders Ready"], rows)
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    bundles_line = f"Bundles Target: {bundles_target}"
    return f"{timestamp}\n{table}\n{bundles_line}"


def format_post_send_status_table(
    store_stats: Dict[str, Dict[str, int]],
    sent_orders_by_store: Dict[str, int],
    bundles_target: int,
    bundles_sent: int,
) -> str:
    ordered_stores = sorted(store_stats)
    rows: List[List[str]] = []
    total_orders_target = 0
    total_orders_ready = 0
    total_orders_sent = 0

    for store in ordered_stores:
        orders_target = int(store_stats[store].get("orders_target", 0))
        orders_ready = int(store_stats[store].get("orders_ready", 0))
        orders_sent = int(sent_orders_by_store.get(store, 0))

        total_orders_target += orders_target
        total_orders_ready += orders_ready
        total_orders_sent += orders_sent
        rows.append([store, str(orders_target), str(orders_ready), str(orders_sent)])

    rows.append(["TOTAL", str(total_orders_target), str(total_orders_ready), str(total_orders_sent)])
    table = _build_ascii_table(["STORE", "Orders Target", "Orders Ready", "Orders Sent"], rows)
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    bundles_line = f"Bundles: target={bundles_target}, sent={bundles_sent}"
    return f"{timestamp}\n{table}\n{bundles_line}"


# =============================================================================
# WHATSAPP WEB AUTOMATION
# =============================================================================


def check_playwright() -> bool:
    """Check if Playwright is available."""
    try:
        import playwright  # noqa: F401

        return True
    except Exception:
        return False


def _normalize_chat_key(name: str) -> str:
    return " ".join((name or "").split()).strip().casefold()


def _normalize_identity_value(value: Any) -> str:
    return " ".join(str(value or "").split()).strip().casefold()


def load_whatsapp_chat_identity_map(identity_path: Path) -> Dict[str, Any]:
    if identity_path.exists():
        try:
            payload = json.loads(identity_path.read_text(encoding="utf-8"))
            if isinstance(payload, dict) and isinstance(payload.get("chats"), dict):
                return payload
        except Exception:
            pass
    return {"version": 1, "chats": {}}


def load_whatsapp_chat_identity(identity_path: Path, chat_title: str) -> Optional[Dict[str, Any]]:
    payload = load_whatsapp_chat_identity_map(identity_path)
    raw = payload.get("chats", {}).get(_normalize_chat_key(chat_title))
    return dict(raw) if isinstance(raw, dict) else None


def save_whatsapp_chat_identity(identity_path: Path, chat_title: str, fingerprint: Dict[str, Any]) -> None:
    payload = load_whatsapp_chat_identity_map(identity_path)
    chats = payload.setdefault("chats", {})
    chats[_normalize_chat_key(chat_title)] = dict(fingerprint)
    payload["version"] = 1
    identity_path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = identity_path.with_suffix(".tmp")
    temp_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    temp_path.replace(identity_path)


def _copy_profile_to_temp(user_data_dir: Path, profile_directory: str, verbose: bool = False) -> Path:
    """Copy the browser profile into a temp dir to avoid singleton lock conflicts."""
    profile_src = user_data_dir / profile_directory
    if not profile_src.exists():
        raise FileNotFoundError(f"Chrome profile not found: {profile_src}")

    tmp_root = Path(tempfile.mkdtemp(prefix="whatsapp-profile-"))

    local_state = user_data_dir / "Local State"
    if local_state.exists():
        shutil.copy2(local_state, tmp_root / "Local State")

    def ignore_cache_dirs(_dir: str, names: Iterable[str]) -> List[str]:
        # Keep WhatsApp session state such as Service Worker data; skip only rebuildable caches.
        skip = {
            "Cache",
            "Code Cache",
            "GPUCache",
            "DawnCache",
            "GrShaderCache",
            "ShaderCache",
            "VideoDecodeStats",
            "blob_storage",
            "Blob Storage",
        }
        return [n for n in names if n in skip]

    shutil.copytree(profile_src, tmp_root / profile_directory, dirs_exist_ok=True, ignore=ignore_cache_dirs)

    for root in (tmp_root, tmp_root / profile_directory):
        for lock_name in ("SingletonLock", "SingletonCookie", "SingletonSocket"):
            lock_path = root / lock_name
            if lock_path.exists():
                lock_path.unlink(missing_ok=True)

    if verbose:
        print(f"Using temp browser profile: {tmp_root}")

    return tmp_root


def _should_copy_browser_profile_to_temp(user_data_dir: Path) -> bool:
    try:
        return COPY_PROFILE_TO_TEMP and Path(user_data_dir).expanduser().resolve() == DEFAULT_CHROME_USER_DATA_DIR.resolve()
    except Exception:
        return COPY_PROFILE_TO_TEMP and str(user_data_dir) == str(DEFAULT_CHROME_USER_DATA_DIR)


def _load_chrome_local_state(user_data_dir: Path) -> Dict[str, Any]:
    local_state_path = Path(user_data_dir) / "Local State"
    if not local_state_path.exists():
        raise FileNotFoundError(f"Chrome Local State not found: {local_state_path}")
    try:
        payload = json.loads(local_state_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Chrome Local State is not valid JSON: {local_state_path}") from exc
    if not isinstance(payload, dict):
        raise RuntimeError(f"Chrome Local State has unexpected structure: {local_state_path}")
    return payload


def _profile_info_cache(user_data_dir: Path) -> Dict[str, Dict[str, Any]]:
    payload = _load_chrome_local_state(user_data_dir)
    cache = payload.get("profile", {}).get("info_cache", {})
    if not isinstance(cache, dict):
        raise RuntimeError("Chrome profile info_cache is missing from Local State")
    return {
        str(key): value
        for key, value in cache.items()
        if isinstance(value, dict)
    }


def resolve_chrome_profile_directory(
    user_data_dir: Path,
    *,
    profile_name: Optional[str] = None,
    profile_directory: Optional[str] = None,
) -> str:
    resolved_directory = str(profile_directory or "").strip()
    resolved_name = str(profile_name or "").strip()
    if not resolved_name:
        if not resolved_directory:
            raise RuntimeError("Chrome profile name or directory is required")
        return resolved_directory

    info_cache = _profile_info_cache(user_data_dir)
    matches = [
        directory
        for directory, meta in info_cache.items()
        if _normalize_chat_key(str(meta.get("name") or "")) == _normalize_chat_key(resolved_name)
    ]
    if not matches:
        available = ", ".join(
            sorted(
                {
                    str(meta.get("name") or directory)
                    for directory, meta in info_cache.items()
                }
            )
        )
        raise RuntimeError(
            f"Chrome profile named {resolved_name!r} was not found under {user_data_dir}. "
            f"Available profiles: {available}"
        )
    chosen_directory = sorted(matches)[0]
    if resolved_directory and resolved_directory != chosen_directory:
        raise RuntimeError(
            f"Chrome profile mismatch: name {resolved_name!r} resolves to {chosen_directory!r}, "
            f"not {resolved_directory!r}"
        )
    return chosen_directory


def resolve_chrome_profile_name(user_data_dir: Path, profile_directory: str) -> str:
    info_cache = _profile_info_cache(user_data_dir)
    meta = info_cache.get(str(profile_directory).strip())
    if not meta:
        return str(profile_directory).strip()
    return str(meta.get("name") or profile_directory).strip()


def _fetch_cdp_json(endpoint: str, path: str) -> Any:
    resolved_endpoint = _resolve_live_cdp_endpoint(endpoint)
    target_url = f"{str(resolved_endpoint).rstrip('/')}/{path.lstrip('/')}"
    try:
        with urllib.request.urlopen(target_url, timeout=3) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.URLError as exc:
        raise RuntimeError(f"Chrome DevTools endpoint is unavailable at {resolved_endpoint}.") from exc
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Chrome DevTools endpoint returned invalid JSON: {target_url}") from exc


def _candidate_cdp_endpoints(endpoint: str) -> List[str]:
    normalized = str(endpoint or "").strip() or DEFAULT_CDP_ENDPOINT
    candidates: List[str] = []
    for candidate in (normalized, DEFAULT_CDP_ENDPOINT, DEFAULT_CDP_ENDPOINT_IPV6):
        if candidate and candidate not in candidates:
            candidates.append(candidate)

    try:
        parsed = urllib.parse.urlparse(normalized)
    except Exception:
        return candidates

    if parsed.scheme in {"http", "https"} and parsed.port == 9222:
        hostname = parsed.hostname or ""
        if hostname == "127.0.0.1" and DEFAULT_CDP_ENDPOINT_IPV6 not in candidates:
            candidates.append(DEFAULT_CDP_ENDPOINT_IPV6)
        if hostname in {"::1", "[::1]"} and DEFAULT_CDP_ENDPOINT not in candidates:
            candidates.append(DEFAULT_CDP_ENDPOINT)
    return candidates


def _fetch_cdp_json_once(endpoint: str, path: str) -> Any:
    target_url = f"{str(endpoint).rstrip('/')}/{path.lstrip('/')}"
    with urllib.request.urlopen(target_url, timeout=3) as response:
        return json.loads(response.read().decode("utf-8"))


def _resolve_live_cdp_endpoint(endpoint: str) -> str:
    helper_hint = ""
    if WHATSAPP_DEBUG_CHROME_HELPER.exists():
        helper_hint = f" Use {WHATSAPP_DEBUG_CHROME_HELPER} to launch the Universal debug session."

    last_error: Optional[Exception] = None
    for candidate in _candidate_cdp_endpoints(endpoint):
        try:
            _fetch_cdp_json_once(candidate, "/json/version")
            return candidate
        except Exception as exc:
            last_error = exc
            continue

    raise RuntimeError(
        f"Chrome DevTools endpoint is unavailable at {endpoint}. "
        "Start Chrome with remote debugging enabled and keep the Universal profile open."
        f"{helper_hint}"
    ) from last_error


@dataclass
class _SendContext:
    page: Any
    context: Optional[Any]
    browser: Optional[Any]
    playwright: Any
    temp_profile_root: Optional[Path]
    close_context_on_shutdown: bool = True


class WhatsAppSender:
    """WhatsApp Web document sender with strict active-chat safety gate."""

    def __init__(
        self,
        chat_title: str,
        user_data_dir: Path,
        profile_directory: str = DEFAULT_CHROME_PROFILE_DIR,
        blocked_chat_titles: Iterable[str] = BLOCKED_CHAT_TITLES_DEFAULT,
        profile_name: Optional[str] = DEFAULT_CHROME_PROFILE_NAME,
        cdp_endpoint: str = DEFAULT_CDP_ENDPOINT,
        browser_mode: str = DEFAULT_BROWSER_MODE,
        chat_identity_file: Path = DEFAULT_WHATSAPP_CHAT_IDENTITY_FILE,
        action_timeout_ms: int = ACTION_TIMEOUT_MS,
        verbose: bool = False,
    ) -> None:
        self.chat_title = chat_title
        self.chat_key = _normalize_chat_key(chat_title)
        self.user_data_dir = Path(user_data_dir)
        self.requested_profile_name = str(profile_name or "").strip()
        self.profile_name = self.requested_profile_name
        self.profile_directory = str(profile_directory or "").strip()
        self.cdp_endpoint = str(cdp_endpoint or "").strip() or DEFAULT_CDP_ENDPOINT
        if browser_mode not in BROWSER_MODE_CHOICES:
            raise ValueError(f"Unsupported browser_mode {browser_mode!r}")
        self.browser_mode = browser_mode
        self.chat_identity_file = Path(chat_identity_file)
        self.expected_chat_identity = load_whatsapp_chat_identity(self.chat_identity_file, chat_title)
        self.blocked_chat_keys = {_normalize_chat_key(x) for x in blocked_chat_titles if x}
        self.action_timeout_ms = action_timeout_ms
        self.verbose = verbose
        self._ctx: Optional[_SendContext] = None
        self._last_outgoing_snapshot: List[str] = []
        self._ui_invalidated = False
        self._ui_invalidation_reason = ""
        self._document_send_inflight = False
        self._document_send_filename = ""
        self._page_watchers_registered = False

        if not self.chat_title:
            raise ValueError("chat_title is required")
        if self.chat_key in self.blocked_chat_keys:
            raise ValueError(f"Target chat '{self.chat_title}' is blocked by safety policy")

    @property
    def page(self) -> Any:
        if not self._ctx:
            raise RuntimeError("WhatsApp sender not started")
        return self._ctx.page

    def _log(self, message: str) -> None:
        if self.verbose:
            print(message)

    def _resolve_browser_profile(self) -> None:
        if self.requested_profile_name:
            self.profile_directory = resolve_chrome_profile_directory(
                self.user_data_dir,
                profile_name=self.requested_profile_name,
                profile_directory=self.profile_directory or None,
            )
            self.profile_name = self.requested_profile_name
            return
        if not self.profile_directory:
            self.profile_directory = DEFAULT_CHROME_PROFILE_DIR
        try:
            self.profile_name = resolve_chrome_profile_name(self.user_data_dir, self.profile_directory)
        except Exception:
            self.profile_name = self.profile_directory

    def _mark_ui_invalidated(self, reason: str) -> None:
        message = str(reason or "").strip() or "page invalidated"
        if self._ui_invalidated and self._ui_invalidation_reason == message:
            return
        self._ui_invalidated = True
        self._ui_invalidation_reason = message
        self._log(f"WhatsApp UI invalidated: {message}")

    def _clear_ui_invalidated(self) -> None:
        self._ui_invalidated = False
        self._ui_invalidation_reason = ""

    def _reset_document_send_tracking(self) -> None:
        self._document_send_inflight = False
        self._document_send_filename = ""

    def mark_document_send_clicked(self, expected_filename: str) -> None:
        self._document_send_inflight = True
        self._document_send_filename = str(expected_filename or "").strip()
        self._clear_ui_invalidated()

    def _raise_if_document_send_invalidated(self, expected_filename: str) -> None:
        if not self._document_send_inflight or not self._ui_invalidated:
            return
        detail = self._ui_invalidation_reason or "WhatsApp page reloaded or lost the active chat"
        raise RuntimeError(
            f"reload detected after send click for {expected_filename}: {detail}"
        )

    def _register_page_watchers(self, page: Any) -> None:
        if self._page_watchers_registered or not hasattr(page, "on"):
            return

        def _handle_main_frame_navigation(frame: Any) -> None:
            try:
                if frame != page.main_frame:
                    return
            except Exception:
                return
            frame_url = ""
            try:
                frame_url = str(getattr(frame, "url", "") or page.url or "")
            except Exception:
                frame_url = ""
            self._mark_ui_invalidated(f"main frame navigated to {frame_url or '<unknown>'}")

        def _handle_page_load() -> None:
            try:
                page_url = str(page.url or "")
            except Exception:
                page_url = ""
            self._mark_ui_invalidated(f"page loaded at {page_url or '<unknown>'}")

        page.on("framenavigated", _handle_main_frame_navigation)
        page.on("load", _handle_page_load)
        self._page_watchers_registered = True

    def _select_existing_whatsapp_page(self, browser: Any) -> Any:
        candidates: List[Any] = []
        for context in list(getattr(browser, "contexts", []) or []):
            for page in list(getattr(context, "pages", []) or []):
                try:
                    url = str(page.url or "")
                except Exception:
                    url = ""
                if url.startswith(WHATSAPP_WEB_URL):
                    candidates.append(page)
        if candidates:
            return candidates[-1]

        tabs_payload = _fetch_cdp_json(self.cdp_endpoint, "/json/list")
        tab_urls = []
        if isinstance(tabs_payload, list):
            tab_urls = [
                str(item.get("url") or "").strip()
                for item in tabs_payload
                if isinstance(item, dict)
            ]
        raise RuntimeError(
            "No existing WhatsApp Web tab was found in the attached Chrome session. "
            f"Open {WHATSAPP_WEB_URL} in the Chrome profile {self.profile_name!r} "
            f"({self.profile_directory}) before running the sender. "
            f"Observed CDP tabs: {tab_urls[:8]}"
        )

    def _start_with_attached_chrome(self, playwright: Any) -> _SendContext:
        resolved_cdp_endpoint = _resolve_live_cdp_endpoint(self.cdp_endpoint)
        if resolved_cdp_endpoint != self.cdp_endpoint:
            self._log(f"Resolved Chrome DevTools endpoint: {self.cdp_endpoint} -> {resolved_cdp_endpoint}")
            self.cdp_endpoint = resolved_cdp_endpoint
        _fetch_cdp_json(self.cdp_endpoint, "/json/version")
        self._log(f"Attaching to existing Chrome via CDP: {self.cdp_endpoint}")
        browser = playwright.chromium.connect_over_cdp(self.cdp_endpoint)
        page = self._select_existing_whatsapp_page(browser)
        try:
            page.bring_to_front()
        except Exception:
            pass
        page.set_default_timeout(self.action_timeout_ms)
        self._register_page_watchers(page)
        return _SendContext(
            page=page,
            context=getattr(page, "context", None),
            browser=browser,
            playwright=playwright,
            temp_profile_root=None,
            close_context_on_shutdown=False,
        )

    def _start_with_temp_profile(self, playwright: Any) -> _SendContext:
        temp_root: Optional[Path] = None
        if _should_copy_browser_profile_to_temp(self.user_data_dir):
            temp_root = _copy_profile_to_temp(self.user_data_dir, self.profile_directory, verbose=self.verbose)
            launch_user_data_dir = temp_root
        else:
            launch_user_data_dir = self.user_data_dir

        self._log("Launching Chrome persistent context...")
        context = playwright.chromium.launch_persistent_context(
            user_data_dir=str(launch_user_data_dir),
            channel="chrome",
            headless=False,
            no_viewport=True,
            args=[
                f"--profile-directory={self.profile_directory}",
                "--start-maximized",
            ],
        )
        page = context.new_page()
        page.set_default_timeout(self.action_timeout_ms)
        self._log(f"Navigating to {WHATSAPP_WEB_URL} ...")
        page.goto(WHATSAPP_WEB_URL, wait_until="domcontentloaded")
        self._register_page_watchers(page)
        self._clear_ui_invalidated()
        return _SendContext(
            page=page,
            context=context,
            browser=None,
            playwright=playwright,
            temp_profile_root=temp_root,
            close_context_on_shutdown=True,
        )

    def start(self) -> None:
        from playwright.sync_api import sync_playwright

        self._resolve_browser_profile()
        playwright = sync_playwright().start()
        self._page_watchers_registered = False
        self._clear_ui_invalidated()
        self._reset_document_send_tracking()
        if self.browser_mode == BROWSER_MODE_ATTACH:
            self._ctx = self._start_with_attached_chrome(playwright)
        else:
            self._ctx = self._start_with_temp_profile(playwright)

        self._log("Waiting for WhatsApp session readiness...")
        self._assert_session_ready()
        self._log("Waiting for chat list...")
        self._wait_for_chat_list_ready()
        self._log(f"Opening target chat: {self.chat_title}")
        self.open_chat(self.chat_title)
        self._clear_ui_invalidated()

    def close(self) -> None:
        if not self._ctx:
            return

        temp_root = self._ctx.temp_profile_root
        try:
            if self._ctx.close_context_on_shutdown and self._ctx.context is not None:
                self._ctx.context.close()
        finally:
            try:
                self._ctx.playwright.stop()
            finally:
                if temp_root:
                    shutil.rmtree(temp_root, ignore_errors=True)
        self._ctx = None
        self._page_watchers_registered = False
        self._clear_ui_invalidated()
        self._reset_document_send_tracking()

    def __enter__(self) -> "WhatsAppSender":
        self.start()
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()

    def _wait_for_chat_list_ready(self) -> None:
        self.page.locator("div[aria-label='Chat list']").wait_for(timeout=CHAT_OPEN_TIMEOUT_MS)
        self._resolve_sidebar_search(timeout_ms=min(CHAT_OPEN_TIMEOUT_MS, 8_000), required=False)

    def _assert_session_ready(self, timeout_ms: int = CHAT_OPEN_TIMEOUT_MS) -> None:
        if not hasattr(self.page, "locator"):
            return

        qr_selectors = [
            "[data-testid='qrcode']",
            "canvas[aria-label*='QR']",
            "div[aria-label='Scan this QR code to link a device!']",
        ]
        login_selectors = [
            "button[aria-label='Log in']",
            "button[aria-label='Войти']",
        ]
        deadline = time.time() + (timeout_ms / 1000.0)
        while time.time() < deadline:
            for selector in qr_selectors:
                if self.page.locator(selector).count() > 0:
                    raise RuntimeError(
                        "WhatsApp session is not ready: QR/login screen is visible"
                    )
            for selector in login_selectors:
                if self.page.locator(selector).count() > 0:
                    raise RuntimeError(
                        "WhatsApp session is not ready: login prompt is visible"
                    )
            if self.page.locator("div[aria-label='Chat list']").count() > 0:
                return
            self.page.wait_for_timeout(250)

        raise RuntimeError("WhatsApp session is not ready: chat list did not load")

    @staticmethod
    def _is_navigation_context_error(exc: Exception) -> bool:
        msg = str(exc or "").lower()
        return (
            "execution context was destroyed" in msg
            or "most likely because of a navigation" in msg
            or "cannot find context with specified id" in msg
            or "target closed" in msg
        )

    def _composer_candidates(self) -> List[Any]:
        return [
            self.page.locator("footer div[contenteditable='true'][role='textbox']").first,
            self.page.locator("footer div[contenteditable='true'][data-lexical-editor='true']").first,
            self.page.locator("div[contenteditable='true'][aria-label='Type a message']").first,
            self.page.locator("div[contenteditable='true'][aria-label^='Type to group']").first,
            self.page.locator("footer div[contenteditable='true']").first,
        ]

    def _sidebar_search_candidates(self) -> List[Any]:
        return [
            self.page.locator("input[role='textbox'][aria-label='Search or start a new chat']").first,
            self.page.locator("input[placeholder='Search or start a new chat']").first,
            self.page.locator("div[aria-label='Search input textbox']").first,
            self.page.locator(
                "div[role='textbox'][contenteditable='true'][aria-label='Search input textbox']"
            ).first,
            self.page.locator(
                "div[role='textbox'][contenteditable='true'][aria-label*='Search']"
            ).first,
            self.page.locator("div[contenteditable='true'][role='textbox'][data-tab='3']").first,
            self.page.locator("div[contenteditable='true'][data-tab='3']").first,
        ]

    def _resolve_sidebar_search(
        self,
        timeout_ms: int,
        required: bool = True,
    ) -> Optional[Any]:
        deadline = time.time() + (timeout_ms / 1000.0)
        last_error: Optional[Exception] = None

        while time.time() < deadline:
            for locator in self._sidebar_search_candidates():
                try:
                    if locator.count() <= 0:
                        continue
                    candidate = locator.first
                    candidate.wait_for(timeout=1200)
                    return candidate
                except Exception as exc:
                    last_error = exc
                    continue
            self.page.wait_for_timeout(250)

        if required:
            raise RuntimeError(f"Sidebar search not ready: {last_error}")
        return None

    def _resolve_composer(
        self,
        timeout_ms: int,
        required: bool = True,
    ) -> Optional[Any]:
        deadline = time.time() + (timeout_ms / 1000.0)
        last_error: Optional[Exception] = None

        while time.time() < deadline:
            for locator in self._composer_candidates():
                try:
                    if locator.count() <= 0:
                        continue
                    candidate = locator.first
                    candidate.wait_for(timeout=1200)
                    return candidate
                except Exception as exc:
                    last_error = exc
                    continue
            self.page.wait_for_timeout(250)

        if required:
            raise RuntimeError(f"Composer not ready in target chat: {last_error}")
        return None

    def _active_chat_title(self) -> str:
        last_error: Optional[Exception] = None
        for _ in range(3):
            try:
                title = self.page.evaluate(
                    """
                    () => {
                      const clean = (value) => (value || '').trim();
                      const skip = new Set([
                        '',
                        'click here for group info',
                        'profile details',
                        'wa-wordmark-refreshed',
                        'whatsapp',
                        'call',
                      ]);

                      // Preferred: selected row in chat list.
                      const selectedRow = document.querySelector(\"div[aria-label='Chat list'] [aria-selected='true']\");
                      if (selectedRow) {
                        const rowName = selectedRow.querySelector(\"span[title], span[dir='auto']\");
                        if (rowName) {
                          const text = clean(rowName.getAttribute('title') || rowName.textContent || '');
                          if (!skip.has(text.toLowerCase())) return text;
                        }
                      }

                      // Fallback: right panel header title. Scan from last header because left nav header is first.
                      const headers = Array.from(document.querySelectorAll('header')).reverse();
                      for (const header of headers) {
                        const nodes = [
                          ...header.querySelectorAll(\"span[dir='auto']\"),
                          ...header.querySelectorAll('span[title]'),
                          ...header.querySelectorAll('h1, h2'),
                        ];
                        for (const node of nodes) {
                          const text = clean((node.getAttribute && node.getAttribute('title')) || node.textContent || '');
                          if (skip.has(text.toLowerCase())) continue;
                          if (text.length >= 2) return text;
                        }
                      }
                      return '';
                    }
                    """
                )
                return str(title or "").strip()
            except Exception as exc:
                last_error = exc
                if not self._is_navigation_context_error(exc):
                    raise
                self.page.wait_for_timeout(500)
        if last_error and self._is_navigation_context_error(last_error):
            return ""
        if last_error:
            raise last_error
        return ""

    def _active_chat_fingerprint(self) -> Dict[str, str]:
        try:
            payload = self.page.evaluate(
                """
                () => {
                  const clean = (value) => String(value || '').replace(/\\s+/g, ' ').trim();
                  const skip = new Set([
                    '',
                    'click here for group info',
                    'profile details',
                    'wa-wordmark-refreshed',
                    'whatsapp',
                    'call',
                  ]);
                  const selectedRow = document.querySelector("div[aria-label='Chat list'] [aria-selected='true']");
                  const rowTitleNode = selectedRow?.querySelector("span[title], span[dir='auto']");
                  const rowTitle = clean(rowTitleNode?.getAttribute?.('title') || rowTitleNode?.textContent || '');
                  const rowLabel = clean(selectedRow?.getAttribute?.('aria-label') || '');
                  const rowText = clean(selectedRow?.textContent || '');
                  const rowDataId = clean(selectedRow?.getAttribute?.('data-id') || selectedRow?.dataset?.id || '');
                  const rowTestId = clean(selectedRow?.getAttribute?.('data-testid') || '');
                  const rowDomId = clean(selectedRow?.id || '');

                  let headerTitle = '';
                  let headerSubtitle = '';
                  const headers = Array.from(document.querySelectorAll('header')).reverse();
                  for (const header of headers) {
                    const nodes = [
                      ...header.querySelectorAll("span[dir='auto']"),
                      ...header.querySelectorAll('span[title]'),
                      ...header.querySelectorAll('div[dir=\"auto\"]'),
                      ...header.querySelectorAll('h1, h2'),
                    ];
                    const texts = [];
                    for (const node of nodes) {
                      const text = clean((node.getAttribute && node.getAttribute('title')) || node.textContent || '');
                      if (!text) continue;
                      if (skip.has(text.toLowerCase())) continue;
                      if (!texts.includes(text)) texts.push(text);
                    }
                    if (!texts.length) continue;
                    headerTitle = texts[0] || '';
                    headerSubtitle = texts.find((text) => text !== headerTitle) || '';
                    if (headerTitle) break;
                  }

                  return {
                    chat_title: clean(rowTitle || headerTitle),
                    selected_row_title: rowTitle,
                    selected_row_label: rowLabel,
                    selected_row_text: rowText,
                    selected_row_data_id: rowDataId,
                    selected_row_testid: rowTestId,
                    selected_row_dom_id: rowDomId,
                    header_title: headerTitle,
                    header_subtitle: headerSubtitle,
                  };
                }
                """
            )
        except Exception as exc:
            if self._is_navigation_context_error(exc):
                return {}
            raise
        return dict(payload) if isinstance(payload, dict) else {}

    def _assert_chat_identity_matches(self, actual: Dict[str, Any]) -> None:
        expected = dict(self.expected_chat_identity or {})
        if not expected:
            return

        expected_title = _normalize_chat_key(expected.get("chat_title") or self.chat_title)
        actual_title = _normalize_chat_key(actual.get("chat_title") or actual.get("header_title") or "")
        if expected_title and actual_title != expected_title:
            raise RuntimeError(
                f"Safety gate blocked send: chat identity fingerprint mismatch "
                f"(title {actual.get('chat_title')!r} != {expected.get('chat_title')!r})"
            )

        checked = 0
        for field, label in (
            ("selected_row_data_id", "selected-row data-id"),
            ("selected_row_testid", "selected-row test id"),
            ("selected_row_dom_id", "selected-row dom id"),
            ("header_subtitle", "header subtitle"),
        ):
            expected_value = _normalize_identity_value(expected.get(field))
            if not expected_value:
                continue
            actual_value = _normalize_identity_value(actual.get(field))
            checked += 1
            if actual_value != expected_value:
                raise RuntimeError(
                    f"Safety gate blocked send: chat identity fingerprint mismatch "
                    f"for {label} ({actual.get(field)!r} != {expected.get(field)!r})"
                )

        if checked <= 0:
            raise RuntimeError(
                "Safety gate blocked send: expected chat identity fingerprint is incomplete"
            )

    def bind_active_chat_identity_if_missing(self) -> Dict[str, Any]:
        if self.expected_chat_identity:
            return dict(self.expected_chat_identity)

        actual = self._active_chat_fingerprint()
        if not actual:
            raise RuntimeError("Could not capture active WhatsApp chat fingerprint")

        fingerprint: Dict[str, Any] = {
            "chat_title": actual.get("chat_title") or self.chat_title,
        }
        for field in ("selected_row_data_id", "selected_row_testid", "selected_row_dom_id", "header_subtitle"):
            value = str(actual.get(field) or "").strip()
            if value:
                fingerprint[field] = value
                break

        if len(fingerprint) <= 1:
            raise RuntimeError(
                "Could not derive a stable WhatsApp chat identity fingerprint from the active chat"
            )

        save_whatsapp_chat_identity(self.chat_identity_file, self.chat_title, fingerprint)
        self.expected_chat_identity = dict(fingerprint)
        self._log(
            f"Bound WhatsApp chat identity for {self.chat_title}: "
            f"{', '.join(sorted(k for k in fingerprint.keys() if k != 'chat_title'))}"
        )
        return dict(fingerprint)

    def _chat_home_screen_visible(self) -> bool:
        try:
            return bool(
                self.page.evaluate(
                    """
                    () => {
                      const text = String(document.body?.innerText || '');
                      return text.includes('Download WhatsApp for Mac')
                        && text.includes('Send document')
                        && text.includes('Add contact');
                    }
                    """
                )
            )
        except Exception:
            return False

    def _attach_button_available(self) -> bool:
        for selector in ATTACH_BUTTON_SELECTORS:
            try:
                if self.page.locator(selector).count() > 0:
                    return True
            except Exception:
                continue
        return False

    def _assert_active_target_chat(self) -> None:
        deadline = time.time() + 12.0
        last_title = ""
        last_identity: Dict[str, Any] = {}
        while time.time() < deadline:
            if self._chat_home_screen_visible():
                raise RuntimeError("WhatsApp home screen is visible; no chat is currently open")
            active_identity = self._active_chat_fingerprint()
            active_title = str(active_identity.get("chat_title") or self._active_chat_title() or "").strip()
            active_key = _normalize_chat_key(active_title)
            last_title = active_title
            last_identity = active_identity

            if not active_key:
                self.page.wait_for_timeout(250)
                continue

            if active_key in self.blocked_chat_keys:
                raise RuntimeError(
                    f"Safety gate blocked send: active chat is forbidden ({active_title!r})"
                )

            if active_key == self.chat_key:
                if self._chat_home_screen_visible():
                    raise RuntimeError(
                        "WhatsApp home screen is visible; target chat did not open"
                    )
                self._assert_chat_identity_matches(active_identity)
                return

            self.page.wait_for_timeout(250)

        if not _normalize_chat_key(last_title):
            raise RuntimeError("Could not determine active WhatsApp chat title")
        try:
            self._assert_chat_identity_matches(last_identity)
        except RuntimeError as exc:
            raise RuntimeError(str(exc)) from exc
        raise RuntimeError(
            f"Safety gate blocked send: active chat mismatch ({last_title!r} != {self.chat_title!r})"
        )

    def _dismiss_blocking_dialog_if_present(self) -> bool:
        page = self.page
        if not hasattr(page, "locator"):
            return False
        dialog_locator = page.locator("div[role='dialog'][aria-modal='true']")
        try:
            if dialog_locator.count() <= 0:
                return False
        except Exception:
            return False

        close_selectors = [
            "div[role='dialog'][aria-modal='true'] button[aria-label='Close']",
            "div[role='dialog'][aria-modal='true'] button[aria-label='Закрыть']",
            "div[role='dialog'][aria-modal='true'] button[aria-label='Cancel']",
            "div[role='dialog'][aria-modal='true'] button[aria-label='Отмена']",
        ]
        for selector in close_selectors:
            try:
                locator = page.locator(selector)
                if locator.count() <= 0:
                    continue
                locator.first.click(timeout=1500, force=True)
                page.wait_for_timeout(300)
                return True
            except Exception:
                continue
        try:
            keyboard = getattr(page, "keyboard", None)
            if keyboard is None or not hasattr(keyboard, "press"):
                return False
            keyboard.press("Escape")
            page.wait_for_timeout(300)
            return True
        except Exception:
            return False

    def _recover_target_chat_after_ui_drift(self) -> None:
        last_error: Optional[Exception] = None
        for _ in range(3):
            try:
                self._log("Recovering target chat after WhatsApp UI drift...")
                self._dismiss_blocking_dialog_if_present()
                self._assert_session_ready(timeout_ms=min(self.action_timeout_ms, CHAT_OPEN_TIMEOUT_MS))
                self._wait_for_chat_list_ready()
                self.open_chat(self.chat_title)
                self._clear_ui_invalidated()
                self._log(f"Target chat reopened: {self.chat_title}")
                return
            except Exception as exc:
                last_error = exc
                self.page.wait_for_timeout(700)
        if last_error:
            raise last_error
        raise RuntimeError("Could not recover target WhatsApp chat")

    def _ensure_target_chat_ready(
        self,
        *,
        require_composer: bool = True,
        require_attach_button: bool = False,
        timeout_ms: Optional[int] = None,
    ) -> None:
        resolved_timeout = timeout_ms if timeout_ms is not None else max(self.action_timeout_ms, 12_000)
        last_error: Optional[Exception] = None
        for attempt in range(1, 3):
            try:
                if self._ui_invalidated and not self._document_send_inflight:
                    self._recover_target_chat_after_ui_drift()
                self._assert_active_target_chat()
                self._resolve_composer(timeout_ms=resolved_timeout, required=require_composer)
                if require_attach_button and not self._attach_button_available():
                    raise RuntimeError("Attach button is not visible in target chat")
                self._clear_ui_invalidated()
                return
            except Exception as exc:
                last_error = exc
                if attempt >= 2:
                    break
                self._recover_target_chat_after_ui_drift()
        if last_error:
            raise last_error

    def _try_click_candidate(self, candidates: Iterable[Any], timeout_ms: int = 3500) -> bool:
        deadline = time.time() + (timeout_ms / 1000.0)
        while time.time() < deadline:
            for candidate in candidates:
                if candidate.count() <= 0:
                    continue
                candidate.first.click()
                self.page.wait_for_timeout(900)
                if _normalize_chat_key(self._active_chat_title()) != self.chat_key:
                    continue
                try:
                    self._assert_chat_identity_matches(self._active_chat_fingerprint())
                except RuntimeError:
                    if self.expected_chat_identity:
                        continue
                return True
            self.page.wait_for_timeout(250)
        return False

    def open_chat(self, chat_title: str) -> None:
        if _normalize_chat_key(chat_title) in self.blocked_chat_keys:
            raise RuntimeError(f"Requested chat is blocked: {chat_title!r}")

        if _normalize_chat_key(self._active_chat_title()) == self.chat_key:
            try:
                self._assert_chat_identity_matches(self._active_chat_fingerprint())
                self._resolve_composer(timeout_ms=min(self.action_timeout_ms, 20_000), required=False)
                return
            except RuntimeError:
                if not self.expected_chat_identity:
                    self._resolve_composer(timeout_ms=min(self.action_timeout_ms, 20_000), required=False)
                    return

        # First attempt: direct click from visible chat list (fastest + safest).
        chat_list = self.page.locator("div[aria-label='Chat list']")
        direct_candidates = [
            chat_list.locator(f"span[title='{chat_title}']"),
            chat_list.locator("span[dir='auto']", has_text=chat_title),
            chat_list.get_by_text(chat_title, exact=True),
        ]
        if not self._try_click_candidate(
            direct_candidates,
            timeout_ms=min(self.action_timeout_ms, 12_000),
        ):
            # Search box can lag behind the chat list on fresh WhatsApp loads.
            search = self._resolve_sidebar_search(
                timeout_ms=min(self.action_timeout_ms, 20_000),
                required=False,
            )
            if search is not None:
                search.click()
                search.fill("")
                search.fill(chat_title)
                self.page.wait_for_timeout(1000)

                if not self._try_click_candidate(
                    [
                        chat_list.locator(f"span[title='{chat_title}']"),
                        chat_list.locator("span[dir='auto']", has_text=chat_title),
                        self.page.locator(f"span[title='{chat_title}']"),
                        self.page.get_by_text(chat_title, exact=True),
                    ],
                    timeout_ms=min(self.action_timeout_ms, 12_000),
                ):
                    self.page.keyboard.press("Enter")
                    self.page.wait_for_timeout(1200)
            else:
                if not self._try_click_candidate(
                    [
                        chat_list.locator(f"span[title='{chat_title}']"),
                        chat_list.locator("span[dir='auto']", has_text=chat_title),
                        self.page.locator(f"span[title='{chat_title}']"),
                        self.page.get_by_text(chat_title, exact=True),
                    ],
                    timeout_ms=min(self.action_timeout_ms, 12_000),
                ):
                    raise RuntimeError("Sidebar search not ready and target chat was not clickable from chat list")

        self._assert_active_target_chat()
        self._resolve_composer(timeout_ms=min(self.action_timeout_ms, 20_000), required=False)
        self._clear_ui_invalidated()

        if self.verbose:
            print(f"WhatsApp active chat: {self._active_chat_title()}")

    def _safe_click_selectors(
        self,
        selectors: Iterable[str],
        label: str,
        timeout_ms: Optional[int] = None,
    ) -> None:
        timeout_ms = timeout_ms if timeout_ms is not None else self.action_timeout_ms
        deadline = time.time() + (timeout_ms / 1000.0)
        errors: List[str] = []

        while time.time() < deadline:
            for selector in selectors:
                locator = self.page.locator(selector)
                if locator.count() <= 0:
                    continue
                target = locator.first
                try:
                    target.click(timeout=1500)
                    return
                except Exception as exc:
                    errors.append(f"{selector} normal: {exc}")

                try:
                    target.click(timeout=1500, force=True)
                    return
                except Exception as exc:
                    errors.append(f"{selector} force: {exc}")

                try:
                    target.evaluate("el => el.click()")
                    return
                except Exception as exc:
                    errors.append(f"{selector} js: {exc}")

                # Direct page-level query avoids locator re-resolution races when
                # WhatsApp re-renders the composer/attachment controls mid-click.
                try:
                    clicked = self.page.evaluate(
                        """
                        (sel) => {
                          const el = document.querySelector(sel);
                          if (!el) return false;
                          el.click();
                          return true;
                        }
                        """,
                        selector,
                    )
                    if clicked:
                        return
                except Exception as exc:
                    errors.append(f"{selector} page-js: {exc}")

            self.page.wait_for_timeout(250)

        err_tail = " | ".join(errors[-6:]) if errors else "no matching elements"
        raise RuntimeError(f"Failed to click {label}. Errors: {err_tail}")

    def _choose_file_via_document_menu(self, pdf_path: Path) -> None:
        from playwright.sync_api import TimeoutError as PWTimeoutError

        if self._try_set_document_input_files(pdf_path):
            return

        last_error: Optional[Exception] = None
        for _ in range(3):
            try:
                with self.page.expect_file_chooser(timeout=7000) as chooser_info:
                    self._safe_click_selectors(
                        DOCUMENT_MENU_SELECTORS,
                        "document menu item",
                        timeout_ms=5000,
                    )
                chooser = chooser_info.value
                chooser.set_files(str(pdf_path))
                return
            except PWTimeoutError as exc:
                last_error = exc
                if self._try_set_document_input_files(pdf_path):
                    return
                self.page.wait_for_timeout(500)
            except Exception as exc:
                last_error = exc
                if self._try_set_document_input_files(pdf_path):
                    return
                self.page.wait_for_timeout(500)

        if last_error:
            raise last_error
        raise RuntimeError("Failed to open document file chooser")

    def _try_set_document_input_files(self, pdf_path: Path) -> bool:
        for selector in DOCUMENT_INPUT_SELECTORS:
            locator = self.page.locator(selector)
            if locator.count() <= 0:
                continue
            try:
                locator.first.set_input_files(str(pdf_path), timeout=1500)
                return True
            except Exception:
                continue
        return False

    def _document_controls_available(self) -> bool:
        for selector in [*DOCUMENT_INPUT_SELECTORS, *DOCUMENT_MENU_SELECTORS]:
            try:
                if self.page.locator(selector).count() > 0:
                    return True
            except Exception:
                continue
        return False

    def _wait_for_document_controls(self, timeout_ms: int = 4000) -> bool:
        deadline = time.time() + (timeout_ms / 1000.0)
        while time.time() < deadline:
            if self._document_controls_available():
                return True
            self.page.wait_for_timeout(200)
        return False

    def _global_share_modal_visible(self) -> bool:
        try:
            return bool(
                self.page.evaluate(
                    """
                    () => {
                      const bodyText = String(document.body?.innerText || '');
                      const hasSelectChats =
                        bodyText.includes('Select chats') || bodyText.includes('Выберите чаты');
                      const hasSearchNameOrNumber =
                        bodyText.includes('Search name or number') || bodyText.includes('Поиск имени или номера');
                      const dialogTitle = document.querySelector("[role='dialog'] h2");
                      const titleText = String(dialogTitle?.textContent || '').trim();
                      return (
                        titleText === 'Select chats' ||
                        titleText === 'Выберите чаты' ||
                        (hasSelectChats && hasSearchNameOrNumber)
                      );
                    }
                    """
                )
            )
        except Exception:
            return False

    def assert_document_send_ready(self) -> None:
        last_error: Optional[Exception] = None
        for attempt in range(1, 3):
            try:
                if self.verbose:
                    print(f"Checking document controls (attempt {attempt}/2)...")
                self._ensure_target_chat_ready(
                    require_composer=True,
                    require_attach_button=True,
                )
                if self._document_controls_available():
                    if self.verbose:
                        print("Document controls already visible.")
                    return
                self._safe_click_selectors(
                    ATTACH_BUTTON_SELECTORS,
                    "attach button",
                    timeout_ms=8_000,
                )
                if not self._wait_for_document_controls(timeout_ms=4_000):
                    raise RuntimeError("Document upload controls not ready in target chat")
                try:
                    self.page.keyboard.press("Escape")
                except Exception:
                    pass
                self._ensure_target_chat_ready(
                    require_composer=True,
                    require_attach_button=True,
                )
                if self.verbose:
                    print("Document controls verified.")
                return
            except Exception as exc:
                last_error = exc
                if attempt >= 2:
                    break
                self._recover_target_chat_after_ui_drift()
                self.page.wait_for_timeout(500)
        if last_error:
            raise last_error
        raise RuntimeError("Document upload controls not ready in target chat")

    def _outgoing_message_count(self) -> int:
        try:
            value = self.page.evaluate(
                """
                () => {
                  const normalize = (raw) =>
                    String(raw || "")
                      .replace(/\\s+/g, " ")
                      .trim()
                      .toLowerCase();
                  const outgoing = Array.from(document.querySelectorAll("div.message-out"));
                  return {
                    count: outgoing.length,
                    tail: outgoing
                      .slice(-8)
                      .map((node) => normalize(node.innerText || node.textContent || ""))
                      .filter(Boolean),
                  };
                }
                """
            )
            if isinstance(value, dict):
                self._last_outgoing_snapshot = [
                    self._normalize_outgoing_text(item)
                    for item in (value.get("tail") or [])
                    if self._normalize_outgoing_text(item)
                ]
                return int(value.get("count") or 0)
            self._last_outgoing_snapshot = []
            return int(value or 0)
        except Exception:
            self._last_outgoing_snapshot = []
            return 0

    @staticmethod
    def _normalize_outgoing_text(value: str) -> str:
        return " ".join(str(value or "").split()).strip().lower()

    def _wait_for_new_outgoing_message(self, previous_count: int, timeout_ms: int) -> None:
        last_error: Optional[Exception] = None
        for attempt in range(1, 4):
            try:
                self.page.wait_for_function(
                    """
                    (prev) => {
                      const count = document.querySelectorAll("div.message-out").length;
                      return count > prev;
                    }
                    """,
                    arg=previous_count,
                    timeout=timeout_ms,
                )
                return
            except Exception as exc:
                last_error = exc
                if not self._is_navigation_context_error(exc):
                    raise
                if attempt < 3:
                    self.page.wait_for_timeout(800)
                    continue
        # Soft fallback for transient navigation race: avoid hard crash mid-run.
        if last_error and self._is_navigation_context_error(last_error):
            self.page.wait_for_timeout(2000)
            return
        if last_error:
            raise last_error

    def _wait_for_text_message_bubble(self, text: str, timeout_ms: int) -> None:
        collapsed = self._normalize_outgoing_text(text)
        lines = [
            normalized
            for normalized in (
                self._normalize_outgoing_text(line)
                for line in str(text or "").splitlines()
            )
            if normalized
        ]
        self.page.wait_for_function(
            """
            (payload) => {
              const normalize = (value) =>
                String(value || "")
                  .replace(/\\s+/g, " ")
                  .trim()
                  .toLowerCase();
              const outgoing = Array.from(document.querySelectorAll("div.message-out")).slice(-12).reverse();
              return outgoing.some((node) => {
                const normalized = normalize(node.innerText || node.textContent || "");
                if (!normalized) return false;
                if (payload.collapsed && normalized.includes(payload.collapsed)) return true;
                if (payload.lines && payload.lines.length) {
                  return payload.lines.every((line) => normalized.includes(line));
                }
                return false;
              });
            }
            """,
            arg={"collapsed": collapsed, "lines": lines},
            timeout=timeout_ms,
        )

    def _wait_for_last_outgoing_settled(self, timeout_ms: int) -> None:
        """
        Wait until the latest outgoing message is no longer in "sending/uploading" state.

        This prevents closing the temporary browser profile before WhatsApp finishes
        syncing the just-sent message to server state.
        """
        last_error: Optional[Exception] = None
        for attempt in range(1, 4):
            try:
                self.page.wait_for_function(
                    """
                    () => {
                      const outgoing = document.querySelectorAll("div.message-out");
                      if (!outgoing.length) return false;
                      const last = outgoing[outgoing.length - 1];
                      if (!last) return false;

                      const pending = last.querySelector(
                        [
                          "span[data-icon='msg-time']",
                          "span[data-icon='status-clock']",
                          "[role='progressbar']",
                          "[aria-label*='sending']",
                          "[aria-label*='Sending']",
                          "[aria-label*='отправля']",
                          "[aria-label*='Отправля']"
                        ].join(",")
                      );
                      return !pending;
                    }
                    """,
                    timeout=timeout_ms,
                )
                return
            except Exception as exc:
                last_error = exc
                if not self._is_navigation_context_error(exc):
                    raise
                if attempt < 3:
                    self.page.wait_for_timeout(800)
                    continue
        if last_error and self._is_navigation_context_error(last_error):
            self.page.wait_for_timeout(2500)
            return
        if last_error:
            raise last_error

    def wait_for_outgoing_sync(self, timeout_ms: int = 90_000) -> None:
        self._wait_for_last_outgoing_settled(timeout_ms=timeout_ms)

    def confirm_text_message_sent(self, text: str, timeout_ms: int = 120_000) -> Dict[str, Any]:
        collapsed = self._normalize_outgoing_text(text)
        lines = [
            normalized
            for normalized in (
                self._normalize_outgoing_text(line)
                for line in str(text or "").splitlines()
            )
            if normalized
        ]
        payload = {"collapsed": collapsed, "lines": lines}
        self.page.wait_for_function(
            """
            (payload) => {
              const normalize = (value) =>
                String(value || "")
                  .replace(/\\s+/g, " ")
                  .trim()
                  .toLowerCase();
              const outgoing = Array.from(document.querySelectorAll("div.message-out")).slice(-12).reverse();
              const matched = outgoing.find((node) => {
                const normalized = normalize(node.innerText || node.textContent || "");
                if (!normalized) return false;
                if (payload.collapsed && normalized.includes(payload.collapsed)) return true;
                if (payload.lines && payload.lines.length) {
                  return payload.lines.every((line) => normalized.includes(line));
                }
                return false;
              });
              if (!matched) return false;
              const pending = matched.querySelector(
                [
                  "span[data-icon='msg-time']",
                  "span[data-icon='status-clock']",
                  "[role='progressbar']",
                  "[aria-label*='sending']",
                  "[aria-label*='Sending']",
                  "[aria-label*='отправля']",
                  "[aria-label*='Отправля']"
                ].join(",")
              );
              return !pending;
            }
            """,
            arg=payload,
            timeout=timeout_ms,
        )
        status = self.page.evaluate(
            """
            (payload) => {
              const normalize = (value) =>
                String(value || "")
                  .replace(/\\s+/g, " ")
                  .trim()
                  .toLowerCase();
              const outgoing = Array.from(document.querySelectorAll("div.message-out")).slice(-12).reverse();
              const matched = outgoing.find((node) => {
                const normalized = normalize(node.innerText || node.textContent || "");
                if (!normalized) return false;
                if (payload.collapsed && normalized.includes(payload.collapsed)) return true;
                if (payload.lines && payload.lines.length) {
                  return payload.lines.every((line) => normalized.includes(line));
                }
                return false;
              });
              if (!matched) {
                return {
                  present: false,
                  sent: false,
                  delivered: false,
                  delivery_state: "missing",
                  icons: [],
                  aria_labels: [],
                };
              }
              const iconNodes = Array.from(matched.querySelectorAll("span[data-icon]"));
              const icons = iconNodes
                .map((node) => String(node.getAttribute("data-icon") || "").trim())
                .filter(Boolean);
              const ariaLabels = Array.from(matched.querySelectorAll("[aria-label]"))
                .map((node) => String(node.getAttribute("aria-label") || "").replace(/\\s+/g, " ").trim())
                .filter(Boolean);
              const pending = matched.querySelector(
                [
                  "span[data-icon='msg-time']",
                  "span[data-icon='status-clock']",
                  "[role='progressbar']",
                  "[aria-label*='sending']",
                  "[aria-label*='Sending']",
                  "[aria-label*='отправля']",
                  "[aria-label*='Отправля']"
                ].join(",")
              );
              const delivered = matched.querySelector(
                [
                  "span[data-icon='msg-dblcheck']",
                  "span[data-icon='status-dblcheck']",
                  "span[data-icon*='dblcheck']",
                  "span[data-icon*='delivered']",
                  "span[data-icon*='read']",
                  "[aria-label*='Delivered']",
                  "[aria-label*='Read']",
                  "[aria-label*='Доставлено']",
                  "[aria-label*='Прочитано']"
                ].join(",")
              );
              const singleCheck = matched.querySelector(
                [
                  "span[data-icon='msg-check']",
                  "span[data-icon='status-check']"
                ].join(",")
              );
              const hasSentLabel = ariaLabels.some((label) => {
                const normalized = normalize(label);
                return normalized === "sent"
                  || normalized.includes(" sent ")
                  || normalized.includes("отправлено");
              });
              const sent = !pending && !!(delivered || singleCheck || hasSentLabel || matched);
              return {
                present: true,
                sent,
                delivered: !!delivered,
                delivery_state: delivered ? "delivered" : sent ? "sent" : "pending",
                icons,
                aria_labels: ariaLabels,
              };
            }
            """,
            payload,
        )
        self._assert_active_target_chat()
        if not isinstance(status, dict) or not status.get("sent"):
            raise RuntimeError(
                f"WhatsApp text message did not reach a stable sent state for {text!r}"
            )
        return dict(status)

    def confirm_text_message_delivered(self, text: str, timeout_ms: int = 120_000) -> None:
        status = self.confirm_text_message_sent(text, timeout_ms=timeout_ms)
        if status.get("delivered"):
            return
        raise RuntimeError(
            f"WhatsApp text message did not reach delivered state for {text!r}"
        )

    def _wait_for_document_bubble(self, expected_filename: str, timeout_ms: int) -> None:
        expected_name = expected_filename.strip()
        expected_stem = Path(expected_name).stem
        self.page.wait_for_function(
            """
            (payload) => {
              const normalize = (raw) =>
                String(raw || "")
                  .replace(/\\s+/g, " ")
                  .trim()
                  .toLowerCase();
              const seen = new Set((payload.seen || []).map((value) => normalize(value)));
              const outgoing = Array.from(document.querySelectorAll("div.message-out")).slice(-12);
              const candidates = [payload.filename, payload.stem].filter(Boolean).map((x) => x.toLowerCase());
              return outgoing.some((node) => {
                const text = normalize(node.innerText || node.textContent || '');
                if (!text || seen.has(text)) return false;
                return candidates.some((candidate) => candidate && text.includes(candidate));
              });
            }
            """,
            arg={
                "filename": expected_name,
                "stem": expected_stem,
                "seen": list(self._last_outgoing_snapshot),
            },
            timeout=timeout_ms,
        )

    def _wait_for_document_bubble_settled(self, expected_filename: str, timeout_ms: int) -> None:
        expected_name = expected_filename.strip()
        expected_stem = Path(expected_name).stem
        self.page.wait_for_function(
            """
            (payload) => {
              const normalize = (raw) =>
                String(raw || "")
                  .replace(/\\s+/g, " ")
                  .trim()
                  .toLowerCase();
              const outgoing = Array.from(document.querySelectorAll("div.message-out")).slice(-12).reverse();
              const seen = new Set((payload.seen || []).map((value) => normalize(value)));
              const candidates = [payload.filename, payload.stem].filter(Boolean).map((x) => x.toLowerCase());
              const matched = outgoing.find((node) => {
                const text = normalize(node.innerText || node.textContent || '');
                if (!text || seen.has(text)) return false;
                return candidates.some((candidate) => candidate && text.includes(candidate));
              });
              if (!matched) return false;
              const pending = matched.querySelector(
                [
                  "span[data-icon='msg-time']",
                  "span[data-icon='status-clock']",
                  "[role='progressbar']",
                  "[aria-label*='sending']",
                  "[aria-label*='Sending']",
                  "[aria-label*='отправля']",
                  "[aria-label*='Отправля']"
                ].join(",")
              );
              return !pending;
            }
            """,
            arg={
                "filename": expected_name,
                "stem": expected_stem,
                "seen": list(self._last_outgoing_snapshot),
            },
            timeout=timeout_ms,
        )

    def send_text_message(self, text: str) -> None:
        if not text.strip():
            return

        lines = text.splitlines()
        if not lines:
            return

        self._ensure_target_chat_ready(require_composer=True)
        composer = self._resolve_composer(
            timeout_ms=max(self.action_timeout_ms, 12_000),
            required=True,
        )
        if composer is None:
            raise RuntimeError("Composer not available")
        try:
            composer.click()
        except Exception:
            self._recover_target_chat_after_ui_drift()
            composer = self._resolve_composer(
                timeout_ms=max(self.action_timeout_ms, 12_000),
                required=True,
            )
            if composer is None:
                raise RuntimeError("Composer not available after chat recovery")
            composer.click()

        previous_outgoing = self._outgoing_message_count()
        try:
            composer.press("Control+A")
            composer.press("Backspace")
        except Exception:
            pass

        for idx, line in enumerate(lines):
            if line:
                self.page.keyboard.insert_text(line)
            if idx < len(lines) - 1:
                self.page.keyboard.press("Shift+Enter")

        self.page.keyboard.press("Enter")
        try:
            self._wait_for_text_message_bubble(
                text,
                timeout_ms=max(self.action_timeout_ms, TEXT_SETTLE_TIMEOUT_MS),
            )
            self._wait_for_last_outgoing_settled(
                timeout_ms=max(self.action_timeout_ms, TEXT_SETTLE_TIMEOUT_MS),
            )
            self._ensure_target_chat_ready(require_composer=False)
            return
        except Exception as exc:
            if not self._ui_invalidated and not self._is_navigation_context_error(exc):
                raise
            self._recover_target_chat_after_ui_drift()
            try:
                self._wait_for_new_outgoing_message(
                    previous_outgoing,
                    timeout_ms=max(self.action_timeout_ms, TEXT_SETTLE_TIMEOUT_MS),
                )
            except Exception:
                pass
            self._wait_for_text_message_bubble(
                text,
                timeout_ms=max(self.action_timeout_ms, TEXT_SETTLE_TIMEOUT_MS),
            )
            self._wait_for_last_outgoing_settled(
                timeout_ms=max(self.action_timeout_ms, TEXT_SETTLE_TIMEOUT_MS),
            )
            self._ensure_target_chat_ready(require_composer=False)

    def prepare_document(self, pdf_path: Path) -> None:
        if not pdf_path.exists():
            raise FileNotFoundError(f"PDF not found: {pdf_path}")

        last_error: Optional[Exception] = None
        for attempt in range(1, 3):
            try:
                self._ensure_target_chat_ready(
                    require_composer=True,
                    require_attach_button=True,
                )
                self._safe_click_selectors(
                    ATTACH_BUTTON_SELECTORS,
                    "attach button",
                    timeout_ms=8_000,
                )
                self._choose_file_via_document_menu(pdf_path)
                self.page.wait_for_timeout(300)
                if self._global_share_modal_visible():
                    raise RuntimeError(
                        "WhatsApp global share modal opened instead of target chat document preview"
                    )
                return
            except Exception as exc:
                last_error = exc
                if attempt >= 2:
                    break
                self._recover_target_chat_after_ui_drift()
                self.page.wait_for_timeout(500)
        if last_error:
            raise last_error

    def click_document_send(self) -> None:
        selectors = [
            "button[aria-label='Send']",
            "button[aria-label='Отправить']",
            "span[data-icon='wds-ic-send-filled']",
            "span[data-icon='send']",
        ]
        deadline = time.time() + 8.0
        last_error: Optional[Exception] = None
        while time.time() < deadline:
            for selector in selectors:
                locator = self.page.locator(selector)
                if locator.count() <= 0:
                    continue
                try:
                    locator.first.click(timeout=1200)
                    return
                except Exception as exc:
                    last_error = exc
            self.page.wait_for_timeout(200)
        raise RuntimeError(f"Failed to click send button once: {last_error}")

    def confirm_document_sent(
        self,
        expected_filename: str,
        previous_outgoing: Optional[int] = None,
    ) -> None:
        count_gate_error: Optional[Exception] = None
        try:
            self._raise_if_document_send_invalidated(expected_filename)
            if previous_outgoing is not None:
                try:
                    self._wait_for_new_outgoing_message(
                        previous_outgoing,
                        timeout_ms=max(self.action_timeout_ms, DOCUMENT_SETTLE_TIMEOUT_MS),
                    )
                except Exception as exc:
                    count_gate_error = exc
            self._raise_if_document_send_invalidated(expected_filename)
            self._wait_for_document_bubble(
                expected_filename,
                timeout_ms=max(self.action_timeout_ms, DOCUMENT_APPEAR_TIMEOUT_MS),
            )
            self._raise_if_document_send_invalidated(expected_filename)
            self._wait_for_document_bubble_settled(
                expected_filename,
                timeout_ms=max(self.action_timeout_ms, DOCUMENT_SETTLE_TIMEOUT_MS),
            )
            self._raise_if_document_send_invalidated(expected_filename)
            self._assert_active_target_chat()
            self._clear_ui_invalidated()
            self._reset_document_send_tracking()
        except Exception as exc:
            self._reset_document_send_tracking()
            if count_gate_error is not None:
                raise RuntimeError(
                    f"{UNSURE_REASON_PREFIX} document confirmation failed for {expected_filename}: "
                    f"outgoing count gate failed ({count_gate_error}); "
                    f"filename bubble confirmation failed: {exc}"
                ) from exc
            raise RuntimeError(
                f"{UNSURE_REASON_PREFIX} document confirmation failed for {expected_filename}: {exc}"
            ) from exc

    def verify_recent_documents_persist(
        self,
        filenames: Iterable[str],
        timeout_ms: int = 120_000,
    ) -> None:
        expected = [str(name or "").strip() for name in filenames if str(name or "").strip()]
        if not expected:
            return
        try:
            self.page.reload(wait_until="domcontentloaded", timeout=min(timeout_ms, self.action_timeout_ms))
        except Exception:
            pass
        self._recover_target_chat_after_ui_drift()
        self._ensure_target_chat_ready(require_composer=False)
        stems = [Path(name).stem for name in expected]
        self.page.wait_for_function(
            """
            (payload) => {
              const normalize = (raw) =>
                String(raw || "")
                  .replace(/\\s+/g, " ")
                  .trim()
                  .toLowerCase();
              const outgoing = Array.from(document.querySelectorAll("div.message-out")).slice(-80);
              const texts = outgoing
                .map((node) => normalize(node.innerText || node.textContent || ""))
                .filter(Boolean);
              const candidates = [...(payload.filenames || []), ...(payload.stems || [])]
                .map((value) => normalize(value))
                .filter(Boolean);
              return candidates.every((candidate) =>
                texts.some((text) => text.includes(candidate))
              );
            }
            """,
            arg={"filenames": expected, "stems": stems},
            timeout=timeout_ms,
        )

    def verify_recent_texts_persist(
        self,
        texts: Iterable[str],
        timeout_ms: int = 120_000,
    ) -> None:
        expected = [str(text or "").strip() for text in texts if str(text or "").strip()]
        if not expected:
            return
        try:
            self.page.reload(wait_until="domcontentloaded", timeout=min(timeout_ms, self.action_timeout_ms))
        except Exception:
            pass
        self._recover_target_chat_after_ui_drift()
        self._ensure_target_chat_ready(require_composer=False)
        payload = []
        for text in expected:
            payload.append(
                {
                    "collapsed": self._normalize_outgoing_text(text),
                    "lines": [
                        normalized
                        for normalized in (
                            self._normalize_outgoing_text(line)
                            for line in str(text or "").splitlines()
                        )
                        if normalized
                    ],
                }
            )
        self.page.wait_for_function(
            """
            (payload) => {
              const normalize = (value) =>
                String(value || "")
                  .replace(/\\s+/g, " ")
                  .trim()
                  .toLowerCase();
              const outgoing = Array.from(document.querySelectorAll("div.message-out")).slice(-80);
              const texts = outgoing
                .map((node) => normalize(node.innerText || node.textContent || ""))
                .filter(Boolean);
              return (payload.expected || []).every((entry) => {
                const collapsed = normalize(entry.collapsed || "");
                const lines = Array.isArray(entry.lines)
                  ? entry.lines.map((value) => normalize(value)).filter(Boolean)
                  : [];
                return texts.some((text) => {
                  if (collapsed && text.includes(collapsed)) return true;
                  if (lines.length) return lines.every((line) => text.includes(line));
                  return false;
                });
              });
            }
            """,
            arg={"expected": payload},
            timeout=timeout_ms,
        )


# =============================================================================
# MAIN LOGIC
# =============================================================================


def _store_stats_from_manifest(manifest: Dict[str, Any]) -> Dict[str, Dict[str, int]]:
    stats: Dict[str, Dict[str, int]] = defaultdict(lambda: {"orders_target": 0, "orders_ready": 0})
    for entry in manifest.get("entries") or []:
        counts = dict(entry.get("order_counts_by_store") or {})
        for store, qty in counts.items():
            store_name = _normalize_store_label(store)
            stats[store_name]["orders_target"] += int(qty)
            stats[store_name]["orders_ready"] += int(qty)
    return dict(stats)


def _manifest_entry_label(entry: Dict[str, Any], index: int) -> str:
    return (
        str(entry.get("filename") or "").strip()
        or str(entry.get("relative_output_path") or "").strip()
        or str(entry.get("pdf_key") or "").strip()
        or f"entry#{index}"
    )


def _manifest_entry_order_ids(entry: Dict[str, Any]) -> List[str]:
    order_ids: List[str] = []
    for raw in entry.get("order_ids") or []:
        order_id = str(raw or "").strip()
        if order_id and order_id not in order_ids:
            order_ids.append(order_id)
    return order_ids


def _validate_manifest_order_consistency(manifest: Dict[str, Any]) -> List[Dict[str, Any]]:
    issues: List[Dict[str, Any]] = []
    entries = list(manifest.get("entries") or [])
    order_occurrences: Counter[str] = Counter()
    seen_pdf_keys: set[str] = set()
    send_sequences: dict[int, str] = {}
    total_store_orders = 0
    all_entries_have_store_counts = True

    for index, entry in enumerate(entries, start=1):
        label = _manifest_entry_label(entry, index)
        pdf_key = str(entry.get("pdf_key") or "").strip()
        if pdf_key:
            if pdf_key in seen_pdf_keys:
                issues.append(
                    {
                        "code": "duplicate_pdf_key",
                        "detail": label,
                    }
                )
            seen_pdf_keys.add(pdf_key)

        raw_send_sequence = entry.get("send_sequence")
        if raw_send_sequence in {"", None}:
            issues.append(
                {
                    "code": "entry_send_sequence_missing",
                    "detail": label,
                }
            )
        else:
            try:
                send_sequence = int(raw_send_sequence)
            except (TypeError, ValueError):
                issues.append(
                    {
                        "code": "entry_send_sequence_invalid",
                        "detail": f"{label}: {raw_send_sequence!r}",
                    }
                )
            else:
                if send_sequence <= 0:
                    issues.append(
                        {
                            "code": "entry_send_sequence_invalid",
                            "detail": f"{label}: {send_sequence}",
                        }
                    )
                elif send_sequence in send_sequences:
                    issues.append(
                        {
                            "code": "entry_send_sequence_duplicate",
                            "detail": f"{label}: {send_sequence}",
                        }
                    )
                else:
                    send_sequences[send_sequence] = label

        raw_order_ids = [str(raw or "").strip() for raw in entry.get("order_ids") or [] if str(raw or "").strip()]
        entry_order_ids = _manifest_entry_order_ids(entry)
        if raw_order_ids and len(raw_order_ids) != len(entry_order_ids):
            issues.append(
                {
                    "code": "entry_order_ids_not_unique",
                    "detail": label,
                }
            )
        if not entry_order_ids:
            issues.append(
                {
                    "code": "entry_missing_order_ids",
                    "detail": label,
                }
            )
            all_entries_have_store_counts = False
            continue

        for order_id in entry_order_ids:
            order_occurrences[order_id] += 1

        counts_raw = dict(entry.get("order_counts_by_store") or {})
        if not counts_raw:
            issues.append(
                {
                    "code": "entry_store_order_count_missing",
                    "detail": label,
                }
            )
            all_entries_have_store_counts = False
            continue

        entry_store_total = 0
        entry_counts_valid = True
        for store_name, qty in counts_raw.items():
            try:
                qty_int = int(qty)
            except (TypeError, ValueError):
                issues.append(
                    {
                        "code": "entry_store_order_count_invalid",
                        "detail": f"{label}: {store_name}={qty!r}",
                    }
                )
                entry_counts_valid = False
                all_entries_have_store_counts = False
                continue
            if qty_int < 0:
                issues.append(
                    {
                        "code": "entry_store_order_count_invalid",
                        "detail": f"{label}: {store_name}={qty_int}",
                    }
                )
                entry_counts_valid = False
                all_entries_have_store_counts = False
                continue
            entry_store_total += qty_int

        if not entry_counts_valid:
            continue

        if entry_store_total != len(entry_order_ids):
            issues.append(
                {
                    "code": "entry_store_order_count_mismatch",
                    "detail": (
                        f"{label}: store_total={entry_store_total} "
                        f"unique_orders={len(entry_order_ids)}"
                    ),
                }
            )
        total_store_orders += entry_store_total

        unsafe_core_sources = [
            str(source or "").strip()
            for source in entry.get("unsafe_core_resolution_sources") or []
            if str(source or "").strip()
        ]
        if unsafe_core_sources or bool(entry.get("requires_core_review")):
            issues.append(
                {
                    "code": "unsafe_kaspi_name_core_resolution",
                    "detail": f"{label}: {','.join(sorted(set(unsafe_core_sources or ['requires_core_review'])))}",
                }
            )

    unique_order_ids = set(order_occurrences)
    repeated_order_ids = sorted(
        order_id for order_id, occurrences in order_occurrences.items() if occurrences > 1
    )
    if repeated_order_ids:
        issues.append(
            {
                "code": "order_id_repeated_across_entries",
                "detail": ",".join(repeated_order_ids[:10]),
            }
        )

    counts = dict(manifest.get("counts") or {})
    manifest_pdf_total = int(counts.get("pdfs", 0) or 0)
    if manifest_pdf_total != len(entries):
        issues.append(
            {
                "code": "manifest_pdf_total_mismatch",
                "detail": f"manifest={manifest_pdf_total} entries={len(entries)}",
            }
        )

    if send_sequences:
        expected_sequences = list(range(1, len(entries) + 1))
        actual_sequences = sorted(send_sequences)
        if actual_sequences != expected_sequences:
            issues.append(
                {
                    "code": "send_sequence_range_mismatch",
                    "detail": f"actual={actual_sequences} expected={expected_sequences}",
                }
            )

    manifest_order_total = int(counts.get("orders", 0) or 0)
    if manifest_order_total != len(unique_order_ids):
        issues.append(
            {
                "code": "manifest_order_total_mismatch",
                "detail": f"manifest={manifest_order_total} entries={len(unique_order_ids)}",
            }
        )

    overdue_order_ids = {
        str(raw or "").strip()
        for raw in manifest.get("overdue_order_ids") or []
        if str(raw or "").strip()
    }
    manifest_overdue_total = int(counts.get("overdue_orders", 0) or 0)
    if manifest_overdue_total != len(overdue_order_ids):
        issues.append(
            {
                "code": "manifest_overdue_total_mismatch",
                "detail": f"manifest={manifest_overdue_total} entries={len(overdue_order_ids)}",
            }
        )

    send_order_ids = {
        str(raw or "").strip()
        for raw in manifest.get("send_order_ids") or []
        if str(raw or "").strip()
    }
    if send_order_ids and send_order_ids != unique_order_ids:
        issues.append(
            {
                "code": "send_order_ids_mismatch",
                "detail": (
                    f"manifest={len(send_order_ids)} entries={len(unique_order_ids)}"
                ),
            }
        )

    expected_missing_overdue = sorted(overdue_order_ids - unique_order_ids)
    manifest_missing_overdue = sorted(
        {
            str(raw or "").strip()
            for raw in manifest.get("missing_overdue_order_ids") or []
            if str(raw or "").strip()
        }
    )
    if manifest_missing_overdue and manifest_missing_overdue != expected_missing_overdue:
        issues.append(
            {
                "code": "missing_overdue_order_ids_mismatch",
                "detail": (
                    f"manifest={','.join(manifest_missing_overdue)} "
                    f"expected={','.join(expected_missing_overdue)}"
                ),
            }
        )

    if all_entries_have_store_counts and total_store_orders != len(unique_order_ids):
        issues.append(
            {
                "code": "manifest_store_order_total_mismatch",
                "detail": f"store_total={total_store_orders} unique_orders={len(unique_order_ids)}",
            }
        )

    return issues


def _record_status_message_failure(results: Dict[str, Any], *, phase: str, error: Exception) -> None:
    phase_key = "pre" if phase == "pre" else "post"
    results["status_message_failed"] = 1
    results["status_message_failures"] = int(results.get("status_message_failures", 0) or 0) + 1
    phase_counts = results.setdefault(
        "status_message_failures_by_phase",
        {"pre": 0, "post": 0},
    )
    phase_counts[phase_key] = int(phase_counts.get(phase_key, 0) or 0) + 1
    details = results.setdefault("status_message_failure_details", [])
    details.append({"phase": phase_key, "detail": str(error)})


def _is_retryable_document_send_setup_error(exc: Exception) -> bool:
    message = str(exc or "").strip().lower()
    if not message:
        return False
    return any(
        needle in message
        for needle in (
            "failed to click send button once",
            "whatsapp home screen is visible",
            "no chat is currently open",
            "active chat mismatch",
            "target chat did not open",
            "attach button is not visible in target chat",
            "global share modal opened",
        )
    )


def _rearm_entries_for_forced_resend(
    ledger: Dict[str, Any],
    pdf_keys: Iterable[str],
) -> None:
    now = datetime.now().isoformat()
    ledger_entries = ledger.setdefault("entries", {})
    for pdf_key in pdf_keys:
        entry = ledger_entries.get(str(pdf_key))
        if not isinstance(entry, dict):
            continue
        entry["state"] = "pending"
        entry["last_updated"] = now
        history = entry.setdefault("history", [])
        if isinstance(history, list):
            history.append(
                {
                    "state": "pending",
                    "at": now,
                    "note": "forced resend requested (--no-resume)",
                }
            )
    ledger["updated_at"] = now


def _confirmed_progress_snapshot(
    entries: List[Dict[str, Any]],
    ledger: Dict[str, Any],
) -> tuple[int, Counter[str]]:
    confirmed_bundles = 0
    sent_orders_by_store: Counter[str] = Counter()
    ledger_entries = dict(ledger.get("entries") or {})
    for entry in entries:
        entry_state = str(ledger_entries.get(entry["pdf_key"], {}).get("state") or "pending")
        if entry_state != "confirmed":
            continue
        confirmed_bundles += 1
        for store_name, qty in dict(entry.get("order_counts_by_store") or {}).items():
            sent_orders_by_store[_normalize_store_label(store_name)] += int(qty)
    return confirmed_bundles, sent_orders_by_store


def _all_manifest_entries_in_state(
    entries: List[Dict[str, Any]],
    ledger: Dict[str, Any],
    state: str,
) -> bool:
    ledger_entries = dict(ledger.get("entries") or {})
    for entry in entries:
        pdf_key = str(entry.get("pdf_key") or "")
        if not pdf_key:
            return False
        if str(ledger_entries.get(pdf_key, {}).get("state") or "") != state:
            return False
    return True


def run_delivery_probe(
    *,
    chat_title: str,
    chrome_user_data_dir: Path = DEFAULT_CHROME_USER_DATA_DIR,
    chrome_profile_directory: str = DEFAULT_CHROME_PROFILE_DIR,
    chrome_profile_name: Optional[str] = DEFAULT_CHROME_PROFILE_NAME,
    cdp_endpoint: str = DEFAULT_CDP_ENDPOINT,
    browser_mode: str = DEFAULT_BROWSER_MODE,
    blocked_chat_titles: Iterable[str] = BLOCKED_CHAT_TITLES_DEFAULT,
    probe_message_prefix: str = DEFAULT_DELIVERY_PROBE_MESSAGE_PREFIX,
    probe_repeat_count: int = DEFAULT_DELIVERY_PROBE_REPEAT_COUNT,
    probe_interval_seconds: float = DEFAULT_DELIVERY_PROBE_INTERVAL_SECONDS,
    probe_timeout_seconds: float = DEFAULT_DELIVERY_PROBE_TIMEOUT_SECONDS,
    verbose: bool = False,
) -> Dict[str, Any]:
    results: Dict[str, Any] = {
        "ok": False,
        "target_chat": chat_title or "",
        "probe_message_prefix": str(probe_message_prefix or DEFAULT_DELIVERY_PROBE_MESSAGE_PREFIX),
        "probe_repeat_count": int(probe_repeat_count or 0),
        "probe_interval_seconds": float(probe_interval_seconds or 0.0),
        "probe_timeout_seconds": float(probe_timeout_seconds or 0.0),
        "attempts": [],
        "failure": "",
    }
    if not chat_title:
        results["failure"] = "chat_title is required"
        return results
    if not check_playwright():
        results["failure"] = "playwright not installed"
        return results

    timeout_ms = max(1_000, int(float(probe_timeout_seconds) * 1000))
    repeat_count = max(1, int(probe_repeat_count))
    interval_seconds = max(0.0, float(probe_interval_seconds))
    message_prefix = str(probe_message_prefix or DEFAULT_DELIVERY_PROBE_MESSAGE_PREFIX).strip()

    sender = WhatsAppSender(
        chat_title=chat_title,
        user_data_dir=Path(chrome_user_data_dir),
        profile_directory=chrome_profile_directory,
        profile_name=chrome_profile_name,
        cdp_endpoint=cdp_endpoint,
        browser_mode=browser_mode,
        blocked_chat_titles=blocked_chat_titles,
        action_timeout_ms=ACTION_TIMEOUT_MS,
        verbose=verbose,
    )

    sent_texts: List[str] = []
    try:
        with sender:
            if hasattr(sender, "assert_document_send_ready"):
                sender.assert_document_send_ready()
            for attempt_num in range(1, repeat_count + 1):
                stamp = datetime.now(ALMATY_TZ).strftime("%Y-%m-%d %H:%M:%S")
                probe_text = f"{message_prefix} #{attempt_num} {stamp}"
                attempt_result: Dict[str, Any] = {
                    "attempt": attempt_num,
                    "text": probe_text,
                    "sent": False,
                    "delivered": False,
                    "persisted": False,
                    "sent_at": datetime.now(ALMATY_TZ).isoformat(),
                }
                sender.send_text_message(probe_text)
                status = sender.confirm_text_message_sent(probe_text, timeout_ms=timeout_ms)
                attempt_result["sent"] = bool(status.get("sent"))
                attempt_result["delivered"] = bool(status.get("delivered"))
                attempt_result["delivery_state"] = str(
                    status.get("delivery_state") or ("delivered" if attempt_result["delivered"] else "sent")
                )
                sent_texts.append(probe_text)
                if hasattr(sender, "bind_active_chat_identity_if_missing"):
                    sender.bind_active_chat_identity_if_missing()
                sender.wait_for_outgoing_sync(timeout_ms=timeout_ms)
                if hasattr(sender, "verify_recent_texts_persist"):
                    sender.verify_recent_texts_persist(sent_texts, timeout_ms=timeout_ms)
                attempt_result["persisted"] = True
                attempt_result["verified_at"] = datetime.now(ALMATY_TZ).isoformat()
                results["attempts"].append(attempt_result)
                if hasattr(sender, "assert_document_send_ready"):
                    sender.assert_document_send_ready()
                if attempt_num < repeat_count and interval_seconds > 0:
                    time.sleep(interval_seconds)
        results["ok"] = True
        return results
    except Exception as exc:
        results["failure"] = str(exc)
        return results


def run_sender(
    today_folder: Path,
    chat_title: Optional[str],
    dry_run: bool = False,
    resume: bool = True,
    bundle_source: str = SOURCE_AUTO,
    status_messages: bool = True,
    post_status_message_only: bool = False,
    expected_target_date: Optional[date] = None,
    allow_stale_batch: bool = False,
    send_delay: float = SEND_DELAY,
    chrome_user_data_dir: Path = DEFAULT_CHROME_USER_DATA_DIR,
    chrome_profile_directory: str = DEFAULT_CHROME_PROFILE_DIR,
    chrome_profile_name: Optional[str] = DEFAULT_CHROME_PROFILE_NAME,
    cdp_endpoint: str = DEFAULT_CDP_ENDPOINT,
    browser_mode: str = DEFAULT_BROWSER_MODE,
    blocked_chat_titles: Iterable[str] = BLOCKED_CHAT_TITLES_DEFAULT,
    fail_fast: bool = False,
    allow_unsure_resume: bool = False,
    max_pdfs: Optional[int] = None,
    post_send_linger_seconds: float = 0.0,
    verbose: bool = False,
) -> Dict[str, Any]:
    """Run WhatsApp PDF sender workflow."""
    results: Dict[str, Any] = {
        "sent": 0,
        "skipped": 0,
        "failed": 0,
        "total": 0,
        "target_chat": chat_title or "",
        "source_root": "",
        "status_message_failed": 0,
        "status_message_failures": 0,
        "status_message_failures_by_phase": {"pre": 0, "post": 0},
        "status_message_failure_details": [],
        "post_send_verification_failed": 0,
        "post_send_verification_details": [],
        "halted": False,
        "halt_reason": "",
        "diagnostics_dir": "",
        "recovery_ladder": [],
    }

    if not chat_title and not dry_run:
        print("ERROR: --chat-title is required for live send.")
        return results

    send_pre_status_message = bool(status_messages and not post_status_message_only)
    send_post_status_message = bool(status_messages or post_status_message_only)

    if not dry_run and not check_playwright():
        print("ERROR: playwright not installed.")
        print("Install with: pip install playwright")
        return results

    preflight = verify_send_batch_preflight(
        today_folder,
        source_mode=bundle_source,
        allow_unsure_resume=allow_unsure_resume,
        expected_target_date=expected_target_date,
        allow_stale_batch=allow_stale_batch,
    )
    if not preflight["ok"]:
        results["failed"] += 1
        results["halted"] = True
        results["halt_reason"] = "PREFLIGHT_RED"
        _write_send_stopline(
            today_folder,
            {
                "halt_reason": results["halt_reason"],
                "issues": preflight["issues"],
                "captured_at": datetime.now().isoformat(),
            },
        )
        print("ERROR: send batch preflight failed.")
        for issue in preflight["issues"]:
            print(f"  - {issue['code']}: {issue['detail']}")
        return results

    manifest = load_send_batch_manifest(today_folder, source_mode=bundle_source)
    batch_root = Path(manifest["batch_root"])
    results["source_root"] = str(batch_root)
    entries = list(manifest.get("entries") or [])
    results["total"] = len(entries)
    store_stats = _store_stats_from_manifest(manifest)
    ledger_path = batch_root / SEND_LEDGER_FILE
    ledger = load_send_ledger(ledger_path, manifest)
    save_send_ledger(ledger_path, ledger)

    if verbose:
        print(f"Bundle source root: {batch_root}")
        print(f"Found {len(entries)} PDFs total")

    if not entries:
        print("No PDFs found in send batch manifest")
        return results

    def _make_sender() -> WhatsAppSender:
        return WhatsAppSender(
            chat_title=chat_title or "",
            user_data_dir=Path(chrome_user_data_dir),
            profile_directory=chrome_profile_directory,
            profile_name=chrome_profile_name,
            cdp_endpoint=cdp_endpoint,
            browser_mode=browser_mode,
            blocked_chat_titles=blocked_chat_titles,
            action_timeout_ms=ACTION_TIMEOUT_MS,
            verbose=verbose,
        )

    if resume:
        pdfs_to_send = select_manifest_entries_for_send(
            manifest,
            ledger,
            allow_unsure_resume=allow_unsure_resume,
        )
    else:
        pdfs_to_send = list(entries)
        _rearm_entries_for_forced_resend(
            ledger,
            [str(entry.get("pdf_key") or "") for entry in pdfs_to_send],
        )
        save_send_ledger(ledger_path, ledger)
    pdfs_to_send = order_pdfs_for_sending(pdfs_to_send)
    if max_pdfs is not None:
        pdfs_to_send = pdfs_to_send[: max(0, int(max_pdfs))]
    results["skipped"] = len(entries) - len(pdfs_to_send)
    confirmed_bundles_before_run, confirmed_orders_by_store_before_run = _confirmed_progress_snapshot(
        entries,
        ledger,
    )

    if results["skipped"] > 0 and verbose:
        print(f"Skipping {results['skipped']} ledger-complete PDFs")

    if not pdfs_to_send:
        print("All PDFs already sent or blocked by ledger state!")
        pre_status_text = format_pre_send_status_table(
            store_stats,
            bundles_target=len(entries),
        )
        post_status_text = format_post_send_status_table(
            store_stats,
            dict(confirmed_orders_by_store_before_run),
            bundles_target=len(entries),
            bundles_sent=confirmed_bundles_before_run,
        )
        print("\nPre-send status:")
        print(pre_status_text)
        print("\nPost-send status:")
        print(post_status_text)
        if send_post_status_message and not dry_run and post_status_message_only:
            sender = _make_sender()
            try:
                with sender:
                    sender.send_text_message(post_status_text)
                    try:
                        sender.wait_for_outgoing_sync(timeout_ms=120_000)
                    except Exception as exc:
                        if verbose:
                            print(f"WARNING: final outgoing sync check failed: {exc}")
            except Exception as exc:
                _record_status_message_failure(results, phase="post", error=exc)
                print(f"\nWARNING: Failed to send post-send status message: {exc}")
        elif verbose and send_post_status_message and not dry_run:
            print(
                "Skipping post-send WhatsApp status message because no PDFs are pending; "
                "use --post-status-message-only to force a corrected summary resend."
            )
        return results

    bundles_target = len(pdfs_to_send)
    bundles_sent = confirmed_bundles_before_run
    sent_orders_by_store: Counter[str] = Counter(confirmed_orders_by_store_before_run)
    sent_filenames_this_run: List[str] = []

    print(f"\n{'[DRY RUN] ' if dry_run else ''}PDFs to send: {len(pdfs_to_send)}")
    print("-" * 50)
    pre_status_text = format_pre_send_status_table(store_stats, bundles_target=bundles_target)
    print("\nPre-send status:")
    print(pre_status_text)

    current_batch: Optional[str] = None
    current_category: Optional[str] = None

    if dry_run:
        for i, pdf in enumerate(pdfs_to_send, start=1):
            batch_label = str(manifest.get("batch_label") or batch_root.name)
            if batch_label != current_batch:
                current_batch = batch_label
                print(f"\nBatch: {current_batch}")

            if pdf["category"] != current_category:
                current_category = pdf["category"]
                print(f"  [{current_category.replace('_', ' ').title()}]")

            print(f"    {i}. {pdf['filename']}")
            results["sent"] += 1
            bundles_sent += 1
            for store_name, qty in dict(pdf.get("order_counts_by_store") or {}).items():
                sent_orders_by_store[_normalize_store_label(store_name)] += int(qty)

        post_status_text = format_post_send_status_table(
            store_stats,
            dict(sent_orders_by_store),
            bundles_target=len(entries),
            bundles_sent=bundles_sent,
        )
        print("\nPost-send status:")
        print(post_status_text)
        return results

    sender = _make_sender()

    def _capture_failure(
        *,
        failure_code: str,
        detail: str,
        pdf: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        diagnostics = capture_sender_failure_diagnostics(
            sender,
            today_folder=today_folder,
            failure_code=failure_code,
            batch_root=batch_root,
            manifest_path=Path(manifest["manifest_path"]),
            pdf_filename=str(pdf.get("filename") or "") if pdf else None,
            detail=detail,
        )
        results["diagnostics_dir"] = diagnostics.get("diagnostics_dir", "")
        results["recovery_ladder"] = diagnostics.get("recovery_ladder", [])
        if diagnostics.get("diagnostics_dir"):
            print(f"Diagnostics artifact: {diagnostics['diagnostics_dir']}")
        return diagnostics

    try:
        with sender:
            if pdfs_to_send and hasattr(sender, "assert_document_send_ready"):
                sender.assert_document_send_ready()
            if send_pre_status_message:
                try:
                    sender.send_text_message(pre_status_text)
                    if hasattr(sender, "confirm_text_message_sent"):
                        sender.confirm_text_message_sent(
                            pre_status_text,
                            timeout_ms=120_000,
                        )
                    if hasattr(sender, "bind_active_chat_identity_if_missing"):
                        sender.bind_active_chat_identity_if_missing()
                    if pdfs_to_send and hasattr(sender, "assert_document_send_ready"):
                        sender.assert_document_send_ready()
                except Exception as exc:
                    _record_status_message_failure(results, phase="pre", error=exc)
                    raise RuntimeError(f"Pre-send delivery probe failed: {exc}") from exc

            for i, pdf in enumerate(pdfs_to_send, start=1):
                batch_label = str(manifest.get("batch_label") or batch_root.name)
                if batch_label != current_batch:
                    current_batch = batch_label
                    print(f"\nBatch: {current_batch}")

                if pdf["category"] != current_category:
                    current_category = pdf["category"]
                    print(f"  [{current_category.replace('_', ' ').title()}]")

                print(f"    {i}. {pdf['filename']}")

                pdf_key = str(pdf["pdf_key"])
                pdf_path = Path(pdf["path"])
                try:
                    transition_send_ledger_entry(
                        ledger,
                        pdf_key,
                        "opened",
                        allow_unsure_resume=allow_unsure_resume,
                    )
                    save_send_ledger(ledger_path, ledger)
                    document_confirmed = False
                    last_send_exc: Exception | None = None
                    for send_attempt in range(1, 3):
                        try:
                            sender.prepare_document(pdf_path)
                            previous_outgoing = sender._outgoing_message_count()
                            if hasattr(sender, "mark_document_send_clicked"):
                                sender.mark_document_send_clicked(pdf["filename"])
                            sender.click_document_send()
                            transition_send_ledger_entry(ledger, pdf_key, "clicked")
                            save_send_ledger(ledger_path, ledger)
                            sender.confirm_document_sent(
                                pdf["filename"],
                                previous_outgoing=previous_outgoing,
                            )
                            document_confirmed = True
                            break
                        except Exception as send_exc:
                            last_send_exc = send_exc
                            reset_tracking = getattr(sender, "_reset_document_send_tracking", None)
                            if callable(reset_tracking):
                                try:
                                    reset_tracking()
                                except Exception:
                                    pass
                            if (
                                send_attempt < 2
                                and ledger.get("entries", {}).get(pdf_key, {}).get("state") == "opened"
                                and _is_retryable_document_send_setup_error(send_exc)
                            ):
                                print(
                                    f"WARNING: document send UI drift before click for {pdf['filename']}; retrying once..."
                                )
                                recover_target_chat = getattr(sender, "_recover_target_chat_after_ui_drift", None)
                                if callable(recover_target_chat):
                                    recover_target_chat()
                                continue
                            raise
                    if not document_confirmed:
                        raise last_send_exc or RuntimeError(
                            f"Failed to send {pdf['filename']} before confirmation"
                        )
                    transition_send_ledger_entry(ledger, pdf_key, "confirmed")
                    save_send_ledger(ledger_path, ledger)
                except Exception as exc:
                    reset_tracking = getattr(sender, "_reset_document_send_tracking", None)
                    if callable(reset_tracking):
                        try:
                            reset_tracking()
                        except Exception:
                            pass
                    message = str(exc)
                    if message.startswith(UNSURE_REASON_PREFIX):
                        diagnostics = _capture_failure(
                            failure_code="UNSURE",
                            detail=message,
                            pdf=pdf,
                        )
                        transition_send_ledger_entry(ledger, pdf_key, "unsure")
                        save_send_ledger(ledger_path, ledger)
                        results["failed"] += 1
                        results["halted"] = True
                        results["halt_reason"] = "UNSURE"
                        _write_send_stopline(
                            today_folder,
                            {
                                "halt_reason": "UNSURE",
                                "pdf_key": pdf_key,
                                "filename": pdf["filename"],
                                "detail": message,
                                "batch_root": str(batch_root),
                                "manifest_path": manifest["manifest_path"],
                                "ledger_path": str(ledger_path),
                                "captured_at": datetime.now().isoformat(),
                                "diagnostics_dir": diagnostics.get("diagnostics_dir", ""),
                                "recovery_ladder": diagnostics.get("recovery_ladder", []),
                            },
                        )
                        print(f"\nSTOPPING: {message}")
                        break

                    results["failed"] += 1
                    diagnostics = _capture_failure(
                        failure_code="FAILED",
                        detail=str(exc),
                        pdf=pdf,
                    )
                    if ledger.get("entries", {}).get(pdf_key, {}).get("state") == "opened":
                        try:
                            transition_send_ledger_entry(ledger, pdf_key, "failed")
                            save_send_ledger(ledger_path, ledger)
                        except Exception:
                            pass
                    if fail_fast:
                        print(f"\nSTOPPING: Failed to send {pdf['filename']}: {exc}")
                        print("Use --resume after fixing WhatsApp UI/session")
                        results["halted"] = True
                        results["halt_reason"] = "FAILED"
                        _write_send_stopline(
                            today_folder,
                            {
                                "halt_reason": "FAILED",
                                "pdf_key": pdf_key,
                                "filename": pdf["filename"],
                                "detail": str(exc),
                                "batch_root": str(batch_root),
                                "manifest_path": manifest["manifest_path"],
                                "ledger_path": str(ledger_path),
                                "captured_at": datetime.now().isoformat(),
                                "diagnostics_dir": diagnostics.get("diagnostics_dir", ""),
                                "recovery_ladder": diagnostics.get("recovery_ladder", []),
                            },
                        )
                        break
                    print(f"\nWARNING: Failed to send {pdf['filename']}: {exc}")
                    continue

                results["sent"] += 1
                bundles_sent += 1
                sent_filenames_this_run.append(str(pdf["filename"]))
                for store_name, qty in dict(pdf.get("order_counts_by_store") or {}).items():
                    sent_orders_by_store[_normalize_store_label(store_name)] += int(qty)

                if i < len(pdfs_to_send) and send_delay > 0:
                    time.sleep(send_delay)

            post_status_text = format_post_send_status_table(
                store_stats,
                dict(sent_orders_by_store),
                bundles_target=len(entries),
                bundles_sent=bundles_sent,
            )
            print("\nPost-send status:")
            print(post_status_text)
            if send_post_status_message:
                try:
                    sender.send_text_message(post_status_text)
                except Exception as exc:
                    _record_status_message_failure(results, phase="post", error=exc)
                    print(f"\nWARNING: Failed to send post-send status message: {exc}")

            # Ensure final message/doc upload state is synced before browser closes.
            try:
                sender.wait_for_outgoing_sync(timeout_ms=120_000)
            except Exception as exc:
                if verbose:
                    print(f"WARNING: final outgoing sync check failed: {exc}")
            if sent_filenames_this_run and hasattr(sender, "verify_recent_documents_persist"):
                try:
                    sender.verify_recent_documents_persist(
                        sent_filenames_this_run,
                        timeout_ms=120_000,
                    )
                except Exception as exc:
                    if _all_manifest_entries_in_state(entries, ledger, "confirmed"):
                        detail = str(exc)
                        results["post_send_verification_failed"] = int(
                            results.get("post_send_verification_failed", 0) or 0
                        ) + 1
                        verification_details = list(results.get("post_send_verification_details") or [])
                        verification_details.append(detail)
                        results["post_send_verification_details"] = verification_details
                        print(
                            "\nWARNING: post-send persistence check timed out after all bundles were already "
                            f"confirmed in the ledger: {detail}"
                        )
                    else:
                        raise
            linger_seconds = max(0.0, float(post_send_linger_seconds or 0.0))
            if linger_seconds > 0:
                if verbose:
                    print(f"Lingering with WhatsApp open for {int(linger_seconds)}s before shutdown...")
                time.sleep(linger_seconds)
    except Exception as exc:
        results["failed"] += 1
        results["halted"] = True
        results["halt_reason"] = "RUNTIME_ERROR"
        diagnostics = _capture_failure(
            failure_code="RUNTIME_ERROR",
            detail=str(exc),
        )
        _write_send_stopline(
            today_folder,
            {
                "halt_reason": results["halt_reason"],
                "detail": str(exc),
                "batch_root": str(batch_root),
                "manifest_path": manifest["manifest_path"],
                "ledger_path": str(ledger_path),
                "captured_at": datetime.now().isoformat(),
                "diagnostics_dir": diagnostics.get("diagnostics_dir", ""),
                "recovery_ladder": diagnostics.get("recovery_ladder", []),
            },
        )
        if fail_fast:
            print(f"\nSTOPPING: Sender runtime error: {exc}")
        else:
            print(f"\nWARNING: Sender runtime error: {exc}")
    finally:
        sender.close()

    return results


# =============================================================================
# CLI
# =============================================================================


def main() -> None:
    def _parse_iso_date(value: str) -> date:
        try:
            return date.fromisoformat(value)
        except ValueError as exc:
            raise argparse.ArgumentTypeError(
                f"Invalid ISO date {value!r}; expected YYYY-MM-DD"
            ) from exc

    parser = argparse.ArgumentParser(description="Send waybill PDFs to WhatsApp chat")
    parser.add_argument(
        "--today-folder",
        type=Path,
        default=TODAY_FOLDER,
        help="Path to Today folder (default: excel_ui/Kaspi_orders/Today)",
    )
    parser.add_argument(
        "--chat-title",
        type=str,
        default=DEFAULT_WHATSAPP_CHAT_TITLE,
        help="Exact WhatsApp chat title to send into (default: Заказы)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview only, don't send",
    )
    parser.add_argument(
        "--no-resume",
        action="store_true",
        help="Don't skip already-sent PDFs",
    )
    parser.add_argument(
        "--allow-unsure-resume",
        action="store_true",
        help="Allow explicit resume from ledger entries currently marked UNSURE",
    )
    parser.add_argument(
        "--bundle-source",
        choices=SOURCE_CHOICES,
        default=SOURCE_AUTO,
        help=(
            "Which bundle layout to send from: "
            "auto (prefer MERGED/SEND, then MERGED, then PER_STORE, then legacy), "
            "merged (MERGED/SEND only), per-store, or legacy."
        ),
    )
    parser.add_argument(
        "--chrome-user-data-dir",
        type=Path,
        default=DEFAULT_CHROME_USER_DATA_DIR,
        help="Chrome user data dir containing the named profile and WhatsApp session",
    )
    parser.add_argument(
        "--chrome-profile-name",
        type=str,
        default=DEFAULT_CHROME_PROFILE_NAME,
        help="Chrome profile display name (default: Universal)",
    )
    parser.add_argument(
        "--chrome-profile-directory",
        type=str,
        default=DEFAULT_CHROME_PROFILE_DIR,
        help="Chrome profile directory name (e.g. 'Profile 2'); validated against --chrome-profile-name when provided",
    )
    parser.add_argument(
        "--cdp-endpoint",
        type=str,
        default=DEFAULT_CDP_ENDPOINT,
        help="Chrome DevTools endpoint used for attach mode (default: http://127.0.0.1:9222)",
    )
    parser.add_argument(
        "--browser-mode",
        choices=BROWSER_MODE_CHOICES,
        default=DEFAULT_BROWSER_MODE,
        help="Browser control mode: attach to an existing Chrome session or launch a temp-profile browser",
    )
    parser.add_argument(
        "--forbid-chat",
        action="append",
        default=list(BLOCKED_CHAT_TITLES_DEFAULT),
        help="Blocked chat title safety gate (repeatable)",
    )
    parser.add_argument(
        "--send-delay",
        type=float,
        default=SEND_DELAY,
        help="Delay between sends in seconds",
    )
    parser.add_argument(
        "--status-messages",
        dest="status_messages",
        action="store_true",
        default=True,
        help="Send pre/post ASCII status tables to WhatsApp chat (default: on)",
    )
    parser.add_argument(
        "--no-status-messages",
        dest="status_messages",
        action="store_false",
        help="Disable sending pre/post ASCII status tables to WhatsApp chat",
    )
    parser.add_argument(
        "--post-status-message-only",
        action="store_true",
        help="Send only the final post-send ASCII status table to WhatsApp chat",
    )
    parser.add_argument(
        "--delivery-probe-only",
        action="store_true",
        help="Send delivered-state probe text messages only and verify persistence without sending PDFs",
    )
    parser.add_argument(
        "--probe-message-prefix",
        type=str,
        default=DEFAULT_DELIVERY_PROBE_MESSAGE_PREFIX,
        help="Prefix used for delivery probe messages",
    )
    parser.add_argument(
        "--probe-repeat-count",
        type=int,
        default=DEFAULT_DELIVERY_PROBE_REPEAT_COUNT,
        help="How many delivery probe messages to send",
    )
    parser.add_argument(
        "--probe-interval-seconds",
        type=float,
        default=DEFAULT_DELIVERY_PROBE_INTERVAL_SECONDS,
        help="Seconds to wait between delivery probe messages",
    )
    parser.add_argument(
        "--probe-timeout-seconds",
        type=float,
        default=DEFAULT_DELIVERY_PROBE_TIMEOUT_SECONDS,
        help="Per-probe delivery/persistence timeout in seconds",
    )
    parser.add_argument(
        "--linger-seconds",
        type=float,
        default=0.0,
        help="Keep the browser session open for N seconds after final send sync before shutdown",
    )
    parser.add_argument(
        "--expected-target-date",
        type=_parse_iso_date,
        default=None,
        help="Expected send-batch target date in YYYY-MM-DD format (default: today in Asia/Almaty)",
    )
    parser.add_argument(
        "--allow-stale-batch",
        action="store_true",
        help="Allow sending a batch whose manifest target date does not match the expected target date",
    )
    parser.add_argument(
        "--fail-fast",
        action="store_true",
        help="Stop on first send/runtime error (default: continue and report failures)",
    )
    parser.add_argument(
        "--preflight-only",
        action="store_true",
        help="Validate immutable send batch contract and exit without sending",
    )
    parser.add_argument(
        "--smoke-check-only",
        action="store_true",
        help="Open WhatsApp, verify target chat + document controls, and exit without sending PDFs",
    )
    parser.add_argument(
        "--resolve-unsure-filename",
        type=str,
        default=None,
        help="Resolve one existing UNSURE ledger entry by exact filename and exit",
    )
    parser.add_argument(
        "--resolve-unsure-as",
        choices=("confirmed", "pending"),
        default=None,
        help="Resolution to apply with --resolve-unsure-filename",
    )
    parser.add_argument(
        "--resolve-unsure-note",
        type=str,
        default="",
        help="Optional ledger history note stored with --resolve-unsure-filename",
    )
    parser.add_argument(
        "--json-out",
        type=Path,
        default=None,
        help="Optional JSON output path for preflight or live run summary",
    )
    parser.add_argument(
        "--max-pdfs",
        type=int,
        default=None,
        help="Optional cap on how many pending PDFs to send in this run",
    )
    parser.add_argument("--verbose", "-v", action="store_true", help="Verbose output")

    args = parser.parse_args()
    dedup_blocked: List[str] = []
    seen_blocked: set[str] = set()
    for name in args.forbid_chat:
        key = _normalize_chat_key(name)
        if key and key not in seen_blocked:
            seen_blocked.add(key)
            dedup_blocked.append(name)
    try:
        resolved_profile_directory = resolve_chrome_profile_directory(
            args.chrome_user_data_dir,
            profile_name=args.chrome_profile_name,
            profile_directory=args.chrome_profile_directory,
        )
    except Exception:
        resolved_profile_directory = str(args.chrome_profile_directory)

    print("=" * 60)
    print("  WhatsApp PDF Sender")
    print("=" * 60)
    print(f"  Folder: {args.today_folder}")
    print(f"  Bundle source: {args.bundle_source}")
    print(f"  Target chat: {args.chat_title}")
    print(f"  Blocked chats: {', '.join(dedup_blocked)}")
    print(
        "  Browser profile: "
        f"{args.chrome_user_data_dir} / {args.chrome_profile_name} / {resolved_profile_directory}"
    )
    print(f"  Browser mode: {args.browser_mode}")
    print(f"  CDP endpoint: {args.cdp_endpoint}")
    print(f"  Mode: {'DRY RUN' if args.dry_run else 'LIVE'}")
    if args.post_status_message_only:
        status_mode_label = "Post only"
    else:
        status_mode_label = "Yes" if args.status_messages else "No"
    expected_target_date = args.expected_target_date or datetime.now(ALMATY_TZ).date()
    print(f"  Status messages: {status_mode_label}")
    print(f"  Expected target date: {expected_target_date.isoformat()}")
    print(f"  Allow stale batch: {'Yes' if args.allow_stale_batch else 'No'}")
    print(f"  Fail fast: {'Yes' if args.fail_fast else 'No'}")
    print(f"  Resume: {'No' if args.no_resume else 'Yes'}")
    print(f"  Allow UNSURE resume: {'Yes' if args.allow_unsure_resume else 'No'}")
    print(f"  Delivery probe only: {'Yes' if args.delivery_probe_only else 'No'}")
    print(f"  Preflight only: {'Yes' if args.preflight_only else 'No'}")
    print(f"  Smoke check only: {'Yes' if args.smoke_check_only else 'No'}")
    print(f"  Resolve UNSURE filename: {args.resolve_unsure_filename or 'No'}")
    print(f"  Max PDFs this run: {args.max_pdfs if args.max_pdfs is not None else 'All pending'}")
    print()

    if args.resolve_unsure_filename and not args.resolve_unsure_as:
        raise SystemExit("--resolve-unsure-as is required with --resolve-unsure-filename")
    if args.resolve_unsure_as and not args.resolve_unsure_filename:
        raise SystemExit("--resolve-unsure-filename is required with --resolve-unsure-as")

    if args.preflight_only and args.smoke_check_only:
        raise SystemExit("--preflight-only and --smoke-check-only are mutually exclusive")
    if args.delivery_probe_only and args.preflight_only:
        raise SystemExit("--delivery-probe-only and --preflight-only are mutually exclusive")
    if args.delivery_probe_only and args.smoke_check_only:
        raise SystemExit("--delivery-probe-only and --smoke-check-only are mutually exclusive")
    if args.delivery_probe_only and args.post_status_message_only:
        raise SystemExit("--delivery-probe-only and --post-status-message-only are mutually exclusive")

    if args.delivery_probe_only:
        probe = run_delivery_probe(
            chat_title=args.chat_title,
            chrome_user_data_dir=args.chrome_user_data_dir,
            chrome_profile_directory=args.chrome_profile_directory,
            chrome_profile_name=args.chrome_profile_name,
            cdp_endpoint=args.cdp_endpoint,
            browser_mode=args.browser_mode,
            blocked_chat_titles=dedup_blocked,
            probe_message_prefix=str(args.probe_message_prefix),
            probe_repeat_count=int(args.probe_repeat_count),
            probe_interval_seconds=float(args.probe_interval_seconds),
            probe_timeout_seconds=float(args.probe_timeout_seconds),
            verbose=args.verbose,
        )
        if args.json_out:
            args.json_out.parent.mkdir(parents=True, exist_ok=True)
            args.json_out.write_text(json.dumps(probe, ensure_ascii=False, indent=2), encoding="utf-8")
        if probe.get("ok"):
            print("Delivery probe OK")
            for attempt in probe.get("attempts", []):
                print(
                    f"  - attempt {attempt.get('attempt')}: sent={attempt.get('sent')} "
                    f"delivery_state={attempt.get('delivery_state')} "
                    f"delivered={attempt.get('delivered')} "
                    f"persisted={attempt.get('persisted')}"
                )
            raise SystemExit(0)
        print("Delivery probe FAIL")
        if probe.get("failure"):
            print(f"  - {probe['failure']}")
        for attempt in probe.get("attempts", []):
            print(
                f"  - attempt {attempt.get('attempt')}: sent={attempt.get('sent')} "
                f"delivery_state={attempt.get('delivery_state')} "
                f"delivered={attempt.get('delivered')} "
                f"persisted={attempt.get('persisted')}"
            )
        raise SystemExit(1)

    if args.preflight_only:
        preflight = verify_send_batch_preflight(
            args.today_folder,
            source_mode=args.bundle_source,
            allow_unsure_resume=bool(args.allow_unsure_resume),
            expected_target_date=expected_target_date,
            allow_stale_batch=bool(args.allow_stale_batch),
        )
        if args.json_out:
            args.json_out.parent.mkdir(parents=True, exist_ok=True)
            args.json_out.write_text(json.dumps(preflight, ensure_ascii=False, indent=2), encoding="utf-8")
        if preflight["ok"]:
            print("Preflight OK")
            print(f"  Manifest: {preflight['manifest_path']}")
            print(f"  Batch root: {preflight['batch_root']}")
            print(f"  Batch hash: {preflight['batch_hash']}")
            print(f"  Target date: {preflight.get('target_date')}")
            raise SystemExit(0)
        print("Preflight FAIL")
        for issue in preflight["issues"]:
            print(f"  - {issue['code']}: {issue['detail']}")
        raise SystemExit(1)

    if args.smoke_check_only:
        smoke = run_sender_smoke_check(
            today_folder=args.today_folder,
            chat_title=args.chat_title,
            bundle_source=args.bundle_source,
            chrome_user_data_dir=args.chrome_user_data_dir,
            chrome_profile_directory=args.chrome_profile_directory,
            chrome_profile_name=args.chrome_profile_name,
            cdp_endpoint=args.cdp_endpoint,
            browser_mode=args.browser_mode,
            blocked_chat_titles=dedup_blocked,
            expected_target_date=expected_target_date,
            allow_stale_batch=bool(args.allow_stale_batch),
            verbose=args.verbose,
        )
        if args.json_out:
            args.json_out.parent.mkdir(parents=True, exist_ok=True)
            args.json_out.write_text(json.dumps(smoke, ensure_ascii=False, indent=2), encoding="utf-8")
        if smoke.get("ok"):
            print("Smoke check OK")
            print(f"  Manifest: {smoke.get('manifest_path')}")
            print(f"  Batch root: {smoke.get('batch_root')}")
            print(f"  Target date: {smoke.get('target_date')}")
            print(f"  Active chat: {smoke.get('active_chat_title') or args.chat_title}")
            raise SystemExit(0)
        print("Smoke check FAIL")
        for issue in smoke.get("issues", []):
            print(f"  - {issue['code']}: {issue['detail']}")
        if smoke.get("diagnostics_dir"):
            print(f"  Diagnostics: {smoke['diagnostics_dir']}")
        for step in smoke.get("recovery_ladder", []):
            print(f"  - recovery/{step.get('code')}: {step.get('detail')}")
        raise SystemExit(1)

    if args.resolve_unsure_filename:
        manifest = load_send_batch_manifest(args.today_folder, source_mode=args.bundle_source)
        ledger_path = Path(manifest["batch_root"]) / SEND_LEDGER_FILE
        ledger = load_send_ledger(ledger_path, manifest)
        pdf_key = resolve_unsure_ledger_entry(
            manifest,
            ledger,
            filename=str(args.resolve_unsure_filename),
            resolution=str(args.resolve_unsure_as),
            note=str(args.resolve_unsure_note or ""),
        )
        save_send_ledger(ledger_path, ledger)
        print("UNSURE ledger entry resolved")
        print(f"  Batch root: {manifest['batch_root']}")
        print(f"  PDF key: {pdf_key}")
        print(f"  Filename: {args.resolve_unsure_filename}")
        print(f"  New state: {args.resolve_unsure_as}")
        raise SystemExit(0)

    started_at = time.monotonic()
    results = run_sender(
        today_folder=args.today_folder,
        chat_title=args.chat_title,
        dry_run=args.dry_run,
        resume=not args.no_resume,
        bundle_source=args.bundle_source,
        send_delay=float(args.send_delay),
        status_messages=bool(args.status_messages),
        post_status_message_only=bool(args.post_status_message_only),
        expected_target_date=expected_target_date,
        allow_stale_batch=bool(args.allow_stale_batch),
        chrome_user_data_dir=args.chrome_user_data_dir,
        chrome_profile_directory=args.chrome_profile_directory,
        chrome_profile_name=args.chrome_profile_name,
        cdp_endpoint=args.cdp_endpoint,
        browser_mode=args.browser_mode,
        blocked_chat_titles=dedup_blocked,
        fail_fast=bool(args.fail_fast),
        allow_unsure_resume=bool(args.allow_unsure_resume),
        max_pdfs=args.max_pdfs,
        post_send_linger_seconds=float(args.linger_seconds or 0.0),
        verbose=args.verbose,
    )
    elapsed = max(0, int(time.monotonic() - started_at))
    mins, secs = divmod(elapsed, 60)

    if args.json_out:
        args.json_out.parent.mkdir(parents=True, exist_ok=True)
        args.json_out.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")

    print()
    print("=" * 60)
    print("  Results:")
    print(f"    Total PDFs: {results['total']}")
    print(f"    Sent: {results['sent']}")
    print(f"    Skipped (ledger-complete): {results['skipped']}")
    print(f"    Failed: {results['failed']}")
    print(f"    Halted: {'Yes' if results.get('halted') else 'No'}")
    print(f"    Halt reason: {results.get('halt_reason', '')}")
    print(f"    Status message failures: {results.get('status_message_failures', results['status_message_failed'])}")
    phase_failures = results.get("status_message_failures_by_phase") or {}
    if any(int(phase_failures.get(phase, 0) or 0) for phase in ("pre", "post")):
        print(
            "    Status message failure phases: "
            f"pre={int(phase_failures.get('pre', 0) or 0)}, "
            f"post={int(phase_failures.get('post', 0) or 0)}"
        )
    print(f"    Source root: {results.get('source_root', '')}")
    print(f"    Duration: {mins}m {secs}s")
    print("=" * 60)

    if results["failed"] > 0 or results.get("halted"):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
