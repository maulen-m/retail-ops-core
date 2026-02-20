#!/usr/bin/env python3
"""Sync Gmail history via Gmail API and update DB."""

from __future__ import annotations

import argparse
import os
import subprocess
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from core.db import get_db
from core.integrations.gmail_api_client import get_gmail_service, fetch_message_raw
from core.transfer_ledger.binance_withdrawal_email_import import parse_binance_withdrawal_email
from core.transfer_ledger.exchanger_email_import import parse_exchanger_email
from core.transfer_ledger.exchanger_matching import label_withdrawals_for_order
from core.transfer_ledger.matching import address_match
from core.transfer_ledger.telegram_ledger_alerts import send_exchanger_update_alert
from core.transfer_ledger.repository import (
    ensure_schema,
    upsert_exchanger_order,
    insert_exchanger_event,
    list_withdrawals,
    update_withdrawal_metadata,
)


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


def _get_sync_state() -> tuple[str | None, list[str]]:
    ensure_schema()
    with get_db() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS gmail_sync_state (
                email_address TEXT PRIMARY KEY,
                history_id TEXT,
                labels TEXT,
                updated_at TEXT DEFAULT (datetime('now'))
            )
            """
        )
        row = conn.execute(
            "SELECT email_address, history_id, labels FROM gmail_sync_state LIMIT 1"
        ).fetchone()
    if not row:
        return None, []
    labels = [s for s in (row["labels"] or "").split(",") if s]
    return row["history_id"], labels


def _set_sync_state(email_address: str, history_id: str, labels: list[str]) -> None:
    ensure_schema()
    labels_str = ",".join(labels)
    with get_db() as conn:
        conn.execute(
            """
            INSERT INTO gmail_sync_state (email_address, history_id, labels, updated_at)
            VALUES (?, ?, ?, datetime('now'))
            ON CONFLICT(email_address) DO UPDATE SET
                history_id = excluded.history_id,
                labels = excluded.labels,
                updated_at = datetime('now')
            """,
            (email_address, history_id, labels_str),
        )


def _resolve_label_ids(service, labels: list[str]) -> list[str]:
    if not labels:
        return []
    available = service.users().labels().list(userId="me").execute()
    label_map = {l["name"]: l["id"] for l in available.get("labels", [])}
    out = []
    for name in labels:
        if name in label_map:
            out.append(label_map[name])
    return out


def _update_withdrawal_from_email(email_row: dict, withdrawals: list[dict]) -> bool:
    coin = (email_row.get("coin") or "").upper()
    amount = email_row.get("amount")
    address = email_row.get("address") or ""
    tx_id = email_row.get("tx_id") or ""

    candidates = [w for w in withdrawals if (w.get("coin") or "").upper() == coin]
    if amount is not None:
        candidates = [w for w in candidates if abs(float(w.get("amount") or 0) - float(amount)) <= 2.0]

    if tx_id:
        for w in candidates:
            if (w.get("tx_id") or "") == tx_id:
                return update_withdrawal_metadata(
                    w["withdraw_id"],
                    address=email_row.get("address"),
                    tx_id=email_row.get("tx_id"),
                    success_time=email_row.get("success_time"),
                )

    if address:
        for w in candidates:
            if address_match(address, w.get("address") or ""):
                return update_withdrawal_metadata(
                    w["withdraw_id"],
                    address=email_row.get("address"),
                    tx_id=email_row.get("tx_id"),
                    success_time=email_row.get("success_time"),
                )
    return False


def main() -> int:
    parser = argparse.ArgumentParser(description="Sync Gmail history")
    parser.add_argument("--credentials", default=None, help="OAuth client JSON path")
    parser.add_argument("--token", default=None, help="OAuth token cache path")
    parser.add_argument("--labels", default=None, help="Comma-separated labels to watch")
    parser.add_argument("--start-history-id", default=None, help="Override start history id")
    args = parser.parse_args()

    _load_env_file(PROJECT_ROOT / ".env")

    creds_path = args.credentials or _get_env("GMAIL_OAUTH_CLIENT_JSON")
    token_path = args.token or _get_env("GMAIL_TOKEN_PATH", "GMAIL_OAUTH_TOKEN")
    if not creds_path:
        print("Missing OAuth client JSON path")
        return 1
    if not token_path:
        token_path = str(Path.home() / ".config" / "autonomous_business" / "gmail_token.json")

    start_history = args.start_history_id
    stored_history, stored_labels = _get_sync_state()
    if not start_history:
        start_history = stored_history

    labels = [s.strip() for s in (args.labels or ",".join(stored_labels)).split(",") if s.strip()]

    service = get_gmail_service(Path(creds_path), Path(token_path))
    label_ids = _resolve_label_ids(service, labels)

    if not start_history:
        print("Missing start historyId; run gmail_watch_setup.py first.")
        return 1

    # Gmail history.list supports only a single labelId. If multiple labels are configured,
    # skip label filtering to avoid invalid queries.
    label_param = label_ids[0] if len(label_ids) == 1 else None

    history = service.users().history().list(
        userId="me",
        startHistoryId=start_history,
        historyTypes=["messageAdded"],
        labelId=label_param,
    ).execute()

    history_id = history.get("historyId")
    updates = 0
    withdrawals = list_withdrawals()

    while history:
        for item in history.get("history", []):
            for msg in item.get("messagesAdded", []):
                msg_id = msg.get("message", {}).get("id")
                if not msg_id:
                    continue
                payload = fetch_message_raw(service, msg_id)

                order = parse_exchanger_email(payload)
                if order:
                    is_new = upsert_exchanger_order(order)
                    if insert_exchanger_event(order):
                        send_exchanger_update_alert(order)
                    label_withdrawals_for_order(order)
                    updates += 1

                bw = parse_binance_withdrawal_email(payload)
                if bw:
                    if _update_withdrawal_from_email(bw, withdrawals):
                        updates += 1

        page_token = history.get("nextPageToken")
        if page_token:
            history = service.users().history().list(
                userId="me",
                startHistoryId=start_history,
                historyTypes=["messageAdded"],
                labelId=label_param,
                pageToken=page_token,
            ).execute()
            history_id = history.get("historyId") or history_id
        else:
            break

    if history_id:
        _set_sync_state("me", str(history_id), labels)

    print(f"Gmail sync updates: {updates}")
    if updates > 0:
        subprocess.run(
            [sys.executable, str(PROJECT_ROOT / "scripts" / "generate_transfer_ledger_reports.py")],
            check=False,
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
