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


def _ensure_columns(conn, table: str, columns: dict[str, str]) -> None:
    existing = {
        row["name"]
        for row in conn.execute(f"PRAGMA table_info({table})").fetchall()
    }
    for name, col_type in columns.items():
        if name not in existing:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {name} {col_type}")


def ensure_schema(db_path: Optional[Path] = None) -> None:
    path = db_path or DEFAULT_DB_PATH
    if not _SCHEMA_PATH.exists():
        raise FileNotFoundError(f"Schema not found: {_SCHEMA_PATH}")
    with get_db(path) as conn:
        conn.executescript(_SCHEMA_PATH.read_text())
        # Lightweight migrations for new columns
        _ensure_columns(
            conn,
            "binance_withdrawals",
            {
                "counterparty_label": "TEXT",
                "exchanger_order_id": "TEXT",
                "account_label": "TEXT",
            },
        )
        _ensure_columns(
            conn,
            "binance_c2c_orders",
            {
                "account_label": "TEXT",
            },
        )


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


def has_entry(
    reference_type: str,
    reference_id: str,
    db_path: Optional[Path] = None,
) -> bool:
    path = db_path or DEFAULT_DB_PATH
    ensure_schema(path)
    with get_db(path) as conn:
        row = conn.execute(
            """
            SELECT 1
            FROM transfer_ledger
            WHERE reference_type = ? AND reference_id = ?
            LIMIT 1
            """,
            (reference_type, reference_id),
        ).fetchone()
    return row is not None


def record_sync_log(
    source: str,
    *,
    success: bool,
    last_run_ts: Optional[str] = None,
    min_date_seen: Optional[str] = None,
    max_date_seen: Optional[str] = None,
    rows_total: int = 0,
    rows_inserted: int = 0,
    errors_count: int = 0,
    db_path: Optional[Path] = None,
) -> None:
    """Upsert a sync log entry for transfer-ledger imports."""
    path = db_path or DEFAULT_DB_PATH
    ensure_schema(path)
    now = datetime.now().isoformat()
    last_run = last_run_ts or now
    with get_db(path) as conn:
        existing = conn.execute(
            "SELECT last_success_ts FROM transfer_ledger_sync_log WHERE source = ?",
            (source,),
        ).fetchone()
        last_success = now if success else (existing["last_success_ts"] if existing else None)
        conn.execute(
            """
            INSERT OR REPLACE INTO transfer_ledger_sync_log (
                source, last_run_ts, last_success_ts, min_date_seen, max_date_seen,
                rows_total, rows_inserted, errors_count, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))
            """,
            (
                source,
                last_run,
                last_success,
                min_date_seen,
                max_date_seen,
                int(rows_total),
                int(rows_inserted),
                int(errors_count),
            ),
        )


def update_withdrawal_metadata(
    withdraw_id: str,
    address: Optional[str] = None,
    tx_id: Optional[str] = None,
    success_time: Optional[str] = None,
    status: Optional[str] = None,
    db_path: Optional[Path] = None,
) -> bool:
    path = db_path or DEFAULT_DB_PATH
    ensure_schema(path)
    fields: list[str] = []
    params: list = []
    if address:
        fields.append("address = ?")
        params.append(address)
    if tx_id:
        fields.append("tx_id = ?")
        params.append(tx_id)
    if success_time:
        fields.append("success_time = ?")
        params.append(success_time)
    if status:
        fields.append("status = ?")
        params.append(status)
    if not fields:
        return False
    fields.append("updated_at = datetime('now')")
    params.append(withdraw_id)
    sql = f"UPDATE binance_withdrawals SET {', '.join(fields)} WHERE withdraw_id = ?"
    with get_db(path) as conn:
        cur = conn.execute(sql, params)
        return cur.rowcount > 0


