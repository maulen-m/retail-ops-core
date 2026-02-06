"""Gmail IMAP client (app password)."""

from __future__ import annotations

import imaplib
import email
from email.header import decode_header
from email.message import Message
from email.utils import parsedate_to_datetime
from typing import Optional


def _decode_header(value: str) -> str:
    if not value:
        return ""
    parts = decode_header(value)
    decoded = []
    for text, enc in parts:
        if isinstance(text, bytes):
            decoded.append(text.decode(enc or "utf-8", errors="replace"))
        else:
            decoded.append(text)
    return "".join(decoded)


def _extract_body(msg: Message) -> tuple[str, str]:
    text = ""
    html = ""
    if msg.is_multipart():
        for part in msg.walk():
            ctype = part.get_content_type()
            disp = str(part.get("Content-Disposition") or "")
            if "attachment" in disp:
                continue
            payload = part.get_payload(decode=True)
            if payload is None:
                continue
            charset = part.get_content_charset() or "utf-8"
            try:
                content = payload.decode(charset, errors="replace")
            except Exception:
                content = payload.decode("utf-8", errors="replace")
            if ctype == "text/plain" and not text:
                text = content
            elif ctype == "text/html" and not html:
                html = content
    else:
        payload = msg.get_payload(decode=True)
        if payload:
            charset = msg.get_content_charset() or "utf-8"
            try:
                text = payload.decode(charset, errors="replace")
            except Exception:
                text = payload.decode("utf-8", errors="replace")
    return text, html


def fetch_messages(
    username: str,
    app_password: str,
    mailbox: str = "INBOX",
    query: Optional[str] = None,
    limit: int = 200,
) -> list[dict]:
    """Fetch Gmail messages using IMAP.

    Args:
        username: Gmail address
        app_password: Gmail app password
        mailbox: Label or mailbox (e.g., "INBOX" or "Exchanger")
        query: Gmail search query (X-GM-RAW)
        limit: Max messages to return
    """
    imap = imaplib.IMAP4_SSL("imap.gmail.com")
    imap.login(username, app_password)
    status, _ = imap.select(mailbox)
    if status != "OK":
        imap.logout()
        raise ValueError(f"IMAP select failed for mailbox: {mailbox}")

    if query:
        safe = query.replace("\\", "\\\\").replace('"', '\\"')
        status, data = imap.search(None, "X-GM-RAW", f"\"{safe}\"")
    else:
        status, data = imap.search(None, "ALL")

    if status != "OK":
        imap.logout()
        raise ValueError(f"IMAP search failed for mailbox: {mailbox}")

    msg_ids = data[0].split()
    msg_ids = msg_ids[-limit:]

    out: list[dict] = []
    for msg_id in msg_ids:
        status, msg_data = imap.fetch(msg_id, "(RFC822)")
        if status != "OK":
            continue
        raw = msg_data[0][1]
        msg = email.message_from_bytes(raw)

        message_id = _decode_header(msg.get("Message-ID", ""))
        subject = _decode_header(msg.get("Subject", ""))
        from_addr = _decode_header(msg.get("From", ""))
        date_str = msg.get("Date", "")
        msg_date = parsedate_to_datetime(date_str) if date_str else None

        body_text, body_html = _extract_body(msg)

        out.append(
            {
                "message_id": message_id,
                "subject": subject,
                "from": from_addr,
                "date": msg_date.isoformat() if msg_date else None,
                "body_text": body_text,
                "body_html": body_html,
            }
        )

    imap.logout()
    return out
