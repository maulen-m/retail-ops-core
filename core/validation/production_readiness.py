"""Production readiness validation using dashboard output."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path
from typing import Any
import sqlite3

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DASHBOARD_PATH = PROJECT_ROOT / "exports" / "po_dashboard_data.json"
DEFAULT_DB_PATH = PROJECT_ROOT / "db" / "app.db"


@dataclass
class ReadinessReport:
    ok: bool
    blockers: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    details: dict[str, Any] = field(default_factory=dict)


def _table_exists(conn: sqlite3.Connection, name: str) -> bool:
    row = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
        (name,),
    ).fetchone()
    return row is not None


def _parse_iso_date(value: str | None, label: str, blockers: list[str]) -> date | None:
    if not value:
        blockers.append(f"Missing {label} in dashboard output")
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        blockers.append(f"Invalid {label} value: {value}")
        return None


def _extract_dashboard_view(output: dict[str, Any]) -> tuple[dict[str, Any], list[dict[str, Any]], str | None, str | None]:
    if "pos" in output:
        pos = output.get("pos", {})
        plan0 = pos.get("PLAN-0", {})
        summary = plan0.get("summary", output.get("summary", {}))
        sku_level = plan0.get("sku_level", [])
        stock_date = output.get("base_stock_date") or output.get("stock_date")
        cutoff_date = output.get("cutoff_date") or plan0.get("cutoff_date") or output.get("sales_data_cutoff")
        return summary, sku_level, stock_date, cutoff_date

    summary = output.get("summary", {})
    sku_level = output.get("sku_level", [])
    stock_date = output.get("stock_date")
    cutoff_date = output.get("cutoff_date") or output.get("sales_data_cutoff")
    return summary, sku_level, stock_date, cutoff_date


def _fetch_recent_sales_skus(
    conn: sqlite3.Connection,
    sku_keys: list[str],
    cutoff_dt: date,
    days: int = 30,
) -> set[str] | None:
    if not sku_keys:
        return set()

    since = (cutoff_dt - timedelta(days=days)).isoformat()
    until = cutoff_dt.isoformat()
    placeholders = ",".join(["?"] * len(sku_keys))

    if _table_exists(conn, "fact_sales_daily"):
        rows = conn.execute(
            f"""
            SELECT DISTINCT sku_key
            FROM fact_sales_daily
            WHERE sku_key IN ({placeholders})
              AND sale_date >= ?
              AND sale_date <= ?
            """,
            tuple(sku_keys) + (since, until),
        ).fetchall()
        return {row[0] for row in rows}

    if _table_exists(conn, "fact_sales"):
        rows = conn.execute(
            f"""
            SELECT DISTINCT sku_key
            FROM fact_sales
            WHERE sku_key IN ({placeholders})
              AND order_date >= ?
              AND order_date <= ?
            """,
            tuple(sku_keys) + (since, until),
        ).fetchall()
        return {row[0] for row in rows}

    return None


def _fetch_active_skus(conn: sqlite3.Connection) -> set[str] | None:
    if not _table_exists(conn, "dim_sku"):
        return None
    rows = conn.execute(
        "SELECT sku_key FROM dim_sku WHERE active_flag = 1"
    ).fetchall()
    return {row[0] for row in rows if row[0]}


def _fetch_portfolio_active_skus(conn: sqlite3.Connection) -> tuple[set[str] | None, str]:
    if _table_exists(conn, "portfolio_active"):
        columns = [row[1] for row in conn.execute("PRAGMA table_info(portfolio_active)").fetchall()]
        has_active = "active_flag" in columns
        if has_active:
            rows = conn.execute(
                "SELECT sku_key FROM portfolio_active WHERE active_flag = 1"
            ).fetchall()
        else:
            rows = conn.execute("SELECT sku_key FROM portfolio_active").fetchall()
        return {row[0] for row in rows if row[0]}, "portfolio_active"

    active = _fetch_active_skus(conn)
    if active is None:
        return None, "missing"
    return active, "dim_sku.active_flag"


def _count_missing_size_rows(
    conn: sqlite3.Connection,
    table: str,
    date_field: str,
    cutoff_dt: date,
) -> int:
    if not _table_exists(conn, table):
        return 0
    row = conn.execute(
        f"""
        SELECT COUNT(*) as cnt
        FROM {table}
        WHERE (my_size IS NULL OR my_size = '')
          AND {date_field} <= ?
        """,
        (cutoff_dt.isoformat(),),
    ).fetchone()
    return int(row[0]) if row else 0


def _latest_date_on_or_before(
    conn: sqlite3.Connection,
    table: str,
    date_field: str,
    cutoff_dt: date,
) -> str | None:
    if not _table_exists(conn, table):
        return None
    row = conn.execute(
        f"""
        SELECT MAX({date_field}) as latest
        FROM {table}
        WHERE {date_field} <= ?
        """,
        (cutoff_dt.isoformat(),),
    ).fetchone()
    if not row:
        return None
    return row[0] if row[0] else None


def _count_missing_size_rows_on_date(
    conn: sqlite3.Connection,
    table: str,
    date_field: str,
    target_date: str | None,
) -> int:
    if not target_date or not _table_exists(conn, table):
        return 0
    row = conn.execute(
        f"""
        SELECT COUNT(*) as cnt
        FROM {table}
        WHERE (my_size IS NULL OR my_size = '')
          AND {date_field} = ?
        """,
        (target_date,),
    ).fetchone()
    return int(row[0]) if row else 0


def evaluate_production_readiness(
    output: dict[str, Any],
    db_path: Path | None = None,
) -> ReadinessReport:
    """Return readiness blockers based on dashboard output + recent sales checks."""
    summary, sku_level, stock_date, cutoff_date = _extract_dashboard_view(output)

    blockers: list[str] = []
    warnings: list[str] = []

    stock_dt = _parse_iso_date(stock_date, "stock_date", blockers)
    cutoff_dt = _parse_iso_date(cutoff_date, "cutoff_date", blockers)

    ordered_skus = [
        sku.get("sku_key", "")
        for sku in sku_level
        if int(sku.get("po_qty_total", 0) or 0) > 0
    ]

    missing_stock_skus = [
        sku.get("sku_key", "")
        for sku in sku_level
        if "NO_STOCK_SNAPSHOT" in (sku.get("notes") or "")
    ]
    missing_stock_blockers: set[str] = set(
        sku for sku in missing_stock_skus if sku in ordered_skus
    )

    missing_demand_skus = [
        sku.get("sku_key", "")
        for sku in sku_level
        if "NO_DEMAND_ESTIMATE" in (sku.get("notes") or "")
    ]

    recent_sales_missing_demand: list[str] = []

    if stock_dt and cutoff_dt:
        if stock_dt < (cutoff_dt - timedelta(days=1)):
            blockers.append(
                f"Stock snapshot stale vs cutoff: stock_date={stock_dt} cutoff_date={cutoff_dt}"
            )

    day_complete_ok = output.get("day_complete_ok")
    if day_complete_ok is False:
        blockers.append("Day complete gate failed: sizes pending")

    active_skus: set[str] | None = None
    portfolio_skus: set[str] | None = None
    portfolio_source = "missing"
    missing_size_sales = 0
    missing_size_snapshot = 0
    missing_size_snapshot_date: str | None = None
    if db_path and cutoff_dt:
        conn = sqlite3.connect(str(db_path))
        try:
            if missing_stock_skus:
                recent_sales = _fetch_recent_sales_skus(conn, missing_stock_skus, cutoff_dt)
                if recent_sales is None:
                    blockers.append("Missing sales tables for stock coverage check")
                else:
                    missing_stock_blockers.update(recent_sales)

            if missing_demand_skus:
                recent_sales = _fetch_recent_sales_skus(conn, missing_demand_skus, cutoff_dt)
                if recent_sales is None:
                    blockers.append("Missing sales tables for demand readiness check")
                else:
                    recent_sales_missing_demand = sorted(recent_sales)
                    if recent_sales_missing_demand:
                        blockers.append(
                            "Missing demand estimates for SKUs with recent sales: "
                            + ", ".join(recent_sales_missing_demand[:10])
                        )

            portfolio_skus, portfolio_source = _fetch_portfolio_active_skus(conn)
            if portfolio_skus is None:
                warnings.append("Missing portfolio_active scope; falling back to dim_sku.active_flag when available")
                active_skus = _fetch_active_skus(conn)
                if active_skus is None:
                    blockers.append("Missing dim_sku table for active SKU coverage check")

            scope_skus = portfolio_skus if portfolio_skus is not None else active_skus
            if scope_skus is not None:
                summary_total = summary.get("total_skus", len(sku_level))
                scope_label = portfolio_source if portfolio_skus is not None else "dim_sku.active_flag"
                if summary_total != len(scope_skus):
                    blockers.append(
                        f"Dashboard SKU coverage mismatch: dashboard={summary_total} {scope_label}={len(scope_skus)}"
                    )

            missing_size_sales = _count_missing_size_rows(conn, "fact_sales", "order_date", cutoff_dt)
            missing_size_snapshot_date = _latest_date_on_or_before(
                conn, "fact_inventory_snapshot_size", "snapshot_date", cutoff_dt
            )
            missing_size_snapshot = _count_missing_size_rows_on_date(
                conn, "fact_inventory_snapshot_size", "snapshot_date", missing_size_snapshot_date
            )
            if missing_size_sales or missing_size_snapshot:
                blockers.append(
                    f"Missing MY_SIZE rows detected (sales={missing_size_sales}, snapshot={missing_size_snapshot})"
                )
        finally:
            conn.close()
    elif missing_demand_skus and not db_path:
        if summary.get("no_demand_estimate", 0) > 0:
            blockers.append(
                "Missing demand estimates detected (no DB available for recent-sales check)"
            )

    if portfolio_skus is not None:
        dashboard_skus = {sku.get("sku_key") for sku in sku_level if sku.get("sku_key")}
        missing_from_dashboard = sorted(portfolio_skus - dashboard_skus)
        if missing_from_dashboard:
            blockers.append(
                "Portfolio SKUs missing from dashboard: "
                + ", ".join(missing_from_dashboard[:10])
                + (" ..." if len(missing_from_dashboard) > 10 else "")
            )

        missing_stock_portfolio = sorted(
            sku for sku in missing_stock_skus if sku in portfolio_skus
        )
        if missing_stock_portfolio:
            blockers.append(
                "Portfolio SKUs missing stock snapshot: "
                + ", ".join(missing_stock_portfolio[:10])
                + (" ..." if len(missing_stock_portfolio) > 10 else "")
            )

        missing_demand_portfolio = sorted(
            sku for sku in missing_demand_skus if sku in portfolio_skus
        )
        if missing_demand_portfolio:
            blockers.append(
                "Portfolio SKUs missing demand estimates: "
                + ", ".join(missing_demand_portfolio[:10])
                + (" ..." if len(missing_demand_portfolio) > 10 else "")
            )

    if missing_stock_blockers:
        blockers.append(
            "Missing stock snapshot for SKUs with orders/recent sales: "
            + ", ".join(sorted(missing_stock_blockers)[:10])
        )

    details = {
        "total_skus": summary.get("total_skus", len(sku_level)),
        "skus_with_orders": summary.get("skus_with_orders", len(ordered_skus)),
        "ordered_missing_stock": len([s for s in missing_stock_skus if s in ordered_skus]),
        "missing_stock_skus": len(missing_stock_skus),
        "missing_demand_skus": len(missing_demand_skus),
        "recent_sales_missing_demand": len(recent_sales_missing_demand),
        "missing_size_sales_rows": missing_size_sales,
        "missing_size_snapshot_rows": missing_size_snapshot,
        "missing_size_snapshot_date": missing_size_snapshot_date,
        "day_complete_ok": day_complete_ok,
        "stock_date": stock_date,
        "cutoff_date": cutoff_date,
        "portfolio_active_skus": len(portfolio_skus) if portfolio_skus is not None else None,
        "portfolio_active_source": portfolio_source,
    }

    return ReadinessReport(ok=not blockers, blockers=blockers, warnings=warnings, details=details)
