"""SQLite repository for transfer ledger."""

from __future__ import annotations

from datetime import date, datetime
from pathlib import Path
from typing import Iterable, Optional

from core.db import get_db, DEFAULT_DB_PATH
from .models import LedgerEntry

_SCHEMA_PATH = Path(__file__).resolve().parent / "schema.sql"


def _normalize_date(value: Optional[date | datetime]) -> Optional[str]:
    if value is None:
        return None
    if isinstance(value, datetime):
        value = value.date()
    return value.isoformat()


def ensure_schema(db_path: Optional[Path] = None) -> None:
    path = db_path or DEFAULT_DB_PATH
    if not _SCHEMA_PATH.exists():
        raise FileNotFoundError(f"Schema not found: {_SCHEMA_PATH}")
    with get_db(path) as conn:
        conn.executescript(_SCHEMA_PATH.read_text())


def insert_entry(entry: LedgerEntry, db_path: Optional[Path] = None) -> int:
    path = db_path or DEFAULT_DB_PATH
    ensure_schema(path)
    with get_db(path) as conn:
        cur = conn.execute(
            """
            INSERT INTO transfer_ledger (
                entry_date, amount, currency, amount_kzt, fx_rate_to_kzt,
                fx_source, reference_type, reference_id, from_account, to_account, notes
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                entry.entry_date.isoformat(),
                entry.amount,
                entry.currency,
                entry.amount_kzt,
                entry.fx_rate_to_kzt,
                entry.fx_source,
                entry.reference_type,
                entry.reference_id,
                entry.from_account,
                entry.to_account,
                entry.notes,
            ),
        )
        return int(cur.lastrowid)


def list_entries(
    reference_type: Optional[str] = None,
    reference_id: Optional[str] = None,
    currency: Optional[str] = None,
    db_path: Optional[Path] = None,
    limit: Optional[int] = None,
) -> list[LedgerEntry]:
    path = db_path or DEFAULT_DB_PATH
    ensure_schema(path)
    clauses: list[str] = []
    params: list = []

    if reference_type:
        clauses.append("reference_type = ?")
        params.append(reference_type)
    if reference_id:
        clauses.append("reference_id = ?")
        params.append(reference_id)
    if currency:
        clauses.append("currency = ?")
        params.append(currency)

    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    limit_sql = f"LIMIT {int(limit)}" if limit is not None else ""

    sql = f"""
        SELECT
            entry_id, entry_date, amount, currency, amount_kzt, fx_rate_to_kzt,
            fx_source, reference_type, reference_id, from_account, to_account, notes
        FROM transfer_ledger
        {where}
        ORDER BY entry_date DESC, entry_id DESC
        {limit_sql}
    """

    with get_db(path) as conn:
        rows = conn.execute(sql, params).fetchall()
    entries: list[LedgerEntry] = []
    for row in rows:
        entries.append(
            LedgerEntry(
                entry_id=row["entry_id"],
                entry_date=date.fromisoformat(row["entry_date"]),
                amount=row["amount"],
                currency=row["currency"],
                amount_kzt=row["amount_kzt"],
                fx_rate_to_kzt=row["fx_rate_to_kzt"],
                fx_source=row["fx_source"],
                reference_type=row["reference_type"],
                reference_id=row["reference_id"],
                from_account=row["from_account"] or "",
                to_account=row["to_account"] or "",
                notes=row["notes"] or "",
            )
        )
    return entries


def get_balance(
    currency: str = "KZT",
    as_of_date: Optional[date | datetime] = None,
    db_path: Optional[Path] = None,
) -> float:
    path = db_path or DEFAULT_DB_PATH
    ensure_schema(path)
    as_of = _normalize_date(as_of_date)

    where = []
    params: list = []
    if currency and currency.upper() != "KZT":
        where.append("currency = ?")
        params.append(currency)
    if as_of:
        where.append("entry_date <= ?")
        params.append(as_of)

    where_sql = f"WHERE {' AND '.join(where)}" if where else ""
    column = "amount_kzt" if currency.upper() == "KZT" else "amount"

    with get_db(path) as conn:
        row = conn.execute(
            f"SELECT COALESCE(SUM({column}), 0) AS total FROM transfer_ledger {where_sql}",
            params,
        ).fetchone()
    return float(row["total"]) if row else 0.0


def ledger_entry_exists(
    reference_type: str,
    reference_id: str,
    currency: Optional[str] = None,
    db_path: Optional[Path] = None,
) -> bool:
    path = db_path or DEFAULT_DB_PATH
    ensure_schema(path)
    clauses = ["reference_type = ?", "reference_id = ?"]
    params: list = [reference_type, reference_id]
    if currency:
        clauses.append("currency = ?")
        params.append(currency)
    where = " AND ".join(clauses)
    with get_db(path) as conn:
        row = conn.execute(
            f"SELECT 1 FROM transfer_ledger WHERE {where} LIMIT 1",
            params,
        ).fetchone()
    return row is not None


def upsert_binance_c2c_order(order: dict, db_path: Optional[Path] = None) -> bool:
    path = db_path or DEFAULT_DB_PATH
    ensure_schema(path)
    with get_db(path) as conn:
        existing = conn.execute(
            "SELECT 1 FROM binance_c2c_orders WHERE order_number = ? LIMIT 1",
            (order["order_number"],),
        ).fetchone()
        conn.execute(
            """
            INSERT OR REPLACE INTO binance_c2c_orders (
                order_number, adv_no, trade_type, asset, fiat, fiat_amount, crypto_amount,
                unit_price, order_status, create_time, commission, counterparty,
                advertisement_role, raw_json, source, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))
            """,
            (
                order["order_number"],
                order.get("adv_no"),
                order["trade_type"],
                order["asset"],
                order["fiat"],
                order["fiat_amount"],
                order["crypto_amount"],
                order["unit_price"],
                order["order_status"],
                order["create_time"],
                order.get("commission"),
                order.get("counterparty"),
                order.get("advertisement_role"),
                order.get("raw_json"),
                order.get("source", "BINANCE_P2P"),
            ),
        )
    return existing is None
