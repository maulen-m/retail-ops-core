#!/usr/bin/env python3
from __future__ import annotations

import argparse
import errno
import fcntl
import json
import os
import sys
import time
from collections import Counter
from datetime import date, datetime
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.integrations.telegram_bot import (  # noqa: E402
    get_waybill_telegram_config,
    send_document,
    send_message,
)
from scripts import returns_pickup_report as returns_pickup_report_mod  # noqa: E402
from scripts.waybill_telegram_state import arm_passive_handover_watch  # noqa: E402
from scripts.send_waybills_whatsapp import (  # noqa: E402
    ALMATY_TZ,
    SOURCE_AUTO,
    SOURCE_CHOICES,
    SOURCE_MERGED,
    TODAY_FOLDER,
    _normalize_store_label,
    _store_stats_from_manifest,
    format_post_send_status_table,
    format_pre_send_status_table,
    load_send_batch_manifest,
    order_pdfs_for_sending,
    verify_send_batch_preflight,
)


TELEGRAM_SEND_LEDGER_FILE = "telegram_send_ledger.json"
TELEGRAM_SEND_STOPLINE_FILE = "telegram_send_stopline.json"
TELEGRAM_SEND_LOCK_FILE = ".telegram_send.lock"
TELEGRAM_LEDGER_STATES = {"pending", "api_started", "confirmed", "failed", "unsure"}
DEFAULT_SEND_DELAY_SECONDS = 3.5
DEFAULT_RATE_LIMIT_RETRIES = 3


def _now_iso() -> str:
    return datetime.now(ALMATY_TZ).isoformat()


def _default_ledger_entry(entry: dict[str, Any]) -> dict[str, Any]:
    return {
        "state": "pending",
        "last_updated": None,
        "history": [],
        "filename": entry.get("filename"),
        "relative_output_path": entry.get("relative_output_path"),
        "order_ids": list(entry.get("order_ids") or []),
    }


def load_telegram_ledger(ledger_path: Path, manifest: dict[str, Any]) -> dict[str, Any]:
    if ledger_path.exists():
        payload = json.loads(ledger_path.read_text(encoding="utf-8"))
        if str(payload.get("batch_hash") or "") != str(manifest.get("batch_hash") or ""):
            raise RuntimeError("Existing Telegram send ledger batch hash does not match current manifest")
    else:
        payload = {
            "schema_version": 1,
            "channel": "telegram",
            "batch_hash": manifest.get("batch_hash"),
            "batch_label": manifest.get("batch_label"),
            "manifest_path": str(manifest.get("manifest_path") or ""),
            "created_at": _now_iso(),
            "updated_at": _now_iso(),
            "entries": {},
        }
    payload.setdefault("schema_version", 1)
    payload.setdefault("channel", "telegram")
    payload.setdefault("batch_hash", manifest.get("batch_hash"))
    payload.setdefault("batch_label", manifest.get("batch_label"))
    payload.setdefault("manifest_path", str(manifest.get("manifest_path") or ""))
    payload.setdefault("created_at", _now_iso())
    payload.setdefault("updated_at", _now_iso())
    payload.setdefault("entries", {})
    for entry in manifest.get("entries") or []:
        payload["entries"].setdefault(str(entry["pdf_key"]), _default_ledger_entry(entry))
    return payload


