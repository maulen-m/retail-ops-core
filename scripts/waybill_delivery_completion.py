#!/usr/bin/env python3
from __future__ import annotations

import json
import hashlib
import sys
from collections import Counter
from datetime import date
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.paths import data_path  # noqa: E402
from core.ops.waybill_send_batch import compute_manifest_batch_hash  # noqa: E402


DEFAULT_TODAY_FOLDER = data_path("excel_ui", "Kaspi_orders", "Today")
DEFAULT_RUN_ROOT = data_path("exports", "google_ops_board", "workflow_runs")
SEND_BATCH_MANIFEST_FILE = "send_batch_manifest.json"
TELEGRAM_SEND_LEDGER_FILE = "telegram_send_ledger.json"
WHATSAPP_SEND_LEDGER_FILE = "send_ledger.json"


def _load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        return payload if isinstance(payload, dict) else {}
    except json.JSONDecodeError:
        return {}


def _clean(value: Any) -> str:
    text = str(value or "").strip()
    if text.endswith(".0") and text[:-2].isdigit():
        return text[:-2]
    return text


def find_latest_send_manifest(today_folder: Path, *, target_date: date | None = None) -> Path | None:
    root = Path(today_folder).expanduser() / "MERGED" / "SEND"
    if not root.exists():
        return None
    candidates: list[Path] = []
    for path in root.glob(f"*/{SEND_BATCH_MANIFEST_FILE}"):
        payload = _load_json(path)
        if target_date is not None and _clean(payload.get("target_date")) != target_date.isoformat():
            continue
        candidates.append(path)
    candidates.sort(key=lambda path: (path.stat().st_mtime, str(path)), reverse=True)
    return candidates[0] if candidates else None


def _manifest_pdf_keys(manifest: dict[str, Any]) -> list[str]:
    keys: list[str] = []
    for entry in manifest.get("entries") or []:
        pdf_key = _clean(entry.get("pdf_key"))
        if pdf_key:
            keys.append(pdf_key)
    return keys


def _state_counts(ledger: dict[str, Any]) -> Counter[str]:
    return Counter(_clean(entry.get("state")) or "pending" for entry in (ledger.get("entries") or {}).values())


def _delivery_report_for_run(*, run_root: Path, target_date: date, run_id: str) -> dict[str, Any]:
    if not run_id:
        return {}
    report_path = Path(run_root).expanduser() / target_date.isoformat() / run_id / "delivery_send_report.json"
    payload = _load_json(report_path)
    if payload:
        payload["_report_path"] = str(report_path)
    return payload


def _base_state(
    *,
    status: str,
    target_date: date,
    manifest_path: Path | None = None,
    manifest: dict[str, Any] | None = None,
    batch_root: Path | None = None,
) -> dict[str, Any]:
    entries = list((manifest or {}).get("entries") or [])
    return {
        "completed": False,
        "status": status,
        "channel": "",
        "target_date": target_date.isoformat(),
        "request_identity": dict((manifest or {}).get("request_identity") or {}),
        "manifest_path": str(manifest_path or ""),
        "batch_root": str(batch_root or ""),
        "batch_label": _clean((manifest or {}).get("batch_label")) or (batch_root.name if batch_root else ""),
        "manifest_count": len(entries),
        "confirmed_count": 0,
        "pending_count": len(entries),
        "ledger_path": "",
        "delivery_report_path": "",
        "state_counts": {},
    }


