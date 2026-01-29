"""Parse Binance withdrawal emails into structured data."""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from typing import Optional
from zoneinfo import ZoneInfo


LOCAL_TZ = ZoneInfo("Asia/Almaty")


def _strip_html(html: str) -> str:
    return re.sub(r"<[^>]+>", " ", html or "")


def _normalize_text(*parts: str) -> str:
    return " ".join([p for p in parts if p]).replace("\n", " ").replace("\r", " ")


def _parse_amount(text: str) -> tuple[Optional[float], Optional[str]]:
    patterns = [
        r"withdrawn\s+([0-9][0-9,\.]+)\s*([A-Z]{2,10})",
        r"withdrawal\s+amount\s*[:#]?\s*([0-9][0-9,\.]+)\s*([A-Z]{2,10})",
    ]
    for pat in patterns:
        m = re.search(pat, text, re.I)
        if m:
            try:
                return float(m.group(1).replace(",", "")), m.group(2).upper()
            except ValueError:
                return None, None
    return None, None


def _parse_coin_from_subject(subject: str) -> Optional[str]:
    m = re.search(r"\b([A-Z0-9]{2,10})\s+Withdrawal\b", subject, re.I)
    if m:
        return m.group(1).upper()
    return None


def _parse_address(text: str) -> Optional[str]:
    # Prefer explicit labels if present
    m = re.search(r"Withdrawal\s+Address\s*[:#]?\s*([0-9A-Za-z]{10,})", text, re.I)
    if m:
        return m.group(1).strip()
    # Fallback to TRC20-like address
    m = re.search(r"\b(T[0-9A-Za-z]{33,})\b", text)
    if m:
        return m.group(1)
    return None


def _parse_tx_id(text: str) -> Optional[str]:
    m = re.search(r"Transaction\s*ID\s*[:#]?\s*([0-9a-fA-F]{20,})", text)
    if m:
        return m.group(1)
    m = re.search(r"\btxid[:#]?\s*([0-9a-fA-F]{20,})\b", text, re.I)
    if m:
        return m.group(1)
    return None


def _parse_subject_time(subject: str) -> Optional[str]:
    m = re.search(r"(\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2})\s*\(UTC\)", subject)
    if not m:
        return None
    try:
        dt = datetime.fromisoformat(m.group(1)).replace(tzinfo=timezone.utc)
    except ValueError:
        return None
    return dt.astimezone(LOCAL_TZ).isoformat()


def parse_binance_withdrawal_email(msg: dict) -> Optional[dict]:
    subject = msg.get("subject") or ""
    from_addr = msg.get("from") or ""
    body_text = msg.get("body_text") or ""
    body_html = msg.get("body_html") or ""
    body = _normalize_text(subject, from_addr, body_text, _strip_html(body_html))

    if "withdraw" not in body.lower():
        return None

    amount, coin = _parse_amount(body)
    coin = coin or _parse_coin_from_subject(subject)
    address = _parse_address(body)
    tx_id = _parse_tx_id(body)
    success_time = _parse_subject_time(subject)

    # If we can't extract anything useful, skip
    if not any([amount, coin, address, tx_id, success_time]):
        return None

    return {
        "coin": coin,
        "amount": amount,
        "address": address,
        "tx_id": tx_id,
        "success_time": success_time,
        "message_id": msg.get("message_id") or "",
        "message_date": msg.get("date"),
        "subject": subject,
        "raw_json": json.dumps(msg, ensure_ascii=False),
        "source": "GMAIL_BINANCE",
    }
