"""Durable owner-alert outbox with Telegram retries and a local fallback."""

from __future__ import annotations

import fcntl
import html
import json
import os
import re
import subprocess
import time
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable

from core.alerts.error_alerts import ERROR_ALERT_CHAT_ID
from core.alerts.telegram import send_message


PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
DEFAULT_OUTBOX_PATH = PROJECT_ROOT / "runtime" / "state" / "ops_alert_outbox.jsonl"
TELEGRAM_RETRY_BACKOFF_SECONDS = (1, 5)
DEDUP_WINDOW = timedelta(hours=1)
DELIVERABLE_STATUSES = {"queued", "failed", "telegram_failed_notified"}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(now: datetime | None = None) -> str:
    return (now or _now()).isoformat()


def _append_event(entry: dict[str, Any], path: Path | None = None) -> None:
    target = Path(path or DEFAULT_OUTBOX_PATH)
    target.parent.mkdir(parents=True, exist_ok=True)
    encoded = json.dumps(entry, ensure_ascii=False, sort_keys=True) + "\n"
    with target.open("a", encoding="utf-8") as handle:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        try:
            handle.write(encoded)
            handle.flush()
            os.fsync(handle.fileno())
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def _latest_entries(path: Path | None = None) -> dict[str, dict[str, Any]]:
    target = Path(path or DEFAULT_OUTBOX_PATH)
    if not target.exists():
        return {}
    latest: dict[str, dict[str, Any]] = {}
    try:
        raw_lines = target.read_text(encoding="utf-8").splitlines()
    except OSError:
        return {}
    for raw in raw_lines:
        if not raw.strip():
            continue
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            continue
        if not isinstance(payload, dict):
            continue
        alert_id = str(payload.get("alert_id") or "").strip()
        if alert_id:
            latest[alert_id] = payload
    return latest


def _parse_timestamp(value: Any) -> datetime | None:
    try:
        parsed = datetime.fromisoformat(str(value or ""))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _recent_dedup_match(
    dedup_key: str,
    *,
    now: datetime,
    path: Path | None = None,
    dedup_window: timedelta = DEDUP_WINDOW,
) -> dict[str, Any] | None:
    if not dedup_key:
        return None
    for entry in _latest_entries(path).values():
        if str(entry.get("dedup_key") or "") != dedup_key:
            continue
        created_at = _parse_timestamp(entry.get("created_at"))
        if created_at is not None and now - created_at < dedup_window:
            return entry
    return None


def _format_telegram_message(title: str, lines: Iterable[str]) -> str:
    clean_lines = [html.escape(str(line)) for line in lines if str(line).strip()]
    message = f"<b>{html.escape(title)}</b>"
    if clean_lines:
        message += "\n\n" + "\n".join(clean_lines)
    return message


def _sanitize_delivery_error(value: Any, *, token: str = "") -> str:
    text = str(value or "")
    if token:
        text = text.replace(token, "<redacted>")
    return re.sub(
        r"(?i)(api\.telegram\.org/bot)[^/\s]+",
        r"\1<redacted>",
        text,
    )


