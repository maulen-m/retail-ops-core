#!/usr/bin/env python3
"""Validate that unresolved COGS cannot leak into published profit surfaces."""

from __future__ import annotations

import argparse
from datetime import date, timedelta
import json
from pathlib import Path
import re
import sqlite3
import sys
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from core.sales import ensure_sales_truth_views

DEFAULT_DB = PROJECT_ROOT / "db" / "app.db"
DEFAULT_PO_DASHBOARD_PATH = PROJECT_ROOT / "exports" / "po_dashboard_data.json"


def _resolve_business_insides_path(as_of_iso: str, explicit: Path | None) -> Path:
    if explicit is not None:
        return explicit
    current = PROJECT_ROOT / "config" / "business_insides" / f"BUSINESS_INSIDES_{as_of_iso}.md"
    if current.exists():
        return current
    return (
        PROJECT_ROOT
        / "config"
        / "business_insides"
        / "snapshots"
        / f"BUSINESS_INSIDES_{as_of_iso}.md"
    )


def _parse_unresolved_markers(text: str) -> tuple[int | None, int | None]:
    rows_match = re.search(r"Unresolved COGS rows:\s*`?(\d+)`?", text)
    sku_match = re.search(r"Unresolved SKU count:\s*`?(\d+)`?", text)
    rows_value = int(rows_match.group(1)) if rows_match else None
    sku_value = int(sku_match.group(1)) if sku_match else None
    return rows_value, sku_value


def _extract_business_insides_profit_values(text: str) -> dict[str, str]:
    values: dict[str, str] = {}
    for metric in (
        "Avg 30d Profit",
        "Avg 7d Profit",
        "Avg 30d Profit After Ads",
        "Avg 7d Profit After Ads",
    ):
        match = re.search(rf"\|\s*{re.escape(metric)}\s*\|\s*([^|]+)\|", text, flags=re.IGNORECASE)
        if match:
            values[metric] = str(match.group(1)).strip()
    return values


def _load_unresolved_from_db(
    conn: sqlite3.Connection,
    *,
    start_date: str,
    end_date: str,
) -> dict[str, int]:
    ensure_sales_truth_views(conn)
    rows = conn.execute(
        """
        SELECT
            sku_key,
            SUM(CASE WHEN cogs_source = 'unresolved' THEN 1 ELSE 0 END) AS unresolved_rows
        FROM view_sales_line_truth
        WHERE date(sale_date) BETWEEN ? AND ?
        GROUP BY sku_key
        HAVING SUM(CASE WHEN cogs_source = 'unresolved' THEN 1 ELSE 0 END) > 0
        """,
        (start_date, end_date),
    ).fetchall()
    return {str(row[0]): int(row[1] or 0) for row in rows}


