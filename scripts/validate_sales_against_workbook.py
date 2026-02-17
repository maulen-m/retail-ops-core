#!/usr/bin/env python3
"""Strict validator for published sales truth against CRM workbook anchor."""

from __future__ import annotations

import argparse
from collections import defaultdict
from datetime import date, datetime, timedelta
from pathlib import Path
import sqlite3
import sys
from typing import Any

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from core.sales import ensure_sales_truth_views

DEFAULT_DB = PROJECT_ROOT / "db" / "app.db"
_ALT_WORKBOOK = PROJECT_ROOT.parent / "Autonomous_business 2" / "excel_ui" / "SALES_KSP_CRM_V3.xlsx"
DEFAULT_WORKBOOK = _ALT_WORKBOOK if _ALT_WORKBOOK.exists() else (PROJECT_ROOT / "excel_ui" / "SALES_KSP_CRM_V3.xlsx")
DEFAULT_SHEET = "SALES_KSP_CRM_1"


def _norm_header(value: Any) -> str:
    text = str(value or "").strip().lower()
    for ch in (" ", "_", "-", "/", "\\", "\t", "\n", "\r"):
        text = text.replace(ch, "")
    return text


def _find_column(columns: list[str], aliases: list[str]) -> str | None:
    normalized = {_norm_header(c): c for c in columns}
    for alias in aliases:
        key = _norm_header(alias)
        if key in normalized:
            return normalized[key]
    return None


