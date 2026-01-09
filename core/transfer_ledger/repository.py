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


def get_entry(entry_id: int, db_path: Optional[Path] = None) -> Optional[LedgerEntry]:
    path = db_path or DEFAULT_DB_PATH
    ensure_schema(path)
    with get_db(path) as conn:
        row = conn.execute(
            """
            SELECT
                entry_id, entry_date, amount, currency, amount_kzt, fx_rate_to_kzt,
                fx_source, reference_type, reference_id, from_account, to_account, notes
            FROM transfer_ledger
            WHERE entry_id = ?
            """,
            (entry_id,),
        ).fetchone()
    if not row:
        return None
    return LedgerEntry(
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


def upsert_binance_withdrawal(withdraw: dict, db_path: Optional[Path] = None) -> bool:
    path = db_path or DEFAULT_DB_PATH
    ensure_schema(path)
    with get_db(path) as conn:
        existing = conn.execute(
            "SELECT 1 FROM binance_withdrawals WHERE withdraw_id = ? LIMIT 1",
            (withdraw["withdraw_id"],),
        ).fetchone()
        conn.execute(
            """
            INSERT OR REPLACE INTO binance_withdrawals (
                withdraw_id, tx_id, coin, network, amount, transaction_fee, address,
                address_tag, apply_time, success_time, status, wallet_type,
                counterparty_label, raw_json, source, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))
            """,
            (
                withdraw["withdraw_id"],
                withdraw.get("tx_id"),
                withdraw["coin"],
                withdraw.get("network"),
                withdraw["amount"],
                withdraw.get("transaction_fee"),
                withdraw.get("address"),
                withdraw.get("address_tag"),
                withdraw.get("apply_time"),
                withdraw.get("success_time"),
                withdraw.get("status"),
                withdraw.get("wallet_type"),
                withdraw.get("counterparty_label"),
                withdraw.get("raw_json"),
                withdraw.get("source", "BINANCE_WITHDRAW"),
            ),
        )
    return existing is None


def create_po_funding_allocation(
    po_id: str,
    entry_id: int,
    amount: float,
    currency: str,
    amount_kzt: float,
    notes: str = "",
    db_path: Optional[Path] = None,
) -> int:
    path = db_path or DEFAULT_DB_PATH
    ensure_schema(path)
    with get_db(path) as conn:
        cur = conn.execute(
            """
            INSERT INTO po_funding_allocations
            (po_id, entry_id, amount, currency, amount_kzt, notes)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (po_id, entry_id, amount, currency, amount_kzt, notes),
        )
        return int(cur.lastrowid)


def list_po_funding_allocations(
    po_id: Optional[str] = None,
    entry_id: Optional[int] = None,
    db_path: Optional[Path] = None,
) -> list[dict]:
    path = db_path or DEFAULT_DB_PATH
    ensure_schema(path)
    clauses: list[str] = []
    params: list = []
    if po_id:
        clauses.append("po_id = ?")
        params.append(po_id)
    if entry_id is not None:
        clauses.append("entry_id = ?")
        params.append(entry_id)
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    sql = f"""
        SELECT allocation_id, po_id, entry_id, amount, currency, amount_kzt, notes, created_at
        FROM po_funding_allocations
        {where}
        ORDER BY allocation_id DESC
    """
    with get_db(path) as conn:
        rows = conn.execute(sql, params).fetchall()
    return [dict(r) for r in rows]


def list_pos_for_allocation(db_path: Optional[Path] = None) -> list[dict]:
    path = db_path or DEFAULT_DB_PATH
    ensure_schema(path)
    with get_db(path) as conn:
        table = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='po_header'"
        ).fetchone()
        if not table:
            return []
        rows = conn.execute(
            """
            SELECT
                po_id,
                message_date,
                total_cost_cny,
                total_cost_kzt_supplier,
                fx_rate_cny_plan,
                created_at
            FROM po_header
            WHERE po_id IS NOT NULL
            """
        ).fetchall()
    return [dict(r) for r in rows]


def get_po_allocated_kzt(po_id: str, db_path: Optional[Path] = None) -> float:
    path = db_path or DEFAULT_DB_PATH
    ensure_schema(path)
    with get_db(path) as conn:
        row = conn.execute(
            "SELECT COALESCE(SUM(amount_kzt), 0) AS total FROM po_funding_allocations WHERE po_id = ?",
            (po_id,),
        ).fetchone()
    return float(row["total"]) if row else 0.0


def get_po_total_cny_from_lines(po_id: str, db_path: Optional[Path] = None) -> Optional[float]:
    path = db_path or DEFAULT_DB_PATH
    ensure_schema(path)
    with get_db(path) as conn:
        table = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='po_line'"
        ).fetchone()
        if not table:
            return None
        row = conn.execute(
            """
            SELECT COALESCE(SUM(order_qty * unit_cost_cny), 0) AS total_cny
            FROM po_line
            WHERE po_id = ?
            """,
            (po_id,),
        ).fetchone()
    if row is None:
        return None
    return float(row["total_cny"])
