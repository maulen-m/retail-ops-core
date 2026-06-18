#!/usr/bin/env python3
"""Publish the G-PO-03 forecast accuracy and signed-bias loop report."""

from __future__ import annotations

import argparse
import csv
from datetime import date, datetime
import glob
import json
from pathlib import Path
import re
import sqlite3
import sys
from typing import Any
from zoneinfo import ZoneInfo

PROJECT_ROOT = Path(__file__).resolve().parent.parent
ALMATY_TZ = ZoneInfo("Asia/Almaty")

DEFAULT_CONFIG = PROJECT_ROOT / "config" / "validation" / "forecast_accuracy_bias_loop.json"
DEFAULT_OUTPUT_ROOT = PROJECT_ROOT / "exports" / "validation" / "g_po03_forecast_accuracy_loop"


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


def _age_days(latest: str | None, as_of_date: date) -> int | None:
    parsed = _parse_date(latest)
    if parsed is None:
        return None
    return (as_of_date - parsed).days


def _resolve_path(raw: str | Path) -> Path:
    path = Path(raw)
    if path.is_absolute():
        return path
    return PROJECT_ROOT / path


def _resolve_glob(raw: str) -> str:
    path = Path(raw)
    if path.is_absolute():
        return str(path)
    return str(PROJECT_ROOT / path)


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


def _parse_float(raw: Any) -> float | None:
    text = str(raw or "").strip()
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def _report_date_from_path(path: Path) -> str | None:
    match = re.search(r"forecast_accuracy_(\d{4}-\d{2}-\d{2})\.csv$", path.name)
    if match:
        return match.group(1)
    return None


def _latest_accuracy_report(pattern: str) -> Path | None:
    candidates = [Path(value) for value in glob.glob(_resolve_glob(pattern))]
    if not candidates:
        return None

    def sort_key(path: Path) -> tuple[date, float, str]:
        parsed = _parse_date(_report_date_from_path(path))
        return (parsed or date.min, path.stat().st_mtime if path.exists() else 0.0, str(path))

    return max(candidates, key=sort_key)


def _avg(values: list[float]) -> float | None:
    if not values:
        return None
    return round(sum(values) / len(values), 2)


def _parse_accuracy_csv(path: Path | None) -> tuple[dict[str, Any], list[str]]:
    if path is None:
        return {}, ["missing_accuracy_report"]
    if not path.exists():
        return {}, [f"missing_accuracy_report:{path}"]

    fatal: list[str] = []
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        fieldnames = {name.strip().lower() for name in (reader.fieldnames or [])}
        has_mape = "mape" in fieldnames
        has_bias = "bias" in fieldnames
        wmape_column = "wmape" if "wmape" in fieldnames else "wape" if "wape" in fieldnames else None
        rows = list(reader)

    mape_values: list[float] = []
    wmape_values: list[float] = []
    bias_values: list[float] = []
    grade_counts: dict[str, int] = {}
    for row in rows:
        mape = _parse_float(row.get("mape"))
        if mape is not None:
            mape_values.append(mape)
        if wmape_column:
            wmape = _parse_float(row.get(wmape_column))
            if wmape is not None:
                wmape_values.append(wmape)
        bias = _parse_float(row.get("bias"))
        if bias is not None:
            bias_values.append(bias)
        grade = str(row.get("grade") or "").strip().upper()
        if grade:
            grade_counts[grade] = grade_counts.get(grade, 0) + 1

    report_date = _report_date_from_path(path)
    summary = {
        "latest_report_path": str(path),
        "latest_report_date": report_date,
        "latest_report_row_count": len(rows),
        "latest_report_has_mape": has_mape,
        "latest_report_has_wmape": wmape_column is not None,
        "latest_report_wmape_column": wmape_column,
        "latest_report_has_bias": has_bias,
        "latest_report_avg_mape": _avg(mape_values),
        "latest_report_avg_wmape": _avg(wmape_values),
        "latest_report_avg_bias": _avg(bias_values),
        "latest_report_max_abs_bias": round(max((abs(value) for value in bias_values), default=0.0), 2)
        if bias_values
        else None,
        "latest_report_grade_counts": grade_counts,
        "latest_report_rows_with_mape": len(mape_values),
        "latest_report_rows_with_wmape": len(wmape_values),
        "latest_report_rows_with_bias": len(bias_values),
    }
    if rows and not has_mape:
        fatal.append("missing_csv_column:mape")
    if rows and not has_bias:
        fatal.append("missing_csv_column:bias")
    return summary, fatal


