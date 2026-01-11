#!/usr/bin/env python3
"""Generate Markdown reports for transfer ledger (P2P, exchanger, combined)."""

from __future__ import annotations

import argparse
import os
from datetime import datetime, timedelta
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from core.integrations.binance_wallet_client import BinanceWalletClient
from core.transfer_ledger.exchanger_matching import AMOUNT_TOLERANCE, DATE_WINDOW_DAYS
from core.transfer_ledger.repository import (
    list_deposits,
    list_transfers,
    list_funding_balance_snapshots,
    list_pos_for_allocation,
    get_po_total_cny_from_lines,
)


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
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except Exception:
        return None


def _fmt_dt(value) -> str:
    if not value:
        return ""
    text = str(value)
    return text[:19].replace("T", " ")


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
        if address and (wd.get("address") or "") != address:
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


def _get_current_usdt_balance() -> float | None:
    try:
        client = BinanceWalletClient()
        return client.get_funding_balance("USDT")
    except Exception:
        return None


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate transfer ledger reports")
    parser.add_argument("--db", type=Path, default=DB_PATH, help="Path to SQLite DB")
    parser.add_argument("--days", type=int, default=120, help="Lookback days")
    parser.add_argument("--current-usdt", type=float, default=None, help="Override current USDT balance")
    parser.add_argument("--output-dir", type=Path, default=PROJECT_ROOT / "docs" / "transfer_ledger")
    args = parser.parse_args()

    _load_env_file(PROJECT_ROOT / ".env")

    end_dt = datetime.now()
    start_dt = end_dt - timedelta(days=args.days)
    start_iso = start_dt.isoformat()

    import sqlite3

    conn = sqlite3.connect(str(args.db))
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    # P2P orders (USDT/KZT)
    rows_p2p = cur.execute(
        """
        SELECT order_number, create_time, fiat_amount, crypto_amount, unit_price, counterparty
        FROM binance_c2c_orders
        WHERE trade_type='BUY' AND asset='USDT' AND fiat='KZT'
          AND order_status='COMPLETED'
          AND create_time >= ?
        ORDER BY create_time DESC
        """,
        (start_iso,),
    ).fetchall()

    # Exchanger orders (USDT->CNY)
    rows_ex = cur.execute(
        """
        SELECT exchanger_order_id, exchanger, order_id, status, message_date,
               amount_usdt, amount_cny, deposit_address
        FROM exchanger_orders
        WHERE message_date >= ?
          AND amount_usdt IS NOT NULL AND amount_cny IS NOT NULL
        ORDER BY message_date DESC
        """,
        (start_iso,),
    ).fetchall()

    rows_dep = list_deposits(db_path=args.db, start_time=start_iso, coin="USDT")
    rows_trans = list_transfers(db_path=args.db, start_time=start_iso, asset="USDT")
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
            events = cur.execute(
                """
                SELECT exchanger_order_id, status, message_date
                FROM exchanger_order_events
                WHERE message_date >= ?
                """,
                (start_iso,),
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
    withdrawals = cur.execute(
        """
        SELECT withdraw_id, amount, address, apply_time, exchanger_order_id
        FROM binance_withdrawals
        WHERE apply_time >= ?
        """,
        (start_iso,),
    ).fetchall()

    withdrawals_list = [dict(w) for w in withdrawals]
    wd_by_order = {w["exchanger_order_id"]: w for w in withdrawals_list if w["exchanger_order_id"]}
    unmatched_withdrawals = [w for w in withdrawals_list if not w.get("exchanger_order_id")]
    used_withdrawals: set[str] = set()

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
    usdt_events.sort(key=lambda x: _parse_dt(x[0]) or datetime.min, reverse=True)

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

    # P2P double entries
    p2p_entries = []
    for r in rows_p2p:
        order = r["order_number"]
        dt = r["create_time"]
        usdt = float(r["crypto_amount"] or 0)
        kzt = float(r["fiat_amount"] or 0)
        rate = float(r["unit_price"] or 0)
        cp = r["counterparty"] or ""
        bal = balance_after.get(f"p2p:{order}")
        p2p_entries.append([
            _fmt_dt(dt),
            str(order),
            "ASSET",
            "USDT",
            f"{usdt:.2f}",
            f"{usdt * rate:.2f}",
            f"{rate:.4f}",
            f"{bal:.2f}" if bal is not None else "",
            cp,
        ])
        p2p_entries.append([
            _fmt_dt(dt),
            str(order),
            "FIAT",
            "KZT",
            f"{-kzt:.2f}",
            f"{-kzt:.2f}",
            "1.0000",
            f"{bal:.2f}" if bal is not None else "",
            cp,
        ])

    po_info_by_order: dict[str, dict] = {}
    pos = list_pos_for_allocation(db_path=args.db)
    po_list: list[tuple[datetime, str, float]] = []
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
        if not total_cny or total_cny <= 0:
            continue
        po_list.append((po_date, po_id, total_cny))
    po_list.sort(key=lambda x: (x[0], x[1]))

    if po_list:
        po_state = {po_id: {"total_cny": total_cny, "paid_cny": 0.0} for _, po_id, total_cny in po_list}
        orders_for_alloc = []
        for r in rows_ex:
            amount_cny = float(r["amount_cny"] or 0)
            amount_usdt = float(r["amount_usdt"] or 0)
            if amount_cny <= 0 or amount_usdt <= 0:
                continue
            order_dt = _parse_dt(r["message_date"])
            if not order_dt:
                continue
            rate = amount_cny / amount_usdt
            orders_for_alloc.append((order_dt, r, rate))
        orders_for_alloc.sort(key=lambda x: x[0])

        po_idx = 0
        for order_dt, row, rate in orders_for_alloc:
            while po_idx + 1 < len(po_list) and order_dt >= po_list[po_idx + 1][0]:
                po_idx += 1

            remaining = float(row["amount_cny"] or 0)
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
                alloc = min(left, remaining)
                state["paid_cny"] += alloc
                remaining -= alloc
                last_po_id = po_id
                last_po_total = total_cny
                last_paid = state["paid_cny"]
                last_left = total_cny - state["paid_cny"]
                if remaining <= 0:
                    break
                i += 1

            if last_po_id:
                avg_kzt = _avg_recent_rate(p2p_rates, order_dt, window=5)
                po_total_usdt = last_po_total / rate if rate > 0 else None
                po_left_usdt = last_left / rate if last_left is not None and rate > 0 else None
                po_left_kzt = po_left_usdt * avg_kzt if po_left_usdt is not None and avg_kzt is not None else None
                po_info_by_order[row["exchanger_order_id"]] = {
                    "po_id": last_po_id,
                    "po_total_cny": last_po_total,
                    "po_total_usdt": po_total_usdt,
                    "po_paid_cny": last_paid,
                    "po_left_cny": last_left,
                    "po_left_usdt": po_left_usdt,
                    "po_left_kzt": po_left_kzt,
                }

    # Exchanger entries
    ex_entries = []
    for r in rows_ex:
        order = dict(r)
        order_key = order["exchanger_order_id"]
        amount_usdt = float(order["amount_usdt"] or 0)
        amount_cny = float(order["amount_cny"] or 0)
        if amount_usdt <= 0 or amount_cny <= 0:
            continue
        rate = amount_cny / amount_usdt
        match = wd_by_order.get(order_key)
        if not match:
            match = _match_withdrawal_for_order(order, unmatched_withdrawals, used_withdrawals)
            if match and match.get("withdraw_id"):
                used_withdrawals.add(match["withdraw_id"])
        ref_parts = []
        bal = None
        if match:
            wd_id = match.get("withdraw_id")
            if wd_id:
                ref_parts.append(f"wd={wd_id}")
                bal = balance_after.get(f"wd:{wd_id}")
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

    conn.close()

    # Tables
    p2p_cols = [
        ("Date", 19), ("Order", 12), ("Leg", 8), ("Curr", 5),
        ("Amount", 14), ("KZT_Value", 14), ("Rate", 10),
        ("USDT_Bal", 12), ("Counterparty", 60)
    ]
    ex_cols = [
        ("Date", 19), ("Order", 12), ("Exch", 12), ("Leg", 8), ("Curr", 5),
        ("Amount", 14), ("CNY_Value", 14), ("USDT/CNY", 10),
        ("USDT_Bal", 12), ("Duration_min", 12), ("Ref", 50),
        ("PO", 12), ("PO_Tot_CNY", 12), ("PO_Tot_USDT", 12),
        ("PO_Paid_CNY", 12), ("PO_Left_CNY", 12), ("PO_Left_USDT", 12),
        ("PO_Left_KZT", 12)
    ]

    # Write docs
    args.output_dir.mkdir(parents=True, exist_ok=True)

    # P2P report
    p2p_doc = []
    p2p_doc.append(f"# Binance P2P BUY (USDT/KZT) — Last {args.days} Days")
    p2p_doc.append("")
    p2p_doc.append(f"Window: {start_dt.date().isoformat()} → {end_dt.date().isoformat()}")
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

    (args.output_dir / "P2P_BUY_LAST_120_DAYS.md").write_text("\n".join(p2p_doc))

    # Exchanger report
    ex_doc = []
    ex_doc.append(f"# Exchanger USDT→CNY Buys — Last {args.days} Days")
    ex_doc.append("")
    ex_doc.append(f"Window: {start_dt.date().isoformat()} → {end_dt.date().isoformat()}")
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

    (args.output_dir / "EXCHANGER_BUY_LAST_120_DAYS.md").write_text("\n".join(ex_doc))

    # Combined report
    combo = []
    combo.append(f"# Transfer Ledger — Last {args.days} Days (Combined)")
    combo.append("")
    combo.append(f"Window: {start_dt.date().isoformat()} → {end_dt.date().isoformat()}")
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

    (args.output_dir / "TRANSFER_LEDGER_LAST_120_DAYS.md").write_text("\n".join(combo))

    print(args.output_dir / "P2P_BUY_LAST_120_DAYS.md")
    print(args.output_dir / "EXCHANGER_BUY_LAST_120_DAYS.md")
    print(args.output_dir / "TRANSFER_LEDGER_LAST_120_DAYS.md")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
