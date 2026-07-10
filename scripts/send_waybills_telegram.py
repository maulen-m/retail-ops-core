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
from scripts.waybill_telegram_state import arm_passive_handover_watch  # noqa: E402
from scripts.google_ops_board_automation_common import (  # noqa: E402
    DEFAULT_CLOSEOUT_HALT_BARRIER_PATH,
    evaluate_closeout_halt_barrier,
)
from scripts.waybill_send_policy import blocked_live_action_for_manifest  # noqa: E402
from scripts.send_waybills_whatsapp import (  # noqa: E402
    ALMATY_TZ,
    SOURCE_AUTO,
    SOURCE_CHOICES,
    SOURCE_MERGED,
    TODAY_FOLDER,
    _hash_file,
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
CLOSEOUT_HALT_BARRIER_PATH = DEFAULT_CLOSEOUT_HALT_BARRIER_PATH


def _now_iso() -> str:
    return datetime.now(ALMATY_TZ).isoformat()


def _manifest_halt_gate(manifest: dict[str, Any]) -> dict[str, Any]:
    target_raw = str(manifest.get("target_date") or "").strip()
    request_identity = dict(manifest.get("request_identity") or {})
    ready_set_at = str(request_identity.get("ready_set_at") or "").strip()
    try:
        target_date = date.fromisoformat(target_raw)
    except ValueError:
        return {
            "blocked": True,
            "reason": "HALT_GATE_MANIFEST_TARGET_DATE_INVALID",
        }
    try:
        return evaluate_closeout_halt_barrier(
            target_date=target_date,
            run_control_row={
                "target_date": target_raw,
                "ready_for_closeout": "READY",
                "ready_set_at": ready_set_at,
            },
            request_ready_set_at=ready_set_at,
            path=CLOSEOUT_HALT_BARRIER_PATH,
            persist_safe_transition=False,
        )
    except Exception as exc:
        return {
            "blocked": True,
            "reason": "HALT_BARRIER_REREAD_FAILED",
            "detail": f"{type(exc).__name__}: {exc}",
        }


def _halt_barrier_send_result(manifest: dict[str, Any]) -> dict[str, Any] | None:
    gate = _manifest_halt_gate(manifest)
    if not bool(gate.get("blocked")):
        return None
    gate_reason = str(gate.get("reason") or "HALT_BARRIER_ACTIVE")
    detail = str(gate.get("detail") or "").strip()
    error = f"local halt barrier blocks Telegram external send: {gate_reason}"
    if detail:
        error = f"{error}: {detail}"
    return {
        "success": False,
        "ambiguous": False,
        "halted": True,
        "halt_reason": "TELEGRAM_HALT_BARRIER",
        "halt_gate_reason": gate_reason,
        "error": error,
    }


def _default_ledger_entry(entry: dict[str, Any]) -> dict[str, Any]:
    return {
        "state": "pending",
        "last_updated": None,
        "history": [],
        "filename": entry.get("filename"),
        "relative_output_path": entry.get("relative_output_path"),
        "order_ids": list(entry.get("order_ids") or []),
    }


def load_telegram_ledger(
    ledger_path: Path,
    manifest: dict[str, Any],
    *,
    chat_id: str | None = None,
) -> dict[str, Any]:
    expected_chat_id = str(chat_id or "").strip()
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
            "telegram_chat_id": expected_chat_id,
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
    pinned_chat_id = str(payload.get("telegram_chat_id") or "").strip()
    attempted = any(
        str(entry.get("state") or "pending") != "pending"
        or bool(entry.get("history"))
        for entry in dict(payload.get("entries") or {}).values()
    )
    if not pinned_chat_id:
        if attempted:
            raise RuntimeError(
                "Existing Telegram send ledger has attempt evidence but no pinned chat identity"
            )
        if not expected_chat_id:
            raise RuntimeError("Telegram send ledger chat identity is missing")
        pinned_chat_id = expected_chat_id
        payload["telegram_chat_id"] = pinned_chat_id
    elif expected_chat_id and pinned_chat_id != expected_chat_id:
        raise RuntimeError(
            "Configured Telegram chat does not match the batch-pinned chat identity"
        )
    for entry in manifest.get("entries") or []:
        payload["entries"].setdefault(str(entry["pdf_key"]), _default_ledger_entry(entry))
    for pdf_key, entry in dict(payload.get("entries") or {}).items():
        if str(entry.get("state") or "pending") != "confirmed":
            continue
        entry_chat_id = str(entry.get("telegram_chat_id") or "").strip()
        if entry_chat_id != pinned_chat_id:
            raise RuntimeError(
                f"Confirmed Telegram ledger entry target mismatch: {pdf_key}"
            )
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
    previous_state = str(entry.get("state") or "pending")
    if previous_state == "confirmed":
        if state != "confirmed":
            raise RuntimeError(f"Confirmed Telegram ledger entry is immutable: {pdf_key}")
        return
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
    # One channel-wide lock under MERGED/SEND prevents two distinct batch
    # directories for the same READY request from sending concurrently.
    lock_path = Path(batch_root).parent / TELEGRAM_SEND_LOCK_FILE
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


def _locked_artifact_issue(
    *,
    manifest: dict[str, Any],
    expected_manifest_sha256: str,
    entry: dict[str, Any] | None = None,
) -> str:
    manifest_path = Path(str(manifest.get("manifest_path") or ""))
    try:
        if _hash_file(manifest_path) != expected_manifest_sha256:
            return "manifest_bytes_changed_after_preflight"
    except OSError as exc:
        return f"manifest_reread_failed:{exc}"
    if entry is None:
        return ""
    pdf_path = Path(str(entry.get("path") or ""))
    try:
        if int(entry.get("file_size") or 0) != int(pdf_path.stat().st_size):
            return f"pdf_size_changed_after_preflight:{pdf_path.name}"
        if _hash_file(pdf_path) != str(entry.get("sha256") or ""):
            return f"pdf_hash_changed_after_preflight:{pdf_path.name}"
    except OSError as exc:
        return f"pdf_reread_failed:{pdf_path.name}:{exc}"
    return ""


def _other_batch_attempt_reason(
    *,
    batch_root: Path,
    manifest: dict[str, Any],
) -> str:
    expected_target_date = str(manifest.get("target_date") or "").strip()
    send_root = Path(batch_root).parent
    for candidate_manifest_path in sorted(send_root.glob("*/send_batch_manifest.json")):
        if candidate_manifest_path.parent.resolve() == Path(batch_root).resolve():
            continue
        candidate_ledger_path = candidate_manifest_path.parent / TELEGRAM_SEND_LEDGER_FILE
        try:
            candidate_manifest = json.loads(candidate_manifest_path.read_text(encoding="utf-8"))
        except Exception as exc:
            return f"unreadable_sibling_manifest:{candidate_manifest_path}:{exc}"
        candidate_target_date = str(candidate_manifest.get("target_date") or "").strip()
        if not candidate_target_date:
            return f"missing_sibling_target_date:{candidate_manifest_path}"
        if candidate_target_date != expected_target_date:
            continue
        if not candidate_ledger_path.is_file():
            return f"missing_same_target_date_sibling_telegram_ledger:{candidate_ledger_path}"
        try:
            candidate_ledger = json.loads(candidate_ledger_path.read_text(encoding="utf-8"))
        except Exception as exc:
            return f"unreadable_sibling_attempt_ledger:{candidate_ledger_path}:{exc}"
        entries = candidate_ledger.get("entries")
        if not isinstance(entries, dict):
            return f"malformed_sibling_attempt_ledger:{candidate_ledger_path}"
        for pdf_key, raw_entry in entries.items():
            if not isinstance(raw_entry, dict):
                return f"malformed_sibling_attempt_entry:{candidate_ledger_path}:{pdf_key}"
            if (
                str(raw_entry.get("state") or "pending") != "pending"
                or bool(raw_entry.get("history"))
            ):
                return (
                    f"same_target_date_attempt_in_other_batch:{candidate_manifest_path}:"
                    f"{pdf_key}:{raw_entry.get('state') or 'pending'}"
                )
    return ""


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
    manifest: dict[str, Any],
    max_retries: int = DEFAULT_RATE_LIMIT_RETRIES,
) -> dict[str, Any]:
    attempt = 0
    while True:
        halted_result = _halt_barrier_send_result(manifest)
        if halted_result is not None:
            return halted_result
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
    manifest: dict[str, Any],
    timeout_seconds: int = 15,
    max_retries: int = DEFAULT_RATE_LIMIT_RETRIES,
    reply_markup: dict[str, Any] | None = None,
) -> dict[str, Any]:
    attempt = 0
    while True:
        halted_result = _halt_barrier_send_result(manifest)
        if halted_result is not None:
            return halted_result
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
        manifest=manifest,
        timeout_seconds=timeout_seconds,
    )
    success = bool(status_result.get("success"))
    return {
        "ok": success,
        "halted": bool(status_result.get("halted")),
        "halt_reason": str(status_result.get("halt_reason") or ""),
        "halt_gate_reason": str(status_result.get("halt_gate_reason") or ""),
        "fallback_allowed": False,
        "final_status_sent": success,
        "final_status_message_id": str(status_result.get("message_id") or ""),
        "status_message_failures": 0 if success else 1,
        "error": str(status_result.get("error") or ""),
        "confirmed_total": confirmed_total,
        "total": len(entries),
    }


