#!/usr/bin/env python3
"""Compute paid-capital truth snapshot from bank balances + inventory + paid PO parts."""

from __future__ import annotations

from datetime import date, datetime
from pathlib import Path
import sqlite3
from typing import Any

import yaml

from core.config.business_params import get_fx_rates
from core.calc.economics import resolve_landed_cogs

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
DEFAULT_DB = PROJECT_ROOT / "db" / "app.db"
DEFAULT_BANK_ACCOUNTS = PROJECT_ROOT / "config" / "bank_accounts.yaml"


def _table_exists(conn: sqlite3.Connection, name: str) -> bool:
    return conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
        (name,),
    ).fetchone() is not None


def _parse_date_maybe(value: Any) -> date | None:
    if value is None:
        return None
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    if isinstance(value, datetime):
        return value.date()
    raw = str(value).replace("GMT+5", "").strip()
    if not raw:
        return None
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d"):
        try:
            return datetime.strptime(raw, fmt).date()
        except ValueError:
            continue
    try:
        return datetime.fromisoformat(raw).date()
    except ValueError:
        return None


def _to_float(value: Any) -> float:
    if value is None:
        return 0.0
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _to_int(value: Any) -> int:
    if value is None:
        return 0
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _load_cash_total_kzt(bank_accounts_path: Path, *, db_path: Path, as_of: date | None) -> tuple[float, dict[str, float], str | None]:
    if not bank_accounts_path.exists():
        return 0.0, {}, None
    config = yaml.safe_load(bank_accounts_path.read_text(encoding="utf-8")) or {}
    as_of_cfg = _parse_date_maybe(config.get("as_of"))
    as_of_date = as_of or as_of_cfg or date.today()
    fx = get_fx_rates(as_of_date, db_path=db_path)

    by_currency: dict[str, float] = {"KZT": 0.0, "USD": 0.0, "USDT": 0.0, "RUB": 0.0}
    stores = config.get("stores") or {}
    for store_meta in stores.values():
        accounts = (store_meta or {}).get("accounts") or {}
        for account_meta in accounts.values():
            if not isinstance(account_meta, dict):
                continue
            by_currency["KZT"] += _to_float(account_meta.get("balance_kzt"))
            by_currency["USD"] += _to_float(account_meta.get("balance_usd"))
            by_currency["USDT"] += _to_float(account_meta.get("balance_usdt"))
            by_currency["RUB"] += _to_float(account_meta.get("balance_rub"))

    rub_kzt = _to_float(getattr(fx, "rub_kzt", 6.6)) or 6.6
    total_kzt = (
        by_currency["KZT"]
        + by_currency["USD"] * _to_float(fx.usd_kzt)
        + by_currency["USDT"] * _to_float(fx.usd_kzt)
        + by_currency["RUB"] * rub_kzt
    )
    return round(total_kzt, 2), by_currency, as_of_date.isoformat()


def _load_paid_on_hand_inventory_kzt(conn: sqlite3.Connection, *, db_path: Path, as_of: date | None) -> tuple[float, str | None]:
    if not _table_exists(conn, "fact_inventory_snapshot_size") or not _table_exists(conn, "dim_sku"):
        return 0.0, None
    cutoff = as_of.isoformat() if as_of else None
    if cutoff:
        row = conn.execute(
            """
            SELECT MAX(snapshot_date)
            FROM fact_inventory_snapshot_size
            WHERE snapshot_date <= ?
            """,
            (cutoff,),
        ).fetchone()
    else:
        row = conn.execute("SELECT MAX(snapshot_date) FROM fact_inventory_snapshot_size").fetchone()
    snapshot_date = row[0] if row and row[0] else None
    if not snapshot_date:
        return 0.0, None

    sku_meta = {}
    for row in conn.execute("SELECT sku_key, cogs_kzt, base_cost_cny, weight_kg FROM dim_sku").fetchall():
        sku_meta[str(row[0] or "")] = {
            "cogs_kzt": _to_float(row[1]),
            "base_cost_cny": _to_float(row[2]),
            "weight_kg": _to_float(row[3]),
        }

    total = 0.0
    for row in conn.execute(
        """
        SELECT sku_key, SUM(current_stock) AS current_stock
        FROM fact_inventory_snapshot_size
        WHERE snapshot_date = ?
        GROUP BY sku_key
        """,
        (snapshot_date,),
    ).fetchall():
        sku_key = str(row[0] or "")
        qty = _to_float(row[1])
        if qty <= 0:
            continue
        meta = sku_meta.get(sku_key, {})
        cogs_unit, _cost_source, _fx = resolve_landed_cogs(
            meta.get("base_cost_cny"),
            meta.get("weight_kg"),
            as_of_date=_parse_date_maybe(snapshot_date) or date.today(),
            db_path=db_path,
            stored_cogs_kzt=meta.get("cogs_kzt"),
        )
        if cogs_unit is None or cogs_unit <= 0:
            continue
        total += qty * cogs_unit

    return round(total, 2), snapshot_date


