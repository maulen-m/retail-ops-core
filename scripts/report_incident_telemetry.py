#!/usr/bin/env python3
"""Validate OD-030 incident telemetry and publish the G-OPS-01 report."""

from __future__ import annotations

import argparse
import csv
from datetime import date, datetime, timezone
import json
from pathlib import Path
import re
from typing import Any
from zoneinfo import ZoneInfo

PROJECT_ROOT = Path(__file__).resolve().parent.parent
ALMATY_TZ = ZoneInfo("Asia/Almaty")

DEFAULT_CONFIG = PROJECT_ROOT / "config" / "validation" / "ops_incident_telemetry.json"
DEFAULT_OWNER_DECISIONS = PROJECT_ROOT / "docs" / "plan" / "green_path_2026-06" / "OWNER_DECISIONS_RECORDED.yaml"
DEFAULT_OUTPUT_ROOT = PROJECT_ROOT / "exports" / "validation" / "incident_telemetry"

SENSITIVE_PATTERNS = (
    re.compile(r"(?i)\b(token|secret|password|bearer)\b"),
    re.compile(r"(?i)[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}"),
    re.compile(r"(?<!\d)\+?7\d{10}(?!\d)"),
)


def _now_almaty() -> str:
    return datetime.now(ALMATY_TZ).replace(microsecond=0).isoformat()


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _check(ok: bool, name: str, details: str, **extra: Any) -> dict[str, Any]:
    row: dict[str, Any] = {"check": name, "ok": bool(ok), "details": details}
    row.update(extra)
    return row


def _resolve_project_path(value: str | Path) -> Path:
    path = Path(value)
    if path.is_absolute():
        return path
    return PROJECT_ROOT / path


def _parse_datetime(value: str) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        try:
            return datetime.combine(date.fromisoformat(text[:10]), datetime.min.time(), tzinfo=ALMATY_TZ)
        except ValueError:
            return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=ALMATY_TZ)
    return parsed


def _parse_date(value: str) -> date:
    return date.fromisoformat(str(value)[:10])