def upsert_binance_deposit(deposit: dict, db_path: Optional[Path] = None) -> bool:
    path = db_path or DEFAULT_DB_PATH
    ensure_schema(path)
    with get_db(path) as conn:
        existing = conn.execute(
            "SELECT 1 FROM binance_deposits WHERE deposit_id = ? LIMIT 1",
            (deposit["deposit_id"],),
        ).fetchone()
        conn.execute(
            """
            INSERT OR REPLACE INTO binance_deposits (
                deposit_id, coin, amount, address, address_tag, tx_id,
                insert_time, complete_time, status, network, transfer_type,
                wallet_type, account_label, raw_json, source, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))
            """,
            (
                deposit["deposit_id"],
                deposit.get("coin"),
                deposit.get("amount"),
                deposit.get("address"),
                deposit.get("address_tag"),
                deposit.get("tx_id"),
                deposit.get("insert_time"),
                deposit.get("complete_time"),
                deposit.get("status"),
                deposit.get("network"),
                deposit.get("transfer_type"),
                deposit.get("wallet_type"),
                deposit.get("account_label"),
                deposit.get("raw_json"),
                deposit.get("source", "BINANCE_DEPOSIT"),
            ),
        )
    return existing is None


def upsert_binance_transfer(transfer: dict, db_path: Optional[Path] = None) -> bool:
    path = db_path or DEFAULT_DB_PATH
    ensure_schema(path)
    with get_db(path) as conn:
        existing = conn.execute(
            "SELECT 1 FROM binance_transfers WHERE transfer_id = ? LIMIT 1",
            (transfer["transfer_id"],),
        ).fetchone()
        conn.execute(
            """
            INSERT OR REPLACE INTO binance_transfers (
                transfer_id, asset, amount, transfer_type, status, timestamp,
                account_label, raw_json, source, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))
            """,
            (
                transfer["transfer_id"],
                transfer.get("asset"),
                transfer.get("amount"),
                transfer.get("transfer_type"),
                transfer.get("status"),
                transfer.get("timestamp"),
                transfer.get("account_label"),
                transfer.get("raw_json"),
                transfer.get("source", "BINANCE_TRANSFER"),
            ),
        )
    return existing is None


def upsert_binance_account_snapshot(snapshot: dict, db_path: Optional[Path] = None) -> bool:
    path = db_path or DEFAULT_DB_PATH
    ensure_schema(path)
    with get_db(path) as conn:
        existing = conn.execute(
            "SELECT 1 FROM binance_account_snapshots WHERE snapshot_id = ? LIMIT 1",
            (snapshot["snapshot_id"],),
        ).fetchone()
        conn.execute(
            """
            INSERT OR REPLACE INTO binance_account_snapshots (
                snapshot_id, account_type, snapshot_time, total_asset_btc,
                account_label, data_json, raw_json, source, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))
            """,
            (
                snapshot["snapshot_id"],
                snapshot.get("account_type"),
                snapshot.get("snapshot_time"),
                snapshot.get("total_asset_btc"),
                snapshot.get("account_label"),
                snapshot.get("data_json"),
                snapshot.get("raw_json"),
                snapshot.get("source", "BINANCE_SNAPSHOT"),
            ),
        )
    return existing is None


def insert_funding_balance_snapshot(snapshot: dict, db_path: Optional[Path] = None) -> None:
    path = db_path or DEFAULT_DB_PATH
    ensure_schema(path)
    with get_db(path) as conn:
        conn.execute(
            """
            INSERT OR REPLACE INTO binance_funding_balances (
                snapshot_time, asset, free, locked, total, account_label, raw_json, source, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))
            """,
            (
                snapshot.get("snapshot_time"),
                snapshot.get("asset"),
                snapshot.get("free"),
                snapshot.get("locked"),
                snapshot.get("total"),
                snapshot.get("account_label"),
                snapshot.get("raw_json"),
                snapshot.get("source", "BINANCE_FUNDING_BAL"),
            ),
        )


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
                advertisement_role, account_label, raw_json, source, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))
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
                order.get("account_label"),
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
                counterparty_label, exchanger_order_id, account_label, raw_json, source, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))
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
                withdraw.get("exchanger_order_id"),
                withdraw.get("account_label"),
                withdraw.get("raw_json"),
                withdraw.get("source", "BINANCE_WITHDRAW"),
            ),
        )
    return existing is None


