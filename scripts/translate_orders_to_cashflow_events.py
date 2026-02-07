#!/usr/bin/env python3
"""
Translate Kaspi order lifecycle into cashflow events (cash-in at delivered + inventory moves).

Default: DRY RUN. Apply requires ENABLE_CASHFLOW_WRITE=1 and --apply.
"""
from __future__ import annotations

import argparse
import hashlib
import json
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
from core.integrations.kaspi_order_stage import (
    StageCode,
    api_state_filter_for_stage,
    classify_kaspi_stage_from_db_row,
    stage_to_internal_status,
)

DEFAULT_DB = PROJECT_ROOT / "db" / "app.db"
DEFAULT_CONFIG = PROJECT_ROOT / "config" / "kaspi_column_map.yaml"
EXPORT_PATH = PROJECT_ROOT / "exports" / "orders_to_cashflow_report.txt"
_DELIVERY_STATE = api_state_filter_for_stage(StageCode.ACCEPTED_PENDING_ASSEMBLY) or ""

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


def _load_order_entries(conn: sqlite3.Connection) -> dict[tuple[str, str], list[dict]]:
    if not _table_exists(conn, "fact_order_entries_kaspi"):
        return {}
    if not _table_exists(conn, "dim_kaspi_article_map"):
        return {}
    map_rows = conn.execute(
        """
        SELECT store_code, kaspi_article, kaspi_offer_name, sku_key, sku_id
        FROM dim_kaspi_article_map
        WHERE sku_key IS NOT NULL
          AND trim(sku_key) <> ''
          AND sku_id IS NOT NULL
          AND trim(sku_id) <> ''
        """
    ).fetchall()

    article_map: dict[tuple[str, str], tuple[str, str]] = {}
    name_map: dict[tuple[str, str], tuple[str, str]] = {}
    ambiguous_article: set[tuple[str, str]] = set()
    ambiguous_name: set[tuple[str, str]] = set()
    for row in map_rows:
        store = str(row["store_code"] or "").strip()
        article = str(row["kaspi_article"] or "").strip()
        offer_name = str(row["kaspi_offer_name"] or "").strip()
        value = (str(row["sku_key"]), str(row["sku_id"]))
        if store and article:
            key = (store, article)
            if key in ambiguous_article:
                pass
            elif key in article_map and article_map[key] != value:
                ambiguous_article.add(key)
                article_map.pop(key, None)
            else:
                article_map[key] = value
        if store and offer_name:
            key = (store, offer_name)
            if key in ambiguous_name:
                pass
            elif key in name_map and name_map[key] != value:
                ambiguous_name.add(key)
                name_map.pop(key, None)
            else:
                name_map[key] = value

    rows = conn.execute(
        """
        SELECT
            order_id,
            store_code,
            offer_id,
            quantity,
            unit_price_kzt,
            total_price_kzt,
            raw_json
        FROM fact_order_entries_kaspi
        """
    ).fetchall()

    def _offer_candidates(offer_id: str | None) -> list[str]:
        raw = str(offer_id or "").strip()
        if not raw:
            return []
        candidates = [raw]
        if "\t" in raw:
            candidates.extend(part.strip() for part in raw.split("\t") if part.strip())
        if " " in raw:
            candidates.extend(part.strip() for part in raw.split(" ") if part.strip())
        for marker in ("CL_", "ELS_"):
            idx = raw.find(marker)
            if idx > 0:
                candidates.append(raw[idx:].strip())
        out = []
        seen = set()
        for item in candidates:
            if item and item not in seen:
                out.append(item)
                seen.add(item)
        return out

    def _offer_name_from_raw(raw_json: str | None) -> str | None:
        if not raw_json:
            return None
        try:
            payload = json.loads(raw_json)
        except Exception:
            return None
        attrs = payload.get("attributes") or {}
        offer = attrs.get("offer") or {}
        name = str(offer.get("name") or "").strip()
        return name or None

    entries_by_order: dict[tuple[str, str], list[dict]] = {}
    for row in rows:
        order_id = str(row["order_id"]) if row["order_id"] is not None else ""
        store_code = str(row["store_code"]) if row["store_code"] is not None else ""
        if not order_id or not store_code:
            continue
        sku_key = None
        sku_id = None
        for candidate in _offer_candidates(row["offer_id"]):
            mapped = article_map.get((store_code, candidate))
            if mapped:
                sku_key, sku_id = mapped
                break
        if (not sku_key or not sku_id) and row["raw_json"]:
            offer_name = _offer_name_from_raw(row["raw_json"])
            if offer_name:
                mapped = name_map.get((store_code, offer_name))
                if mapped:
                    sku_key, sku_id = mapped
        entries_by_order.setdefault((order_id, store_code), []).append(
            {
                "sku_key": sku_key,
                "sku_id": sku_id,
                "quantity": float(row["quantity"] or 0.0),
                "unit_price_kzt": row["unit_price_kzt"],
                "total_price_kzt": row["total_price_kzt"],
            }
        )
    return entries_by_order


