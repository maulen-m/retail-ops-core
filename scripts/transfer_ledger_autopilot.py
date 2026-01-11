#!/usr/bin/env python3
"""Autonomous end-to-end transfer ledger sync.

Pipeline:
1) Import exchanger emails (Gmail)
2) Import Binance P2P BUY orders (USDT/KZT)
3) Derive FX rates (USDT/KZT + USDT/CNY) and upsert dim_fx_rates
4) Import Binance withdrawals (USDT TRC20) and post ledger entries
"""

from __future__ import annotations

import argparse
import os
import subprocess
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from core.integrations.gmail_imap_client import fetch_messages
from core.transfer_ledger.exchanger_email_import import parse_exchanger_email
from core.transfer_ledger.repository import upsert_exchanger_order, insert_exchanger_event
from core.transfer_ledger.exchanger_matching import label_withdrawals_for_order
from core.integrations.binance_c2c_client import BinanceC2CClient
from core.transfer_ledger.binance_import import import_binance_orders
from core.integrations.binance_wallet_client import BinanceWalletClient
from core.transfer_ledger.binance_withdraw_import import import_binance_withdrawals
from core.transfer_ledger.fx_derive import derive_daily_fx_rows
from core.db import get_db


DB_PATH = PROJECT_ROOT / "db" / "app.db"


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


def _to_ms(dt: datetime) -> int:
    return int(dt.astimezone(timezone.utc).timestamp() * 1000)


def _date_bounds(d: date, end: bool) -> datetime:
    if end:
        return datetime.combine(d, time(23, 59, 59, 999000), tzinfo=timezone.utc)
    return datetime.combine(d, time(0, 0, 0), tzinfo=timezone.utc)


def _window_ranges(start_dt: datetime, end_dt: datetime, max_days: int) -> list[tuple[datetime, datetime]]:
    windows = []
    cur = start_dt
    delta = timedelta(days=max_days)
    while cur <= end_dt:
        win_end = min(cur + delta, end_dt)
        windows.append((cur, win_end))
        cur = win_end + timedelta(milliseconds=1)
    return windows