def _escape_applescript(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"').replace("\n", " ")


def _notify_macos(title: str, lines: Iterable[str]) -> bool:
    """Best-effort local notification. This fallback never raises."""
    try:
        detail = " | ".join(str(line).strip() for line in lines if str(line).strip())
        script = (
            f'display notification "{_escape_applescript(detail[:500])}" '
            f'with title "{_escape_applescript(title[:120])}"'
        )
        result = subprocess.run(
            ["osascript", "-e", script],
            check=False,
            capture_output=True,
            text=True,
            timeout=10,
        )
        return result.returncode == 0
    except Exception:
        return False


def _deliver(entry: dict[str, Any], *, path: Path | None = None) -> bool:
    current = dict(entry)
    attempts = list(current.get("attempts") or [])
    token = str(os.environ.get("TELEGRAM_BOT_TOKEN") or "").strip()
    message = _format_telegram_message(
        str(current.get("title") or "Owner alert"),
        list(current.get("lines") or []),
    )
    chat_id = str(current.get("chat_id") or ERROR_ALERT_CHAT_ID)
    last_error = ""

    for retry_number in range(1, 4):
        attempted_at = _iso()
        try:
            if not token:
                result = {"success": False, "error": "TELEGRAM_BOT_TOKEN missing"}
            else:
                result = send_message(chat_id, message, token)
        except Exception as exc:
            result = {"success": False, "error": f"{type(exc).__name__}: {exc}"}
        success = bool(result.get("success"))
        last_error = _sanitize_delivery_error(result.get("error"), token=token)
        attempts.append(
            {
                "attempt": len(attempts) + 1,
                "retry_number": retry_number,
                "attempted_at": attempted_at,
                "success": success,
                "error": last_error,
                "message_id": str(result.get("message_id") or ""),
            }
        )
        if success:
            current.update(
                {
                    "status": "delivered",
                    "held": False,
                    "attempts": attempts,
                    "delivered_at": _iso(),
                    "telegram_message_id": str(result.get("message_id") or ""),
                    "last_error": "",
                    "updated_at": _iso(),
                }
            )
            try:
                _append_event(current, path)
            except Exception:
                pass
            return True
        if retry_number < 3:
            time.sleep(TELEGRAM_RETRY_BACKOFF_SECONDS[retry_number - 1])

    fallback_ok = _notify_macos(
        str(current.get("title") or "Owner alert"),
        list(current.get("lines") or []),
    )
    current.update(
        {
            "status": "telegram_failed_notified" if fallback_ok else "failed",
            "held": False,
            "attempts": attempts,
            "telegram_failed_at": _iso(),
            "macos_fallback_notified": fallback_ok,
            "last_error": last_error,
            "updated_at": _iso(),
        }
    )
    try:
        _append_event(current, path)
    except Exception:
        pass
    return False


def enqueue_alert(
    *,
    title: str,
    lines: Iterable[str],
    severity: str = "WARN",
    dedup_key: str = "",
    held: bool = False,
    local_only: bool = False,
    chat_id: str = ERROR_ALERT_CHAT_ID,
    dedup_window: timedelta = DEDUP_WINDOW,
) -> bool:
    """Persist an alert, optionally making it permanently local-only."""
    if held and local_only:
        raise ValueError("local_only alerts cannot also be held")
    normalized_severity = str(severity or "WARN").strip().upper()
    if normalized_severity not in {"WARN", "CRITICAL"}:
        raise ValueError("severity must be WARN or CRITICAL")
    now = _now()
    normalized_key = str(dedup_key or "").strip()
    duplicate = _recent_dedup_match(
        normalized_key,
        now=now,
        dedup_window=dedup_window,
    )
    if duplicate is not None:
        return str(duplicate.get("status") or "") in {"delivered", "local_only"}

    entry = {
        "schema_version": 1,
        "alert_id": uuid.uuid4().hex,
        "title": str(title),
        "lines": [str(line) for line in lines if str(line).strip()],
        "severity": normalized_severity,
        "dedup_key": normalized_key,
        "chat_id": str(chat_id or ERROR_ALERT_CHAT_ID),
        "held": bool(held),
        "local_only": bool(local_only),
        "status": "local_only" if local_only else "queued",
        "attempts": [],
        "created_at": now.isoformat(),
        "queued_at": now.isoformat(),
        "updated_at": now.isoformat(),
    }
    try:
        _append_event(entry)
    except Exception:
        if not local_only:
            _notify_macos(entry["title"], entry["lines"])
        return False
    if local_only:
        return True
    if held:
        return False
    return _deliver(entry)


def flush_undelivered(max_age_hours: int = 48) -> dict[str, int]:
    """Re-attempt recent queued or failed alerts, excluding held entries."""
    now = _now()
    cutoff = now - timedelta(hours=max(0, int(max_age_hours)))
    candidates: list[dict[str, Any]] = []
    for entry in _latest_entries().values():
        created_at = _parse_timestamp(entry.get("created_at"))
        if (
            str(entry.get("status") or "") in DELIVERABLE_STATUSES
            and not bool(entry.get("held"))
            and created_at is not None
            and created_at >= cutoff
        ):
            candidates.append(entry)
    delivered = sum(1 for entry in candidates if _deliver(entry))
    return {"attempted": len(candidates), "delivered": delivered}


def flush_held(reason: str) -> dict[str, int]:
    """Release every held alert and attempt Telegram delivery."""
    candidates = [
        entry
        for entry in _latest_entries().values()
        if bool(entry.get("held")) and str(entry.get("status") or "") in DELIVERABLE_STATUSES
    ]
    delivered = 0
    for entry in candidates:
        released = dict(entry)
        released.update(
            {
                "held": False,
                "status": "queued",
                "held_release_reason": str(reason),
                "held_released_at": _iso(),
                "updated_at": _iso(),
            }
        )
        try:
            _append_event(released)
        except Exception:
            continue
        delivered += int(_deliver(released))
    return {"attempted": len(candidates), "delivered": delivered}
