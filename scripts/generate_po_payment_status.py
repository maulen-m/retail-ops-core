#!/usr/bin/env python3
"""Generate PO payment status report (total/paid/left)."""

from __future__ import annotations

import argparse
from datetime import datetime
from pathlib import Path
import sys

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

    # Gather PO ids
    po_ids = set()
    for row in cur.execute("SELECT po_id FROM po_header WHERE po_id IS NOT NULL").fetchall():
        po_ids.add(row["po_id"])
    for row in cur.execute("SELECT DISTINCT po_id FROM po_line WHERE po_id IS NOT NULL").fetchall():
        po_ids.add(row["po_id"])
    for row in cur.execute("SELECT po_id FROM po_funding_plan WHERE po_id IS NOT NULL").fetchall():
        po_ids.add(row["po_id"])

    if not po_ids:
        print("No PO data found.")
        return 1

    # Latest FX
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

    # Paid amounts from exchanger allocations
    paid_map = {
        r["po_id"]: {
            "paid_cny": float(r["paid_cny"]) if r["paid_cny"] is not None else 0.0,
            "paid_usdt": float(r["paid_usdt"]) if r["paid_usdt"] is not None else 0.0,
        }
        for r in cur.execute(
            """
            SELECT po_id,
                   SUM(amount_cny) AS paid_cny,
                   SUM(amount_usdt) AS paid_usdt
            FROM po_exchanger_allocations
            GROUP BY po_id
            """
        ).fetchall()
    }

    # Last payment date
    last_map = {
        r["po_id"]: r["last_date"]
        for r in cur.execute(
            """
            SELECT pea.po_id, MAX(eo.message_date) AS last_date
            FROM po_exchanger_allocations pea
            JOIN exchanger_orders eo ON eo.exchanger_order_id = pea.exchanger_order_id
            GROUP BY pea.po_id
            """
        ).fetchall()
    }

    rows = []
    for po_id in sorted(po_ids):
        header = cur.execute(
            "SELECT total_cost_cny, message_date FROM po_header WHERE po_id = ?",
            (po_id,),
        ).fetchone()
        total_cny = header["total_cost_cny"] if header else None
        message_date = header["message_date"] if header else None

        if not total_cny or float(total_cny) <= 0:
            row = cur.execute(
                """
                SELECT COALESCE(SUM(order_qty * unit_cost_cny), 0) AS total
                FROM po_line WHERE po_id = ?
                """,
                (po_id,),
            ).fetchone()
            total_cny = float(row["total"]) if row and row["total"] else None

        if not total_cny or float(total_cny) <= 0:
            row = cur.execute(
                "SELECT total_cny FROM po_funding_plan WHERE po_id = ?",
                (po_id,),
            ).fetchone()
            total_cny = float(row["total_cny"]) if row and row["total_cny"] else None

        row = cur.execute(
            "SELECT total_usdt FROM po_funding_plan WHERE po_id = ?",
            (po_id,),
        ).fetchone()
        total_usdt = float(row["total_usdt"]) if row and row["total_usdt"] else None
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
                message_date or "",
                _fmt(total_cny),
                _fmt(paid_cny),
                _fmt(left_cny),
                _fmt(total_usdt),
                _fmt(paid_usdt),
                _fmt(left_usdt),
                _fmt(left_kzt),
                last_map.get(po_id, "") or "",
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
