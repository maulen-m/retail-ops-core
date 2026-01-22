#!/usr/bin/env python3
"""
Update cashflow calendar exports (CSV + HTML).

Optionally rebuilds the cashflow calendar (dry-run by default).
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import shutil
import sqlite3
from datetime import date, datetime
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from core.db.queries import get_cutoff_date_almaty
from scripts.rebuild_cashflow_calendar import (
    compute_daily_rows,
    _fetch_manual_events,
    _build_system_events,
    _resolve_start_end,
)
from core.config.business_params import get_fx_rates
DEFAULT_DB = PROJECT_ROOT / "db" / "app.db"
EXPORT_DIR = PROJECT_ROOT / "exports"
CSV_PATH = EXPORT_DIR / "cashflow_calendar.csv"
HTML_PATH = EXPORT_DIR / "cashflow_dashboard.html"
BACKUP_DIR = PROJECT_ROOT / "backups"


def _backup_file(path: Path) -> None:
    if not path.exists():
        return
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    dest = BACKUP_DIR / f"{path.stem}.{timestamp}{path.suffix}"
    shutil.copy2(path, dest)


def _table_exists(conn: sqlite3.Connection, name: str) -> bool:
    return conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
        (name,),
    ).fetchone() is not None


def _load_daily_from_db(conn: sqlite3.Connection, start: date, end: date) -> list[dict]:
    if not _table_exists(conn, "fact_cashflow_daily"):
        return []
    rows = conn.execute(
        """
        SELECT *
        FROM fact_cashflow_daily
        WHERE date BETWEEN ? AND ?
        ORDER BY date
        """,
        (start.isoformat(), end.isoformat()),
    ).fetchall()
    return [dict(r) for r in rows]


def _write_csv(rows: list[dict], path: Path) -> None:
    _backup_file(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    if not rows:
        tmp.write_text("date,cash_open,cash_close,receivables_open,receivables_close,inventory_cost_open,inventory_cost_close,capital_close\n")
        tmp.replace(path)
        return
    with tmp.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
    tmp.replace(path)


def _write_html(rows: list[dict], path: Path) -> None:
    _backup_file(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    data = json.dumps(rows)
    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <title>Cashflow Calendar</title>
  <style>
    body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; padding: 20px; }}
    h1 {{ margin-bottom: 6px; }}
    .summary {{ margin-bottom: 16px; color: #555; }}
    table {{ width: 100%; border-collapse: collapse; font-size: 12px; }}
    th, td {{ border: 1px solid #ddd; padding: 6px 8px; text-align: right; }}
    th {{ background: #f3f4f6; text-align: right; }}
    td:first-child, th:first-child {{ text-align: left; }}
  </style>
</head>
<body>
  <h1>Cashflow Calendar</h1>
  <div class="summary" id="summary"></div>
  <table id="table"></table>
  <script>
    const rows = {data};
    const summary = document.getElementById('summary');
    if (rows.length) {{
      const minCashRow = rows.reduce((a, b) => (a.cash_close < b.cash_close ? a : b));
      summary.textContent = `Min cash: ${'{'}minCashRow.cash_close.toFixed(0){'}'} on ${'{'}minCashRow.date{'}'}`;
    }}
    const table = document.getElementById('table');
    if (!rows.length) {{
      table.innerHTML = '<tr><td>No data</td></tr>';
    }} else {{
      const headers = Object.keys(rows[0]);
      table.innerHTML = '<thead><tr>' + headers.map(h => `<th>${'{'}h{'}'}</th>`).join('') + '</tr></thead>' +
        '<tbody>' + rows.map(r => '<tr>' + headers.map(h => `<td>${'{'}r[h] ?? ''{'}'}</td>`).join('') + '</tr>').join('') + '</tbody>';
    }}
  </script>
</body>
</html>"""
    tmp = path.with_suffix(".tmp")
    tmp.write_text(html, encoding="utf-8")
    tmp.replace(path)


def main() -> int:
    parser = argparse.ArgumentParser(description="Update cashflow calendar exports")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB, help="Path to SQLite DB")
    parser.add_argument("--start-date", type=str, help="Start date (YYYY-MM-DD)")
    parser.add_argument("--end-date", type=str, help="End date (YYYY-MM-DD)")
    parser.add_argument("--rebuild", action="store_true", help="Rebuild calendar before export")
    parser.add_argument("--apply", action="store_true", help="Apply rebuild (requires ENABLE_CASHFLOW_WRITE=1)")
    parser.add_argument("--run-id", type=str, default=None, help="Run id for audit")
    args = parser.parse_args()

    cutoff = get_cutoff_date_almaty()
    start = date.fromisoformat(args.start_date) if args.start_date else None
    end = date.fromisoformat(args.end_date) if args.end_date else None
    run_id = args.run_id or datetime.now().strftime("%Y%m%d_%H%M%S")

    with sqlite3.connect(str(args.db)) as conn:
        conn.row_factory = sqlite3.Row
        if start is None or end is None:
            resolved_start, resolved_end = _resolve_start_end(conn)
            start = start or resolved_start
            end = end or resolved_end

        rows = _load_daily_from_db(conn, start, end)

        if args.rebuild or not rows:
            fx_rates = get_fx_rates(end, db_path=args.db)
            manual = _fetch_manual_events(conn, start, end)
            system = _build_system_events(conn, start, end, fx_rates, run_id)
            rows = compute_daily_rows(manual + system, start, end, run_id=run_id)
            if args.apply:
                if os.environ.get("ENABLE_CASHFLOW_WRITE") != "1":
                    raise RuntimeError("ENABLE_CASHFLOW_WRITE=1 is required to apply cashflow writes.")
                conn.execute(
                    "DELETE FROM fact_cashflow_daily WHERE date BETWEEN ? AND ?",
                    (start.isoformat(), end.isoformat()),
                )
                for row in rows:
                    conn.execute(
                        """
                        INSERT OR REPLACE INTO fact_cashflow_daily (
                            date, cash_open, cash_close, receivables_open, receivables_close,
                            inventory_cost_open, inventory_cost_close, capital_close,
                            sales_accrued_kzt, payouts_received_kzt, refunds_kzt, po_payments_kzt,
                            expenses_kzt, cogs_kzt, cash_flow_kzt, receivables_flow_kzt,
                            inventory_cost_flow_kzt, profit_accrual_kzt, run_id
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                conn.commit()

    _write_csv(rows, CSV_PATH)
    _write_html(rows, HTML_PATH)

    print(f"Cashflow exports updated: {CSV_PATH} | {HTML_PATH}")
    if args.apply:
        print("  APPLY: daily table updated.")
    else:
        print("  DRY RUN: daily table not updated (exports generated).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
