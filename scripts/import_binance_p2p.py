#!/usr/bin/env python3
"""Import Binance C2C/P2P orders into the database and transfer ledger."""

from __future__ import annotations

import argparse
import os
from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo
from pathlib import Path
import sys

# Add project root to path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from core.integrations.binance_c2c_client import BinanceC2CClient, BinanceC2CError
from core.transfer_ledger.binance_import import import_binance_orders


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


def main() -> int:
    parser = argparse.ArgumentParser(description="Import Binance C2C/P2P orders")
    parser.add_argument("--db", type=Path, default=None, help="Path to SQLite DB")
    parser.add_argument("--trade-type", default="BUY", help="BUY, SELL, or comma-separated list")
    parser.add_argument("--start-date", type=_parse_date, help="YYYY-MM-DD")
    parser.add_argument("--end-date", type=_parse_date, help="YYYY-MM-DD")
    parser.add_argument("--days", type=int, default=30, help="Lookback days if no start/end")
    parser.add_argument("--tz", default="Asia/Almaty", help="Timezone for date bounds")
    parser.add_argument("--page-size", type=int, default=100, help="Rows per page (max 100)")
    parser.add_argument("--sleep", type=float, default=0.2, help="Sleep between pages (seconds)")
    parser.add_argument("--dry-run", action="store_true", help="Fetch only; do not write to DB")
    parser.add_argument("--no-ledger", action="store_true", help="Do not create ledger entries")
    parser.add_argument("--include-non-completed", action="store_true", help="Allow non-completed orders into ledger")
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

    # Binance C2C history is limited; warn if range is large
    if (end_date - start_date).days > 185:
        print("Warning: Binance C2C API may only return ~6 months of history.")

    trade_types = [t.strip().upper() for t in args.trade_type.split(",") if t.strip()]

    client = BinanceC2CClient()

    total_orders = 0
    total_inserted = 0
    total_ledger = 0
    errors: list[str] = []

    windows = _window_ranges(start_dt, end_dt, max_days=30)

    for trade_type in trade_types:
        for win_start, win_end in windows:
            begin_ms = _to_ms(win_start)
            end_ms = _to_ms(win_end)
            try:
                raw_orders = client.iter_user_orders(
                    trade_type=trade_type,
                    begin_time_ms=begin_ms,
                    end_time_ms=end_ms,
                    rows=args.page_size,
                    sleep_s=args.sleep,
                )
            except BinanceC2CError as exc:
                errors.append(str(exc))
                continue

            total_orders += len(raw_orders)

            if args.dry_run:
                continue

            result = import_binance_orders(
                raw_orders,
                db_path=args.db,
                write_ledger=not args.no_ledger,
                completed_only=not args.include_non_completed,
            )
            total_inserted += result["inserted"]
            total_ledger += result["ledger_entries"]
            errors.extend(result["errors"])

    print(f"Fetched orders: {total_orders}")
    if not args.dry_run:
        print(f"Inserted new orders: {total_inserted}")
        print(f"Ledger entries created: {total_ledger}")
    if errors:
        print("Errors:")
        for e in errors[:10]:
            print(f"  - {e}")
        if len(errors) > 10:
            print(f"  ... {len(errors) - 10} more")

    return 0 if not errors else 1


if __name__ == "__main__":
    raise SystemExit(main())