def upsert_exchanger_order(order: dict, db_path: Optional[Path] = None) -> bool:
    path = db_path or DEFAULT_DB_PATH
    ensure_schema(path)
    def _parse_dt(value: object) -> Optional[datetime]:
        if not value:
            return None
        try:
            return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        except Exception:
            return None

    def _choose_latest(existing_value: object, new_value: object, prefer_new: bool) -> object:
        if prefer_new and new_value not in (None, ""):
            return new_value
        if existing_value not in (None, ""):
            return existing_value
        return new_value

    with get_db(path) as conn:
        existing = conn.execute(
            """
            SELECT
                exchanger_order_id, exchanger, order_id, status, direction,
                amount_usdt, amount_cny, rate_usdt_cny, deposit_address,
                receiver_account, message_id, message_date, subject, raw_json, source
            FROM exchanger_orders
            WHERE exchanger_order_id = ?
            LIMIT 1
            """,
            (order["exchanger_order_id"],),
        ).fetchone()
        payload = dict(order)
        if existing is not None:
            current = dict(existing)
            new_dt = _parse_dt(order.get("message_date"))
            cur_dt = _parse_dt(current.get("message_date"))
            prefer_new = False
            if new_dt and cur_dt:
                prefer_new = new_dt >= cur_dt
            elif new_dt and not cur_dt:
                prefer_new = True

            payload = {
                "exchanger_order_id": order["exchanger_order_id"],
                "exchanger": order.get("exchanger") or current.get("exchanger"),
                "order_id": order.get("order_id") or current.get("order_id"),
                "status": _choose_latest(current.get("status"), order.get("status"), prefer_new),
                "direction": order.get("direction") or current.get("direction"),
                "amount_usdt": order.get("amount_usdt") if order.get("amount_usdt") is not None else current.get("amount_usdt"),
                "amount_cny": order.get("amount_cny") if order.get("amount_cny") is not None else current.get("amount_cny"),
                "rate_usdt_cny": order.get("rate_usdt_cny") if order.get("rate_usdt_cny") is not None else current.get("rate_usdt_cny"),
                "deposit_address": order.get("deposit_address") or current.get("deposit_address"),
                "receiver_account": order.get("receiver_account") or current.get("receiver_account"),
                "message_id": _choose_latest(current.get("message_id"), order.get("message_id"), prefer_new),
                "message_date": _choose_latest(current.get("message_date"), order.get("message_date"), prefer_new),
                "subject": _choose_latest(current.get("subject"), order.get("subject"), prefer_new),
                "raw_json": _choose_latest(current.get("raw_json"), order.get("raw_json"), prefer_new),
                "source": _choose_latest(current.get("source"), order.get("source", "GMAIL"), prefer_new),
            }

        conn.execute(
            """
            INSERT OR REPLACE INTO exchanger_orders (
                exchanger_order_id, exchanger, order_id, status, direction,
                amount_usdt, amount_cny, rate_usdt_cny, deposit_address,
                receiver_account, message_id, message_date, subject, raw_json,
                source, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))
            """,
            (
                payload["exchanger_order_id"],
                payload.get("exchanger"),
                payload.get("order_id"),
                payload.get("status"),
                payload.get("direction"),
                payload.get("amount_usdt"),
                payload.get("amount_cny"),
                payload.get("rate_usdt_cny"),
                payload.get("deposit_address"),
                payload.get("receiver_account"),
                payload.get("message_id"),
                payload.get("message_date"),
                payload.get("subject"),
                payload.get("raw_json"),
                payload.get("source", "GMAIL"),
            ),
        )
    return existing is None


