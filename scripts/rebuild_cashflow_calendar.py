#!/usr/bin/env python3
"""
Rebuild cashflow calendar (events + daily roll-forward).

Default: DRY RUN (no DB writes). Apply requires ENABLE_CASHFLOW_WRITE=1 and --apply.
"""

from __future__ import annotations

import argparse
import os
import hashlib
import re
import sqlite3
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Optional, Iterable
import sys

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from scripts.backup_db import backup_database  # noqa: E402
from core.db.queries import get_cutoff_date_almaty
from core.config.business_params import get_fx_rates
from core.calc.economics import calc_cogs
DEFAULT_DB = PROJECT_ROOT / "db" / "app.db"
PROD_WRITE_ENV_GATE = "ENABLE_CASHFLOW_PROD_WRITE"

AUTO_EVENT_TYPES = {"COGS_RECOGNIZED"}
EXPENSE_EVENT_TYPES = {
    "EXPENSE",
    "KASPI_FEES",
    "DELIVERY_FEES",
    "ADS",
    "BONUS",
    "TRANSFER",
    "LOAN_PAYMENT",
    "UNKNOWN",
}
PAYOUT_EVENT_TYPES = {"PAYOUT_RECEIVED"}
INVENTORY_ACCOUNTS = {
    "INVENTORY_COST",
    "INVENTORY_ON_HAND_COST",
    "INVENTORY_INBOUND_COST",
    "INVENTORY_ON_DELIVERY_COST",
}
DAILY_AUTO_MIGRATE_COLUMNS = {
    "inventory_on_hand_open": "REAL NOT NULL DEFAULT 0",
    "inventory_on_hand_close": "REAL NOT NULL DEFAULT 0",
    "inventory_inbound_open": "REAL NOT NULL DEFAULT 0",
    "inventory_inbound_close": "REAL NOT NULL DEFAULT 0",
    "inventory_on_delivery_open": "REAL NOT NULL DEFAULT 0",
    "inventory_on_delivery_close": "REAL NOT NULL DEFAULT 0",
}
DAILY_REQUIRED_COLUMNS = {
    "date",
    "cash_open",
    "cash_close",
    "receivables_open",
    "receivables_close",
    "inventory_cost_open",
    "inventory_cost_close",
    "capital_close",
    "inventory_on_hand_open",
    "inventory_on_hand_close",
    "inventory_inbound_open",
    "inventory_inbound_close",
    "inventory_on_delivery_open",
    "inventory_on_delivery_close",
    "sales_accrued_kzt",
    "payouts_received_kzt",
    "refunds_kzt",
    "po_payments_kzt",
    "expenses_kzt",
    "cogs_kzt",
    "cash_flow_kzt",
    "receivables_flow_kzt",
    "inventory_cost_flow_kzt",
    "profit_accrual_kzt",
    "run_id",
}
ANCHOR_TIMESTAMP_RE = re.compile(
    r"(?P<day>\d{2})\.(?P<month>\d{2})\.(?P<year>\d{4})_"
    r"(?P<hour>\d{2})_(?P<minute>\d{2})_(?P<second>\d{2})"
)


@dataclass(frozen=True)
class ActualCashAnchor:
    anchor_date: date
    operating_cash_kzt: float
    row_count: int
    run_id: str | None = None
    created_at: str | None = None
    anchor_ts: datetime | None = None
    reserve_kzt: float | None = None
    grand_total_with_reserve_kzt: float | None = None


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _sqlite_integrity_check(path: Path) -> str:
    conn = sqlite3.connect(str(path))
    try:
        row = conn.execute("PRAGMA integrity_check").fetchone()
        return str(row[0]) if row else "missing"
    finally:
        conn.close()


def _sidecar_paths(db_path: Path) -> list[Path]:
    return [db_path.with_name(db_path.name + suffix) for suffix in ("-wal", "-shm", "-journal")]


def _fail_on_sqlite_sidecars(db_path: Path) -> None:
    existing = [path for path in _sidecar_paths(db_path) if path.exists()]
    if existing:
        joined = ", ".join(str(path) for path in existing)
        raise RuntimeError(f"refusing production cashflow rebuild while SQLite sidecars exist: {joined}")


def _is_production_db(db_path: Path) -> bool:
    return db_path.resolve() == DEFAULT_DB.resolve()


