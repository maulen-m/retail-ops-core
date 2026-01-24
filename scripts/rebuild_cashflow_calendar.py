#!/usr/bin/env python3
"""
Rebuild cashflow calendar (events + daily roll-forward).

Default: DRY RUN (no DB writes). Apply requires ENABLE_CASHFLOW_WRITE=1 and --apply.
"""

from __future__ import annotations

import argparse
import os
import hashlib
import sqlite3
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Optional, Iterable
import sys

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from core.db.queries import get_cutoff_date_almaty
from core.cashflow.payout_model import load_payout_model
from core.config.business_params import get_fx_rates
from core.calc.economics import calc_cogs
DEFAULT_DB = PROJECT_ROOT / "db" / "app.db"

AUTO_EVENT_TYPES = {"SALE_ACCRUED", "COGS_RECOGNIZED", "PAYOUT_EXPECTED"}
EXPENSE_EVENT_TYPES = {
    "EXPENSE",
    "KASPI_FEES",
    "DELIVERY_FEES",
    "ADS",
    "BONUS",
    "TRANSFER",
    "LOAN_PAYMENT",
    "UNKNOWN",
}
PAYOUT_EVENT_TYPES = {"PAYOUT_RECEIVED", "PAYOUT_EXPECTED"}


def _table_exists(conn: sqlite3.Connection, name: str) -> bool:
    return conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
        (name,),
    ).fetchone() is not None


def _get_columns(conn: sqlite3.Connection, table: str) -> set[str]:
    return {row[1] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}


def _normalize_date(value: str | date | datetime) -> str:
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    return str(value)


def _event_hash(event: dict) -> str:
    parts = [
        _normalize_date(event.get("event_date")),
        str(event.get("event_type") or ""),
        str(event.get("account") or ""),
        f"{float(event.get('amount_kzt') or 0.0):.4f}",
        str(event.get("store_code") or ""),
        str(event.get("sku_key") or ""),
        str(event.get("sku_id") or ""),
        str(event.get("ref_type") or ""),
        str(event.get("ref_id") or ""),
        str(event.get("source") or ""),
    ]
    payload = "|".join(parts)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _detect_sales_source(conn: sqlite3.Connection) -> Optional[dict]:
    candidates = [
        ("fact_sales", {"date": ["order_date", "sale_date"], "qty": ["quantity", "qty"]}),
        ("sales_fact_v2", {"date": ["order_date", "sale_date"], "qty": ["quantity", "qty"]}),
    ]
    for table, req in candidates:
        if not _table_exists(conn, table):
            continue
        cols = _get_columns(conn, table)
        date_col = next((c for c in req["date"] if c in cols), None)
        qty_col = next((c for c in req["qty"] if c in cols), None)
        if not date_col or not qty_col:
            continue
        return {"table": table, "date_col": date_col, "qty_col": qty_col, "cols": cols}
    return None


def _get_net_rev_expression(cols: set[str], qty_col: str) -> tuple[str, bool]:
    line_cols = ["line_net_rev", "line_net_revenue", "line_net_rev_kzt"]
    unit_cols = ["net_rev_unit", "net_revenue_unit", "net_rev_kzt", "net_revenue"]
    for col in line_cols:
        if col in cols:
            return f"{col}", True
    for col in unit_cols:
        if col in cols:
            return f"{col} * {qty_col}", True
    return "0", False


def _get_cogs_expression(cols: set[str], qty_col: str) -> tuple[str, bool]:
    unit_cols = ["cogs_unit", "unit_cogs"]
    for col in unit_cols:
        if col in cols:
            return f"{col} * {qty_col}", True
    return "0", False


def _load_dim_sku_costs(conn: sqlite3.Connection) -> dict[str, dict]:
    if not _table_exists(conn, "dim_sku"):
        return {}
    rows = conn.execute(
        "SELECT sku_key, cogs_kzt, base_cost_cny, weight_kg FROM dim_sku"
    ).fetchall()
    return {
        row["sku_key"]: {
            "cogs_kzt": row["cogs_kzt"] or 0.0,
            "base_cost_cny": row["base_cost_cny"] or 0.0,
            "weight_kg": row["weight_kg"] or 0.0,
        }
        for row in rows
    }


