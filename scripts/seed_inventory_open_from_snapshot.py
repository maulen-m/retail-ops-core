#!/usr/bin/env python3
"""
Seed INVENTORY_COST opening balance from the latest snapshot on/before a date.

Default: DRY RUN. Apply requires ENABLE_CASHFLOW_WRITE=1 and --apply.
"""
from __future__ import annotations

import argparse
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
EXPORT_PATH = PROJECT_ROOT / "exports" / "inventory_open_seed_report.txt"


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


def seed_inventory_open(as_of: str, db_path: Path, apply: bool, run_id: str, notes: str | None) -> int:
    if not db_path.exists():
        raise FileNotFoundError(f"DB not found: {db_path}")

    report_lines = []
    with sqlite3.connect(str(db_path)) as conn:
        conn.row_factory = sqlite3.Row
        if not _table_exists(conn, "fact_cashflow_events"):
            raise RuntimeError("fact_cashflow_events missing; run migrate_018_cashflow_calendar.py")
        if not _table_exists(conn, "fact_inventory_snapshot_size"):
            raise RuntimeError("fact_inventory_snapshot_size missing; cannot seed inventory")

        snapshot_date = _latest_snapshot_on_or_before(conn, as_of)
        if not snapshot_date:
            raise RuntimeError(f"No inventory snapshot on/before {as_of}")

        inventory_cost = _compute_inventory_cost(conn, snapshot_date)

        event = {
            "event_date": as_of,
            "event_type": "INVENTORY_OPEN",
            "account": "INVENTORY_COST",
            "amount_kzt": float(inventory_cost),
            "notes": notes or f"snapshot={snapshot_date}",
            "source": "SYSTEM",
            "run_id": run_id,
            "ref_type": "SNAPSHOT",
            "ref_id": snapshot_date,
        }
        event["event_hash"] = _event_hash(event)

        existing = conn.execute(
            "SELECT 1 FROM fact_cashflow_events WHERE event_hash = ?",
            (event["event_hash"],),
        ).fetchone()

        if existing:
            report_lines.append("Existing INVENTORY_OPEN event already present; skipping.")
        elif apply:
            if os.environ.get("ENABLE_CASHFLOW_WRITE") != "1":
                raise RuntimeError("ENABLE_CASHFLOW_WRITE=1 is required to apply cashflow writes.")
            conn.execute(
                """
                INSERT OR IGNORE INTO fact_cashflow_events (
                    event_date, event_type, account, amount_kzt, notes, source, run_id, ref_type, ref_id, event_hash
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    event["event_date"],
                    event["event_type"],
                    event["account"],
                    event["amount_kzt"],
                    event["notes"],
                    event["source"],
                    event["run_id"],
                    event["ref_type"],
                    event["ref_id"],
                    event["event_hash"],
                ),
            )
            conn.commit()
            report_lines.append("APPLY: inserted INVENTORY_OPEN event.")
        else:
            report_lines.append("DRY RUN: no DB writes.")

        report_lines.append(f"as_of={as_of}")
        report_lines.append(f"snapshot_date={snapshot_date}")
        report_lines.append(f"inventory_cost_kzt={inventory_cost:,.2f}")

    EXPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    EXPORT_PATH.write_text("\n".join(report_lines) + "\n")
    print(f"Inventory open seed report: {EXPORT_PATH}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Seed INVENTORY_COST opening balance from snapshot")
    parser.add_argument("--as-of", required=True, help="As-of date for opening balance (YYYY-MM-DD)")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--run-id", type=str, default=None)
    parser.add_argument("--notes", type=str, default=None)
    args = parser.parse_args()

    run_id = args.run_id or datetime.now().strftime("%Y%m%d_%H%M%S")
    return seed_inventory_open(args.as_of, args.db, args.apply, run_id, args.notes)


if __name__ == "__main__":
    raise SystemExit(main())
