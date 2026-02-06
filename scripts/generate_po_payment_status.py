#!/usr/bin/env python3
"""Generate PO payment status report (total/paid/left)."""

from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
from pathlib import Path
import sys
from collections import defaultdict

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from core.transfer_ledger.repository import ensure_schema


def _fmt(value, digits: int = 2) -> str:
    if value is None:
        return ""
    try:
        return f"{float(value):.{digits}f}"
    except Exception:
        return ""


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


LOCAL_TZ = timezone(timedelta(hours=5))
UTC = timezone.utc


def _fmt_dt(value) -> str:
    if not value:
        return ""
    try:
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except Exception:
        return str(value)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    else:
        dt = dt.astimezone(UTC)
    local = dt.astimezone(LOCAL_TZ)
    return local.strftime("%Y-%m-%d %H:%M:%S")


def _parse_dt(value):
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except Exception:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC)


def _table_exists(cur, table_name: str) -> bool:
    row = cur.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name = ? LIMIT 1",
        (table_name,),
    ).fetchone()
    return row is not None


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate PO payment status report")
    parser.add_argument("--db", type=Path, default=PROJECT_ROOT / "db" / "app.db")
    parser.add_argument("--output", type=Path, default=PROJECT_ROOT / "docs" / "transfer_ledger" / "PO_PAYMENT_STATUS.md")
    args = parser.parse_args()

    import sqlite3

    ensure_schema(args.db)
    conn = sqlite3.connect(str(args.db))
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    has_po_header = _table_exists(cur, "po_header")
    has_po_line = _table_exists(cur, "po_line")
    has_po_plan = _table_exists(cur, "po_funding_plan")
    has_po_ex_alloc = _table_exists(cur, "po_exchanger_allocations")
    has_exchanger_orders = _table_exists(cur, "exchanger_orders")
    has_withdrawals = _table_exists(cur, "binance_withdrawals")

    # Gather PO ids
    po_ids = set()
    if has_po_header:
        for row in cur.execute("SELECT po_id FROM po_header WHERE po_id IS NOT NULL").fetchall():
            po_ids.add(row["po_id"])
    if has_po_line:
        for row in cur.execute("SELECT DISTINCT po_id FROM po_line WHERE po_id IS NOT NULL").fetchall():
            po_ids.add(row["po_id"])
    if has_po_plan:
        for row in cur.execute("SELECT po_id FROM po_funding_plan WHERE po_id IS NOT NULL").fetchall():
            po_ids.add(row["po_id"])

    if not po_ids:
        print("No PO data found.")
        return 1

    # Latest FX
    usdt_kzt = None
    usdt_cny = None
    if _table_exists(cur, "dim_fx_rates"):
        fx = cur.execute(
            """
            SELECT usdt_kzt, usdt_cny
            FROM dim_fx_rates
            ORDER BY effective_date DESC
            LIMIT 1
            """
        ).fetchone()
        usdt_kzt = float(fx["usdt_kzt"]) if fx and fx["usdt_kzt"] is not None else None
        usdt_cny = float(fx["usdt_cny"]) if fx and fx["usdt_cny"] is not None else None

    po_meta: dict[str, dict] = {}
    for po_id in sorted(po_ids):
        total_cny = None
        message_date = None
        total_usdt = None

        if has_po_header:
            header = cur.execute(
                "SELECT total_cost_cny, message_date FROM po_header WHERE po_id = ?",
                (po_id,),
            ).fetchone()
            if header:
                total_cny = header["total_cost_cny"]
                message_date = header["message_date"]

        if (not total_cny or float(total_cny) <= 0) and has_po_line:
            row = cur.execute(
                """
                SELECT COALESCE(SUM(order_qty * unit_cost_cny), 0) AS total
                FROM po_line WHERE po_id = ?
                """,
                (po_id,),
            ).fetchone()
            total_cny = float(row["total"]) if row and row["total"] else None

        if has_po_plan:
            plan_row = cur.execute(
                "SELECT message_date, total_cny, total_usdt FROM po_funding_plan WHERE po_id = ?",
                (po_id,),
            ).fetchone()
            if plan_row:
                if (not total_cny or float(total_cny) <= 0) and plan_row["total_cny"]:
                    total_cny = float(plan_row["total_cny"])
                if not message_date and plan_row["message_date"]:
                    message_date = plan_row["message_date"]
                if plan_row["total_usdt"] is not None:
                    total_usdt = float(plan_row["total_usdt"])

        po_meta[po_id] = {
            "total_cny": float(total_cny) if total_cny is not None else None,
            "message_date": message_date,
            "total_usdt": total_usdt,
        }

    po_plan = []
    for po_id, meta in po_meta.items():
        po_dt = _parse_dt(meta.get("message_date"))
        total_cny = meta.get("total_cny")
        if po_dt and total_cny and total_cny > 0:
            po_plan.append((po_dt, po_id, total_cny))
    po_plan.sort(key=lambda x: (x[0], x[1]))

    paid_map: dict[str, dict] = {po_id: {"paid_cny": 0.0, "paid_usdt": 0.0} for po_id in po_ids}
    last_map_dt: dict[str, datetime] = {}

    alloc_by_order: dict[str, str] = {}
    if has_po_ex_alloc:
        for row in cur.execute(
            """
            SELECT exchanger_order_id, po_id
            FROM po_exchanger_allocations
            WHERE exchanger_order_id IS NOT NULL AND po_id IS NOT NULL
            """
        ).fetchall():
            alloc_by_order[row["exchanger_order_id"]] = row["po_id"]

    fee_by_order: dict[str, float] = defaultdict(float)
    if has_withdrawals:
        for row in cur.execute(
            """
            SELECT exchanger_order_id, transaction_fee
            FROM binance_withdrawals
            WHERE exchanger_order_id IS NOT NULL
            """
        ).fetchall():
            try:
                fee_by_order[row["exchanger_order_id"]] += float(row["transaction_fee"] or 0.0)
            except Exception:
                continue

    if has_exchanger_orders and po_plan:
        order_rows = cur.execute(
            """
            SELECT exchanger_order_id, status, message_date, amount_usdt, amount_cny
            FROM exchanger_orders
            WHERE amount_usdt IS NOT NULL AND amount_cny IS NOT NULL
            ORDER BY message_date ASC
            """
        ).fetchall()

        po_idx = 0
        for row in order_rows:
            status = (row["status"] or "").upper()
            if status == "CANCELLED":
                continue
            order_dt = _parse_dt(row["message_date"])
            if not order_dt:
                continue
            amount_cny = float(row["amount_cny"] or 0.0)
            amount_usdt = float(row["amount_usdt"] or 0.0)
            amount_usdt += float(fee_by_order.get(row["exchanger_order_id"], 0.0))
            if amount_cny <= 0 or amount_usdt <= 0:
                continue

            ex_id = row["exchanger_order_id"]
            explicit_po = alloc_by_order.get(ex_id)
            if explicit_po and explicit_po in paid_map:
                paid_map[explicit_po]["paid_cny"] += amount_cny
                paid_map[explicit_po]["paid_usdt"] += amount_usdt
                last_map_dt[explicit_po] = max(last_map_dt.get(explicit_po, order_dt), order_dt)
                continue

            while po_idx + 1 < len(po_plan) and order_dt >= po_plan[po_idx + 1][0]:
                po_idx += 1

            remaining_cny = amount_cny
            i = po_idx
            while remaining_cny > 0 and i < len(po_plan):
                _, po_id, total_cny = po_plan[i]
                left_cny = total_cny - paid_map[po_id]["paid_cny"]
                if left_cny <= 0:
                    i += 1
                    continue
                alloc_cny = min(left_cny, remaining_cny)
                ratio = (alloc_cny / amount_cny) if amount_cny else 0.0
                paid_map[po_id]["paid_cny"] += alloc_cny
                paid_map[po_id]["paid_usdt"] += amount_usdt * ratio
                remaining_cny -= alloc_cny
                last_map_dt[po_id] = max(last_map_dt.get(po_id, order_dt), order_dt)
                if remaining_cny <= 0:
                    break
                i += 1
    elif has_po_ex_alloc:
        # Fallback path when exchanger timeline is unavailable.
        for r in cur.execute(
            """
            SELECT po_id,
                   SUM(amount_cny) AS paid_cny,
                   SUM(amount_usdt) AS paid_usdt
            FROM po_exchanger_allocations
            GROUP BY po_id
            """
        ).fetchall():
            paid_map[r["po_id"]] = {
                "paid_cny": float(r["paid_cny"]) if r["paid_cny"] is not None else 0.0,
                "paid_usdt": float(r["paid_usdt"]) if r["paid_usdt"] is not None else 0.0,
            }

    last_map = {po_id: dt.isoformat() for po_id, dt in last_map_dt.items()}

    rows = []
    for po_id in sorted(po_ids):
        meta = po_meta.get(po_id, {})
        total_cny = meta.get("total_cny")
        message_date = meta.get("message_date")
        total_usdt = meta.get("total_usdt")
        if total_usdt is None and total_cny and usdt_cny:
            total_usdt = float(total_cny) / usdt_cny if usdt_cny else None

        paid = paid_map.get(po_id, {})
        paid_cny = paid.get("paid_cny", 0.0)
        paid_usdt = paid.get("paid_usdt", 0.0)

        left_cny = (float(total_cny) - paid_cny) if total_cny is not None else None
        left_usdt = (float(total_usdt) - paid_usdt) if total_usdt is not None else None
        left_kzt = (left_usdt * usdt_kzt) if left_usdt is not None and usdt_kzt is not None else None

        rows.append(
            [
                po_id,
                _fmt_dt(message_date),
                _fmt(total_cny),
                _fmt(paid_cny),
                _fmt(left_cny),
                _fmt(total_usdt),
                _fmt(paid_usdt),
                _fmt(left_usdt),
                _fmt(left_kzt),
                _fmt_dt(last_map.get(po_id, "")),
            ]
        )

    conn.close()

    cols = [
        ("PO", 16),
        ("Message_Date", 12),
        ("Total_CNY", 12),
        ("Paid_CNY", 12),
        ("Left_CNY", 12),
        ("Total_USDT", 12),
        ("Paid_USDT", 12),
        ("Left_USDT", 12),
        ("Left_KZT", 12),
        ("Last_Payment", 19),
    ]

    doc = []
    doc.append("# PO Payment Status")
    doc.append("")
    doc.append(f"Generated: {datetime.now().isoformat(timespec='seconds')}")
    doc.append("")
    doc.append("```text")
    doc.extend(_ascii_table(rows, cols))
    doc.append("```")

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text("\n".join(doc))
    print(args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