def _build_sales_aggregates(
    conn: sqlite3.Connection,
    start_date: date,
    end_date: date,
    fx_rates,
) -> tuple[dict[str, float], dict[str, float]]:
    source = _detect_sales_source(conn)
    if not source:
        return {}, {}

    table = source["table"]
    date_col = source["date_col"]
    qty_col = source["qty_col"]
    cols = source["cols"]
    store_col = "store_code" if "store_code" in cols else None
    sku_key_col = "sku_key" if "sku_key" in cols else None
    sku_id_col = "sku_id" if "sku_id" in cols else None

    net_rev_expr, has_net_rev = _get_net_rev_expression(cols, qty_col)
    cogs_expr, has_cogs = _get_cogs_expression(cols, qty_col)

    select_cols = [
        f"{date_col} as sale_date",
        f"{qty_col} as quantity",
        f"{net_rev_expr} as line_net_rev",
        f"{cogs_expr} as line_cogs",
    ]
    if store_col:
        select_cols.append(f"{store_col} as store_code")
    else:
        select_cols.append("NULL as store_code")
    if sku_key_col:
        select_cols.append(f"{sku_key_col} as sku_key")
    else:
        select_cols.append("NULL as sku_key")
    if sku_id_col:
        select_cols.append(f"{sku_id_col} as sku_id")
    else:
        select_cols.append("NULL as sku_id")

    query = f"""
        SELECT {", ".join(select_cols)}
        FROM {table}
        WHERE {date_col} BETWEEN ? AND ?
    """

    dim_costs = _load_dim_sku_costs(conn)
    sales_by_date: dict[str, float] = {}
    cogs_by_date: dict[str, float] = {}

    rows = conn.execute(query, (start_date.isoformat(), end_date.isoformat())).fetchall()
    for row in rows:
        sale_date = row["sale_date"]
        if not sale_date:
            continue
        qty = float(row["quantity"] or 0.0)
        if qty <= 0:
            continue
        line_net = float(row["line_net_rev"] or 0.0)
        line_cogs = float(row["line_cogs"] or 0.0)

        if not has_net_rev:
            line_net = 0.0
        if not has_cogs:
            sku_key = row["sku_key"]
            meta = dim_costs.get(sku_key or "", {})
            cogs_unit = meta.get("cogs_kzt") or 0.0
            if cogs_unit <= 0:
                base_cost = meta.get("base_cost_cny", 0.0)
                weight = meta.get("weight_kg", 0.0)
                cogs_unit = calc_cogs(
                    base_cost,
                    weight,
                    cny_kzt=fx_rates.cny_kzt,
                    volumetric_factor=fx_rates.dlv_rate_usd_kg,
                    freight_rate=fx_rates.usd_kzt,
                )
            line_cogs = cogs_unit * qty

        sales_by_date[sale_date] = sales_by_date.get(sale_date, 0.0) + line_net
        cogs_by_date[sale_date] = cogs_by_date.get(sale_date, 0.0) + line_cogs

    return sales_by_date, cogs_by_date


def _inventory_anchor_date(conn: sqlite3.Connection) -> date | None:
    if not _table_exists(conn, "fact_cashflow_events"):
        return None
    row = conn.execute(
        """
        SELECT MAX(event_date) as max_date
        FROM fact_cashflow_events
        WHERE account = 'INVENTORY_COST'
          AND event_type IN ('INVENTORY_OPEN', 'OPENING_BALANCE')
        """
    ).fetchone()
    if row and row["max_date"]:
        return date.fromisoformat(row["max_date"])
    return None


