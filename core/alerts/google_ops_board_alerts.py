"""Telegram alerts for Google Ops Board automation."""

from __future__ import annotations

import os
from typing import Iterable

from core.alerts.error_alerts import ERROR_ALERT_CHAT_ID
from core.alerts.ops_alert_outbox import enqueue_alert


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
    return enqueue_alert(title=title, lines=lines, chat_id=chat_id)