def _prepare_cashflow_rebuild_apply_guard(
    db_path: Path,
    *,
    expected_pre_sha256: str | None = None,
    backup_dir: Path | None = None,
) -> dict[str, object]:
    if os.environ.get("ENABLE_CASHFLOW_WRITE") != "1":
        raise RuntimeError("ENABLE_CASHFLOW_WRITE=1 is required to apply cashflow writes.")

    production_apply = _is_production_db(db_path)
    metadata: dict[str, object] = {
        "production_apply": production_apply,
        "pre_sha256": _sha256_file(db_path),
    }
    if not production_apply:
        return metadata

    if os.environ.get(PROD_WRITE_ENV_GATE) != "1":
        raise RuntimeError(f"{PROD_WRITE_ENV_GATE}=1 is required for production cashflow rebuild.")
    if not expected_pre_sha256:
        raise RuntimeError("--expected-pre-sha256 is required for production cashflow rebuild.")
    if backup_dir is None:
        raise RuntimeError("--backup-dir is required for production cashflow rebuild.")

    _fail_on_sqlite_sidecars(db_path)
    pre_integrity = _sqlite_integrity_check(db_path)
    if pre_integrity.lower() != "ok":
        raise RuntimeError(f"production DB integrity_check failed before cashflow rebuild: {pre_integrity}")
    pre_sha256 = str(metadata["pre_sha256"])
    if pre_sha256 != expected_pre_sha256:
        raise RuntimeError(
            "production DB SHA mismatch before cashflow rebuild: "
            f"expected {expected_pre_sha256}, observed {pre_sha256}"
        )

    backup_path = backup_database(db_path, backup_dir, compress=False)
    backup_integrity = _sqlite_integrity_check(backup_path)
    if backup_integrity.lower() != "ok":
        raise RuntimeError(f"cashflow rebuild backup integrity_check failed: {backup_integrity}")
    metadata.update(
        {
            "expected_pre_sha256": expected_pre_sha256,
            "backup_path": str(backup_path),
            "backup_sha256": _sha256_file(backup_path),
            "pre_integrity_check": pre_integrity,
            "backup_integrity_check": backup_integrity,
        }
    )
    return metadata


def _is_cash_account(account: str | None) -> bool:
    if not account:
        return False
    if account == "CASH":
        return True
    if account.startswith("KASPI_PAY"):
        return True
    if account.startswith("KASPI_GOLD"):
        return True
    if account.startswith("KZ"):
        return True
    return False


def _table_exists(conn: sqlite3.Connection, name: str) -> bool:
    return conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
        (name,),
    ).fetchone() is not None


def _get_columns(conn: sqlite3.Connection, table: str) -> set[str]:
    return {row[1] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}


def _parse_anchor_timestamp(value: str | None) -> datetime | None:
    if not value:
        return None
    match = ANCHOR_TIMESTAMP_RE.search(str(value))
    if not match:
        return None
    parts = {key: int(raw) for key, raw in match.groupdict().items()}
    return datetime(
        parts["year"],
        parts["month"],
        parts["day"],
        parts["hour"],
        parts["minute"],
        parts["second"],
    )


def _parse_event_timestamp(value: str | None) -> datetime | None:
    if not value:
        return None
    raw = str(value).strip()
    if not raw:
        return None
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is not None:
        return parsed.replace(tzinfo=None)
    return parsed


def _parse_note_amount(notes: str | None, key: str) -> float | None:
    if not notes:
        return None
    match = re.search(rf"{re.escape(key)}\s*=\s*([0-9]+(?:\.[0-9]+)?)", str(notes))
    if not match:
        return None
    return float(match.group(1))


def load_latest_actual_cash_anchor(
    conn: sqlite3.Connection,
    *,
    on_or_before: date | None = None,
) -> ActualCashAnchor | None:
    if not _table_exists(conn, "cashflow_cash_anchor"):
        return None
    cols = _get_columns(conn, "cashflow_cash_anchor")
    if "anchor_date" not in cols or "anchor_closing_balance_kzt" not in cols:
        return None

    trust_col = "trust_class" if "trust_class" in cols else "anchor_kind" if "anchor_kind" in cols else None
    status_col = (
        "reconciliation_status"
        if "reconciliation_status" in cols
        else "status"
        if "status" in cols
        else None
    )
    if not trust_col or not status_col:
        return None

    run_col = "created_by_run_id" if "created_by_run_id" in cols else "NULL"
    created_col = "created_at" if "created_at" in cols else "NULL"
    source_col = "source_store_dir" if "source_store_dir" in cols else "NULL"
    notes_col = "notes_redacted" if "notes_redacted" in cols else "NULL"
    params: list[object] = ["ACTUAL_ANCHOR", "RECONCILED"]
    date_filter = ""
    if on_or_before is not None:
        date_filter = "AND anchor_date <= ?"
        params.append(on_or_before.isoformat())

    row = conn.execute(
        f"""
        SELECT
            anchor_date,
            {run_col} AS run_id,
            COUNT(*) AS row_count,
            ROUND(SUM(anchor_closing_balance_kzt), 2) AS operating_cash_kzt,
            MAX({created_col}) AS created_at,
            MAX({source_col}) AS source_store_dir,
            MAX({notes_col}) AS notes_redacted
        FROM cashflow_cash_anchor
        WHERE {trust_col} = ?
          AND {status_col} = ?
          {date_filter}
        GROUP BY anchor_date, run_id
        HAVING row_count > 0
        ORDER BY anchor_date DESC, created_at DESC, run_id DESC
        LIMIT 1
        """,
        params,
    ).fetchone()
    if row is None:
        return None

    notes = row["notes_redacted"]
    return ActualCashAnchor(
        anchor_date=date.fromisoformat(str(row["anchor_date"])[:10]),
        operating_cash_kzt=float(row["operating_cash_kzt"] or 0.0),
        row_count=int(row["row_count"] or 0),
        run_id=row["run_id"],
        created_at=row["created_at"],
        anchor_ts=_parse_anchor_timestamp(row["source_store_dir"]),
        reserve_kzt=_parse_note_amount(notes, "reserve_kzt"),
        grand_total_with_reserve_kzt=_parse_note_amount(notes, "grand_total_with_reserve_kzt"),
    )


def _event_day(event: dict) -> date:
    return date.fromisoformat(_normalize_date(event.get("event_date"))[:10])