def save_telegram_ledger(ledger_path: Path, ledger: dict[str, Any]) -> None:
    ledger["updated_at"] = _now_iso()
    temp_path = ledger_path.with_suffix(".tmp")
    temp_path.write_text(json.dumps(ledger, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temp_path.replace(ledger_path)


def _set_entry_state(
    ledger: dict[str, Any],
    pdf_key: str,
    state: str,
    *,
    note: str = "",
    extra: dict[str, Any] | None = None,
) -> None:
    if state not in TELEGRAM_LEDGER_STATES:
        raise ValueError(f"Unsupported Telegram ledger state: {state}")
    entry = ledger.setdefault("entries", {}).setdefault(pdf_key, {"history": []})
    entry["state"] = state
    entry["last_updated"] = _now_iso()
    if extra:
        entry.update(extra)
    entry.setdefault("history", []).append(
        {
            "state": state,
            "at": _now_iso(),
            "note": note,
        }
    )


def _confirmed_progress_snapshot(
    manifest_entries: list[dict[str, Any]],
    ledger: dict[str, Any],
) -> tuple[int, Counter[str]]:
    confirmed = 0
    orders_by_store: Counter[str] = Counter()
    ledger_entries = ledger.get("entries") or {}
    for entry in manifest_entries:
        pdf_key = str(entry.get("pdf_key") or "")
        if str(ledger_entries.get(pdf_key, {}).get("state") or "") != "confirmed":
            continue
        confirmed += 1
        for store_name, qty in dict(entry.get("order_counts_by_store") or {}).items():
            orders_by_store[_normalize_store_label(store_name)] += int(qty)
    return confirmed, orders_by_store


def _select_entries_for_telegram_send(
    manifest_entries: list[dict[str, Any]],
    ledger: dict[str, Any],
    *,
    resume: bool,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    if not resume:
        return list(manifest_entries), []
    selected: list[dict[str, Any]] = []
    blocked: list[dict[str, Any]] = []
    ledger_entries = ledger.get("entries") or {}
    for entry in manifest_entries:
        pdf_key = str(entry.get("pdf_key") or "")
        state = str(ledger_entries.get(pdf_key, {}).get("state") or "pending")
        if state == "confirmed":
            continue
        if state in {"unsure", "api_started"}:
            blocked.append(entry)
            continue
        if state in {"pending", "failed"}:
            selected.append(entry)
            continue
        blocked.append(entry)
    return selected, blocked


def _write_stopline(today_folder: Path, payload: dict[str, Any]) -> Path:
    output_path = Path(today_folder) / TELEGRAM_SEND_STOPLINE_FILE
    output_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return output_path


def _acquire_telegram_send_lock(batch_root: Path) -> tuple[Any | None, Path]:
    lock_path = Path(batch_root) / TELEGRAM_SEND_LOCK_FILE
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    handle = lock_path.open("a+", encoding="utf-8")
    try:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError as exc:
        handle.close()
        if exc.errno in {errno.EACCES, errno.EAGAIN}:
            return None, lock_path
        raise
    handle.seek(0)
    handle.truncate()
    handle.write(
        json.dumps(
            {
                "pid": os.getpid(),
                "locked_at": _now_iso(),
                "purpose": "telegram_waybill_send",
            },
            ensure_ascii=False,
        )
        + "\n"
    )
    handle.flush()
    return handle, lock_path


def _release_telegram_send_lock(handle: Any | None) -> None:
    if handle is None:
        return
    try:
        fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
    finally:
        handle.close()


def _format_caption(entry: dict[str, Any], *, index: int, total: int, batch_label: str) -> str:
    order_ids = ", ".join(str(value) for value in entry.get("order_ids") or [])
    filename = str(entry.get("filename") or Path(str(entry.get("path") or "")).name)
    return (
        f"<b>{index}/{total}</b> {filename}\n"
        f"<code>{batch_label}</code>\n"
        f"Orders: <code>{order_ids}</code>"
    )


def _send_document_with_rate_limit_retry(
    *,
    token: str,
    chat_id: str,
    document_path: Path,
    caption: str,
    timeout_seconds: int,
    max_retries: int = DEFAULT_RATE_LIMIT_RETRIES,
) -> dict[str, Any]:
    attempt = 0
    while True:
        result = send_document(
            token=token,
            chat_id=chat_id,
            document_path=document_path,
            caption=caption,
            timeout_seconds=timeout_seconds,
        )
        retry_after = result.get("retry_after")
        if result.get("success") or result.get("ambiguous") or retry_after is None or attempt >= max_retries:
            return result
        attempt += 1
        time.sleep(max(0, int(retry_after)))


def _send_message_with_rate_limit_retry(
    *,
    token: str,
    chat_id: str,
    text: str,
    timeout_seconds: int = 15,
    max_retries: int = DEFAULT_RATE_LIMIT_RETRIES,
    reply_markup: dict[str, Any] | None = None,
) -> dict[str, Any]:
    attempt = 0
    while True:
        result = send_message(
            token=token,
            chat_id=chat_id,
            text=text,
            timeout_seconds=timeout_seconds,
            reply_markup=reply_markup,
        )
        retry_after = result.get("retry_after")
        if result.get("success") or result.get("ambiguous") or retry_after is None or attempt >= max_retries:
            return result
        attempt += 1
        time.sleep(max(0, int(retry_after)))


def _base_report(*, today_folder: Path, bundle_source: str, expected_target_date: date | None) -> dict[str, Any]:
    return {
        "ok": False,
        "channel": "telegram",
        "today_folder": str(today_folder),
        "bundle_source": bundle_source,
        "expected_target_date": expected_target_date.isoformat() if expected_target_date else None,
        "source_root": "",
        "manifest_path": "",
        "ledger_path": "",
        "batch_hash": "",
        "total": 0,
        "sent": 0,
        "skipped": 0,
        "failed": 0,
        "confirmed_total": 0,
        "halted": False,
        "halt_reason": "",
        "fallback_allowed": False,
        "status_message_failures": 0,
        "pre_status_sent": False,
        "pre_status_message_id": "",
        "final_status_sent": False,
        "final_status_message_id": "",
        "returns_pickup_sent": False,
        "returns_pickup_message_id": "",
        "handover_watch_armed": False,
        "handover_watch_next_check_at": "",
        "started_at": _now_iso(),
        "completed_at": "",
    }


def _send_final_status_table_from_manifest(
    *,
    manifest: dict[str, Any],
    ledger: dict[str, Any],
    token: str,
    chat_id: str,
    timeout_seconds: int = 15,
) -> dict[str, Any]:
    entries = list(manifest.get("entries") or [])
    store_stats = _store_stats_from_manifest(manifest)
    confirmed_total, confirmed_orders_by_store = _confirmed_progress_snapshot(entries, ledger)
    post_status_text = format_post_send_status_table(
        store_stats,
        dict(confirmed_orders_by_store),
        bundles_target=len(entries),
        bundles_sent=confirmed_total,
    )
    status_result = _send_message_with_rate_limit_retry(
        token=token,
        chat_id=chat_id,
        text=post_status_text,
        timeout_seconds=timeout_seconds,
    )
    success = bool(status_result.get("success"))
    return {
        "ok": success,
        "final_status_sent": success,
        "final_status_message_id": str(status_result.get("message_id") or ""),
        "status_message_failures": 0 if success else 1,
        "error": str(status_result.get("error") or ""),
        "confirmed_total": confirmed_total,
        "total": len(entries),
    }


def _send_returns_pickup_message(
    *,
    token: str,
    chat_id: str,
    timeout_seconds: int = 15,
) -> dict[str, Any]:
    snapshot = returns_pickup_report_mod.build_pickup_ready_snapshot()
    message = returns_pickup_report_mod.format_returns_pickup_message(snapshot)
    reply_markup = returns_pickup_report_mod.build_returns_pickup_reply_markup(snapshot)
    status_result = _send_message_with_rate_limit_retry(
        token=token,
        chat_id=chat_id,
        text=message,
        timeout_seconds=timeout_seconds,
        reply_markup=reply_markup,
    )
    success = bool(status_result.get("success"))
    return {
        "ok": success,
        "returns_pickup_sent": success,
        "returns_pickup_message_id": str(status_result.get("message_id") or ""),
        "status_message_failures": 0 if success else 1,
        "error": str(status_result.get("error") or ""),
    }


def send_final_status_table(
    *,
    today_folder: Path = TODAY_FOLDER,
    bundle_source: str = SOURCE_MERGED,
    expected_target_date: date | None = None,
    token: str | None = None,
    chat_id: str | None = None,
    timeout_seconds: int = 15,
) -> dict[str, Any]:
    config = get_waybill_telegram_config(token=token, chat_id=chat_id)
    manifest = load_send_batch_manifest(
        Path(today_folder),
        source_mode=bundle_source,
    )
    if expected_target_date is not None and str(manifest.get("target_date") or "") != expected_target_date.isoformat():
        return {
            "ok": False,
            "final_status_sent": False,
            "final_status_message_id": "",
            "returns_pickup_sent": False,
            "returns_pickup_message_id": "",
            "status_message_failures": 1,
            "error": f"manifest target_date mismatch: {manifest.get('target_date')} != {expected_target_date.isoformat()}",
            "confirmed_total": 0,
            "total": len(manifest.get("entries") or []),
        }
    ledger = load_telegram_ledger(Path(str(manifest["batch_root"])) / TELEGRAM_SEND_LEDGER_FILE, manifest)
    result = _send_final_status_table_from_manifest(
        manifest=manifest,
        ledger=ledger,
        token=config["token"],
        chat_id=config["chat_id"],
        timeout_seconds=timeout_seconds,
    )
    returns_pickup = _send_returns_pickup_message(
        token=config["token"],
        chat_id=config["chat_id"],
        timeout_seconds=timeout_seconds,
    )
    result["ok"] = bool(result.get("ok")) and bool(returns_pickup.get("ok"))
    result["returns_pickup_sent"] = bool(returns_pickup.get("returns_pickup_sent"))
    result["returns_pickup_message_id"] = str(returns_pickup.get("returns_pickup_message_id") or "")
    result["status_message_failures"] = int(result.get("status_message_failures") or 0) + int(
        returns_pickup.get("status_message_failures") or 0
    )
    if returns_pickup.get("error"):
        result["returns_pickup_error"] = str(returns_pickup.get("error") or "")
    return result


def run_sender(
    *,
    today_folder: Path = TODAY_FOLDER,
    bundle_source: str = SOURCE_MERGED,
    expected_target_date: date | None = None,
    token: str | None = None,
    chat_id: str | None = None,
    dry_run: bool = False,
    resume: bool = True,
    status_messages: bool = True,
    send_delay: float = DEFAULT_SEND_DELAY_SECONDS,
    fail_fast: bool = True,
    max_pdfs: int | None = None,
    timeout_seconds: int = 60,
    verbose: bool = False,
) -> dict[str, Any]:
    today_folder = Path(today_folder)
    report = _base_report(
        today_folder=today_folder,
        bundle_source=bundle_source,
        expected_target_date=expected_target_date,
    )

    preflight = verify_send_batch_preflight(
        today_folder,
        source_mode=bundle_source,
        expected_target_date=expected_target_date,
    )
    if not preflight.get("ok"):
        report.update(
            {
                "failed": 1,
                "halted": True,
                "halt_reason": "MANIFEST_PREFLIGHT_RED",
                "preflight": preflight,
                "fallback_allowed": False,
                "completed_at": _now_iso(),
            }
        )
        _write_stopline(today_folder, report)
        return report

    try:
        config = get_waybill_telegram_config(token=token, chat_id=chat_id)
    except ValueError as exc:
        report.update(
            {
                "failed": 1,
                "halted": True,
                "halt_reason": "TELEGRAM_CONFIG",
                "error": str(exc),
                "fallback_allowed": True,
                "completed_at": _now_iso(),
            }
        )
        return report

    manifest = load_send_batch_manifest(today_folder, source_mode=bundle_source)
    batch_root = Path(str(manifest["batch_root"]))
    ledger_path = batch_root / TELEGRAM_SEND_LEDGER_FILE
    report.update(
        {
            "source_root": str(batch_root),
            "manifest_path": str(manifest.get("manifest_path") or ""),
            "ledger_path": str(ledger_path),
            "batch_hash": str(manifest.get("batch_hash") or ""),
        }
    )

    lock_handle, lock_path = _acquire_telegram_send_lock(batch_root)
    report["lock_path"] = str(lock_path)
    if lock_handle is None:
        report.update(
            {
                "failed": 1,
                "halted": True,
                "halt_reason": "TELEGRAM_SEND_LOCKED",
                "fallback_allowed": False,
                "completed_at": _now_iso(),
            }
        )
        _write_stopline(today_folder, report)
        return report

    try:
        return _run_sender_with_lock(
            today_folder=today_folder,
            bundle_source=bundle_source,
            expected_target_date=expected_target_date,
            config=config,
            manifest=manifest,
            batch_root=batch_root,
            ledger_path=ledger_path,
            report=report,
            dry_run=dry_run,
            resume=resume,
            status_messages=status_messages,
            send_delay=send_delay,
            fail_fast=fail_fast,
            max_pdfs=max_pdfs,
            timeout_seconds=timeout_seconds,
            verbose=verbose,
        )
    finally:
        _release_telegram_send_lock(lock_handle)


def _run_sender_with_lock(
    *,
    today_folder: Path,
    bundle_source: str,
    expected_target_date: date | None,
    config: dict[str, str],
    manifest: dict[str, Any],
    batch_root: Path,
    ledger_path: Path,
    report: dict[str, Any],
    dry_run: bool,
    resume: bool,
    status_messages: bool,
    send_delay: float,
    fail_fast: bool,
    max_pdfs: int | None,
    timeout_seconds: int,
    verbose: bool,
) -> dict[str, Any]:
    ledger_path = batch_root / TELEGRAM_SEND_LEDGER_FILE
    ledger = load_telegram_ledger(ledger_path, manifest)
    save_telegram_ledger(ledger_path, ledger)

    entries = list(manifest.get("entries") or [])
    ordered_entries = order_pdfs_for_sending(entries)
    selected_entries, blocked_entries = _select_entries_for_telegram_send(
        ordered_entries,
        ledger,
        resume=resume,
    )
    if max_pdfs is not None:
        selected_entries = selected_entries[: max(0, int(max_pdfs))]

    confirmed_before, confirmed_orders_by_store = _confirmed_progress_snapshot(entries, ledger)
    if not resume:
        confirmed_before = 0
        confirmed_orders_by_store = Counter()
    store_stats = _store_stats_from_manifest(manifest)
    report.update(
        {
            "total": len(entries),
            "skipped": max(0, len(entries) - len(selected_entries) - len(blocked_entries)),
            "confirmed_total": confirmed_before,
        }
    )

    if blocked_entries:
        report.update(
            {
                "failed": len(blocked_entries),
                "halted": True,
                "halt_reason": "TELEGRAM_UNRESOLVED_LEDGER",
                "blocked_filenames": [entry.get("filename") for entry in blocked_entries],
                "fallback_allowed": False,
                "completed_at": _now_iso(),
            }
        )
        _write_stopline(today_folder, report)
        return report

    if not selected_entries:
        report.update({"ok": True, "fallback_allowed": False, "completed_at": _now_iso()})
        return report

    sent_orders_by_store = Counter(confirmed_orders_by_store)
    batch_label = str(manifest.get("batch_label") or batch_root.name)
    pre_status_text = format_pre_send_status_table(store_stats, bundles_target=len(selected_entries))

    if status_messages and not dry_run:
        status_result = _send_message_with_rate_limit_retry(
            token=config["token"],
            chat_id=config["chat_id"],
            text=pre_status_text,
        )
        if status_result.get("success"):
            report["pre_status_sent"] = True
            report["pre_status_message_id"] = str(status_result.get("message_id") or "")
        else:
            report["status_message_failures"] = int(report.get("status_message_failures") or 0) + 1
            if verbose:
                print(f"WARNING: Telegram pre-status message failed: {status_result.get('error')}")

    for index, entry in enumerate(selected_entries, start=1):
        pdf_key = str(entry["pdf_key"])
        pdf_path = Path(entry["path"])
        manifest_index = int(entry.get("send_sequence") or index)
        if dry_run:
            report["sent"] = int(report["sent"]) + 1
            continue

        _set_entry_state(ledger, pdf_key, "api_started", note="telegram_send_document_started")
        save_telegram_ledger(ledger_path, ledger)
        result = _send_document_with_rate_limit_retry(
            token=config["token"],
            chat_id=config["chat_id"],
            document_path=pdf_path,
            caption=_format_caption(entry, index=manifest_index, total=len(entries), batch_label=batch_label),
            timeout_seconds=timeout_seconds,
        )
        if result.get("success"):
            _set_entry_state(
                ledger,
                pdf_key,
                "confirmed",
                note="telegram_send_document_confirmed",
                extra={
                    "telegram_message_id": str(result.get("message_id") or ""),
                    "telegram_chat_id": str(result.get("chat_id") or config["chat_id"]),
                    "telegram_date": result.get("date"),
                    "telegram_file_id": str(result.get("file_id") or ""),
                    "telegram_file_unique_id": str(result.get("file_unique_id") or ""),
                },
            )
            save_telegram_ledger(ledger_path, ledger)
            report["sent"] = int(report["sent"]) + 1
            report["confirmed_total"] = int(report["confirmed_total"]) + 1
            for store_name, qty in dict(entry.get("order_counts_by_store") or {}).items():
                sent_orders_by_store[_normalize_store_label(store_name)] += int(qty)
            if send_delay > 0 and index < len(selected_entries):
                time.sleep(send_delay)
            continue

        report["failed"] = int(report["failed"]) + 1
        if result.get("ambiguous"):
            _set_entry_state(
                ledger,
                pdf_key,
                "unsure",
                note=str(result.get("error") or "ambiguous Telegram send failure"),
            )
            report["halt_reason"] = "TELEGRAM_UNSURE"
        else:
            _set_entry_state(
                ledger,
                pdf_key,
                "failed",
                note=str(result.get("error") or "Telegram send failed"),
            )
            report["halt_reason"] = "TELEGRAM_SEND_FAILED"
        save_telegram_ledger(ledger_path, ledger)
        report["halted"] = True
        if fail_fast:
            break

    if dry_run:
        report.update({"ok": True, "confirmed_total": confirmed_before, "completed_at": _now_iso()})
        return report

    if status_messages:
        final_status = _send_final_status_table_from_manifest(
            manifest=manifest,
            ledger=ledger,
            token=config["token"],
            chat_id=config["chat_id"],
        )
        report["final_status_sent"] = bool(final_status.get("final_status_sent"))
        report["final_status_message_id"] = str(final_status.get("final_status_message_id") or "")
        report["status_message_failures"] = int(report.get("status_message_failures") or 0) + int(
            final_status.get("status_message_failures") or 0
        )
        returns_pickup = _send_returns_pickup_message(
            token=config["token"],
            chat_id=config["chat_id"],
        )
        report["returns_pickup_sent"] = bool(returns_pickup.get("returns_pickup_sent"))
        report["returns_pickup_message_id"] = str(returns_pickup.get("returns_pickup_message_id") or "")
        report["status_message_failures"] = int(report.get("status_message_failures") or 0) + int(
            returns_pickup.get("status_message_failures") or 0
        )
        if not final_status.get("ok"):
            if verbose:
                print(f"WARNING: Telegram post-status message failed: {final_status.get('error')}")

    report["ok"] = int(report["failed"]) == 0 and not report["halted"]
    report["fallback_allowed"] = (
        not report["ok"]
        and int(report["sent"]) == 0
        and int(report["confirmed_total"]) == 0
        and str(report.get("halt_reason") or "") not in {"MANIFEST_PREFLIGHT_RED", "TELEGRAM_UNSURE"}
    )
    if report["ok"] and status_messages and (report.get("final_status_sent") or report.get("returns_pickup_sent")):
        target_date = expected_target_date
        if target_date is None:
            try:
                target_date = date.fromisoformat(str(manifest.get("target_date") or ""))
            except ValueError:
                target_date = datetime.now(ALMATY_TZ).date()
        try:
            watch = arm_passive_handover_watch(
                chat_id=str(config["chat_id"]),
                target_date=target_date,
                source_batch_label=batch_label,
            )
            report["handover_watch_armed"] = bool(watch.get("armed"))
            report["handover_watch_next_check_at"] = str(watch.get("next_check_at") or "")
        except Exception as exc:
            report["handover_watch_armed"] = False
            report["handover_watch_error"] = str(exc)
    report["completed_at"] = _now_iso()
    if not report["ok"]:
        _write_stopline(today_folder, report)
    return report


def build_ordered_resend_proof(
    *,
    today_folder: Path = TODAY_FOLDER,
    bundle_source: str = SOURCE_MERGED,
    started_at: str,
) -> dict[str, Any]:
    """Prove the latest Telegram resend matches the manifest send sequence."""
    manifest = load_send_batch_manifest(Path(today_folder), source_mode=bundle_source)
    batch_root = Path(str(manifest["batch_root"]))
    ledger_path = batch_root / TELEGRAM_SEND_LEDGER_FILE
    ledger = load_telegram_ledger(ledger_path, manifest)
    ordered_entries = order_pdfs_for_sending(list(manifest.get("entries") or []))
    ledger_entries = ledger.get("entries") or {}

    rows: list[dict[str, Any]] = []
    issues: list[dict[str, Any]] = []
    for expected_index, entry in enumerate(ordered_entries, start=1):
        pdf_key = str(entry.get("pdf_key") or "")
        ledger_entry = dict(ledger_entries.get(pdf_key) or {})
        filename = str(entry.get("filename") or "")
        state = str(ledger_entry.get("state") or "")
        last_updated = str(ledger_entry.get("last_updated") or "")
        message_id_raw = str(ledger_entry.get("telegram_message_id") or "").strip()
        if state != "confirmed":
            issues.append({"code": "entry_not_confirmed", "detail": filename})
            continue
        if started_at and last_updated < started_at:
            issues.append({"code": "entry_not_confirmed_in_current_resend", "detail": filename})
            continue
        try:
            message_id = int(message_id_raw)
        except ValueError:
            issues.append({"code": "entry_message_id_invalid", "detail": f"{filename}: {message_id_raw!r}"})
            continue
        rows.append(
            {
                "expected_index": expected_index,
                "pdf_key": pdf_key,
                "filename": filename,
                "telegram_message_id": message_id,
                "last_updated": last_updated,
            }
        )

    expected_keys = [str(entry.get("pdf_key") or "") for entry in ordered_entries]
    actual_by_message_id = sorted(rows, key=lambda row: int(row["telegram_message_id"]))
    actual_keys = [str(row.get("pdf_key") or "") for row in actual_by_message_id]
    sequence_match = actual_keys == expected_keys
    if rows and len({int(row["telegram_message_id"]) for row in rows}) != len(rows):
        issues.append({"code": "telegram_message_id_duplicate", "detail": "duplicate message ids in resend proof"})
    if not sequence_match:
        issues.append({"code": "telegram_message_sequence_mismatch", "detail": "message-id order differs from manifest order"})

    message_ids = [int(row["telegram_message_id"]) for row in rows]
    return {
        "ok": not issues,
        "sequence_match": sequence_match,
        "issues": issues,
        "manifest_path": str(manifest.get("manifest_path") or ""),
        "batch_root": str(batch_root),
        "batch_label": str(manifest.get("batch_label") or batch_root.name),
        "expected_count": len(ordered_entries),
        "current_resend_confirmed_count": len(rows),
        "message_id_min": min(message_ids) if message_ids else None,
        "message_id_max": max(message_ids) if message_ids else None,
        "first": actual_by_message_id[:3],
        "last": actual_by_message_id[-3:],
    }


def run_ordered_full_resend(
    *,
    today_folder: Path = TODAY_FOLDER,
    bundle_source: str = SOURCE_MERGED,
    expected_target_date: date | None = None,
    token: str | None = None,
    chat_id: str | None = None,
    send_delay: float = DEFAULT_SEND_DELAY_SECONDS,
    fail_fast: bool = True,
    timeout_seconds: int = 60,
    verbose: bool = False,
) -> dict[str, Any]:
    """Live recovery path: resend the whole current manifest once in manifest order."""
    report = run_sender(
        today_folder=today_folder,
        bundle_source=bundle_source,
        expected_target_date=expected_target_date,
        token=token,
        chat_id=chat_id,
        dry_run=False,
        resume=False,
        status_messages=False,
        send_delay=send_delay,
        fail_fast=fail_fast,
        max_pdfs=None,
        timeout_seconds=timeout_seconds,
        verbose=verbose,
    )
    proof = build_ordered_resend_proof(
        today_folder=today_folder,
        bundle_source=bundle_source,
        started_at=str(report.get("started_at") or ""),
    )
    report["ordered_resend_proof"] = proof
    if not proof.get("ok"):
        report["ok"] = False
        report["halted"] = True
        report["halt_reason"] = "ORDERED_RESEND_SEQUENCE_PROOF_FAILED"
    return report


def _parse_iso_date(value: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f"Invalid ISO date {value!r}; expected YYYY-MM-DD") from exc


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Send waybill PDFs to Telegram via Bot API")
    parser.add_argument("--today-folder", type=Path, default=TODAY_FOLDER)
    parser.add_argument("--bundle-source", choices=SOURCE_CHOICES, default=SOURCE_AUTO)
    parser.add_argument("--expected-target-date", type=_parse_iso_date, default=None)
    parser.add_argument("--telegram-token", type=str, default=None)
    parser.add_argument("--telegram-chat-id", type=str, default=None)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--no-resume", action="store_true")
    parser.add_argument("--send-delay", type=float, default=DEFAULT_SEND_DELAY_SECONDS)
    parser.add_argument("--status-messages", dest="status_messages", action="store_true", default=True)
    parser.add_argument("--no-status-messages", dest="status_messages", action="store_false")
    parser.add_argument("--fail-fast", action="store_true", default=True)
    parser.add_argument("--preflight-only", action="store_true")
    parser.add_argument("--ordered-full-resend", action="store_true")
    parser.add_argument("--confirm-resend", action="store_true")
    parser.add_argument("--max-pdfs", type=int, default=None)
    parser.add_argument("--timeout-seconds", type=int, default=60)
    parser.add_argument("--json-out", type=Path, default=None)
    parser.add_argument("--verbose", "-v", action="store_true")
    args = parser.parse_args(argv)

    expected_target_date = args.expected_target_date or datetime.now(ALMATY_TZ).date()
    if args.preflight_only:
        preflight = verify_send_batch_preflight(
            args.today_folder,
            source_mode=args.bundle_source,
            expected_target_date=expected_target_date,
        )
        try:
            config = get_waybill_telegram_config(
                token=args.telegram_token,
                chat_id=args.telegram_chat_id,
            )
            preflight["telegram_config_ok"] = True
            preflight["telegram_chat_id"] = config["chat_id"]
        except ValueError as exc:
            preflight["telegram_config_ok"] = False
            preflight.setdefault("issues", []).append(
                {"code": "telegram_config_missing", "detail": str(exc)}
            )
            preflight["ok"] = False
        if args.json_out:
            args.json_out.parent.mkdir(parents=True, exist_ok=True)
            args.json_out.write_text(json.dumps(preflight, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(json.dumps(preflight, ensure_ascii=False, indent=2))
        return 0 if preflight.get("ok") else 1

    if args.ordered_full_resend:
        if not args.confirm_resend:
            report = {
                "ok": False,
                "halted": True,
                "halt_reason": "ORDERED_RESEND_REQUIRES_CONFIRM",
                "error": "Pass --confirm-resend to perform a live ordered full resend.",
            }
            if args.json_out:
                args.json_out.parent.mkdir(parents=True, exist_ok=True)
                args.json_out.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            print(json.dumps(report, ensure_ascii=False, indent=2))
            return 2
        report = run_ordered_full_resend(
            today_folder=args.today_folder,
            bundle_source=args.bundle_source,
            expected_target_date=expected_target_date,
            token=args.telegram_token,
            chat_id=args.telegram_chat_id,
            send_delay=float(args.send_delay),
            fail_fast=bool(args.fail_fast),
            timeout_seconds=int(args.timeout_seconds),
            verbose=bool(args.verbose),
        )
        if args.json_out:
            args.json_out.parent.mkdir(parents=True, exist_ok=True)
            args.json_out.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0 if report.get("ok") else 1

    report = run_sender(
        today_folder=args.today_folder,
        bundle_source=args.bundle_source,
        expected_target_date=expected_target_date,
        token=args.telegram_token,
        chat_id=args.telegram_chat_id,
        dry_run=bool(args.dry_run),
        resume=not args.no_resume,
        status_messages=bool(args.status_messages),
        send_delay=float(args.send_delay),
        fail_fast=bool(args.fail_fast),
        max_pdfs=args.max_pdfs,
        timeout_seconds=int(args.timeout_seconds),
        verbose=bool(args.verbose),
    )
    if args.json_out:
        args.json_out.parent.mkdir(parents=True, exist_ok=True)
        args.json_out.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
