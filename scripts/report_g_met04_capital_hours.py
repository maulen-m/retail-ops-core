#!/usr/bin/env python3
"""Publish the G-MET-04 capital-hours by lifecycle stage report."""

from __future__ import annotations

import argparse
import csv
from datetime import date, datetime, timedelta
import json
from pathlib import Path
import re
import sqlite3
from typing import Any
from zoneinfo import ZoneInfo

PROJECT_ROOT = Path(__file__).resolve().parent.parent
ALMATY_TZ = ZoneInfo("Asia/Almaty")

DEFAULT_CONFIG = PROJECT_ROOT / "config" / "validation" / "capital_hours_stage_ledger.json"
DEFAULT_OUTPUT_ROOT = PROJECT_ROOT / "exports" / "validation" / "g_met04_capital_hours"

IDENT_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")

STAGE_COLUMNS = [
    "stage",
    "source_table",
    "open_column",
    "close_column",
    "measured",
    "row_count",
    "capital_hours",
    "average_capital_kzt",
    "latest_close_kzt",
    "details",
]

CONTEXT_COLUMNS = [
    "table",
    "exists",
    "row_count",
    "details",
]


def _now_almaty() -> str:
    return datetime.now(ALMATY_TZ).replace(microsecond=0).isoformat()


def _parse_as_of(value: str | None) -> datetime:
    text = str(value or "").strip()
    if not text:
        return datetime.now(ALMATY_TZ)
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    parsed = datetime.fromisoformat(text)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=ALMATY_TZ)
    return parsed.astimezone(ALMATY_TZ)


def _parse_date(value: Any) -> date | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return date.fromisoformat(text[:10])
    except ValueError:
        return None


def _resolve_project_path(raw: str | Path | None) -> Path:
    path = Path(str(raw or ""))
    if path.is_absolute():
        return path
    return PROJECT_ROOT / path


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _check(ok: bool, name: str, details: str, **extra: Any) -> dict[str, Any]:
    row: dict[str, Any] = {"check": name, "ok": bool(ok), "details": details}
    row.update(extra)
    return row


def _as_float(value: Any) -> float:
    if value is None or isinstance(value, bool):
        return 0.0
    try:
        return float(str(value).strip() or "0")
    except ValueError:
        return 0.0


def _fmt(value: float) -> float:
    return round(float(value), 2)


