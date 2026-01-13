#!/usr/bin/env python3
"""Autonomous end-to-end transfer ledger sync.

Pipeline:
1) Import exchanger emails (Gmail)
2) Import Binance P2P BUY orders (USDT/KZT)
3) Derive FX rates (USDT/KZT + USDT/CNY) and upsert dim_fx_rates
4) Import Binance withdrawals (USDT TRC20) and post ledger entries
5) Import Binance deposits + universal transfers
6) Snapshot funding wallet balances + account snapshots
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from core.integrations.gmail_imap_client import fetch_messages
from core.transfer_ledger.exchanger_email_import import parse_exchanger_email
from core.transfer_ledger.repository import (
    upsert_exchanger_order,
    insert_exchanger_event,
    insert_funding_balance_snapshot,
    upsert_binance_account_snapshot,
)
from core.transfer_ledger.exchanger_matching import label_withdrawals_for_order
from core.integrations.binance_c2c_client import BinanceC2CClient
from core.transfer_ledger.binance_import import import_binance_orders
from core.integrations.binance_wallet_client import BinanceWalletClient
from core.transfer_ledger.binance_withdraw_import import import_binance_withdrawals
from core.transfer_ledger.binance_deposit_import import import_binance_deposits
from core.transfer_ledger.binance_transfer_import import import_binance_transfers
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


def import_deposits(db_path: Path, days: int, coin: str = "USDT") -> dict:
    client = BinanceWalletClient()
    end_date = date.today()
    start_date = end_date - timedelta(days=days)
    start_dt = _date_bounds(start_date, end=False)
    end_dt = _date_bounds(end_date, end=True)

    total_rows = 0
    total_inserted = 0
    errors: list[str] = []

    windows = _window_ranges(start_dt, end_dt, max_days=90)
    for win_start, win_end in windows:
        try:
            raw_deposits = client.iter_deposits(
                coin=coin,
                start_time_ms=_to_ms(win_start),
                end_time_ms=_to_ms(win_end),
            )
        except Exception as exc:
            errors.append(str(exc))
            continue
        total_rows += len(raw_deposits)
        result = import_binance_deposits(raw_deposits, db_path=db_path)
        total_inserted += result["inserted"]
        errors.extend(result["errors"])

    return {
        "fetched": total_rows,
        "inserted": total_inserted,
        "errors": errors,
    }


def import_transfers(db_path: Path, days: int, types: list[str]) -> dict:
    client = BinanceWalletClient()
    end_date = date.today()
    start_date = end_date - timedelta(days=days)
    start_dt = _date_bounds(start_date, end=False)
    end_dt = _date_bounds(end_date, end=True)

    total_rows = 0
    total_inserted = 0
    errors: list[str] = []

    windows = _window_ranges(start_dt, end_dt, max_days=180)
    for transfer_type in types:
        for win_start, win_end in windows:
            try:
                raw_rows = client.iter_universal_transfers(
                    transfer_type=transfer_type,
                    start_time_ms=_to_ms(win_start),
                    end_time_ms=_to_ms(win_end),
                )
            except Exception as exc:
                errors.append(str(exc))
                continue
            total_rows += len(raw_rows)
            result = import_binance_transfers(raw_rows, db_path=db_path)
            total_inserted += result["inserted"]
            errors.extend(result["errors"])

    return {
        "fetched": total_rows,
        "inserted": total_inserted,
        "errors": errors,
    }


def snapshot_funding_balances(db_path: Path, asset: str | None = "USDT") -> dict:
    client = BinanceWalletClient()
    errors: list[str] = []
    try:
        rows = client.get_funding_assets(asset=asset)
    except Exception as exc:
        return {"captured": 0, "errors": [str(exc)]}

    snapshot_time = datetime.now().isoformat()
    captured = 0
    for row in rows:
        asset_name = (row.get("asset") or "").upper()
        if not asset_name:
            continue
        try:
            free = float(row.get("free", 0) or 0)
            locked = float(row.get("locked", 0) or 0)
        except (TypeError, ValueError):
            free = None
            locked = None
        total = free + locked if free is not None and locked is not None else None
        insert_funding_balance_snapshot(
            {
                "snapshot_time": snapshot_time,
                "asset": asset_name,
                "free": free,
                "locked": locked,
                "total": total,
                "raw_json": json.dumps(row, ensure_ascii=False),
                "source": "BINANCE_FUNDING_BAL",
            },
            db_path=db_path,
        )
        captured += 1
    return {"captured": captured, "errors": errors}


def import_account_snapshots(db_path: Path, days: int, account_type: str = "SPOT") -> dict:
    client = BinanceWalletClient()
    end_date = date.today()
    start_date = end_date - timedelta(days=min(days, 30))
    start_dt = _date_bounds(start_date, end=False)
    end_dt = _date_bounds(end_date, end=True)

    total = 0
    inserted = 0
    errors: list[str] = []

    windows = _window_ranges(start_dt, end_dt, max_days=30)
    for win_start, win_end in windows:
        try:
            rows = client.list_account_snapshots(
                account_type=account_type,
                start_time_ms=_to_ms(win_start),
                end_time_ms=_to_ms(win_end),
                limit=30,
            )
        except Exception as exc:
            errors.append(str(exc))
            continue
        total += len(rows)
        for row in rows:
            try:
                snapshot_time = row.get("updateTime") or row.get("snapshotTime")
                snapshot_id = f"{account_type}:{snapshot_time or datetime.now().isoformat()}"
                data = row.get("data") or {}
                total_btc = data.get("totalAssetOfBtc") if isinstance(data, dict) else None
                payload = {
                    "snapshot_id": snapshot_id,
                    "account_type": account_type,
                    "snapshot_time": snapshot_time,
                    "total_asset_btc": total_btc,
                    "data_json": json.dumps(data, ensure_ascii=False),
                    "raw_json": json.dumps(row, ensure_ascii=False),
                    "source": "BINANCE_SNAPSHOT",
                }
                if upsert_binance_account_snapshot(payload, db_path=db_path):
                    inserted += 1
            except Exception as exc:
                errors.append(str(exc))

    return {"fetched": total, "inserted": inserted, "errors": errors}


def main() -> int:
    parser = argparse.ArgumentParser(description="Autonomous transfer ledger sync")
    parser.add_argument("--db", type=Path, default=DB_PATH, help="Path to SQLite DB")
    parser.add_argument("--days", type=int, default=120, help="Lookback days")
    parser.add_argument("--po-plan", type=Path, default=None, help="Optional PO funding plan Excel file")
    parser.add_argument("--mailbox", default=None, help="Gmail mailbox/label")
    parser.add_argument("--query", default=None, help="Gmail search query")
    parser.add_argument("--since-days", type=int, default=30, help="Gmail lookback days")
    parser.add_argument("--limit", type=int, default=200, help="Max Gmail messages")
    parser.add_argument("--skip-emails", action="store_true", help="Skip Gmail IMAP import")
    parser.add_argument("--statuses", default="COMPLETED", help="Exchanger statuses for FX")
    parser.add_argument("--current-usdt", type=float, default=None, help="Override current USDT balance")
    parser.add_argument("--reports", action="store_true", help="Generate Markdown reports")
    parser.add_argument("--report-days", type=int, default=0, help="Report lookback days (0 for full history)")
    parser.add_argument("--transfer-types", default="MAIN_FUNDING,FUNDING_MAIN", help="Universal transfer types")
    parser.add_argument("--skip-deposits", action="store_true", help="Skip deposit history")
    parser.add_argument("--skip-transfers", action="store_true", help="Skip universal transfer history")
    parser.add_argument("--skip-funding-balance", action="store_true", help="Skip funding balance snapshot")
    parser.add_argument("--skip-snapshots", action="store_true", help="Skip account snapshots")
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

    po_plan = args.po_plan or _get_env("PO_PLAN_XLSX", "PO_FUNDING_PLAN_XLSX")
    if po_plan:
        print("[0/9] Importing PO funding plan...")
        cmd = [
            sys.executable,
            str(PROJECT_ROOT / "scripts" / "import_po_funding_plan.py"),
            "--xlsx",
            str(po_plan),
        ]
        subprocess.run(cmd, check=False)

    if args.skip_emails:
        print("[1/9] Skipping exchanger emails (IMAP)")
    else:
        print("[1/9] Importing exchanger emails...")
        email_res = import_emails(args.db, mailbox, query, args.since_days, args.limit)
        print(
            f"  parsed={email_res['parsed']} inserted={email_res['inserted']} "
            f"events={email_res['events']} labeled={email_res['labeled']}"
        )
        if email_res["errors"]:
            print("  email errors (first 5):")
            for e in email_res["errors"][:5]:
                print(f"    - {e}")

    print("[2/9] Importing Binance P2P BUY orders...")
    p2p_res = import_p2p(args.db, args.days)
    print(f"  fetched={p2p_res['fetched']} inserted={p2p_res['inserted']} ledger_entries={p2p_res['ledger_entries']}")
    if p2p_res["errors"]:
        print("  P2P errors (first 5):")
        for e in p2p_res["errors"][:5]:
            print(f"    - {e}")

    print("[3/9] Deriving FX rates...")
    end_date = date.today()
    start_date = end_date - timedelta(days=args.days)
    fx_res = derive_fx(args.db, start_date, end_date, statuses)
    print(f"  fx_rows={fx_res['rows']}")
    if fx_res["errors"]:
        print("  FX errors:")
        for e in fx_res["errors"]:
            print(f"    - {e}")

    print("[4/9] Importing Binance withdrawals...")
    wd_res = import_withdrawals(args.db, args.days)
    print(f"  fetched={wd_res['fetched']} inserted={wd_res['inserted']} ledger_entries={wd_res['ledger_entries']}")
    if wd_res["errors"]:
        print("  withdrawal errors (first 5):")
        for e in wd_res["errors"][:5]:
            print(f"    - {e}")

    print("[5/9] Importing Binance withdrawal emails...")
    cmd = [
        sys.executable,
        str(PROJECT_ROOT / "scripts" / "import_binance_withdrawal_emails.py"),
        "--since-days",
        str(args.since_days),
    ]
    subprocess.run(cmd, check=False)

    if not args.skip_deposits:
        print("[6/9] Importing Binance deposits...")
        dep_res = import_deposits(args.db, args.days)
        print(f"  fetched={dep_res['fetched']} inserted={dep_res['inserted']}")
        if dep_res["errors"]:
            print("  deposit errors (first 5):")
            for e in dep_res["errors"][:5]:
                print(f"    - {e}")

    if not args.skip_transfers:
        print("[7/9] Importing Binance transfers...")
        types = [t.strip() for t in args.transfer_types.split(",") if t.strip()]
        trans_res = import_transfers(args.db, args.days, types=types)
        print(f"  fetched={trans_res['fetched']} inserted={trans_res['inserted']}")
        if trans_res["errors"]:
            print("  transfer errors (first 5):")
            for e in trans_res["errors"][:5]:
                print(f"    - {e}")

    if not args.skip_funding_balance:
        print("[8/9] Snapshotting funding wallet balances...")
        bal_res = snapshot_funding_balances(args.db)
        print(f"  captured={bal_res['captured']}")
        if bal_res["errors"]:
            print("  funding balance errors (first 5):")
            for e in bal_res["errors"][:5]:
                print(f"    - {e}")

    if not args.skip_snapshots:
        snap_res = import_account_snapshots(args.db, args.days)
        if snap_res["errors"]:
            print("  snapshot errors (first 5):")
            for e in snap_res["errors"][:5]:
                print(f"    - {e}")

    if args.reports:
        print("[9/9] Generating reports...")
        cmd = [sys.executable, str(PROJECT_ROOT / "scripts" / "generate_transfer_ledger_reports.py")]
        if args.report_days and args.report_days > 0:
            cmd += ["--days", str(args.report_days)]
        if args.current_usdt is not None:
            cmd += ["--current-usdt", str(args.current_usdt)]
        subprocess.run(cmd, check=False)
        subprocess.run([sys.executable, str(PROJECT_ROOT / "scripts" / "generate_po_payment_status.py")], check=False)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
