"""Telegram alerts for Google Ops Board automation."""

from __future__ import annotations

import html
import os
from typing import Iterable

from core.alerts.error_alerts import ERROR_ALERT_CHAT_ID
from core.alerts.telegram import send_message


def _token() -> str:
    return str(os.environ.get("TELEGRAM_BOT_TOKEN") or "").strip()


def owner_alert_env_ready() -> tuple[bool, str]:
    token = _token()
    if not token:
        return False, "TELEGRAM_BOT_TOKEN missing"
    return True, ""


def send_owner_ops_alert(
    *,
    title: str,
    lines: Iterable[str],
    chat_id: str = ERROR_ALERT_CHAT_ID,
) -> bool:
    ready, reason = owner_alert_env_ready()
    if not ready:
        print(f"Owner alert skipped: {reason}")
        return False

    escaped_lines = [html.escape(str(line)) for line in lines if str(line).strip()]
    body = "\n".join(escaped_lines)
    message = f"<b>{html.escape(title)}</b>"
    if body:
        message += f"\n\n{body}"
    result = send_message(chat_id, message, _token())
    return bool(result.get("success", False))