def _ledger_completion_state(
    *,
    channel: str,
    ledger_path: Path,
    manifest: dict[str, Any],
    target_date: date,
    manifest_path: Path,
    batch_root: Path,
) -> dict[str, Any]:
    missing_status = f"{channel.upper()}_LEDGER_MISSING"
    if not ledger_path.exists():
        return _base_state(
            status=missing_status,
            target_date=target_date,
            manifest_path=manifest_path,
            manifest=manifest,
            batch_root=batch_root,
        ) | {"channel": channel, "ledger_path": str(ledger_path)}

    ledger = _load_json(ledger_path)
    manifest_hash = _clean(manifest.get("batch_hash"))
    ledger_hash = _clean(ledger.get("batch_hash"))
    if not manifest_hash:
        return _base_state(
            status=f"{channel.upper()}_MANIFEST_BATCH_HASH_MISSING",
            target_date=target_date,
            manifest_path=manifest_path,
            manifest=manifest,
            batch_root=batch_root,
        ) | {"channel": channel, "ledger_path": str(ledger_path)}
    if not ledger_hash:
        return _base_state(
            status=f"{channel.upper()}_LEDGER_BATCH_HASH_MISSING",
            target_date=target_date,
            manifest_path=manifest_path,
            manifest=manifest,
            batch_root=batch_root,
        ) | {"channel": channel, "ledger_path": str(ledger_path)}
    if manifest_hash != ledger_hash:
        return _base_state(
            status=f"{channel.upper()}_LEDGER_BATCH_HASH_MISMATCH",
            target_date=target_date,
            manifest_path=manifest_path,
            manifest=manifest,
            batch_root=batch_root,
        ) | {"channel": channel, "ledger_path": str(ledger_path)}

    pdf_keys = _manifest_pdf_keys(manifest)
    ledger_entries = ledger.get("entries") or {}
    pinned_chat_id = _clean(ledger.get("telegram_chat_id")) if channel == "telegram" else ""
    if channel == "telegram" and not pinned_chat_id:
        return _base_state(
            status="TELEGRAM_LEDGER_TARGET_MISSING",
            target_date=target_date,
            manifest_path=manifest_path,
            manifest=manifest,
            batch_root=batch_root,
        ) | {"channel": channel, "ledger_path": str(ledger_path)}
    confirmed_count = 0
    for pdf_key in pdf_keys:
        ledger_entry = ledger_entries.get(pdf_key) or {}
        if _clean(ledger_entry.get("state")) == "confirmed":
            if channel == "telegram" and _clean(
                ledger_entry.get("telegram_chat_id")
            ) != pinned_chat_id:
                return _base_state(
                    status="TELEGRAM_LEDGER_TARGET_MISMATCH",
                    target_date=target_date,
                    manifest_path=manifest_path,
                    manifest=manifest,
                    batch_root=batch_root,
                ) | {
                    "channel": channel,
                    "ledger_path": str(ledger_path),
                    "telegram_chat_id": pinned_chat_id,
                }
            confirmed_count += 1
    state_counts = dict(_state_counts(ledger))
    completed = bool(pdf_keys) and confirmed_count == len(pdf_keys)
    return {
        "completed": completed,
        "status": f"{channel.upper()}_CONFIRMED" if completed else f"{channel.upper()}_LEDGER_INCOMPLETE",
        "channel": channel,
        "target_date": target_date.isoformat(),
        "request_identity": dict(manifest.get("request_identity") or {}),
        "manifest_path": str(manifest_path),
        "batch_root": str(batch_root),
        "batch_label": _clean(manifest.get("batch_label")) or batch_root.name,
        "manifest_count": len(pdf_keys),
        "confirmed_count": confirmed_count,
        "pending_count": max(0, len(pdf_keys) - confirmed_count),
        "ledger_path": str(ledger_path),
        "delivery_report_path": "",
        "state_counts": state_counts,
        "telegram_chat_id": pinned_chat_id,
    }