def _build_system_events(
    conn: sqlite3.Connection,
    start_date: date,
    end_date: date,
    fx_rates,
    run_id: str,
) -> list[dict]:
    sales_by_date, cogs_by_date = _build_sales_aggregates(conn, start_date, end_date, fx_rates)
    payout_model = load_payout_model()
    last_statement_date = None
    if _table_exists(conn, "fact_cashflow_events"):
        row = conn.execute(
            """
            SELECT MAX(event_date) as max_date
            FROM fact_cashflow_events
            WHERE source = 'STATEMENT_ACTUAL'
            """
        ).fetchone()
        if row and row["max_date"]:
            last_statement_date = date.fromisoformat(row["max_date"])
    inventory_anchor_date = _inventory_anchor_date(conn)
    events: list[dict] = []
    for sale_date, amount in sales_by_date.items():
        if amount == 0:
            continue
        events.append(
            {
                "event_date": sale_date,
                "event_type": "SALE_ACCRUED",
                "account": "RECEIVABLES",
                "amount_kzt": round(amount, 2),
                "source": "ORDER_MODELLED",
                "run_id": run_id,
            }
        )
        sale_day = date.fromisoformat(sale_date)
        if last_statement_date and sale_day <= last_statement_date:
            continue
        payout_date = sale_day + timedelta(days=payout_model.base_lag_days)
        events.append(
            {
                "event_date": payout_date.isoformat(),
                "event_type": "PAYOUT_EXPECTED",
                "account": "CASH",
                "amount_kzt": round(amount, 2),
                "source": "ORDER_MODELLED",
                "run_id": run_id,
            }
        )
        events.append(
            {
                "event_date": payout_date.isoformat(),
                "event_type": "PAYOUT_EXPECTED",
                "account": "RECEIVABLES",
                "amount_kzt": round(-abs(amount), 2),
                "source": "ORDER_MODELLED",
                "run_id": run_id,
            }
        )
    for sale_date, amount in cogs_by_date.items():
        if amount == 0:
            continue
        if inventory_anchor_date and date.fromisoformat(sale_date) < inventory_anchor_date:
            continue
        events.append(
            {
                "event_date": sale_date,
                "event_type": "COGS_RECOGNIZED",
                "account": "INVENTORY_COST",
                "amount_kzt": round(-abs(amount), 2),
                "source": "ORDER_MODELLED",
                "run_id": run_id,
            }
        )
    return events


def _fetch_manual_events(
    conn: sqlite3.Connection,
    start_date: date,
    end_date: date,
) -> list[dict]:
    if not _table_exists(conn, "fact_cashflow_events"):
        return []
    rows = conn.execute(
        """
        SELECT event_date, event_type, account, amount_kzt, store_code, sku_key, sku_id,
               ref_type, ref_id, notes, source, run_id, event_hash
        FROM fact_cashflow_events
        WHERE event_date BETWEEN ? AND ?
          AND NOT (source IN ('SYSTEM', 'ORDER_MODELLED') AND event_type IN ('SALE_ACCRUED', 'COGS_RECOGNIZED', 'PAYOUT_EXPECTED'))
        """,
        (start_date.isoformat(), end_date.isoformat()),
    ).fetchall()
    events = []
    for row in rows:
        events.append(dict(row))
    return events


def _date_range(start: date, end: date) -> Iterable[date]:
    current = start
    while current <= end:
        yield current
        current += timedelta(days=1)


