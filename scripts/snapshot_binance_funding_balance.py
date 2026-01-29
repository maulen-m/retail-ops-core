#!/usr/bin/env python3
"""Snapshot Binance funding wallet balances into the database."""

from __future__ import annotations

import argparse
import json
import os
from datetime import datetime
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from core.integrations.binance_wallet_client import BinanceWalletClient, BinanceWalletError
from core.transfer_ledger.repository import insert_funding_balance_snapshot


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


def _to_float(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def main() -> int:
    parser = argparse.ArgumentParser(description="Snapshot Binance funding wallet balances")
    parser.add_argument("--db", type=Path, default=None, help="Path to SQLite DB")
    parser.add_argument("--asset", default=None, help="Optional asset filter (e.g., USDT)")
    args = parser.parse_args()

    _load_env_file(PROJECT_ROOT / ".env")

    client = BinanceWalletClient()

    try:
        rows = client.get_funding_assets(asset=args.asset)
    except BinanceWalletError as exc:
        print(f"Error: {exc}")
        return 1

    snapshot_time = datetime.now().isoformat()

    inserted = 0
    for row in rows:
        asset = (row.get("asset") or "").upper()
        if not asset:
            continue
        payload = {
            "snapshot_time": snapshot_time,
            "asset": asset,
            "free": _to_float(row.get("free")),
            "locked": _to_float(row.get("locked")),
            "total": _to_float(row.get("free")) + _to_float(row.get("locked"))
            if _to_float(row.get("free")) is not None and _to_float(row.get("locked")) is not None
            else None,
            "raw_json": json.dumps(row, ensure_ascii=False),
            "source": "BINANCE_FUNDING_BAL",
        }
        insert_funding_balance_snapshot(payload, db_path=args.db)
        inserted += 1

    print(f"Snapshot time: {snapshot_time}")
    print(f"Assets captured: {inserted}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
