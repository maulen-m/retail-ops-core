#!/usr/bin/env python3
"""Telegram bot poller for transfer ledger slash commands."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys
import time
import requests

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from core.alerts.telegram import get_telegram_config, send_message
from core.transfer_ledger.telegram_ledger_alerts import (
    build_pending_po_table,
)


STATE_FILE = PROJECT_ROOT / "logs" / "telegram_ledger_bot_offset.json"
MAX_MSG_LEN = 3500


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


def _load_offset() -> int | None:
    if not STATE_FILE.exists():
        return None
    try:
        data = json.loads(STATE_FILE.read_text())
        return int(data.get("offset")) if data.get("offset") is not None else None
    except Exception:
        return None


def _save_offset(offset: int) -> None:
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps({"offset": offset}))


def _allowed_chat_ids() -> set[str]:
    allow = os.getenv("TELEGRAM_ALLOWED_CHAT_IDS", "").strip()
    if not allow:
        return set()
    return {c.strip() for c in allow.split(",") if c.strip()}


def _get_updates(token: str, offset: int | None) -> list[dict]:
    url = f"https://api.telegram.org/bot{token}/getUpdates"
    params = {"timeout": 10}
    if offset is not None:
        params["offset"] = offset
    try:
        res = requests.get(url, params=params, timeout=15)
        data = res.json()
        if not data.get("ok"):
            return []
        return data.get("result", [])
    except Exception:
        return []


def _chunk_message(text: str) -> list[str]:
    if len(text) <= MAX_MSG_LEN:
        return [text]
    lines = text.splitlines()
    chunks = []
    cur = []
    cur_len = 0
    for line in lines:
        extra = len(line) + 1
        if cur_len + extra > MAX_MSG_LEN and cur:
            chunks.append("\n".join(cur))
            cur = [line]
            cur_len = len(line)
        else:
            cur.append(line)
            cur_len += extra
    if cur:
        chunks.append("\n".join(cur))
    return chunks


def _send_text(chat_id: str, token: str, text: str) -> None:
    for chunk in _chunk_message(text):
        send_message(chat_id, chunk, token, parse_mode="HTML")


def _handle_command(text: str, chat_id: str, token: str) -> None:
    cmd = text.strip().split()[0]
    if "@" in cmd:
        cmd = cmd.split("@", 1)[0]
    cmd = cmd.lower()

    if cmd in {"/pay_po", "/paypo"}:
        table, summary = build_pending_po_table()
        msg = "\n".join(
            [
                "<b>PO Payment Pending</b>",
                summary,
                "<pre>" + table + "</pre>",
            ]
        )
        _send_text(chat_id, token, msg)
        return

    if cmd in {"/start", "/help"}:
        msg = "\n".join(
            [
                "<b>Transfer Ledger Bot</b>",
                "Commands:",
                "/Pay_PO — show current pending PO payment summary",
            ]
        )
        _send_text(chat_id, token, msg)
        return


def poll_once() -> int:
    _load_env_file(PROJECT_ROOT / ".env")
    try:
        config = get_telegram_config()
    except Exception as exc:
        print(f"Telegram not configured: {exc}")
        return 1

    token = config["token"]
    default_chat = str(config["chat_id"])
    allow = _allowed_chat_ids()

    offset = _load_offset()
    updates = _get_updates(token, offset)
    if not updates:
        return 0

    max_id = None
    for upd in updates:
        upd_id = upd.get("update_id")
        if upd_id is not None:
            max_id = max(max_id or 0, upd_id)

        msg = upd.get("message") or upd.get("edited_message")
        if not msg:
            continue
        text = msg.get("text") or ""
        if not text:
            continue
        chat_id = str(msg.get("chat", {}).get("id", ""))
        if allow and chat_id not in allow:
            continue
        if not allow and chat_id != default_chat:
            continue

        _handle_command(text, chat_id, token)

    if max_id is not None:
        _save_offset(max_id + 1)
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Telegram ledger bot poller")
    parser.add_argument("--loop", action="store_true", help="Poll continuously")
    parser.add_argument("--interval", type=int, default=30, help="Loop interval seconds")
    args = parser.parse_args()

    if not args.loop:
        return poll_once()

    while True:
        poll_once()
        time.sleep(max(5, args.interval))


if __name__ == "__main__":
    raise SystemExit(main())
