#!/usr/bin/env python3
"""
Import opening balance events for CASH / RECEIVABLES / INVENTORY_COST.

Default: DRY RUN. Apply requires ENABLE_CASHFLOW_WRITE=1 and --apply.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import os
import sqlite3
from datetime import datetime
from pathlib import Path

import sys

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from core.config.business_params import get_fx_rates
from core.calc.economics import calc_cogs

DEFAULT_DB = PROJECT_ROOT / "db" / "app.db"
EXPORT_PATH = PROJECT_ROOT / "exports" / "opening_balance_import_report.txt"


def _table_exists(conn: sqlite3.Connection, name: str) -> bool:
    return conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
        (name,),
    ).fetchone() is not None


def _event_hash(event: dict) -> str:
    parts = [
        str(event.get("event_date") or ""),
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


def _normalize_amount(value: str | None) -> float | None:
    if value is None:
        return None
    text = str(value).strip()
    if text == "":
        return None
    try:
        return float(text.replace(",", ""))
    except Exception:
        return None


def _latest_snapshot_on_or_before(conn: sqlite3.Connection, as_of: str) -> str | None:
    row = conn.execute(
        "SELECT MAX(snapshot_date) as latest FROM fact_inventory_snapshot_size WHERE snapshot_date <= ?",
        (as_of,),
    ).fetchone()
    return row[0] if row and row[0] else None


def _load_dim_sku_costs(conn: sqlite3.Connection) -> dict[str, dict]:
    if not _table_exists(conn, "dim_sku"):
        return {}
    rows = conn.execute(
        "SELECT sku_key, cogs_kzt, base_cost_cny, weight_kg FROM dim_sku"
    ).fetchall()
    return {
        row[0]: {
            "cogs_kzt": row[1] or 0.0,
            "base_cost_cny": row[2] or 0.0,
            "weight_kg": row[3] or 0.0,
        }
        for row in rows
    }


def _compute_inventory_cost(conn: sqlite3.Connection, snapshot_date: str) -> float:
    if not _table_exists(conn, "fact_inventory_snapshot_size"):
        return 0.0

    rows = conn.execute(
        """
        SELECT sku_key, SUM(current_stock) as stock
        FROM fact_inventory_snapshot_size
        WHERE snapshot_date = ?
        GROUP BY sku_key
        """,
        (snapshot_date,),
    ).fetchall()

    fx_rates = get_fx_rates(snapshot_date, db_path=DEFAULT_DB)
    dim_costs = _load_dim_sku_costs(conn)
    total = 0.0
    for sku_key, stock in rows:
        if stock is None or stock <= 0:
            continue
        meta = dim_costs.get(sku_key, {})
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
        total += float(stock) * cogs_unit
    return round(total, 2)


def import_opening_balances(csv_path: Path, db_path: Path, apply: bool, run_id: str) -> int:
    if not csv_path.exists():
        raise FileNotFoundError(f"CSV not found: {csv_path}")
    if not db_path.exists():
        raise FileNotFoundError(f"DB not found: {db_path}")

    report_lines = []
    with sqlite3.connect(str(db_path)) as conn:
        conn.row_factory = sqlite3.Row
        if not _table_exists(conn, "fact_cashflow_events"):
            raise RuntimeError("fact_cashflow_events missing; run migrate_018_cashflow_calendar.py")

        reader = csv.DictReader(csv_path.open("r", newline=""))
        required = {"as_of_date", "account", "amount_kzt"}
        if not required.issubset(reader.fieldnames or []):
            raise ValueError(f"CSV missing required columns: {required}")

        rows = list(reader)
        to_insert = []
        computed_inventory = None

        for row in rows:
            as_of = (row.get("as_of_date") or "").strip()
            account = (row.get("account") or "").strip().upper()
            amount = _normalize_amount(row.get("amount_kzt"))

            if account == "INVENTORY_COST" and amount is None:
                snapshot_date = _latest_snapshot_on_or_before(conn, as_of)
                if not snapshot_date:
                    raise RuntimeError(f"No inventory snapshot on/before {as_of}")
                computed_inventory = _compute_inventory_cost(conn, snapshot_date)
                amount = computed_inventory
                report_lines.append(f"Computed INVENTORY_COST from snapshot {snapshot_date}: {computed_inventory:,.2f} KZT")

            if amount is None:
                raise ValueError(f"Missing amount_kzt for account {account} on {as_of}")

            event = {
                "event_date": as_of,
                "event_type": "OPENING_BALANCE",
                "account": account,
                "amount_kzt": float(amount),
                "notes": row.get("notes") or None,
                "source": row.get("source") or "MANUAL",
                "run_id": run_id,
            }
            event["event_hash"] = _event_hash(event)
            to_insert.append(event)

        existing_hashes = set()
        if to_insert:
            existing_hashes = {
                row[0]
                for row in conn.execute(
                    "SELECT event_hash FROM fact_cashflow_events WHERE event_hash IN ({})".format(",".join("?" * len(to_insert))
                    ),
                    [e["event_hash"] for e in to_insert],
                ).fetchall()
            }

        new_events = [e for e in to_insert if e["event_hash"] not in existing_hashes]

        report_lines.append(f"Rows in CSV: {len(rows)}")
        report_lines.append(f"New events: {len(new_events)} (existing skipped: {len(to_insert) - len(new_events)})")

        if apply:
            if os.environ.get("ENABLE_CASHFLOW_WRITE") != "1":
                raise RuntimeError("ENABLE_CASHFLOW_WRITE=1 is required to apply cashflow writes.")
            for e in new_events:
                conn.execute(
                    """
                    INSERT OR IGNORE INTO fact_cashflow_events (
                        event_date, event_type, account, amount_kzt, notes, source, run_id, event_hash
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        e["event_date"],
                        e["event_type"],
                        e["account"],
                        e["amount_kzt"],
                        e["notes"],
                        e["source"],
                        e["run_id"],
                        e["event_hash"],
                    ),
                )
            conn.commit()
            report_lines.append("APPLY: inserted opening balance events.")
        else:
            report_lines.append("DRY RUN: no DB writes.")

    EXPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    EXPORT_PATH.write_text("\n".join(report_lines) + "\n")
    print(f"Opening balance report: {EXPORT_PATH}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Import cashflow opening balances")
    parser.add_argument("--csv", type=Path, default=PROJECT_ROOT / "data" / "cashflow" / "opening_balances.csv")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--run-id", type=str, default=None)
    args = parser.parse_args()

    run_id = args.run_id or datetime.now().strftime("%Y%m%d_%H%M%S")
    return import_opening_balances(args.csv, args.db, args.apply, run_id)


if __name__ == "__main__":
    raise SystemExit(main())
