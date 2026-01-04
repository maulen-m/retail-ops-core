"""Query helpers for analytics API endpoints."""
from __future__ import annotations

import sqlite3
from datetime import date, datetime, timedelta
from typing import Iterable, Optional
from zoneinfo import ZoneInfo

from .views import ensure_sales_views

ALMATY_TZ = ZoneInfo("Asia/Almaty")


def _table_exists(conn: sqlite3.Connection, name: str) -> bool:
    row = conn.execute(
        "SELECT name FROM sqlite_master WHERE type IN ('table','view') AND name = ?",
        (name,),
    ).fetchone()
    return row is not None


def _today_almaty() -> date:
    return datetime.now(ALMATY_TZ).date()


def _parse_date(value: Optional[str]) -> Optional[date]:
    if not value:
        return None
    return date.fromisoformat(value)


def _build_filter_clause(
    store_codes: Optional[Iterable[str]] = None,
    store_exclude: Optional[Iterable[str]] = None,
    sku_keys: Optional[Iterable[str]] = None,
    sku_exclude: Optional[Iterable[str]] = None,
    include_returns: bool = False,
) -> tuple[str, list]:
    clauses = []
    params: list = []
    if store_codes:
        store_list = [s for s in store_codes if s]
        if store_list:
            clauses.append("store_code IN (%s)" % ",".join(["?"] * len(store_list)))
            params.extend(store_list)
    if store_exclude:
        store_ex_list = [s for s in store_exclude if s]
        if store_ex_list:
            clauses.append("store_code NOT IN (%s)" % ",".join(["?"] * len(store_ex_list)))
            params.extend(store_ex_list)
    if sku_keys:
        sku_list = [s for s in sku_keys if s]
        if sku_list:
            clauses.append("sku_key IN (%s)" % ",".join(["?"] * len(sku_list)))
            params.extend(sku_list)
    if sku_exclude:
        sku_ex_list = [s for s in sku_exclude if s]
        if sku_ex_list:
            clauses.append("sku_key NOT IN (%s)" % ",".join(["?"] * len(sku_ex_list)))
            params.extend(sku_ex_list)
    if not include_returns:
        clauses.append("status NOT IN ('CANCELLED','RETURNED')")
    if clauses:
        return " AND " + " AND ".join(clauses), params
    return "", params


def _ensure_fx_coverage(
    conn: sqlite3.Connection,
    start_date: date,
    end_date: date,
    filter_clause: str,
    params: list,
) -> None:
    sql = (
        "SELECT COUNT(*) AS missing_count "
        "FROM v_sales_enriched "
        "WHERE order_date BETWEEN ? AND ? "
        "AND (fx_cny_kzt IS NULL OR fx_usd_kzt IS NULL OR fx_dlv_rate_usd_kg IS NULL)"
        f"{filter_clause}"
    )
    row = conn.execute(sql, [start_date.isoformat(), end_date.isoformat(), *params]).fetchone()
    if row and row[0] > 0:
        raise RuntimeError("FX rates missing for one or more sales rows in range")


def _ensure_fx_rate_for_date(conn: sqlite3.Connection, as_of_date: date) -> None:
    row = conn.execute(
        "SELECT 1 FROM dim_fx_rates WHERE effective_date <= ? ORDER BY effective_date DESC LIMIT 1",
        (as_of_date.isoformat(),),
    ).fetchone()
    if not row:
        raise RuntimeError("FX rates missing for inventory snapshot date")


def _latest_snapshot_date(
    conn: sqlite3.Connection,
    as_of_date: date,
    store_codes: Optional[Iterable[str]] = None,
    sku_keys: Optional[Iterable[str]] = None,
) -> Optional[date]:
    clause = []
    params: list = [as_of_date.isoformat()]
    if store_codes:
        clause.append("store_code IN (%s)" % ",".join(["?"] * len(store_codes)))
        params.extend(store_codes)
    if sku_keys:
        clause.append("sku_key IN (%s)" % ",".join(["?"] * len(sku_keys)))
        params.extend(sku_keys)
    where = ""
    if clause:
        where = " AND " + " AND ".join(clause)
    row = conn.execute(
        f"SELECT MAX(snapshot_date) FROM fact_inventory_snapshot WHERE snapshot_date <= ?{where}",
        params,
    ).fetchone()
    if not row or not row[0]:
        return None
    return date.fromisoformat(row[0])


