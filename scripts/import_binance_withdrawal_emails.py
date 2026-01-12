#!/usr/bin/env python3
"""Import Binance withdrawal emails from Gmail (IMAP) and update DB rows."""

from __future__ import annotations

import argparse
import os
import re
from datetime import datetime
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from core.integrations.gmail_imap_client import fetch_messages
from core.transfer_ledger.binance_withdrawal_email_import import parse_binance_withdrawal_email
from core.transfer_ledger.exchanger_matching import AMOUNT_TOLERANCE, DATE_WINDOW_DAYS, address_match
from core.transfer_ledger.repository import list_withdrawals, update_withdrawal_metadata


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
    return re.sub(r"\s*;\s*", " OR ", query)


def _parse_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except Exception:
        return None


def _amount_close(a: float | None, b: float | None, tol: float = AMOUNT_TOLERANCE) -> bool:
    if a is None or b is None:
        return False
    return abs(float(a) - float(b)) <= tol


def _best_match(email_row: dict, withdrawals: list[dict]) -> dict | None:
    coin = (email_row.get("coin") or "").upper()
    amount = email_row.get("amount")
    address = email_row.get("address") or ""
    tx_id = email_row.get("tx_id") or ""
    email_dt = _parse_dt(email_row.get("success_time") or email_row.get("message_date"))

    candidates = [w for w in withdrawals if (w.get("coin") or "").upper() == coin]
    if amount is not None:
        candidates = [w for w in candidates if _amount_close(w.get("amount"), amount)]

    if tx_id:
        tx_match = [w for w in candidates if (w.get("tx_id") or "") == tx_id]
        if tx_match:
            return tx_match[0]

    if address:
        addr_match = [w for w in candidates if address_match(address, w.get("address") or "")]
        if addr_match:
            candidates = addr_match

    if not candidates:
        return None

    best = None
    best_delta = float("inf")
    for w in candidates:
        wd_dt = _parse_dt(w.get("apply_time") or w.get("success_time"))
        if email_dt and wd_dt:
            delta = abs((wd_dt - email_dt).total_seconds())
            if delta > DATE_WINDOW_DAYS * 86400:
                continue
        else:
            delta = 0
        if delta < best_delta:
            best = w
            best_delta = delta
    return best


def main() -> int:
    parser = argparse.ArgumentParser(description="Import Binance withdrawal emails from Gmail")
    parser.add_argument("--db", type=Path, default=None, help="Path to SQLite DB")
    parser.add_argument("--mailbox", default=None, help="Gmail label/mailbox (default INBOX)")
    parser.add_argument("--query", default=None, help="Gmail search query (X-GM-RAW)")
    parser.add_argument("--since-days", type=int, default=None, help="Shortcut for query: newer_than:Xd")
    parser.add_argument("--limit", type=int, default=200, help="Max messages to scan")
    parser.add_argument("--dry-run", action="store_true", help="Parse only; do not write to DB")
    args = parser.parse_args()

    _load_env_file(PROJECT_ROOT / ".env")

    username = os.getenv("GMAIL_USER")
    app_password = os.getenv("GMAIL_APP_PASSWORD")
    if not username or not app_password:
        print("Missing GMAIL_USER or GMAIL_APP_PASSWORD in environment")
        return 1
    app_password = app_password.replace(" ", "")

    mailbox = args.mailbox or _get_env("GMAIL_MAILBOX_Binance", "GMAIL_MAILBOX_BINANCE") or "INBOX"
    query = args.query or _get_env("GMAIL_QUERY_Binance", "GMAIL_QUERY_BINANCE")
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

    withdrawals = list_withdrawals(db_path=args.db)

    parsed = 0
    updated = 0
    errors: list[str] = []

    for msg in messages:
        try:
            row = parse_binance_withdrawal_email(msg)
            if not row:
                continue
            parsed += 1
            if args.dry_run:
                continue
            match = _best_match(row, withdrawals)
            if not match:
                continue
            updated_any = update_withdrawal_metadata(
                match["withdraw_id"],
                address=row.get("address"),
                tx_id=row.get("tx_id"),
                success_time=row.get("success_time"),
                db_path=args.db,
            )
            if updated_any:
                updated += 1
        except Exception as exc:
            errors.append(str(exc))

    print(f"Messages scanned: {len(messages)}")
    print(f"Binance withdrawal emails parsed: {parsed}")
    if not args.dry_run:
        print(f"Withdrawals updated: {updated}")
    if errors:
        print("Errors:")
        for e in errors[:10]:
            print(f"  - {e}")
        if len(errors) > 10:
            print(f"  ... {len(errors) - 10} more")

    return 0 if not errors else 1


if __name__ == "__main__":
    raise SystemExit(main())