def _db_summary(conn: sqlite3.Connection, *, as_of_date: date) -> tuple[dict[str, Any], list[str]]:
    fatal: list[str] = []
    if not _table_exists(conn, "fact_forecast_accuracy"):
        return {}, ["missing_table:fact_forecast_accuracy"]
    latest = conn.execute(
        """
        SELECT
            COUNT(*) AS row_count,
            MAX(accuracy_date) AS latest_accuracy_date,
            ROUND(AVG(mape), 2) AS avg_mape_all,
            ROUND(AVG(bias), 2) AS avg_bias_all,
            SUM(sample_size) AS sample_size_all
        FROM fact_forecast_accuracy
        """
    ).fetchone()
    latest_date = latest["latest_accuracy_date"]
    latest_slice = conn.execute(
        """
        SELECT
            COUNT(*) AS latest_row_count,
            ROUND(AVG(mape), 2) AS latest_avg_mape,
            ROUND(AVG(bias), 2) AS latest_avg_bias,
            ROUND(MAX(ABS(bias)), 2) AS latest_max_abs_bias,
            SUM(sample_size) AS latest_sample_size
        FROM fact_forecast_accuracy
        WHERE accuracy_date = ?
        """,
        (latest_date,),
    ).fetchone()
    horizons = [
        int(row["horizon_days"])
        for row in conn.execute(
            "SELECT DISTINCT horizon_days FROM fact_forecast_accuracy ORDER BY horizon_days"
        ).fetchall()
    ]
    by_sku = [
        {
            "sku_key": str(row["sku_key"]),
            "store_code": str(row["store_code"]),
            "horizon_days": int(row["horizon_days"]),
            "mape": float(row["mape"]),
            "bias": float(row["bias"]),
            "sample_size": int(row["sample_size"] or 0),
            "model_version": row["model_version"],
        }
        for row in conn.execute(
            """
            SELECT sku_key, store_code, horizon_days, mape, bias, sample_size, model_version
            FROM fact_forecast_accuracy
            WHERE accuracy_date = ?
            ORDER BY mape DESC, sku_key
            """,
            (latest_date,),
        ).fetchall()
    ]
    summary = {
        "accuracy_table_row_count": int(latest["row_count"] or 0),
        "accuracy_latest_date": latest_date,
        "accuracy_age_days": _age_days(latest_date, as_of_date),
        "accuracy_avg_mape_all": float(latest["avg_mape_all"]) if latest["avg_mape_all"] is not None else None,
        "accuracy_avg_bias_all": float(latest["avg_bias_all"]) if latest["avg_bias_all"] is not None else None,
        "accuracy_sample_size_all": int(latest["sample_size_all"] or 0),
        "accuracy_latest_row_count": int(latest_slice["latest_row_count"] or 0),
        "accuracy_latest_avg_mape": float(latest_slice["latest_avg_mape"])
        if latest_slice["latest_avg_mape"] is not None
        else None,
        "accuracy_latest_avg_bias": float(latest_slice["latest_avg_bias"])
        if latest_slice["latest_avg_bias"] is not None
        else None,
        "accuracy_latest_max_abs_bias": float(latest_slice["latest_max_abs_bias"])
        if latest_slice["latest_max_abs_bias"] is not None
        else None,
        "accuracy_latest_sample_size": int(latest_slice["latest_sample_size"] or 0),
        "accuracy_horizons": horizons,
        "accuracy_latest_rows": by_sku,
    }
    return summary, fatal


