#!/usr/bin/env python3
"""Load workbook sales anchor totals into a DB-backed publication table."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sqlite3
import sys
from typing import Any

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.validate_sales_against_workbook import (
    DEFAULT_DB,
    DEFAULT_SHEET,
    DEFAULT_WORKBOOK,
    _find_column,
    _to_date_iso,
    _to_float,
)

STORE_NORMALIZATION = {
    "ACMEWEAR": "ACMEWEAR",
    "UNIVERSAL": "UNIVERSAL",
    "STORE-B": "STOREB",
    "STOREB": "STOREB",
    "11KZ": "11KZ",
    "MELVIS": "MELVIS",
}


def _normalize_store_code(value: Any) -> str:
    raw = str(value or "").strip().upper()
    return STORE_NORMALIZATION.get(raw, raw or "UNKNOWN")


def _load_workbook_rows(workbook_path: Path, *, sheet_name: str = DEFAULT_SHEET) -> pd.DataFrame:
    df = pd.read_excel(workbook_path, sheet_name=sheet_name, dtype=object)
    if df.empty:
        return pd.DataFrame(
            columns=["order_id", "sale_date", "quantity", "net_rev_kzt", "total_price_kzt", "store_code"]
        )

    order_col = _find_column(df.columns.tolist(), ["OrderID", "№ заказа"])
    date_col = _find_column(df.columns.tolist(), ["Date", "order_date", "Дата поступления заказа"])
    qty_col = _find_column(df.columns.tolist(), ["Quantity", "qty", "Количество"])
    total_price_col = _find_column(df.columns.tolist(), ["Total_price", "totalprice", "Сумма"])
    net_rev_col = _find_column(df.columns.tolist(), ["Total_net_rev", "net_rev", "Line_NetRev"])
    store_col = _find_column(df.columns.tolist(), ["STORE_NAME", "store_name", "Store"])

    if order_col is None or date_col is None or qty_col is None:
        raise RuntimeError("workbook missing order/date/quantity columns required for anchor sync")

    rows: list[dict[str, Any]] = []
    for _, row in df.iterrows():
        order_id = str(row.get(order_col) or "").strip()
        sale_date = _to_date_iso(row.get(date_col))
        quantity = _to_float(row.get(qty_col))
        if not order_id or sale_date is None or quantity is None:
            continue
        total_price = _to_float(row.get(total_price_col)) if total_price_col else None
        net_rev = _to_float(row.get(net_rev_col)) if net_rev_col else None
        rows.append(
            {
                "order_id": order_id,
                "sale_date": sale_date,
                "quantity": round(float(quantity or 0.0), 2),
                "net_rev_kzt": round(float(net_rev or 0.0), 2),
                "total_price_kzt": round(float(total_price or 0.0), 2),
                "store_code": _normalize_store_code(row.get(store_col)) if store_col else "UNKNOWN",
            }
        )
    return pd.DataFrame(rows)


def build_workbook_anchor_rows(
    *,
    workbook_path: Path,
    sheet_name: str = DEFAULT_SHEET,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    workbook_rows = _load_workbook_rows(workbook_path, sheet_name=sheet_name)
    if workbook_rows.empty:
        return [], [], {"accepted_orders": 0, "quarantined_orders": 0, "input_rows": 0}

    rows_out: list[dict[str, Any]] = []
    quarantine_out: list[dict[str, Any]] = []
    source_file = str(workbook_path.resolve())

    for (order_id, store_code), group in workbook_rows.groupby(["order_id", "store_code"], dropna=False):
        sale_dates = sorted(set(str(value) for value in group["sale_date"].tolist() if str(value)))
        if len(sale_dates) != 1:
            quarantine_out.append(
                {
                    "order_id": str(order_id),
                    "store_code": str(store_code),
                    "sale_dates": "|".join(sale_dates),
                    "row_count": int(len(group)),
                    "quantity": round(float(group["quantity"].sum()), 2),
                    "net_rev_kzt": round(float(group["net_rev_kzt"].sum()), 2),
                    "total_price_kzt": round(float(group["total_price_kzt"].sum()), 2),
                    "source_file": source_file,
                }
            )
            continue

        rows_out.append(
            {
                "order_id": str(order_id),
                "store_code": str(store_code),
                "sale_date": sale_dates[0],
                "quantity": round(float(group["quantity"].sum()), 2),
                "net_rev_kzt": round(float(group["net_rev_kzt"].sum()), 2),
                "total_price_kzt": round(float(group["total_price_kzt"].sum()), 2),
                "source_file": source_file,
            }
        )

    rows_out.sort(key=lambda row: (row["sale_date"], row["store_code"], row["order_id"]))
    quarantine_out.sort(key=lambda row: (row["store_code"], row["order_id"]))
    summary = {
        "input_rows": int(len(workbook_rows)),
        "accepted_orders": int(len(rows_out)),
        "quarantined_orders": int(len(quarantine_out)),
    }
    return rows_out, quarantine_out, summary


def _ensure_table(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS fact_sales_workbook_anchor (
            order_id TEXT NOT NULL,
            store_code TEXT NOT NULL,
            sale_date TEXT NOT NULL,
            quantity REAL NOT NULL,
            net_rev_kzt REAL NOT NULL,
            total_price_kzt REAL NOT NULL,
            source_file TEXT,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (order_id, store_code)
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS fact_sales_workbook_anchor_quarantine (
            order_id TEXT NOT NULL,
            store_code TEXT NOT NULL,
            sale_dates TEXT NOT NULL,
            row_count INTEGER NOT NULL,
            quantity REAL NOT NULL,
            net_rev_kzt REAL NOT NULL,
            total_price_kzt REAL NOT NULL,
            reason TEXT NOT NULL,
            source_file TEXT,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (order_id, store_code)
        )
        """
    )