def _load_sales_fact_fallback(conn: sqlite3.Connection) -> dict[tuple[str, str], list[dict]]:
    if not _table_exists(conn, "sales_fact_v2"):
        return {}
    rows = conn.execute(
        """
        SELECT order_id, store_code, sku_key, sku_id, quantity, sell_price_kzt
        FROM sales_fact_v2
        WHERE order_id IS NOT NULL
          AND trim(order_id) <> ''
          AND store_code IS NOT NULL
          AND trim(store_code) <> ''
          AND sku_key IS NOT NULL
          AND trim(sku_key) <> ''
          AND sku_id IS NOT NULL
          AND trim(sku_id) <> ''
        """
    ).fetchall()
    lines_by_order: dict[tuple[str, str], list[dict]] = {}
    for row in rows:
        order_id = str(row["order_id"]).strip()
        store_code = str(row["store_code"]).strip()
        lines_by_order.setdefault((order_id, store_code), []).append(
            {
                "sku_key": str(row["sku_key"]).strip(),
                "sku_id": str(row["sku_id"]).strip(),
                "quantity": float(row["quantity"] or 0.0),
                "unit_price_kzt": row["sell_price_kzt"],
                "total_price_kzt": None,
            }
        )
    return lines_by_order


def _unit_cost_kzt_for_sku(sku_key: str | None, fx_rates, dim_costs: dict[str, dict]) -> float:
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


