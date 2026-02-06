#!/usr/bin/env python3
"""Sync UNIVERSAL/binance_usdt balance into bank_accounts history + snapshot.

Default mode is dry-run. Writes require:
1) ENABLE_BANK_ACCOUNTS_WRITE=1
2) --apply
"""

from __future__ import annotations

import argparse
from datetime import datetime
import os
from pathlib import Path
import sys
from typing import Any

import yaml

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from core.integrations.binance_wallet_client import BinanceWalletClient, BinanceWalletError
from scripts import generate_bank_snapshot

DEFAULT_HISTORY = PROJECT_ROOT / "config" / "bank_accounts_history.yaml"
DEFAULT_SNAPSHOT = PROJECT_ROOT / "config" / "bank_accounts.yaml"
DEFAULT_DB = PROJECT_ROOT / "db" / "app.db"

STORE_CODE = "UNIVERSAL"
ACCOUNT_NAME = "binance_usdt"
CURRENCY = "USDT"
AUTO_SOURCE = "binance api autosync"


def _now_gmt5() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S GMT+5")


def _float_equal(a: float, b: float, tol: float = 1e-9) -> bool:
    return abs(a - b) <= tol


def load_history_entries(history_path: Path) -> list[dict[str, Any]]:
    if not history_path.exists():
        return []
    payload = yaml.safe_load(history_path.read_text(encoding="utf-8")) or {}
    entries = payload.get("entries") or []
    return entries if isinstance(entries, list) else []


def _write_history_entries(history_path: Path, entries: list[dict[str, Any]]) -> None:
    header = (
        "# Bank Account Balance History (append-only)\n"
        "# Add new snapshots only; do not edit past entries.\n"
        "entries:\n"
    )
    body = yaml.safe_dump({"entries": entries}, sort_keys=False, allow_unicode=False)
    text = header + body.split("entries:\n", 1)[1]
    history_path.write_text(text, encoding="utf-8")


def _latest_universal_usdt(entries: list[dict[str, Any]]) -> float | None:
    if not entries:
        return None
    latest = entries[-1]
    balances = latest.get("balances") or []
    for row in balances:
        if (
            str(row.get("store")) == STORE_CODE
            and str(row.get("account")) == ACCOUNT_NAME
            and str(row.get("currency", "")).upper() == CURRENCY
        ):
            try:
                return float(row.get("amount"))
            except (TypeError, ValueError):
                return None
    return None


def append_or_update_universal_usdt_history(
    history_path: Path,
    balance_usdt: float,
    as_of: str,
) -> bool:
    entries = load_history_entries(history_path)
    if entries:
        latest = entries[-1]
        latest_source = str(latest.get("source") or "")
        latest_amount = _latest_universal_usdt(entries)
        if latest_source == AUTO_SOURCE and latest_amount is not None and _float_equal(latest_amount, balance_usdt):
            return False

    entry = {
        "as_of": as_of,
        "source": AUTO_SOURCE,
        "balances": [
            {
                "store": STORE_CODE,
                "account": ACCOUNT_NAME,
                "amount": float(balance_usdt),
                "currency": CURRENCY,
            }
        ],
    }
    entries.append(entry)
    _write_history_entries(history_path, entries)
    return True


def _fetch_binance_usdt_balance() -> float:
    client = BinanceWalletClient()
    balance = client.get_funding_balance("USDT")
    if balance is None:
        raise BinanceWalletError("USDT funding balance not returned by Binance API")
    return float(balance)


def _load_env_file(path: Path) -> None:
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip("'").strip('"')
        if key and key not in os.environ:
            os.environ[key] = value


def main() -> int:
    parser = argparse.ArgumentParser(description="Sync UNIVERSAL/binance_usdt to bank_accounts files")
    parser.add_argument("--history", type=Path, default=DEFAULT_HISTORY, help="bank_accounts_history.yaml path")
    parser.add_argument("--snapshot", type=Path, default=DEFAULT_SNAPSHOT, help="bank_accounts.yaml path")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB, help="DB path for FX in snapshot generation")
    parser.add_argument("--balance-usdt", type=float, default=None, help="Manual override for USDT balance")
    parser.add_argument("--as-of", default=None, help='Timestamp like "YYYY-MM-DD HH:MM:SS GMT+5"')
    parser.add_argument("--dry-run", action="store_true", help="Preview only (default behavior)")
    parser.add_argument("--apply", action="store_true", help="Write history + snapshot")
    args = parser.parse_args()

    _load_env_file(PROJECT_ROOT / ".env")

    do_apply = args.apply and os.getenv("ENABLE_BANK_ACCOUNTS_WRITE") == "1"
    if args.apply and not do_apply:
        print("Refusing to apply: set ENABLE_BANK_ACCOUNTS_WRITE=1")
        return 1

    balance = args.balance_usdt if args.balance_usdt is not None else _fetch_binance_usdt_balance()
    as_of = args.as_of or _now_gmt5()

    if args.dry_run or not do_apply:
        entries = load_history_entries(args.history)
        latest = _latest_universal_usdt(entries)
        print(f"Mode: DRY-RUN")
        print(f"Balance USDT: {balance:.6f}")
        print(f"As of: {as_of}")
        print(f"Latest UNIVERSAL/binance_usdt in history: {latest if latest is not None else 'N/A'}")
        return 0

    changed = append_or_update_universal_usdt_history(
        history_path=args.history,
        balance_usdt=balance,
        as_of=as_of,
    )

    # Regenerate snapshot from latest history entry.
    entries = generate_bank_snapshot.load_history(args.history)
    latest_entry = generate_bank_snapshot.get_latest_entry(entries)
    fx_rates = generate_bank_snapshot.get_fx_rates(args.db)
    snapshot_text = generate_bank_snapshot.generate_snapshot(latest_entry, fx_rates)
    args.snapshot.write_text(snapshot_text, encoding="utf-8")

    print(f"Applied: {'yes' if changed else 'no (unchanged latest auto snapshot)'}")
    print(f"History: {args.history}")
    print(f"Snapshot: {args.snapshot}")
    print(f"Balance USDT: {balance:.6f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