def sync_sales_workbook_anchor(
    *,
    db_path: Path,
    workbook_path: Path,
    sheet_name: str = DEFAULT_SHEET,
    apply: bool = False,
) -> dict[str, Any]:
    rows, quarantine, summary = build_workbook_anchor_rows(
        workbook_path=workbook_path,
        sheet_name=sheet_name,
    )
    report = {
        **summary,
        "db_path": str(db_path.resolve()),
        "workbook_path": str(workbook_path.resolve()),
        "apply": bool(apply),
        "applied_rows": 0,
        "quarantined": quarantine,
    }
    if not apply:
        return report

    conn = sqlite3.connect(str(db_path))
    try:
        _ensure_table(conn)
        conn.execute("DELETE FROM fact_sales_workbook_anchor")
        conn.execute("DELETE FROM fact_sales_workbook_anchor_quarantine")
        conn.executemany(
            """
            INSERT INTO fact_sales_workbook_anchor (
                order_id, store_code, sale_date, quantity, net_rev_kzt, total_price_kzt, source_file
            ) VALUES (
                :order_id, :store_code, :sale_date, :quantity, :net_rev_kzt, :total_price_kzt, :source_file
            )
            """,
            rows,
        )
        conn.executemany(
            """
            INSERT INTO fact_sales_workbook_anchor_quarantine (
                order_id, store_code, sale_dates, row_count, quantity, net_rev_kzt, total_price_kzt, reason, source_file
            ) VALUES (
                :order_id, :store_code, :sale_dates, :row_count, :quantity, :net_rev_kzt, :total_price_kzt, 'MULTI_DATE', :source_file
            )
            """,
            quarantine,
        )
        conn.commit()
    finally:
        conn.close()
    report["applied_rows"] = len(rows)
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description="Sync workbook sales anchor into DB")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument("--workbook", type=Path, default=DEFAULT_WORKBOOK)
    parser.add_argument("--sheet-name", default=DEFAULT_SHEET)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()

    if args.apply and str(os.environ.get("ENABLE_SALES_WORKBOOK_ANCHOR_WRITE") or "").strip() != "1":
        raise RuntimeError("workbook anchor write requires ENABLE_SALES_WORKBOOK_ANCHOR_WRITE=1")

    report = sync_sales_workbook_anchor(
        db_path=args.db,
        workbook_path=args.workbook,
        sheet_name=args.sheet_name,
        apply=args.apply,
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