def _inventory_cogs_for_date(
    conn: sqlite3.Connection,
    snapshot_date: date,
    store_codes: Optional[Iterable[str]] = None,
    sku_keys: Optional[Iterable[str]] = None,
) -> dict:
    _ensure_fx_rate_for_date(conn, snapshot_date)
    clause = []
    params: list = [snapshot_date.isoformat()]
    if store_codes:
        clause.append("s.store_code IN (%s)" % ",".join(["?"] * len(store_codes)))
        params.extend(store_codes)
    if sku_keys:
        clause.append("s.sku_key IN (%s)" % ",".join(["?"] * len(sku_keys)))
        params.extend(sku_keys)
    where = ""
    if clause:
        where = " AND " + " AND ".join(clause)

    sql = f"""
        SELECT
            SUM(s.current_stock * (sku.base_cost_cny * fx.cny_kzt + sku.weight_kg * fx.usd_kzt * fx.dlv_rate_usd_kg)) AS warehouse_cogs,
            SUM(s.inbound_stock * (sku.base_cost_cny * fx.cny_kzt + sku.weight_kg * fx.usd_kzt * fx.dlv_rate_usd_kg)) AS inbound_cogs
        FROM fact_inventory_snapshot s
        JOIN dim_sku sku ON sku.sku_key = s.sku_key
        JOIN (
            SELECT cny_kzt, usd_kzt, dlv_rate_usd_kg
            FROM dim_fx_rates
            WHERE effective_date <= ?
            ORDER BY effective_date DESC
            LIMIT 1
        ) fx
        WHERE s.snapshot_date = ?{where}
    """
    row = conn.execute(sql, [snapshot_date.isoformat(), snapshot_date.isoformat(), *params[1:]]).fetchone()
    warehouse = float(row[0]) if row and row[0] is not None else None
    inbound = float(row[1]) if row and row[1] is not None else None
    total = None
    if warehouse is not None and inbound is not None:
        total = warehouse + inbound
    return {
        "snapshot_date": snapshot_date.isoformat(),
        "warehouse": warehouse,
        "inbound": inbound,
        "total": total,
    }


def _inventory_series(
    conn: sqlite3.Connection,
    start_date: date,
    end_date: date,
    store_codes: Optional[Iterable[str]] = None,
    sku_keys: Optional[Iterable[str]] = None,
) -> dict[str, dict]:
    if not _table_exists(conn, "fact_inventory_snapshot"):
        return {}
    latest = _latest_snapshot_date(conn, end_date, store_codes, sku_keys)
    if not latest:
        return {}

    snapshot_dates = conn.execute(
        "SELECT DISTINCT snapshot_date FROM fact_inventory_snapshot WHERE snapshot_date <= ? ORDER BY snapshot_date",
        (end_date.isoformat(),),
    ).fetchall()
    snapshots = [date.fromisoformat(r[0]) for r in snapshot_dates if r and r[0]]
    totals = {}
    for snap in snapshots:
        totals[snap.isoformat()] = _inventory_cogs_for_date(conn, snap, store_codes, sku_keys)

    series = {}
    cursor = start_date
    idx = 0
    last_snap = None
    while cursor <= end_date:
        while idx < len(snapshots) and snapshots[idx] <= cursor:
            last_snap = snapshots[idx]
            idx += 1
        if last_snap:
            series[cursor.isoformat()] = totals.get(last_snap.isoformat(), {})
        else:
            series[cursor.isoformat()] = {}
        cursor += timedelta(days=1)
    return series