def send_final_status_table(
    *,
    today_folder: Path = TODAY_FOLDER,
    bundle_source: str = SOURCE_MERGED,
    expected_target_date: date | None = None,
    token: str | None = None,
    chat_id: str | None = None,
    timeout_seconds: int = 15,
    manifest_path: Path | None = None,
) -> dict[str, Any]:
    manifest = load_send_batch_manifest(
        Path(today_folder),
        source_mode=bundle_source,
        manifest_path=manifest_path,
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
    blocked = blocked_live_action_for_manifest(
        manifest,
        action="telegram_batch_status_message",
    )
    if blocked is not None:
        return {
            "ok": False,
            "final_status_sent": False,
            "final_status_message_id": "",
            "returns_pickup_sent": False,
            "returns_pickup_message_id": "",
            "status_message_failures": 1,
            "error": f"TARGET_DATE_SEND_EXCLUDED: {blocked.get('reason')}",
            "confirmed_total": 0,
            "total": len(manifest.get("entries") or []),
        }
    config = get_waybill_telegram_config(token=token, chat_id=chat_id)
    ledger = load_telegram_ledger(
        Path(str(manifest["batch_root"])) / TELEGRAM_SEND_LEDGER_FILE,
        manifest,
        chat_id=config["chat_id"],
    )
    result = _send_final_status_table_from_manifest(
        manifest=manifest,
        ledger=ledger,
        token=config["token"],
        chat_id=config["chat_id"],
        timeout_seconds=timeout_seconds,
    )
    result["returns_pickup_sent"] = False
    result["returns_pickup_message_id"] = ""
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
    manifest_path: Path | None = None,
    expected_manifest_sha256: str = "",
) -> dict[str, Any]:
    today_folder = Path(today_folder)
    report = _base_report(
        today_folder=today_folder,
        bundle_source=bundle_source,
        expected_target_date=expected_target_date,
    )

    required_manifest_sha256 = str(expected_manifest_sha256 or "").strip().lower()
    if not dry_run and (
        manifest_path is None
        or len(required_manifest_sha256) != 64
        or any(char not in "0123456789abcdef" for char in required_manifest_sha256)
    ):
        report.update(
            {
                "failed": 1,
                "halted": True,
                "halt_reason": "MANIFEST_PIN_REQUIRED",
                "error": "live Telegram send requires explicit manifest path and SHA-256",
                "fallback_allowed": False,
                "completed_at": _now_iso(),
            }
        )
        _write_stopline(today_folder, report)
        return report

    try:
        selected_manifest = load_send_batch_manifest(
            today_folder,
            source_mode=bundle_source,
            manifest_path=manifest_path,
        )
    except Exception as exc:
        report.update(
            {
                "failed": 1,
                "halted": True,
                "halt_reason": "MANIFEST_PREFLIGHT_RED",
                "preflight": {
                    "ok": False,
                    "issues": [{"code": "manifest_unavailable", "detail": str(exc)}],
                },
                "fallback_allowed": False,
                "completed_at": _now_iso(),
            }
        )
        _write_stopline(today_folder, report)
        return report

    explicit_manifest_path = Path(str(selected_manifest["manifest_path"]))
    batch_root = Path(str(selected_manifest["batch_root"]))
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
        preflight = verify_send_batch_preflight(
            today_folder,
            source_mode=bundle_source,
            expected_target_date=expected_target_date,
            manifest_path=explicit_manifest_path,
            require_autonomous_manifest=not dry_run,
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
        manifest = load_send_batch_manifest(
            today_folder,
            source_mode=bundle_source,
            manifest_path=explicit_manifest_path,
        )
        observed_manifest_sha256 = str(preflight.get("manifest_sha256") or "")
        if (
            str(manifest.get("_manifest_file_sha256") or "") != observed_manifest_sha256
            or (
                not dry_run
                and required_manifest_sha256 != observed_manifest_sha256
            )
        ):
            report.update(
                {
                    "failed": 1,
                    "halted": True,
                    "halt_reason": "MANIFEST_TOCTOU",
                    "fallback_allowed": False,
                    "completed_at": _now_iso(),
                }
            )
            _write_stopline(today_folder, report)
            return report
        if not dry_run:
            blocked = blocked_live_action_for_manifest(
                manifest,
                action="telegram_pdf_send",
            )
            if blocked is not None:
                report.update(
                    {
                        "failed": 1,
                        "halted": True,
                        "halt_reason": "TARGET_DATE_SEND_EXCLUDED",
                        "error": str(
                            blocked.get("reason")
                            or "Manifest target date is excluded from live delivery"
                        ),
                        "fallback_allowed": False,
                        "completed_at": _now_iso(),
                    }
                )
                _write_stopline(today_folder, report)
                return report
            prior_attempt_reason = _other_batch_attempt_reason(
                batch_root=batch_root,
                manifest=manifest,
            )
            if prior_attempt_reason:
                report.update(
                    {
                        "failed": 1,
                        "halted": True,
                        "halt_reason": "TELEGRAM_PRIOR_REQUEST_ATTEMPT",
                        "error": prior_attempt_reason,
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
        ledger_path = batch_root / TELEGRAM_SEND_LEDGER_FILE
        report.update(
            {
                "source_root": str(batch_root),
                "manifest_path": str(explicit_manifest_path),
                "manifest_sha256": observed_manifest_sha256,
                "ledger_path": str(ledger_path),
                "batch_hash": str(manifest.get("batch_hash") or ""),
            }
        )
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
            expected_manifest_sha256=observed_manifest_sha256,
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
    expected_manifest_sha256: str,
) -> dict[str, Any]:
    ledger_path = batch_root / TELEGRAM_SEND_LEDGER_FILE
    try:
        ledger = load_telegram_ledger(
            ledger_path,
            manifest,
            chat_id=config["chat_id"],
        )
        save_telegram_ledger(ledger_path, ledger)
    except Exception as exc:
        report.update(
            {
                "failed": 1,
                "halted": True,
                "halt_reason": "TELEGRAM_LEDGER_IDENTITY",
                "error": str(exc),
                "fallback_allowed": False,
                "completed_at": _now_iso(),
            }
        )
        _write_stopline(today_folder, report)
        return report

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
        artifact_issue = _locked_artifact_issue(
            manifest=manifest,
            expected_manifest_sha256=expected_manifest_sha256,
        )
        if artifact_issue:
            report.update(
                {
                    "failed": 1,
                    "halted": True,
                    "halt_reason": "MANIFEST_TOCTOU",
                    "error": artifact_issue,
                    "completed_at": _now_iso(),
                }
            )
            _write_stopline(today_folder, report)
            return report
        status_result = _send_message_with_rate_limit_retry(
            token=config["token"],
            chat_id=config["chat_id"],
            text=pre_status_text,
            manifest=manifest,
        )
        if status_result.get("halted"):
            report.update(
                {
                    "halted": True,
                    "halt_reason": str(
                        status_result.get("halt_reason") or "TELEGRAM_HALT_BARRIER"
                    ),
                    "halt_gate_reason": str(status_result.get("halt_gate_reason") or ""),
                    "error": str(status_result.get("error") or ""),
                    "fallback_allowed": False,
                    "completed_at": _now_iso(),
                }
            )
            _write_stopline(today_folder, report)
            return report
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

        artifact_issue = _locked_artifact_issue(
            manifest=manifest,
            expected_manifest_sha256=expected_manifest_sha256,
            entry=entry,
        )
        if artifact_issue:
            report["failed"] = int(report["failed"]) + 1
            report["halted"] = True
            report["halt_reason"] = "SEND_ARTIFACT_TOCTOU"
            report["error"] = artifact_issue
            break

        halted_result = _halt_barrier_send_result(manifest)
        if halted_result is not None:
            report["halted"] = True
            report["halt_reason"] = str(
                halted_result.get("halt_reason") or "TELEGRAM_HALT_BARRIER"
            )
            report["halt_gate_reason"] = str(halted_result.get("halt_gate_reason") or "")
            report["error"] = str(halted_result.get("error") or "")
            report["fallback_allowed"] = False
            break

        _set_entry_state(ledger, pdf_key, "api_started", note="telegram_send_document_started")
        save_telegram_ledger(ledger_path, ledger)
        result = _send_document_with_rate_limit_retry(
            token=config["token"],
            chat_id=config["chat_id"],
            document_path=pdf_path,
            caption=_format_caption(entry, index=manifest_index, total=len(entries), batch_label=batch_label),
            timeout_seconds=timeout_seconds,
            manifest=manifest,
        )
        if result.get("halted"):
            _set_entry_state(
                ledger,
                pdf_key,
                "pending",
                note="local halt barrier activated before Telegram document API send",
            )
            save_telegram_ledger(ledger_path, ledger)
            report["halted"] = True
            report["halt_reason"] = str(
                result.get("halt_reason") or "TELEGRAM_HALT_BARRIER"
            )
            report["halt_gate_reason"] = str(result.get("halt_gate_reason") or "")
            report["error"] = str(result.get("error") or "")
            report["fallback_allowed"] = False
            break
        if result.get("success"):
            observed_chat_id = str(result.get("chat_id") or config["chat_id"])
            if observed_chat_id != str(ledger.get("telegram_chat_id") or ""):
                _set_entry_state(
                    ledger,
                    pdf_key,
                    "unsure",
                    note="Telegram API confirmed a different target chat identity",
                    extra={"telegram_chat_id": observed_chat_id},
                )
                save_telegram_ledger(ledger_path, ledger)
                report["failed"] = int(report["failed"]) + 1
                report["halted"] = True
                report["halt_reason"] = "TELEGRAM_TARGET_IDENTITY_MISMATCH"
                break
            _set_entry_state(
                ledger,
                pdf_key,
                "confirmed",
                note="telegram_send_document_confirmed",
                extra={
                    "telegram_message_id": str(result.get("message_id") or ""),
                    "telegram_chat_id": observed_chat_id,
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
        if not final_status.get("ok"):
            if final_status.get("halted"):
                report["halted"] = True
                report["halt_reason"] = str(
                    final_status.get("halt_reason") or "TELEGRAM_HALT_BARRIER"
                )
                report["halt_gate_reason"] = str(
                    final_status.get("halt_gate_reason") or ""
                )
                report["error"] = str(final_status.get("error") or "")
                report["fallback_allowed"] = False
            if verbose:
                print(f"WARNING: Telegram post-status message failed: {final_status.get('error')}")

    report["ok"] = int(report["failed"]) == 0 and not report["halted"]
    report["fallback_allowed"] = (
        not report["ok"]
        and int(report["sent"]) == 0
        and int(report["confirmed_total"]) == 0
        and str(report.get("halt_reason") or "")
        not in {"MANIFEST_PREFLIGHT_RED", "TELEGRAM_UNSURE", "TELEGRAM_HALT_BARRIER"}
    )
    if report["ok"] and int(report.get("confirmed_total") or 0) == len(entries):
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
    """Deprecated unsafe recovery path; confirmed ledger keys are immutable."""
    return {
        "ok": False,
        "halted": True,
        "halt_reason": "ORDERED_FULL_RESEND_DISABLED",
        "error": "Whole-manifest resend is disabled; resume only the pinned ledger.",
        "sent": 0,
        "failed": 0,
        "confirmed_total": 0,
    }


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
    parser.add_argument("--manifest-path", type=Path, default=None)
    parser.add_argument("--manifest-sha256", type=str, default="")
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
            manifest_path=args.manifest_path,
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
        manifest_path=args.manifest_path,
        expected_manifest_sha256=args.manifest_sha256,
    )
    if args.json_out:
        args.json_out.parent.mkdir(parents=True, exist_ok=True)
        args.json_out.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