def _write_csv(path: Path, rows: list[dict[str, Any]], columns: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({column: row.get(column, "") for column in columns})


def _ident(value: str) -> str:
    text = str(value or "").strip()
    if not IDENT_RE.match(text):
        raise ValueError(f"invalid SQL identifier: {value!r}")
    return text


def _connect_readonly(db_path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(f"file:{db_path.resolve()}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def _table_exists(conn: sqlite3.Connection, table_name: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type IN ('table', 'view') AND name=?",
        (table_name,),
    ).fetchone()
    return row is not None


def _columns(conn: sqlite3.Connection, table_name: str) -> set[str]:
    if not _table_exists(conn, table_name):
        return set()
    table = _ident(table_name)
    return {str(row["name"]) for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}


def _count_rows(conn: sqlite3.Connection, table_name: str) -> int | None:
    if not _table_exists(conn, table_name):
        return None
    table = _ident(table_name)
    return int(conn.execute(f"SELECT COUNT(*) AS cnt FROM {table}").fetchone()["cnt"])


def _latest_cashflow_date(conn: sqlite3.Connection, as_of_date: date) -> str | None:
    if not _table_exists(conn, "fact_cashflow_daily"):
        return None
    row = conn.execute(
        """
        SELECT MAX(date) AS latest_date
        FROM fact_cashflow_daily
        WHERE date(date) <= date(?)
        """,
        (as_of_date.isoformat(),),
    ).fetchone()
    return str(row["latest_date"]) if row and row["latest_date"] else None


def _load_cashflow_rows(conn: sqlite3.Connection, start: date, end: date) -> list[sqlite3.Row]:
    return conn.execute(
        """
        SELECT *
        FROM fact_cashflow_daily
        WHERE date(date) >= date(?)
          AND date(date) <= date(?)
        ORDER BY date
        """,
        (start.isoformat(), end.isoformat()),
    ).fetchall()


def _stage_row(source: dict[str, Any], rows: list[sqlite3.Row], table_columns: set[str]) -> dict[str, Any]:
    stage = str(source.get("stage") or "")
    table = str(source.get("source_table") or "")
    open_column = str(source.get("open_column") or "")
    close_column = str(source.get("close_column") or "")
    missing_columns = [col for col in (open_column, close_column) if col not in table_columns]
    if table != "fact_cashflow_daily":
        return {
            "stage": stage,
            "source_table": table,
            "open_column": open_column,
            "close_column": close_column,
            "measured": False,
            "row_count": 0,
            "capital_hours": 0.0,
            "average_capital_kzt": 0.0,
            "latest_close_kzt": 0.0,
            "details": "unsupported source_table for read-only weekly stage-hours report",
        }
    if missing_columns:
        return {
            "stage": stage,
            "source_table": table,
            "open_column": open_column,
            "close_column": close_column,
            "measured": False,
            "row_count": 0,
            "capital_hours": 0.0,
            "average_capital_kzt": 0.0,
            "latest_close_kzt": 0.0,
            "details": "missing_columns=" + ",".join(missing_columns),
        }
    capital_hours = 0.0
    latest_close = 0.0
    for row in rows:
        open_value = _as_float(row[open_column])
        close_value = _as_float(row[close_column])
        capital_hours += ((open_value + close_value) / 2.0) * 24.0
        latest_close = close_value
    denominator_hours = len(rows) * 24.0
    average_capital = capital_hours / denominator_hours if denominator_hours else 0.0
    return {
        "stage": stage,
        "source_table": table,
        "open_column": open_column,
        "close_column": close_column,
        "measured": bool(rows),
        "row_count": len(rows),
        "capital_hours": _fmt(capital_hours),
        "average_capital_kzt": _fmt(average_capital),
        "latest_close_kzt": _fmt(latest_close),
        "details": "measured_from_daily_open_close",
    }


def _context_rows(conn: sqlite3.Connection, tables: list[str]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for table in tables:
        exists = _table_exists(conn, table)
        count = _count_rows(conn, table) if exists else None
        out.append(
            {
                "table": table,
                "exists": exists,
                "row_count": "" if count is None else count,
                "details": "present" if exists else "missing",
            }
        )
    return out


def _return_qc_count(conn: sqlite3.Connection, as_of_date: date) -> int:
    if not _table_exists(conn, "return_qc_event"):
        return 0
    columns = _columns(conn, "return_qc_event")
    if "qc_ts" not in columns:
        return int(conn.execute("SELECT COUNT(*) AS cnt FROM return_qc_event").fetchone()["cnt"])
    row = conn.execute(
        """
        SELECT COUNT(*) AS cnt
        FROM return_qc_event
        WHERE qc_ts IS NULL OR date(qc_ts) <= date(?)
        """,
        (as_of_date.isoformat(),),
    ).fetchone()
    return int(row["cnt"] or 0)


def _render_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# G-MET-04 Capital-Hours Stage Report",
        "",
        f"Gate: {report['gate']}",
        f"Generated: {report['generated_at']}",
        f"As of: {report['as_of']}",
        f"Period: `{report['period_start']}` to `{report['period_end']}`",
        "",
        "## Stages",
        "",
        "| stage | measured | capital_hours | avg_capital_kzt | latest_close_kzt | details |",
        "|---|---:|---:|---:|---:|---|",
    ]
    for stage, row in report["stage_hours_by_stage"].items():
        lines.append(
            f"| `{stage}` | {row['measured']} | {row['capital_hours']} | "
            f"{row['average_capital_kzt']} | {row['latest_close_kzt']} | {row['details']} |"
        )
    lines.extend(["", "## Blockers", ""])
    if report["blockers"]:
        lines.extend(f"- {blocker}" for blocker in report["blockers"])
    else:
        lines.append("- none")
    lines.extend(["", "## Measurement Blockers", ""])
    if report["measurement_blockers"]:
        lines.extend(f"- {blocker}" for blocker in report["measurement_blockers"])
    else:
        lines.append("- none")
    lines.extend(["", "## Checks", "", "| check | status | details |", "|---|---:|---|"])
    for row in report["checks"]:
        lines.append(f"| `{row['check']}` | {'PASS' if row['ok'] else 'FAIL'} | {row['details']} |")
    lines.append("")
    return "\n".join(lines)


def build_capital_hours_report(
    *,
    config_path: Path = DEFAULT_CONFIG,
    output_root: Path = DEFAULT_OUTPUT_ROOT,
    as_of: str | None = None,
) -> dict[str, Any]:
    checks: list[dict[str, Any]] = []
    blockers: list[str] = []
    measurement_blockers: list[str] = []

    config_path = config_path.expanduser().resolve()
    if config_path.exists():
        config = _load_json(config_path)
        checks.append(_check(True, "config_present", str(config_path)))
    else:
        config = {}
        checks.append(_check(False, "config_present", f"missing: {config_path}"))
    checks.append(
        _check(
            config.get("contract_id") == "CAPITAL_HOURS_STAGE_LEDGER_V1" and config.get("gate_id") == "G-MET-04",
            "config_identity",
            f"contract={config.get('contract_id')} gate={config.get('gate_id')}",
        )
    )

    as_of_dt = _parse_as_of(as_of)
    as_of_date = as_of_dt.date()
    db_path = _resolve_project_path(config.get("db_path", "db/app.db"))
    checks.append(_check(db_path.exists(), "db_present", str(db_path)))

    period_days = int(config.get("period_days") or 7)
    max_latest_lag = int(config.get("max_latest_daily_lag_days") or 2)
    latest_date_text: str | None = None
    latest_date: date | None = None
    period_start: date = as_of_date
    period_end: date = as_of_date
    daily_rows: list[sqlite3.Row] = []
    stage_rows: list[dict[str, Any]] = []
    context: list[dict[str, Any]] = []
    return_qc_event_count = 0
    dedicated_stage_ledger_present = False

    conn: sqlite3.Connection | None = None
    try:
        if db_path.exists():
            conn = _connect_readonly(db_path)
            checks.append(_check(True, "db_readonly_open", "mode=ro"))
            checks.append(_check(_table_exists(conn, "fact_cashflow_daily"), "table_fact_cashflow_daily_present", "fact_cashflow_daily"))
            latest_date_text = _latest_cashflow_date(conn, as_of_date)
            latest_date = _parse_date(latest_date_text)
            if latest_date is not None:
                period_end = latest_date
                period_start = max(latest_date - timedelta(days=period_days - 1), date.min)
                daily_rows = _load_cashflow_rows(conn, period_start, period_end)
                if daily_rows:
                    first_row_date = _parse_date(daily_rows[0]["date"])
                    last_row_date = _parse_date(daily_rows[-1]["date"])
                    if first_row_date is not None:
                        period_start = first_row_date
                    if last_row_date is not None:
                        period_end = last_row_date
            table_columns = _columns(conn, "fact_cashflow_daily")
            for source in config.get("stage_sources") or []:
                stage_rows.append(_stage_row(source, daily_rows, table_columns))
            context = _context_rows(conn, [str(table) for table in config.get("source_tables_for_context") or []])
            return_qc_event_count = _return_qc_count(conn, as_of_date)
            dedicated_stage_ledger_present = any(
                _table_exists(conn, str(table)) for table in config.get("stage_event_ledger_candidates") or []
            )
    except (sqlite3.Error, ValueError) as exc:
        checks.append(_check(False, "db_readonly_open", str(exc)))
    finally:
        if conn is not None:
            conn.close()

    latest_lag_days = None if latest_date is None else (as_of_date - latest_date).days
    checks.append(_check(latest_date is not None, "latest_cashflow_date_present", f"latest_date={latest_date_text}"))
    checks.append(
        _check(
            latest_lag_days is not None and latest_lag_days <= max_latest_lag,
            "latest_cashflow_lag_within_limit",
            f"lag_days={latest_lag_days} max_days={max_latest_lag}",
        )
    )
    checks.append(_check(bool(daily_rows), "period_rows_present", f"rows={len(daily_rows)}"))

    measured_stages = {str(row["stage"]) for row in stage_rows if row.get("measured")}
    required_stages = [str(stage) for stage in config.get("required_stages") or []]
    missing_required = sorted(set(required_stages) - measured_stages)
    for stage in missing_required:
        measurement_blockers.append(f"stage_source_missing:{stage}")
    if bool(config.get("return_qc_required_for_green", True)) and return_qc_event_count <= 0:
        measurement_blockers.append("return_qc_event_count=0 so returned/quarantine stage-hours remain unmeasured")
    if bool(config.get("dedicated_stage_event_ledger_required_for_green", True)) and not dedicated_stage_ledger_present:
        measurement_blockers.append("dedicated_capital_stage_event_ledger_missing")

    for row in checks:
        if not row["ok"]:
            blockers.append(f"{row['check']}: {row['details']}")

    if blockers:
        gate = "RED"
    elif measurement_blockers:
        gate = "ARMED"
    else:
        gate = "GREEN"

    output_root = output_root.expanduser().resolve()
    output_root.mkdir(parents=True, exist_ok=True)
    stage_csv = output_root / "capital_hours_by_stage.csv"
    context_csv = output_root / "capital_hours_source_context.csv"
    _write_csv(stage_csv, stage_rows, STAGE_COLUMNS)
    _write_csv(context_csv, context, CONTEXT_COLUMNS)

    stage_by_stage = {str(row["stage"]): row for row in stage_rows}
    report: dict[str, Any] = {
        "gate_id": "G-MET-04",
        "gate": gate,
        "ok": gate in {"GREEN", "ARMED"},
        "generated_at": _now_almaty(),
        "as_of": as_of_dt.replace(microsecond=0).isoformat(),
        "config_path": str(config_path),
        "db_path": str(db_path),
        "period_days": period_days,
        "period_start": period_start.isoformat() if daily_rows else "",
        "period_end": period_end.isoformat() if daily_rows else "",
        "latest_cashflow_date": latest_date_text or "",
        "latest_cashflow_lag_days": latest_lag_days,
        "daily_row_count": len(daily_rows),
        "required_stages": required_stages,
        "stage_count_measured": len(measured_stages),
        "stage_hours_by_stage": stage_by_stage,
        "return_qc_event_count": return_qc_event_count,
        "dedicated_stage_ledger_present": dedicated_stage_ledger_present,
        "source_context": context,
        "checks": checks,
        "blockers": blockers,
        "measurement_blockers": measurement_blockers,
        "artifacts": {
            "stage_hours_csv": str(stage_csv),
            "source_context_csv": str(context_csv),
        },
        "forbidden_writes_performed": False,
        "production_db_written": False,
        "external_writes_performed": False,
    }
    json_path = output_root / "capital_hours_stage_report.json"
    md_path = output_root / "capital_hours_stage_report.md"
    report["json_path"] = str(json_path)
    report["md_path"] = str(md_path)
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    md_path.write_text(_render_markdown(report), encoding="utf-8")
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--as-of", default="")
    parser.add_argument("--strict", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    report = build_capital_hours_report(
        config_path=args.config,
        output_root=args.output_dir,
        as_of=args.as_of or None,
    )
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(f"Gate: {report['gate']}")
        print(f"Report: {report['json_path']}")
        if report["blockers"]:
            print("Blockers:")
            for blocker in report["blockers"]:
                print(f"  - {blocker}")
        if report["measurement_blockers"]:
            print("Measurement blockers:")
            for blocker in report["measurement_blockers"]:
                print(f"  - {blocker}")
    return 1 if args.strict and report["gate"] == "RED" else 0


if __name__ == "__main__":
    raise SystemExit(main())