def insert_exchanger_event(event: dict, db_path: Optional[Path] = None) -> bool:
    path = db_path or DEFAULT_DB_PATH
    ensure_schema(path)
    message_id = event.get("message_id") or ""
    with get_db(path) as conn:
        existing = None
        if message_id:
            existing = conn.execute(
                "SELECT 1 FROM exchanger_order_events WHERE message_id = ? LIMIT 1",
                (message_id,),
            ).fetchone()
        if existing is None:
            conn.execute(
                """
                INSERT INTO exchanger_order_events (
                    exchanger_order_id, exchanger, order_id, status,
                    message_id, message_date, subject, raw_json, source, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))
                """,
                (
                    event.get("exchanger_order_id"),
                    event.get("exchanger"),
                    event.get("order_id"),
                    event.get("status"),
                    message_id,
                    event.get("message_date"),
                    event.get("subject"),
                    event.get("raw_json"),
                    event.get("source", "GMAIL"),
                ),
            )
    return existing is None


def list_exchanger_orders(
    db_path: Optional[Path] = None,
    exchanger: Optional[str] = None,
    status: Optional[str] = None,
    limit: Optional[int] = None,
) -> list[dict]:
    path = db_path or DEFAULT_DB_PATH
    ensure_schema(path)
    clauses: list[str] = []
    params: list = []
    if exchanger:
        clauses.append("exchanger = ?")
        params.append(exchanger)
    if status:
        clauses.append("status = ?")
        params.append(status)
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    limit_sql = f"LIMIT {int(limit)}" if limit is not None else ""
    sql = f"""
        SELECT
            exchanger_order_id, exchanger, order_id, status, direction,
            amount_usdt, amount_cny, rate_usdt_cny, deposit_address, receiver_account,
            message_id, message_date, subject, raw_json, source, updated_at
        FROM exchanger_orders
        {where}
        ORDER BY message_date DESC, exchanger_order_id DESC
        {limit_sql}
    """
    with get_db(path) as conn:
        rows = conn.execute(sql, params).fetchall()
    return [dict(r) for r in rows]


def find_exchanger_orders_by_address(
    address: str,
    db_path: Optional[Path] = None,
) -> list[dict]:
    path = db_path or DEFAULT_DB_PATH
    ensure_schema(path)
    with get_db(path) as conn:
        rows = conn.execute(
            """
            SELECT
                exchanger_order_id, exchanger, order_id, status, direction,
                amount_usdt, amount_cny, rate_usdt_cny, deposit_address,
                receiver_account, message_id, message_date, subject, raw_json,
                source, updated_at
            FROM exchanger_orders
            WHERE deposit_address = ?
            ORDER BY message_date DESC
            """,
            (address,),
        ).fetchall()
    return [dict(r) for r in rows]


def list_withdrawals(
    db_path: Optional[Path] = None,
    only_unlabeled: bool = False,
) -> list[dict]:
    path = db_path or DEFAULT_DB_PATH
    ensure_schema(path)
    where = ""
    if only_unlabeled:
        where = "WHERE (counterparty_label IS NULL OR counterparty_label = '')"
    sql = f"""
        SELECT
            withdraw_id, tx_id, coin, network, amount, transaction_fee, address,
            address_tag, apply_time, success_time, status, wallet_type,
            counterparty_label, exchanger_order_id, account_label
        FROM binance_withdrawals
        {where}
        ORDER BY apply_time DESC
    """
    with get_db(path) as conn:
        rows = conn.execute(sql).fetchall()
    return [dict(r) for r in rows]


def list_deposits(
    db_path: Optional[Path] = None,
    start_time: Optional[str] = None,
    coin: Optional[str] = None,
) -> list[dict]:
    path = db_path or DEFAULT_DB_PATH
    ensure_schema(path)
    clauses: list[str] = []
    params: list = []
    if start_time:
        clauses.append("insert_time >= ?")
        params.append(start_time)
    if coin:
        clauses.append("coin = ?")
        params.append(coin.upper())
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    sql = f"""
        SELECT
            deposit_id, coin, amount, address, address_tag, tx_id,
            insert_time, complete_time, status, network, transfer_type,
            wallet_type, account_label
        FROM binance_deposits
        {where}
        ORDER BY insert_time DESC
    """
    with get_db(path) as conn:
        rows = conn.execute(sql, params).fetchall()
    return [dict(r) for r in rows]


