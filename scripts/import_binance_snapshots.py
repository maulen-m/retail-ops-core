#!/usr/bin/env python3
"""Import Binance account snapshots into the database."""

from __future__ import annotations

import argparse
import json
import os
from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from core.integrations.binance_wallet_client import BinanceWalletClient, BinanceWalletError
from core.transfer_ledger.repository import upsert_binance_account_snapshot

MAX_WINDOW_DAYS = 30


def _parse_date(value: str) -> date:
    return date.fromisoformat(value)


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


def _date_bounds(d: date, tz: ZoneInfo, end: bool) -> datetime:
    if end:
        return datetime.combine(d, time(23, 59, 59, 999000), tzinfo=tz)
    return datetime.combine(d, time(0, 0, 0), tzinfo=tz)


def _to_ms(dt: datetime) -> int:
    return int(dt.astimezone(timezone.utc).timestamp() * 1000)


def _window_ranges(start_dt: datetime, end_dt: datetime, max_days: int) -> list[tuple[datetime, datetime]]:
    windows = []
    cur = start_dt
    delta = timedelta(days=max_days)
    while cur <= end_dt:
        win_end = min(cur + delta, end_dt)
        windows.append((cur, win_end))
        cur = win_end + timedelta(milliseconds=1)
    return windows


def _to_iso(ms_or_str) -> str:
    if ms_or_str is None:
        return datetime.now(ZoneInfo("Asia/Almaty")).isoformat()
    dt: datetime | None = None
    if isinstance(ms_or_str, (int, float)):
        dt = datetime.fromtimestamp(ms_or_str / 1000, tz=timezone.utc)
    else:
        try:
            dt = datetime.fromtimestamp(float(ms_or_str) / 1000, tz=timezone.utc)
        except Exception:
            try:
                dt = datetime.fromisoformat(str(ms_or_str).replace("Z", "+00:00"))
            except Exception:
                return str(ms_or_str)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(ZoneInfo("Asia/Almaty")).isoformat()


def main() -> int:
    parser = argparse.ArgumentParser(description="Import Binance account snapshots")
    parser.add_argument("--db", type=Path, default=None, help="Path to SQLite DB")
    parser.add_argument("--type", default="SPOT", help="Account type (SPOT/MARGIN/FUTURES)")
    parser.add_argument("--start-date", type=_parse_date, help="YYYY-MM-DD")
    parser.add_argument("--end-date", type=_parse_date, help="YYYY-MM-DD")
    parser.add_argument("--days", type=int, default=30, help="Lookback days if no start/end")
    parser.add_argument("--tz", default="Asia/Almaty", help="Timezone for date bounds")
    parser.add_argument("--dry-run", action="store_true", help="Fetch only; do not write to DB")
    args = parser.parse_args()

    _load_env_file(PROJECT_ROOT / ".env")

    tz = ZoneInfo(args.tz)

    if args.start_date and args.end_date:
        start_date = args.start_date
        end_date = args.end_date
    else:
        end_date = date.today()
        start_date = end_date - timedelta(days=args.days)

    start_dt = _date_bounds(start_date, tz, end=False)
    end_dt = _date_bounds(end_date, tz, end=True)

    client = BinanceWalletClient()

    total_rows = 0
    inserted = 0
    errors: list[str] = []

    windows = _window_ranges(start_dt, end_dt, max_days=MAX_WINDOW_DAYS)

    for win_start, win_end in windows:
        try:
            rows = client.list_account_snapshots(
                account_type=args.type,
                start_time_ms=_to_ms(win_start),
                end_time_ms=_to_ms(win_end),
                limit=30,
            )
        except BinanceWalletError as exc:
            errors.append(str(exc))
            continue

        total_rows += len(rows)

        if args.dry_run:
            continue

        for row in rows:
            try:
                snapshot_time = _to_iso(row.get("updateTime") or row.get("snapshotTime"))
                snapshot_id = f"{args.type}:{row.get('updateTime') or row.get('snapshotTime') or snapshot_time}"
                data = row.get("data") or {}
                total_btc = data.get("totalAssetOfBtc") if isinstance(data, dict) else None
                payload = {
                    "snapshot_id": snapshot_id,
                    "account_type": args.type,
                    "snapshot_time": snapshot_time,
                    "total_asset_btc": total_btc,
                    "data_json": json.dumps(data, ensure_ascii=False),
                    "raw_json": json.dumps(row, ensure_ascii=False),
                    "source": "BINANCE_SNAPSHOT",
                }
                if upsert_binance_account_snapshot(payload, db_path=args.db):
                    inserted += 1
            except Exception as exc:
                errors.append(str(exc))

    print(f"Fetched snapshots: {total_rows}")
    if not args.dry_run:
        print(f"Inserted new snapshots: {inserted}")
    if errors:
        print("Errors:")
        for e in errors[:10]:
            print(f"  - {e}")
        if len(errors) > 10:
            print(f"  ... {len(errors) - 10} more")

    return 0 if not errors else 1


if __name__ == "__main__":
    raise SystemExit(main())