def _aggregate_range(
    conn: sqlite3.Connection,
    start_date: date,
    end_date: date,
    store_codes: Optional[Iterable[str]] = None,
    store_exclude: Optional[Iterable[str]] = None,
    sku_keys: Optional[Iterable[str]] = None,
    sku_exclude: Optional[Iterable[str]] = None,
    include_returns: bool = False,
) -> dict:
    filter_clause, params = _build_filter_clause(
        store_codes,
        store_exclude,
        sku_keys,
        sku_exclude,
        include_returns,
    )
    _ensure_fx_coverage(conn, start_date, end_date, filter_clause, params)

    sql = (
        "SELECT "
        "COALESCE(SUM(quantity), 0) AS units, "
        "COALESCE(SUM(line_net_rev), 0) AS revenue, "
        "COALESCE(SUM(cogs_line), 0) AS cogs, "
        "COALESCE(SUM(profit_line), 0) AS profit "
        "FROM v_sales_enriched "
        "WHERE order_date BETWEEN ? AND ?"
        f"{filter_clause}"
    )
    row = conn.execute(sql, [start_date.isoformat(), end_date.isoformat(), *params]).fetchone()
    units, revenue, cogs, profit = row if row else (0, 0, 0, 0)
    margin_pct = (profit / revenue) if revenue else None
    return {
        "start_date": start_date.isoformat(),
        "end_date": end_date.isoformat(),
        "units": float(units),
        "revenue": float(revenue),
        "cogs": float(cogs),
        "profit": float(profit),
        "margin_pct": margin_pct,
    }


def _daily_series(
    conn: sqlite3.Connection,
    start_date: date,
    end_date: date,
    store_codes: Optional[Iterable[str]] = None,
    store_exclude: Optional[Iterable[str]] = None,
    sku_keys: Optional[Iterable[str]] = None,
    sku_exclude: Optional[Iterable[str]] = None,
    include_returns: bool = False,
) -> list[dict]:
    filter_clause, params = _build_filter_clause(
        store_codes,
        store_exclude,
        sku_keys,
        sku_exclude,
        include_returns,
    )
    _ensure_fx_coverage(conn, start_date, end_date, filter_clause, params)

    sql = (
        "SELECT order_date, "
        "SUM(quantity) AS units, "
        "SUM(line_net_rev) AS revenue, "
        "SUM(cogs_line) AS cogs, "
        "SUM(profit_line) AS profit "
        "FROM v_sales_enriched "
        "WHERE order_date BETWEEN ? AND ?"
        f"{filter_clause} "
        "GROUP BY order_date "
        "ORDER BY order_date"
    )
    rows = conn.execute(sql, [start_date.isoformat(), end_date.isoformat(), *params]).fetchall()
    by_date = {row[0]: row for row in rows}

    series = []
    cursor = start_date
    while cursor <= end_date:
        key = cursor.isoformat()
        row = by_date.get(key)
        if row:
            _, units, revenue, cogs, profit = row
        else:
            units = revenue = cogs = profit = 0
        margin_pct = (profit / revenue) if revenue else None
        series.append(
            {
                "date": key,
                "units": float(units),
                "revenue": float(revenue),
                "cogs": float(cogs),
                "profit": float(profit),
                "margin_pct": margin_pct,
            }
        )
        cursor += timedelta(days=1)
    return series