def list_transfers(
    db_path: Optional[Path] = None,
    start_time: Optional[str] = None,
    asset: Optional[str] = None,
) -> list[dict]:
    path = db_path or DEFAULT_DB_PATH
    ensure_schema(path)
    clauses: list[str] = []
    params: list = []
    if start_time:
        clauses.append("timestamp >= ?")
        params.append(start_time)
    if asset:
        clauses.append("asset = ?")
        params.append(asset.upper())
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    sql = f"""
        SELECT
            transfer_id, asset, amount, transfer_type, status, timestamp, account_label
        FROM binance_transfers
        {where}
        ORDER BY timestamp DESC
    """
    with get_db(path) as conn:
        rows = conn.execute(sql, params).fetchall()
    return [dict(r) for r in rows]


def list_funding_balance_snapshots(
    db_path: Optional[Path] = None,
    asset: Optional[str] = None,
    limit: int = 50,
) -> list[dict]:
    path = db_path or DEFAULT_DB_PATH
    ensure_schema(path)
    params: list = []
    where = ""
    if asset:
        where = "WHERE asset = ?"
        params.append(asset.upper())
    sql = f"""
        SELECT snapshot_time, asset, free, locked, total
        FROM binance_funding_balances
        {where}
        ORDER BY snapshot_time DESC
        LIMIT {int(limit)}
    """
    with get_db(path) as conn:
        rows = conn.execute(sql, params).fetchall()
    return [dict(r) for r in rows]


def update_withdrawal_label(
    withdraw_id: str,
    counterparty_label: str,
    exchanger_order_id: Optional[str] = None,
    db_path: Optional[Path] = None,
) -> None:
    path = db_path or DEFAULT_DB_PATH
    ensure_schema(path)
    with get_db(path) as conn:
        conn.execute(
            """
            UPDATE binance_withdrawals
            SET counterparty_label = ?, exchanger_order_id = ?, updated_at = datetime('now')
            WHERE withdraw_id = ?
            """,
            (counterparty_label, exchanger_order_id, withdraw_id),
        )


def update_withdrawal_entry_notes(
    withdraw_id: str,
    counterparty_label: str,
    exchanger_order_id: Optional[str] = None,
    db_path: Optional[Path] = None,
) -> None:
    path = db_path or DEFAULT_DB_PATH
    ensure_schema(path)
    with get_db(path) as conn:
        row = conn.execute(
            """
            SELECT entry_id, notes
            FROM transfer_ledger
            WHERE reference_type = 'BINANCE_WITHDRAWAL' AND reference_id = ?
            ORDER BY entry_id DESC
            LIMIT 1
            """,
            (withdraw_id,),
        ).fetchone()
        if not row:
            return
        notes = row["notes"] or ""
        label_token = f"label={counterparty_label}"
        order_token = f"exchanger_order_id={exchanger_order_id}" if exchanger_order_id else ""
        if label_token not in notes:
            if notes:
                notes = f"{notes}; {label_token}"
            else:
                notes = label_token
        if order_token and order_token not in notes:
            notes = f"{notes}; {order_token}"
        conn.execute(
            "UPDATE transfer_ledger SET notes = ? WHERE entry_id = ?",
            (notes, row["entry_id"]),
        )


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


def upsert_po_funding_plan(plan: dict, db_path: Optional[Path] = None) -> bool:
    path = db_path or DEFAULT_DB_PATH
    ensure_schema(path)
    with get_db(path) as conn:
        existing = conn.execute(
            "SELECT 1 FROM po_funding_plan WHERE po_id = ? LIMIT 1",
            (plan["po_id"],),
        ).fetchone()
        conn.execute(
            """
            INSERT INTO po_funding_plan (po_id, message_date, total_cny, total_usdt, source, updated_at)
            VALUES (?, ?, ?, ?, ?, datetime('now'))
            ON CONFLICT(po_id) DO UPDATE SET
                message_date = COALESCE(excluded.message_date, po_funding_plan.message_date),
                total_cny = COALESCE(excluded.total_cny, po_funding_plan.total_cny),
                total_usdt = COALESCE(excluded.total_usdt, po_funding_plan.total_usdt),
                source = COALESCE(excluded.source, po_funding_plan.source),
                updated_at = datetime('now')
            """,
            (
                plan["po_id"],
                plan.get("message_date"),
                plan.get("total_cny"),
                plan.get("total_usdt"),
                plan.get("source"),
            ),
        )
    return existing is None


