#!/usr/bin/env python3
"""Publish the G-PO-02 size-priors rebuild readiness report."""

from __future__ import annotations

import argparse
import csv
from datetime import date, datetime
import json
from pathlib import Path
import re
import sqlite3
import subprocess
import sys
from typing import Any
from zoneinfo import ZoneInfo

PROJECT_ROOT = Path(__file__).resolve().parent.parent
ALMATY_TZ = ZoneInfo("Asia/Almaty")

DEFAULT_CONFIG = PROJECT_ROOT / "config" / "validation" / "po_size_priors_rebuild.json"
DEFAULT_OUTPUT_ROOT = PROJECT_ROOT / "exports" / "validation" / "g_po02_size_priors"


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


def _check(ok: bool, check_id: str, details: str, **extra: Any) -> dict[str, Any]:
    row: dict[str, Any] = {"check": check_id, "ok": bool(ok), "details": details}
    row.update(extra)
    return row


def _age_days(latest: str | None, as_of_date: date) -> int | None:
    parsed = _parse_date(latest)
    if parsed is None:
        return None
    return (as_of_date - parsed).days


def _db_summary(conn: sqlite3.Connection, *, as_of_date: date) -> tuple[dict[str, Any], list[str]]:
    fatal: list[str] = []
    required_tables = ["dim_size_probability", "fact_forecast_accuracy", "fact_demand_forecast"]
    for table in required_tables:
        if not _table_exists(conn, table):
            fatal.append(f"missing_table:{table}")
    if fatal:
        return {}, fatal
    prior = conn.execute(
        """
        SELECT
            COUNT(*) AS row_count,
            COUNT(DISTINCT level) AS level_count,
            MIN(updated_at) AS min_updated_at,
            MAX(updated_at) AS max_updated_at
        FROM dim_size_probability
        """
    ).fetchone()
    levels = [
        str(row["level"])
        for row in conn.execute(
            "SELECT DISTINCT level FROM dim_size_probability ORDER BY level"
        ).fetchall()
    ]
    forecast = conn.execute(
        """
        SELECT
            COUNT(*) AS row_count,
            MAX(forecast_date) AS latest_forecast_date
        FROM fact_demand_forecast
        """
    ).fetchone()
    accuracy = conn.execute(
        """
        SELECT
            COUNT(*) AS row_count,
            MAX(accuracy_date) AS latest_accuracy_date,
            ROUND(AVG(mape), 2) AS avg_mape,
            ROUND(AVG(bias), 2) AS avg_bias
        FROM fact_forecast_accuracy
        """
    ).fetchone()
    po_draft_count = 0
    po_execution_count = 0
    if _table_exists(conn, "fact_po_draft"):
        po_draft_count = int(conn.execute("SELECT COUNT(*) FROM fact_po_draft").fetchone()[0] or 0)
    if _table_exists(conn, "fact_po_execution"):
        po_execution_count = int(conn.execute("SELECT COUNT(*) FROM fact_po_execution").fetchone()[0] or 0)
    summary = {
        "prior_row_count": int(prior["row_count"] or 0),
        "prior_level_count": int(prior["level_count"] or 0),
        "prior_levels": levels,
        "prior_latest_updated_at": prior["max_updated_at"],
        "prior_age_days": _age_days(prior["max_updated_at"], as_of_date),
        "forecast_row_count": int(forecast["row_count"] or 0),
        "forecast_latest_date": forecast["latest_forecast_date"],
        "forecast_age_days": _age_days(forecast["latest_forecast_date"], as_of_date),
        "forecast_accuracy_row_count": int(accuracy["row_count"] or 0),
        "forecast_accuracy_latest_date": accuracy["latest_accuracy_date"],
        "forecast_accuracy_age_days": _age_days(accuracy["latest_accuracy_date"], as_of_date),
        "forecast_accuracy_avg_mape": float(accuracy["avg_mape"]) if accuracy["avg_mape"] is not None else None,
        "forecast_accuracy_avg_bias": float(accuracy["avg_bias"]) if accuracy["avg_bias"] is not None else None,
        "fact_po_draft_rows": po_draft_count,
        "fact_po_execution_rows": po_execution_count,
    }
    return summary, fatal


def _run_dashboard_invariants(db_path: Path, dashboard_path: Path, enabled: bool) -> dict[str, Any]:
    if not enabled:
        return {"ok": True, "returncode": None, "stdout": "skipped_by_config", "stderr": ""}
    proc = subprocess.run(
        [
            sys.executable,
            str(PROJECT_ROOT / "scripts" / "validate_po_dashboard_invariants.py"),
            "--db",
            str(db_path),
            "--input",
            str(dashboard_path),
        ],
        cwd=str(PROJECT_ROOT),
        check=False,
        capture_output=True,
        text=True,
    )
    return {
        "ok": proc.returncode == 0,
        "returncode": proc.returncode,
        "stdout": proc.stdout.strip(),
        "stderr": proc.stderr.strip(),
    }


def _render_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# G-PO-02 Size Priors Rebuild Report",
        "",
        f"Gate: {report['gate']}",
        f"Generated: {report['generated_at']}",
        f"Passed checks: {report['passed_checks']}/{report['total_checks']}",
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


