"""Refund reserve helpers (conservative scenario liability)."""
from __future__ import annotations

from collections import deque
from datetime import date, timedelta


def compute_refund_reserve_series(
    rows: list[dict],
    reserve_rate: float,
    window_days: int,
) -> dict[str, dict[str, float]]:
    """Compute refund reserve balance + delta by date.

    Reserve is derived from trailing net cash-in over window_days:
    reserve_kzt = max(0, sum(net_cash_in_lookback) * reserve_rate)
    """
    if reserve_rate <= 0 or window_days <= 0:
        return {str(r.get("date")): {"reserve_kzt": 0.0, "delta_kzt": 0.0} for r in rows if r.get("date")}

    series: dict[str, dict[str, float]] = {}
    window: deque[tuple[date, float]] = deque()
    window_sum = 0.0
    prev_reserve = 0.0

    for row in rows:
        day_str = row.get("date")
        if not day_str:
            continue
        day = date.fromisoformat(day_str)
        sales = float(row.get("sales_accrued_kzt") or 0.0)

        window.append((day, sales))
        window_sum += sales

        window_start = day - timedelta(days=window_days - 1)
        while window and window[0][0] < window_start:
            _, old_sales = window.popleft()
            window_sum -= old_sales

        reserve = max(0.0, window_sum * reserve_rate)
        delta = reserve - prev_reserve
        series[day_str] = {"reserve_kzt": reserve, "delta_kzt": delta}
        prev_reserve = reserve

    return series


def apply_refund_reserve(
    rows: list[dict],
    reserve_series: dict[str, dict[str, float]],
    reset_dates: set[str] | None = None,
) -> list[dict]:
    """Apply reserve deltas to cashflow rows (conservative scenario)."""
    reset_dates = reset_dates or set()
    out: list[dict] = []
    cash_open = None
    for row in rows:
        day_key = row.get("date")
        if not day_key:
            out.append(row)
            continue
        reserve = reserve_series.get(day_key, {}).get("reserve_kzt", 0.0)
        delta = reserve_series.get(day_key, {}).get("delta_kzt", 0.0)

        if cash_open is None or day_key in reset_dates:
            cash_open = float(row.get("cash_open") or 0.0)
            if day_key in reset_dates:
                delta = reserve
        cash_flow = float(row.get("cash_flow_kzt") or 0.0) - float(delta)
        cash_close = cash_open + cash_flow

        updated = dict(row)
        updated["cash_open"] = round(cash_open, 2)
        updated["cash_flow_kzt"] = round(cash_flow, 2)
        updated["cash_close"] = round(cash_close, 2)
        updated["refund_reserve_kzt"] = round(reserve, 2)
        updated["refund_reserve_delta_kzt"] = round(delta, 2)

        receivables_close = float(updated.get("receivables_close") or 0.0)
        inventory_close = float(updated.get("inventory_cost_close") or 0.0)
        updated["capital_close"] = round(cash_close + receivables_close + inventory_close, 2)

        out.append(updated)
        cash_open = cash_close

    return out
