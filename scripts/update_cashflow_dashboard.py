#!/usr/bin/env python3
"""
Update cashflow calendar exports (CSV + HTML).

Default range: last 90 days history + next 120 days forecast.
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import shutil
import sqlite3
from dataclasses import dataclass
from datetime import date, datetime, timedelta
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
MIN_CASH_PATH = EXPORT_DIR / "min_cash_summary.txt"
BACKUP_DIR = PROJECT_ROOT / "backups"


@dataclass
class Commitment:
    commit_date: str
    commit_type: str
    amount_kzt: float
    scenario_tag: str | None
    ref_id: str | None
    notes: str | None


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


def _load_commitments(conn: sqlite3.Connection, start: date, end: date) -> list[Commitment]:
    if not _table_exists(conn, "fact_cashflow_commitments"):
        return []
    rows = conn.execute(
        """
        SELECT commit_date, commit_type, amount_kzt, scenario_tag, ref_id, notes
        FROM fact_cashflow_commitments
        WHERE commit_date BETWEEN ? AND ?
        """,
        (start.isoformat(), end.isoformat()),
    ).fetchall()
    return [
        Commitment(
            commit_date=row[0],
            commit_type=row[1],
            amount_kzt=float(row[2] or 0.0),
            scenario_tag=row[3],
            ref_id=row[4],
            notes=row[5],
        )
        for row in rows
    ]


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


def _write_min_cash(rows: list[dict], path: Path) -> None:
    if not rows:
        return
    min_row = min(rows, key=lambda r: r.get("cash_close", 0) or 0)
    breach = "YES" if (min_row.get("cash_close", 0) or 0) < 0 else "NO"
    lines = [
        f"min_cash_kzt: {min_row.get('cash_close', 0)}",
        f"min_cash_date: {min_row.get('date')}",
        f"breach: {breach}",
    ]
    path.write_text("\n".join(lines) + "\n")


def _render_html(rows: list[dict], path: Path) -> None:
    _backup_file(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    data = json.dumps(rows)
    html = f"""<!DOCTYPE html>
