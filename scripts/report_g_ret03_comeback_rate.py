#!/usr/bin/env python3
"""Publish the G-RET-03 measured return comeback-rate report."""

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

DEFAULT_CONFIG = PROJECT_ROOT / "config" / "validation" / "return_comeback_rate.json"
DEFAULT_OUTPUT_ROOT = PROJECT_ROOT / "exports" / "validation" / "g_ret03_comeback_rate"


def _now_almaty() -> str:
    return datetime.now(ALMATY_TZ).replace(microsecond=0).isoformat()


def _parse_as_of(raw: str | None) -> datetime:
    text = str(raw or "").strip()
    if not text:
        return datetime.now(ALMATY_TZ)
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    parsed = datetime.fromisoformat(text)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=ALMATY_TZ)
    return parsed.astimezone(ALMATY_TZ)


def _parse_date(raw: Any) -> date | None:
    text = str(raw or "").strip()
    if not text:
        return None
    try:
        return date.fromisoformat(text[:10])
    except ValueError:
        return None


def _resolve_path(raw: str | Path) -> Path:
    path = Path(raw)
    if path.is_absolute():
        return path
    return PROJECT_ROOT / path


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _connect_ro(db_path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(f"file:{db_path.resolve()}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def _table_exists(conn: sqlite3.Connection, table: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type IN ('table', 'view') AND name=?",
        (table,),
    ).fetchone()
    return row is not None


def _load_scoreboard(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    states: dict[str, str] = {}
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            gate_id = str(row.get("gate_id") or row.get("gate") or "").strip()
            status = str(row.get("status") or row.get("state") or "").strip().upper()
            if gate_id and status:
                states[gate_id] = status
    return states


def _load_dashboard_gate_states(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    text = path.read_text(encoding="utf-8")
    match = re.search(r"window\.GP\s*=\s*(\{.*\});\s*$", text, re.S)
    if not match:
        return {}
    payload = json.loads(match.group(1))
    states: dict[str, str] = {}
    for row in payload.get("gates", []):
        gate_id = str(row.get("id") or "").strip()
        status = str(row.get("status") or "").strip().upper()
        if gate_id and status:
            states[gate_id] = status
    return states


def _write_csv(path: Path, rows: list[dict[str, Any]], columns: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({column: row.get(column, "") for column in columns})


def _returned_counts(conn: sqlite3.Connection, *, as_of: date, maturity_days: int) -> dict[str, Any]:
    cutoff = as_of - timedelta(days=maturity_days)
    if not _table_exists(conn, "fact_orders_kaspi"):
        return {
            "missing": True,
            "total_returned_to_warehouse_orders": 0,
            "eligible_returned_orders": 0,
            "cutoff_date": cutoff.isoformat(),
            "by_date": [],
        }
    rows = conn.execute(
        """
        SELECT
            date(COALESCE(status_updated_at, updated_at, created_at)) AS return_date,
            COUNT(DISTINCT CAST(order_id AS TEXT)) AS orders
        FROM fact_orders_kaspi
        WHERE UPPER(COALESCE(internal_status, '')) = 'RETURNED'
          AND COALESCE(returned_to_warehouse, 0) = 1
          AND date(COALESCE(status_updated_at, updated_at, created_at)) <= date(?)
        GROUP BY date(COALESCE(status_updated_at, updated_at, created_at))
        ORDER BY return_date
        """,
        (as_of.isoformat(),),
    ).fetchall()
    by_date = [
        {
            "return_date": str(row["return_date"]),
            "orders": int(row["orders"] or 0),
            "eligible": str(row["return_date"]) <= cutoff.isoformat(),
        }
        for row in rows
    ]
    total = sum(int(row["orders"]) for row in by_date)
    eligible = sum(int(row["orders"]) for row in by_date if row["eligible"])
    return {
        "missing": False,
        "total_returned_to_warehouse_orders": total,
        "eligible_returned_orders": eligible,
        "cutoff_date": cutoff.isoformat(),
        "by_date": by_date,
    }


def _qc_summary(
    conn: sqlite3.Connection,
    *,
    as_of: date,
    maturity_days: int,
    pass_statuses: list[str],
) -> dict[str, Any]:
    cutoff = as_of - timedelta(days=maturity_days)
    if not _table_exists(conn, "return_qc_event"):
        return {
            "missing": True,
            "return_qc_event_count": 0,
            "first_qc_date": None,
            "latest_qc_date": None,
            "qc_telemetry_days": 0,
            "qc_passed_reentered_orders": 0,
            "qc_passed_reentered_units": 0,
            "qc_reviewed_eligible_orders": 0,
        }
    row = conn.execute(
        """
        SELECT
            COUNT(*) AS cnt,
            MIN(date(qc_ts)) AS first_qc_date,
            MAX(date(qc_ts)) AS latest_qc_date
        FROM return_qc_event
        WHERE qc_ts IS NULL OR date(qc_ts) <= date(?)
        """,
        (as_of.isoformat(),),
    ).fetchone()
    first_qc_date = _parse_date(row["first_qc_date"] if row else None)
    latest_qc_date = _parse_date(row["latest_qc_date"] if row else None)
    telemetry_days = (
        (latest_qc_date - first_qc_date).days + 1
        if first_qc_date is not None and latest_qc_date is not None
        else 0
    )
    placeholders = ",".join("?" for _ in pass_statuses) or "''"
    pass_filter = f"AND qc_status IN ({placeholders})" if pass_statuses else ""
    passed = conn.execute(
        f"""
        WITH eligible AS (
            SELECT DISTINCT CAST(order_id AS TEXT) AS order_id
            FROM fact_orders_kaspi
            WHERE UPPER(COALESCE(internal_status, '')) = 'RETURNED'
              AND COALESCE(returned_to_warehouse, 0) = 1
              AND date(COALESCE(status_updated_at, updated_at, created_at)) <= date(?)
        ),
        qc AS (
            SELECT
                CAST(q.order_id AS TEXT) AS order_id,
                COALESCE(q.accepted_active_qty, 0) AS accepted_active_qty,
                UPPER(COALESCE(q.qc_status, '')) AS qc_status
            FROM return_qc_event q
            JOIN eligible e ON e.order_id = CAST(q.order_id AS TEXT)
            WHERE q.qc_ts IS NULL OR date(q.qc_ts) <= date(?)
        )
        SELECT
            COUNT(DISTINCT order_id) AS reviewed_orders,
            COUNT(DISTINCT CASE WHEN accepted_active_qty > 0 {pass_filter} THEN order_id END) AS passed_orders,
            COALESCE(SUM(CASE WHEN accepted_active_qty > 0 {pass_filter} THEN accepted_active_qty ELSE 0 END), 0) AS passed_units
        FROM qc
        """,
        [cutoff.isoformat(), as_of.isoformat(), *pass_statuses, *pass_statuses],
    ).fetchone()
    return {
        "missing": False,
        "return_qc_event_count": int(row["cnt"] or 0),
        "first_qc_date": first_qc_date.isoformat() if first_qc_date else None,
        "latest_qc_date": latest_qc_date.isoformat() if latest_qc_date else None,
        "qc_telemetry_days": telemetry_days,
        "qc_passed_reentered_orders": int(passed["passed_orders"] or 0),
        "qc_passed_reentered_units": int(passed["passed_units"] or 0),
        "qc_reviewed_eligible_orders": int(passed["reviewed_orders"] or 0),
    }


def _stock_reentry_count(conn: sqlite3.Connection) -> int | None:
    if not _table_exists(conn, "stock_ledger"):
        return None
    row = conn.execute(
        """
        SELECT COUNT(*) AS cnt
        FROM stock_ledger
        WHERE COALESCE(qty_change, 0) > 0
          AND (
                lower(coalesce(reference_id, '') || ' ' || coalesce(reference_type, '') || ' ' || coalesce(notes, '') || ' ' || coalesce(input_source, '') || ' ' || coalesce(idempotency_key, '')) LIKE '%retqc%'
                OR lower(coalesce(reference_id, '') || ' ' || coalesce(reference_type, '') || ' ' || coalesce(notes, '') || ' ' || coalesce(input_source, '') || ' ' || coalesce(idempotency_key, '')) LIKE '%return_qc%'
              )
        """
    ).fetchone()
    return int(row["cnt"] or 0)


def _render_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# G-RET-03 Return Comeback Rate Report",
        "",
        f"Gate: {report['gate']}",
        f"Generated: {report['generated_at']}",
        f"As of: {report['as_of']}",
        f"Dependency: {report['dependency_gate']}={report['dependency_gate_status']}",
        "",
        "## Measurement",
        "",
        f"- total_returned_to_warehouse_orders: {report['total_returned_to_warehouse_orders']}",
        f"- eligible_returned_orders: {report['eligible_returned_orders']}",
        f"- return_qc_event_count: {report['return_qc_event_count']}",
        f"- qc_telemetry_days: {report['qc_telemetry_days']}",
        f"- qc_passed_reentered_orders: {report['qc_passed_reentered_orders']}",
        f"- comeback_rate: {report['comeback_rate']}",
        "",
        "## Blockers",
        "",
    ]
    if report["blockers"]:
        lines.extend(f"- {blocker}" for blocker in report["blockers"])
    else:
        lines.append("- none")
    return "\n".join(lines) + "\n"


def build_comeback_rate_report(
    *,
    config_path: Path = DEFAULT_CONFIG,
    output_root: Path = DEFAULT_OUTPUT_ROOT,
    as_of: str | None = None,
) -> dict[str, Any]:
    config = _load_json(config_path)
    db_path = _resolve_path(config["db_path"])
    dashboard_path = _resolve_path(config.get("dashboard_path", "docs/plan/green_path_2026-06/dashboard/progress-data.js"))
    scoreboard_path = _resolve_path(config["scoreboard_path"])
    maturity_days = int(config.get("maturity_days", 30))
    required_qc_days = int(config.get("required_qc_telemetry_days", 30))
    dependency_gate = str(config.get("dependency_gate", "G-RET-02"))
    pass_statuses = [str(value).upper() for value in config.get("pass_statuses", [])]
    as_of_dt = _parse_as_of(as_of)
    as_of_date = as_of_dt.date()
    generated_at = _now_almaty()
    run_id = generated_at.replace("-", "").replace(":", "").replace("+", "_").replace("T", "_")
    out_dir = output_root / run_id
    out_dir.mkdir(parents=True, exist_ok=True)

    gate_states = _load_dashboard_gate_states(dashboard_path)
    gate_states.update(_load_scoreboard(scoreboard_path))
    dependency_status = gate_states.get(dependency_gate, "MISSING")

    blockers: list[str] = []
    fatal_errors: list[str] = []
    with _connect_ro(db_path) as conn:
        returned = _returned_counts(conn, as_of=as_of_date, maturity_days=maturity_days)
        qc = _qc_summary(
            conn,
            as_of=as_of_date,
            maturity_days=maturity_days,
            pass_statuses=pass_statuses,
        )
        stock_reentry_rows = _stock_reentry_count(conn)

    if returned["missing"]:
        fatal_errors.append("missing_table:fact_orders_kaspi")
    if qc["missing"]:
        fatal_errors.append("missing_table:return_qc_event")
    if dependency_status != "GREEN":
        blockers.append(f"dependency_gate_not_green:{dependency_gate}={dependency_status}")
    if qc["return_qc_event_count"] <= 0:
        blockers.append("return_qc_event_count=0")
    if qc["qc_telemetry_days"] < required_qc_days:
        blockers.append(f"qc_telemetry_days={qc['qc_telemetry_days']}<{required_qc_days}")
    if returned["eligible_returned_orders"] <= 0:
        blockers.append("eligible_returned_orders=0")

    denominator = int(returned["eligible_returned_orders"])
    numerator = int(qc["qc_passed_reentered_orders"])
    if numerator > denominator and denominator >= 0:
        fatal_errors.append("qc_passed_reentered_orders_exceeds_eligible_returned_orders")
    comeback_rate = round(numerator / denominator, 4) if denominator > 0 and qc["return_qc_event_count"] > 0 else None

    if fatal_errors:
        gate = "RED"
    elif blockers:
        gate = "ARMED"
    else:
        gate = "GREEN"

    by_date_path = out_dir / "returned_to_warehouse_by_date.csv"
    _write_csv(by_date_path, returned["by_date"], ["return_date", "orders", "eligible"])

    report: dict[str, Any] = {
        "contract_id": config.get("contract_id"),
        "gate_id": config.get("gate_id", "G-RET-03"),
        "gate": gate,
        "generated_at": generated_at,
        "as_of": as_of_dt.isoformat(),
        "db_path": str(db_path),
        "db_open_mode": "ro",
        "dashboard_path": str(dashboard_path),
        "scoreboard_path": str(scoreboard_path),
        "dependency_gate": dependency_gate,
        "dependency_gate_status": dependency_status,
        "maturity_days": maturity_days,
        "required_qc_telemetry_days": required_qc_days,
        "maturity_cutoff_date": returned["cutoff_date"],
        "total_returned_to_warehouse_orders": int(returned["total_returned_to_warehouse_orders"]),
        "eligible_returned_orders": denominator,
        "return_qc_event_count": int(qc["return_qc_event_count"]),
        "first_qc_date": qc["first_qc_date"],
        "latest_qc_date": qc["latest_qc_date"],
        "qc_telemetry_days": int(qc["qc_telemetry_days"]),
        "qc_reviewed_eligible_orders": int(qc["qc_reviewed_eligible_orders"]),
        "qc_passed_reentered_orders": numerator,
        "qc_passed_reentered_units": int(qc["qc_passed_reentered_units"]),
        "stock_reentry_ledger_rows": stock_reentry_rows,
        "comeback_rate": comeback_rate,
        "blockers": blockers,
        "fatal_errors": fatal_errors,
        "returned_to_warehouse_by_date_csv": str(by_date_path),
    }
    json_path = out_dir / "comeback_rate_report.json"
    md_path = out_dir / "comeback_rate_report.md"
    report["json_path"] = str(json_path)
    report["md_path"] = str(md_path)
    json_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    md_path.write_text(_render_markdown(report), encoding="utf-8")
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--as-of", default="")
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args()
    report = build_comeback_rate_report(
        config_path=args.config,
        output_root=args.output_root,
        as_of=args.as_of or None,
    )
    print(json.dumps(report, indent=2, sort_keys=True))
    if args.strict and report["gate"] == "RED":
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
