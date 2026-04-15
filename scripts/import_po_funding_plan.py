#!/usr/bin/env python3
"""Import PO funding plan totals from Excel into SQLite."""

from __future__ import annotations

import argparse
from datetime import datetime
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from core.transfer_ledger.repository import upsert_po_funding_plan, upsert_po_header_min


def _find_header_row(df, header_name: str, max_rows: int = 50) -> int | None:
    for i in range(min(max_rows, len(df))):
        row = df.iloc[i].astype(str).tolist()
        if any(header_name in cell for cell in row):
            return i
    return None


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


def _load_sheet(path: Path, sheet_name: str, header_key: str):
    import pandas as pd

    raw = pd.read_excel(path, sheet_name=sheet_name, header=None)
    header_row = _find_header_row(raw, header_key)
    if header_row is None:
        return None
    return pd.read_excel(path, sheet_name=sheet_name, header=header_row)


def main() -> int:
    parser = argparse.ArgumentParser(description="Import PO funding plan totals from Excel")
    parser.add_argument("--xlsx", type=Path, required=True, help="Path to PO funding workbook (.xlsx)")
    parser.add_argument("--dry-run", action="store_true", help="Parse only; do not write to DB")
    parser.add_argument("--source", default=None, help="Source label for po_funding_plan")
    args = parser.parse_args()

    if not args.xlsx.exists():
        print(f"File not found: {args.xlsx}")
        return 1

    try:
        cny_df = _load_sheet(args.xlsx, "CNY_buy", "Internal_order_code")
        usdt_df = _load_sheet(args.xlsx, "USDT_buy", "Internal_order_code")
    except Exception as exc:
        print(f"Failed to read Excel: {exc}")
        return 1

    if cny_df is None:
        print("CNY_buy sheet header not found")
        return 1

    plans: dict[str, dict] = {}

    def _get_po_id(row) -> str | None:
        po_id = row.get("PO_id")
        if po_id is None or (isinstance(po_id, float) and po_id != po_id):
            po_id = row.get("Internal_order_code")
        if po_id is None or (isinstance(po_id, float) and po_id != po_id):
            return None
        return str(po_id).strip()

    for _, row in cny_df.iterrows():
        po_id = _get_po_id(row)
        if not po_id:
            continue
        total_cny = row.get("PO_total_CNY")
        if total_cny is None or (isinstance(total_cny, float) and total_cny != total_cny):
            total_cny = row.get("PO_cost_CNY")
        total_cny = _to_float(total_cny)
        send_date = _to_date(row.get("Send_Date"))
        rec = plans.setdefault(po_id, {"po_id": po_id})
        if total_cny and not rec.get("total_cny"):
            rec["total_cny"] = total_cny
        if send_date:
            prev = rec.get("message_date")
            if not prev or send_date < prev:
                rec["message_date"] = send_date

    if usdt_df is not None:
        for _, row in usdt_df.iterrows():
            po_id = _get_po_id(row)
            if not po_id:
                continue
            total_usdt = row.get("PO_total_USDT")
            if total_usdt is None or (isinstance(total_usdt, float) and total_usdt != total_usdt):
                total_usdt = row.get("PO_cost_USDT_nom")
            total_usdt = _to_float(total_usdt)
            send_date = _to_date(row.get("Send_Date"))
            rec = plans.setdefault(po_id, {"po_id": po_id})
            if total_usdt and not rec.get("total_usdt"):
                rec["total_usdt"] = total_usdt
            if send_date and not rec.get("message_date"):
                rec["message_date"] = send_date

    if not plans:
        print("No PO rows parsed.")
        return 1

    inserted = 0
    updated = 0
    for po_id, rec in plans.items():
        rec["source"] = args.source or args.xlsx.name
        if args.dry_run:
            continue
        is_new = upsert_po_funding_plan(rec)
        if is_new:
            inserted += 1
        else:
            updated += 1
        upsert_po_header_min(
            po_id=po_id,
            message_date=rec.get("message_date"),
            total_cost_cny=rec.get("total_cny"),
        )

    print(f"PO funding plans parsed: {len(plans)}")
    if not args.dry_run:
        print(f"Inserted: {inserted}")
        print(f"Updated: {updated}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
