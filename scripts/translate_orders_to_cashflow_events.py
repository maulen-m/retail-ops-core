#!/usr/bin/env python3
"""
Translate Kaspi order lifecycle into cashflow events (receivables + expected payouts).

Default: DRY RUN. Apply requires ENABLE_CASHFLOW_WRITE=1 and --apply.
"""
from __future__ import annotations

import argparse
import hashlib
import os
import sqlite3
from datetime import date, datetime, timedelta
from pathlib import Path
import sys
import yaml

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from core.db.queries import get_cutoff_date_almaty
from core.cashflow.payout_model import load_payout_model
from core.cashflow.order_status import normalize_order_status
from core.config.business_params import get_vat_rate
from core.calc.economics import calc_delivery_fee, calc_net_rev

DEFAULT_DB = PROJECT_ROOT / "db" / "app.db"
DEFAULT_CONFIG = PROJECT_ROOT / "config" / "kaspi_column_map.yaml"
EXPORT_PATH = PROJECT_ROOT / "exports" / "orders_to_cashflow_report.txt"

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


def _parse_date(value: str | None) -> str | None:
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(value)
        return dt.date().isoformat()
    except Exception:
        try:
            return date.fromisoformat(value[:10]).isoformat()
        except Exception:
            return None


def _load_dim_sku_weights(conn: sqlite3.Connection) -> dict[str, float]:
    if not _table_exists(conn, "dim_sku"):
        return {}
    rows = conn.execute("SELECT sku_key, weight_kg FROM dim_sku").fetchall()
    return {row[0]: float(row[1] or 0.0) for row in rows}


def _load_existing_sales(conn: sqlite3.Connection) -> set[str]:
    if not _table_exists(conn, "fact_cashflow_events"):
        return set()
    rows = conn.execute(
        """
        SELECT DISTINCT ref_id
        FROM fact_cashflow_events
        WHERE ref_type = 'ORDER'
          AND event_type = 'SALE_ACCRUED'
        """
    ).fetchall()
    return {row[0] for row in rows if row[0]}


