#!/usr/bin/env python3
"""
Translate Kaspi order lifecycle into cashflow events (cash-in at delivered + inventory moves).

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
from core.cashflow.order_status import normalize_order_status
from core.config.business_params import get_vat_rate, get_fx_rates
from core.calc.economics import calc_delivery_fee, calc_net_rev, calc_cogs

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


def _unit_cost_kzt(row: sqlite3.Row, fx_rates, dim_costs: dict[str, dict]) -> float:
    sku_key = row["sku_key"]
    meta = dim_costs.get(sku_key or "", {})
    base_cost = meta.get("base_cost_cny", 0.0)
    if base_cost and base_cost > 0:
        return float(base_cost) * float(fx_rates.cny_kzt)
    cogs_unit = meta.get("cogs_kzt") or 0.0
    if cogs_unit > 0:
        return float(cogs_unit)
    weight = meta.get("weight_kg", 0.0)
    return float(
        calc_cogs(
            base_cost,
            weight,
            cny_kzt=fx_rates.cny_kzt,
            volumetric_factor=fx_rates.dlv_rate_usd_kg,
            freight_rate=fx_rates.usd_kzt,
        )
    )


def _cash_account(store_code: str | None) -> str:
    if not store_code:
        return "KASPI_PAY_UNKNOWN"
    return f"KASPI_PAY_{store_code}"


def _load_existing_cash_in(conn: sqlite3.Connection) -> set[tuple[str, str]]:
    if not _table_exists(conn, "fact_cashflow_events"):
        return set()
    rows = conn.execute(
        """
        SELECT DISTINCT ref_id, sku_id
        FROM fact_cashflow_events
        WHERE ref_type = 'ORDER'
          AND event_type = 'CASH_IN'
        """
    ).fetchall()
    return {
        (str(row[0]), str(row[1]) if row[1] is not None else "")
        for row in rows
        if row[0] is not None
    }


def _load_existing_refunds(conn: sqlite3.Connection) -> set[tuple[str, str]]:
    if not _table_exists(conn, "fact_cashflow_events"):
        return set()
    rows = conn.execute(
        """
        SELECT DISTINCT ref_id, sku_id
        FROM fact_cashflow_events
        WHERE ref_type = 'ORDER'
          AND event_type = 'CASH_IN'
          AND amount_kzt < 0
        """
    ).fetchall()
    return {
        (str(row[0]), str(row[1]) if row[1] is not None else "")
        for row in rows
        if row[0] is not None
    }


def _load_existing_on_delivery(conn: sqlite3.Connection) -> set[tuple[str, str]]:
    if not _table_exists(conn, "fact_cashflow_events"):
        return set()
    rows = conn.execute(
        """
        SELECT DISTINCT ref_id, sku_id
        FROM fact_cashflow_events
        WHERE ref_type = 'ORDER'
          AND event_type = 'INVENTORY_MOVE'
          AND account = 'INVENTORY_ON_DELIVERY_COST'
        """
    ).fetchall()
    return {
        (str(row[0]), str(row[1]) if row[1] is not None else "")
        for row in rows
        if row[0] is not None
    }


def _load_existing_cogs_dates(conn: sqlite3.Connection) -> dict[tuple[str, str], str]:
    if not _table_exists(conn, "fact_cashflow_events"):
        return {}
    rows = conn.execute(
        """
        SELECT ref_id, sku_id, MIN(date(event_date)) as cogs_date
        FROM fact_cashflow_events
        WHERE ref_type = 'ORDER'
          AND event_type = 'COGS_RECOGNIZED'
        GROUP BY ref_id, sku_id
        """
    ).fetchall()
    return {
        (str(row[0]), str(row[1]) if row[1] is not None else ""): row[2]
        for row in rows
        if row[0] is not None and row[2] is not None
    }


def _load_existing_move_dates(conn: sqlite3.Connection) -> dict[tuple[str, str], str]:
    if not _table_exists(conn, "fact_cashflow_events"):
        return {}
    rows = conn.execute(
        """
        SELECT ref_id, sku_id, MIN(date(event_date)) as move_date
        FROM fact_cashflow_events
        WHERE ref_type = 'ORDER'
          AND event_type = 'INVENTORY_MOVE'
          AND account = 'INVENTORY_ON_DELIVERY_COST'
        GROUP BY ref_id, sku_id
        """
    ).fetchall()
    return {
        (str(row[0]), str(row[1]) if row[1] is not None else ""): row[2]
        for row in rows
        if row[0] is not None and row[2] is not None
    }


def _has_existing(existing: set[tuple[str, str]], order_id: str, order_sku_id: str) -> bool:
    if (order_id, order_sku_id) in existing:
        return True
    return (order_id, "") in existing


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
        dim_costs = _load_dim_sku_costs(conn)
        existing_cash = _load_existing_cash_in(conn)
        existing_refunds = _load_existing_refunds(conn)
        existing_on_delivery = _load_existing_on_delivery(conn)
        existing_cogs_dates = _load_existing_cogs_dates(conn)
        existing_move_dates = _load_existing_move_dates(conn)
        fx_rates = get_fx_rates(until.isoformat(), db_path=db_path)

        rows = conn.execute(
            """
            SELECT *
            FROM fact_orders_kaspi
            WHERE date(COALESCE(status_updated_at, actual_shipment_date, planned_shipment_date, created_at))
                  BETWEEN ? AND ?
            """,
            (since.isoformat(), until.isoformat()),
        ).fetchall()

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
            delivery_fee_line = round(float(delivery_fee or 0.0) * qty, 2)
            unit_cost = _unit_cost_kzt(row, fx_rates, dim_costs)
            cost_line = round(unit_cost * qty, 2)

            order_id = str(row["order_id"]) if row["order_id"] is not None else ""
            order_sku_id = str(row["sku_id"]) if row["sku_id"] is not None else ""
            order_key = (order_id, order_sku_id)
            base_fields = {
                "store_code": row["store_code"],
                "sku_key": row["sku_key"],
                "sku_id": order_sku_id,
                "ref_type": "ORDER",
                "ref_id": order_id,
                "source": "ORDER_MODELLED",
                "run_id": run_id,
            }

            if status == "COMPLETED":
                if _has_existing(existing_cash, order_id, order_sku_id):
                    # Cash/COGS already recorded; only backfill on-delivery if missing.
                    if not _has_existing(existing_on_delivery, order_id, order_sku_id):
                        backfill_date = existing_cogs_dates.get(order_key) or event_date
                        events.append(
                            {
                                "event_date": backfill_date,
                                "event_type": "INVENTORY_MOVE",
                                "account": "INVENTORY_ON_HAND_COST",
                                "amount_kzt": -abs(cost_line),
                                **base_fields,
                                "notes": "Backfill on-delivery at completion",
                            }
                        )
                        events.append(
                            {
                                "event_date": backfill_date,
                                "event_type": "INVENTORY_MOVE",
                                "account": "INVENTORY_ON_DELIVERY_COST",
                                "amount_kzt": abs(cost_line),
                                **base_fields,
                                "notes": "Backfill on-delivery at completion",
                            }
                        )
                        existing_on_delivery.add(order_key)
                    else:
                        cogs_date = existing_cogs_dates.get(order_key)
                        move_date = existing_move_dates.get(order_key)
                        if cogs_date and move_date and move_date > cogs_date:
                            # Shift on-delivery timing earlier to avoid negative balance on cogs date.
                            events.append(
                                {
                                    "event_date": cogs_date,
                                    "event_type": "INVENTORY_MOVE",
                                    "account": "INVENTORY_ON_HAND_COST",
                                    "amount_kzt": -abs(cost_line),
                                    **base_fields,
                                    "notes": "Timing shift (earlier on-delivery)",
                                }
                            )
                            events.append(
                                {
                                    "event_date": cogs_date,
                                    "event_type": "INVENTORY_MOVE",
                                    "account": "INVENTORY_ON_DELIVERY_COST",
                                    "amount_kzt": abs(cost_line),
                                    **base_fields,
                                    "notes": "Timing shift (earlier on-delivery)",
                                }
                            )
                            events.append(
                                {
                                    "event_date": move_date,
                                    "event_type": "INVENTORY_MOVE",
                                    "account": "INVENTORY_ON_HAND_COST",
                                    "amount_kzt": abs(cost_line),
                                    **base_fields,
                                    "notes": "Timing shift (reverse later move)",
                                }
                            )
                            events.append(
                                {
                                    "event_date": move_date,
                                    "event_type": "INVENTORY_MOVE",
                                    "account": "INVENTORY_ON_DELIVERY_COST",
                                    "amount_kzt": -abs(cost_line),
                                    **base_fields,
                                    "notes": "Timing shift (reverse later move)",
                                }
                            )
                    counts["ignored"] += 1
                    continue
                counts["completed"] += 1
                if not _has_existing(existing_on_delivery, order_id, order_sku_id):
                    backfill_date = existing_cogs_dates.get(order_key) or event_date
                    events.append(
                        {
                            "event_date": backfill_date,
                            "event_type": "INVENTORY_MOVE",
                            "account": "INVENTORY_ON_HAND_COST",
                            "amount_kzt": -abs(cost_line),
                            **base_fields,
                            "notes": "Backfill on-delivery at completion",
                        }
                    )
                    events.append(
                        {
                            "event_date": backfill_date,
                            "event_type": "INVENTORY_MOVE",
                            "account": "INVENTORY_ON_DELIVERY_COST",
                            "amount_kzt": abs(cost_line),
                            **base_fields,
                            "notes": "Backfill on-delivery at completion",
                            }
                        )
                    existing_on_delivery.add(order_key)
                events.append(
                    {
                        "event_date": event_date,
                        "event_type": "CASH_IN",
                        "account": _cash_account(row["store_code"]),
                        "amount_kzt": net_rev_line,
                        **base_fields,
                    }
                )
                events.append(
                    {
                        "event_date": event_date,
                        "event_type": "COGS_RECOGNIZED",
                        "account": "INVENTORY_ON_DELIVERY_COST",
                        "amount_kzt": -abs(cost_line),
                        **base_fields,
                    }
                )
                existing_cash.add(order_key)
            elif status == "CANCELLED":
                # Only reverse if we previously recorded cash for this order
                if not _has_existing(existing_cash, order_id, order_sku_id):
                    counts["ignored"] += 1
                    continue
                if _has_existing(existing_refunds, order_id, order_sku_id):
                    counts["ignored"] += 1
                    continue
                counts["cancelled"] += 1
                refund_cash = -abs(net_rev_line + delivery_fee_line)
                events.append(
                    {
                        "event_date": event_date,
                        "event_type": "CASH_IN",
                        "account": _cash_account(row["store_code"]),
                        "amount_kzt": refund_cash,
                        **base_fields,
                    }
                )
                events.append(
                    {
                        "event_date": event_date,
                        "event_type": "INVENTORY_RETURN",
                        "account": "INVENTORY_ON_HAND_COST",
                        "amount_kzt": abs(cost_line),
                        **base_fields,
                    }
                )
            elif status == "ON_DELIVERY":
                if _has_existing(existing_on_delivery, order_id, order_sku_id):
                    counts["ignored"] += 1
                    continue
                counts["on_delivery"] += 1
                events.append(
                    {
                        "event_date": event_date,
                        "event_type": "INVENTORY_MOVE",
                        "account": "INVENTORY_ON_HAND_COST",
                        "amount_kzt": -abs(cost_line),
                        **base_fields,
                        "notes": "Move to on-delivery",
                    }
                )
                events.append(
                    {
                        "event_date": event_date,
                        "event_type": "INVENTORY_MOVE",
                        "account": "INVENTORY_ON_DELIVERY_COST",
                        "amount_kzt": abs(cost_line),
                        **base_fields,
                        "notes": "On-delivery inventory",
                    }
                )
                existing_on_delivery.add(order_key)
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
