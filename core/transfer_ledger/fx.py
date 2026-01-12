"""FX snapshot helper for transfer ledger."""

from __future__ import annotations

from datetime import date, datetime
from pathlib import Path
from typing import Optional

from core.db import get_db, DEFAULT_DB_PATH


def _normalize_date(value: Optional[date | datetime]) -> str:
    if value is None:
        return date.today().isoformat()
    if isinstance(value, datetime):
        value = value.date()
    return value.isoformat()


def get_fx_snapshot(
    as_of_date: Optional[date | datetime] = None,
    db_path: Optional[Path] = None,
) -> Optional[dict]:
    """
    Fetch the most recent FX row where effective_date <= as_of_date.

    Returns None if dim_fx_rates is missing or empty.
    """
    path = db_path or DEFAULT_DB_PATH
    as_of = _normalize_date(as_of_date)

    with get_db(path) as conn:
        table = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='dim_fx_rates'"
        ).fetchone()
        if not table:
            return None
        row = conn.execute(
            """
            SELECT effective_date, usdt_kzt, usdt_cny, cny_kzt, usd_kzt, dlv_rate_usd_kg,
                   provider, source, updated_at
            FROM dim_fx_rates
            WHERE effective_date <= ?
            ORDER BY effective_date DESC
            LIMIT 1
            """,
            (as_of,),
        ).fetchone()
        if not row:
            row = conn.execute(
                """
                SELECT effective_date, usdt_kzt, usdt_cny, cny_kzt, usd_kzt, dlv_rate_usd_kg,
                       provider, source, updated_at
                FROM dim_fx_rates
                ORDER BY effective_date ASC
                LIMIT 1
                """
            ).fetchone()
            if not row:
                return None
        return {
            "effective_date": row["effective_date"],
            "usdt_kzt": row["usdt_kzt"],
            "usdt_cny": row["usdt_cny"],
            "cny_kzt": row["cny_kzt"],
            "usd_kzt": row["usd_kzt"],
            "dlv_rate_usd_kg": row["dlv_rate_usd_kg"],
            "provider": row["provider"],
            "source": row["source"],
            "updated_at": row["updated_at"],
        }
