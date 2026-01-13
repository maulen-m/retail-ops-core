#!/usr/bin/env python3
"""Import exchanger order emails from Gmail (IMAP) into DB and label withdrawals."""

from __future__ import annotations

import argparse
import os
import re
from datetime import datetime, timedelta
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from core.integrations.gmail_imap_client import fetch_messages
from core.transfer_ledger.exchanger_email_import import parse_exchanger_email
from core.transfer_ledger.repository import upsert_exchanger_order, insert_exchanger_event
from core.transfer_ledger.telegram_ledger_alerts import send_exchanger_update_alert
from core.transfer_ledger.exchanger_matching import label_withdrawals_for_order


def _parse_date(value: str) -> datetime:
    return datetime.fromisoformat(value)


def _load_env_file(path: Path) -> None:
    if not path.exists():
        return
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip("'").strip('"')
        if key and key not in os.environ:
            os.environ[key] = value


def _get_env(*keys: str) -> str | None:
    for key in keys:
        val = os.getenv(key)
        if val:
            return val
    return None


def _normalize_query(query: str) -> str:
    # Allow semicolon-separated lists in .env, e.g., from:(a; b; c)
    return re.sub(r"\s*;\s*", " OR ", query)


def main() -> int:
    parser = argparse.ArgumentParser(description="Import exchanger order emails from Gmail")
    parser.add_argument("--db", type=Path, default=None, help="Path to SQLite DB")
    parser.add_argument("--mailbox", default=None, help="Gmail label/mailbox (default INBOX)")
    parser.add_argument("--query", default=None, help="Gmail search query (X-GM-RAW)")
    parser.add_argument("--since-days", type=int, default=None, help="Shortcut for query: newer_than:Xd")
    parser.add_argument("--limit", type=int, default=200, help="Max messages to scan")
    parser.add_argument("--dry-run", action="store_true", help="Parse only; do not write to DB")
    parser.add_argument("--no-label", action="store_true", help="Do not label withdrawals")
    args = parser.parse_args()

    _load_env_file(PROJECT_ROOT / ".env")

    username = os.getenv("GMAIL_USER")
    app_password = os.getenv("GMAIL_APP_PASSWORD")
    if not username or not app_password:
        print("Missing GMAIL_USER or GMAIL_APP_PASSWORD in environment")
        return 1
    # App passwords are displayed with spaces; IMAP expects no spaces
    app_password = app_password.replace(" ", "")

    mailbox = args.mailbox or _get_env(
        "GMAIL_MAILBOX",
        "GMAIL_MAILBOX_Exchengers",
        "GMAIL_MAILBOX_Exchangers",
    ) or "INBOX"
    query = args.query or _get_env(
        "GMAIL_QUERY",
        "GMAIL_QUERY_Exchengers",
        "GMAIL_QUERY_Exchangers",
    )
    if args.since_days and not query:
        query = f"newer_than:{args.since_days}d"
    if query:
        query = _normalize_query(query)

    messages = fetch_messages(
        username=username,
        app_password=app_password,
        mailbox=mailbox,
        query=query,
        limit=args.limit,
    )

    parsed = 0
    inserted = 0
    events = 0
    labeled = 0
    errors: list[str] = []

    for msg in messages:
        try:
            order = parse_exchanger_email(msg)
            if not order:
                continue
            parsed += 1
            if args.dry_run:
                continue
            is_new = upsert_exchanger_order(order, db_path=args.db)
            if is_new:
                inserted += 1
            if insert_exchanger_event(order, db_path=args.db):
                events += 1
                send_exchanger_update_alert(order, db_path=args.db)
            if not args.no_label:
                labeled += label_withdrawals_for_order(order, db_path=args.db)
        except Exception as exc:
            errors.append(str(exc))

    print(f"Messages scanned: {len(messages)}")
    print(f"Exchanger orders parsed: {parsed}")
    if not args.dry_run:
        print(f"Inserted/updated orders: {inserted}")
        print(f"Email events stored: {events}")
        if not args.no_label:
            print(f"Withdrawals labeled: {labeled}")
    if errors:
        print("Errors:")
        for e in errors[:10]:
            print(f"  - {e}")
        if len(errors) > 10:
            print(f"  ... {len(errors) - 10} more")

    return 0 if not errors else 1


if __name__ == "__main__":
    raise SystemExit(main())
