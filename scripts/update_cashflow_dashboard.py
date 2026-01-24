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
    _has_order_modelled_events,
    _resolve_start_end,
)
from core.config.business_params import get_fx_rates
from core.cashflow.payout_model import load_payout_model
DEFAULT_DB = PROJECT_ROOT / "db" / "app.db"
EXPORT_DIR = PROJECT_ROOT / "exports"
CSV_PATH = EXPORT_DIR / "cashflow_calendar.csv"
HTML_PATH = EXPORT_DIR / "cashflow_dashboard.html"
MIN_CASH_PATH = EXPORT_DIR / "min_cash_summary.txt"
TRUST_REPORT_PATH = EXPORT_DIR / "cashflow_trust_report_{label}.md"
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


def _write_min_cash(rows: list[dict], rows_conservative: list[dict] | None, path: Path) -> None:
    if not rows:
        return
    base_min = _min_cash(rows)
    conservative_min = _min_cash(rows_conservative) if rows_conservative else base_min
    base_breach = "YES" if (base_min.get("cash_close", 0) or 0) < 0 else "NO"
    cons_breach = "YES" if (conservative_min.get("cash_close", 0) or 0) < 0 else "NO"
    lines = [
        f"base_min_cash_kzt: {base_min.get('cash_close', 0)}",
        f"base_min_cash_date: {base_min.get('date')}",
        f"base_breach: {base_breach}",
        f"conservative_min_cash_kzt: {conservative_min.get('cash_close', 0)}",
        f"conservative_min_cash_date: {conservative_min.get('date')}",
        f"conservative_breach: {cons_breach}",
    ]
    path.write_text("\n".join(lines) + "\n")


def _min_cash(rows: list[dict]) -> dict:
    if not rows:
        return {"date": None, "cash_close": 0}
    return min(rows, key=lambda r: r.get("cash_close", 0) or 0)


def _load_last_statement_date(conn: sqlite3.Connection) -> str | None:
    if not _table_exists(conn, "fact_cashflow_events"):
        return None
    row = conn.execute(
        "SELECT MAX(event_date) as max_date FROM fact_cashflow_events WHERE source = 'STATEMENT_ACTUAL'"
    ).fetchone()
    return row[0] if row and row[0] else None


def _load_sync_age_hours(conn: sqlite3.Connection) -> float | None:
    if not _table_exists(conn, "kaspi_order_sync_log"):
        return None
    rows = conn.execute("SELECT last_success_ts FROM kaspi_order_sync_log").fetchall()
    if not rows:
        return None
    now = datetime.now()
    ages = []
    for row in rows:
        if not row[0]:
            continue
        try:
            last_ts = datetime.fromisoformat(row[0])
        except Exception:
            continue
        ages.append((now - last_ts).total_seconds() / 3600)
    return max(ages) if ages else None