def upsert_po_header_min(
    *,
    po_id: str,
    message_date: Optional[str] = None,
    total_cost_cny: Optional[float] = None,
    db_path: Optional[Path] = None,
) -> bool:
    path = db_path or DEFAULT_DB_PATH
    ensure_schema(path)
    with get_db(path) as conn:
        existing = conn.execute(
            "SELECT 1 FROM po_header WHERE po_id = ? LIMIT 1",
            (po_id,),
        ).fetchone()
        conn.execute(
            """
            INSERT INTO po_header (po_id, message_date, total_cost_cny)
            VALUES (?, ?, COALESCE(?, 0))
            ON CONFLICT(po_id) DO UPDATE SET
                message_date = CASE
                    WHEN excluded.message_date IS NULL THEN po_header.message_date
                    WHEN po_header.message_date IS NULL THEN excluded.message_date
                    WHEN excluded.message_date < po_header.message_date THEN excluded.message_date
                    ELSE po_header.message_date
                END,
                total_cost_cny = COALESCE(excluded.total_cost_cny, po_header.total_cost_cny),
                updated_at = datetime('now')
            """,
            (po_id, message_date, total_cost_cny),
        )
    return existing is None


def list_po_funding_plan(db_path: Optional[Path] = None) -> list[dict]:
    path = db_path or DEFAULT_DB_PATH
    ensure_schema(path)
    with get_db(path) as conn:
        table = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='po_funding_plan'"
        ).fetchone()
        if not table:
            return []
        rows = conn.execute(
            """
            SELECT po_id, message_date, total_cny, total_usdt, source, updated_at
            FROM po_funding_plan
            WHERE po_id IS NOT NULL
            """
        ).fetchall()
    return [dict(r) for r in rows]


def upsert_po_exchanger_allocation(allocation: dict, db_path: Optional[Path] = None) -> bool:
    path = db_path or DEFAULT_DB_PATH
    ensure_schema(path)
    with get_db(path) as conn:
        existing = conn.execute(
            "SELECT 1 FROM po_exchanger_allocations WHERE exchanger_order_id = ? LIMIT 1",
            (allocation["exchanger_order_id"],),
        ).fetchone()
        conn.execute(
            """
            INSERT INTO po_exchanger_allocations (
                po_id, exchanger_order_id, amount_usdt, amount_cny, source, created_at
            ) VALUES (?, ?, ?, ?, ?, datetime('now'))
            ON CONFLICT(exchanger_order_id) DO UPDATE SET
                po_id = excluded.po_id,
                amount_usdt = COALESCE(excluded.amount_usdt, po_exchanger_allocations.amount_usdt),
                amount_cny = COALESCE(excluded.amount_cny, po_exchanger_allocations.amount_cny),
                source = COALESCE(excluded.source, po_exchanger_allocations.source),
                created_at = po_exchanger_allocations.created_at
            """,
            (
                allocation["po_id"],
                allocation["exchanger_order_id"],
                allocation.get("amount_usdt"),
                allocation.get("amount_cny"),
                allocation.get("source"),
            ),
        )
    return existing is None


def list_po_exchanger_allocations(
    db_path: Optional[Path] = None,
    po_id: Optional[str] = None,
) -> list[dict]:
    path = db_path or DEFAULT_DB_PATH
    ensure_schema(path)
    params: list = []
    where = ""
    if po_id:
        where = "WHERE po_id = ?"
        params.append(po_id)
    sql = f"""
        SELECT allocation_id, po_id, exchanger_order_id, amount_usdt, amount_cny, source, created_at
        FROM po_exchanger_allocations
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
