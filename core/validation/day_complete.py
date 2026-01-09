"""Day complete validation for order sizing readiness."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import Any
import sqlite3


@dataclass
class DayCompleteViolation:
    order_id: str
    sku_id: str
    store_code: str
    planned_ship_date: str
    internal_status: str
    kaspi_status: str


@dataclass
class DayCompleteReport:
    ok: bool
    violations: list[DayCompleteViolation] = field(default_factory=list)
    details: dict[str, Any] = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)


_INTERNAL_READY = {"ready", "shipped", "completed"}
_KASPI_READY = {
    "kaspi_delivery",
    "delivery",
    "completed",
    "archive",
    "ожидаетпередачикурьеру",
    "доставляется",
    "завершен",
}

_REQUIRED_COLUMNS = {
    "order_id",
    "sku_id",
    "store_code",
    "planned_shipment_date",
    "internal_status",
    "kaspi_status",
    "assigned_size",
    "my_size",
}


def _normalize(value: Any) -> str:
    if value is None:
        return ""
    return "".join(str(value).strip().lower().split())


def _coerce_str(value: Any) -> str:
    if value is None:
        return ""
    text = str(value).strip()
    if text.endswith(".0") and text[:-2].isdigit():
        return text[:-2]
    return text


def _parse_date(value: Any) -> date | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    text = str(value).strip()
    if not text:
        return None
    for fmt in ("%Y-%m-%d", "%d.%m.%Y"):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    return None


def _has_size(assigned_size: Any, my_size: Any) -> bool:
    return bool(_normalize(assigned_size) or _normalize(my_size))


def _is_ready_status(internal_status: Any, kaspi_status: Any) -> bool:
    internal_norm = _normalize(internal_status)
    kaspi_norm = _normalize(kaspi_status)
    return internal_norm in _INTERNAL_READY or kaspi_norm in _KASPI_READY


def evaluate_day_complete(db_path: Path, cutoff_date: date) -> DayCompleteReport:
    if not db_path.exists():
        return DayCompleteReport(
            ok=False,
            errors=[f"DB not found: {db_path}"],
            details={"cutoff_date": cutoff_date.isoformat()},
        )

    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    try:
        table = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='fact_orders_kaspi'"
        ).fetchone()
        if not table:
            return DayCompleteReport(
                ok=False,
                errors=["Missing table fact_orders_kaspi"],
                details={"cutoff_date": cutoff_date.isoformat()},
            )

        cols = conn.execute("PRAGMA table_info(fact_orders_kaspi)").fetchall()
        col_names = {row[1] for row in cols}
        missing = sorted(_REQUIRED_COLUMNS - col_names)
        if missing:
            return DayCompleteReport(
                ok=False,
                errors=[f"fact_orders_kaspi missing columns: {', '.join(missing)}"],
                details={"cutoff_date": cutoff_date.isoformat()},
            )

        rows = conn.execute(
            """
            SELECT order_id, sku_id, store_code, planned_shipment_date,
                   internal_status, kaspi_status, assigned_size, my_size
            FROM fact_orders_kaspi
            WHERE planned_shipment_date IS NOT NULL
            """
        ).fetchall()
    finally:
        conn.close()

    eligible = 0
    violations: list[DayCompleteViolation] = []

    for row in rows:
        planned_date = _parse_date(row["planned_shipment_date"])
        if planned_date is None or planned_date > cutoff_date:
            continue
        if not _is_ready_status(row["internal_status"], row["kaspi_status"]):
            continue

        eligible += 1
        if not _has_size(row["assigned_size"], row["my_size"]):
            violations.append(
                DayCompleteViolation(
                    order_id=_coerce_str(row["order_id"]),
                    sku_id=_coerce_str(row["sku_id"]),
                    store_code=_coerce_str(row["store_code"]),
                    planned_ship_date=planned_date.isoformat(),
                    internal_status=_coerce_str(row["internal_status"]),
                    kaspi_status=_coerce_str(row["kaspi_status"]),
                )
            )

    violations.sort(key=lambda v: (v.planned_ship_date, v.store_code, v.order_id))

    details = {
        "cutoff_date": cutoff_date.isoformat(),
        "eligible_orders": eligible,
        "violations": len(violations),
    }

    ok = not violations
    return DayCompleteReport(ok=ok, violations=violations, details=details)
