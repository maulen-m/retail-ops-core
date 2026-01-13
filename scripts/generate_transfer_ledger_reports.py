#!/usr/bin/env python3
"""Generate Markdown reports for transfer ledger (P2P, exchanger, combined)."""

from __future__ import annotations

import argparse
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from core.integrations.binance_wallet_client import BinanceWalletClient
from core.transfer_ledger.exchanger_matching import AMOUNT_TOLERANCE, DATE_WINDOW_DAYS, address_match
from core.transfer_ledger.repository import (
    list_deposits,
    list_transfers,
    list_funding_balance_snapshots,
    list_pos_for_allocation,
    get_po_total_cny_from_lines,
    list_po_funding_plan,
    list_po_exchanger_allocations,
)


DB_PATH = PROJECT_ROOT / "db" / "app.db"
LOCAL_TZ = timezone(timedelta(hours=5))
UTC = timezone.utc
EPOCH = datetime.min.replace(tzinfo=UTC)


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


def _ascii_table(rows, cols):
    widths = [w for _, w in cols]
    sep = "+" + "+".join("-" * w for w in widths) + "+"
    header = "|" + "|".join(name.ljust(widths[i]) for i, (name, _) in enumerate(cols)) + "|"
    lines = [sep, header, sep]
    for r in rows:
        line = "|" + "|".join(str(r[i]).ljust(widths[i])[:widths[i]] for i in range(len(cols))) + "|"
        lines.append(line)
    lines.append(sep)
    return lines


def _parse_dt(value) -> datetime | None:
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=UTC)
        else:
            dt = dt.astimezone(UTC)
        return dt
    except Exception:
        return None


def _fmt_dt(value) -> str:
    dt = value if isinstance(value, datetime) else _parse_dt(value)
    if not dt:
        return ""
    local = dt.astimezone(LOCAL_TZ)
    return local.strftime("%Y-%m-%d %H:%M:%S")


def _fmt(value, digits: int = 2) -> str:
    if value is None:
        return ""
    try:
        return f"{float(value):.{digits}f}"
    except (TypeError, ValueError):
        return ""


def _avg_recent_rate(rates: list[tuple[datetime, float]], dt: datetime | None, window: int = 5) -> float | None:
    if not dt:
        return None
    values = [rate for rate_dt, rate in rates if rate_dt and rate_dt <= dt]
    if not values:
        return None
    recent = values[-window:]
    return sum(recent) / len(recent)


def _transfer_delta(transfer_type: str | None, amount: float) -> float:
    if not transfer_type:
        return 0.0
    t = transfer_type.upper()
    if t.startswith("FUNDING_"):
        return -amount
    if t.endswith("_FUNDING"):
        return amount
    return 0.0


def _is_funding_wallet(value) -> bool:
    if value is None:
        return False
    text = str(value).strip().upper()
    return text in {"1", "FUNDING"}


def _match_withdrawal_for_order(order: dict, withdrawals: list[dict], used_ids: set[str]) -> dict | None:
    amount = order.get("amount_usdt")
    if amount is None:
        return None
    order_dt = _parse_dt(order.get("message_date"))
    address = (order.get("deposit_address") or "").strip()

    best = None
    best_delta = float("inf")
    for wd in withdrawals:
        wd_id = wd.get("withdraw_id")
        if not wd_id or wd_id in used_ids:
            continue
        if address and not address_match(address, wd.get("address") or ""):
            continue
        wd_amount = wd.get("amount")
        if wd_amount is None or abs(float(wd_amount) - float(amount)) > AMOUNT_TOLERANCE:
            continue
        wd_dt = _parse_dt(wd.get("apply_time"))
        if order_dt and wd_dt:
            delta_sec = abs((wd_dt - order_dt).total_seconds())
            if delta_sec > DATE_WINDOW_DAYS * 86400:
                continue
        else:
            delta_sec = 0
        if delta_sec < best_delta:
            best = wd
            best_delta = delta_sec
    return best


def _effective_usdt(amount_usdt: float, fee_usdt: float) -> float:
    try:
        return float(amount_usdt) + float(fee_usdt or 0)
    except (TypeError, ValueError):
        return float(amount_usdt or 0)