def _cash_event_applies_after_anchor(event: dict, anchor: ActualCashAnchor | None) -> bool:
    if anchor is None or not _is_cash_account(event.get("account")):
        return True

    event_date = _event_day(event)
    if event_date < anchor.anchor_date:
        return True
    if event_date > anchor.anchor_date:
        return True
    if anchor.anchor_ts is None:
        return False

    event_ts = _parse_event_timestamp(event.get("event_ts"))
    return bool(event_ts and event_ts > anchor.anchor_ts)


def _effective_events_for_cash_anchor(
    events: list[dict],
    anchor: ActualCashAnchor | None,
) -> list[dict]:
    if anchor is None:
        return events
    return [event for event in events if _cash_event_applies_after_anchor(event, anchor)]


def _is_modelled_cash_in(event: dict) -> bool:
    return (
        str(event.get("event_type") or "").upper() == "CASH_IN"
        and float(event.get("amount_kzt") or 0.0) > 0
        and "MODEL" in str(event.get("source") or "").upper()
    )


def _cash_delta_after_anchor_before_start(
    conn: sqlite3.Connection,
    anchor: ActualCashAnchor,
    start_date: date,
) -> float:
    if start_date <= anchor.anchor_date:
        return 0.0
    events = _fetch_manual_events(conn, anchor.anchor_date, start_date - timedelta(days=1))
    return round(
        sum(
            float(event.get("amount_kzt") or 0.0)
            for event in events
            if _is_cash_account(event.get("account"))
            and _cash_event_applies_after_anchor(event, anchor)
        ),
        2,
    )


def _apply_cash_anchor_opening_state(
    conn: sqlite3.Connection,
    start_date: date,
    opening_state: dict[str, float] | None,
    anchor: ActualCashAnchor | None,
) -> dict[str, float] | None:
    if anchor is None or start_date < anchor.anchor_date:
        return opening_state
    state = dict(opening_state or {})
    state["cash_open"] = round(
        anchor.operating_cash_kzt + _cash_delta_after_anchor_before_start(conn, anchor, start_date),
        2,
    )
    return state


def rebase_daily_history_to_cash_anchor(
    conn: sqlite3.Connection,
    history_rows: list[dict],
    anchor: ActualCashAnchor | None = None,
) -> tuple[list[dict], dict[str, object]]:
    if not history_rows:
        return history_rows, {"anchor_date": None}

    first_date = date.fromisoformat(str(history_rows[0]["date"])[:10])
    last_date = date.fromisoformat(str(history_rows[-1]["date"])[:10])
    anchor = anchor or load_latest_actual_cash_anchor(conn, on_or_before=last_date)
    if anchor is None or last_date < anchor.anchor_date:
        return history_rows, {"anchor_date": None}

    events = _fetch_manual_events(conn, anchor.anchor_date, last_date)
    cash_delta_by_date: dict[str, float] = {}
    modelled_cash_in_kzt = 0.0
    for event in events:
        if not _is_cash_account(event.get("account")):
            continue
        if not _cash_event_applies_after_anchor(event, anchor):
            continue
        day_key = _event_day(event).isoformat()
        amount = float(event.get("amount_kzt") or 0.0)
        cash_delta_by_date[day_key] = cash_delta_by_date.get(day_key, 0.0) + amount
        if _is_modelled_cash_in(event):
            modelled_cash_in_kzt += amount

    cash_close = round(anchor.operating_cash_kzt, 2)
    if first_date > anchor.anchor_date:
        for day_key, amount in cash_delta_by_date.items():
            if anchor.anchor_date < date.fromisoformat(day_key) < first_date:
                cash_close += amount

    rebased_rows: list[dict] = []
    touched = 0
    for row in history_rows:
        updated = dict(row)
        row_date = date.fromisoformat(str(updated["date"])[:10])
        if row_date >= anchor.anchor_date:
            cash_open = cash_close
            cash_flow = round(cash_delta_by_date.get(row_date.isoformat(), 0.0), 2)
            cash_close = round(cash_open + cash_flow, 2)
            updated["cash_open"] = round(cash_open, 2)
            updated["cash_flow_kzt"] = cash_flow
            updated["cash_close"] = cash_close
            if "capital_close" in updated:
                receivables_close = float(updated.get("receivables_close") or 0.0)
                inventory_close = float(updated.get("inventory_cost_close") or 0.0)
                updated["capital_close"] = round(cash_close + receivables_close + inventory_close, 2)
            touched += 1
        rebased_rows.append(updated)

    return rebased_rows, {
        "anchor_date": anchor.anchor_date.isoformat(),
        "anchor_opening_cash_kzt": round(anchor.operating_cash_kzt, 2),
        "anchor_row_count": anchor.row_count,
        "anchor_run_id": anchor.run_id,
        "modelled_cash_in_after_anchor": modelled_cash_in_kzt > 0,
        "modelled_cash_in_after_anchor_kzt": round(modelled_cash_in_kzt, 2),
        "rebased_history_rows": touched,
    }


def _missing_daily_columns(conn: sqlite3.Connection) -> list[str]:
    return sorted(DAILY_REQUIRED_COLUMNS - _get_columns(conn, "fact_cashflow_daily"))


def _raise_missing_daily_columns(missing: list[str]) -> None:
    missing_list = ", ".join(missing)
    raise RuntimeError(
        "fact_cashflow_daily missing required columns "
        f"({missing_list}); run the reviewed cashflow schema migration before rebuild."
    )


