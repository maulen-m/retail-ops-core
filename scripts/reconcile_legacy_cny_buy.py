#!/usr/bin/env python3
"""Reconcile legacy CNY buy rows from PO_storing_Vibecode_1.xlsx."""

from __future__ import annotations

import argparse
from datetime import datetime, time, timezone
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from core.db import get_db
from core.transfer_ledger.exchanger_matching import AMOUNT_TOLERANCE, DATE_WINDOW_DAYS, address_match
from core.transfer_ledger.exchanger_email_import import STATUS_MAP
from core.transfer_ledger.repository import (
    ensure_schema,
    upsert_exchanger_order,
    upsert_po_exchanger_allocation,
    update_withdrawal_label,
    update_withdrawal_entry_notes,
)


def _to_float(value):
    if value is None or value == "" or (isinstance(value, float) and value != value):
        return None
    try:
        return float(value)
    except Exception:
        try:
            return float(str(value).replace(",", ""))
        except Exception:
            return None


def _to_date(value) -> datetime | None:
    if value is None or value == "" or (isinstance(value, float) and value != value):
        return None
    if isinstance(value, datetime):
        return value
    try:
        return datetime.fromisoformat(str(value))
    except Exception:
        return None


def _combine_date_time(d, t) -> datetime | None:
    base = _to_date(d)
    if not base:
        return None
    if isinstance(t, datetime):
        return datetime.combine(base.date(), t.time())
    if isinstance(t, time):
        return datetime.combine(base.date(), t)
    try:
        parsed = datetime.fromisoformat(str(t))
        return datetime.combine(base.date(), parsed.time())
    except Exception:
        return base


def _naive(dt: datetime | None) -> datetime | None:
    if not dt:
        return None
    if dt.tzinfo is not None:
        return dt.astimezone(timezone.utc).replace(tzinfo=None)
    return dt


def _find_header_row(df, header_name: str, max_rows: int = 50) -> int | None:
    for i in range(min(max_rows, len(df))):
        row = df.iloc[i].astype(str).tolist()
        if any(header_name in cell for cell in row):
            return i
    return None


def _match_exchanger_order(cur, order_id: str | None, address: str | None, amount_usdt: float | None, dt: datetime | None):
    dt = _naive(dt)
    if order_id:
        row = cur.execute(
            "SELECT exchanger_order_id FROM exchanger_orders WHERE order_id = ? LIMIT 1",
            (str(order_id),),
        ).fetchone()
        if row:
            return row[0]

    candidates = cur.execute(
        """
        SELECT exchanger_order_id, amount_usdt, message_date, deposit_address
        FROM exchanger_orders
        WHERE amount_usdt IS NOT NULL
        """
    ).fetchall()

    best = None
    best_delta = None
    for ex_id, amt, msg_date, dep_addr in candidates:
        if address and dep_addr and not address_match(address, dep_addr):
            continue
        if amount_usdt is not None and amt is not None:
            if abs(float(amt) - float(amount_usdt)) > AMOUNT_TOLERANCE:
                continue
        if dt and msg_date:
            try:
                msg_dt = _naive(datetime.fromisoformat(str(msg_date).replace("Z", "+00:00")))
            except Exception:
                msg_dt = None
            if msg_dt:
                delta = abs((msg_dt - dt).total_seconds())
                if delta > DATE_WINDOW_DAYS * 86400:
                    continue
            else:
                delta = 0
        else:
            delta = 0
        if best_delta is None or delta < best_delta:
            best = ex_id
            best_delta = delta
    return best


def _match_withdrawal(cur, address: str | None, amount_usdt: float | None, dt: datetime | None):
    dt = _naive(dt)
    rows = cur.execute(
        """
        SELECT withdraw_id, amount, address, apply_time
        FROM binance_withdrawals
        WHERE amount IS NOT NULL
        """
    ).fetchall()
    best = None
    best_delta = None
    for wd_id, amt, addr, apply_time in rows:
        if address and addr and not address_match(address, addr):
            continue
        if amount_usdt is not None and amt is not None:
            if abs(float(amt) - float(amount_usdt)) > AMOUNT_TOLERANCE:
                continue
        if dt and apply_time:
            try:
                wd_dt = _naive(datetime.fromisoformat(str(apply_time).replace("Z", "+00:00")))
            except Exception:
                wd_dt = None
            if wd_dt:
                delta = abs((wd_dt - dt).total_seconds())
                if delta > DATE_WINDOW_DAYS * 86400:
                    continue
            else:
                delta = 0
        else:
            delta = 0
        if best_delta is None or delta < best_delta:
            best = wd_id
            best_delta = delta
    return best