def _paid_component(total_value: float, to_pay_value: float, paid_flag: int) -> float:
    total = max(0.0, _to_float(total_value))
    to_pay = max(0.0, _to_float(to_pay_value))
    paid = max(0.0, total - to_pay)
    if paid <= 0 and _to_int(paid_flag) == 1:
        paid = total
    if paid > total:
        paid = total
    return paid


def _load_paid_inbound_from_po_parts(conn: sqlite3.Connection) -> tuple[float, float]:
    if not _table_exists(conn, "po_part"):
        return 0.0, 0.0
    total_paid = 0.0
    total_unpaid = 0.0
    rows = conn.execute(
        """
        SELECT
            po_part_id,
            COALESCE(base_cost_kzt, 0) AS base_cost_kzt,
            COALESCE(est_delivery_kzt, 0) AS est_delivery_kzt,
            COALESCE(is_paid_base, 0) AS is_paid_base,
            COALESCE(is_paid_dlv, 0) AS is_paid_dlv,
            COALESCE(to_pay_base_kzt, 0) AS to_pay_base_kzt,
            COALESCE(to_pay_dlv_kzt, 0) AS to_pay_dlv_kzt
        FROM po_part
        WHERE COALESCE(TRIM(po_part_id), '') <> ''
        """
    ).fetchall()

    for row in rows:
        base_cost_kzt = _to_float(row["base_cost_kzt"])
        dlv_cost_kzt = _to_float(row["est_delivery_kzt"])
        to_pay_base = _to_float(row["to_pay_base_kzt"])
        to_pay_dlv = _to_float(row["to_pay_dlv_kzt"])
        paid_base = _paid_component(base_cost_kzt, to_pay_base, _to_int(row["is_paid_base"]))
        paid_dlv = _paid_component(dlv_cost_kzt, to_pay_dlv, _to_int(row["is_paid_dlv"]))
        total_paid += paid_base + paid_dlv
        total_unpaid += max(0.0, to_pay_base) + max(0.0, to_pay_dlv)

    return round(total_paid, 2), round(total_unpaid, 2)


def _load_paid_on_delivery(conn: sqlite3.Connection, as_of: date | None) -> float:
    if not _table_exists(conn, "fact_cashflow_daily"):
        return 0.0
    if as_of:
        row = conn.execute(
            """
            SELECT inventory_on_delivery_close
            FROM fact_cashflow_daily
            WHERE date <= ?
            ORDER BY date DESC
            LIMIT 1
            """,
            (as_of.isoformat(),),
        ).fetchone()
    else:
        row = conn.execute(
            """
            SELECT inventory_on_delivery_close
            FROM fact_cashflow_daily
            ORDER BY date DESC
            LIMIT 1
            """
        ).fetchone()
    if not row:
        return 0.0
    return round(max(0.0, _to_float(row[0])), 2)


def compute_paid_capital_truth(
    *,
    db_path: Path = DEFAULT_DB,
    bank_accounts_path: Path = DEFAULT_BANK_ACCOUNTS,
    as_of: date | str | None = None,
) -> dict[str, Any]:
    as_of_date = _parse_date_maybe(as_of)
    cash_actual_kzt, bank_by_currency, bank_as_of = _load_cash_total_kzt(
        bank_accounts_path,
        db_path=db_path,
        as_of=as_of_date,
    )
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    try:
        inventory_on_hand_paid_kzt, snapshot_date = _load_paid_on_hand_inventory_kzt(
            conn,
            db_path=db_path,
            as_of=as_of_date,
        )
        inventory_inbound_paid_kzt, inbound_unpaid_obligations_kzt = _load_paid_inbound_from_po_parts(conn)
        inventory_on_delivery_paid_kzt = _load_paid_on_delivery(conn, as_of_date)
    finally:
        conn.close()

    total_capital_paid_kzt = (
        cash_actual_kzt
        + inventory_on_hand_paid_kzt
        + inventory_inbound_paid_kzt
        + inventory_on_delivery_paid_kzt
    )
    return {
        "as_of_date": as_of_date.isoformat() if as_of_date else bank_as_of,
        "bank_as_of_date": bank_as_of,
        "snapshot_date": snapshot_date,
        "cash_actual_kzt": round(cash_actual_kzt, 2),
        "inventory_on_hand_paid_kzt": round(inventory_on_hand_paid_kzt, 2),
        "inventory_inbound_paid_kzt": round(inventory_inbound_paid_kzt, 2),
        "inventory_on_delivery_paid_kzt": round(inventory_on_delivery_paid_kzt, 2),
        "inbound_unpaid_obligations_kzt": round(inbound_unpaid_obligations_kzt, 2),
        "total_capital_paid_kzt": round(total_capital_paid_kzt, 2),
        "bank_by_currency": bank_by_currency,
    }