def _ensure_dim_fx_rates_schema(conn) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS dim_fx_rates (
            effective_date TEXT PRIMARY KEY,
            usdt_kzt REAL NOT NULL,
            usdt_cny REAL NOT NULL,
            cny_kzt REAL NOT NULL,
            usd_kzt REAL NOT NULL,
            dlv_rate_usd_kg REAL NOT NULL,
            provider TEXT NOT NULL DEFAULT 'AUTO',
            source TEXT,
            updated_at TEXT DEFAULT (datetime('now'))
        )
        """
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_fx_rates_effective ON dim_fx_rates(effective_date DESC)"
    )


def import_emails(db_path: Path, mailbox: str, query: str | None, since_days: int, limit: int) -> dict:
    username = os.getenv("GMAIL_USER")
    app_password = os.getenv("GMAIL_APP_PASSWORD")
    if not username or not app_password:
        return {
            "errors": ["Missing GMAIL_USER or GMAIL_APP_PASSWORD"],
            "parsed": 0,
            "inserted": 0,
            "events": 0,
            "labeled": 0,
        }
    app_password = app_password.replace(" ", "")

    if since_days and not query:
        query = f"newer_than:{since_days}d"

    messages = fetch_messages(
        username=username,
        app_password=app_password,
        mailbox=mailbox,
        query=query,
        limit=limit,
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
            is_new = upsert_exchanger_order(order, db_path=db_path)
            if is_new:
                inserted += 1
            if insert_exchanger_event(order, db_path=db_path):
                events += 1
            labeled += label_withdrawals_for_order(order, db_path=db_path)
        except Exception as exc:
            errors.append(str(exc))

    return {"parsed": parsed, "inserted": inserted, "events": events, "labeled": labeled, "errors": errors}


def import_p2p(db_path: Path, days: int) -> dict:
    client = BinanceC2CClient()
    end_date = date.today()
    start_date = end_date - timedelta(days=days)
    start_dt = _date_bounds(start_date, end=False)
    end_dt = _date_bounds(end_date, end=True)

    total_orders = 0
    total_inserted = 0
    total_ledger = 0
    errors: list[str] = []

    windows = _window_ranges(start_dt, end_dt, max_days=30)
    for win_start, win_end in windows:
        raw_orders = client.iter_user_orders(
            trade_type="BUY",
            begin_time_ms=_to_ms(win_start),
            end_time_ms=_to_ms(win_end),
        )
        total_orders += len(raw_orders)
        result = import_binance_orders(
            raw_orders,
            db_path=db_path,
            write_ledger=True,
            completed_only=True,
        )
        total_inserted += result["inserted"]
        total_ledger += result["ledger_entries"]
        errors.extend(result["errors"])

    return {
        "fetched": total_orders,
        "inserted": total_inserted,
        "ledger_entries": total_ledger,
        "errors": errors,
    }


def derive_fx(db_path: Path, start_date: date | None, end_date: date | None, statuses: list[str]) -> dict:
    rows = derive_daily_fx_rows(
        db_path=db_path,
        start_date=start_date,
        end_date=end_date,
        min_count=1,
        include_statuses=statuses,
    )
    if not rows:
        return {"rows": 0, "errors": ["No FX rows derived"]}

    with get_db(db_path) as conn:
        _ensure_dim_fx_rates_schema(conn)
        # Backfill earliest withdrawal date if needed
        try:
            row = conn.execute("SELECT MIN(apply_time) FROM binance_withdrawals").fetchone()
            if row and row[0]:
                min_withdraw_date = datetime.fromisoformat(str(row[0]).replace("Z", "+00:00")).date()
                earliest = min(rows, key=lambda r: r["effective_date"])
                if min_withdraw_date.isoformat() < earliest["effective_date"]:
                    rows.insert(
                        0,
                        {
                            **earliest,
                            "effective_date": min_withdraw_date.isoformat(),
                            "provider": "AUTO_BACKFILL",
                            "source": "Backfill earliest withdrawal date",
                        },
                    )
        except Exception:
            pass

        for row in rows:
            conn.execute(
                """
                INSERT OR REPLACE INTO dim_fx_rates (
                    effective_date, usdt_kzt, usdt_cny, cny_kzt,
                    usd_kzt, dlv_rate_usd_kg, provider, source, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))
                """,
                (
                    row["effective_date"],
                    row["usdt_kzt"],
                    row["usdt_cny"],
                    row["cny_kzt"],
                    row["usd_kzt"],
                    row["dlv_rate_usd_kg"],
                    row["provider"],
                    row["source"],
                ),
            )
    return {"rows": len(rows), "errors": []}


def import_withdrawals(db_path: Path, days: int) -> dict:
    client = BinanceWalletClient()
    end_date = date.today()
    start_date = end_date - timedelta(days=days)
    start_dt = _date_bounds(start_date, end=False)
    end_dt = _date_bounds(end_date, end=True)

    total_rows = 0
    total_inserted = 0
    total_ledger = 0
    errors: list[str] = []

    windows = _window_ranges(start_dt, end_dt, max_days=30)
    for win_start, win_end in windows:
        raw_withdrawals = client.iter_withdrawals(
            coin="USDT",
            start_time_ms=_to_ms(win_start),
            end_time_ms=_to_ms(win_end),
        )
        total_rows += len(raw_withdrawals)
        result = import_binance_withdrawals(
            raw_withdrawals,
            db_path=db_path,
            ledger_coin="USDT",
            write_ledger=True,
            auto_allocate=True,
            auto_label=True,
        )
        total_inserted += result["inserted"]
        total_ledger += result["ledger_entries"]
        errors.extend(result["errors"])

    return {
        "fetched": total_rows,
        "inserted": total_inserted,
        "ledger_entries": total_ledger,
        "errors": errors,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Autonomous transfer ledger sync")
    parser.add_argument("--db", type=Path, default=DB_PATH, help="Path to SQLite DB")
    parser.add_argument("--days", type=int, default=120, help="Lookback days")
    parser.add_argument("--mailbox", default=None, help="Gmail mailbox/label")
    parser.add_argument("--query", default=None, help="Gmail search query")
    parser.add_argument("--since-days", type=int, default=30, help="Gmail lookback days")
    parser.add_argument("--limit", type=int, default=200, help="Max Gmail messages")
    parser.add_argument("--statuses", default="COMPLETED", help="Exchanger statuses for FX")
    parser.add_argument("--current-usdt", type=float, default=None, help="Override current USDT balance")
    parser.add_argument("--reports", action="store_true", help="Generate Markdown reports")
    args = parser.parse_args()

    _load_env_file(PROJECT_ROOT / ".env")

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

    statuses = [s.strip().upper() for s in args.statuses.split(",") if s.strip()]

    print("[1/4] Importing exchanger emails...")
    email_res = import_emails(args.db, mailbox, query, args.since_days, args.limit)
    print(
        f"  parsed={email_res['parsed']} inserted={email_res['inserted']} "
        f"events={email_res['events']} labeled={email_res['labeled']}"
    )
    if email_res["errors"]:
        print("  email errors (first 5):")
        for e in email_res["errors"][:5]:
            print(f"    - {e}")

    print("[2/4] Importing Binance P2P BUY orders...")
    p2p_res = import_p2p(args.db, args.days)
    print(f"  fetched={p2p_res['fetched']} inserted={p2p_res['inserted']} ledger_entries={p2p_res['ledger_entries']}")
    if p2p_res["errors"]:
        print("  P2P errors (first 5):")
        for e in p2p_res["errors"][:5]:
            print(f"    - {e}")

    print("[3/4] Deriving FX rates...")
    end_date = date.today()
    start_date = end_date - timedelta(days=args.days)
    fx_res = derive_fx(args.db, start_date, end_date, statuses)
    print(f"  fx_rows={fx_res['rows']}")
    if fx_res["errors"]:
        print("  FX errors:")
        for e in fx_res["errors"]:
            print(f"    - {e}")

    print("[4/4] Importing Binance withdrawals...")
    wd_res = import_withdrawals(args.db, args.days)
    print(f"  fetched={wd_res['fetched']} inserted={wd_res['inserted']} ledger_entries={wd_res['ledger_entries']}")
    if wd_res["errors"]:
        print("  withdrawal errors (first 5):")
        for e in wd_res["errors"][:5]:
            print(f"    - {e}")

    if args.reports:
        print("[5/5] Generating reports...")
        cmd = [sys.executable, str(PROJECT_ROOT / "scripts" / "generate_transfer_ledger_reports.py"), "--days", str(args.days)]
        if args.current_usdt is not None:
            cmd += ["--current-usdt", str(args.current_usdt)]
        subprocess.run(cmd, check=False)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