def _auto_po_consumer_summary(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {
            "auto_po_consumer_path": str(path),
            "auto_po_consumer_exists": False,
            "auto_po_consumer_uses_accuracy_table": False,
            "auto_po_consumer_reads_mape": False,
        }
    text = path.read_text(encoding="utf-8")
    return {
        "auto_po_consumer_path": str(path),
        "auto_po_consumer_exists": True,
        "auto_po_consumer_uses_accuracy_table": "fact_forecast_accuracy" in text,
        "auto_po_consumer_reads_mape": "mape" in text.lower(),
    }


def _render_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# G-PO-03 Forecast Accuracy Bias Loop Report",
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


def build_forecast_accuracy_loop_report(
    *,
    config_path: Path = DEFAULT_CONFIG,
    output_root: Path = DEFAULT_OUTPUT_ROOT,
    as_of: str | None = None,
) -> dict[str, Any]:
    config = _load_json(config_path)
    db_path = _resolve_path(config["db_path"])
    dashboard_path = _resolve_path(config.get("dashboard_path", "docs/plan/green_path_2026-06/dashboard/progress-data.js"))
    scoreboard_path = _resolve_path(config["scoreboard_path"])
    report_pattern = str(config["accuracy_report_glob"])
    auto_po_consumer_path = _resolve_path(config["auto_po_consumer_path"])
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
    max_report_age = int(config.get("max_report_age_days", 30))
    max_mape = float(config.get("max_mape_pct", 30.0))
    max_wmape = float(config.get("max_wmape_pct", 30.0))
    max_abs_bias = float(config.get("max_abs_bias_pct", 5.0))

    fatal_errors: list[str] = []
    with _connect_ro(db_path) as conn:
        db_summary, db_fatal = _db_summary(conn, as_of_date=as_of_date)
    fatal_errors.extend(db_fatal)

    latest_report_path = _latest_accuracy_report(report_pattern)
    csv_summary, csv_fatal = _parse_accuracy_csv(latest_report_path)
    fatal_errors.extend(csv_fatal)
    consumer_summary = _auto_po_consumer_summary(auto_po_consumer_path)

    latest_report_date = csv_summary.get("latest_report_date")
    latest_report_age_days = _age_days(latest_report_date, as_of_date)
    avg_mape = csv_summary.get("latest_report_avg_mape")
    avg_wmape = csv_summary.get("latest_report_avg_wmape")
    avg_bias = csv_summary.get("latest_report_avg_bias")
    max_observed_abs_bias = csv_summary.get("latest_report_max_abs_bias")

    checks: list[dict[str, Any]] = []
    blockers: list[str] = []

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

    report_found = latest_report_path is not None and Path(latest_report_path).exists()
    checks.append(
        _check(
            report_found,
            "monthly_report_found",
            str(latest_report_path) if latest_report_path else "missing",
        )
    )
    if not report_found:
        blockers.append("monthly_forecast_accuracy_report_missing")

    report_fresh = latest_report_age_days is not None and latest_report_age_days <= max_report_age
    checks.append(
        _check(
            report_fresh,
            "monthly_report_fresh",
            f"report_age_days={latest_report_age_days} max={max_report_age}",
        )
    )
    if not report_fresh:
        blockers.append(f"report_age_days={latest_report_age_days}>{max_report_age}")

    mape_ok = avg_mape is not None and avg_mape <= max_mape
    checks.append(
        _check(
            mape_ok,
            "mape_published_and_below_threshold",
            f"avg_mape={avg_mape} max={max_mape}",
        )
    )
    if not mape_ok:
        blockers.append(f"avg_mape={avg_mape}>{max_mape}")

    wmape_ok = avg_wmape is not None and avg_wmape <= max_wmape
    checks.append(
        _check(
            wmape_ok,
            "wape_published_and_below_threshold",
            f"avg_wmape={avg_wmape} max={max_wmape} column={csv_summary.get('latest_report_wmape_column')}",
        )
    )
    if not wmape_ok:
        blockers.append(f"avg_wmape={avg_wmape}>{max_wmape}")

    bias_ok = avg_bias is not None and abs(avg_bias) <= max_abs_bias
    checks.append(
        _check(
            bias_ok,
            "signed_bias_published_and_within_threshold",
            f"avg_bias={avg_bias} max_abs={max_abs_bias} max_observed_abs_bias={max_observed_abs_bias}",
        )
    )
    if not bias_ok:
        blockers.append(f"avg_bias={avg_bias} outside +/-{max_abs_bias}")

    consumer_ok = bool(
        consumer_summary["auto_po_consumer_exists"]
        and consumer_summary["auto_po_consumer_uses_accuracy_table"]
        and consumer_summary["auto_po_consumer_reads_mape"]
    )
    checks.append(
        _check(
            consumer_ok,
            "auto_po_consumes_accuracy_table",
            (
                f"exists={consumer_summary['auto_po_consumer_exists']} "
                f"uses_table={consumer_summary['auto_po_consumer_uses_accuracy_table']} "
                f"reads_mape={consumer_summary['auto_po_consumer_reads_mape']}"
            ),
        )
    )
    if not consumer_ok:
        blockers.append("auto_po_consumer_not_bound_to_fact_forecast_accuracy")

    if fatal_errors:
        gate = "RED"
    elif all(row["ok"] for row in checks):
        gate = "GREEN"
    else:
        gate = "ARMED"

    passed_checks = sum(1 for row in checks if row["ok"])
    json_path = out_dir / "forecast_accuracy_loop_report.json"
    md_path = out_dir / "forecast_accuracy_loop_report.md"
    report: dict[str, Any] = {
        "contract_id": config.get("contract_id", "FORECAST_ACCURACY_BIAS_LOOP_V1"),
        "gate_id": config.get("gate_id", "G-PO-03"),
        "gate": gate,
        "generated_at": generated_at,
        "as_of": as_of_dt.isoformat(),
        "db_open_mode": "ro",
        "db_path": str(db_path),
        "dashboard_path": str(dashboard_path),
        "scoreboard_path": str(scoreboard_path),
        "accuracy_report_glob": report_pattern,
        "dependency_statuses": dependency_statuses,
        "max_report_age_days": max_report_age,
        "max_mape_pct": max_mape,
        "max_wmape_pct": max_wmape,
        "max_abs_bias_pct": max_abs_bias,
        "fatal_errors": fatal_errors,
        "blockers": blockers,
        "checks": checks,
        "passed_checks": passed_checks,
        "total_checks": len(checks),
        "json_path": str(json_path),
        "md_path": str(md_path),
    }
    report.update(db_summary)
    report.update(csv_summary)
    report.update(
        {
            "latest_report_age_days": latest_report_age_days,
            "signed_bias_direction": "over_forecast" if avg_bias and avg_bias > 0 else "under_forecast" if avg_bias and avg_bias < 0 else "neutral_or_missing",
        }
    )
    report.update(consumer_summary)

    json_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    md_path.write_text(_render_markdown(report), encoding="utf-8")
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--as-of")
    parser.add_argument("--strict", action="store_true", help="Return non-zero only when the gate is RED.")
    args = parser.parse_args(argv)

    report = build_forecast_accuracy_loop_report(
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
