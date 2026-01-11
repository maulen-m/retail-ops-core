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
                try:
                    dt = datetime.fromisoformat(str(e["message_date"]).replace("Z", "+00:00"))
                except Exception:
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

    wd_by_order = {w["exchanger_order_id"]: w for w in withdrawals if w["exchanger_order_id"]}

    # Build USDT event timeline for balance
    usdt_events = []
    for r in rows_p2p:
        dt = r["create_time"]
        usdt_events.append((dt, f"p2p:{r['order_number']}", float(r["crypto_amount"] or 0)))
    for w in withdrawals:
        dt = w["apply_time"]
        usdt_events.append((dt, f"wd:{w['withdraw_id']}", -float(w["amount"] or 0)))

    # Sort descending
    usdt_events.sort(key=lambda x: x[0], reverse=True)

    current_usdt = args.current_usdt
    api_usdt = None
    if current_usdt is None:
        api_usdt = _get_current_usdt_balance()
        current_usdt = api_usdt

    balance_after: dict[str, float] = {}
    if current_usdt is not None:
        bal = float(current_usdt)
        for dt, key, delta in usdt_events:
            balance_after[key] = bal
            bal -= delta

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
            dt[:19].replace("T", " "),
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
            dt[:19].replace("T", " "),
            str(order),
            "FIAT",
            "KZT",
            f"{-kzt:.2f}",
            f"{-kzt:.2f}",
            "1.0000",
            f"{bal:.2f}" if bal is not None else "",
            cp,
        ])

    # Exchanger entries
    ex_entries = []
    for r in rows_ex:
        order_key = r["exchanger_order_id"]
        amount_usdt = float(r["amount_usdt"] or 0)
        amount_cny = float(r["amount_cny"] or 0)
        if amount_usdt <= 0 or amount_cny <= 0:
            continue
        rate = amount_cny / amount_usdt
        match = wd_by_order.get(order_key)
        ref = ""
        bal = None
        if match:
            ref = f"wd={match['withdraw_id']} addr={match['address']}"
            bal = balance_after.get(f"wd:{match['withdraw_id']}")
        else:
            ref = f"addr={r['deposit_address'] or ''}"

        # Duration
        duration = ""
        if order_key in events_by_order:
            created_list = events_by_order[order_key].get("NEW") or []
            completed_list = events_by_order[order_key].get("COMPLETED") or []
            if created_list and completed_list:
                dur_min = int((max(completed_list) - min(created_list)).total_seconds() // 60)
                duration = str(dur_min)

        dt = r["message_date"]
        ex_entries.append([
            dt[:19].replace("T", " "),
            str(r["order_id"] or order_key),
            r["exchanger"],
            "USDT_OUT",
            "USDT",
            f"{-amount_usdt:.2f}",
            f"{-amount_cny:.2f}",
            f"{rate:.4f}",
            f"{bal:.2f}" if bal is not None else "",
            duration,
            ref,
        ])
        ex_entries.append([
            dt[:19].replace("T", " "),
            str(r["order_id"] or order_key),
            r["exchanger"],
            "CNY_IN",
            "CNY",
            f"{amount_cny:.2f}",
            f"{amount_cny:.2f}",
            f"{rate:.4f}",
            f"{bal:.2f}" if bal is not None else "",
            duration,
            ref,
        ])

    conn.close()

    # Tables
    p2p_cols = [
        ("Date", 19), ("Order", 12), ("Leg", 8), ("Curr", 5),
        ("Amount", 14), ("KZT_Value", 14), ("Rate", 10),
        ("USDT_Bal", 12), ("Counterparty", 40)
    ]
    ex_cols = [
        ("Date", 19), ("Order", 12), ("Exch", 12), ("Leg", 8), ("Curr", 5),
        ("Amount", 14), ("CNY_Value", 14), ("USDT/CNY", 10),
        ("USDT_Bal", 12), ("Duration_min", 12), ("Ref", 28)
    ]

    # Write docs
    args.output_dir.mkdir(parents=True, exist_ok=True)

    # P2P report
    p2p_doc = []
    p2p_doc.append("# Binance P2P BUY (USDT/KZT) — Last 120 Days")
    p2p_doc.append("")
    p2p_doc.append(f"Window: {start_dt.date().isoformat()} → {end_dt.date().isoformat()}")
    if current_usdt is not None:
        p2p_doc.append(f"Current funding USDT (used for balance): {current_usdt}")
    if api_usdt is not None:
        p2p_doc.append(f"Funding USDT (API): {api_usdt}")
    p2p_doc.append("")
    p2p_doc.append("## Double-book Entries (ASCII)")
    p2p_doc.append("")
    p2p_doc.append("```text")
    p2p_doc.extend(_ascii_table(p2p_entries, p2p_cols))
    p2p_doc.append("```")

    (args.output_dir / "P2P_BUY_LAST_120_DAYS.md").write_text("\n".join(p2p_doc))

    # Exchanger report
    ex_doc = []
    ex_doc.append("# Exchanger USDT→CNY Buys — Last 120 Days")
    ex_doc.append("")
    ex_doc.append(f"Window: {start_dt.date().isoformat()} → {end_dt.date().isoformat()}")
    if current_usdt is not None:
        ex_doc.append(f"Current funding USDT (used for balance): {current_usdt}")
    if api_usdt is not None:
        ex_doc.append(f"Funding USDT (API): {api_usdt}")
    ex_doc.append("")
    ex_doc.append("## Double-book Entries (ASCII)")
    ex_doc.append("")
    ex_doc.append("```text")
    ex_doc.extend(_ascii_table(ex_entries, ex_cols))
    ex_doc.append("```")

    (args.output_dir / "EXCHANGER_BUY_LAST_120_DAYS.md").write_text("\n".join(ex_doc))

    # Combined report
    combo = []
    combo.append("# Transfer Ledger — Last 120 Days (Combined)")
    combo.append("")
    combo.append(f"Window: {start_dt.date().isoformat()} → {end_dt.date().isoformat()}")
    if current_usdt is not None:
        combo.append(f"Current funding USDT (used for balance): {current_usdt}")
    if api_usdt is not None:
        combo.append(f"Funding USDT (API): {api_usdt}")
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