def get_last30_kpis(
    conn: sqlite3.Connection,
    end_date: Optional[str] = None,
    store_codes: Optional[Iterable[str]] = None,
    store_exclude: Optional[Iterable[str]] = None,
    sku_keys: Optional[Iterable[str]] = None,
    sku_exclude: Optional[Iterable[str]] = None,
    include_returns: bool = False,
) -> dict:
    ensure_sales_views(conn)

    end_dt = _parse_date(end_date) or _today_almaty()
    start_dt = end_dt - timedelta(days=29)

    current = _aggregate_range(
        conn,
        start_dt,
        end_dt,
        store_codes,
        store_exclude,
        sku_keys,
        sku_exclude,
        include_returns,
    )

    prev_end = start_dt - timedelta(days=1)
    prev_start = prev_end - timedelta(days=29)
    previous = _aggregate_range(
        conn,
        prev_start,
        prev_end,
        store_codes,
        store_exclude,
        sku_keys,
        sku_exclude,
        include_returns,
    )

    deltas = {
        "units": current["units"] - previous["units"],
        "revenue": current["revenue"] - previous["revenue"],
        "cogs": current["cogs"] - previous["cogs"],
        "profit": current["profit"] - previous["profit"],
    }
    deltas_pct = {
        "units": (deltas["units"] / previous["units"]) if previous["units"] else None,
        "revenue": (deltas["revenue"] / previous["revenue"]) if previous["revenue"] else None,
        "cogs": (deltas["cogs"] / previous["cogs"]) if previous["cogs"] else None,
        "profit": (deltas["profit"] / previous["profit"]) if previous["profit"] else None,
    }

    return {
        "current": current,
        "previous": previous,
        "delta": deltas,
        "delta_pct": deltas_pct,
        "series": _daily_series(
            conn,
            start_dt,
            end_dt,
            store_codes,
            store_exclude,
            sku_keys,
            sku_exclude,
            include_returns,
        ),
    }


def get_timeseries_monthly(
    conn: sqlite3.Connection,
    end_date: Optional[str] = None,
    store_codes: Optional[Iterable[str]] = None,
    store_exclude: Optional[Iterable[str]] = None,
    sku_keys: Optional[Iterable[str]] = None,
    sku_exclude: Optional[Iterable[str]] = None,
    include_returns: bool = False,
) -> dict:
    ensure_sales_views(conn)

    end_dt = _parse_date(end_date) or _today_almaty()
    current_month_start = end_dt.replace(day=1)

    # 12 full months before current month
    start_month = (current_month_start.replace(day=1) - timedelta(days=1)).replace(day=1)
    for _ in range(11):
        start_month = (start_month - timedelta(days=1)).replace(day=1)

    filter_clause, params = _build_filter_clause(
        store_codes,
        store_exclude,
        sku_keys,
        sku_exclude,
        include_returns,
    )
    _ensure_fx_coverage(conn, start_month, end_dt, filter_clause, params)

    sql = (
        "SELECT strftime('%Y-%m-01', order_date) AS month_start, "
        "SUM(quantity) AS units, "
        "SUM(line_net_rev) AS revenue, "
        "SUM(cogs_line) AS cogs, "
        "SUM(profit_line) AS profit "
        "FROM v_sales_enriched "
        "WHERE order_date BETWEEN ? AND ?"
        f"{filter_clause} "
        "GROUP BY month_start "
        "ORDER BY month_start"
    )
    rows = conn.execute(
        sql,
        [start_month.isoformat(), current_month_start.isoformat(), *params],
    ).fetchall()
    by_month = {row[0]: row for row in rows}

    series = []
    cursor = start_month
    while cursor <= current_month_start:
        key = cursor.isoformat()
        row = by_month.get(key)
        if row:
            _, units, revenue, cogs, profit = row
        else:
            units = revenue = cogs = profit = 0
        margin_pct = (profit / revenue) if revenue else None
        series.append(
            {
                "month_start": key,
                "units": float(units),
                "revenue": float(revenue),
                "cogs": float(cogs),
                "profit": float(profit),
                "margin_pct": margin_pct,
            }
        )
        # advance to next month
        next_month = (cursor.replace(day=28) + timedelta(days=4)).replace(day=1)
        cursor = next_month

    return {"series": series, "start_month": start_month.isoformat(), "end_month": current_month_start.isoformat()}


