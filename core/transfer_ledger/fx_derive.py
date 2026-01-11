"""Derive daily FX rates from Binance P2P and exchanger emails."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Iterable, Optional

from core.db import get_db, DEFAULT_DB_PATH
from core.config.business_params import DEFAULT_FX_RATES


@dataclass(frozen=True)
class DerivedRate:
    effective_date: date
    rate: float
    count: int
    total_base: float
    total_quote: float


def _to_date(value) -> Optional[date]:
    if value is None:
        return None
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    if isinstance(value, datetime):
        return value.date()
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).date()
    except Exception:
        return None


def _in_range(d: date, start: Optional[date], end: Optional[date]) -> bool:
    if start and d < start:
        return False
    if end and d > end:
        return False
    return True


def derive_daily_usdt_kzt(
    db_path: Optional[Path] = None,
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    min_count: int = 1,
) -> dict[date, DerivedRate]:
    """Derive daily USDT/KZT from Binance P2P BUY orders (weighted average)."""
    path = db_path or DEFAULT_DB_PATH
    with get_db(path) as conn:
        rows = conn.execute(
            """
            SELECT create_time, fiat_amount, crypto_amount, trade_type, asset, fiat, order_status
            FROM binance_c2c_orders
            WHERE trade_type = 'BUY' AND asset = 'USDT' AND fiat = 'KZT'
              AND order_status = 'COMPLETED'
            """
        ).fetchall()

    totals: dict[date, dict[str, float]] = {}
    counts: dict[date, int] = {}
    for row in rows:
        d = _to_date(row["create_time"])
        if not d or not _in_range(d, start_date, end_date):
            continue
        fiat = float(row["fiat_amount"] or 0.0)
        crypto = float(row["crypto_amount"] or 0.0)
        if crypto <= 0:
            continue
        totals.setdefault(d, {"fiat": 0.0, "crypto": 0.0})
        totals[d]["fiat"] += fiat
        totals[d]["crypto"] += crypto
        counts[d] = counts.get(d, 0) + 1

    out: dict[date, DerivedRate] = {}
    for d, tot in totals.items():
        if counts.get(d, 0) < min_count:
            continue
        rate = tot["fiat"] / tot["crypto"]
        out[d] = DerivedRate(
            effective_date=d,
            rate=rate,
            count=counts.get(d, 0),
            total_base=tot["crypto"],
            total_quote=tot["fiat"],
        )
    return out


def derive_daily_usdt_cny(
    db_path: Optional[Path] = None,
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    min_count: int = 1,
    include_statuses: Iterable[str] = ("COMPLETED",),
) -> dict[date, DerivedRate]:
    """Derive daily USDT/CNY from exchanger emails (weighted average)."""
    path = db_path or DEFAULT_DB_PATH
    statuses = {s.upper() for s in include_statuses}
    with get_db(path) as conn:
        rows = conn.execute(
            """
            SELECT message_date, amount_usdt, amount_cny, status
            FROM exchanger_orders
            WHERE amount_usdt IS NOT NULL AND amount_cny IS NOT NULL
            """
        ).fetchall()

    totals: dict[date, dict[str, float]] = {}
    counts: dict[date, int] = {}
    for row in rows:
        status = (row["status"] or "").upper()
        if statuses and status not in statuses:
            continue
        d = _to_date(row["message_date"])
        if not d or not _in_range(d, start_date, end_date):
            continue
        usdt = float(row["amount_usdt"] or 0.0)
        cny = float(row["amount_cny"] or 0.0)
        if usdt <= 0 or cny <= 0:
            continue
        totals.setdefault(d, {"usdt": 0.0, "cny": 0.0})
        totals[d]["usdt"] += usdt
        totals[d]["cny"] += cny
        counts[d] = counts.get(d, 0) + 1

    out: dict[date, DerivedRate] = {}
    for d, tot in totals.items():
        if counts.get(d, 0) < min_count:
            continue
        rate = tot["cny"] / tot["usdt"]
        out[d] = DerivedRate(
            effective_date=d,
            rate=rate,
            count=counts.get(d, 0),
            total_base=tot["usdt"],
            total_quote=tot["cny"],
        )
    return out


def _get_latest_usd_params(conn, effective_date: date) -> tuple[float, float]:
    try:
        table = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='dim_fx_rates'"
        ).fetchone()
        if not table:
            return float(DEFAULT_FX_RATES["usd_kzt"]), float(DEFAULT_FX_RATES["dlv_rate_usd_kg"])
        row = conn.execute(
            """
            SELECT usd_kzt, dlv_rate_usd_kg
            FROM dim_fx_rates
            WHERE effective_date <= ?
            ORDER BY effective_date DESC
            LIMIT 1
            """,
            (effective_date.isoformat(),),
        ).fetchone()
        if row:
            return float(row[0] or DEFAULT_FX_RATES["usd_kzt"]), float(row[1] or DEFAULT_FX_RATES["dlv_rate_usd_kg"])
    except Exception:
        pass
    return float(DEFAULT_FX_RATES["usd_kzt"]), float(DEFAULT_FX_RATES["dlv_rate_usd_kg"])


def derive_daily_fx_rows(
    db_path: Optional[Path] = None,
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    min_count: int = 1,
    include_statuses: Iterable[str] = ("COMPLETED",),
) -> list[dict]:
    """Return FX rows ready for upsert into dim_fx_rates."""
    path = db_path or DEFAULT_DB_PATH
    usdt_kzt = derive_daily_usdt_kzt(path, start_date, end_date, min_count)
    usdt_cny = derive_daily_usdt_cny(path, start_date, end_date, min_count, include_statuses)

    dates = sorted(set(usdt_kzt.keys()) & set(usdt_cny.keys()))
    if not dates:
        return []

    rows: list[dict] = []
    with get_db(path) as conn:
        for d in dates:
            rate_kzt = usdt_kzt[d].rate
            rate_cny = usdt_cny[d].rate
            if rate_kzt <= 0 or rate_cny <= 0:
                continue
            usd_kzt, dlv_rate = _get_latest_usd_params(conn, d)
            rows.append(
                {
                    "effective_date": d.isoformat(),
                    "usdt_kzt": rate_kzt,
                    "usdt_cny": rate_cny,
                    "cny_kzt": rate_kzt / rate_cny,
                    "usd_kzt": usd_kzt,
                    "dlv_rate_usd_kg": dlv_rate,
                    "provider": "AUTO",
                    "source": "Binance P2P + Exchanger emails",
                    "counts": {
                        "p2p_orders": usdt_kzt[d].count,
                        "exchanger_orders": usdt_cny[d].count,
                    },
                }
            )
    return rows
