"""Gmail API client helpers (OAuth token + raw message fetch)."""

from __future__ import annotations

import base64
import email
from email.header import decode_header
from email.message import Message
from email.utils import parsedate_to_datetime
from pathlib import Path
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


def get_gmail_service(creds_path: Path, token_path: Path, scopes: Optional[list[str]] = None):
    if scopes is None:
        scopes = ["https://www.googleapis.com/auth/gmail.readonly"]
    try:
        from google.oauth2.credentials import Credentials
        from google_auth_oauthlib.flow import InstalledAppFlow
        from google.auth.transport.requests import Request
        from googleapiclient.discovery import build
    except Exception as exc:  # pragma: no cover - dependency gate
        raise RuntimeError(
            "Missing Gmail API dependencies. Install: "
            "pip install google-api-python-client google-auth-httplib2 google-auth-oauthlib"
        ) from exc

    creds = None
    if token_path.exists():
        creds = Credentials.from_authorized_user_file(str(token_path), scopes)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(str(creds_path), scopes)
            creds = flow.run_local_server(port=0)
        token_path.parent.mkdir(parents=True, exist_ok=True)
        token_path.write_text(creds.to_json())

    return build("gmail", "v1", credentials=creds)


def fetch_message_raw(service, message_id: str) -> dict:
    msg = (
        service.users()
        .messages()
        .get(userId="me", id=message_id, format="raw")
        .execute()
    )
    raw = msg.get("raw")
    if not raw:
        raise ValueError("Missing raw content for Gmail message")
    data = base64.urlsafe_b64decode(raw.encode("utf-8"))
    mime = email.message_from_bytes(data)

    message_id_val = _decode_header(mime.get("Message-ID", ""))
    subject = _decode_header(mime.get("Subject", ""))
    from_addr = _decode_header(mime.get("From", ""))
    date_str = mime.get("Date", "")
    msg_date = parsedate_to_datetime(date_str) if date_str else None

    body_text, body_html = _extract_body(mime)

    return {
        "message_id": message_id_val,
        "subject": subject,
        "from": from_addr,
        "date": msg_date.isoformat() if msg_date else None,
        "body_text": body_text,
        "body_html": body_html,
    }