def get_calendar_daily(
    conn: sqlite3.Connection,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    store_codes: Optional[Iterable[str]] = None,
    store_exclude: Optional[Iterable[str]] = None,
    sku_keys: Optional[Iterable[str]] = None,
    sku_exclude: Optional[Iterable[str]] = None,
    include_returns: bool = False,
    include_inventory: bool = False,
) -> dict:
    ensure_sales_views(conn)

    end_dt = _parse_date(end_date) or _today_almaty()
    start_dt = _parse_date(start_date) or (end_dt - timedelta(days=59))

    series = _daily_series(
        conn,
        start_dt,
        end_dt,
        store_codes,
        store_exclude,
        sku_keys,
        sku_exclude,
        include_returns,
    )

    if include_inventory:
        inv_series = _inventory_series(conn, start_dt, end_dt, store_codes, sku_keys)
        for day in series:
            inv = inv_series.get(day["date"], {})
            day["warehouse_cogs"] = inv.get("warehouse")
            day["inbound_cogs"] = inv.get("inbound")
            day["total_inventory_cogs"] = inv.get("total")

    return {
        "start_date": start_dt.isoformat(),
        "end_date": end_dt.isoformat(),
        "series": series,
    }


def get_compare_summary(
    conn: sqlite3.Connection,
    start_date: str,
    end_date: str,
    store_codes: Optional[Iterable[str]] = None,
    store_exclude: Optional[Iterable[str]] = None,
    sku_keys: Optional[Iterable[str]] = None,
    sku_exclude: Optional[Iterable[str]] = None,
    include_returns: bool = False,
) -> dict:
    ensure_sales_views(conn)

    if not start_date or not end_date:
        raise ValueError("start_date and end_date are required")

    start_dt = _parse_date(start_date)
    end_dt = _parse_date(end_date)
    if start_dt > end_dt:
        raise ValueError("start_date must be <= end_date")

    window_days = (end_dt - start_dt).days + 1
    prev_end = start_dt - timedelta(days=1)
    prev_start = prev_end - timedelta(days=window_days - 1)

    period_a = _aggregate_range(
        conn,
        start_dt,
        end_dt,
        store_codes,
        store_exclude,
        sku_keys,
        sku_exclude,
        include_returns,
    )
    period_b = _aggregate_range(
        conn,
        prev_start,
        prev_end,
        store_codes,
        store_exclude,
        sku_keys,
        sku_exclude,
        include_returns,
    )

    deltas = {
        "units": period_a["units"] - period_b["units"],
        "revenue": period_a["revenue"] - period_b["revenue"],
        "cogs": period_a["cogs"] - period_b["cogs"],
        "profit": period_a["profit"] - period_b["profit"],
    }
    deltas_pct = {
        "units": (deltas["units"] / period_b["units"]) if period_b["units"] else None,
        "revenue": (deltas["revenue"] / period_b["revenue"]) if period_b["revenue"] else None,
        "cogs": (deltas["cogs"] / period_b["cogs"]) if period_b["cogs"] else None,
        "profit": (deltas["profit"] / period_b["profit"]) if period_b["profit"] else None,
    }

    return {
        "period_a": period_a,
        "period_b": period_b,
        "delta": deltas,
        "delta_pct": deltas_pct,
    }