def _validate_daily_columns(conn: sqlite3.Connection) -> None:
    missing = _missing_daily_columns(conn)
    if missing:
        _raise_missing_daily_columns(missing)


def _ensure_daily_columns(conn: sqlite3.Connection, *, allow_schema_write: bool) -> None:
    if not allow_schema_write:
        _validate_daily_columns(conn)
        return
    cols = _get_columns(conn, "fact_cashflow_daily")
    for name, ddl in DAILY_AUTO_MIGRATE_COLUMNS.items():
        if name not in cols:
            conn.execute(f"ALTER TABLE fact_cashflow_daily ADD COLUMN {name} {ddl}")
    _validate_daily_columns(conn)


def _normalize_date(value: str | date | datetime) -> str:
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    return str(value)


def _event_hash(event: dict) -> str:
    parts = [
        _normalize_date(event.get("event_date")),
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


def _detect_sales_source(conn: sqlite3.Connection) -> Optional[dict]:
    candidates = [
        ("fact_sales", {"date": ["order_date", "sale_date"], "qty": ["quantity", "qty"]}),
        ("sales_fact_v2", {"date": ["order_date", "sale_date"], "qty": ["quantity", "qty"]}),
    ]
    for table, req in candidates:
        if not _table_exists(conn, table):
            continue
        cols = _get_columns(conn, table)
        date_col = next((c for c in req["date"] if c in cols), None)
        qty_col = next((c for c in req["qty"] if c in cols), None)
        if not date_col or not qty_col:
            continue
        return {"table": table, "date_col": date_col, "qty_col": qty_col, "cols": cols}
    return None


def _get_net_rev_expression(cols: set[str], qty_col: str) -> tuple[str, bool]:
    line_cols = ["line_net_rev", "line_net_revenue", "line_net_rev_kzt"]
    unit_cols = ["net_rev_unit", "net_revenue_unit", "net_rev_kzt", "net_revenue"]
    for col in line_cols:
        if col in cols:
            return f"{col}", True
    for col in unit_cols:
        if col in cols:
            return f"{col} * {qty_col}", True
    return "0", False


def _get_cogs_expression(cols: set[str], qty_col: str) -> tuple[str, bool]:
    unit_cols = ["cogs_unit", "unit_cogs"]
    for col in unit_cols:
        if col in cols:
            return f"{col} * {qty_col}", True
    return "0", False


def _load_dim_sku_costs(conn: sqlite3.Connection) -> dict[str, dict]:
    if not _table_exists(conn, "dim_sku"):
        return {}
    rows = conn.execute(
        "SELECT sku_key, cogs_kzt, base_cost_cny, weight_kg FROM dim_sku"
    ).fetchall()
    return {
        row["sku_key"]: {
            "cogs_kzt": row["cogs_kzt"] or 0.0,
            "base_cost_cny": row["base_cost_cny"] or 0.0,
            "weight_kg": row["weight_kg"] or 0.0,
        }
        for row in rows
    }


def _build_sales_aggregates(
    conn: sqlite3.Connection,
    start_date: date,
    end_date: date,
    fx_rates,
) -> tuple[dict[str, float], dict[str, float]]:
    source = _detect_sales_source(conn)
    if not source:
        return {}, {}

    table = source["table"]
    date_col = source["date_col"]
    qty_col = source["qty_col"]
    cols = source["cols"]
    store_col = "store_code" if "store_code" in cols else None
    sku_key_col = "sku_key" if "sku_key" in cols else None
    sku_id_col = "sku_id" if "sku_id" in cols else None

    net_rev_expr, has_net_rev = _get_net_rev_expression(cols, qty_col)
    cogs_expr, has_cogs = _get_cogs_expression(cols, qty_col)

    select_cols = [
        f"{date_col} as sale_date",
        f"{qty_col} as quantity",
        f"{net_rev_expr} as line_net_rev",
        f"{cogs_expr} as line_cogs",
    ]
    if store_col:
        select_cols.append(f"{store_col} as store_code")
    else:
        select_cols.append("NULL as store_code")
    if sku_key_col:
        select_cols.append(f"{sku_key_col} as sku_key")
    else:
        select_cols.append("NULL as sku_key")
    if sku_id_col:
        select_cols.append(f"{sku_id_col} as sku_id")
    else:
        select_cols.append("NULL as sku_id")

    query = f"""
        SELECT {", ".join(select_cols)}
        FROM {table}
        WHERE {date_col} BETWEEN ? AND ?
    """

    dim_costs = _load_dim_sku_costs(conn)
    sales_by_date: dict[str, float] = {}
    cogs_by_date: dict[str, float] = {}

    rows = conn.execute(query, (start_date.isoformat(), end_date.isoformat())).fetchall()
    for row in rows:
        sale_date = row["sale_date"]
        if not sale_date:
            continue
        qty = float(row["quantity"] or 0.0)
        if qty <= 0:
            continue
        line_net = float(row["line_net_rev"] or 0.0)
        line_cogs = float(row["line_cogs"] or 0.0)

        if not has_net_rev:
            line_net = 0.0
        if not has_cogs:
            sku_key = row["sku_key"]
            meta = dim_costs.get(sku_key or "", {})
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
            line_cogs = cogs_unit * qty

        sales_by_date[sale_date] = sales_by_date.get(sale_date, 0.0) + line_net
        cogs_by_date[sale_date] = cogs_by_date.get(sale_date, 0.0) + line_cogs

    return sales_by_date, cogs_by_date


def _inventory_anchor_date(conn: sqlite3.Connection) -> date | None:
    if not _table_exists(conn, "fact_cashflow_events"):
        return None
    row = conn.execute(
        """
        SELECT MAX(event_date) as max_date
        FROM fact_cashflow_events
        WHERE account IN ('INVENTORY_COST', 'INVENTORY_ON_HAND_COST', 'INVENTORY_INBOUND_COST', 'INVENTORY_ON_DELIVERY_COST')
          AND event_type IN ('INVENTORY_OPEN', 'OPENING_BALANCE')
        """
    ).fetchone()
    if row and row["max_date"]:
        return date.fromisoformat(row["max_date"])
    return None


def _has_order_modelled_events(
    conn: sqlite3.Connection,
    start_date: date,
    end_date: date,
) -> bool:
    if not _table_exists(conn, "fact_cashflow_events"):
        return False
    row = conn.execute(
        """
        SELECT 1
        FROM fact_cashflow_events
        WHERE event_date BETWEEN ? AND ?
          AND source = 'ORDER_MODELLED'
          AND event_type IN ('CASH_IN', 'INVENTORY_MOVE', 'INVENTORY_RETURN')
        LIMIT 1
        """,
        (start_date.isoformat(), end_date.isoformat()),
    ).fetchone()
    return row is not None


def _build_system_events(
    conn: sqlite3.Connection,
    start_date: date,
    end_date: date,
    fx_rates,
    run_id: str,
    *,
    skip_sales: bool = False,
) -> list[dict]:
    if skip_sales:
        return []
    sales_by_date, cogs_by_date = _build_sales_aggregates(conn, start_date, end_date, fx_rates)
    inventory_anchor_date = _inventory_anchor_date(conn)
    events: list[dict] = []
    for sale_date, amount in cogs_by_date.items():
        if amount == 0:
            continue
        if inventory_anchor_date and date.fromisoformat(sale_date) < inventory_anchor_date:
            continue
        events.append(
            {
                "event_date": sale_date,
                "event_type": "COGS_RECOGNIZED",
                "account": "INVENTORY_ON_DELIVERY_COST",
                "amount_kzt": round(-abs(amount), 2),
                "source": "SYSTEM",
                "run_id": run_id,
            }
        )
    return events


def _fetch_manual_events(
    conn: sqlite3.Connection,
    start_date: date,
    end_date: date,
) -> list[dict]:
    if not _table_exists(conn, "fact_cashflow_events"):
        return []
    cols = _get_columns(conn, "fact_cashflow_events")
    event_ts_select = "event_ts" if "event_ts" in cols else "NULL AS event_ts"
    rows = conn.execute(
        f"""
        SELECT event_date, {event_ts_select}, event_type, account, amount_kzt, store_code, sku_key, sku_id,
               ref_type, ref_id, notes, source, run_id, event_hash
        FROM fact_cashflow_events
        WHERE event_date BETWEEN ? AND ?
          AND NOT (source = 'SYSTEM' AND event_type IN ('COGS_RECOGNIZED'))
        """,
        (start_date.isoformat(), end_date.isoformat()),
    ).fetchall()
    events = []
    for row in rows:
        events.append(dict(row))
    return events


def _date_range(start: date, end: date) -> Iterable[date]:
    current = start
    while current <= end:
        yield current
        current += timedelta(days=1)


def _is_legacy_order_modelled_receivables(event: dict) -> bool:
    return (
        str(event.get("account") or "").upper() == "RECEIVABLES"
        and str(event.get("source") or "").upper() == "ORDER_MODELLED"
    )


def _count_ignored_legacy_receivables(events: list[dict]) -> tuple[int, float]:
    count = 0
    amount = 0.0
    for event in events:
        if _is_legacy_order_modelled_receivables(event):
            count += 1
            amount += float(event.get("amount_kzt", 0.0) or 0.0)
    return count, round(amount, 2)


def compute_daily_rows(
    events: list[dict],
    start_date: date,
    end_date: date,
    run_id: Optional[str] = None,
    opening_state: dict[str, float] | None = None,
    cash_anchor: ActualCashAnchor | None = None,
) -> list[dict]:
    events_by_date: dict[str, list[dict]] = {}
    for event in events:
        key = _normalize_date(event["event_date"])
        events_by_date.setdefault(key, []).append(event)

    daily_rows = []
    opening_state = opening_state or {}
    cash_open = float(opening_state.get("cash_open", 0.0) or 0.0)
    receivables_open = float(opening_state.get("receivables_open", 0.0) or 0.0)
    inv_on_hand_open = float(opening_state.get("inventory_on_hand_open", 0.0) or 0.0)
    inv_inbound_open = float(opening_state.get("inventory_inbound_open", 0.0) or 0.0)
    inv_on_delivery_open = float(opening_state.get("inventory_on_delivery_open", 0.0) or 0.0)

    for day in _date_range(start_date, end_date):
        day_key = day.isoformat()
        if cash_anchor is not None and day == cash_anchor.anchor_date:
            cash_open = round(cash_anchor.operating_cash_kzt, 2)
        day_events = _effective_events_for_cash_anchor(events_by_date.get(day_key, []), cash_anchor)
        cash_flow = sum(
            e.get("amount_kzt", 0.0)
            for e in day_events
            if _is_cash_account(e.get("account"))
        )
        recv_flow = sum(
            e.get("amount_kzt", 0.0)
            for e in day_events
            if e.get("account") == "RECEIVABLES"
            and not _is_legacy_order_modelled_receivables(e)
        )
        legacy_inv_flow = sum(
            e.get("amount_kzt", 0.0)
            for e in day_events
            if e.get("account") == "INVENTORY_COST"
        )
        inv_on_hand_flow = sum(
            e.get("amount_kzt", 0.0)
            for e in day_events
            if e.get("account") == "INVENTORY_ON_HAND_COST"
        ) + legacy_inv_flow
        inv_inbound_flow = sum(
            e.get("amount_kzt", 0.0)
            for e in day_events
            if e.get("account") == "INVENTORY_INBOUND_COST"
        )
        inv_on_delivery_flow = sum(
            e.get("amount_kzt", 0.0)
            for e in day_events
            if e.get("account") == "INVENTORY_ON_DELIVERY_COST"
        )
        inv_flow = inv_on_hand_flow + inv_inbound_flow + inv_on_delivery_flow

        cash_close = cash_open + cash_flow
        receivables_close = receivables_open + recv_flow
        inv_on_hand_close = inv_on_hand_open + inv_on_hand_flow
        inv_inbound_close = inv_inbound_open + inv_inbound_flow
        inv_on_delivery_close = inv_on_delivery_open + inv_on_delivery_flow
        inventory_open = inv_on_hand_open + inv_inbound_open + inv_on_delivery_open
        inventory_close = inv_on_hand_close + inv_inbound_close + inv_on_delivery_close

        sales_accrued = sum(
            e.get("amount_kzt", 0.0)
            for e in day_events
            if e.get("event_type") == "CASH_IN"
        )
        payouts_received = sum(
            e.get("amount_kzt", 0.0)
            for e in day_events
            if e.get("event_type") in PAYOUT_EVENT_TYPES or e.get("event_type") == "CASH_IN"
        )
        refunds = abs(
            sum(
                e.get("amount_kzt", 0.0)
                for e in day_events
                if e.get("event_type") == "REFUND"
                or (e.get("event_type") == "CASH_IN" and (e.get("amount_kzt", 0.0) or 0.0) < 0)
            )
        )
        po_payments = abs(sum(e.get("amount_kzt", 0.0) for e in day_events if e.get("event_type") == "PO_PAYMENT"))
        expenses = abs(
            sum(
                e.get("amount_kzt", 0.0)
                for e in day_events
                if e.get("event_type") in EXPENSE_EVENT_TYPES
            )
        )
        cogs = abs(sum(e.get("amount_kzt", 0.0) for e in day_events if e.get("event_type") == "COGS_RECOGNIZED"))

        profit_accrual = sales_accrued - cogs - expenses
        capital_close = cash_close + receivables_close + inventory_close

        daily_rows.append(
            {
                "date": day_key,
                "cash_open": round(cash_open, 2),
                "cash_close": round(cash_close, 2),
                "receivables_open": round(receivables_open, 2),
                "receivables_close": round(receivables_close, 2),
                "inventory_cost_open": round(inventory_open, 2),
                "inventory_cost_close": round(inventory_close, 2),
                "inventory_on_hand_open": round(inv_on_hand_open, 2),
                "inventory_on_hand_close": round(inv_on_hand_close, 2),
                "inventory_inbound_open": round(inv_inbound_open, 2),
                "inventory_inbound_close": round(inv_inbound_close, 2),
                "inventory_on_delivery_open": round(inv_on_delivery_open, 2),
                "inventory_on_delivery_close": round(inv_on_delivery_close, 2),
                "capital_close": round(capital_close, 2),
                "sales_accrued_kzt": round(sales_accrued, 2),
                "payouts_received_kzt": round(payouts_received, 2),
                "refunds_kzt": round(refunds, 2),
                "po_payments_kzt": round(po_payments, 2),
                "expenses_kzt": round(expenses, 2),
                "cogs_kzt": round(cogs, 2),
                "cash_flow_kzt": round(cash_flow, 2),
                "receivables_flow_kzt": round(recv_flow, 2),
                "inventory_cost_flow_kzt": round(inv_flow, 2),
                "profit_accrual_kzt": round(profit_accrual, 2),
                "run_id": run_id or "",
            }
        )

        cash_open = cash_close
        receivables_open = receivables_close
        inv_on_hand_open = inv_on_hand_close
        inv_inbound_open = inv_inbound_close
        inv_on_delivery_open = inv_on_delivery_close

    return daily_rows


def _load_opening_state(
    conn: sqlite3.Connection,
    start_date: date,
) -> dict[str, float] | None:
    if not _table_exists(conn, "fact_cashflow_daily"):
        return None
    previous_date = (start_date - timedelta(days=1)).isoformat()
    row = conn.execute(
        """
        SELECT cash_close, receivables_close, inventory_on_hand_close,
               inventory_inbound_close, inventory_on_delivery_close
        FROM fact_cashflow_daily
        WHERE date = ?
        """,
        (previous_date,),
    ).fetchone()
    if row is None:
        return None
    return {
        "cash_open": float(row["cash_close"] or 0.0),
        "receivables_open": float(row["receivables_close"] or 0.0),
        "inventory_on_hand_open": float(row["inventory_on_hand_close"] or 0.0),
        "inventory_inbound_open": float(row["inventory_inbound_close"] or 0.0),
        "inventory_on_delivery_open": float(row["inventory_on_delivery_close"] or 0.0),
    }


def rebuild_cashflow_calendar(
    db_path: Path,
    start_date: date,
    end_date: date,
    apply: bool,
    run_id: str,
    *,
    expected_pre_sha256: str | None = None,
    backup_dir: Path | None = None,
) -> tuple[list[dict], list[dict]]:
    if not db_path.exists():
        raise FileNotFoundError(f"DB not found: {db_path}")
    rebuild_cashflow_calendar.last_apply_metadata = {}
    rebuild_cashflow_calendar.last_cash_anchor = None
    apply_metadata: dict[str, object] = {}
    if apply:
        apply_metadata = _prepare_cashflow_rebuild_apply_guard(
            db_path,
            expected_pre_sha256=expected_pre_sha256,
            backup_dir=backup_dir,
        )

    fx_rates = get_fx_rates(end_date, db_path=db_path)
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    try:
        if not _table_exists(conn, "fact_cashflow_events"):
            raise RuntimeError("fact_cashflow_events missing; run migrate_018_cashflow_calendar.py")
        if not _table_exists(conn, "fact_cashflow_daily"):
            raise RuntimeError("fact_cashflow_daily missing; run migrate_018_cashflow_calendar.py")
        if apply:
            _ensure_daily_columns(conn, allow_schema_write=True)
        else:
            _validate_daily_columns(conn)
        skip_sales = _has_order_modelled_events(conn, start_date, end_date)
        system_events = _build_system_events(
            conn,
            start_date,
            end_date,
            fx_rates,
            run_id,
            skip_sales=skip_sales,
        )
        manual_events = _fetch_manual_events(conn, start_date, end_date)
        inventory_anchor_date = _inventory_anchor_date(conn)
        if inventory_anchor_date:
            anchor_key = inventory_anchor_date.isoformat()
            manual_events = [
                e
                for e in manual_events
                if not (
                    e.get("account") in INVENTORY_ACCOUNTS
                    and _normalize_date(e.get("event_date")) < anchor_key
                )
            ]
        all_events = manual_events + system_events

        if apply:
            conn.execute(
                """
                DELETE FROM fact_cashflow_events
                WHERE event_date BETWEEN ? AND ?
                  AND source = 'SYSTEM'
                  AND event_type IN ('COGS_RECOGNIZED')
                """,
                (start_date.isoformat(), end_date.isoformat()),
            )
            for event in system_events:
                event["event_hash"] = _event_hash(event)
                conn.execute(
                    """
                    INSERT OR IGNORE INTO fact_cashflow_events (
                        event_date, event_type, account, amount_kzt, store_code, sku_key, sku_id,
                        ref_type, ref_id, notes, source, run_id, event_hash
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        _normalize_date(event["event_date"]),
                        event["event_type"],
                        event["account"],
                        float(event["amount_kzt"]),
                        event.get("store_code"),
                        event.get("sku_key"),
                        event.get("sku_id"),
                        event.get("ref_type"),
                        event.get("ref_id"),
                        event.get("notes"),
                        event.get("source", "SYSTEM"),
                        event.get("run_id", run_id),
                        event["event_hash"],
                    ),
                )

        cash_anchor = load_latest_actual_cash_anchor(conn, on_or_before=end_date)
        rebuild_cashflow_calendar.last_cash_anchor = cash_anchor
        opening_state = _load_opening_state(conn, start_date)
        opening_state = _apply_cash_anchor_opening_state(conn, start_date, opening_state, cash_anchor)
        daily_rows = compute_daily_rows(
            all_events,
            start_date,
            end_date,
            run_id=run_id,
            opening_state=opening_state,
            cash_anchor=cash_anchor,
        )

        if apply:
            conn.execute(
                "DELETE FROM fact_cashflow_daily WHERE date BETWEEN ? AND ?",
                (start_date.isoformat(), end_date.isoformat()),
            )
            for row in daily_rows:
                conn.execute(
                    """
                    INSERT OR REPLACE INTO fact_cashflow_daily (
                        date, cash_open, cash_close, receivables_open, receivables_close,
                        inventory_cost_open, inventory_cost_close, capital_close,
                        inventory_on_hand_open, inventory_on_hand_close,
                        inventory_inbound_open, inventory_inbound_close,
                        inventory_on_delivery_open, inventory_on_delivery_close,
                        sales_accrued_kzt, payouts_received_kzt, refunds_kzt, po_payments_kzt,
                        expenses_kzt, cogs_kzt, cash_flow_kzt, receivables_flow_kzt,
                        inventory_cost_flow_kzt, profit_accrual_kzt, run_id
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        row["date"],
                        row["cash_open"],
                        row["cash_close"],
                        row["receivables_open"],
                        row["receivables_close"],
                        row["inventory_cost_open"],
                        row["inventory_cost_close"],
                        row["capital_close"],
                        row["inventory_on_hand_open"],
                        row["inventory_on_hand_close"],
                        row["inventory_inbound_open"],
                        row["inventory_inbound_close"],
                        row["inventory_on_delivery_open"],
                        row["inventory_on_delivery_close"],
                        row["sales_accrued_kzt"],
                        row["payouts_received_kzt"],
                        row["refunds_kzt"],
                        row["po_payments_kzt"],
                        row["expenses_kzt"],
                        row["cogs_kzt"],
                        row["cash_flow_kzt"],
                        row["receivables_flow_kzt"],
                        row["inventory_cost_flow_kzt"],
                        row["profit_accrual_kzt"],
                        row["run_id"],
                    ),
                )

        if apply:
            conn.commit()
    finally:
        conn.close()

    if apply_metadata:
        rebuild_cashflow_calendar.last_apply_metadata = apply_metadata
    if apply_metadata.get("production_apply"):
        post_integrity = _sqlite_integrity_check(db_path)
        if post_integrity.lower() != "ok":
            raise RuntimeError(f"production DB integrity_check failed after cashflow rebuild: {post_integrity}")
        apply_metadata["post_sha256"] = _sha256_file(db_path)
        apply_metadata["post_integrity_check"] = post_integrity
        rebuild_cashflow_calendar.last_apply_metadata = apply_metadata

    return daily_rows, system_events


def _resolve_start_end(conn: sqlite3.Connection) -> tuple[date, date]:
    cutoff = get_cutoff_date_almaty()
    start = cutoff
    if _table_exists(conn, "fact_cashflow_events"):
        row = conn.execute(
            "SELECT MIN(event_date) AS min_date FROM fact_cashflow_events"
        ).fetchone()
        if row and row["min_date"]:
            start = min(start, date.fromisoformat(row["min_date"]))
    source = _detect_sales_source(conn)
    if source:
        row = conn.execute(
            f"SELECT MIN({source['date_col']}) AS min_date FROM {source['table']}"
        ).fetchone()
        if row and row["min_date"]:
            start = min(start, date.fromisoformat(row["min_date"]))
    return start, cutoff


def main() -> int:
    parser = argparse.ArgumentParser(description="Rebuild cashflow calendar")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB, help="Path to SQLite DB")
    parser.add_argument("--start-date", type=str, help="Start date (YYYY-MM-DD)")
    parser.add_argument("--end-date", type=str, help="End date (YYYY-MM-DD)")
    parser.add_argument("--apply", action="store_true", help="Write derived tables/events (requires ENABLE_CASHFLOW_WRITE=1)")
    parser.add_argument("--run-id", type=str, default=None, help="Run id for audit")
    parser.add_argument("--expected-pre-sha256", type=str, default=None)
    parser.add_argument("--backup-dir", type=Path, default=None)
    args = parser.parse_args()

    conn = sqlite3.connect(str(args.db))
    conn.row_factory = sqlite3.Row
    try:
        if args.start_date and args.end_date:
            start = date.fromisoformat(args.start_date)
            end = date.fromisoformat(args.end_date)
        else:
            start, end = _resolve_start_end(conn)
    finally:
        conn.close()

    run_id = args.run_id or datetime.now().strftime("%Y%m%d_%H%M%S")
    daily_rows, system_events = rebuild_cashflow_calendar(
        args.db,
        start,
        end,
        args.apply,
        run_id,
        expected_pre_sha256=args.expected_pre_sha256,
        backup_dir=args.backup_dir,
    )
    ignored_count, ignored_amount = (0, 0.0)
    with sqlite3.connect(str(args.db)) as conn:
        conn.row_factory = sqlite3.Row
        if _table_exists(conn, "fact_cashflow_events"):
            rows = conn.execute(
                """
                SELECT account, source, amount_kzt
                FROM fact_cashflow_events
                WHERE event_date BETWEEN ? AND ?
                """,
                (start.isoformat(), end.isoformat()),
            ).fetchall()
            ignored_count, ignored_amount = _count_ignored_legacy_receivables(
                [dict(r) for r in rows]
            )

    print("Cashflow rebuild summary")
    print(f"  Range: {start.isoformat()} → {end.isoformat()}")
    print(f"  System events generated: {len(system_events)}")
    print(f"  legacy_receivables_ignored_count: {ignored_count}")
    print(f"  ignored_amount_kzt: {ignored_amount:.2f}")
    print(f"  Daily rows computed: {len(daily_rows)}")
    cash_anchor = getattr(rebuild_cashflow_calendar, "last_cash_anchor", None)
    if cash_anchor is not None:
        print(f"  Cash anchor rebase date: {cash_anchor.anchor_date.isoformat()}")
        print(f"  Cash anchor operating opening KZT: {cash_anchor.operating_cash_kzt:.2f}")
        print(f"  Cash anchor rows: {cash_anchor.row_count}")
    if args.apply:
        print("  APPLY: wrote SYSTEM events + daily table.")
        metadata = getattr(rebuild_cashflow_calendar, "last_apply_metadata", {})
        if metadata.get("production_apply"):
            print(f"  Production pre SHA256: {metadata.get('pre_sha256')}")
            print(f"  Production post SHA256: {metadata.get('post_sha256')}")
            print(f"  Production backup path: {metadata.get('backup_path')}")
            print(f"  Production backup SHA256: {metadata.get('backup_sha256')}")
            print(f"  Production integrity check: {metadata.get('post_integrity_check')}")
    else:
        print("  DRY RUN: no DB writes.")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