def _number(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip().replace(" ", "").replace(",", ".")
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def _contains_sensitive_text(value: str) -> bool:
    text = str(value or "")
    return any(pattern.search(text) for pattern in SENSITIVE_PATTERNS)


def _load_rows(path: Path) -> tuple[list[dict[str, str]], list[str]]:
    if not path.exists():
        return [], []
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        rows = [dict(row) for row in reader]
        return rows, list(reader.fieldnames or [])


def _validate_config(config_path: Path) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    if not config_path.exists():
        return {}, [_check(False, "config_present", f"missing: {config_path}")]
    config = _load_json(config_path)
    checks = [_check(True, "config_present", str(config_path))]
    checks.append(
        _check(
            config.get("contract_id") == "OPS_INCIDENT_TELEMETRY_V1"
            and config.get("gate_id") == "G-OPS-01"
            and config.get("owner_decision_id") == "OD-030",
            "config_identity",
            f"contract={config.get('contract_id')} gate={config.get('gate_id')} decision={config.get('owner_decision_id')}",
        )
    )
    checks.append(
        _check(
            _number(config.get("placeholder_rate_kzt_per_hour")) == 5000.0
            and config.get("cost_basis_mark") == "ASSUMED",
            "placeholder_rate_marked_assumed",
            f"rate={config.get('placeholder_rate_kzt_per_hour')} mark={config.get('cost_basis_mark')}",
        )
    )
    checks.append(
        _check(
            _number(config.get("minimum_collection_days_before_labor_ranking")) == 30.0
            and config.get("labor_ranking_allowed_before_maturity") is False,
            "ranking_blocked_until_30d",
            (
                f"days={config.get('minimum_collection_days_before_labor_ranking')} "
                f"allowed={config.get('labor_ranking_allowed_before_maturity')}"
            ),
        )
    )
    return config, checks


def _validate_owner_decision(path: Path) -> dict[str, Any]:
    if not path.exists():
        return _check(False, "owner_decision_od_030_recorded", f"missing: {path}")
    text = path.read_text(encoding="utf-8")
    required = [
        "id: OD-030",
        "operator_labor_valuation",
        "placeholder_rate_kzt_per_hour: 5000",
        "marked: ASSUMED",
        "telemetry: mandatory_now",
        "revisit: acceptance_with_30d_data",
    ]
    missing = [token for token in required if token not in text]
    return _check(
        not missing,
        "owner_decision_od_030_recorded",
        "missing=" + (",".join(missing) if missing else "none"),
        owner_decisions_path=str(path),
    )


def _validate_rows(
    *,
    rows: list[dict[str, str]],
    fieldnames: list[str],
    config: dict[str, Any],
    as_of: date,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    checks: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []
    required_columns = [str(col) for col in config.get("required_columns") or []]
    missing_columns = [col for col in required_columns if col not in fieldnames]
    checks.append(
        _check(
            not missing_columns,
            "log_schema_columns",
            "missing=" + (",".join(missing_columns) if missing_columns else "none"),
            fieldnames=fieldnames,
        )
    )
    expected_rate = float(config.get("placeholder_rate_kzt_per_hour") or 0)
    expected_mark = str(config.get("cost_basis_mark") or "")
    duplicate_ids: set[str] = set()
    seen_ids: set[str] = set()
    normalized: list[dict[str, Any]] = []
    for index, row in enumerate(rows, start=2):
        incident_id = str(row.get("incident_id") or "").strip()
        row_errors: list[str] = []
        if not incident_id:
            row_errors.append("incident_id missing")
        elif incident_id in seen_ids:
            duplicate_ids.add(incident_id)
            row_errors.append("duplicate incident_id")
        seen_ids.add(incident_id)
        for col in required_columns:
            if not str(row.get(col) or "").strip():
                row_errors.append(f"{col} missing")

        occurred = _parse_datetime(str(row.get("occurred_at") or ""))
        if occurred is None:
            row_errors.append("occurred_at invalid")
        minutes = _number(row.get("minutes_spent"))
        if minutes is None or minutes <= 0:
            row_errors.append("minutes_spent must be positive")
        rate = _number(row.get("cost_rate_kzt_per_hour"))
        if rate != expected_rate:
            row_errors.append(f"cost_rate_kzt_per_hour must be {expected_rate:g}")
        mark = str(row.get("cost_basis_mark") or "").strip()
        if mark != expected_mark:
            row_errors.append(f"cost_basis_mark must be {expected_mark}")
        cost = _number(row.get("cost_kzt"))
        expected_cost = round(((minutes or 0.0) / 60.0) * expected_rate, 2)
        if cost is None or abs(cost - expected_cost) > 0.01:
            row_errors.append(f"cost_kzt must equal {expected_cost:.2f}")
        if str(row.get("owner_decision_id") or "").strip() != "OD-030":
            row_errors.append("owner_decision_id must be OD-030")
        if str(row.get("gate_id") or "").strip() != "G-OPS-01":
            row_errors.append("gate_id must be G-OPS-01")
        for text_col in ("evidence_ref", "operator_notes"):
            if _contains_sensitive_text(str(row.get(text_col) or "")):
                row_errors.append(f"{text_col} contains forbidden sensitive text")

        in_window = False
        if occurred:
            in_window = occurred.astimezone(ALMATY_TZ).date() >= date.fromordinal(as_of.toordinal() - 29)
        normalized.append(
            {
                "incident_id": incident_id,
                "occurred_at": occurred.isoformat() if occurred else None,
                "incident_class": str(row.get("incident_class") or "").strip(),
                "source_surface": str(row.get("source_surface") or "").strip(),
                "severity": str(row.get("severity") or "").strip(),
                "minutes_spent": minutes,
                "cost_kzt": cost,
                "in_trailing_30d": in_window,
                "row_number": index,
            }
        )
        if row_errors:
            errors.append({"row_number": index, "incident_id": incident_id, "errors": row_errors})

    checks.append(
        _check(
            not duplicate_ids,
            "incident_ids_unique",
            "duplicates=" + (",".join(sorted(duplicate_ids)) if duplicate_ids else "none"),
        )
    )
    checks.append(
        _check(
            not errors,
            "incident_rows_have_kzt_cost_lines",
            f"invalid_rows={len(errors)} total_rows={len(rows)}",
        )
    )
    return checks, errors, normalized


def _render_md(report: dict[str, Any]) -> str:
    lines = [
        "# G-OPS-01 Incident Telemetry",
        "",
        f"Gate: {report['gate']}",
        f"Status: {report['status']}",
        f"Generated at: {report['generated_at']}",
        f"As of: {report['as_of']}",
        f"Log path: `{report['log_path']}`",
        "",
        "## Telemetry Window",
        "",
        f"- telemetry_started_at: `{report['telemetry_started_at']}`",
        f"- collection_age_days: `{report['collection_age_days']}`",
        f"- required_collection_days: `{report['required_collection_days']}`",
        f"- labor_ranking_allowed: `{report['labor_ranking_allowed']}`",
        f"- INEF-17 status: `{report['inef17_status']}`",
        f"- rows_total: `{report['row_count_total']}`",
        f"- rows_trailing_30d: `{report['row_count_trailing_30d']}`",
        "",
        "## Checks",
        "",
        "| check | status | details |",
        "|---|---:|---|",
    ]
    for row in report["checks"]:
        lines.append(f"| `{row['check']}` | {'PASS' if row['ok'] else 'FAIL'} | {row['details']} |")
    if report["row_errors"]:
        lines.extend(["", "## Row Errors", ""])
        for error in report["row_errors"]:
            lines.append(f"- row {error['row_number']} `{error.get('incident_id')}`: {', '.join(error['errors'])}")
    if report["first_real_incident_required"]:
        lines.extend(["", "First real non-PII incident row is still required before any measured labor claim."])
    lines.append("")
    return "\n".join(lines)


def build_incident_telemetry_report(
    *,
    as_of: str,
    config_path: Path = DEFAULT_CONFIG,
    owner_decisions_path: Path = DEFAULT_OWNER_DECISIONS,
    output_root: Path = DEFAULT_OUTPUT_ROOT,
) -> dict[str, Any]:
    checks: list[dict[str, Any]] = []
    config, config_checks = _validate_config(config_path)
    checks.extend(config_checks)
    checks.append(_validate_owner_decision(owner_decisions_path))
    as_of_date = _parse_date(as_of)
    log_path = _resolve_project_path(config.get("log_path") or ".claude/ops_incident_telemetry.csv")
    log_exists = log_path.exists()
    rows, fieldnames = _load_rows(log_path)
    checks.append(_check(log_exists, "log_path_present", str(log_path)))
    row_checks, row_errors, normalized_rows = _validate_rows(
        rows=rows,
        fieldnames=fieldnames,
        config=config,
        as_of=as_of_date,
    )
    checks.extend(row_checks)

    started = _parse_datetime(str(config.get("telemetry_started_at") or ""))
    if started is None:
        checks.append(_check(False, "telemetry_started_at_valid", f"value={config.get('telemetry_started_at')}"))
        collection_age_days = 0
    else:
        started_date = started.astimezone(ALMATY_TZ).date()
        collection_age_days = max(0, as_of_date.toordinal() - started_date.toordinal() + 1)
        checks.append(
            _check(
                collection_age_days >= 1,
                "telemetry_started_at_valid",
                f"started={started.isoformat()} age_days={collection_age_days}",
            )
        )

    required_days = int(config.get("minimum_collection_days_before_labor_ranking") or 30)
    mature = collection_age_days >= required_days
    no_failures = all(row["ok"] for row in checks)
    if not no_failures:
        gate = "RED"
    elif mature:
        gate = "GREEN"
    else:
        gate = "ARMED"

    trailing_rows = [row for row in normalized_rows if row["in_trailing_30d"]]
    out_dir = output_root.resolve() / as_of
    out_dir.mkdir(parents=True, exist_ok=True)
    report: dict[str, Any] = {
        "generated_at": _now_almaty(),
        "as_of": as_of,
        "gate": gate,
        "status": gate,
        "ok": gate in {"GREEN", "ARMED"},
        "config_path": str(config_path.resolve()),
        "owner_decisions_path": str(owner_decisions_path.resolve()),
        "log_path": str(log_path.resolve()),
        "telemetry_started_at": str(config.get("telemetry_started_at") or ""),
        "collection_age_days": collection_age_days,
        "required_collection_days": required_days,
        "labor_ranking_allowed": gate == "GREEN",
        "inef17_status": "MEASURED_READY" if gate == "GREEN" else "HYPOTHESIS",
        "first_real_incident_required": len(rows) == 0,
        "row_count_total": len(rows),
        "row_count_trailing_30d": len(trailing_rows),
        "total_minutes_trailing_30d": round(sum(float(row["minutes_spent"] or 0) for row in trailing_rows), 2),
        "total_cost_kzt_trailing_30d": round(sum(float(row["cost_kzt"] or 0) for row in trailing_rows), 2),
        "checks": checks,
        "row_errors": row_errors,
        "no_external_writes_performed": True,
        "production_db_written": False,
    }
    json_path = out_dir / "incident_telemetry_report.json"
    md_path = out_dir / "incident_telemetry_report.md"
    report["json_path"] = str(json_path)
    report["md_path"] = str(md_path)
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    md_path.write_text(_render_md(report), encoding="utf-8")
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate OD-030 incident telemetry for G-OPS-01.")
    parser.add_argument("--as-of", default=datetime.now(ALMATY_TZ).date().isoformat())
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--owner-decisions", type=Path, default=DEFAULT_OWNER_DECISIONS)
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args()

    output_root = args.output_dir if args.output_dir is not None else DEFAULT_OUTPUT_ROOT
    report = build_incident_telemetry_report(
        as_of=args.as_of,
        config_path=args.config,
        owner_decisions_path=args.owner_decisions,
        output_root=output_root,
    )
    print(f"Gate: {report['gate']}")
    print(f"Report: {report['json_path']}")
    if report["row_errors"]:
        print(f"Row errors: {len(report['row_errors'])}")
    if args.strict and report["gate"] == "RED":
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