def _unit_cost_kzt(row: sqlite3.Row, fx_rates, dim_costs: dict[str, dict]) -> float:
    return _unit_cost_kzt_for_sku(row["sku_key"], fx_rates, dim_costs)


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
          AND ABS(amount_kzt) > 0
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
          AND ABS(amount_kzt) > 0
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
          AND ABS(amount_kzt) > 0
        GROUP BY ref_id, sku_id
        """
    ).fetchall()
    return {
        (str(row[0]), str(row[1]) if row[1] is not None else ""): row[2]
        for row in rows
        if row[0] is not None and row[2] is not None
    }


def _load_on_delivery_balances(conn: sqlite3.Connection) -> dict[tuple[str, str], float]:
    if not _table_exists(conn, "fact_cashflow_events"):
        return {}
    rows = conn.execute(
        """
        SELECT ref_id, sku_id, SUM(amount_kzt) AS balance_kzt
        FROM fact_cashflow_events
        WHERE ref_type = 'ORDER'
          AND account = 'INVENTORY_ON_DELIVERY_COST'
          AND ABS(amount_kzt) > 0
        GROUP BY ref_id, sku_id
        """
    ).fetchall()
    return {
        (str(row[0]), str(row[1]) if row[1] is not None else ""): float(row[2] or 0.0)
        for row in rows
        if row[0] is not None
    }


def _has_existing(existing: set[tuple[str, str]], order_id: str, order_sku_id: str) -> bool:
    if (order_id, order_sku_id) in existing:
        return True
    return (order_id, "") in existing


def _get_existing_date(
    existing: dict[tuple[str, str], str], order_id: str, order_sku_id: str
) -> str | None:
    return existing.get((order_id, order_sku_id)) or existing.get((order_id, ""))


def _get_existing_balance(
    balances: dict[tuple[str, str], float], order_id: str, order_sku_id: str
) -> float:
    return float(balances.get((order_id, order_sku_id), balances.get((order_id, ""), 0.0)) or 0.0)


def _apply_balance_delta(
    balances: dict[tuple[str, str], float], order_id: str, order_sku_id: str, delta: float
) -> None:
    key = (order_id, order_sku_id)
    fallback = (order_id, "")
    target = key if key in balances or fallback not in balances else fallback
    balances[target] = float(balances.get(target, 0.0)) + float(delta)


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
        entries_by_order = _load_order_entries(conn)
        sales_fact_fallback = _load_sales_fact_fallback(conn)
        existing_cash = _load_existing_cash_in(conn)
        existing_refunds = _load_existing_refunds(conn)
        existing_on_delivery = _load_existing_on_delivery(conn)
        existing_cogs_dates = _load_existing_cogs_dates(conn)
        existing_move_dates = _load_existing_move_dates(conn)
        on_delivery_balances = _load_on_delivery_balances(conn)
        existing_cash_order_ids = {order_id for order_id, _ in existing_cash}
        existing_refund_order_ids = {order_id for order_id, _ in existing_refunds}
        existing_cogs_order_ids = {order_id for order_id, _ in existing_cogs_dates}
        existing_on_delivery_order_ids = {order_id for order_id, _ in existing_on_delivery}
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
        # Some orders have duplicate history rows where one row already has SKU identity,
        # but the resolved sibling can be outside this date window.
        # Build resolved keys from the whole table and use them only as a missing-SKU guard.
        resolved_order_keys = {
            (str(r[0]), str(r[1]))
            for r in conn.execute(
                """
                SELECT DISTINCT order_id, store_code
                FROM fact_orders_kaspi
                WHERE order_id IS NOT NULL
                  AND store_code IS NOT NULL
                  AND sku_key IS NOT NULL
                  AND trim(sku_key) <> ''
                  AND sku_id IS NOT NULL
                  AND trim(sku_id) <> ''
                """
            ).fetchall()
        }
        resolved_order_ids = {order_id for order_id, _ in resolved_order_keys}
        resolved_order_ids_from_entries = {
            order_id
            for (order_id, _store), lines in entries_by_order.items()
            if any(line.get("sku_key") and line.get("sku_id") for line in lines)
        }
        resolved_order_ids_from_sales = {
            order_id
            for (order_id, _store), lines in sales_fact_fallback.items()
            if any(line.get("sku_key") and line.get("sku_id") for line in lines)
        }
        # Some legacy CRM exports persist as UNKNOWN-store shadow rows, even when a
        # resolved non-UNKNOWN row exists for the same order/SKU outside the active window.
        # Skip those shadows to avoid duplicate COGS/backfill events.
        non_unknown_row_tokens: set[tuple[str, str]] = set()
        for row_order_id, row_sku_id, row_sku_key in conn.execute(
            """
            SELECT order_id, sku_id, sku_key
            FROM fact_orders_kaspi
            WHERE order_id IS NOT NULL
              AND trim(order_id) <> ''
              AND store_code IS NOT NULL
              AND UPPER(trim(store_code)) <> 'UNKNOWN'
              AND (
                    (sku_id IS NOT NULL AND trim(sku_id) <> '')
                 OR (sku_key IS NOT NULL AND trim(sku_key) <> '')
              )
            """
        ).fetchall():
            oid = str(row_order_id).strip()
            sid = str(row_sku_id or "").strip()
            skey = str(row_sku_key or "").strip()
            if sid:
                non_unknown_row_tokens.add((oid, sid))
            if skey:
                non_unknown_row_tokens.add((oid, skey))
        non_unknown_order_ids = {order_id for order_id, _ in non_unknown_row_tokens}
        resolved_completed_rows_by_key: dict[tuple[str, str], dict[str, str]] = {}
        for row_order_id, row_store_code, row_sku_key, row_sku_id in conn.execute(
            """
            SELECT order_id, store_code, sku_key, sku_id
            FROM fact_orders_kaspi
            WHERE order_id IS NOT NULL
              AND trim(order_id) <> ''
              AND store_code IS NOT NULL
              AND UPPER(trim(store_code)) <> 'UNKNOWN'
              AND internal_status = 'COMPLETED'
              AND sku_key IS NOT NULL
              AND trim(sku_key) <> ''
              AND sku_id IS NOT NULL
              AND trim(sku_id) <> ''
            """
        ).fetchall():
            key = (str(row_order_id), str(row_sku_id))
            resolved_completed_rows_by_key.setdefault(
                key,
                {
                    "order_id": str(row_order_id),
                    "store_code": str(row_store_code),
                    "sku_key": str(row_sku_key),
                    "sku_id": str(row_sku_id),
                },
            )

        events = []
        missing_sku = []
        missing_cost = []
        counts = {"completed": 0, "cancelled": 0, "on_delivery": 0, "ignored": 0}

        # Global corrective pass: if completed orders already have cash/cogs but their
        # INVENTORY_ON_DELIVERY_COST balance is non-zero, add a balancing COGS entry.
        # Restrict corrections to cogs dates inside the requested window.
        for (order_id, order_sku_id), row_meta in resolved_completed_rows_by_key.items():
            if not _has_existing(existing_cash, order_id, order_sku_id):
                continue
            cogs_date = _get_existing_date(existing_cogs_dates, order_id, order_sku_id)
            if not cogs_date:
                continue
            try:
                cogs_date_obj = date.fromisoformat(str(cogs_date))
            except ValueError:
                continue
            if cogs_date_obj < since or cogs_date_obj > until:
                continue
            imbalance = _get_existing_balance(on_delivery_balances, order_id, order_sku_id)
            if abs(imbalance) <= 0.01:
                continue
            correction = round(-imbalance, 2)
            events.append(
                {
                    "event_date": cogs_date_obj.isoformat(),
                    "event_type": "COGS_RECOGNIZED",
                    "account": "INVENTORY_ON_DELIVERY_COST",
                    "amount_kzt": correction,
                    "store_code": row_meta["store_code"],
                    "sku_key": row_meta["sku_key"],
                    "sku_id": row_meta["sku_id"],
                    "ref_type": "ORDER",
                    "ref_id": row_meta["order_id"],
                    "source": "ORDER_MODELLED",
                    "run_id": run_id,
                    "notes": "Backfill on-delivery balance correction",
                }
            )
            _apply_balance_delta(on_delivery_balances, order_id, order_sku_id, correction)

        for row in rows:
            stage = classify_kaspi_stage_from_db_row(row)
            status = normalize_order_status(stage_to_internal_status(stage), row["kaspi_status"], config)
            event_date = (
                _parse_date(row["status_updated_at"])
                or _parse_date(row["actual_shipment_date"])
                or _parse_date(row["planned_shipment_date"])
                or _parse_date(row["created_at"])
            )
            if not event_date:
                counts["ignored"] += 1
                continue
            if status not in {"COMPLETED", "CANCELLED", "RETURNED", "ON_DELIVERY"}:
                counts["ignored"] += 1
                continue
            order_id = str(row["order_id"]) if row["order_id"] is not None else ""
            store_code = row["store_code"]
            store_code_norm = str(store_code or "").strip().upper()
            row_sku_id = str(row["sku_id"] or "").strip()
            row_sku_key = str(row["sku_key"] or "").strip()
            if store_code_norm == "UNKNOWN":
                if (
                    (row_sku_id and (order_id, row_sku_id) in non_unknown_row_tokens)
                    or (row_sku_key and (order_id, row_sku_key) in non_unknown_row_tokens)
                    or (not row_sku_id and not row_sku_key and order_id in non_unknown_order_ids)
                ):
                    counts["ignored"] += 1
                    continue
            raw_kaspi_status = str(row["kaspi_status"] or "").strip().upper()
            # Guard against premature stage inflation from API fields:
            # if DB still marks order as ACCEPTED/READY, do not model on-delivery moves yet.
            raw_internal_status = str(row["internal_status"] or "").strip().upper()
            if status == "ON_DELIVERY" and raw_internal_status in {"NEW", "ACCEPTED", "READY"}:
                counts["ignored"] += 1
                continue
            if status == "ON_DELIVERY" and raw_kaspi_status == _DELIVERY_STATE:
                counts["ignored"] += 1
                continue
            order_lines = []
            if row["sku_key"] and row["sku_id"]:
                order_lines.append(
                    {
                        "sku_key": row["sku_key"],
                        "sku_id": row["sku_id"],
                        "quantity": float(row["quantity"] or 0.0),
                        "unit_price_kzt": row["unit_price_kzt"],
                        "total_price_kzt": None,
                    }
                )
            else:
                order_lines = entries_by_order.get((order_id, str(store_code)), [])
                if not order_lines:
                    order_lines = sales_fact_fallback.get((order_id, str(store_code)), [])
                if not order_lines:
                    if (order_id, str(store_code)) in resolved_order_keys:
                        counts["ignored"] += 1
                        continue
                    if order_id in resolved_order_ids:
                        counts["ignored"] += 1
                        continue
                    if order_id in resolved_order_ids_from_entries:
                        counts["ignored"] += 1
                        continue
                    if order_id in resolved_order_ids_from_sales:
                        counts["ignored"] += 1
                        continue
                    if status in {"COMPLETED", "ON_DELIVERY"}:
                        if order_id in existing_cash_order_ids and order_id in existing_cogs_order_ids:
                            counts["ignored"] += 1
                            continue
                    if status in {"CANCELLED", "RETURNED"}:
                        if order_id in existing_refund_order_ids:
                            counts["ignored"] += 1
                            continue
                        if (
                            order_id not in existing_cash_order_ids
                            and order_id not in existing_on_delivery_order_ids
                            and order_id not in existing_cogs_order_ids
                        ):
                            counts["ignored"] += 1
                            continue
                    missing_sku.append(f"{order_id}:{store_code}")
                    counts["ignored"] += 1
                    continue

            for line in order_lines:
                qty = float(line.get("quantity") or 0.0)
                if qty <= 0:
                    counts["ignored"] += 1
                    continue

                sku_key = line.get("sku_key")
                sku_id = line.get("sku_id")
                if not sku_key or not sku_id:
                    if (order_id, str(store_code)) in resolved_order_keys:
                        counts["ignored"] += 1
                        continue
                    if order_id in resolved_order_ids:
                        counts["ignored"] += 1
                        continue
                    if order_id in resolved_order_ids_from_entries:
                        counts["ignored"] += 1
                        continue
                    if order_id in resolved_order_ids_from_sales:
                        counts["ignored"] += 1
                        continue
                    if status in {"COMPLETED", "ON_DELIVERY"}:
                        if order_id in existing_cash_order_ids and order_id in existing_cogs_order_ids:
                            counts["ignored"] += 1
                            continue
                    if status in {"CANCELLED", "RETURNED"}:
                        if order_id in existing_refund_order_ids:
                            counts["ignored"] += 1
                            continue
                        if (
                            order_id not in existing_cash_order_ids
                            and order_id not in existing_on_delivery_order_ids
                            and order_id not in existing_cogs_order_ids
                        ):
                            counts["ignored"] += 1
                            continue
                    missing_sku.append(f"{order_id}:{store_code}")
                    counts["ignored"] += 1
                    continue

                sell_price = line.get("unit_price_kzt")
                if not sell_price and line.get("total_price_kzt") and qty > 0:
                    sell_price = float(line.get("total_price_kzt") or 0.0) / qty
                sell_price = float(sell_price or 0.0)

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
                unit_cost = _unit_cost_kzt_for_sku(sku_key, fx_rates, dim_costs)
                if unit_cost <= 0:
                    missing_cost.append(f"{order_id}:{sku_key}")
                    counts["ignored"] += 1
                    continue
                cost_line = round(unit_cost * qty, 2)

                order_sku_id = str(sku_id)
                order_key = (order_id, order_sku_id)
                base_fields = {
                    "store_code": store_code,
                    "sku_key": sku_key,
                    "sku_id": order_sku_id,
                    "ref_type": "ORDER",
                    "ref_id": order_id,
                    "source": "ORDER_MODELLED",
                    "run_id": run_id,
                }

                if status == "COMPLETED":
                    if _has_existing(existing_cash, order_id, order_sku_id):
                        # Legacy rows may have cash recorded but only zero-cost inventory events.
                        # Backfill missing non-zero COGS while preserving cash idempotency.
                        cogs_date = _get_existing_date(existing_cogs_dates, order_id, order_sku_id)
                        if not cogs_date:
                            move_date = _get_existing_date(existing_move_dates, order_id, order_sku_id)
                            cogs_date = move_date or event_date
                            if not _has_existing(existing_on_delivery, order_id, order_sku_id):
                                events.append(
                                    {
                                        "event_date": cogs_date,
                                        "event_type": "INVENTORY_MOVE",
                                        "account": "INVENTORY_ON_HAND_COST",
                                        "amount_kzt": -abs(cost_line),
                                        **base_fields,
                                        "notes": "Backfill on-delivery at completion",
                                    }
                                )
                                events.append(
                                    {
                                        "event_date": cogs_date,
                                        "event_type": "INVENTORY_MOVE",
                                        "account": "INVENTORY_ON_DELIVERY_COST",
                                        "amount_kzt": abs(cost_line),
                                        **base_fields,
                                        "notes": "Backfill on-delivery at completion",
                                    }
                                )
                                _apply_balance_delta(on_delivery_balances, order_id, order_sku_id, abs(cost_line))
                                existing_on_delivery.add(order_key)
                            events.append(
                                {
                                    "event_date": cogs_date,
                                    "event_type": "COGS_RECOGNIZED",
                                    "account": "INVENTORY_ON_DELIVERY_COST",
                                    "amount_kzt": -abs(cost_line),
                                    **base_fields,
                                    "notes": "Backfill missing COGS",
                                }
                            )
                            _apply_balance_delta(on_delivery_balances, order_id, order_sku_id, -abs(cost_line))
                            existing_cogs_dates[order_key] = cogs_date
                            counts["completed"] += 1
                            continue

                        # Cash/COGS already recorded; only backfill on-delivery if missing.
                        if not _has_existing(existing_on_delivery, order_id, order_sku_id):
                            backfill_date = cogs_date or event_date
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
                            _apply_balance_delta(on_delivery_balances, order_id, order_sku_id, abs(cost_line))
                            existing_on_delivery.add(order_key)
                        else:
                            move_date = _get_existing_date(existing_move_dates, order_id, order_sku_id)
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
                                _apply_balance_delta(on_delivery_balances, order_id, order_sku_id, abs(cost_line))
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
                                _apply_balance_delta(on_delivery_balances, order_id, order_sku_id, -abs(cost_line))
                        imbalance = _get_existing_balance(on_delivery_balances, order_id, order_sku_id)
                        if abs(imbalance) > 0.01:
                            correction = round(-imbalance, 2)
                            events.append(
                                {
                                    "event_date": cogs_date or event_date,
                                    "event_type": "COGS_RECOGNIZED",
                                    "account": "INVENTORY_ON_DELIVERY_COST",
                                    "amount_kzt": correction,
                                    **base_fields,
                                    "notes": "Backfill on-delivery balance correction",
                                }
                            )
                            _apply_balance_delta(on_delivery_balances, order_id, order_sku_id, correction)
                        counts["ignored"] += 1
                        continue
                    counts["completed"] += 1
                    if not _has_existing(existing_on_delivery, order_id, order_sku_id):
                        backfill_date = _get_existing_date(existing_cogs_dates, order_id, order_sku_id) or event_date
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
                            "account": _cash_account(store_code),
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
                    existing_cogs_dates[order_key] = event_date
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
                            "account": _cash_account(store_code),
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

        if missing_sku or missing_cost:
            messages = []
            if missing_sku:
                sample = ", ".join(missing_sku[:5])
                messages.append(
                    "Missing SKU resolution for "
                    f"{len(missing_sku)} order lines (sample: {sample}). "
                    "Run order enrichment to populate fact_order_entries_kaspi "
                    "and ensure dim_kaspi_article_map covers offer_id."
                )
            if missing_cost:
                sample = ", ".join(missing_cost[:5])
                messages.append(
                    "Missing unit cost for "
                    f"{len(missing_cost)} order lines (sample: {sample}). "
                    "Ensure dim_sku has base_cost_cny or cogs_kzt (or weight for calc_cogs)."
                )
            raise RuntimeError(" ".join(messages))

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