<html lang=\"en\">
<head>
  <meta charset=\"UTF-8\" />
  <title>Cashflow Calendar</title>
  <style>
    body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; padding: 20px; }}
    h1 {{ margin-bottom: 6px; }}
    .summary {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 12px; margin-bottom: 16px; }}
    .card {{ background: #f7f7f9; border: 1px solid #e5e7eb; border-radius: 8px; padding: 10px 12px; }}
    .label {{ color: #6b7280; font-size: 12px; }}
    .value {{ font-size: 16px; font-weight: 600; }}
    .controls {{ margin-bottom: 12px; display: flex; gap: 10px; align-items: center; }}
    table {{ width: 100%; border-collapse: collapse; font-size: 12px; }}
    th, td {{ border: 1px solid #ddd; padding: 6px 8px; text-align: right; }}
    th {{ background: #f3f4f6; text-align: right; }}
    td:first-child, th:first-child {{ text-align: left; }}
    .chart {{ margin: 16px 0; }}
    .breach {{ color: #b91c1c; font-weight: 700; }}
  </style>
</head>
<body>
  <h1>Cashflow Calendar</h1>
  <div class=\"summary\" id=\"summary\"></div>
  <div class=\"chart\">
    <canvas id=\"cashChart\" height=\"140\"></canvas>
  </div>
  <div class=\"controls\">
    <label>Show range:
      <select id=\"rangeSelect\">
        <option value=\"30\" selected>Last 30 days</option>
        <option value=\"90\">Last 90 days</option>
        <option value=\"all\">All</option>
      </select>
    </label>
    <label><input type=\"checkbox\" id=\"forecastToggle\" checked> Include forecast</label>
  </div>
  <table id=\"table\"></table>
  <script>
    const rows = {data};
    const summary = document.getElementById('summary');
    const forecastToggle = document.getElementById('forecastToggle');
    const rangeSelect = document.getElementById('rangeSelect');

    function formatKzt(val) {{
      return Number(val || 0).toLocaleString('en-US', {{ maximumFractionDigits: 0 }});
    }}

    function buildSummary(rows) {{
      if (!rows.length) {{ summary.textContent = 'No data'; return; }}
      const last = rows.filter(r => !r.is_forecast).slice(-1)[0] || rows[rows.length-1];
      const minRow = rows.reduce((a,b)=> (a.cash_close < b.cash_close ? a : b));
      const breach = (minRow.cash_close || 0) < 0;
      summary.innerHTML = `
        <div class=\"card\"><div class=\"label\">Cash (close)</div><div class=\"value\">${'{'}formatKzt(last.cash_close){'}'} KZT</div></div>
        <div class=\"card\"><div class=\"label\">Receivables (close)</div><div class=\"value\">${'{'}formatKzt(last.receivables_close){'}'} KZT</div></div>
        <div class=\"card\"><div class=\"label\">Inventory Cost (close)</div><div class=\"value\">${'{'}formatKzt(last.inventory_cost_close){'}'} KZT</div></div>
        <div class=\"card\"><div class=\"label\">Capital (close)</div><div class=\"value\">${'{'}formatKzt(last.capital_close){'}'} KZT</div></div>
        <div class=\"card\"><div class=\"label\">Min Cash</div><div class=\"value ${'{'}breach ? 'breach' : ''{'}'}\">${'{'}formatKzt(minRow.cash_close){'}'} KZT (${ '{'}minRow.date{'}'})</div></div>
      `;
    }}

    function filterRows() {{
      let filtered = rows.slice();
      if (!forecastToggle.checked) {{
        filtered = filtered.filter(r => !r.is_forecast);
      }}
      const rangeVal = rangeSelect.value;
      if (rangeVal !== 'all') {{
        const n = parseInt(rangeVal, 10);
        filtered = filtered.slice(-n);
      }}
      return filtered;
    }}

    function renderTable() {{
      const data = filterRows();
      const table = document.getElementById('table');
      if (!data.length) {{
        table.innerHTML = '<tr><td>No data</td></tr>';
        return;
      }}
      const headers = Object.keys(data[0]);
      table.innerHTML = '<thead><tr>' + headers.map(h => `<th>${'{'}h{'}'}</th>`).join('') + '</tr></thead>' +
        '<tbody>' + data.map(r => '<tr>' + headers.map(h => `<td>${'{'}r[h] ?? ''{'}'}</td>`).join('') + '</tr>').join('') + '</tbody>';
    }}

    function renderChart() {{
      const data = filterRows();
      const canvas = document.getElementById('cashChart');
      const ctx = canvas.getContext('2d');
      ctx.clearRect(0, 0, canvas.width, canvas.height);
      if (!data.length) return;
      const values = data.map(r => Number(r.cash_close || 0));
      const min = Math.min(...values);
      const max = Math.max(...values);
      const pad = 10;
      const w = canvas.width - pad * 2;
      const h = canvas.height - pad * 2;
      ctx.strokeStyle = '#111827';
      ctx.lineWidth = 2;
      ctx.beginPath();
      values.forEach((val, i) => {{
        const x = pad + (w * i) / Math.max(values.length - 1, 1);
        const y = pad + h - (h * (val - min)) / Math.max(max - min, 1);
        if (i === 0) ctx.moveTo(x, y);
        else ctx.lineTo(x, y);
      }});
      ctx.stroke();
    }}

    function renderAll() {{
      const filtered = filterRows();
      buildSummary(filtered);
      renderTable();
      renderChart();
    }}

    forecastToggle.addEventListener('change', renderAll);
    rangeSelect.addEventListener('change', renderAll);

    renderAll();
  </script>
</body>
</html>"""
    tmp = path.with_suffix(".tmp")
    tmp.write_text(html, encoding="utf-8")
    tmp.replace(path)


def _avg(values: list[float]) -> float:
    if not values:
        return 0.0
    return sum(values) / len(values)


def _build_forecast_rows(
    history_rows: list[dict],
    commitments: list[Commitment],
    days: int,
    payout_lag_days: int,
    run_id: str,
) -> list[dict]:
    if not history_rows:
        return []

    last_row = history_rows[-1]
    last_date = date.fromisoformat(last_row["date"])

    tail = history_rows[-30:]
    avg_sales = _avg([float(r["sales_accrued_kzt"]) for r in tail])
    avg_cogs = _avg([float(r["cogs_kzt"]) for r in tail])

    # Seed payout queue with last payout_lag_days of sales
    sales_queue = [float(r["sales_accrued_kzt"]) for r in history_rows[-payout_lag_days:]]
    while len(sales_queue) < payout_lag_days:
        sales_queue.insert(0, avg_sales)

    commitments_by_date: dict[str, list[Commitment]] = {}
    for c in commitments:
        commitments_by_date.setdefault(c.commit_date, []).append(c)

    forecast_rows = []
    cash_open = float(last_row["cash_close"])
    recv_open = float(last_row["receivables_close"])
    inv_open = float(last_row["inventory_cost_close"])

    for i in range(1, days + 1):
        day = last_date + timedelta(days=i)
        day_key = day.isoformat()

        sales = avg_sales
        cogs = avg_cogs
        payout = sales_queue.pop(0) if sales_queue else avg_sales
        sales_queue.append(sales)

        cash_flow = payout
        receivables_flow = sales - payout
        inventory_flow = -cogs

        po_payments = 0.0
        expenses = 0.0

        for c in commitments_by_date.get(day_key, []):
            amount = abs(c.amount_kzt)
            if c.commit_type in {"PO_PAYMENT", "PO"}:
                po_payments += amount
            else:
                expenses += amount
            cash_flow -= amount

        cash_close = cash_open + cash_flow
        recv_close = recv_open + receivables_flow
        inv_close = inv_open + inventory_flow
        capital_close = cash_close + recv_close + inv_close
        profit_accrual = sales - cogs - expenses

        forecast_rows.append({
            "date": day_key,
            "cash_open": round(cash_open, 2),
            "cash_close": round(cash_close, 2),
            "receivables_open": round(recv_open, 2),
            "receivables_close": round(recv_close, 2),
            "inventory_cost_open": round(inv_open, 2),
            "inventory_cost_close": round(inv_close, 2),
            "capital_close": round(capital_close, 2),
            "sales_accrued_kzt": round(sales, 2),
            "payouts_received_kzt": round(payout, 2),
            "refunds_kzt": 0.0,
            "po_payments_kzt": round(po_payments, 2),
            "expenses_kzt": round(expenses, 2),
            "cogs_kzt": round(cogs, 2),
            "cash_flow_kzt": round(cash_flow, 2),
            "receivables_flow_kzt": round(receivables_flow, 2),
            "inventory_cost_flow_kzt": round(inventory_flow, 2),
            "profit_accrual_kzt": round(profit_accrual, 2),
            "run_id": run_id,
            "is_forecast": True,
        })

        cash_open = cash_close
        recv_open = recv_close
        inv_open = inv_close

    return forecast_rows


def main() -> int:
    parser = argparse.ArgumentParser(description="Update cashflow calendar exports")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB, help="Path to SQLite DB")
    parser.add_argument("--history-days", type=int, default=90)
    parser.add_argument("--forecast-days", type=int, default=120)
    parser.add_argument("--payout-lag-days", type=int, default=7)
    parser.add_argument("--rebuild", action="store_true", help="Rebuild calendar before export")
    parser.add_argument("--apply", action="store_true", help="Apply rebuild (requires ENABLE_CASHFLOW_WRITE=1)")
    parser.add_argument("--run-id", type=str, default=None, help="Run id for audit")
    args = parser.parse_args()

    cutoff = get_cutoff_date_almaty()
    run_id = args.run_id or datetime.now().strftime("%Y%m%d_%H%M%S")

    with sqlite3.connect(str(args.db)) as conn:
        conn.row_factory = sqlite3.Row
        resolved_start, resolved_end = _resolve_start_end(conn)
        history_end = cutoff
        if _table_exists(conn, "fact_cashflow_events"):
            row = conn.execute("SELECT MAX(event_date) as max_date FROM fact_cashflow_events").fetchone()
            if row and row[0]:
                try:
                    max_event = date.fromisoformat(row[0])
                    if max_event > history_end:
                        history_end = max_event
                except Exception:
                    pass
        history_start = max(resolved_start, cutoff - timedelta(days=args.history_days - 1))

        rows = _load_daily_from_db(conn, history_start, history_end)

        if args.rebuild or not rows:
            fx_rates = get_fx_rates(history_end, db_path=args.db)
            manual = _fetch_manual_events(conn, history_start, history_end)
            system = _build_system_events(conn, history_start, history_end, fx_rates, run_id)
            rows = compute_daily_rows(manual + system, history_start, history_end, run_id=run_id)
            for r in rows:
                r["is_forecast"] = False
            if args.apply:
                if os.environ.get("ENABLE_CASHFLOW_WRITE") != "1":
                    raise RuntimeError("ENABLE_CASHFLOW_WRITE=1 is required to apply cashflow writes.")
                conn.execute(
                    "DELETE FROM fact_cashflow_daily WHERE date BETWEEN ? AND ?",
                    (history_start.isoformat(), history_end.isoformat()),
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
                            row["date"], row["cash_open"], row["cash_close"], row["receivables_open"], row["receivables_close"],
                            row["inventory_cost_open"], row["inventory_cost_close"], row["capital_close"],
                            row["sales_accrued_kzt"], row["payouts_received_kzt"], row["refunds_kzt"], row["po_payments_kzt"],
                            row["expenses_kzt"], row["cogs_kzt"], row["cash_flow_kzt"], row["receivables_flow_kzt"],
                            row["inventory_cost_flow_kzt"], row["profit_accrual_kzt"], row["run_id"],
                        ),
                    )
                conn.commit()
        else:
            for r in rows:
                r["is_forecast"] = False

        forecast_start = history_end + timedelta(days=1)
        forecast_end = forecast_start + timedelta(days=args.forecast_days - 1)
        commitments = _load_commitments(conn, forecast_start, forecast_end)
        forecast_rows = _build_forecast_rows(rows, commitments, args.forecast_days, args.payout_lag_days, run_id)

    all_rows = rows + forecast_rows

    _write_csv(all_rows, CSV_PATH)
    _write_min_cash(all_rows, MIN_CASH_PATH)
    _render_html(all_rows, HTML_PATH)

    print(f"Cashflow exports updated: {CSV_PATH} | {HTML_PATH}")
    if args.apply:
        print("  APPLY: daily table updated.")
    else:
        print("  DRY RUN: daily table not updated (exports generated).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