def get_sku_share(
    conn: sqlite3.Connection,
    metric: str,
    end_date: Optional[str] = None,
    store_codes: Optional[Iterable[str]] = None,
    store_exclude: Optional[Iterable[str]] = None,
    sku_keys: Optional[Iterable[str]] = None,
    sku_exclude: Optional[Iterable[str]] = None,
    include_returns: bool = False,
    top_n: int = 8,
) -> dict:
    ensure_sales_views(conn)
    end_dt = _parse_date(end_date) or _today_almaty()
    start_dt = end_dt - timedelta(days=29)

    metric_map = {
        "revenue": "SUM(line_net_rev)",
        "cogs": "SUM(cogs_line)",
        "profit": "SUM(profit_line)",
    }
    if metric not in metric_map:
        raise ValueError("metric must be revenue, cogs, or profit")

    filter_clause, params = _build_filter_clause(store_codes, store_exclude, sku_keys, sku_exclude, include_returns)
    _ensure_fx_coverage(conn, start_dt, end_dt, filter_clause, params)

    sql = (
        f"SELECT sku_key, {metric_map[metric]} AS value "
        "FROM v_sales_enriched "
        "WHERE order_date BETWEEN ? AND ?"
        f"{filter_clause} "
        "GROUP BY sku_key "
        "ORDER BY value DESC"
    )
    rows = conn.execute(sql, [start_dt.isoformat(), end_dt.isoformat(), *params]).fetchall()
    total = sum(float(r[1]) for r in rows if r[1] is not None) or 1
    items = []
    for r in rows[:top_n]:
        value = float(r[1]) if r[1] is not None else 0.0
        items.append({"sku_key": r[0], "value": value, "pct": value / total})
    if len(rows) > top_n:
        other = sum(float(r[1]) for r in rows[top_n:] if r[1] is not None)
        items.append({"sku_key": "OTHER", "value": other, "pct": other / total})
    return {"metric": metric, "items": items}


def get_health_summary(
    conn: sqlite3.Connection,
    end_date: Optional[str] = None,
    store_codes: Optional[Iterable[str]] = None,
    store_exclude: Optional[Iterable[str]] = None,
    sku_keys: Optional[Iterable[str]] = None,
    sku_exclude: Optional[Iterable[str]] = None,
    include_returns: bool = False,
) -> dict:
    end_dt = _parse_date(end_date) or _today_almaty()

    inventory = None
    if _table_exists(conn, "fact_inventory_snapshot"):
        latest_snap = _latest_snapshot_date(conn, end_dt, store_codes, sku_keys)
        if latest_snap:
            inventory = _inventory_cogs_for_date(conn, latest_snap, store_codes, sku_keys)

    status_distribution = {}
    stock_efficiency = None
    if _table_exists(conn, "fact_sku_metrics"):
        computed_at = conn.execute("SELECT MAX(computed_at) FROM fact_sku_metrics").fetchone()[0]
        if computed_at:
            params = [computed_at]
            clause = ""
            if store_codes:
                clause = " AND store_code IN (%s)" % ",".join(["?"] * len(store_codes))
                params.extend(store_codes)

            rows = conn.execute(
                f"SELECT status, COUNT(*) FROM fact_sku_metrics WHERE computed_at = ?{clause} GROUP BY status",
                params,
            ).fetchall()
            status_distribution = {r[0]: r[1] for r in rows}

            totals = conn.execute(
                f"""SELECT SUM(CASE WHEN total_stock >= rop THEN 1 ELSE 0 END), COUNT(*)
                FROM fact_sku_metrics WHERE computed_at = ?{clause}""",
                params,
            ).fetchone()
            if totals and totals[1]:
                stock_efficiency = totals[0] / totals[1]

    # Top/bottom profit for last 30 days
    top_profit = []
    bottom_profit = []
    if _table_exists(conn, "v_sales_enriched"):
        filter_clause, params = _build_filter_clause(store_codes, store_exclude, sku_keys, sku_exclude, include_returns)
        start_dt = end_dt - timedelta(days=29)
        sql = (
            "SELECT sku_key, SUM(profit_line) AS value "
            "FROM v_sales_enriched "
            "WHERE order_date BETWEEN ? AND ?"
            f"{filter_clause} "
            "GROUP BY sku_key "
            "ORDER BY value DESC"
        )
        rows = conn.execute(sql, [start_dt.isoformat(), end_dt.isoformat(), *params]).fetchall()
        top_profit = [{"sku_key": r[0], "value": float(r[1])} for r in rows[:5]]
        bottom_profit = [{"sku_key": r[0], "value": float(r[1])} for r in rows[-5:]]

    top_revenue = []
    concentration = []
    if _table_exists(conn, "v_sales_enriched"):
        filter_clause, params = _build_filter_clause(store_codes, store_exclude, sku_keys, sku_exclude, include_returns)
        sql = (
            "SELECT sku_key, SUM(line_net_rev) AS value "
            "FROM v_sales_enriched "
            "WHERE order_date BETWEEN ? AND ?"
            f"{filter_clause} "
            "GROUP BY sku_key "
            "ORDER BY value DESC"
        )
        rows = conn.execute(sql, [(end_dt - timedelta(days=29)).isoformat(), end_dt.isoformat(), *params]).fetchall()
        top_revenue = [{"sku_key": r[0], "value": float(r[1])} for r in rows[:5]]
        total = sum(float(r[1]) for r in rows if r[1] is not None) or 1
        for r in rows[:5]:
            value = float(r[1]) if r[1] is not None else 0
            concentration.append({"sku_key": r[0], "pct": value / total})

    store_mix = []
    if _table_exists(conn, "v_sales_enriched"):
        filter_clause, params = _build_filter_clause(store_codes, store_exclude, sku_keys, sku_exclude, include_returns)
        sql = (
            "SELECT store_code, SUM(line_net_rev) AS value "
            "FROM v_sales_enriched "
            "WHERE order_date BETWEEN ? AND ?"
            f"{filter_clause} "
            "GROUP BY store_code "
            "ORDER BY value DESC"
        )
        rows = conn.execute(sql, [(end_dt - timedelta(days=29)).isoformat(), end_dt.isoformat(), *params]).fetchall()
        total = sum(float(r[1]) for r in rows if r[1] is not None) or 1
        for r in rows:
            value = float(r[1]) if r[1] is not None else 0
            store_mix.append({"store_code": r[0], "pct": value / total, "value": value})

    return {
        "inventory_cogs": inventory,
        "status_distribution": status_distribution,
        "stock_efficiency_pct": stock_efficiency,
        "top_profit": top_profit,
        "bottom_profit": bottom_profit,
        "top_revenue": top_revenue,
        "concentration": concentration,
        "store_mix": store_mix,
    }