def _write_trust_report(
    path: Path,
    last_statement_date: str | None,
    sync_age_hours: float | None,
    rows: list[dict],
) -> None:
    statement_days = 0
    modelled_days = 0
    forecast_days = 0
    last_statement = None
    if last_statement_date:
        try:
            last_statement = date.fromisoformat(last_statement_date)
        except Exception:
            last_statement = None
    for row in rows:
        row_date = date.fromisoformat(row["date"])
        if row.get("is_forecast"):
            forecast_days += 1
        elif last_statement and row_date <= last_statement:
            statement_days += 1
        else:
            modelled_days += 1

    lines = [
        "# Cashflow Trust Report",
        "",
        f"- last_statement_date: {last_statement_date or 'NONE'}",
        f"- statement_backed_days: {statement_days}",
        f"- modelled_days: {modelled_days}",
        f"- forecast_days: {forecast_days}",
        f"- order_sync_age_hours: {sync_age_hours if sync_age_hours is not None else 'UNKNOWN'}",
        "",
        "Legend:",
        "- STATEMENT_ACTUAL: derived from MT940 statements",
        "- ORDER_MODELLED: derived from Orders API + payout model",
        "- FORECAST_MODEL: forward projections",
        "",
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n")


def _render_html(rows: list[dict], path: Path, meta: dict) -> None:
    _backup_file(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    data = json.dumps(rows)
    meta_json = json.dumps(meta)
    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>CASHFLOW MONITOR - RETRO TERMINAL</title>
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Press+Start+2P&family=VT323&display=swap" rel="stylesheet">

  <style>
    /* ========================================
       CSS VARIABLES - THEME SYSTEM
       ======================================== */
    :root {{
      --bg-primary: #0a0a0a;
      --bg-secondary: #1a1a1a;
      --bg-card: #1f1f1f;
      --bg-input: #141414;
      --bg-table: #121212;

      --text-primary: #ffaa00;
      --text-secondary: #ff8800;
      --text-accent: #ffcc44;
      --text-dim: #996600;
      --text-muted: #664400;

      --border-primary: #ff8800;
      --border-secondary: #664400;

      --glow-color: #ffaa00;
      --glow-intense: #ff8800;

      --positive-color: #00ff88;
      --negative-color: #ff4444;
      --warning-color: #ffdd00;

      --chart-cash: #ffaa00;
      --chart-capital: #00ddff;
      --chart-receivables: #ff6688;
      --chart-grid: rgba(255, 170, 0, 0.12);
      --chart-axis: rgba(255, 170, 0, 0.4);

      --scanline-opacity: 0.04;
      --pixel-border: 2px;
    }}

    body.theme-light {{
      --bg-primary: #f4f1e8;
      --bg-secondary: #ebe7d9;
      --bg-card: #fefdfb;
      --bg-input: #ffffff;
      --bg-table: #faf9f6;

      --text-primary: #2d2520;
      --text-secondary: #4a3f35;
      --text-accent: #1a1410;
      --text-dim: #6b5d52;
      --text-muted: #9a8a7a;

      --border-primary: #3d3228;
      --border-secondary: #bab0a0;

      --glow-color: transparent;
      --glow-intense: transparent;

      --positive-color: #2d7a4a;
      --negative-color: #b83232;
      --warning-color: #d4a017;

      --chart-cash: #2d2520;
      --chart-capital: #0088aa;
      --chart-receivables: #aa3355;
      --chart-grid: rgba(45, 37, 32, 0.08);
      --chart-axis: rgba(45, 37, 32, 0.3);

      --scanline-opacity: 0.015;
    }}

    /* ========================================
       BASE STYLES
       ======================================== */
    * {{
      margin: 0;
      padding: 0;
      box-sizing: border-box;
    }}

    body {{
      font-family: 'VT323', monospace;
      background: var(--bg-primary);
      color: var(--text-primary);
      overflow-x: hidden;
      transition: background 0.3s ease, color 0.3s ease;
    }}

    .pixel-font {{
      font-family: 'Press Start 2P', cursive;
      text-transform: uppercase;
      letter-spacing: 0.1em;
      line-height: 1.6;
    }}

    .monospace-font {{
      font-family: 'VT323', monospace;
      letter-spacing: 0.03em;
    }}

    /* ========================================
       LAYOUT CONTAINER
       ======================================== */
    .retro-container {{
      min-height: 100vh;
      padding: 20px;
      position: relative;
    }}

    /* CRT Scanline Effect */
    .retro-container::before {{
      content: '';
      position: fixed;
      top: 0;
      left: 0;
      width: 100%;
      height: 100%;
      background: repeating-linear-gradient(
        0deg,
        rgba(0, 0, 0, var(--scanline-opacity)) 0px,
        transparent 1px,
        transparent 2px,
        rgba(0, 0, 0, var(--scanline-opacity)) 3px
      );
      pointer-events: none;
      z-index: 1000;
      animation: scanline 8s linear infinite;
    }}

    @keyframes scanline {{
      0% {{ transform: translateY(0); }}
      100% {{ transform: translateY(4px); }}
    }}

    /* ========================================
       HEADER
       ======================================== */
    .retro-header {{
      position: relative;
      margin-bottom: 24px;
      padding-bottom: 16px;
      border-bottom: var(--pixel-border) solid var(--border-primary);
    }}

    .title-bar {{
      display: flex;
      justify-content: space-between;
      align-items: center;
      flex-wrap: wrap;
      gap: 16px;
    }}

    .pixel-title {{
      font-size: clamp(16px, 3vw, 24px);
      color: var(--text-accent);
      text-shadow:
        0 0 8px var(--glow-color),
        0 0 12px var(--glow-intense);
    }}

    .subtitle {{
      font-size: 18px;
      color: var(--text-dim);
      margin-top: 8px;
    }}

    .theme-toggle-container {{
      display: flex;
      align-items: center;
      gap: 12px;
    }}

    .toggle-label {{
      font-size: 14px;
      color: var(--text-secondary);
    }}

    .toggle-switch {{
      position: relative;
      display: inline-block;
      width: 60px;
      height: 28px;
    }}

    .toggle-switch input {{
      opacity: 0;
      width: 0;
      height: 0;
    }}

    .toggle-slider {{
      position: absolute;
      cursor: pointer;
      top: 0;
      left: 0;
      right: 0;
      bottom: 0;
      background-color: var(--bg-input);
      border: var(--pixel-border) solid var(--border-primary);
      transition: 0.3s;
    }}

    .toggle-slider::before {{
      position: absolute;
      content: "";
      height: 18px;
      width: 22px;
      left: 3px;
      bottom: 3px;
      background-color: var(--text-primary);
      transition: 0.3s;
      box-shadow: 0 0 6px var(--glow-color);
    }}

    .toggle-switch input:checked + .toggle-slider::before {{
      transform: translateX(28px);
    }}

    /* ========================================
       STICKY SUMMARY CARDS
       ======================================== */
    .summary-container {{
      position: sticky;
      top: 0;
      z-index: 100;
      background: var(--bg-primary);
      padding: 16px 0;
      border-bottom: var(--pixel-border) solid var(--border-primary);
      margin-bottom: 24px;
      box-shadow: 0 4px 16px rgba(0, 0, 0, 0.5);
    }}

    .section-label {{
      font-size: 12px;
      color: var(--text-secondary);
      margin-bottom: 12px;
    }}

    /* Header flex container for KEY METRICS and Today date */
    .metrics-header {{
      display: flex;
      justify-content: space-between;
      align-items: center;
      margin-bottom: 12px;
      flex-wrap: wrap;
      gap: 12px;
    }}

    .today-block {{
      background: var(--bg-card);
      border: var(--pixel-border) solid var(--border-primary);
      padding: 8px 16px;
      font-size: 12px;
      color: var(--text-secondary);
      box-shadow: 2px 2px 0 var(--border-secondary);
      white-space: nowrap;
    }}

    .summary-grid {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
      gap: 16px;
    }}

    .trust-banner {{
      margin: 20px 0 32px;
      padding: 16px;
      border: var(--pixel-border) solid var(--border-primary);
      background: linear-gradient(135deg, rgba(255, 136, 0, 0.08), rgba(0, 0, 0, 0.2));
      box-shadow: 0 0 12px rgba(255, 170, 0, 0.2);
    }}

    .trust-grid {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
      gap: 12px;
    }}

    .trust-card {{
      border: 1px solid var(--border-secondary);
      background: var(--bg-card);
      padding: 12px;
      border-radius: 8px;
    }}

    .trust-label {{
      font-size: 8px;
      color: var(--text-dim);
      letter-spacing: 0.08em;
    }}

    .trust-value {{
      font-size: 14px;
      margin-top: 6px;
    }}

    .badge {{
      display: inline-block;
      padding: 2px 8px;
      border: 1px solid var(--border-secondary);
      border-radius: 999px;
      font-size: 8px;
      margin-left: 6px;
      color: var(--text-accent);
    }}

    .metric-card {{
      background: var(--bg-card);
      border: var(--pixel-border) solid var(--border-primary);
      padding: 12px;
      position: relative;
      box-shadow:
        4px 4px 0 var(--border-secondary),
        inset 0 0 20px rgba(0, 0, 0, 0.3);
      transition: transform 0.2s ease;
    }}

    .metric-card:hover {{
      transform: translateY(-2px);
    }}

    .metric-card.breach-card {{
      border-color: var(--negative-color);
      animation: breach-pulse 2s ease-in-out infinite;
    }}

    @keyframes breach-pulse {{
      0%, 100% {{ box-shadow: 4px 4px 0 var(--border-secondary), inset 0 0 20px rgba(255, 68, 68, 0.2); }}
      50% {{ box-shadow: 4px 4px 0 var(--negative-color), inset 0 0 30px rgba(255, 68, 68, 0.4); }}
    }}

    .card-header {{
      display: flex;
      justify-content: space-between;
      align-items: center;
      margin-bottom: 8px;
    }}

    .card-label {{
      font-size: 6px;
      color: var(--text-dim);
    }}

    .trend-indicator {{
      font-size: 10px;
      font-weight: bold;
    }}

    .trend-indicator.up {{
      color: var(--positive-color);
    }}

    .trend-indicator.down {{
      color: var(--negative-color);
    }}

    .card-value-row {{
      display: flex;
      align-items: baseline;
      gap: 8px;
      margin-bottom: 6px;
    }}

    .card-value {{
      font-size: 26px;
      font-weight: 400;
      color: var(--text-accent);
      text-shadow: 0 0 8px var(--glow-color);
    }}

    .card-value.breach-value {{
      color: var(--negative-color);
      text-shadow: 0 0 8px var(--negative-color);
    }}

    .card-unit {{
      font-size: 15px;
      color: var(--text-dim);
    }}

    .card-meta {{
      font-size: 10px;
      color: var(--text-muted);
      margin-bottom: 0;
      display: flex;
      gap: 8px;
      align-items: center;
    }}

    .change-value {{
      font-weight: bold;
    }}

    .change-value.positive {{
      color: var(--positive-color);
    }}

    .change-value.negative {{
      color: var(--negative-color);
    }}

    .sparkline {{
      display: none;
    }}

    .warning-badge {{
      display: none;
    }}

    .warning-icon {{
      color: var(--negative-color);
      font-size: 12px;
      animation: blink 1s infinite;
    }}

    @keyframes blink {{
      0%, 50% {{ opacity: 1; }}
      51%, 100% {{ opacity: 0.3; }}
    }}

    /* ========================================
       CHART SECTION
       ======================================== */
    .chart-section {{
      margin-bottom: 32px;
      background: var(--bg-card);
      border: var(--pixel-border) solid var(--border-primary);
      padding: 20px;
      box-shadow: 4px 4px 0 var(--border-secondary);
    }}

    .chart-wrapper {{
      position: relative;
      margin-top: 16px;
    }}

    #cashChart {{
      width: 100%;
      height: 80px;
      max-width: 1400px;
      display: block;
    }}

    .chart-legend {{
      display: flex;
      justify-content: center;
      gap: 24px;
      margin-top: 16px;
      flex-wrap: wrap;
    }}

    .legend-item {{
      display: flex;
      align-items: center;
      gap: 8px;
      font-size: 16px;
    }}

    .legend-color {{
      width: 20px;
      height: 3px;
      display: inline-block;
    }}

    .legend-color.cash {{
      background: var(--chart-cash);
      box-shadow: 0 0 4px var(--chart-cash);
    }}

    .legend-color.capital {{
      background: var(--chart-capital);
    }}

    .legend-color.receivables {{
      background: var(--chart-receivables);
    }}

    .chart-tooltip {{
      position: fixed;
      background: var(--bg-card);
      border: var(--pixel-border) solid var(--border-primary);
      padding: 12px;
      pointer-events: none;
      z-index: 2000;
      box-shadow: 4px 4px 0 var(--border-secondary);
      min-width: 200px;
    }}

    .chart-tooltip.hidden {{
      display: none;
    }}

    .tooltip-date {{
      font-size: 10px;
      color: var(--text-accent);
      margin-bottom: 8px;
      border-bottom: 1px solid var(--border-secondary);
      padding-bottom: 4px;
    }}

    .tooltip-row {{
      font-size: 14px;
      display: flex;
      justify-content: space-between;
      gap: 16px;
      margin: 4px 0;
    }}

    .tooltip-label {{
      color: var(--text-dim);
    }}

    .tooltip-value {{
      color: var(--text-accent);
      font-weight: bold;
    }}

    .tooltip-forecast {{
      font-size: 10px;
      color: var(--warning-color);
      margin-top: 6px;
      text-align: center;
    }}

    /* ========================================
       PERIOD STATISTICS SECTION
       ======================================== */
    .stats-section {{
      margin-bottom: 32px;
      background: var(--bg-card);
      border: var(--pixel-border) solid var(--border-primary);
      padding: 20px;
      box-shadow: 4px 4px 0 var(--border-secondary);
    }}

    .stats-grid {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(177px, 1fr));
      gap: 12px;
      margin-top: 16px;
    }}

    .stat-card {{
      background: var(--bg-table);
      border: var(--pixel-border) solid var(--border-secondary);
      padding: 12px;
      position: relative;
      box-shadow: 2px 2px 0 rgba(0, 0, 0, 0.3);
      min-height: 92px;
    }}

    .stat-card:hover {{
      transform: translateY(-1px);
      transition: transform 0.2s ease;
    }}

    .stat-card.yesterday {{
      grid-row: 2;
    }}

    .stat-label {{
      font-size: 10px;
      color: var(--text-dim);
      margin-bottom: 4px;
      display: block;
    }}

    .stat-value {{
      font-size: 23px;
      font-weight: 400;
      color: var(--text-accent);
      text-shadow: 0 0 4px var(--glow-color);
    }}

    .stat-unit {{
      font-size: 16px;
      color: var(--text-dim);
      margin-left: 4px;
    }}

    .stat-period {{
      font-size: 13px;
      color: var(--text-muted);
      margin-top: 4px;
    }}

    .stat-value.na {{
      color: var(--text-muted);
      font-style: italic;
    }}

    /* ========================================
       CONTROLS SECTION
       ======================================== */
    .controls-section {{
      margin-bottom: 24px;
    }}

    .retro-controls {{
      display: flex;
      gap: 24px;
      flex-wrap: wrap;
      align-items: center;
    }}

    .control-group {{
      display: flex;
      flex-direction: column;
      gap: 8px;
    }}

    .control-label {{
      font-size: 10px;
      color: var(--text-secondary);
    }}

    .retro-select {{
      font-family: 'VT323', monospace;
      font-size: 18px;
      background: var(--bg-input);
      color: var(--text-primary);
      border: var(--pixel-border) solid var(--border-primary);
      padding: 8px 32px 8px 12px;
      cursor: pointer;
      appearance: none;
      background-image: url('data:image/svg+xml;utf8,<svg fill="{{\'%23\' + \'ffaa00\'}}" height="24" viewBox="0 0 24 24" width="24" xmlns="http://www.w3.org/2000/svg"><path d="M7 10l5 5 5-5z"/></svg>');
      background-repeat: no-repeat;
      background-position: right 8px center;
      text-transform: uppercase;
      transition: all 0.2s;
    }}

    .retro-select:focus {{
      outline: none;
      box-shadow: 0 0 0 2px var(--glow-color);
    }}

    .retro-select:hover {{
      background: var(--bg-card);
    }}

    .retro-checkbox {{
      display: flex;
      align-items: center;
      gap: 12px;
      cursor: pointer;
      user-select: none;
      font-size: 16px;
    }}

    .retro-checkbox input[type="checkbox"] {{
      display: none;
    }}

    .checkbox-custom {{
      width: 20px;
      height: 20px;
      border: var(--pixel-border) solid var(--border-primary);
      background: var(--bg-input);
      position: relative;
      transition: all 0.2s;
    }}

    .retro-checkbox:hover .checkbox-custom {{
      background: var(--bg-card);
    }}

    .retro-checkbox input:checked + .checkbox-custom::after {{
      content: '✕';
      position: absolute;
      top: 50%;
      left: 50%;
      transform: translate(-50%, -50%);
      color: var(--text-accent);
      font-size: 16px;
      font-weight: bold;
    }}

    /* ========================================
       TABLE SECTION
       ======================================== */
    .table-section {{
      margin-bottom: 32px;
    }}

    /* Table navigation container */
    .table-nav-header {{
      display: flex;
      justify-content: space-between;
      align-items: center;
      margin-bottom: 12px;
      flex-wrap: wrap;
      gap: 12px;
    }}

    .table-nav-buttons {{
      display: flex;
      gap: 8px;
    }}

    .retro-nav-button {{
      background: var(--bg-card);
      border: var(--pixel-border) solid var(--border-primary);
      color: var(--text-primary);
      padding: 8px 16px;
      cursor: pointer;
      font-family: 'Press Start 2P', cursive;
      font-size: 10px;
      text-transform: uppercase;
      transition: all 0.2s;
      box-shadow: 2px 2px 0 var(--border-secondary);
    }}

    .retro-nav-button:hover {{
      transform: translateY(-2px);
      box-shadow: 4px 4px 0 var(--border-secondary);
      background: var(--bg-secondary);
    }}

    .retro-nav-button:active {{
      transform: translateY(0);
      box-shadow: 1px 1px 0 var(--border-secondary);
    }}

    .table-wrapper {{
      overflow: auto;
      max-height: 600px;
      border: var(--pixel-border) solid var(--border-primary);
      background: var(--bg-table);
      box-shadow: 4px 4px 0 var(--border-secondary);
    }}

    /* Custom scrollbar for table wrapper */
    .table-wrapper::-webkit-scrollbar {{
      width: 12px;
      height: 12px;
    }}

    .table-wrapper::-webkit-scrollbar-track {{
      background: var(--bg-secondary);
      border: 1px solid var(--border-primary);
    }}

    .table-wrapper::-webkit-scrollbar-thumb {{
      background: var(--border-primary);
      border: 2px solid var(--bg-secondary);
    }}

    .table-wrapper::-webkit-scrollbar-thumb:hover {{
      background: var(--text-secondary);
    }}

    .table-wrapper::-webkit-scrollbar-corner {{
      background: var(--bg-secondary);
    }}

    /* Firefox scrollbar styling */
    .table-wrapper {{
      scrollbar-color: var(--border-primary) var(--bg-secondary);
      scrollbar-width: thin;
    }}

    .retro-table {{
      width: 100%;
      border-collapse: separate;
      border-spacing: 0;
      font-size: 21px;
    }}

    .retro-table thead {{
      position: sticky;
      top: 0;
      z-index: 90;
    }}

    .retro-table thead th {{
      background: var(--bg-secondary);
      color: var(--text-accent);
      border: 1px solid var(--border-primary);
      padding: 10px 12px;
      text-align: right;
      font-weight: bold;
      white-space: nowrap;
    }}

    .retro-table tbody td {{
      border: 1px solid var(--border-secondary);
      padding: 8px 12px;
      text-align: right;
      background: var(--bg-table);
    }}

    .retro-table tbody tr:nth-child(even) td {{
      background: var(--bg-card);
    }}

    .retro-table tbody tr:hover td {{
      background: var(--bg-secondary);
    }}

    .retro-table td:first-child,
    .retro-table th:first-child {{
      position: sticky;
      left: 0;
      z-index: 80;
      text-align: left;
    }}

    .retro-table thead th:first-child {{
      z-index: 95;
      background: var(--bg-secondary);
    }}

    .date-cell {{
      font-weight: bold;
      white-space: nowrap;
      color: var(--text-accent);
    }}

    .negative-value {{
      color: var(--negative-color);
    }}

    .forecast-row {{
      background: var(--bg-input);
      font-style: italic;
    }}

    /* ========================================
       FOOTER
       ======================================== */
    .retro-footer {{
      margin-top: 48px;
      padding-top: 16px;
      border-top: var(--pixel-border) solid var(--border-primary);
      text-align: center;
      font-size: 14px;
      color: var(--text-dim);
      position: relative;
    }}

    .footer-text {{
      animation: footer-glow 3s ease-in-out infinite;
    }}

    @keyframes footer-glow {{
      0%, 100% {{ opacity: 0.6; }}
      50% {{ opacity: 1; }}
    }}

    /* ========================================
       RESPONSIVE
       ======================================== */
    @media (max-width: 768px) {{
      .pixel-title {{
        font-size: 14px;
      }}

      .summary-grid {{
        grid-template-columns: 1fr;
      }}

      #cashChart {{
        height: 60px;
      }}

      .retro-table {{
        font-size: 14px;
      }}

      .card-value {{
        font-size: 20px;
      }}
    }}
  </style>