def delivery_completion_state(
    *,
    today_folder: Path = DEFAULT_TODAY_FOLDER,
    target_date: date,
    run_root: Path = DEFAULT_RUN_ROOT,
    run_id: str = "",
    explicit_delivery_channel: str = "",
    explicit_delivery_ok: bool = False,
    manifest_path: Path | None = None,
    expected_manifest_sha256: str = "",
) -> dict[str, Any]:
    manifest_was_explicit = manifest_path is not None
    resolved_manifest_path = Path(manifest_path).expanduser().resolve() if manifest_path else None
    if resolved_manifest_path is not None:
        today_root = Path(today_folder).expanduser().resolve()
        try:
            resolved_manifest_path.relative_to(today_root)
        except ValueError:
            return _base_state(status="PINNED_MANIFEST_OUTSIDE_TODAY", target_date=target_date)
        if resolved_manifest_path.name != SEND_BATCH_MANIFEST_FILE:
            return _base_state(status="PINNED_MANIFEST_INVALID_NAME", target_date=target_date)
    else:
        resolved_manifest_path = find_latest_send_manifest(today_folder, target_date=target_date)
    if resolved_manifest_path is None:
        return _base_state(status="SEND_MANIFEST_MISSING", target_date=target_date)

    manifest = _load_json(resolved_manifest_path)
    if not manifest_was_explicit:
        return _base_state(
            status="UNPINNED_MANIFEST_DISCOVERY_ONLY",
            target_date=target_date,
            manifest_path=resolved_manifest_path,
            manifest=manifest,
            batch_root=resolved_manifest_path.parent,
        )
    expected_sha = _clean(expected_manifest_sha256).lower()
    if len(expected_sha) != 64 or any(char not in "0123456789abcdef" for char in expected_sha):
        return _base_state(
            status="PINNED_MANIFEST_SHA256_REQUIRED",
            target_date=target_date,
            manifest_path=resolved_manifest_path,
            manifest=manifest,
            batch_root=resolved_manifest_path.parent,
        )
    observed_sha = hashlib.sha256(resolved_manifest_path.read_bytes()).hexdigest()
    if observed_sha != expected_sha:
        return _base_state(
            status="PINNED_MANIFEST_SHA256_MISMATCH",
            target_date=target_date,
            manifest_path=resolved_manifest_path,
            manifest=manifest,
            batch_root=resolved_manifest_path.parent,
        )
    if _clean(manifest.get("batch_hash")) != compute_manifest_batch_hash(manifest):
        return _base_state(
            status="PINNED_MANIFEST_BATCH_HASH_MISMATCH",
            target_date=target_date,
            manifest_path=resolved_manifest_path,
            manifest=manifest,
            batch_root=resolved_manifest_path.parent,
        )
    if _clean(manifest.get("target_date")) != target_date.isoformat():
        return _base_state(
            status="PINNED_MANIFEST_TARGET_DATE_MISMATCH",
            target_date=target_date,
            manifest_path=resolved_manifest_path,
            manifest=manifest,
            batch_root=resolved_manifest_path.parent,
        )
    batch_root = resolved_manifest_path.parent
    telegram_state = _ledger_completion_state(
        channel="telegram",
        ledger_path=batch_root / TELEGRAM_SEND_LEDGER_FILE,
        manifest=manifest,
        target_date=target_date,
        manifest_path=resolved_manifest_path,
        batch_root=batch_root,
    )
    if telegram_state["completed"]:
        return telegram_state

    if explicit_delivery_ok and _clean(explicit_delivery_channel).lower() == "whatsapp":
        whatsapp_state = _ledger_completion_state(
            channel="whatsapp",
            ledger_path=batch_root / WHATSAPP_SEND_LEDGER_FILE,
            manifest=manifest,
            target_date=target_date,
            manifest_path=resolved_manifest_path,
            batch_root=batch_root,
        )
        whatsapp_state["delivery_report_path"] = "explicit:send_waybills_delivery"
        return whatsapp_state

    delivery_report = _delivery_report_for_run(run_root=run_root, target_date=target_date, run_id=run_id)
    delivery_channel = _clean(delivery_report.get("delivery_channel")).lower()
    if delivery_report.get("ok") and delivery_channel == "whatsapp":
        whatsapp_state = _ledger_completion_state(
            channel="whatsapp",
            ledger_path=batch_root / WHATSAPP_SEND_LEDGER_FILE,
            manifest=manifest,
            target_date=target_date,
            manifest_path=resolved_manifest_path,
            batch_root=batch_root,
        )
        whatsapp_state["delivery_report_path"] = _clean(delivery_report.get("_report_path"))
        return whatsapp_state

    return telegram_state


def format_delivery_completion_status(state: dict[str, Any]) -> str:
    status = _clean(state.get("status")) or "UNKNOWN"
    channel = _clean(state.get("channel")) or "none"
    confirmed = int(state.get("confirmed_count") or 0)
    total = int(state.get("manifest_count") or 0)
    lines = [
        "<b>Waybill Delivery Status</b>",
        f"Gate: <code>{status}</code>",
        f"Channel: <code>{channel}</code>",
        f"Bundles confirmed: <code>{confirmed}/{total}</code>",
    ]
    batch_label = _clean(state.get("batch_label"))
    if batch_label:
        lines.append(f"Batch: <code>{batch_label}</code>")
    ledger_path = _clean(state.get("ledger_path"))
    if ledger_path:
        lines.append(f"Ledger: <code>{Path(ledger_path).name}</code>")
    return "\n".join(lines)