def _to_float(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip().replace("\u00a0", "").replace(" ", "")
    if not text:
        return None
    if text.count(",") == 1 and text.count(".") == 0:
        text = text.replace(",", ".")
    try:
        return float(text)
    except ValueError:
        return None


def _to_date_iso(value: Any) -> str | None:
    if value is None:
        return None
    if pd.isna(value):
        return None
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    text = str(value).strip()
    if not text:
        return None
    for fmt in ("%Y-%m-%d", "%d.%m.%Y", "%Y/%m/%d", "%d/%m/%Y"):
        try:
            return datetime.strptime(text, fmt).date().isoformat()
        except ValueError:
            continue
    try:
        parsed = pd.to_datetime(text, errors="raise")
        if pd.isna(parsed):
            return None
        return parsed.date().isoformat()
    except Exception:
        return None


def parse_workbook_daily_totals(
    workbook_path: Path,
    *,
    sheet_name: str = DEFAULT_SHEET,
) -> dict[str, dict[str, float]]:
    if not workbook_path.exists():
        raise FileNotFoundError(f"Workbook not found: {workbook_path}")

    df = pd.read_excel(workbook_path, sheet_name=sheet_name, dtype=object)
    if df.empty:
        return {}

    date_col = _find_column(df.columns.tolist(), ["Date", "order_date", "Дата поступления заказа"])
    qty_col = _find_column(df.columns.tolist(), ["Quantity", "qty", "Количество"])
    total_price_col = _find_column(df.columns.tolist(), ["Total_price", "totalprice", "Сумма"])
    net_rev_col = _find_column(df.columns.tolist(), ["Total_net_rev", "net_rev", "Line_NetRev"])
    sell_price_col = _find_column(df.columns.tolist(), ["Sell_price_kzt", "price"])

    missing = []
    if date_col is None:
        missing.append("Date")
    if qty_col is None:
        missing.append("Quantity")
    if missing:
        raise RuntimeError(f"Missing required workbook columns: {', '.join(missing)}")

    daily: dict[str, dict[str, float]] = defaultdict(
        lambda: {"units": 0.0, "total_price_kzt": 0.0, "net_rev_kzt": 0.0}
    )
    for _, row in df.iterrows():
        day = _to_date_iso(row.get(date_col))
        if day is None:
            continue
        qty = _to_float(row.get(qty_col))
        if qty is None:
            continue

        total_price = _to_float(row.get(total_price_col)) if total_price_col else None
        if total_price is None and sell_price_col:
            unit_price = _to_float(row.get(sell_price_col))
            if unit_price is not None:
                total_price = unit_price * qty
        net_rev = _to_float(row.get(net_rev_col)) if net_rev_col else None
        if net_rev is None:
            net_rev = total_price if total_price is not None else 0.0

        daily[day]["units"] += qty
        daily[day]["total_price_kzt"] += float(total_price or 0.0)
        daily[day]["net_rev_kzt"] += float(net_rev or 0.0)

    for values in daily.values():
        values["units"] = round(values["units"], 2)
        values["total_price_kzt"] = round(values["total_price_kzt"], 2)
        values["net_rev_kzt"] = round(values["net_rev_kzt"], 2)
    return dict(daily)


def load_daily_source(conn: sqlite3.Connection, source: str) -> dict[str, dict[str, float]]:
    if source == "sales_fact_v2":
        rows = conn.execute(
            """
            SELECT
                date(order_date) AS d,
                SUM(COALESCE(quantity, 0)) AS units,
                SUM(COALESCE(net_rev, 0)) AS net_rev_kzt
            FROM sales_fact_v2
            WHERE UPPER(COALESCE(status, '')) = 'DELIVERED'
              AND COALESCE(return_flag, 0) = 0
            GROUP BY date(order_date)
            """
        ).fetchall()
    elif source == "fact_sales":
        rows = conn.execute(
            """
            SELECT
                date(order_date) AS d,
                SUM(COALESCE(quantity, 0)) AS units,
                SUM(COALESCE(line_net_rev, 0)) AS net_rev_kzt
            FROM fact_sales
            GROUP BY date(order_date)
            """
        ).fetchall()
    elif source == "published_truth":
        ensure_sales_truth_views(conn)
        rows = conn.execute(
            """
            SELECT
                sale_date AS d,
                SUM(COALESCE(units, 0)) AS units,
                SUM(COALESCE(revenue_kzt, 0)) AS net_rev_kzt
            FROM view_sales_daily_truth
            GROUP BY sale_date
            """
        ).fetchall()
    else:
        raise ValueError(f"Unknown source: {source}")

    out: dict[str, dict[str, float]] = {}
    for day, units, net in rows:
        if day is None:
            continue
        out[str(day)] = {
            "units": round(float(units or 0.0), 2),
            "net_rev_kzt": round(float(net or 0.0), 2),
        }
    return out


def _pct_diff(anchor: float, value: float) -> float:
    base = abs(anchor)
    if base < 1e-9:
        return 0.0 if abs(value) < 1e-9 else 100000.0
    return abs(value - anchor) / base * 100.0


def validate_sales_against_workbook(
    *,
    db_path: Path,
    workbook_path: Path,
    sheet_name: str = DEFAULT_SHEET,
    days: int = 14,
    tol_pct: float = 5.0,
    as_of: str | None = None,
    min_overlap_days: int = 7,
    max_lag_days: int = 1,
) -> dict[str, Any]:
    try:
        workbook_daily = parse_workbook_daily_totals(workbook_path, sheet_name=sheet_name)
    except Exception as exc:
        return {
            "ok": False,
            "errors": [f"workbook parse error: {exc}"],
            "overlap_days": 0,
            "window_start": None,
            "window_end": None,
            "workbook_max_date": None,
            "db_max_date": None,
            "max_lag_days": int(max_lag_days),
            "daily": [],
        }

    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    try:
        published_daily = load_daily_source(conn, "published_truth")
    finally:
        conn.close()

    errors: list[str] = []
    if not workbook_daily:
        errors.append("workbook has no parsable daily rows")
    if not published_daily:
        errors.append("published truth has no daily rows")
    if errors:
        return {
            "ok": False,
            "errors": errors,
            "overlap_days": 0,
            "window_start": None,
            "window_end": None,
            "workbook_max_date": None,
            "db_max_date": None,
            "max_lag_days": int(max_lag_days),
            "daily": [],
        }

    as_of_date = date.fromisoformat(as_of) if as_of else date.today()
    wb_max = max(date.fromisoformat(d) for d in workbook_daily)
    db_max = max(date.fromisoformat(d) for d in published_daily)

    lag_days = (as_of_date - wb_max).days
    if lag_days > int(max_lag_days):
        errors.append(
            "workbook content lag exceeds threshold: "
            f"workbook_max_date={wb_max.isoformat()} as_of={as_of_date.isoformat()} "
            f"lag_days={lag_days} max_lag_days={int(max_lag_days)}"
        )

    window_end = min(as_of_date, wb_max, db_max)
    window_start = window_end - timedelta(days=max(1, int(days)) - 1)

    overlap_days = []
    day = window_start
    while day <= window_end:
        key = day.isoformat()
        if key in workbook_daily and key in published_daily:
            overlap_days.append(key)
        day += timedelta(days=1)

    if len(overlap_days) < int(min_overlap_days):
        errors.append(
            f"overlap days below minimum: overlap={len(overlap_days)} min_required={int(min_overlap_days)}"
        )

    details: list[dict[str, Any]] = []
    tol = float(tol_pct)
    for d in overlap_days:
        wb_units = float(workbook_daily[d]["units"])
        wb_net = float(workbook_daily[d]["net_rev_kzt"])
        pub_units = float(published_daily[d]["units"])
        pub_net = float(published_daily[d]["net_rev_kzt"])
        units_diff_pct = round(_pct_diff(wb_units, pub_units), 2)
        net_diff_pct = round(_pct_diff(wb_net, pub_net), 2)
        details.append(
            {
                "date": d,
                "workbook_units": wb_units,
                "published_units": pub_units,
                "units_diff_pct": units_diff_pct,
                "workbook_net_rev_kzt": wb_net,
                "published_net_rev_kzt": pub_net,
                "net_rev_diff_pct": net_diff_pct,
            }
        )
        if wb_units > 0 and pub_units > wb_units * (1 + tol / 100.0):
            errors.append(
                f"{d}: published exceeds workbook units ({pub_units:.2f} > {wb_units:.2f})"
            )
        if wb_units == 0 and pub_units > 0:
            errors.append(f"{d}: published exceeds workbook units (anchor is zero)")
        if wb_net > 0 and pub_net > wb_net * (1 + tol / 100.0):
            errors.append(
                f"{d}: published exceeds workbook net_rev ({pub_net:.2f} > {wb_net:.2f})"
            )
        if wb_net == 0 and pub_net > 0:
            errors.append(f"{d}: published exceeds workbook net_rev (anchor is zero)")

    return {
        "ok": len(errors) == 0,
        "errors": errors,
        "overlap_days": len(overlap_days),
        "window_start": window_start.isoformat(),
        "window_end": window_end.isoformat(),
        "workbook_max_date": wb_max.isoformat(),
        "db_max_date": db_max.isoformat(),
        "max_lag_days": int(max_lag_days),
        "daily": details,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate published sales truth against workbook anchor")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument("--workbook", type=Path, default=DEFAULT_WORKBOOK)
    parser.add_argument("--sheet", type=str, default=DEFAULT_SHEET)
    parser.add_argument("--days", type=int, default=14)
    parser.add_argument("--tol-pct", type=float, default=5.0)
    parser.add_argument("--as-of", type=str, default=None)
    parser.add_argument("--min-overlap-days", type=int, default=7)
    parser.add_argument("--max-lag-days", type=int, default=1)
    args = parser.parse_args()

    report = validate_sales_against_workbook(
        db_path=args.db,
        workbook_path=args.workbook,
        sheet_name=args.sheet,
        days=args.days,
        tol_pct=args.tol_pct,
        as_of=args.as_of,
        min_overlap_days=args.min_overlap_days,
        max_lag_days=args.max_lag_days,
    )
    print(
        "window="
        f"{report['window_start']}..{report['window_end']} "
        f"overlap_days={report['overlap_days']} ok={report['ok']}"
    )
    if report["errors"]:
        for err in report["errors"]:
            print(f"ERROR: {err}")
        return 1
    print("OK: published truth is within workbook tolerance")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