</head>

<body class="theme-dark">
  <div class="retro-container">
    <!-- Header -->
    <header class="retro-header">
      <div class="title-bar">
        <div>
          <h1 class="pixel-title pixel-font">CASHFLOW MONITOR</h1>
          <div class="subtitle monospace-font">Financial Command Center</div>
        </div>
        <div class="theme-toggle-container">
          <label class="toggle-switch">
            <input type="checkbox" id="themeToggle">
            <span class="toggle-slider"></span>
          </label>
          <span class="toggle-label monospace-font">AMBER / BEIGE</span>
        </div>
      </div>
    </header>

    <!-- Trust Banner -->
    <section class="trust-banner">
      <div class="section-label pixel-font">TRUST STATUS</div>
      <div class="trust-grid" id="trustSummary"></div>
    </section>

    <!-- Summary Cards -->
    <section class="summary-container">
      <div class="metrics-header">
        <div class="section-label pixel-font">KEY METRICS</div>
        <div class="today-block pixel-font" id="todayDate"></div>
      </div>
      <div class="summary-grid" id="summary"></div>
    </section>

    <!-- Chart -->
    <section class="chart-section">
      <div class="section-label pixel-font">CAPITAL VISUALIZATION</div>
      <div class="chart-wrapper">
        <canvas id="cashChart"></canvas>
        <div class="chart-legend">
          <div class="legend-item monospace-font">
            <span class="legend-color cash"></span>
            <span class="legend-label">Cash Balance</span>
          </div>
          <div class="legend-item monospace-font">
            <span class="legend-color capital"></span>
            <span class="legend-label">Total Capital</span>
          </div>
          <div class="legend-item monospace-font">
            <span class="legend-color receivables"></span>
            <span class="legend-label">Receivables</span>
          </div>
        </div>
      </div>
    </section>

    <!-- Period Statistics -->
    <section class="stats-section">
      <div class="section-label pixel-font">PERIOD STATISTICS</div>
      <div class="stats-grid" id="statsGrid"></div>
    </section>

    <!-- Tooltip -->
    <div id="chartTooltip" class="chart-tooltip hidden monospace-font"></div>

    <!-- Controls -->
    <section class="controls-section">
      <div class="retro-controls">
        <div class="control-group">
          <label class="control-label pixel-font">TIME RANGE</label>
          <select id="rangeSelect" class="retro-select">
            <option value="30">LAST 30 DAYS</option>
            <option value="90" selected>LAST 90 DAYS</option>
            <option value="all">ALL DATA</option>
          </select>
        </div>
        <div class="control-group">
          <label class="retro-checkbox">
            <input type="checkbox" id="forecastToggle" checked>
            <span class="checkbox-custom"></span>
            <span class="pixel-font">INCLUDE FORECAST</span>
          </label>
        </div>
        <div class="control-group">
          <label class="retro-checkbox">
            <input type="checkbox" id="statementToggle">
            <span class="checkbox-custom"></span>
            <span class="pixel-font">STATEMENT ONLY</span>
          </label>
        </div>
        <div class="control-group">
          <label class="control-label pixel-font">STORE</label>
          <select id="storeSelect" class="retro-select"></select>
        </div>
      </div>
    </section>

    <!-- Data Table -->
    <section class="table-section">
      <div class="table-nav-header">
        <div class="section-label pixel-font">DETAILED LEDGER</div>
        <div class="table-nav-buttons">
          <button class="retro-nav-button" id="scrollToTop">▲ TOP</button>
          <button class="retro-nav-button" id="scrollToBottom">▼ BOTTOM</button>
        </div>
      </div>
      <div class="table-wrapper" id="tableWrapper">
        <table id="table" class="retro-table monospace-font"></table>
      </div>
    </section>

    <!-- Footer -->
    <footer class="retro-footer">
      <div class="footer-text monospace-font">
        SYSTEM OPERATIONAL // DATA REFRESH: <span id="refreshTime"></span>
      </div>
    </footer>
  </div>

  <script>
    // ========================================
    // DATA INJECTION
    // ========================================
    const rows = {data};
    const meta = {meta_json};

    // ========================================
    // DOM ELEMENTS
    // ========================================
    const summary = document.getElementById('summary');
    const trustSummary = document.getElementById('trustSummary');
    const forecastToggle = document.getElementById('forecastToggle');
    const statementToggle = document.getElementById('statementToggle');
    const rangeSelect = document.getElementById('rangeSelect');
    const storeSelect = document.getElementById('storeSelect');
    const themeToggle = document.getElementById('themeToggle');
    const body = document.body;
    const chartCanvas = document.getElementById('cashChart');
    const tooltip = document.getElementById('chartTooltip');

    const storeCodes = Array.from(new Set(rows.map(r => r.store_code).filter(Boolean)));
    const storeOptions = ['ALL', ...storeCodes];
    storeSelect.innerHTML = storeOptions.map(code => `<option value="${{code}}">${{code}}</option>`).join('');
    storeSelect.disabled = storeOptions.length <= 1;

    // ========================================
    // THEME MANAGEMENT
    // ========================================
    const savedTheme = localStorage.getItem('cashflow-theme') || 'dark';
    if (savedTheme === 'light') {{
      body.classList.remove('theme-dark');
      body.classList.add('theme-light');
      themeToggle.checked = true;
    }}

    themeToggle.addEventListener('change', function() {{
      if (this.checked) {{
        body.classList.remove('theme-dark');
        body.classList.add('theme-light');
        localStorage.setItem('cashflow-theme', 'light');
      }} else {{
        body.classList.remove('theme-light');
        body.classList.add('theme-dark');
        localStorage.setItem('cashflow-theme', 'dark');
      }}
      renderChart();
    }});

    // ========================================
    // HELPER FUNCTIONS
    // ========================================
    function formatKzt(val) {{
      const num = Math.round(Number(val || 0));
      return num.toString().replace(/\B(?=(\d{{{3}}})+(?!\d))/g, ' ');
    }}

    function calculateTrends(data) {{
      if (data.length < 2) return null;

      const recent = data[data.length - 1];
      const previous30 = data.length > 30 ? data[data.length - 31] : data[0];

      const trends = {{}};

      ['cash_close', 'receivables_close', 'inventory_cost_close', 'capital_close'].forEach(key => {{
        const currentVal = Number(recent[key] || 0);
        const previousVal = Number(previous30[key] || 0);
        const change = currentVal - previousVal;
        const changePercent = previousVal !== 0 ? (change / Math.abs(previousVal)) * 100 : 0;

        trends[key] = {{
          current: currentVal,
          previous: previousVal,
          change: change,
          changePercent: changePercent,
          direction: change >= 0 ? 'up' : 'down',
          isPositive: change >= 0
        }};
      }});

      return trends;
    }}

    function buildTrustSummary() {{
      const statementDate = meta.last_statement_date || 'NONE';
      const syncAge = meta.order_sync_age_hours !== null && meta.order_sync_age_hours !== undefined
        ? (meta.order_sync_age_hours.toFixed(1) + 'h')
        : 'UNKNOWN';
      const baseMin = meta.min_cash_base || {{}};
      const consMin = meta.min_cash_conservative || baseMin;
      trustSummary.innerHTML = `
        <div class="trust-card">
          <div class="trust-label pixel-font">LAST STATEMENT</div>
          <div class="trust-value monospace-font">${{statementDate}}<span class="badge">ACTUAL</span></div>
        </div>
        <div class="trust-card">
          <div class="trust-label pixel-font">ORDER SYNC AGE</div>
          <div class="trust-value monospace-font">${{syncAge}}</div>
        </div>
        <div class="trust-card">
          <div class="trust-label pixel-font">MIN CASH (BASE)</div>
          <div class="trust-value monospace-font">${{formatKzt(baseMin.cash_close)}} KZT on ${{baseMin.date}}</div>
        </div>
        <div class="trust-card">
          <div class="trust-label pixel-font">MIN CASH (CONS)</div>
          <div class="trust-value monospace-font">${{formatKzt(consMin.cash_close)}} KZT on ${{consMin.date}}</div>
        </div>
      `;
    }}

    function filterRows() {{
      let filtered = rows.slice();
      if (!forecastToggle.checked) {{
        filtered = filtered.filter(r => !r.is_forecast);
      }}
      if (statementToggle.checked) {{
        filtered = filtered.filter(r => r.trust === 'STATEMENT_ACTUAL');
      }}
      const storeVal = storeSelect.value;
      if (storeVal && storeVal !== 'ALL') {{
        filtered = filtered.filter(r => r.store_code === storeVal);
      }}
      const rangeVal = rangeSelect.value;
      if (rangeVal !== 'all') {{
        const n = parseInt(rangeVal, 10);
        filtered = filtered.slice(-n);
      }}
      return filtered;
    }}

    // ========================================
    // SPARKLINE RENDERING
    // ========================================
    function renderSparkline(canvasId, data, key) {{
      const canvas = document.getElementById(canvasId);
      if (!canvas) return;

      const ctx = canvas.getContext('2d');
      const width = canvas.width;
      const height = canvas.height;

      ctx.clearRect(0, 0, width, height);

      const values = data.slice(-30).map(r => Number(r[key] || 0));
      if (values.length < 2) return;

      const min = Math.min(...values);
      const max = Math.max(...values);
      const range = max - min || 1;

      const isLightTheme = body.classList.contains('theme-light');
      const lineColor = isLightTheme ? '#2d2520' : '#ffaa00';

      ctx.strokeStyle = lineColor;
      ctx.lineWidth = 2;
      ctx.beginPath();

      values.forEach((val, i) => {{
        const x = (i / (values.length - 1)) * width;
        const y = height - ((val - min) / range) * (height - 4) - 2;

        if (i === 0) {{
          ctx.moveTo(x, y);
        }} else {{
          ctx.lineTo(x, y);
        }}
      }});

      ctx.stroke();
    }}

    // ========================================
    // SUMMARY CARDS
    // ========================================
    function buildSummary(rows) {{
      if (!rows.length) {{
        summary.innerHTML = '<div class="monospace-font">NO DATA AVAILABLE</div>';
        return;
      }}

      const actualData = rows.filter(r => !r.is_forecast);
      const last = actualData.length > 0 ? actualData[actualData.length - 1] : rows[rows.length - 1];
      const lastDate = new Date(last.date);
      const futureRows = rows.filter(r => new Date(r.date) > lastDate);

      const next14 = futureRows.filter(r => (new Date(r.date) - lastDate) <= 14 * 24 * 3600 * 1000);
      const next30 = futureRows.filter(r => (new Date(r.date) - lastDate) <= 30 * 24 * 3600 * 1000);
      const next60 = futureRows.filter(r => (new Date(r.date) - lastDate) <= 60 * 24 * 3600 * 1000);

      const payouts14 = next14.reduce((sum, r) => sum + Number(r.payouts_received_kzt || 0), 0);
      const po30 = next30.reduce((sum, r) => sum + Number(r.po_payments_kzt || 0), 0);
      const po60 = next60.reduce((sum, r) => sum + Number(r.po_payments_kzt || 0), 0);

      const trends = calculateTrends(actualData.length > 0 ? actualData : rows);

      const minRow = rows.reduce((a, b) => (a.cash_close < b.cash_close ? a : b));
      const breach = (minRow.cash_close || 0) < 0;

      let breachWarning = '';
      if (!breach && trends && trends.cash_close.direction === 'down') {{
        const daysToZero = Math.abs(trends.cash_close.current / (trends.cash_close.change / 30));
        if (daysToZero < 60 && daysToZero > 0) {{
          breachWarning = `<div class="warning-badge pixel-font">! ${{Math.floor(daysToZero)}} DAYS TO ZERO</div>`;
        }}
      }}

      summary.innerHTML = `
        <div class="metric-card">
          <div class="card-header">
            <span class="card-label pixel-font">CASH BALANCE</span>
            ${{trends ? `<span class="trend-indicator ${{trends.cash_close.direction}}">${{trends.cash_close.direction === 'up' ? '▲' : '▼'}}</span>` : ''}}
          </div>
          <div class="card-value-row">
            <span class="card-value monospace-font">${{formatKzt(last.cash_close)}}</span>
            <span class="card-unit">KZT</span>
          </div>
          ${{trends ? `
            <div class="card-meta">
              <span class="change-value ${{trends.cash_close.isPositive ? 'positive' : 'negative'}}">
                ${{trends.cash_close.isPositive ? '+' : ''}}${{trends.cash_close.changePercent.toFixed(1)}}%
              </span>
              <span class="change-period">vs 30d</span>
            </div>
          ` : ''}}
          <canvas class="sparkline" id="sparkline-cash" width="240" height="30"></canvas>
          ${{breachWarning}}
        </div>

        <div class="metric-card">
          <div class="card-header">
            <span class="card-label pixel-font">RECEIVABLES</span>
            ${{trends ? `<span class="trend-indicator ${{trends.receivables_close.direction}}">${{trends.receivables_close.direction === 'up' ? '▲' : '▼'}}</span>` : ''}}
          </div>
          <div class="card-value-row">
            <span class="card-value monospace-font">${{formatKzt(last.receivables_close)}}</span>
            <span class="card-unit">KZT</span>
          </div>
          ${{trends ? `
            <div class="card-meta">
              <span class="change-value ${{trends.receivables_close.isPositive ? 'positive' : 'negative'}}">
                ${{trends.receivables_close.isPositive ? '+' : ''}}${{trends.receivables_close.changePercent.toFixed(1)}}%
              </span>
              <span class="change-period">vs 30d</span>
            </div>
          ` : ''}}
          <canvas class="sparkline" id="sparkline-receivables" width="240" height="30"></canvas>
        </div>

        <div class="metric-card">
          <div class="card-header">
            <span class="card-label pixel-font">INVENTORY COST</span>
            ${{trends ? `<span class="trend-indicator ${{trends.inventory_cost_close.direction}}">${{trends.inventory_cost_close.direction === 'up' ? '▲' : '▼'}}</span>` : ''}}
          </div>
          <div class="card-value-row">
            <span class="card-value monospace-font">${{formatKzt(last.inventory_cost_close)}}</span>
            <span class="card-unit">KZT</span>
          </div>
          ${{trends ? `
            <div class="card-meta">
              <span class="change-value ${{trends.inventory_cost_close.isPositive ? 'positive' : 'negative'}}">
                ${{trends.inventory_cost_close.isPositive ? '+' : ''}}${{trends.inventory_cost_close.changePercent.toFixed(1)}}%
              </span>
              <span class="change-period">vs 30d</span>
            </div>
          ` : ''}}
          <canvas class="sparkline" id="sparkline-inventory" width="240" height="30"></canvas>
        </div>

        <div class="metric-card">
          <div class="card-header">
            <span class="card-label pixel-font">TOTAL CAPITAL</span>
            ${{trends ? `<span class="trend-indicator ${{trends.capital_close.direction}}">${{trends.capital_close.direction === 'up' ? '▲' : '▼'}}</span>` : ''}}
          </div>
          <div class="card-value-row">
            <span class="card-value monospace-font">${{formatKzt(last.capital_close)}}</span>
            <span class="card-unit">KZT</span>
          </div>
          ${{trends ? `
            <div class="card-meta">
              <span class="change-value ${{trends.capital_close.isPositive ? 'positive' : 'negative'}}">
                ${{trends.capital_close.isPositive ? '+' : ''}}${{trends.capital_close.changePercent.toFixed(1)}}%
              </span>
              <span class="change-period">vs 30d</span>
            </div>
          ` : ''}}
          <canvas class="sparkline" id="sparkline-capital" width="240" height="30"></canvas>
        </div>

        <div class="metric-card ${{breach ? 'breach-card' : ''}}">
          <div class="card-header">
            <span class="card-label pixel-font">MINIMUM CASH</span>
            ${{breach ? '<span class="warning-icon pixel-font">!</span>' : ''}}
          </div>
          <div class="card-value-row">
            <span class="card-value ${{breach ? 'breach-value' : ''}} monospace-font">${{formatKzt(minRow.cash_close)}}</span>
            <span class="card-unit">KZT</span>
          </div>
          <div class="card-meta">
            <span class="change-period">${{minRow.date}}</span>
          </div>
          ${{breach ? '<div class="warning-badge pixel-font">BREACH DETECTED</div>' : ''}}
        </div>

        <div class="metric-card">
          <div class="card-header">
            <span class="card-label pixel-font">PAYOUTS (NEXT 14D)</span>
          </div>
          <div class="card-value-row">
            <span class="card-value monospace-font">${{formatKzt(payouts14)}}</span>
            <span class="card-unit">KZT</span>
          </div>
          <div class="card-meta">
            <span class="change-period">expected cash-in</span>
          </div>
        </div>

        <div class="metric-card">
          <div class="card-header">
            <span class="card-label pixel-font">PO PAYMENTS (30D)</span>
          </div>
          <div class="card-value-row">
            <span class="card-value monospace-font">${{formatKzt(po30)}}</span>
            <span class="card-unit">KZT</span>
          </div>
          <div class="card-meta">
            <span class="change-period">commitments</span>
          </div>
        </div>

        <div class="metric-card">
          <div class="card-header">
            <span class="card-label pixel-font">PO PAYMENTS (60D)</span>
          </div>
          <div class="card-value-row">
            <span class="card-value monospace-font">${{formatKzt(po60)}}</span>
            <span class="card-unit">KZT</span>
          </div>
          <div class="card-meta">
            <span class="change-period">commitments</span>
          </div>
        </div>
      `;

      setTimeout(() => {{
        renderSparkline('sparkline-cash', actualData.length > 0 ? actualData : rows, 'cash_close');
        renderSparkline('sparkline-receivables', actualData.length > 0 ? actualData : rows, 'receivables_close');
        renderSparkline('sparkline-inventory', actualData.length > 0 ? actualData : rows, 'inventory_cost_close');
        renderSparkline('sparkline-capital', actualData.length > 0 ? actualData : rows, 'capital_close');
      }}, 10);
    }}

    // ========================================
    // PERIOD STATISTICS CALCULATIONS
    // ========================================
    function calculatePeriodStats(rows) {{
      const actualData = rows.filter(r => !r.is_forecast);

      if (actualData.length === 0) {{
        return null;
      }}

      const sortedData = actualData.slice().sort((a, b) =>
        a.date.localeCompare(b.date)
      );

      const result = {{
        yesterday: {{}},
        avg7d: {{}},
        avg14d: {{}}
      }};

      // Yesterday = most recent actual date
      const yesterday = sortedData[sortedData.length - 1];
      result.yesterday = {{
        cash: Number(yesterday.cash_close || 0),
        receivables: Number(yesterday.receivables_close || 0),
        cogs: Number(yesterday.cogs_kzt || 0),
        profit: Number(yesterday.profit_accrual_kzt || 0),
        soldUnits: 'N/A',
        date: yesterday.date
      }};

      // 7-day averages
      const last7Days = sortedData.slice(-7);
      if (last7Days.length > 0) {{
        result.avg7d.receivables = last7Days.reduce((sum, r) =>
          sum + Number(r.receivables_close || 0), 0) / last7Days.length;
        result.avg7d.cogs = last7Days.reduce((sum, r) =>
          sum + Number(r.cogs_kzt || 0), 0) / last7Days.length;
        result.avg7d.profit = last7Days.reduce((sum, r) =>
          sum + Number(r.profit_accrual_kzt || 0), 0) / last7Days.length;
      }}

      // 14-day averages
      const last14Days = sortedData.slice(-14);
      if (last14Days.length > 0) {{
        result.avg14d.receivables = last14Days.reduce((sum, r) =>
          sum + Number(r.receivables_close || 0), 0) / last14Days.length;
        result.avg14d.cogs = last14Days.reduce((sum, r) =>
          sum + Number(r.cogs_kzt || 0), 0) / last14Days.length;
        result.avg14d.profit = last14Days.reduce((sum, r) =>
          sum + Number(r.profit_accrual_kzt || 0), 0) / last14Days.length;
      }}

      return result;
    }}

    // ========================================
    // RENDER PERIOD STATISTICS
    // ========================================
    function renderPeriodStats(rows) {{
      const statsGrid = document.getElementById('statsGrid');
      if (!statsGrid) return;

      const stats = calculatePeriodStats(rows);

      if (!stats) {{
        statsGrid.innerHTML = '<div class="monospace-font">NO ACTUAL DATA AVAILABLE</div>';
        return;
      }}

      statsGrid.innerHTML = `
        <!-- 7-Day Averages -->
        <div class="stat-card">
          <span class="stat-label pixel-font">7D AVG RECEIVABLES</span>
          <div>
            <span class="stat-value monospace-font">${{formatKzt(stats.avg7d.receivables || 0)}}</span>
            <span class="stat-unit">KZT</span>
          </div>
          <div class="stat-period monospace-font">Last 7 days</div>
        </div>

        <div class="stat-card">
          <span class="stat-label pixel-font">7D AVG COGS</span>
          <div>
            <span class="stat-value monospace-font">${{formatKzt(stats.avg7d.cogs || 0)}}</span>
            <span class="stat-unit">KZT</span>
          </div>
          <div class="stat-period monospace-font">Last 7 days</div>
        </div>

        <div class="stat-card">
          <span class="stat-label pixel-font">7D AVG PROFIT</span>
          <div>
            <span class="stat-value monospace-font">${{formatKzt(stats.avg7d.profit || 0)}}</span>
            <span class="stat-unit">KZT</span>
          </div>
          <div class="stat-period monospace-font">Last 7 days</div>
        </div>

        <!-- 14-Day Averages -->
        <div class="stat-card">
          <span class="stat-label pixel-font">14D AVG RECEIVABLES</span>
          <div>
            <span class="stat-value monospace-font">${{formatKzt(stats.avg14d.receivables || 0)}}</span>
            <span class="stat-unit">KZT</span>
          </div>
          <div class="stat-period monospace-font">Last 14 days</div>
        </div>

        <div class="stat-card">
          <span class="stat-label pixel-font">14D AVG COGS</span>
          <div>
            <span class="stat-value monospace-font">${{formatKzt(stats.avg14d.cogs || 0)}}</span>
            <span class="stat-unit">KZT</span>
          </div>
          <div class="stat-period monospace-font">Last 14 days</div>
        </div>

        <div class="stat-card">
          <span class="stat-label pixel-font">14D AVG PROFIT</span>
          <div>
            <span class="stat-value monospace-font">${{formatKzt(stats.avg14d.profit || 0)}}</span>
            <span class="stat-unit">KZT</span>
          </div>
          <div class="stat-period monospace-font">Last 14 days</div>
        </div>

        <!-- Yesterday's Values -->
        <div class="stat-card yesterday">
          <span class="stat-label pixel-font">YESTERDAY CASH</span>
          <div>
            <span class="stat-value monospace-font">${{formatKzt(stats.yesterday.cash)}}</span>
            <span class="stat-unit">KZT</span>
          </div>
          <div class="stat-period monospace-font">${{stats.yesterday.date}}</div>
        </div>

        <div class="stat-card yesterday">
          <span class="stat-label pixel-font">YESTERDAY RECEIVABLES</span>
          <div>
            <span class="stat-value monospace-font">${{formatKzt(stats.yesterday.receivables)}}</span>
            <span class="stat-unit">KZT</span>
          </div>
          <div class="stat-period monospace-font">${{stats.yesterday.date}}</div>
        </div>

        <div class="stat-card yesterday">
          <span class="stat-label pixel-font">YESTERDAY COGS</span>
          <div>
            <span class="stat-value monospace-font">${{formatKzt(stats.yesterday.cogs)}}</span>
            <span class="stat-unit">KZT</span>
          </div>
          <div class="stat-period monospace-font">${{stats.yesterday.date}}</div>
        </div>

        <div class="stat-card yesterday">
          <span class="stat-label pixel-font">YESTERDAY PROFIT</span>
          <div>
            <span class="stat-value monospace-font">${{formatKzt(stats.yesterday.profit)}}</span>
            <span class="stat-unit">KZT</span>
          </div>
          <div class="stat-period monospace-font">${{stats.yesterday.date}}</div>
        </div>

        <div class="stat-card yesterday">
          <span class="stat-label pixel-font">YESTERDAY SOLD UNITS</span>
          <div>
            <span class="stat-value na monospace-font">${{stats.yesterday.soldUnits}}</span>
          </div>
          <div class="stat-period monospace-font">${{stats.yesterday.date}}</div>
        </div>
      `;
    }}

    // ========================================
    // CHART RENDERING
    // ========================================
    function renderChart() {{
      const data = filterRows();
      const canvas = chartCanvas;
      const ctx = canvas.getContext('2d');

      // Set canvas size
      canvas.width = canvas.offsetWidth;
      canvas.height = 80;

      ctx.clearRect(0, 0, canvas.width, canvas.height);

      if (!data.length) return;

      const padding = {{ top: 20, right: 40, bottom: 40, left: 60 }};
      const width = canvas.width - padding.left - padding.right;
      const height = canvas.height - padding.top - padding.bottom;

      const isLightTheme = body.classList.contains('theme-light');
      const colors = {{
        cash: isLightTheme ? '#2d2520' : '#ffaa00',
        capital: isLightTheme ? '#0088aa' : '#00ddff',
        receivables: isLightTheme ? '#aa3355' : '#ff6688',
        grid: isLightTheme ? 'rgba(45, 37, 32, 0.08)' : 'rgba(255, 170, 0, 0.12)',
        axis: isLightTheme ? 'rgba(45, 37, 32, 0.3)' : 'rgba(255, 170, 0, 0.4)',
        text: isLightTheme ? '#2d2520' : '#ffaa00'
      }};

      const cashValues = data.map(r => Number(r.cash_close || 0));
      const capitalValues = data.map(r => Number(r.capital_close || 0));
      const receivablesValues = data.map(r => Number(r.receivables_close || 0));

      const allValues = [...cashValues, ...capitalValues, ...receivablesValues];
      const minVal = Math.min(...allValues);
      const maxVal = Math.max(...allValues);
      const range = maxVal - minVal || 1;

      function getY(val) {{
        return padding.top + height - ((val - minVal) / range) * height;
      }}

      function getX(i) {{
        return padding.left + (width * i) / Math.max(data.length - 1, 1);
      }}

      // Draw grid
      ctx.strokeStyle = colors.grid;
      ctx.lineWidth = 1;

      for (let i = 0; i <= 5; i++) {{
        const y = padding.top + (height / 5) * i;
        ctx.beginPath();
        ctx.moveTo(padding.left, y);
        ctx.lineTo(padding.left + width, y);
        ctx.stroke();
      }}

      const gridInterval = Math.max(Math.floor(data.length / 10), 1);
      for (let i = 0; i < data.length; i += gridInterval) {{
        const x = getX(i);
        ctx.beginPath();
        ctx.moveTo(x, padding.top);
        ctx.lineTo(x, padding.top + height);
        ctx.stroke();
      }}

      // Draw axes
      ctx.strokeStyle = colors.axis;
      ctx.lineWidth = 2;
      ctx.beginPath();
      ctx.moveTo(padding.left, padding.top);
      ctx.lineTo(padding.left, padding.top + height);
      ctx.lineTo(padding.left + width, padding.top + height);
      ctx.stroke();

      // Draw axis labels
      ctx.fillStyle = colors.text;
      ctx.font = '21px VT323';
      ctx.textAlign = 'right';
      ctx.fillText(formatKzt(maxVal), padding.left - 10, padding.top + 5);
      ctx.fillText(formatKzt(minVal), padding.left - 10, padding.top + height + 5);

      // Y-axis label
      ctx.save();
      ctx.translate(20, padding.top + height / 2);
      ctx.rotate(-Math.PI / 2);
      ctx.textAlign = 'center';
      ctx.font = '23px VT323';
      ctx.fillText('KZT', 0, 0);
      ctx.restore();

      // X-axis labels
      ctx.textAlign = 'center';
      ctx.font = '21px VT323';
      const labelInterval = Math.max(Math.floor(data.length / 6), 1);
      for (let i = 0; i < data.length; i += labelInterval) {{
        const x = getX(i);
        const date = data[i].date.substring(5);
        ctx.fillText(date, x, padding.top + height + 25);
      }}

      // Draw lines
      function drawLine(values, color, withGlow = false) {{
        if (withGlow && !isLightTheme) {{
          ctx.shadowBlur = 8;
          ctx.shadowColor = color;
        }}

        ctx.strokeStyle = color;
        ctx.lineWidth = 3;
        ctx.beginPath();

        values.forEach((val, i) => {{
          const x = getX(i);
          const y = getY(val);

          if (i === 0) {{
            ctx.moveTo(x, y);
          }} else {{
            ctx.lineTo(x, y);
          }}
        }});

        ctx.stroke();

        if (withGlow) {{
          ctx.shadowBlur = 0;
        }}
      }}

      drawLine(receivablesValues, colors.receivables, false);
      drawLine(capitalValues, colors.capital, false);
      drawLine(cashValues, colors.cash, true);

      canvas.chartData = {{
        data: data,
        padding: padding,
        width: width,
        height: height,
        minVal: minVal,
        maxVal: maxVal,
        getX: getX,
        getY: getY
      }};
    }}

    // ========================================
    // CHART TOOLTIP
    // ========================================
    chartCanvas.addEventListener('mousemove', function(e) {{
      if (!this.chartData) return;

      const rect = this.getBoundingClientRect();
      const x = e.clientX - rect.left;
      const y = e.clientY - rect.top;

      const {{ data, padding, width }} = this.chartData;

      if (x < padding.left || x > padding.left + width) {{
        tooltip.classList.add('hidden');
        return;
      }}

      const relativeX = x - padding.left;
      const index = Math.round((relativeX / width) * (data.length - 1));

      if (index < 0 || index >= data.length) {{
        tooltip.classList.add('hidden');
        return;
      }}

      const point = data[index];

      const tooltipHTML = `
        <div class="tooltip-date pixel-font">${{point.date}}</div>
        <div class="tooltip-row">
          <span class="tooltip-label">Cash:</span>
          <span class="tooltip-value">${{formatKzt(point.cash_close)}} KZT</span>
        </div>
        <div class="tooltip-row">
          <span class="tooltip-label">Capital:</span>
          <span class="tooltip-value">${{formatKzt(point.capital_close)}} KZT</span>
        </div>
        <div class="tooltip-row">
          <span class="tooltip-label">Receivables:</span>
          <span class="tooltip-value">${{formatKzt(point.receivables_close)}} KZT</span>
        </div>
        <div class="tooltip-row">
          <span class="tooltip-label">Trust:</span>
          <span class="tooltip-value">${{point.trust || ''}}</span>
        </div>
        ${{point.is_forecast ? '<div class="tooltip-forecast pixel-font">FORECAST</div>' : ''}}
      `;

      tooltip.innerHTML = tooltipHTML;
      tooltip.style.left = (e.clientX + 15) + 'px';
      tooltip.style.top = (e.clientY + 15) + 'px';
      tooltip.classList.remove('hidden');
    }});

    chartCanvas.addEventListener('mouseleave', function() {{
      tooltip.classList.add('hidden');
    }});

    // ========================================
    // TABLE RENDERING
    // ========================================
    function renderTable() {{
      const data = filterRows();
      const table = document.getElementById('table');

      if (!data.length) {{
        table.innerHTML = '<tr><td class="monospace-font">NO DATA AVAILABLE</td></tr>';
        return;
      }}

      const headers = Object.keys(data[0]);

      let headerHTML = '<thead><tr>';
      headers.forEach(h => {{
        const displayName = h.replace(/_/g, ' ').toUpperCase();
        headerHTML += `<th class="pixel-font">${{displayName}}</th>`;
      }});
      headerHTML += '</tr></thead>';

      let bodyHTML = '<tbody>';
      data.forEach(row => {{
        const rowClass = row.is_forecast ? 'forecast-row' : '';
        bodyHTML += `<tr class="${{rowClass}}">`;
        headers.forEach(h => {{
          let cellValue = row[h] ?? '';
          let cellClass = 'monospace-font';

          if (h === 'date') {{
            cellClass += ' date-cell';
            cellValue = `<strong>${{cellValue}}</strong>`;
          }}
          else if (typeof cellValue === 'number' || !isNaN(cellValue)) {{
            cellValue = formatKzt(cellValue);

            if (Number(row[h]) < 0) {{
              cellClass += ' negative-value';
            }}
          }}

          bodyHTML += `<td class="${{cellClass}}">${{cellValue}}</td>`;
        }});
        bodyHTML += '</tr>';
      }});
      bodyHTML += '</tbody>';

      table.innerHTML = headerHTML + bodyHTML;
    }}

    // ========================================
    // TABLE NAVIGATION
    // ========================================
    function setupTableNavigation() {{
      const tableWrapper = document.getElementById('tableWrapper');
      const scrollToTop = document.getElementById('scrollToTop');
      const scrollToBottom = document.getElementById('scrollToBottom');

      if (scrollToTop && tableWrapper) {{
        scrollToTop.addEventListener('click', function() {{
          tableWrapper.scrollTo({{
            top: 0,
            behavior: 'instant'
          }});
        }});
      }}

      if (scrollToBottom && tableWrapper) {{
        scrollToBottom.addEventListener('click', function() {{
          tableWrapper.scrollTo({{
            top: tableWrapper.scrollHeight,
            behavior: 'instant'
          }});
        }});
      }}
    }}

    // ========================================
    // RENDER ALL
    // ========================================
    function renderAll() {{
      const filtered = filterRows();
      buildTrustSummary();
      buildSummary(filtered);
      renderTable();
      renderChart();
      renderPeriodStats(rows);
    }}

    // ========================================
    // UPDATE REFRESH TIME
    // ========================================
    function updateRefreshTime() {{
      const now = new Date();
      const timeString = now.toLocaleTimeString('en-US', {{
        hour12: false,
        hour: '2-digit',
        minute: '2-digit',
        second: '2-digit'
      }});
      const refreshElement = document.getElementById('refreshTime');
      if (refreshElement) {{
        refreshElement.textContent = timeString;
      }}
    }}

    // ========================================
    // UPDATE TODAY DATE
    // ========================================
    function updateTodayDate() {{
      const now = new Date();
      const almatyDate = new Date(now.toLocaleString('en-US', {{
        timeZone: 'Asia/Almaty'
      }}));

      const day = String(almatyDate.getDate()).padStart(2, '0');
      const month = String(almatyDate.getMonth() + 1).padStart(2, '0');
      const year = almatyDate.getFullYear();

      const todayElement = document.getElementById('todayDate');
      if (todayElement) {{
        todayElement.textContent = `Today - ${{day}}.${{month}}.${{year}}`;
      }}
    }}

    // ========================================
    // EVENT LISTENERS
    // ========================================
    forecastToggle.addEventListener('change', renderAll);
    statementToggle.addEventListener('change', renderAll);
    storeSelect.addEventListener('change', renderAll);
    rangeSelect.addEventListener('change', renderAll);

    window.addEventListener('resize', () => {{
      renderChart();
    }});

    // ========================================
    // INITIALIZATION
    // ========================================
    renderAll();
    updateRefreshTime();
    updateTodayDate();
    setupTableNavigation();
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
    parser.add_argument("--payout-lag-days", type=int, default=None)
    parser.add_argument("--rebuild", action="store_true", help="Rebuild calendar before export")
    parser.add_argument("--apply", action="store_true", help="Apply rebuild (requires ENABLE_CASHFLOW_WRITE=1)")
    parser.add_argument("--run-id", type=str, default=None, help="Run id for audit")
    args = parser.parse_args()

    cutoff = get_cutoff_date_almaty()
    run_id = args.run_id or datetime.now().strftime("%Y%m%d_%H%M%S")
    payout_model = load_payout_model()
    base_lag = args.payout_lag_days if args.payout_lag_days is not None else payout_model.base_lag_days
    conservative_lag = max(payout_model.conservative_lag_days, base_lag)

    applied_daily = False
    with sqlite3.connect(str(args.db)) as conn:
        conn.row_factory = sqlite3.Row
        last_statement_date = _load_last_statement_date(conn)
        sync_age_hours = _load_sync_age_hours(conn)
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
            skip_sales = _has_order_modelled_events(conn, history_start, history_end)
            system = _build_system_events(
                conn,
                history_start,
                history_end,
                fx_rates,
                run_id,
                skip_sales=skip_sales,
            )
            rows = compute_daily_rows(manual + system, history_start, history_end, run_id=run_id)
            for r in rows:
                r["is_forecast"] = False
            apply_daily = args.apply and history_start == resolved_start and history_end == resolved_end
            if args.apply and not apply_daily:
                print("WARN: Skipping daily table update (partial range rebuild).")
            if apply_daily:
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
                applied_daily = True
        else:
            for r in rows:
                r["is_forecast"] = False

        forecast_start = history_end + timedelta(days=1)
        forecast_end = forecast_start + timedelta(days=args.forecast_days - 1)
        commitments = _load_commitments(conn, forecast_start, forecast_end)
        forecast_rows = _build_forecast_rows(rows, commitments, args.forecast_days, base_lag, run_id)
        forecast_rows_conservative = _build_forecast_rows(rows, commitments, args.forecast_days, conservative_lag, run_id)

    all_rows = rows + forecast_rows
    all_rows_conservative = rows + forecast_rows_conservative

    if last_statement_date:
        try:
            last_statement = date.fromisoformat(last_statement_date)
        except Exception:
            last_statement = None
    else:
        last_statement = None

    for row in all_rows:
        row_date = date.fromisoformat(row["date"])
        if row.get("is_forecast"):
            trust = "FORECAST_MODEL"
        elif last_statement and row_date <= last_statement:
            trust = "STATEMENT_ACTUAL"
        else:
            trust = "ORDER_MODELLED"
        row["trust"] = trust

    min_base = _min_cash(all_rows) if all_rows else {"date": None, "cash_close": 0}
    min_cons = _min_cash(all_rows_conservative) if all_rows_conservative else min_base
    trust_path = Path(str(TRUST_REPORT_PATH).format(label=cutoff.isoformat()))
    _write_trust_report(trust_path, last_statement_date, sync_age_hours, all_rows)

    _write_csv(all_rows, CSV_PATH)
    _write_min_cash(all_rows, all_rows_conservative, MIN_CASH_PATH)
    _render_html(
        all_rows,
        HTML_PATH,
        {
            "last_statement_date": last_statement_date,
            "order_sync_age_hours": sync_age_hours,
            "min_cash_base": min_base,
            "min_cash_conservative": min_cons,
            "payout_lag_base": base_lag,
            "payout_lag_conservative": conservative_lag,
        },
    )

    print(f"Cashflow exports updated: {CSV_PATH} | {HTML_PATH}")
    if applied_daily:
        print("  APPLY: daily table updated.")
    else:
        print("  DRY RUN: daily table not updated (exports generated).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