def validate_profit_publication_integrity(
    *,
    db_path: Path = DEFAULT_DB,
    as_of: str | None = None,
    days: int = 30,
    business_insides_path: Path | None = None,
    po_dashboard_path: Path = DEFAULT_PO_DASHBOARD_PATH,
) -> dict[str, Any]:
    as_of_date = date.fromisoformat(as_of) if as_of else date.today()
    window_end = as_of_date
    window_start = as_of_date - timedelta(days=max(1, int(days)) - 1)

    conn = sqlite3.connect(str(db_path))
    try:
        unresolved_by_sku = _load_unresolved_from_db(
            conn,
            start_date=window_start.isoformat(),
            end_date=window_end.isoformat(),
        )
    finally:
        conn.close()

    unresolved_rows_total = int(sum(unresolved_by_sku.values()))
    unresolved_sku_total = len(unresolved_by_sku)

    errors: list[str] = []
    leak_errors: list[str] = []

    if unresolved_rows_total > 0:
        errors.append(
            "unresolved COGS rows present in publication window: "
            f"rows={unresolved_rows_total}, skus={unresolved_sku_total}"
        )

    resolved_business_insides = _resolve_business_insides_path(as_of_date.isoformat(), business_insides_path)
    if resolved_business_insides.exists():
        text = resolved_business_insides.read_text(encoding="utf-8")
        rows_marker, sku_marker = _parse_unresolved_markers(text)
        if rows_marker is None:
            errors.append("business_insides missing unresolved rows marker")
        elif rows_marker != unresolved_rows_total:
            errors.append(
                "business_insides unresolved rows mismatch: "
                f"snapshot={rows_marker} db={unresolved_rows_total}"
            )
        if sku_marker is None:
            errors.append("business_insides missing unresolved sku marker")
        elif sku_marker != unresolved_sku_total:
            errors.append(
                "business_insides unresolved sku mismatch: "
                f"snapshot={sku_marker} db={unresolved_sku_total}"
            )

        if unresolved_rows_total > 0:
            metric_values = _extract_business_insides_profit_values(text)
            for metric_name, metric_value in metric_values.items():
                normalized = metric_value.strip().upper()
                if normalized not in {"N/A", "-", "NA"}:
                    errors.append(
                        "business_insides profit metric must be N/A when unresolved COGS exist: "
                        f"{metric_name}={metric_value}"
                    )
    else:
        errors.append(f"business_insides snapshot missing: {resolved_business_insides}")

    if po_dashboard_path.exists():
        payload = json.loads(po_dashboard_path.read_text(encoding="utf-8"))
        sku_rows = payload.get("sku_level") or []
        unresolved_rows = {
            str(row.get("sku_key") or ""): row
            for row in sku_rows
            if int(row.get("cogs_unresolved_rows") or 0) > 0
        }

        missing_dashboard_unresolved = sorted(
            sku for sku in unresolved_by_sku if sku not in unresolved_rows
        )
        if missing_dashboard_unresolved:
            errors.append(
                "po_dashboard missing unresolved SKU rows: " + ", ".join(missing_dashboard_unresolved)
            )

        for sku_key, row in unresolved_rows.items():
            if row.get("profit_publishable") is not False:
                leak_errors.append(
                    f"{sku_key}: profit lock violated (profit_publishable must be false)"
                )
            for field in ("profit_unit", "monthly_profit", "roic_pct", "profit_margin_pct"):
                if row.get(field) is not None:
                    leak_errors.append(
                        f"{sku_key}: profit lock violated ({field} must be null for unresolved COGS)"
                    )

        if unresolved_rows_total == 0:
            locked_rows = [
                str(row.get("sku_key") or "")
                for row in sku_rows
                if row.get("profit_publishable") is False
            ]
            if locked_rows:
                errors.append(
                    "po_dashboard has stale locked profit rows with no unresolved COGS: "
                    + ", ".join(sorted(k for k in locked_rows if k))
                )
    else:
        errors.append(f"po_dashboard_data missing: {po_dashboard_path}")

    errors.extend(leak_errors)

    return {
        "ok": not errors,
        "errors": errors,
        "leak_errors": leak_errors,
        "window_start": window_start.isoformat(),
        "window_end": window_end.isoformat(),
        "unresolved_rows": unresolved_rows_total,
        "unresolved_skus": unresolved_sku_total,
        "business_insides_path": str(resolved_business_insides),
        "po_dashboard_path": str(po_dashboard_path),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate unresolved COGS do not leak into published profits")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument("--as-of", type=str, default=None)
    parser.add_argument("--days", type=int, default=30)
    parser.add_argument("--business-insides", type=Path, default=None)
    parser.add_argument("--po-dashboard", type=Path, default=DEFAULT_PO_DASHBOARD_PATH)
    args = parser.parse_args()

    report = validate_profit_publication_integrity(
        db_path=args.db,
        as_of=args.as_of,
        days=args.days,
        business_insides_path=args.business_insides,
        po_dashboard_path=args.po_dashboard,
    )
    print(
        "profit_publication_integrity: "
        f"ok={report['ok']} window={report['window_start']}..{report['window_end']} "
        f"unresolved_rows={report['unresolved_rows']} unresolved_skus={report['unresolved_skus']}"
    )
    if report["errors"]:
        for err in report["errors"]:
            print(f"ERROR: {err}")
        return 1
    print("OK: profit publication integrity passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