def compute_daily_rows(
    events: list[dict],
    start_date: date,
    end_date: date,
    run_id: Optional[str] = None,
) -> list[dict]:
    events_by_date: dict[str, list[dict]] = {}
    for event in events:
        key = _normalize_date(event["event_date"])
        events_by_date.setdefault(key, []).append(event)

    daily_rows = []
    cash_open = receivables_open = inventory_open = 0.0

    for day in _date_range(start_date, end_date):
        day_key = day.isoformat()
        day_events = events_by_date.get(day_key, [])
        cash_flow = sum(e.get("amount_kzt", 0.0) for e in day_events if e.get("account") == "CASH")
        recv_flow = sum(e.get("amount_kzt", 0.0) for e in day_events if e.get("account") == "RECEIVABLES")
        inv_flow = sum(e.get("amount_kzt", 0.0) for e in day_events if e.get("account") == "INVENTORY_COST")

        cash_close = cash_open + cash_flow
        receivables_close = receivables_open + recv_flow
        inventory_close = inventory_open + inv_flow

        sales_accrued = sum(e.get("amount_kzt", 0.0) for e in day_events if e.get("event_type") == "SALE_ACCRUED")
        payouts_received = sum(
            e.get("amount_kzt", 0.0)
            for e in day_events
            if e.get("event_type") in PAYOUT_EVENT_TYPES
        )
        refunds = abs(sum(e.get("amount_kzt", 0.0) for e in day_events if e.get("event_type") == "REFUND"))
        po_payments = abs(sum(e.get("amount_kzt", 0.0) for e in day_events if e.get("event_type") == "PO_PAYMENT"))
        expenses = abs(
            sum(
                e.get("amount_kzt", 0.0)
                for e in day_events
                if e.get("event_type") in EXPENSE_EVENT_TYPES
            )
        )
        cogs = abs(sum(e.get("amount_kzt", 0.0) for e in day_events if e.get("event_type") == "COGS_RECOGNIZED"))

        profit_accrual = sales_accrued - cogs - expenses
        capital_close = cash_close + receivables_close + inventory_close

        daily_rows.append(
            {
                "date": day_key,
                "cash_open": round(cash_open, 2),
                "cash_close": round(cash_close, 2),
                "receivables_open": round(receivables_open, 2),
                "receivables_close": round(receivables_close, 2),
                "inventory_cost_open": round(inventory_open, 2),
                "inventory_cost_close": round(inventory_close, 2),
                "capital_close": round(capital_close, 2),
                "sales_accrued_kzt": round(sales_accrued, 2),
                "payouts_received_kzt": round(payouts_received, 2),
                "refunds_kzt": round(refunds, 2),
                "po_payments_kzt": round(po_payments, 2),
                "expenses_kzt": round(expenses, 2),
                "cogs_kzt": round(cogs, 2),
                "cash_flow_kzt": round(cash_flow, 2),
                "receivables_flow_kzt": round(recv_flow, 2),
                "inventory_cost_flow_kzt": round(inv_flow, 2),
                "profit_accrual_kzt": round(profit_accrual, 2),
                "run_id": run_id or "",
            }
        )

        cash_open = cash_close
        receivables_open = receivables_close
        inventory_open = inventory_close

    return daily_rows


def rebuild_cashflow_calendar(
    db_path: Path,
    start_date: date,
    end_date: date,
    apply: bool,
    run_id: str,
) -> tuple[list[dict], list[dict]]:
    if not db_path.exists():
        raise FileNotFoundError(f"DB not found: {db_path}")

    fx_rates = get_fx_rates(end_date, db_path=db_path)
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    try:
        if not _table_exists(conn, "fact_cashflow_events"):
            raise RuntimeError("fact_cashflow_events missing; run migrate_018_cashflow_calendar.py")

        system_events = _build_system_events(conn, start_date, end_date, fx_rates, run_id)
        manual_events = _fetch_manual_events(conn, start_date, end_date)
        inventory_anchor_date = _inventory_anchor_date(conn)
        if inventory_anchor_date:
            anchor_key = inventory_anchor_date.isoformat()
            manual_events = [
                e
                for e in manual_events
                if not (
                    e.get("account") == "INVENTORY_COST"
                    and _normalize_date(e.get("event_date")) < anchor_key
                )
            ]
        all_events = manual_events + system_events

        if apply:
            if os.environ.get("ENABLE_CASHFLOW_WRITE") != "1":
                raise RuntimeError("ENABLE_CASHFLOW_WRITE=1 is required to apply cashflow writes.")

            conn.execute(
                """
                DELETE FROM fact_cashflow_events
                WHERE event_date BETWEEN ? AND ?
                  AND source IN ('SYSTEM', 'ORDER_MODELLED')
                  AND event_type IN ('SALE_ACCRUED', 'COGS_RECOGNIZED', 'PAYOUT_EXPECTED')
                """,
                (start_date.isoformat(), end_date.isoformat()),
            )
            for event in system_events:
                event["event_hash"] = _event_hash(event)
                conn.execute(
                    """
                    INSERT OR IGNORE INTO fact_cashflow_events (
                        event_date, event_type, account, amount_kzt, store_code, sku_key, sku_id,
                        ref_type, ref_id, notes, source, run_id, event_hash
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        _normalize_date(event["event_date"]),
                        event["event_type"],
                        event["account"],
                        float(event["amount_kzt"]),
                        event.get("store_code"),
                        event.get("sku_key"),
                        event.get("sku_id"),
                        event.get("ref_type"),
                        event.get("ref_id"),
                        event.get("notes"),
                        event.get("source", "SYSTEM"),
                        event.get("run_id", run_id),
                        event["event_hash"],
                    ),
                )

        daily_rows = compute_daily_rows(all_events, start_date, end_date, run_id=run_id)

        if apply:
            conn.execute(
                "DELETE FROM fact_cashflow_daily WHERE date BETWEEN ? AND ?",
                (start_date.isoformat(), end_date.isoformat()),
            )
            for row in daily_rows:
                conn.execute(
                    """
                    INSERT OR REPLACE INTO fact_cashflow_daily (
                        date, cash_open, cash_close, receivables_open, receivables_close,
                        inventory_cost_open, inventory_cost_close, capital_close,
                        sales_accrued_kzt, payouts_received_kzt, refunds_kzt, po_payments_kzt,
                        expenses_kzt, cogs_kzt, cash_flow_kzt, receivables_flow_kzt,
                        inventory_cost_flow_kzt, profit_accrual_kzt, run_id
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        row["date"],
                        row["cash_open"],
                        row["cash_close"],
                        row["receivables_open"],
                        row["receivables_close"],
                        row["inventory_cost_open"],
                        row["inventory_cost_close"],
                        row["capital_close"],
                        row["sales_accrued_kzt"],
                        row["payouts_received_kzt"],
                        row["refunds_kzt"],
                        row["po_payments_kzt"],
                        row["expenses_kzt"],
                        row["cogs_kzt"],
                        row["cash_flow_kzt"],
                        row["receivables_flow_kzt"],
                        row["inventory_cost_flow_kzt"],
                        row["profit_accrual_kzt"],
                        row["run_id"],
                    ),
                )

        if apply:
            conn.commit()

        return daily_rows, system_events
    finally:
        conn.close()