def _status_from_row(row) -> str | None:
    status = row.get("Order_status") or row.get("Status") or row.get("status")
    if status and isinstance(status, str):
        upper = status.upper()
        for key, values in STATUS_MAP.items():
            if any(v.replace(" ", "").upper() in upper.replace(" ", "") for v in values):
                return key
        return upper
    if row.get("Receive_time") or row.get("CNY_received"):
        return "COMPLETED"
    return None


def main() -> int:
    parser = argparse.ArgumentParser(description="Reconcile legacy CNY buy rows from PO_storing_Vibecode_1.xlsx")
    parser.add_argument("--xlsx", type=Path, required=True, help="Path to PO_storing_Vibecode_1.xlsx")
    parser.add_argument("--dry-run", action="store_true", help="Parse only; do not write to DB")
    parser.add_argument("--limit", type=int, default=None, help="Limit rows")
    args = parser.parse_args()

    if not args.xlsx.exists():
        print(f"File not found: {args.xlsx}")
        return 1

    import pandas as pd

    raw = pd.read_excel(args.xlsx, sheet_name="CNY_buy", header=None)
    header_row = _find_header_row(raw, "Internal_order_code")
    if header_row is None:
        print("Header row not found in CNY_buy")
        return 1
    df = pd.read_excel(args.xlsx, sheet_name="CNY_buy", header=header_row)
    if args.limit:
        df = df.head(args.limit)

    ensure_schema()
    inserted_orders = 0
    mapped = 0
    created = 0

    with get_db() as conn:
        cur = conn.cursor()
        for _, row in df.iterrows():
            po_id = row.get("Internal_order_code")
            if po_id is None or (isinstance(po_id, float) and po_id != po_id):
                continue
            po_id = str(po_id).strip()

            transfer_type = str(row.get("Transfer_type") or "")
            if "USDT/KZT" in transfer_type:
                continue

            amount_usdt = _to_float(row.get("USDT_send"))
            amount_cny = _to_float(row.get("CNY_received")) or _to_float(row.get("CNY_receive_claim"))
            if amount_usdt is None or amount_cny is None:
                continue

            address = row.get("USDT_send_Address")
            address = str(address).strip() if address and not (isinstance(address, float) and address != address) else None

            order_id = row.get("Order_ID")
            order_id = str(order_id).strip() if order_id and not (isinstance(order_id, float) and order_id != order_id) else None

            dt = _combine_date_time(row.get("Send_Date"), row.get("Send_time"))

            exchanger = row.get("Exchanger")
            exchanger = str(exchanger).strip() if exchanger and not (isinstance(exchanger, float) and exchanger != exchanger) else None

            ex_order_id = _match_exchanger_order(cur, order_id, address, amount_usdt, dt)

            if not ex_order_id:
                # Create synthetic exchanger order if missing
                synthetic_key = f"LEGACY:{order_id or po_id}:{int(dt.timestamp()) if dt else 'NA'}"
                ex_order_id = f"LEGACY:{synthetic_key}"
                status = _status_from_row(row)
                direction = "Tether TRC20 -> WeChat"
                order = {
                    "exchanger_order_id": ex_order_id,
                    "exchanger": exchanger or "LEGACY",
                    "order_id": order_id or synthetic_key,
                    "status": status,
                    "direction": direction,
                    "amount_usdt": amount_usdt,
                    "amount_cny": amount_cny,
                    "rate_usdt_cny": amount_cny / amount_usdt if amount_usdt else None,
                    "deposit_address": address,
                    "receiver_account": row.get("Receiver_address"),
                    "message_id": "",
                    "message_date": dt.isoformat() if dt else None,
                    "subject": "Legacy XLSX",
                    "raw_json": "{}",
                    "source": "LEGACY_XLSX",
                }
                if not args.dry_run:
                    if upsert_exchanger_order(order):
                        inserted_orders += 1
                created += 1

            if not args.dry_run:
                upsert_po_exchanger_allocation(
                    {
                        "po_id": po_id,
                        "exchanger_order_id": ex_order_id,
                        "amount_usdt": amount_usdt,
                        "amount_cny": amount_cny,
                        "source": "LEGACY_XLSX",
                    }
                )
            mapped += 1

            # Label withdrawal metadata if found
            wd_id = _match_withdrawal(cur, address, amount_usdt, dt)
            if wd_id and not args.dry_run:
                update_withdrawal_label(wd_id, counterparty_label=exchanger or "", exchanger_order_id=ex_order_id)
                update_withdrawal_entry_notes(wd_id, counterparty_label=exchanger or "", exchanger_order_id=ex_order_id)

    print(f"Legacy rows mapped: {mapped}")
    print(f"Legacy orders created: {created}")
    if not args.dry_run:
        print(f"New exchanger orders inserted: {inserted_orders}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
