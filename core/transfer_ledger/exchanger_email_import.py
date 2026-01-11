"""Parse exchanger order emails into structured data."""

from __future__ import annotations

import json
import re
from typing import Optional


EXCHANGER_KEYWORDS = {
    "BTCChange24": ["btcchange24"],
    "UAChanger": ["uachanger"],
}

STATUS_MAP = {
    "NEW": ["new exchange", "order for exchange"],
    "IN_PROCESS": ["in payout processing", "waiting for confirmation"],
    "COMPLETED": ["success done", "completed order"],
    "PAID": ["paid order"],
    "CANCELLED": ["order deleted"],
}


def _strip_html(html: str) -> str:
    return re.sub(r"<[^>]+>", " ", html or "")


def _normalize_text(*parts: str) -> str:
    return " ".join([p for p in parts if p]).replace("\n", " ").replace("\r", " ")


def _detect_exchanger(subject: str, from_addr: str, body: str) -> Optional[str]:
    hay = " ".join([subject, from_addr, body]).lower()
    for name, keys in EXCHANGER_KEYWORDS.items():
        if any(k in hay for k in keys):
            return name
    return None


def _detect_status(subject: str) -> Optional[str]:
    lower = subject.lower()
    for status, keys in STATUS_MAP.items():
        if any(k in lower for k in keys):
            return status
    return None


def _extract_order_id(subject: str) -> Optional[str]:
    m = re.search(r"#(\d{3,})", subject)
    if m:
        return m.group(1)
    m = re.search(r"order\s*(?:for\s*exchange\s*)?(\d{3,})", subject, re.I)
    if m:
        return m.group(1)
    return None


def _extract_order_id_from_body(body: str) -> Optional[str]:
    m = re.search(r"Order\s*ID\s*[:#]?\s*(\d{3,})", body, re.I)
    if m:
        return m.group(1)
    m = re.search(r"\bID\s*(\d{3,})\b", body, re.I)
    if m:
        return m.group(1)
    return None


def _extract_direction(subject: str, body: str) -> Optional[str]:
    m = re.search(r"\[(.+?)\]", subject)
    if m:
        return m.group(1).strip()
    m = re.search("(Tether\\s+TRC20\\s*[-\\u2192>]+\\s*WeChat)", body, re.I)
    if m:
        return m.group(1).replace("\u2192", "->").strip()
    return None


def _extract_rate(text: str) -> Optional[float]:
    m = re.search(r"1\s*USDT\s*[:=]\s*([0-9.,]+)\s*CNY", text, re.I)
    if not m:
        return None
    try:
        return float(m.group(1).replace(",", ""))
    except ValueError:
        return None


def _extract_amounts(text: str) -> tuple[Optional[float], Optional[float]]:
    usdt_vals = []
    for m in re.finditer(r"([0-9][0-9,\.]+)\s*(USDT|Tether(?:\s+TRC20)?)", text, re.I):
        try:
            usdt_vals.append(float(m.group(1).replace(",", "")))
        except ValueError:
            continue
    cny_vals = []
    for m in re.finditer(r"([0-9][0-9,\.]+)\s*CNY", text, re.I):
        try:
            cny_vals.append(float(m.group(1).replace(",", "")))
        except ValueError:
            continue

    usdt_vals = [v for v in usdt_vals if v > 1.0]
    cny_vals = [v for v in cny_vals if v > 1.0]

    amount_usdt = max(usdt_vals) if usdt_vals else None
    amount_cny = max(cny_vals) if cny_vals else None
    return amount_usdt, amount_cny


def _extract_address(text: str) -> Optional[str]:
    m = re.search(r"\b(T[0-9A-Za-z]{33,})\b", text)
    if m:
        return m.group(1)
    return None


def _extract_receiver(text: str) -> Optional[str]:
    m = re.search(r"WeChat\s*account\s*[:#]?\s*([0-9A-Za-z_\-]+)", text, re.I)
    if m:
        return m.group(1)
    return None


def parse_exchanger_email(msg: dict) -> Optional[dict]:
    subject = msg.get("subject") or ""
    from_addr = msg.get("from") or ""
    body_text = msg.get("body_text") or ""
    body_html = msg.get("body_html") or ""
    body = _normalize_text(subject, body_text, _strip_html(body_html))

    exchanger = _detect_exchanger(subject, from_addr, body)
    if not exchanger:
        return None

    status = _detect_status(subject)
    order_id = _extract_order_id(subject) or _extract_order_id_from_body(body)
    direction = _extract_direction(subject, body)
    rate = _extract_rate(body)
    amount_usdt, amount_cny = _extract_amounts(body)
    deposit_address = _extract_address(body)
    receiver_account = _extract_receiver(body)

    # Ignore non-order emails (e.g., OTP, registration) that lack core fields
    if not order_id and not amount_usdt and not amount_cny and not deposit_address and not direction:
        return None

    message_id = msg.get("message_id") or ""
    message_date = msg.get("date")

    order_key = order_id or message_id or str(hash(subject))
    order_key = order_key.strip().strip("<>").replace(" ", "")
    exchanger_order_id = f"{exchanger.upper()}:{order_key}"
    if not order_id:
        order_id = order_key

    derived_rate = None
    if amount_usdt and amount_cny and amount_usdt > 0:
        derived_rate = amount_cny / amount_usdt
    if derived_rate:
        rate = derived_rate

    return {
        "exchanger_order_id": exchanger_order_id,
        "exchanger": exchanger,
        "order_id": order_id,
        "status": status,
        "direction": direction,
        "amount_usdt": amount_usdt,
        "amount_cny": amount_cny,
        "rate_usdt_cny": rate,
        "deposit_address": deposit_address,
        "receiver_account": receiver_account,
        "message_id": message_id,
        "message_date": message_date,
        "subject": subject,
        "raw_json": json.dumps(msg, ensure_ascii=False),
        "source": "GMAIL",
    }