def _get_current_usdt_balance() -> float | None:
    try:
        client = BinanceWalletClient()
        return client.get_funding_balance("USDT")
    except Exception:
        return None


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate transfer ledger reports")
    parser.add_argument("--db", type=Path, default=DB_PATH, help="Path to SQLite DB")
    parser.add_argument("--days", type=int, default=None, help="Lookback days (omit or 0 for full history)")
    parser.add_argument("--current-usdt", type=float, default=None, help="Override current USDT balance")
    parser.add_argument("--output-dir", type=Path, default=PROJECT_ROOT / "docs" / "transfer_ledger")
    args = parser.parse_args()

    _load_env_file(PROJECT_ROOT / ".env")

    end_dt = datetime.now()
    start_dt = None
    start_iso = None
    if args.days and args.days > 0:
        start_dt = end_dt - timedelta(days=args.days)
        start_iso = start_dt.isoformat()

    import sqlite3

    conn = sqlite3.connect(str(args.db))
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    # P2P orders (USDT/KZT)
    p2p_where = (
        "WHERE trade_type='BUY' AND asset='USDT' AND fiat='KZT' "
        "AND order_status='COMPLETED'"
    )
    p2p_params: list = []
    if start_iso:
        p2p_where += " AND create_time >= ?"
        p2p_params.append(start_iso)
    rows_p2p = cur.execute(
        f"""
        SELECT order_number, create_time, fiat_amount, crypto_amount, unit_price, counterparty, account_label
        FROM binance_c2c_orders
        {p2p_where}
        ORDER BY create_time DESC
        """,
        p2p_params,
    ).fetchall()

    # Exchanger orders (USDT->CNY)
    ex_where = "WHERE amount_usdt IS NOT NULL AND amount_cny IS NOT NULL"
    ex_params: list = []
    if start_iso:
        ex_where += " AND message_date >= ?"
        ex_params.append(start_iso)
    rows_ex_all = cur.execute(
        f"""
        SELECT exchanger_order_id, exchanger, order_id, status, message_date,
               amount_usdt, amount_cny, deposit_address
        FROM exchanger_orders
        {ex_where}
        ORDER BY message_date DESC
        """,
        ex_params,
    ).fetchall()
    rows_ex = [r for r in rows_ex_all if (r["status"] or "").upper() != "CANCELLED"]
    rows_ex_cancelled = [r for r in rows_ex_all if (r["status"] or "").upper() == "CANCELLED"]

    if start_iso:
        rows_dep = list_deposits(db_path=args.db, start_time=start_iso, coin="USDT")
        rows_trans = list_transfers(db_path=args.db, start_time=start_iso, asset="USDT")
    else:
        rows_dep = list_deposits(db_path=args.db, coin="USDT")
        rows_trans = list_transfers(db_path=args.db, asset="USDT")
    snapshot_usdt = None
    snapshots = list_funding_balance_snapshots(db_path=args.db, asset="USDT", limit=1)
    if snapshots:
        snap = snapshots[0]
        snapshot_usdt = snap.get("total") if snap.get("total") is not None else snap.get("free")

    # Events for duration (optional table)
    events_by_order: dict[str, dict[str, list[datetime]]] = {}
    try:
        table = cur.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='exchanger_order_events'"
        ).fetchone()
        if table:
            if start_iso:
                events = cur.execute(
                    """
                    SELECT exchanger_order_id, status, message_date
                    FROM exchanger_order_events
                    WHERE message_date >= ?
                    """,
                    (start_iso,),
                ).fetchall()
            else:
                events = cur.execute(
                    """
                    SELECT exchanger_order_id, status, message_date
                    FROM exchanger_order_events
                    """
                ).fetchall()
            for e in events:
                oid = e["exchanger_order_id"]
                if not oid:
                    continue
                status = (e["status"] or "").upper()
                dt = _parse_dt(e["message_date"])
                if not dt:
                    continue
                events_by_order.setdefault(oid, {}).setdefault(status, []).append(dt)
    except Exception:
        pass

    # Withdrawals for cross-ref + balances
    if start_iso:
        withdrawals = cur.execute(
            """
        SELECT withdraw_id, amount, transaction_fee, address, apply_time, exchanger_order_id, account_label
        FROM binance_withdrawals
            WHERE apply_time >= ?
            """,
            (start_iso,),
        ).fetchall()
    else:
        withdrawals = cur.execute(
            """
            SELECT withdraw_id, amount, transaction_fee, address, apply_time, exchanger_order_id, account_label
            FROM binance_withdrawals
            """
        ).fetchall()

    withdrawals_list = [dict(w) for w in withdrawals]
    wd_by_order = {w["exchanger_order_id"]: w for w in withdrawals_list if w["exchanger_order_id"]}
    unmatched_withdrawals = [w for w in withdrawals_list if not w.get("exchanger_order_id")]
    used_withdrawals: set[str] = set()
    order_matches: dict[str, dict] = {}

    for r in rows_ex:
        order_key = r["exchanger_order_id"]
        match = wd_by_order.get(order_key)
        if not match:
            match = _match_withdrawal_for_order(dict(r), unmatched_withdrawals, used_withdrawals)
            if match and match.get("withdraw_id"):
                used_withdrawals.add(match["withdraw_id"])
        if match:
            order_matches[order_key] = match

    # Build USDT event timeline for balance
    usdt_events = []
    for r in rows_p2p:
        dt = r["create_time"]
        usdt_events.append((dt, f"p2p:{r['order_number']}", float(r["crypto_amount"] or 0)))
    for w in withdrawals_list:
        dt = w.get("apply_time")
        usdt_events.append((dt, f"wd:{w['withdraw_id']}", -float(w.get("amount") or 0)))
    for d in rows_dep:
        if (d.get("coin") or "").upper() != "USDT":
            continue
        if not _is_funding_wallet(d.get("wallet_type")):
            continue
        dt = d.get("insert_time")
        if dt:
            usdt_events.append((dt, f"dep:{d['deposit_id']}", float(d.get("amount") or 0)))
    for t in rows_trans:
        if (t.get("asset") or "").upper() != "USDT":
            continue
        delta = _transfer_delta(t.get("transfer_type") or "", float(t.get("amount") or 0))
        if delta == 0:
            continue
        dt = t.get("timestamp")
        if dt:
            usdt_events.append((dt, f"xfer:{t['transfer_id']}", delta))

    # Sort descending
    usdt_events.sort(key=lambda x: _parse_dt(x[0]) or EPOCH, reverse=True)

    current_usdt = args.current_usdt
    api_usdt = None
    if current_usdt is None:
        api_usdt = _get_current_usdt_balance()
        current_usdt = api_usdt if api_usdt is not None else snapshot_usdt

    balance_after: dict[str, float] = {}
    if current_usdt is not None:
        bal = float(current_usdt)
        for dt, key, delta in usdt_events:
            balance_after[key] = bal
            bal -= delta

    p2p_rates: list[tuple[datetime, float]] = []
    for r in rows_p2p:
        rate = r["unit_price"]
        dt = _parse_dt(r["create_time"])
        if dt and rate is not None:
            try:
                p2p_rates.append((dt, float(rate)))
            except (TypeError, ValueError):
                continue
    p2p_rates.sort(key=lambda x: x[0])

    ex_rates: list[tuple[datetime, float]] = []
    for r in rows_ex:
        dt = _parse_dt(r["message_date"])
        amount_usdt = r["amount_usdt"]
        fee_usdt = 0.0
        match = order_matches.get(r["exchanger_order_id"])
        if match:
            fee_usdt = float(match.get("transaction_fee") or 0)
        amount_cny = r["amount_cny"]
        if not dt or amount_usdt is None or amount_cny is None:
            continue
        try:
            rate = float(amount_cny) / _effective_usdt(float(amount_usdt), fee_usdt)
        except (TypeError, ValueError, ZeroDivisionError):
            continue
        if rate > 0:
            ex_rates.append((dt, rate))
    ex_rates.sort(key=lambda x: x[0])

    # PO plan data (from po_funding_plan or po_header fallback)
    po_plan_by_id: dict[str, dict] = {}
    po_cny_list: list[tuple[datetime, str, float]] = []
    po_usdt_list: list[tuple[datetime, str, float]] = []

    plan_rows = list_po_funding_plan(db_path=args.db)
    if plan_rows:
        for row in plan_rows:
            po_id = row.get("po_id")
            po_date = _parse_dt(row.get("message_date"))
            if not po_id or not po_date:
                continue
            total_cny = row.get("total_cny")
            total_usdt = row.get("total_usdt")
            try:
                total_cny = float(total_cny) if total_cny is not None else None
            except (TypeError, ValueError):
                total_cny = None
            try:
                total_usdt = float(total_usdt) if total_usdt is not None else None
            except (TypeError, ValueError):
                total_usdt = None
            po_plan_by_id[po_id] = {
                "po_date": po_date,
                "total_cny": total_cny,
                "total_usdt": total_usdt,
            }
            if total_cny and total_cny > 0:
                po_cny_list.append((po_date, po_id, total_cny))
            if total_usdt is None and total_cny and ex_rates:
                rate = _avg_recent_rate(ex_rates, po_date, window=5)
                if rate and rate > 0:
                    total_usdt = total_cny / rate
            if total_usdt and total_usdt > 0:
                po_usdt_list.append((po_date, po_id, total_usdt))
    else:
        pos = list_pos_for_allocation(db_path=args.db)
        for row in pos:
            po_id = row.get("po_id")
            po_date = _parse_dt(row.get("message_date") or row.get("created_at"))
            if not po_id or not po_date:
                continue
            total_cny = row.get("total_cost_cny")
            if total_cny is None or float(total_cny or 0) <= 0:
                total_cny = get_po_total_cny_from_lines(po_id, db_path=args.db)
            try:
                total_cny = float(total_cny) if total_cny is not None else None
            except (TypeError, ValueError):
                total_cny = None
            if total_cny and total_cny > 0:
                po_plan_by_id[po_id] = {
                    "po_date": po_date,
                    "total_cny": total_cny,
                    "total_usdt": None,
                }
                po_cny_list.append((po_date, po_id, total_cny))
                if ex_rates:
                    rate = _avg_recent_rate(ex_rates, po_date, window=5)
                    if rate and rate > 0:
                        po_usdt_list.append((po_date, po_id, total_cny / rate))

    po_cny_list.sort(key=lambda x: (x[0], x[1]))
    po_usdt_list.sort(key=lambda x: (x[0], x[1]))
    po_total_usdt_by_id = {po_id: total_usdt for _, po_id, total_usdt in po_usdt_list}
    po_dates_by_id = {po_id: po_date for po_date, po_id, _ in po_cny_list}

    # Allocate P2P USDT buys to PO totals (USDT)
    po_info_by_p2p: dict[str, dict] = {}
    if po_usdt_list:
        po_state_usdt = {
            po_id: {"total_usdt": total_usdt, "paid_usdt": 0.0}
            for _, po_id, total_usdt in po_usdt_list
        }
        orders_for_alloc = []
        for r in rows_p2p:
            order_dt = _parse_dt(r["create_time"])
            amount_usdt = float(r["crypto_amount"] or 0)
            if not order_dt or amount_usdt <= 0:
                continue
            orders_for_alloc.append((order_dt, r, amount_usdt))
        orders_for_alloc.sort(key=lambda x: x[0])

        po_idx = 0
        for order_dt, row, amount_usdt in orders_for_alloc:
            while po_idx + 1 < len(po_usdt_list) and order_dt >= po_usdt_list[po_idx + 1][0]:
                po_idx += 1

            remaining = amount_usdt
            last_po_id = None
            last_total = None
            last_paid = None
            last_left = None
            i = po_idx
            while remaining > 0 and i < len(po_usdt_list):
                _, po_id, total_usdt = po_usdt_list[i]
                state = po_state_usdt[po_id]
                left = total_usdt - state["paid_usdt"]
                if left <= 0:
                    i += 1
                    continue
                alloc = min(left, remaining)
                state["paid_usdt"] += alloc
                remaining -= alloc
                last_po_id = po_id
                last_total = total_usdt
                last_paid = state["paid_usdt"]
                last_left = total_usdt - state["paid_usdt"]
                if remaining <= 0:
                    break
                i += 1

            if last_po_id:
                avg_kzt = _avg_recent_rate(p2p_rates, order_dt, window=5)
                plan = po_plan_by_id.get(last_po_id, {})
                total_cny = plan.get("total_cny")
                left_cny = None
                if total_cny and last_total and last_total > 0 and last_left is not None:
                    left_cny = total_cny * (last_left / last_total)
                po_left_kzt = last_left * avg_kzt if last_left is not None and avg_kzt is not None else None
                po_info_by_p2p[row["order_number"]] = {
                    "po_id": last_po_id,
                    "po_total_cny": total_cny,
                    "po_total_usdt": last_total,
                    "po_paid_usdt": last_paid,
                    "po_left_usdt": last_left,
                    "po_left_cny": left_cny,
                    "po_left_kzt": po_left_kzt,
                }

    # P2P double entries
    p2p_entries = []
    for r in rows_p2p:
        order = r["order_number"]
        dt = r["create_time"]
        usdt = float(r["crypto_amount"] or 0)
        kzt = float(r["fiat_amount"] or 0)
        rate = float(r["unit_price"] or 0)
        cp = r["counterparty"] or ""
        acct = r["account_label"] or ""
        bal = balance_after.get(f"p2p:{order}")

        po_info = po_info_by_p2p.get(order, {})
        po_id = po_info.get("po_id", "")
        po_total_cny = _fmt(po_info.get("po_total_cny"))
        po_total_usdt = _fmt(po_info.get("po_total_usdt"))
        po_paid_usdt = _fmt(po_info.get("po_paid_usdt"))
        po_left_usdt = _fmt(po_info.get("po_left_usdt"))
        po_left_cny = _fmt(po_info.get("po_left_cny"))
        po_left_kzt = _fmt(po_info.get("po_left_kzt"))

        p2p_entries.append([
            _fmt_dt(dt),
            str(order),
            acct,
            "ASSET",
            "USDT",
            f"{usdt:.2f}",
            f"{usdt * rate:.2f}",
            f"{rate:.4f}",
            f"{bal:.2f}" if bal is not None else "",
            cp,
            po_id,
            po_total_cny,
            po_total_usdt,
            po_paid_usdt,
            po_left_usdt,
            po_left_cny,
            po_left_kzt,
        ])
        p2p_entries.append([
            _fmt_dt(dt),
            str(order),
            acct,
            "FIAT",
            "KZT",
            f"{-kzt:.2f}",
            f"{-kzt:.2f}",
            "1.0000",
            f"{bal:.2f}" if bal is not None else "",
            cp,
            po_id,
            po_total_cny,
            po_total_usdt,
            po_paid_usdt,
            po_left_usdt,
            po_left_cny,
            po_left_kzt,
        ])

    po_info_by_order: dict[str, dict] = {}
    po_timeline_data: list[tuple[datetime, dict, dict]] = []
    po_last_payment: dict[str, datetime] = {}

    # Prefer explicit PO mappings if present, but compute a unified chronological timeline.
    alloc_rows = list_po_exchanger_allocations(db_path=args.db)
    alloc_by_order = {r["exchanger_order_id"]: r for r in alloc_rows if r.get("exchanger_order_id")}

    po_list = po_cny_list
    po_state: dict[str, dict] = {}
    if po_list:
        po_state = {po_id: {"total_cny": total_cny, "paid_cny": 0.0} for _, po_id, total_cny in po_list}
        orders_for_alloc = []
        for r in rows_ex:
            amount_cny = float(r["amount_cny"] or 0)
            base_usdt = float(r["amount_usdt"] or 0)
            match = order_matches.get(r["exchanger_order_id"])
            fee_usdt = float(match.get("transaction_fee") or 0) if match else 0.0
            amount_usdt = _effective_usdt(base_usdt, fee_usdt)
            if amount_cny <= 0 or amount_usdt <= 0:
                continue
            order_dt = _parse_dt(r["message_date"])
            if not order_dt:
                continue
            status = (r["status"] or "").upper()
            if status == "CANCELLED":
                continue
            orders_for_alloc.append((order_dt, r))
        orders_for_alloc.sort(key=lambda x: x[0])

        po_idx = 0
        for order_dt, row in orders_for_alloc:
            while po_idx + 1 < len(po_list) and order_dt >= po_list[po_idx + 1][0]:
                po_idx += 1

            ex_id = row["exchanger_order_id"]
            amount_cny = float(row["amount_cny"] or 0)
            base_usdt = float(row["amount_usdt"] or 0)
            match = order_matches.get(ex_id)
            fee_usdt = float(match.get("transaction_fee") or 0) if match else 0.0
            amount_usdt = _effective_usdt(base_usdt, fee_usdt)
            if amount_cny <= 0 or amount_usdt <= 0:
                continue
            rate = amount_cny / amount_usdt if amount_usdt else 0.0

            alloc = alloc_by_order.get(ex_id, {})
            explicit_po = alloc.get("po_id")
            if explicit_po and explicit_po in po_state:
                state = po_state[explicit_po]
                state["paid_cny"] += amount_cny
                total_cny = state["total_cny"]
                paid = state["paid_cny"]
                left_cny = total_cny - paid

                plan_total_usdt = po_plan_by_id.get(explicit_po, {}).get("total_usdt")
                if plan_total_usdt is None and total_cny and rate > 0:
                    plan_total_usdt = total_cny / rate
                if plan_total_usdt and total_cny:
                    po_total_usdt = plan_total_usdt
                    left_usdt = plan_total_usdt * (left_cny / total_cny)
                else:
                    po_total_usdt = total_cny / rate if rate > 0 else None
                    left_usdt = left_cny / rate if left_cny is not None and rate > 0 else None

                avg_kzt = _avg_recent_rate(p2p_rates, order_dt, window=5)
                left_kzt = left_usdt * avg_kzt if left_usdt is not None and avg_kzt is not None else None

                info = {
                    "po_id": explicit_po,
                    "po_total_cny": total_cny,
                    "po_total_usdt": po_total_usdt,
                    "po_paid_cny": paid,
                    "po_left_cny": left_cny,
                    "po_left_usdt": left_usdt,
                    "po_left_kzt": left_kzt,
                }
                po_info_by_order[ex_id] = info
                po_timeline_data.append((order_dt, row, info))
                po_last_payment[explicit_po] = order_dt
                continue

            remaining = amount_cny
            last_po_id = None
            last_po_total = None
            last_paid = None
            last_left = None
            i = po_idx
            while remaining > 0 and i < len(po_list):
                _, po_id, total_cny = po_list[i]
                state = po_state[po_id]
                left = total_cny - state["paid_cny"]
                if left <= 0:
                    i += 1
                    continue
                alloc_amt = min(left, remaining)
                state["paid_cny"] += alloc_amt
                remaining -= alloc_amt
                last_po_id = po_id
                last_po_total = total_cny
                last_paid = state["paid_cny"]
                last_left = total_cny - state["paid_cny"]
                if remaining <= 0:
                    break
                i += 1

            if last_po_id:
                avg_kzt = _avg_recent_rate(p2p_rates, order_dt, window=5)
                plan_total_usdt = po_plan_by_id.get(last_po_id, {}).get("total_usdt")
                if plan_total_usdt and last_po_total and last_po_total > 0 and last_left is not None:
                    po_total_usdt = plan_total_usdt
                    po_left_usdt = plan_total_usdt * (last_left / last_po_total)
                else:
                    po_total_usdt = last_po_total / rate if rate > 0 else None
                    po_left_usdt = last_left / rate if last_left is not None and rate > 0 else None
                po_left_kzt = po_left_usdt * avg_kzt if po_left_usdt is not None and avg_kzt is not None else None
                info = {
                    "po_id": last_po_id,
                    "po_total_cny": last_po_total,
                    "po_total_usdt": po_total_usdt,
                    "po_paid_cny": last_paid,
                    "po_left_cny": last_left,
                    "po_left_usdt": po_left_usdt,
                    "po_left_kzt": po_left_kzt,
                }
                po_info_by_order[ex_id] = info
                po_timeline_data.append((order_dt, row, info))
                po_last_payment[last_po_id] = order_dt

    # Exchanger entries
    ex_entries = []
    for r in rows_ex:
        order = dict(r)
        order_key = order["exchanger_order_id"]
        base_usdt = float(order["amount_usdt"] or 0)
        match = order_matches.get(order_key)
        fee_usdt = float(match.get("transaction_fee") or 0) if match else 0.0
        amount_usdt = _effective_usdt(base_usdt, fee_usdt)
        amount_cny = float(order["amount_cny"] or 0)
        if amount_usdt <= 0 or amount_cny <= 0:
            continue
        rate = amount_cny / amount_usdt
        ref_parts = []
        bal = None
        if match:
            wd_id = match.get("withdraw_id")
            if wd_id:
                ref_parts.append(f"wd={wd_id}")
                bal = balance_after.get(f"wd:{wd_id}")
            if fee_usdt:
                ref_parts.append(f"fee={fee_usdt:.2f}")
            acct = match.get("account_label") or ""
            if acct:
                ref_parts.append(f"acct={acct}")
            addr = match.get("address") or order.get("deposit_address")
            if addr:
                ref_parts.append(f"addr={addr}")
        else:
            addr = order.get("deposit_address")
            if addr:
                ref_parts.append(f"addr={addr}")
        ref = " ".join(ref_parts)

        # Duration
        duration = ""
        if order_key in events_by_order:
            created_list = events_by_order[order_key].get("NEW") or []
            completed_list = events_by_order[order_key].get("COMPLETED") or []
            cancelled_list = events_by_order[order_key].get("CANCELLED") or []
            end_list = completed_list or cancelled_list
            if created_list and end_list:
                dur_min = int((max(end_list) - min(created_list)).total_seconds() // 60)
                duration = str(dur_min)

        po_info = po_info_by_order.get(order_key, {})
        po_id = po_info.get("po_id", "")
        po_total_cny = _fmt(po_info.get("po_total_cny"))
        po_total_usdt = _fmt(po_info.get("po_total_usdt"))
        po_paid_cny = _fmt(po_info.get("po_paid_cny"))
        po_left_cny = _fmt(po_info.get("po_left_cny"))
        po_left_usdt = _fmt(po_info.get("po_left_usdt"))
        po_left_kzt = _fmt(po_info.get("po_left_kzt"))

        dt = order["message_date"]
        ex_entries.append([
            _fmt_dt(dt),
            str(order["order_id"] or order_key),
            order["exchanger"],
            "USDT_OUT",
            "USDT",
            f"{-amount_usdt:.2f}",
            f"{-amount_cny:.2f}",
            f"{rate:.4f}",
            f"{bal:.2f}" if bal is not None else "",
            duration,
            ref,
            po_id,
            po_total_cny,
            po_total_usdt,
            po_paid_cny,
            po_left_cny,
            po_left_usdt,
            po_left_kzt,
        ])
        ex_entries.append([
            _fmt_dt(dt),
            str(order["order_id"] or order_key),
            order["exchanger"],
            "CNY_IN",
            "CNY",
            f"{amount_cny:.2f}",
            f"{amount_cny:.2f}",
            f"{rate:.4f}",
            f"{bal:.2f}" if bal is not None else "",
            duration,
            ref,
            po_id,
            po_total_cny,
            po_total_usdt,
            po_paid_cny,
            po_left_cny,
            po_left_usdt,
            po_left_kzt,
        ])

    # Cancelled orders summary (excluded from ledger allocations)
    cancelled_entries = []
    for r in rows_ex_cancelled:
        amount_usdt = float(r["amount_usdt"] or 0)
        amount_cny = float(r["amount_cny"] or 0)
        cancelled_entries.append([
            _fmt_dt(r["message_date"]),
            str(r["order_id"] or r["exchanger_order_id"]),
            r["exchanger"],
            (r["status"] or "CANCELLED").upper(),
            _fmt(amount_usdt),
            _fmt(amount_cny),
        ])

    # PO balance + timeline rows
    po_balance_rows = []
    po_timeline_rows = []
    if po_state:
        po_keys = sorted(po_state.keys(), key=lambda k: po_dates_by_id.get(k) or EPOCH)
        for po_id in po_keys:
            state = po_state[po_id]
            total_cny = state.get("total_cny")
            paid_cny = state.get("paid_cny", 0.0)
            left_cny = (total_cny - paid_cny) if total_cny is not None else None

            po_total_usdt = po_total_usdt_by_id.get(po_id)
            if po_total_usdt is None and total_cny:
                rate = _avg_recent_rate(ex_rates, po_dates_by_id.get(po_id), window=5)
                if rate and rate > 0:
                    po_total_usdt = total_cny / rate
            if po_total_usdt is not None and total_cny:
                left_usdt = po_total_usdt * (left_cny / total_cny) if left_cny is not None else None
            else:
                left_usdt = None

            last_dt = po_last_payment.get(po_id)
            avg_kzt = _avg_recent_rate(p2p_rates, last_dt or po_dates_by_id.get(po_id), window=5)
            left_kzt = left_usdt * avg_kzt if left_usdt is not None and avg_kzt is not None else None

            po_balance_rows.append([
                po_id,
                _fmt_dt(po_dates_by_id.get(po_id)),
                _fmt(total_cny),
                _fmt(paid_cny),
                _fmt(left_cny),
                _fmt(po_total_usdt),
                _fmt(left_usdt),
                _fmt(left_kzt),
                _fmt_dt(last_dt),
            ])

    if po_timeline_data:
        po_timeline_data.sort(key=lambda x: x[0])
        for order_dt, row, info in po_timeline_data:
            base_usdt = float(row["amount_usdt"] or 0)
            match = order_matches.get(row["exchanger_order_id"])
            fee_usdt = float(match.get("transaction_fee") or 0) if match else 0.0
            amount_usdt = _effective_usdt(base_usdt, fee_usdt)
            amount_cny = float(row["amount_cny"] or 0)
            rate = amount_cny / amount_usdt if amount_usdt else 0.0
            po_timeline_rows.append([
                _fmt_dt(order_dt),
                str(row["order_id"] or row["exchanger_order_id"]),
                row["exchanger"],
                (row["status"] or "").upper(),
                _fmt(amount_usdt),
                _fmt(amount_cny),
                f"{rate:.4f}" if rate else "",
                info.get("po_id", ""),
                _fmt(info.get("po_total_cny")),
                _fmt(info.get("po_paid_cny")),
                _fmt(info.get("po_left_cny")),
                _fmt(info.get("po_left_usdt")),
                _fmt(info.get("po_left_kzt")),
            ])

    conn.close()

    # Tables
    p2p_cols = [
        ("Date", 19), ("Order", 12), ("Acct", 10), ("Leg", 8), ("Curr", 5),
        ("Amount", 14), ("KZT_Value", 14), ("Rate", 10),
        ("USDT_Bal", 12), ("Counterparty", 80),
        ("PO", 12), ("PO_Tot_CNY", 12), ("PO_Tot_USDT", 12),
        ("PO_Paid_USDT", 12), ("PO_Left_USDT", 12), ("PO_Left_CNY", 12),
        ("PO_Left_KZT", 12)
    ]
    ex_cols = [
        ("Date", 19), ("Order", 12), ("Exch", 12), ("Leg", 8), ("Curr", 5),
        ("Amount", 14), ("CNY_Value", 14), ("USDT/CNY", 10),
        ("USDT_Bal", 12), ("Duration_min", 12), ("Ref", 50),
        ("PO", 12), ("PO_Tot_CNY", 12), ("PO_Tot_USDT", 12),
        ("PO_Paid_CNY", 12), ("PO_Left_CNY", 12), ("PO_Left_USDT", 12),
        ("PO_Left_KZT", 12)
    ]
    cancel_cols = [
        ("Date", 19), ("Order", 12), ("Exch", 12), ("Status", 10),
        ("USDT", 12), ("CNY", 12)
    ]
    po_balance_cols = [
        ("PO", 12), ("PO_Date", 19), ("Total_CNY", 12), ("Paid_CNY", 12),
        ("Left_CNY", 12), ("Total_USDT", 12), ("Left_USDT", 12),
        ("Left_KZT", 12), ("Last_Payment", 19)
    ]
    po_timeline_cols = [
        ("Date", 19), ("Order", 12), ("Exch", 12), ("Status", 10),
        ("USDT", 12), ("CNY", 12), ("USDT/CNY", 10), ("PO", 12),
        ("PO_Tot_CNY", 12), ("PO_Paid_CNY", 12), ("PO_Left_CNY", 12),
        ("PO_Left_USDT", 12), ("PO_Left_KZT", 12)
    ]

    # Write docs
    args.output_dir.mkdir(parents=True, exist_ok=True)

    # P2P report
    p2p_doc = []
    label_suffix = f"Last {args.days} Days" if start_dt else "Full History"
    window_label = f"{start_dt.date().isoformat()} → {end_dt.date().isoformat()}" if start_dt else "full history"
    name_suffix = f"LAST_{args.days}_DAYS" if start_dt else "FULL_HISTORY"

    p2p_doc.append(f"# Binance P2P BUY (USDT/KZT) — {label_suffix}")
    p2p_doc.append("")
    p2p_doc.append(f"Window: {window_label}")
    if current_usdt is not None:
        p2p_doc.append(f"Current funding USDT (used for balance): {current_usdt}")
    if api_usdt is not None:
        p2p_doc.append(f"Funding USDT (API): {api_usdt}")
    if snapshot_usdt is not None:
        p2p_doc.append(f"Funding USDT (snapshot): {snapshot_usdt}")
    p2p_doc.append("")
    p2p_doc.append("## Double-book Entries (ASCII)")
    p2p_doc.append("")
    p2p_doc.append("```text")
    p2p_doc.extend(_ascii_table(p2p_entries, p2p_cols))
    p2p_doc.append("```")

    (args.output_dir / f"P2P_BUY_{name_suffix}.md").write_text("\n".join(p2p_doc))

    # Exchanger report
    ex_doc = []
    ex_doc.append(f"# Exchanger USDT→CNY Buys — {label_suffix}")
    ex_doc.append("")
    ex_doc.append(f"Window: {window_label}")
    if current_usdt is not None:
        ex_doc.append(f"Current funding USDT (used for balance): {current_usdt}")
    if api_usdt is not None:
        ex_doc.append(f"Funding USDT (API): {api_usdt}")
    if snapshot_usdt is not None:
        ex_doc.append(f"Funding USDT (snapshot): {snapshot_usdt}")
    ex_doc.append("")
    ex_doc.append("## Double-book Entries (ASCII)")
    ex_doc.append("")
    ex_doc.append("```text")
    ex_doc.extend(_ascii_table(ex_entries, ex_cols))
    ex_doc.append("```")
    if cancelled_entries:
        ex_doc.append("")
        ex_doc.append("## Cancelled Orders (Excluded from Ledger)")
        ex_doc.append("")
        ex_doc.append("```text")
        ex_doc.extend(_ascii_table(cancelled_entries, cancel_cols))
        ex_doc.append("```")

    (args.output_dir / f"EXCHANGER_BUY_{name_suffix}.md").write_text("\n".join(ex_doc))

    # Combined report
    combo = []
    combo.append(f"# Transfer Ledger — {label_suffix} (Combined)")
    combo.append("")
    combo.append(f"Window: {window_label}")
    if current_usdt is not None:
        combo.append(f"Current funding USDT (used for balance): {current_usdt}")
    if api_usdt is not None:
        combo.append(f"Funding USDT (API): {api_usdt}")
    if snapshot_usdt is not None:
        combo.append(f"Funding USDT (snapshot): {snapshot_usdt}")
    combo.append("")
    combo.append("## Binance P2P USDT/KZT Buys")
    combo.append("")
    combo.append("```text")
    combo.extend(_ascii_table(p2p_entries, p2p_cols))
    combo.append("```")
    combo.append("")
    combo.append("## Exchanger USDT→CNY Buys")
    combo.append("")
    combo.append("```text")
    combo.extend(_ascii_table(ex_entries, ex_cols))
    combo.append("```")
    if cancelled_entries:
        combo.append("")
        combo.append("## Cancelled Orders (Excluded from Ledger)")
        combo.append("")
        combo.append("```text")
        combo.extend(_ascii_table(cancelled_entries, cancel_cols))
        combo.append("```")

    (args.output_dir / f"TRANSFER_LEDGER_{name_suffix}.md").write_text("\n".join(combo))

    # PO payments timeline
    po_doc = []
    po_doc.append(f"# PO Payments Timeline — {label_suffix}")
    po_doc.append("")
    po_doc.append(f"Window: {window_label}")
    po_doc.append("")
    po_doc.append("## Current PO Balances (as of last payment)")
    po_doc.append("")
    po_doc.append("```text")
    po_doc.extend(_ascii_table(po_balance_rows, po_balance_cols))
    po_doc.append("```")
    po_doc.append("")
    po_doc.append("## Chronological Payments")
    po_doc.append("")
    po_doc.append("```text")
    po_doc.extend(_ascii_table(po_timeline_rows, po_timeline_cols))
    po_doc.append("```")

    (args.output_dir / f"PO_PAYMENTS_CHRONO_{name_suffix}.md").write_text("\n".join(po_doc))

    print(args.output_dir / f"P2P_BUY_{name_suffix}.md")
    print(args.output_dir / f"EXCHANGER_BUY_{name_suffix}.md")
    print(args.output_dir / f"TRANSFER_LEDGER_{name_suffix}.md")
    print(args.output_dir / f"PO_PAYMENTS_CHRONO_{name_suffix}.md")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