def _resolve_start_end(conn: sqlite3.Connection) -> tuple[date, date]:
    cutoff = get_cutoff_date_almaty()
    start = cutoff
    if _table_exists(conn, "fact_cashflow_events"):
        row = conn.execute(
            "SELECT MIN(event_date) AS min_date FROM fact_cashflow_events"
        ).fetchone()
        if row and row["min_date"]:
            start = min(start, date.fromisoformat(row["min_date"]))
    source = _detect_sales_source(conn)
    if source:
        row = conn.execute(
            f"SELECT MIN({source['date_col']}) AS min_date FROM {source['table']}"
        ).fetchone()
        if row and row["min_date"]:
            start = min(start, date.fromisoformat(row["min_date"]))
    return start, cutoff


def main() -> int:
    parser = argparse.ArgumentParser(description="Rebuild cashflow calendar")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB, help="Path to SQLite DB")
    parser.add_argument("--start-date", type=str, help="Start date (YYYY-MM-DD)")
    parser.add_argument("--end-date", type=str, help="End date (YYYY-MM-DD)")
    parser.add_argument("--apply", action="store_true", help="Write derived tables/events (requires ENABLE_CASHFLOW_WRITE=1)")
    parser.add_argument("--run-id", type=str, default=None, help="Run id for audit")
    args = parser.parse_args()

    conn = sqlite3.connect(str(args.db))
    conn.row_factory = sqlite3.Row
    try:
        if args.start_date and args.end_date:
            start = date.fromisoformat(args.start_date)
            end = date.fromisoformat(args.end_date)
        else:
            start, end = _resolve_start_end(conn)
    finally:
        conn.close()

    run_id = args.run_id or datetime.now().strftime("%Y%m%d_%H%M%S")
    daily_rows, system_events = rebuild_cashflow_calendar(args.db, start, end, args.apply, run_id)

    print("Cashflow rebuild summary")
    print(f"  Range: {start.isoformat()} → {end.isoformat()}")
    print(f"  System events generated: {len(system_events)}")
    print(f"  Daily rows computed: {len(daily_rows)}")
    if args.apply:
        print("  APPLY: wrote SYSTEM events + daily table.")
    else:
        print("  DRY RUN: no DB writes.")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
