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
        po4 = pos.get("PO-4", {})
        summary = po4.get("summary", output.get("summary", {}))
        sku_level = po4.get("sku_level", [])
        stock_date = output.get("base_stock_date") or output.get("stock_date")
        cutoff_date = output.get("cutoff_date") or po4.get("cutoff_date") or output.get("sales_data_cutoff")
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

    ordered_missing_stock = [
        sku.get("sku_key", "")
        for sku in sku_level
        if int(sku.get("po_qty_total", 0) or 0) > 0
        and "NO_STOCK_SNAPSHOT" in (sku.get("notes") or "")
    ]
    if ordered_missing_stock:
        blockers.append(
            "Missing stock snapshot for ordered SKUs: "
            + ", ".join(sorted(set(ordered_missing_stock))[:10])
        )

    missing_demand_skus = [
        sku.get("sku_key", "")
        for sku in sku_level
        if "NO_DEMAND_ESTIMATE" in (sku.get("notes") or "")
    ]

    recent_sales_missing_demand: list[str] = []
    if missing_demand_skus and cutoff_dt and db_path:
        conn = sqlite3.connect(str(db_path))
        try:
            recent_sales = _fetch_recent_sales_skus(conn, missing_demand_skus, cutoff_dt)
        finally:
            conn.close()

        if recent_sales is None:
            blockers.append("Missing sales tables for demand readiness check")
        else:
            recent_sales_missing_demand = sorted(recent_sales)
            if recent_sales_missing_demand:
                blockers.append(
                    "Missing demand estimates for SKUs with recent sales: "
                    + ", ".join(recent_sales_missing_demand[:10])
                )
    elif missing_demand_skus and not db_path:
        if summary.get("no_demand_estimate", 0) > 0:
            blockers.append(
                "Missing demand estimates detected (no DB available for recent-sales check)"
            )

    if stock_dt and cutoff_dt:
        if stock_dt < (cutoff_dt - timedelta(days=1)):
            blockers.append(
                f"Stock snapshot stale vs cutoff: stock_date={stock_dt} cutoff_date={cutoff_dt}"
            )

    details = {
        "total_skus": summary.get("total_skus", len(sku_level)),
        "skus_with_orders": summary.get("skus_with_orders", len(ordered_skus)),
        "ordered_missing_stock": len(ordered_missing_stock),
        "missing_demand_skus": len(missing_demand_skus),
        "recent_sales_missing_demand": len(recent_sales_missing_demand),
        "stock_date": stock_date,
        "cutoff_date": cutoff_date,
    }

    return ReadinessReport(ok=not blockers, blockers=blockers, warnings=warnings, details=details)