def get_catalog(
    conn: sqlite3.Connection,
    query: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
) -> dict:
    if not _table_exists(conn, "abc_view_cache"):
        raise RuntimeError("abc_view_cache not found. Run sync_abc_view_to_db.py")
    clause = ""
    params: list = []
    if query:
        clause = "WHERE SKU_key LIKE ?"
        params.append(f"%{query}%")
    total_row = conn.execute(f"SELECT COUNT(*) FROM abc_view_cache {clause}", params).fetchone()
    total = total_row[0] if total_row else 0
    sql = f"SELECT * FROM abc_view_cache {clause} ORDER BY SKU_key LIMIT ? OFFSET ?"
    rows = conn.execute(sql, [*params, limit, offset]).fetchall()
    items = [dict(r) for r in rows]
    return {"items": items, "total": total}


def get_filters_options(conn: sqlite3.Connection) -> dict:
    ensure_sales_views(conn)

    stores = [row[0] for row in conn.execute("SELECT DISTINCT store_code FROM sales_fact_v2 ORDER BY store_code").fetchall()]
    skus = [row[0] for row in conn.execute("SELECT DISTINCT sku_key FROM sales_fact_v2 ORDER BY sku_key").fetchall()]
    sizes = [row[0] for row in conn.execute("SELECT DISTINCT my_size FROM sales_fact_v2 WHERE my_size IS NOT NULL ORDER BY my_size").fetchall()]
    product_types = [row[0] for row in conn.execute("SELECT DISTINCT product_type FROM dim_sku WHERE product_type IS NOT NULL ORDER BY product_type").fetchall()]

    min_date = conn.execute("SELECT MIN(order_date) FROM sales_fact_v2").fetchone()[0]
    max_date = conn.execute("SELECT MAX(order_date) FROM sales_fact_v2").fetchone()[0]

    return {
        "stores": stores,
        "sku_keys": skus,
        "sizes": sizes,
        "product_types": product_types,
        "min_order_date": min_date,
        "max_order_date": max_date,
    }