def build_size_priors_report(
    *,
    config_path: Path = DEFAULT_CONFIG,
    output_root: Path = DEFAULT_OUTPUT_ROOT,
    as_of: str | None = None,
) -> dict[str, Any]:
    config = _load_json(config_path)
    db_path = _resolve_path(config["db_path"])
    dashboard_path = _resolve_path(config.get("dashboard_path", "docs/plan/green_path_2026-06/dashboard/progress-data.js"))
    scoreboard_path = _resolve_path(config["scoreboard_path"])
    po_dashboard_json = _resolve_path(config.get("po_dashboard_json", "exports/po_dashboard_data.json"))
    as_of_dt = _parse_as_of(as_of)
    as_of_date = as_of_dt.date()
    generated_at = _now_almaty()
    run_id = generated_at.replace("-", "").replace(":", "").replace("+", "_").replace("T", "_")
    out_dir = output_root / run_id
    out_dir.mkdir(parents=True, exist_ok=True)

    gate_states = _load_dashboard_gate_states(dashboard_path)
    gate_states.update(_load_scoreboard(scoreboard_path))
    dependency_gates = [str(value) for value in config.get("dependency_gates", [])]
    dependency_statuses = {gate_id: gate_states.get(gate_id, "MISSING") for gate_id in dependency_gates}
    max_prior_age = int(config.get("max_prior_age_days", 30))
    max_forecast_age = int(config.get("max_forecast_age_days", 30))
    max_mape = float(config.get("max_mape_pct", 30.0))
    required_levels = {str(value) for value in config.get("required_prior_levels", [])}

    with _connect_ro(db_path) as conn:
        db_summary, fatal_errors = _db_summary(conn, as_of_date=as_of_date)

    dashboard_result = _run_dashboard_invariants(
        db_path,
        po_dashboard_json,
        bool(config.get("run_dashboard_invariants", True)),
    )

    checks: list[dict[str, Any]] = []
    blockers: list[str] = []
    missing_deps = [f"{gate_id}={status}" for gate_id, status in dependency_statuses.items() if status != "GREEN"]
    checks.append(
        _check(
            not missing_deps,
            "dependency_stack_green",
            "missing=" + (",".join(missing_deps) if missing_deps else "none"),
            dependency_statuses=dependency_statuses,
        )
    )
    if missing_deps:
        blockers.extend(f"dependency_gate_not_green:{item}" for item in missing_deps)
    if fatal_errors:
        checks.extend(_check(False, name, name) for name in fatal_errors)
    else:
        levels = set(db_summary["prior_levels"])
        missing_levels = sorted(required_levels - levels)
        checks.append(
            _check(
                db_summary["prior_row_count"] > 0 and not missing_levels,
                "prior_levels_present",
                "missing_levels=" + (",".join(missing_levels) if missing_levels else "none"),
            )
        )
        prior_age = db_summary["prior_age_days"]
        checks.append(
            _check(
                prior_age is not None and prior_age <= max_prior_age,
                "prior_fresh",
                f"prior_age_days={prior_age} max={max_prior_age}",
            )
        )
        if prior_age is None or prior_age > max_prior_age:
            blockers.append(f"prior_age_days={prior_age}>{max_prior_age}")
        acc_age = db_summary["forecast_accuracy_age_days"]
        checks.append(
            _check(
                db_summary["forecast_accuracy_row_count"] > 0 and acc_age is not None and acc_age <= max_forecast_age,
                "forecast_accuracy_fresh",
                f"forecast_accuracy_age_days={acc_age} max={max_forecast_age}",
            )
        )
        if acc_age is None or acc_age > max_forecast_age:
            blockers.append(f"forecast_accuracy_age_days={acc_age}>{max_forecast_age}")
        avg_mape = db_summary["forecast_accuracy_avg_mape"]
        checks.append(
            _check(
                avg_mape is not None and avg_mape <= max_mape,
                "forecast_mape_threshold",
                f"avg_mape={avg_mape} max={max_mape}",
            )
        )
        if avg_mape is None or avg_mape > max_mape:
            blockers.append(f"forecast_mape={avg_mape}>{max_mape}")
        forecast_age = db_summary["forecast_age_days"]
        checks.append(
            _check(
                db_summary["forecast_row_count"] > 0 and forecast_age is not None and forecast_age <= max_forecast_age,
                "demand_forecast_fresh",
                f"forecast_age_days={forecast_age} max={max_forecast_age}",
            )
        )
        if forecast_age is None or forecast_age > max_forecast_age:
            blockers.append(f"forecast_age_days={forecast_age}>{max_forecast_age}")
    checks.append(
        _check(
            bool(dashboard_result["ok"]),
            "po_dashboard_invariants",
            f"returncode={dashboard_result['returncode']} stdout={dashboard_result['stdout'][:120]}",
        )
    )
    if not dashboard_result["ok"]:
        blockers.append("po_dashboard_invariants_failed")

    total_checks = 7
    passed_checks = sum(1 for row in checks[:total_checks] if row["ok"])
    if fatal_errors:
        gate = "RED"
    elif passed_checks == total_checks and not blockers:
        gate = "GREEN"
    else:
        gate = "ARMED"

    report: dict[str, Any] = {
        "contract_id": config.get("contract_id"),
        "gate_id": config.get("gate_id", "G-PO-02"),
        "gate": gate,
        "generated_at": generated_at,
        "as_of": as_of_dt.isoformat(),
        "db_path": str(db_path),
        "db_open_mode": "ro",
        "dashboard_path": str(dashboard_path),
        "scoreboard_path": str(scoreboard_path),
        "po_dashboard_json": str(po_dashboard_json),
        "dependency_statuses": dependency_statuses,
        "checks": checks[:total_checks],
        "passed_checks": passed_checks,
        "total_checks": total_checks,
        "blockers": blockers,
        "fatal_errors": fatal_errors,
        "dashboard_invariants": dashboard_result,
        **db_summary,
    }
    json_path = out_dir / "po_size_priors_report.json"
    md_path = out_dir / "po_size_priors_report.md"
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
    report = build_size_priors_report(
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
