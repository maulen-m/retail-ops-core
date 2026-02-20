#!/usr/bin/env python3
"""
Import PO arrivals as inventory reclassification (inbound → on-hand).

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
EXPORT_CSV = PROJECT_ROOT / "exports" / "po_arrival_inventory_in_report.csv"
EXPORT_TXT = PROJECT_ROOT / "exports" / "po_arrival_inventory_in_summary.txt"

ARRIVED_STATUSES = {"ARRIVED_AST", "ARRIVED_ALM", "RECEIVED", "CLOSED"}


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


def _latest_inventory_open_date(conn: sqlite3.Connection) -> str | None:
    row = conn.execute(
        """
        SELECT MAX(event_date) as latest
        FROM fact_cashflow_events
        WHERE account IN ('INVENTORY_ON_HAND_COST', 'INVENTORY_INBOUND_COST')
          AND event_type IN ('INVENTORY_OPEN', 'OPENING_BALANCE')
        """
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


def _unit_cost_kzt(line: sqlite3.Row, header: sqlite3.Row, fx_rates, dim_costs: dict) -> float:
    if line["landed_cost_unit_kzt"]:
        return float(line["landed_cost_unit_kzt"])
    if line["unit_cost_kzt"]:
        return float(line["unit_cost_kzt"])
    if line["unit_cost_cny"]:
        fx_rate = header["fx_rate_cny_actual"] or header["fx_rate_cny_plan"]
        if fx_rate:
            return float(line["unit_cost_cny"]) * float(fx_rate)
    meta = dim_costs.get(line["sku_key"], {})
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
    return float(cogs_unit)


def _arrival_date(line: sqlite3.Row, header: sqlite3.Row) -> str | None:
    for field in (
        "receive_date",
        "ast_arrival_real",
        "alm_arrival_real",
        "archive_ast_arrival",
        "archive_alm_arrival",
    ):
        value = None
        if field in line.keys():
            value = line[field]
        if not value and field in header.keys():
            value = header[field]
        if value:
            return value
    return None


def import_po_arrivals(db_path: Path, since: str | None, until: str | None, apply: bool, run_id: str) -> int:
    if not db_path.exists():
        raise FileNotFoundError(f"DB not found: {db_path}")

    summary_lines = []
    with sqlite3.connect(str(db_path)) as conn:
        conn.row_factory = sqlite3.Row
        if not _table_exists(conn, "fact_cashflow_events"):
            raise RuntimeError("fact_cashflow_events missing; run migrate_018_cashflow_calendar.py")
        if not _table_exists(conn, "po_line") or not _table_exists(conn, "po_header"):
            raise RuntimeError("po_line/po_header missing; cannot import PO arrivals")

        if since is None:
            since = _latest_inventory_open_date(conn)
        if since is None:
            raise RuntimeError("No inventory opening balance found; provide --since")

        dim_costs = _load_dim_sku_costs(conn)
        fx_rates = get_fx_rates(until or since, db_path=db_path)

        rows = conn.execute(
            """
            SELECT
                pl.po_id,
                pl.sku_key,
                pl.sku_id,
                pl.my_size,
                pl.order_qty,
                pl.received_qty,
                pl.unit_cost_cny,
                pl.unit_cost_kzt,
                pl.landed_cost_unit_kzt,
                pl.receive_date,
                ph.status as po_status,
                ph.ast_arrival_real,
                ph.alm_arrival_real,
                ph.archive_ast_arrival,
                ph.archive_alm_arrival,
                ph.fx_rate_cny_actual,
                ph.fx_rate_cny_plan
            FROM po_line pl
            JOIN po_header ph ON ph.po_id = pl.po_id
            """
        ).fetchall()

        events = []
        for row in rows:
            arrival = _arrival_date(row, row)
            if not arrival:
                continue
            if arrival < since:
                continue
            if until and arrival > until:
                continue

            received_qty = row["received_qty"] or 0
            qty = received_qty
            if qty <= 0 and row["po_status"] in ARRIVED_STATUSES:
                qty = row["order_qty"] or 0
            if qty <= 0:
                continue

            unit_cost = _unit_cost_kzt(row, row, fx_rates, dim_costs)
            amount = round(unit_cost * qty, 2)
            for event in (
                {
                    "event_date": arrival,
                    "event_type": "INVENTORY_MOVE",
                    "account": "INVENTORY_INBOUND_COST",
                    "amount_kzt": -abs(amount),
                    "sku_key": row["sku_key"],
                    "sku_id": row["sku_id"],
                    "ref_type": "PO_LINE",
                    "ref_id": f"{row['po_id']}:{row['sku_id']}",
                    "notes": f"po_id={row['po_id']} qty={qty} inbound->onhand",
                    "source": "SYSTEM",
                    "run_id": run_id,
                },
                {
                    "event_date": arrival,
                    "event_type": "INVENTORY_MOVE",
                    "account": "INVENTORY_ON_HAND_COST",
                    "amount_kzt": abs(amount),
                    "sku_key": row["sku_key"],
                    "sku_id": row["sku_id"],
                    "ref_type": "PO_LINE",
                    "ref_id": f"{row['po_id']}:{row['sku_id']}",
                    "notes": f"po_id={row['po_id']} qty={qty} inbound->onhand",
                    "source": "SYSTEM",
                    "run_id": run_id,
                },
            ):
                event["event_hash"] = _event_hash(event)
                events.append((event, qty, unit_cost))

        existing_hashes = set()
        if events:
            existing_hashes = {
                row[0]
                for row in conn.execute(
                    "SELECT event_hash FROM fact_cashflow_events WHERE event_hash IN ({})".format(",".join("?" * len(events))
                    ),
                    [e[0]["event_hash"] for e in events],
                ).fetchall()
            }

        new_events = [e for e in events if e[0]["event_hash"] not in existing_hashes]

        EXPORT_CSV.parent.mkdir(parents=True, exist_ok=True)
        with EXPORT_CSV.open("w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow([
                "event_date",
                "po_id",
                "sku_key",
                "sku_id",
                "qty",
                "unit_cost_kzt",
                "amount_kzt",
                "event_hash",
            ])
            for event, qty, unit_cost in new_events:
                po_id = (event.get("ref_id") or "").split(":")[0]
                writer.writerow([
                    event["event_date"],
                    po_id,
                    event["sku_key"],
                    event["sku_id"],
                    qty,
                    round(unit_cost, 2),
                    event["amount_kzt"],
                    event["event_hash"],
                ])

        summary_lines.append(f"since={since}")
        summary_lines.append(f"until={until or 'none'}")
        summary_lines.append(f"events_total={len(events)}")
        summary_lines.append(f"events_new={len(new_events)}")
        summary_lines.append(f"events_existing_skipped={len(events) - len(new_events)}")

        if apply:
            if os.environ.get("ENABLE_CASHFLOW_WRITE") != "1":
                raise RuntimeError("ENABLE_CASHFLOW_WRITE=1 is required to apply cashflow writes.")
            for event, _, _ in new_events:
                conn.execute(
                    """
                    INSERT OR IGNORE INTO fact_cashflow_events (
                        event_date, event_type, account, amount_kzt, sku_key, sku_id, ref_type, ref_id, notes, source, run_id, event_hash
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        event["event_date"],
                        event["event_type"],
                        event["account"],
                        event["amount_kzt"],
                        event["sku_key"],
                        event["sku_id"],
                        event["ref_type"],
                        event["ref_id"],
                        event["notes"],
                        event["source"],
                        event["run_id"],
                        event["event_hash"],
                    ),
                )
            conn.commit()
            summary_lines.append("APPLY: inserted INVENTORY_MOVE events.")
        else:
            summary_lines.append("DRY RUN: no DB writes.")

    EXPORT_TXT.write_text("\n".join(summary_lines) + "\n")
    print(f"PO arrival inventory report: {EXPORT_CSV}")
    print(f"PO arrival summary: {EXPORT_TXT}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Import PO arrivals as inbound→on-hand inventory moves")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument("--since", type=str, default=None, help="Start date (YYYY-MM-DD). Defaults to latest inventory open.")
    parser.add_argument("--until", type=str, default=None, help="Optional end date (YYYY-MM-DD).")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--run-id", type=str, default=None)
    args = parser.parse_args()

    run_id = args.run_id or datetime.now().strftime("%Y%m%d_%H%M%S")
    return import_po_arrivals(args.db, args.since, args.until, args.apply, run_id)


if __name__ == "__main__":
    raise SystemExit(main())
