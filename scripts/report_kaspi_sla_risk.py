#!/usr/bin/env python3
"""Generate Kaspi SLA + risk profile report from fact_orders_kaspi."""
from __future__ import annotations

import argparse
import sqlite3
from datetime import date
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DB = PROJECT_ROOT / "db" / "app.db"
DEFAULT_OUT = PROJECT_ROOT / "exports" / "kaspi_sla_risk_report.md"


def _table_exists(conn: sqlite3.Connection, name: str) -> bool:
    return conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
        (name,),
    ).fetchone() is not None


def _parse_date(value: str | None) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(str(value))
    except Exception:
        return None


def build_sla_risk_report(db_path: Path, output_path: Path) -> None:
    if not db_path.exists():
        raise FileNotFoundError(f"DB not found: {db_path}")

    with sqlite3.connect(str(db_path)) as conn:
        conn.row_factory = sqlite3.Row
        if not _table_exists(conn, "fact_orders_kaspi"):
            raise RuntimeError("fact_orders_kaspi missing")

        rows = conn.execute(
            """
            SELECT planned_shipment_date, actual_shipment_date,
                   courier_transmission_planning_date, courier_transmission_date,
                   returned_to_warehouse, express, signature_required
            FROM fact_orders_kaspi
            """
        ).fetchall()

    total_orders = len(rows)
    ship_delays = []
    transmission_delays = []
    returned_count = 0
    express_count = 0
    signature_count = 0

    for row in rows:
        planned_ship = _parse_date(row["planned_shipment_date"])
        actual_ship = _parse_date(row["actual_shipment_date"])
        if planned_ship and actual_ship:
            ship_delays.append((actual_ship - planned_ship).days)

        planned_trans = _parse_date(row["courier_transmission_planning_date"])
        actual_trans = _parse_date(row["courier_transmission_date"])
        if planned_trans and actual_trans:
            transmission_delays.append((actual_trans - planned_trans).days)

        if row["returned_to_warehouse"]:
            returned_count += 1
        if row["express"]:
            express_count += 1
        if row["signature_required"]:
            signature_count += 1

    avg_ship_delay = round(sum(ship_delays) / len(ship_delays), 2) if ship_delays else 0.0
    avg_trans_delay = (
        round(sum(transmission_delays) / len(transmission_delays), 2)
        if transmission_delays
        else 0.0
    )

    lines = [
        "# Kaspi SLA + Risk Report",
        "",
        f"total_orders: {total_orders}",
        f"avg_ship_delay_days: {avg_ship_delay}",
        f"avg_transmission_delay_days: {avg_trans_delay}",
        f"returned_to_warehouse: {returned_count}",
        f"express: {express_count}",
        f"signature_required: {signature_count}",
    ]

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text("\n".join(lines) + "\n")


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate Kaspi SLA/risk report")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args()

    build_sla_risk_report(args.db, args.out)
    print(f"Report: {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
