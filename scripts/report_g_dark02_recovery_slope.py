#!/usr/bin/env python3
"""Publish the G-DARK-02 dark-relist recovery slope report."""

from __future__ import annotations

import argparse
import csv
from datetime import date, datetime
import json
from pathlib import Path
import re
import sqlite3
from typing import Any
from zoneinfo import ZoneInfo

PROJECT_ROOT = Path(__file__).resolve().parent.parent
ALMATY_TZ = ZoneInfo("Asia/Almaty")

DEFAULT_CONFIG = PROJECT_ROOT / "config" / "validation" / "dark_relist_recovery_slope.json"
DEFAULT_OUTPUT_ROOT = PROJECT_ROOT / "exports" / "validation" / "g_dark02_recovery_slope"

CURVE_COLUMNS = ["period", "family_id", "sku_key", "order_date", "units", "order_rows"]


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


def _connect_ro(path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(f"file:{path.resolve()}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def _table_exists(conn: sqlite3.Connection, table: str) -> bool:
    return conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type IN ('table', 'view') AND name=?",
        (table,),
    ).fetchone() is not None


def _load_scoreboard(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    states: dict[str, str] = {}
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            gate_id = str(row.get("gate_id") or row.get("gate") or "").strip()
            state = str(row.get("status") or row.get("state") or "").strip().upper()
            if gate_id and state:
                states[gate_id] = state
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
        state = str(row.get("status") or "").strip().upper()
        if gate_id and state:
            states[gate_id] = state
    return states


def _check(ok: bool, check_id: str, details: str, **extra: Any) -> dict[str, Any]:
    row: dict[str, Any] = {"check": check_id, "ok": bool(ok), "details": details}
    row.update(extra)
    return row


def _write_csv(path: Path, rows: list[dict[str, Any]], columns: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()
        writer.writerows([{column: row.get(column, "") for column in columns} for row in rows])


def _sales_rows(
    conn: sqlite3.Connection,
    *,
    families: list[dict[str, Any]],
    start_date: date,
    end_date: date,
    period: str,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for family in families:
        sku_key = str(family["sku_key"])
        family_id = str(family.get("family_id") or sku_key)
        for row in conn.execute(
            """
            SELECT order_date, SUM(quantity) AS units, COUNT(*) AS order_rows
            FROM sales_fact_v2
            WHERE sku_key = ?
              AND date(order_date) >= date(?)
              AND date(order_date) <= date(?)
              AND upper(coalesce(status, '')) NOT LIKE '%CANCEL%'
            GROUP BY order_date
            ORDER BY order_date
            """,
            (sku_key, start_date.isoformat(), end_date.isoformat()),
        ).fetchall():
            rows.append(
                {
                    "period": period,
                    "family_id": family_id,
                    "sku_key": sku_key,
                    "order_date": row["order_date"],
                    "units": int(row["units"] or 0),
                    "order_rows": int(row["order_rows"] or 0),
                }
            )
    return rows


def _render_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# G-DARK-02 Recovery Slope Report",
        "",
        f"Gate: {report['gate']}",
        f"Generated: {report['generated_at']}",
        f"Passed checks: {report['passed_checks']}/{report['total_checks']}",
        "",
        "## Summary",
        "",
        f"- baseline_units: {report['baseline_units']}",
        f"- post_relist_units: {report['post_relist_units']}",
        f"- mature_post_relist_days: {report['mature_post_relist_days']}",
        f"- relist_start: {report['relist_start'] or 'missing'}",
        "",
        "## Checks",
        "",
        "| check | status | details |",
        "|---|---:|---|",
    ]
    for row in report["checks"]:
        lines.append(f"| `{row['check']}` | {'PASS' if row['ok'] else 'FAIL'} | {row['details']} |")
    lines.extend(["", "## Blockers", ""])
    if report["blockers"]:
        lines.extend(f"- {blocker}" for blocker in report["blockers"])
    else:
        lines.append("- none")
    return "\n".join(lines) + "\n"


def build_dark_recovery_slope_report(
    *,
    config_path: Path = DEFAULT_CONFIG,
    output_root: Path = DEFAULT_OUTPUT_ROOT,
    as_of: str | None = None,
) -> dict[str, Any]:
    config = _load_json(config_path)
    db_path = _resolve_path(config["db_path"])
    dashboard_path = _resolve_path(config.get("dashboard_path", "docs/plan/green_path_2026-06/dashboard/progress-data.js"))
    scoreboard_path = _resolve_path(config["scoreboard_path"])
    generated_at = _now_almaty()
    as_of_dt = _parse_as_of(as_of)
    as_of_date = as_of_dt.date()
    run_id = generated_at.replace("-", "").replace(":", "").replace("+", "_").replace("T", "_")
    out_dir = output_root / run_id
    out_dir.mkdir(parents=True, exist_ok=True)

    gate_states = _load_dashboard_gate_states(dashboard_path)
    gate_states.update(_load_scoreboard(scoreboard_path))
    dependency_gates = [str(value) for value in config.get("dependency_gates") or []]
    dependency_statuses = {gate_id: gate_states.get(gate_id, "MISSING") for gate_id in dependency_gates}
    families = list(config.get("families") or [])
    baseline_start = _parse_date(config.get("baseline_start")) or as_of_date
    relist_start = _parse_date(config.get("relist_start"))
    maturity_days = int(config.get("maturity_days") or 30)
    blockers: list[str] = []
    fatal_errors: list[str] = []
    checks: list[dict[str, Any]] = []

    dependency_missing = {gate: state for gate, state in dependency_statuses.items() if state != "GREEN"}
    checks.append(
        _check(
            not dependency_missing,
            "dependency_stack_green",
            "missing=" + ",".join(f"{gate}={state}" for gate, state in dependency_missing.items())
            if dependency_missing
            else "all dependencies GREEN",
            dependency_statuses=dependency_statuses,
        )
    )
    for gate, state in dependency_missing.items():
        blockers.append(f"dependency_gate_not_green:{gate}={state}")

    if not db_path.exists():
        fatal_errors.append("missing_db")
    baseline_rows: list[dict[str, Any]] = []
    post_rows: list[dict[str, Any]] = []
    if db_path.exists():
        with _connect_ro(db_path) as conn:
            if not _table_exists(conn, "sales_fact_v2"):
                fatal_errors.append("missing_table:sales_fact_v2")
            else:
                baseline_rows = _sales_rows(
                    conn,
                    families=families,
                    start_date=baseline_start,
                    end_date=as_of_date,
                    period="baseline",
                )
                if relist_start is not None:
                    post_rows = _sales_rows(
                        conn,
                        families=families,
                        start_date=relist_start,
                        end_date=as_of_date,
                        period="post_relist",
                    )

    baseline_units = sum(int(row["units"]) for row in baseline_rows)
    post_units = sum(int(row["units"]) for row in post_rows)
    mature_days = (as_of_date - relist_start).days if relist_start else 0
    checks.append(
        _check(
            not fatal_errors,
            "baseline_truth_readable",
            "fatal_errors=" + (",".join(fatal_errors) if fatal_errors else "none"),
        )
    )
    checks.append(_check(relist_start is not None, "relist_start_present", relist_start.isoformat() if relist_start else "missing"))
    if relist_start is None:
        blockers.append("relist_start_missing")
    checks.append(
        _check(
            mature_days >= maturity_days,
            "post_relist_window_mature",
            f"mature_days={mature_days} required={maturity_days}",
        )
    )
    if mature_days < maturity_days:
        blockers.append(f"mature_post_relist_days={mature_days}<{maturity_days}")
    checks.append(
        _check(
            relist_start is not None and mature_days >= maturity_days,
            "measured_curve_published",
            f"post_relist_units={post_units}",
        )
    )

    if fatal_errors:
        gate = "RED"
    elif all(row["ok"] for row in checks):
        gate = "GREEN"
    else:
        gate = "ARMED"

    curve_path = out_dir / "dark_relist_recovery_curve.csv"
    _write_csv(curve_path, baseline_rows + post_rows, CURVE_COLUMNS)
    json_path = out_dir / "dark_relist_recovery_slope_report.json"
    md_path = out_dir / "dark_relist_recovery_slope_report.md"
    report: dict[str, Any] = {
        "contract_id": config.get("contract_id", "DARK_RELIST_RECOVERY_SLOPE_V1"),
        "gate_id": config.get("gate_id", "G-DARK-02"),
        "gate": gate,
        "generated_at": generated_at,
        "as_of": as_of_dt.isoformat(),
        "db_open_mode": "ro",
        "db_path": str(db_path),
        "dashboard_path": str(dashboard_path),
        "scoreboard_path": str(scoreboard_path),
        "dependency_statuses": dependency_statuses,
        "family_count": len(families),
        "baseline_start": baseline_start.isoformat(),
        "baseline_units": baseline_units,
        "post_relist_units": post_units,
        "relist_start": relist_start.isoformat() if relist_start else "",
        "mature_post_relist_days": mature_days,
        "maturity_days_required": maturity_days,
        "estimated_serviceable_flow_low_kzt_per_month": config.get("estimated_serviceable_flow_low_kzt_per_month"),
        "estimated_serviceable_flow_high_kzt_per_month": config.get("estimated_serviceable_flow_high_kzt_per_month"),
        "source_reference": config.get("source_reference"),
        "fatal_errors": fatal_errors,
        "blockers": blockers,
        "checks": checks,
        "passed_checks": sum(1 for row in checks if row["ok"]),
        "total_checks": len(checks),
        "curve_csv": str(curve_path),
        "json_path": str(json_path),
        "md_path": str(md_path),
        "external_writes_performed": False,
    }
    json_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    md_path.write_text(_render_markdown(report), encoding="utf-8")
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--as-of")
    parser.add_argument("--strict", action="store_true", help="Return non-zero only when gate is RED.")
    args = parser.parse_args(argv)
    report = build_dark_recovery_slope_report(
        config_path=args.config,
        output_root=args.output_root,
        as_of=args.as_of,
    )
    print(json.dumps(report, indent=2, sort_keys=True))
    if args.strict and report["gate"] == "RED":
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