def translate_orders(db_path: Path, since: date, until: date, apply: bool, run_id: str) -> int:
    if not db_path.exists():
        raise FileNotFoundError(f"DB not found: {db_path}")

    report_lines = []
    with sqlite3.connect(str(db_path)) as conn:
        conn.row_factory = sqlite3.Row
        if not _table_exists(conn, "fact_orders_kaspi"):
            raise RuntimeError("fact_orders_kaspi missing")
        if not _table_exists(conn, "fact_cashflow_events"):
            raise RuntimeError("fact_cashflow_events missing; run migrate_018_cashflow_calendar.py")

        config = {}
        if DEFAULT_CONFIG.exists():
            config = yaml.safe_load(DEFAULT_CONFIG.read_text(encoding="utf-8")) or {}

        weights = _load_dim_sku_weights(conn)
        existing_sales = _load_existing_sales(conn)

        rows = conn.execute(
            """
            SELECT *
            FROM fact_orders_kaspi
            WHERE date(COALESCE(status_updated_at, actual_shipment_date, planned_shipment_date, created_at))
                  BETWEEN ? AND ?
            """,
            (since.isoformat(), until.isoformat()),
        ).fetchall()

        payout_model = load_payout_model()
        events = []
        counts = {"completed": 0, "cancelled": 0, "on_delivery": 0, "ignored": 0}

        for row in rows:
            status = normalize_order_status(row["internal_status"], row["kaspi_status"], config)
            event_date = (
                _parse_date(row["status_updated_at"])
                or _parse_date(row["actual_shipment_date"])
                or _parse_date(row["planned_shipment_date"])
                or _parse_date(row["created_at"])
            )
            if not event_date:
                counts["ignored"] += 1
                continue

            qty = float(row["quantity"] or 0.0)
            if qty <= 0:
                counts["ignored"] += 1
                continue

            sell_price = float(row["unit_price_kzt"] or 0.0)
            sku_key = row["sku_key"]
            weight = weights.get(sku_key or "", 0.0)
            vat_rate = get_vat_rate(date.fromisoformat(event_date))
            delivery_fee = calc_delivery_fee(sell_price, weight_kg=weight, delivery_type="city")
            net_rev_unit = calc_net_rev(
                sell_price,
                delivery_fee=delivery_fee,
                weight_kg=weight,
                as_of_date=date.fromisoformat(event_date),
            )
            net_rev_line = round(net_rev_unit * qty, 2)
            delivery_fee_line = round(delivery_fee * (1 - vat_rate) * qty, 2)

            base_fields = {
                "store_code": row["store_code"],
                "sku_key": row["sku_key"],
                "sku_id": row["sku_id"],
                "ref_type": "ORDER",
                "ref_id": row["order_id"],
                "source": "ORDER_MODELLED",
                "run_id": run_id,
            }

            if status == "COMPLETED":
                counts["completed"] += 1
                events.append(
                    {
                        "event_date": event_date,
                        "event_type": "SALE_ACCRUED",
                        "account": "RECEIVABLES",
                        "amount_kzt": net_rev_line,
                        **base_fields,
                    }
                )
                payout_date = date.fromisoformat(event_date) + timedelta(days=payout_model.base_lag_days)
                events.append(
                    {
                        "event_date": payout_date.isoformat(),
                        "event_type": "PAYOUT_EXPECTED",
                        "account": "CASH",
                        "amount_kzt": net_rev_line,
                        **base_fields,
                    }
                )
                events.append(
                    {
                        "event_date": payout_date.isoformat(),
                        "event_type": "PAYOUT_EXPECTED",
                        "account": "RECEIVABLES",
                        "amount_kzt": -abs(net_rev_line),
                        **base_fields,
                    }
                )
            elif status == "CANCELLED":
                # Only reverse if we previously accrued this order
                if row["order_id"] not in existing_sales:
                    counts["ignored"] += 1
                    continue
                counts["cancelled"] += 1
                events.append(
                    {
                        "event_date": event_date,
                        "event_type": "REFUND",
                        "account": "RECEIVABLES",
                        "amount_kzt": -abs(net_rev_line),
                        **base_fields,
                    }
                )
            elif status == "ON_DELIVERY":
                counts["on_delivery"] += 1
            else:
                counts["ignored"] += 1
                continue
                events.append(
                    {
                        "event_date": event_date,
                        "event_type": "DELIVERY_FEES",
                        "account": "RECEIVABLES",
                        "amount_kzt": -abs(delivery_fee_line),
                        **base_fields,
                        "notes": "Delivery fee not refunded",
                    }
                )
                # Reverse expected payout if previously scheduled
                events.append(
                    {
                        "event_date": event_date,
                        "event_type": "PAYOUT_EXPECTED",
                        "account": "CASH",
                        "amount_kzt": -abs(net_rev_line),
                        **base_fields,
                    }
                )
                events.append(
                    {
                        "event_date": event_date,
                        "event_type": "PAYOUT_EXPECTED",
                        "account": "RECEIVABLES",
                        "amount_kzt": abs(net_rev_line),
                        **base_fields,
                    }
                )
            else:
                counts["ignored"] += 1
                continue

        new_events = []
        if events:
            for event in events:
                event["event_hash"] = _event_hash(event)
            existing_hashes = {
                row[0]
                for row in conn.execute(
                    "SELECT event_hash FROM fact_cashflow_events WHERE event_hash IN ({})".format(
                        ",".join("?" * len(events))
                    ),
                    [e["event_hash"] for e in events],
                ).fetchall()
            }
            new_events = [e for e in events if e["event_hash"] not in existing_hashes]

        report_lines.append(f"Orders scanned: {len(rows)}")
        report_lines.append(f"Completed orders: {counts['completed']}")
        report_lines.append(f"Cancelled/returned orders: {counts['cancelled']}")
        report_lines.append(f"On-delivery orders: {counts['on_delivery']}")
        report_lines.append(f"Ignored orders: {counts['ignored']}")
        report_lines.append(f"New cashflow events: {len(new_events)}")

        if apply:
            if os.environ.get("ENABLE_CASHFLOW_WRITE") != "1":
                raise RuntimeError("ENABLE_CASHFLOW_WRITE=1 is required to apply cashflow writes.")
            for event in new_events:
                conn.execute(
                    """
                    INSERT OR IGNORE INTO fact_cashflow_events (
                        event_date, event_type, account, amount_kzt, store_code, sku_key, sku_id,
                        ref_type, ref_id, notes, source, run_id, event_hash
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        event["event_date"],
                        event["event_type"],
                        event["account"],
                        float(event["amount_kzt"]),
                        event.get("store_code"),
                        event.get("sku_key"),
                        event.get("sku_id"),
                        event.get("ref_type"),
                        event.get("ref_id"),
                        event.get("notes"),
                        event.get("source"),
                        event.get("run_id"),
                        event.get("event_hash"),
                    ),
                )
            conn.commit()

    EXPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    EXPORT_PATH.write_text("\n".join(report_lines) + "\n")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Translate Kaspi orders into cashflow events")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB, help="Path to SQLite DB")
    parser.add_argument("--since", type=str, default=None, help="Start date (YYYY-MM-DD)")
    parser.add_argument("--until", type=str, default=None, help="End date (YYYY-MM-DD)")
    parser.add_argument("--apply", action="store_true", help="Apply writes (requires ENABLE_CASHFLOW_WRITE=1)")
    parser.add_argument("--run-id", type=str, default=None, help="Run id for audit")
    args = parser.parse_args()

    cutoff = get_cutoff_date_almaty()
    since = date.fromisoformat(args.since) if args.since else cutoff - timedelta(days=30)
    until = date.fromisoformat(args.until) if args.until else cutoff
    run_id = args.run_id or datetime.now().strftime("%Y%m%d_%H%M%S")

    if since > until:
        raise ValueError("--since must be <= --until")

    return translate_orders(args.db, since, until, args.apply, run_id)


if __name__ == "__main__":
    raise SystemExit(main())
