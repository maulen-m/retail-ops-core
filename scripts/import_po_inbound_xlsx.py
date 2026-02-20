#!/usr/bin/env python3
"""Import PO inbound Excel into po_header + po_line."""

from __future__ import annotations

import argparse
from datetime import datetime
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from core.db import get_db
from core.transfer_ledger.repository import ensure_schema, upsert_po_header_min


def _to_date(value) -> str | None:
    if value is None or value == "" or (isinstance(value, float) and value != value):
        return None
    if isinstance(value, datetime):
        return value.date().isoformat()
    try:
        return datetime.fromisoformat(str(value)).date().isoformat()
    except Exception:
        return None


def _to_float(value) -> float | None:
    if value is None or value == "" or (isinstance(value, float) and value != value):
        return None
    try:
        return float(value)
    except Exception:
        try:
            return float(str(value).replace(",", ""))
        except Exception:
            return None


def _derive_po_id(values: list[str]) -> str | None:
    base = None
    for v in values:
        if not v:
            continue
        v = str(v).strip()
        if v.upper().startswith("PO"):
            digits = ""
            for ch in v[2:]:
                if ch.isdigit():
                    digits += ch
                else:
                    break
            if digits:
                po_id = f"PO-{int(digits)}"
                if base and base != po_id:
                    return None
                base = po_id
    return base


def main() -> int:
    parser = argparse.ArgumentParser(description="Import PO inbound Excel into po_header + po_line")
    parser.add_argument("--xlsx", type=Path, required=True, help="Path to PO inbound xlsx")
    parser.add_argument("--po-id", default=None, help="Override PO id (e.g. PO-4)")
    parser.add_argument("--sheet", default=None, help="Sheet name (default first)")
    parser.add_argument("--dry-run", action="store_true", help="Parse only; do not write to DB")
    args = parser.parse_args()

    if not args.xlsx.exists():
        print(f"File not found: {args.xlsx}")
        return 1

    import pandas as pd

    xls = pd.ExcelFile(args.xlsx)
    sheet = args.sheet or xls.sheet_names[0]
    df = pd.read_excel(args.xlsx, sheet_name=sheet)

    if "Internal_PO" not in df.columns:
        print("Missing Internal_PO column in inbound sheet")
        return 1

    po_id = args.po_id
    if not po_id:
        po_id = _derive_po_id([v for v in df["Internal_PO"].dropna().unique().tolist()])
    if not po_id:
        print("Unable to derive PO id; pass --po-id explicitly")
        return 1

    # Compute header aggregates
    message_dates = [_to_date(v) for v in df.get("Message_date", [])]
    message_dates = [d for d in message_dates if d]
    message_date = min(message_dates) if message_dates else None

    total_units = 0
    total_cost_cny = 0.0
    total_weight = 0.0

    lines = []
    for _, row in df.iterrows():
        sku_id = str(row.get("SKU_ID") or "").strip()
        sku_key = str(row.get("SKU_key") or "").strip()
        my_size = str(row.get("MY_SIZE") or "").strip()
        qty = row.get("Approved_by_supplier_qty")
        if qty is None or (isinstance(qty, float) and qty != qty):
            qty = row.get("Final_qty")
        qty = _to_float(qty) or 0
        if qty <= 0:
            continue

        unit_cost = _to_float(row.get("BaseCost_CNY"))
        line_cost = _to_float(row.get("LineBaseCost_CNY"))
        if unit_cost is None and line_cost is not None:
            unit_cost = line_cost / qty if qty else None
        if unit_cost is None:
            continue

        unit_weight = _to_float(row.get("Weight_kg"))
        line_weight = _to_float(row.get("LineWeight_kg"))
        if unit_weight is None and line_weight is not None:
            unit_weight = line_weight / qty if qty else None

        total_units += int(qty)
        total_cost_cny += float(unit_cost) * qty
        if unit_weight:
            total_weight += float(unit_weight) * qty

        lines.append(
            {
                "sku_id": sku_id,
                "sku_key": sku_key or sku_id,
                "my_size": my_size or "NA",
                "order_qty": int(qty),
                "unit_cost_cny": float(unit_cost),
                "unit_weight_kg": float(unit_weight) if unit_weight else None,
            }
        )

    if not lines:
        print("No valid line items found in inbound sheet")
        return 1

    if args.dry_run:
        print(f"PO id: {po_id}")
        print(f"Lines parsed: {len(lines)}")
        return 0

    ensure_schema()
    upsert_po_header_min(po_id=po_id, message_date=message_date, total_cost_cny=total_cost_cny)

    with get_db() as conn:
        row = conn.execute("SELECT 1 FROM po_header WHERE po_id = ? LIMIT 1", (po_id,)).fetchone()
        if row:
            conn.execute(
                """
                UPDATE po_header
                SET units_total = ?, weight_nom_kg = ?, updated_at = datetime('now')
                WHERE po_id = ?
                """,
                (total_units, total_weight if total_weight else None, po_id),
            )

        for line in lines:
            existing = conn.execute(
                """
                SELECT po_line_id FROM po_line
                WHERE po_id = ? AND sku_id = ?
                LIMIT 1
                """,
                (po_id, line["sku_id"]),
            ).fetchone()
            if existing:
                conn.execute(
                    """
                    UPDATE po_line
                    SET sku_key = ?, my_size = ?, order_qty = ?, unit_cost_cny = ?,
                        unit_weight_kg = ?, updated_at = datetime('now')
                    WHERE po_line_id = ?
                    """,
                    (
                        line["sku_key"],
                        line["my_size"],
                        line["order_qty"],
                        line["unit_cost_cny"],
                        line["unit_weight_kg"],
                        existing[0],
                    ),
                )
            else:
                conn.execute(
                    """
                    INSERT INTO po_line (
                        po_id, sku_key, sku_id, my_size, order_qty, unit_cost_cny, unit_weight_kg
                    ) VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        po_id,
                        line["sku_key"],
                        line["sku_id"],
                        line["my_size"],
                        line["order_qty"],
                        line["unit_cost_cny"],
                        line["unit_weight_kg"],
                    ),
                )

    print(f"Imported PO {po_id}: {len(lines)} lines, total_cny={total_cost_cny:.2f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
