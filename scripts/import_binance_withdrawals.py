#!/usr/bin/env python3
"""Import Binance withdrawals into the database and transfer ledger."""

from __future__ import annotations

import argparse
import os
from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from core.integrations.binance_wallet_client import BinanceWalletClient, BinanceWalletError
from core.transfer_ledger.binance_withdraw_import import import_binance_withdrawals
from core.transfer_ledger import repository


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


def _to_iso_safe(value, tz: ZoneInfo) -> str | None:
    if value is None:
        return None
    try:
        return datetime.fromtimestamp(float(value) / 1000, tz=timezone.utc).astimezone(tz).isoformat()
    except Exception:
        try:
            return datetime.fromisoformat(str(value).replace("Z", "+00:00")).astimezone(tz).isoformat()
        except Exception:
            return None


def _window_ranges(start_dt: datetime, end_dt: datetime, max_days: int) -> list[tuple[datetime, datetime]]:
    windows = []
    cur = start_dt
    delta = timedelta(days=max_days)
    while cur <= end_dt:
        win_end = min(cur + delta, end_dt)
        windows.append((cur, win_end))
        cur = win_end + timedelta(milliseconds=1)
    return windows


def main() -> int:
    parser = argparse.ArgumentParser(description="Import Binance withdrawal history")
    parser.add_argument("--db", type=Path, default=None, help="Path to SQLite DB")
    parser.add_argument("--coin", default="USDT", help="Coin symbol (default USDT)")
    parser.add_argument("--start-date", type=_parse_date, help="YYYY-MM-DD")
    parser.add_argument("--end-date", type=_parse_date, help="YYYY-MM-DD")
    parser.add_argument("--days", type=int, default=30, help="Lookback days if no start/end")
    parser.add_argument("--tz", default="Asia/Almaty", help="Timezone for date bounds")
    parser.add_argument("--dry-run", action="store_true", help="Fetch only; do not write to DB")
    parser.add_argument("--no-ledger", action="store_true", help="Do not create ledger entries")
    parser.add_argument("--no-auto-allocate", action="store_true", help="Disable auto PO allocation")
    parser.add_argument("--no-auto-label", action="store_true", help="Disable auto labeling from exchanger orders")
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
    total_inserted = 0
    total_ledger = 0
    errors: list[str] = []
    min_seen: Optional[str] = None
    max_seen: Optional[str] = None

    windows = _window_ranges(start_dt, end_dt, max_days=30)

    for win_start, win_end in windows:
        try:
            raw_withdrawals = client.iter_withdrawals(
                coin=args.coin,
                start_time_ms=_to_ms(win_start),
                end_time_ms=_to_ms(win_end),
            )
        except BinanceWalletError as exc:
            errors.append(str(exc))
            continue

        total_rows += len(raw_withdrawals)
        for raw in raw_withdrawals:
            seen = _to_iso_safe(raw.get("applyTime") or raw.get("applyTimeStamp"), tz)
            if not seen:
                continue
            if not min_seen or seen < min_seen:
                min_seen = seen
            if not max_seen or seen > max_seen:
                max_seen = seen

        if args.dry_run:
            continue

        result = import_binance_withdrawals(
            raw_withdrawals,
            db_path=args.db,
            ledger_coin=args.coin.upper(),
            write_ledger=not args.no_ledger,
            auto_allocate=not args.no_auto_allocate,
            auto_label=not args.no_auto_label,
        )
        total_inserted += result["inserted"]
        total_ledger += result["ledger_entries"]
        errors.extend(result["errors"])

    print(f"Fetched withdrawals: {total_rows}")
    if not args.dry_run:
        print(f"Inserted new withdrawals: {total_inserted}")
        print(f"Ledger entries created: {total_ledger}")
    if errors:
        print("Errors:")
        for e in errors[:10]:
            print(f"  - {e}")
        if len(errors) > 10:
            print(f"  ... {len(errors) - 10} more")

    if not args.dry_run:
        repository.record_sync_log(
            "binance_withdrawals",
            success=not errors,
            min_date_seen=min_seen,
            max_date_seen=max_seen,
            rows_total=total_rows,
            rows_inserted=total_inserted,
            errors_count=len(errors),
            db_path=args.db,
        )

    return 0 if not errors else 1


if __name__ == "__main__":
    raise SystemExit(main())
