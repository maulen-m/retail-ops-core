#!/usr/bin/env python3
"""Fail-closed validator for OPEX readiness used by owner PnL publication."""

from __future__ import annotations

import argparse
from datetime import date, datetime, timedelta, timezone
import json
from pathlib import Path
import sqlite3
import sys
from typing import Any

import yaml

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

DEFAULT_DB = PROJECT_ROOT / "db" / "app.db"
DEFAULT_OUTPUT_ROOT = PROJECT_ROOT / "exports" / "validation" / "opex_readiness"
DEFAULT_SCHEDULE_YAML = PROJECT_ROOT / "config" / "opex" / "opex_schedule.yaml"


class OpexReadinessError(RuntimeError):
    """Raised when strict OPEX readiness validation fails."""


def _render_md(report: dict[str, Any]) -> str:
    lines = [
        "# OPEX Readiness",
        "",
        f"- generated_at: `{report['generated_at']}`",
        f"- as_of: `{report['as_of']}`",
        f"- status: `{report['status']}`",
        f"- error_code: `{report.get('error_code') or 'none'}`",
        f"- db_path: `{report['db_path']}`",
        f"- schedule_yaml: `{report['schedule_yaml']}`",
        "",
        "| check | status | details |",
        "|---|---:|---|",
    ]
    for check in report["checks"]:
        lines.append(
            f"| `{check['check']}` | {'PASS' if check['ok'] else 'FAIL'} | {check['details']} |"
        )
    if report["errors"]:
        lines.extend(["", "## Errors", ""])
        for err in report["errors"]:
            lines.append(f"- {err}")
    return "\n".join(lines) + "\n"


def validate_opex_readiness(
    *,
    db_path: Path,
    as_of: date,
    output_root: Path,
    schedule_yaml: Path,
    max_schedule_age_days: int,
    min_horizon_days: int,
    reference_utc: datetime | None = None,
    strict: bool = False,
) -> dict[str, Any]:
    checks: list[dict[str, Any]] = []
    errors: list[str] = []
    error_codes: list[str] = []

    if max_schedule_age_days < 0:
        raise OpexReadinessError("max_schedule_age_days must be >= 0")
    if min_horizon_days < 0:
        raise OpexReadinessError("min_horizon_days must be >= 0")

    if not db_path.exists():
        raise OpexReadinessError(f"db not found: {db_path}")

    now_utc = reference_utc or datetime.now(timezone.utc)
    freshness_reference_utc = now_utc
    schedule_path = schedule_yaml.expanduser().resolve()
    schedule_exists = schedule_path.exists()
    checks.append(
        {
            "check": "schedule_yaml_exists",
            "ok": schedule_exists,
            "details": str(schedule_path),
        }
    )
    if not schedule_exists:
        error_codes.append("OPEX_SCHEDULE_MISSING")
        errors.append(f"schedule yaml missing: {schedule_path}")

    schedule_source_xlsx = None
    schedule_age_days = None
    schedule_payload: dict[str, Any] = {}
    if schedule_exists:
        schedule_payload = yaml.safe_load(schedule_path.read_text(encoding="utf-8")) or {}
        source_xlsx = str(schedule_payload.get("source_xlsx") or "").strip()
        schedule_source_xlsx = source_xlsx or None
        if source_xlsx:
            xlsx_exists = Path(source_xlsx).expanduser().exists()
            checks.append(
                {
                    "check": "schedule_source_xlsx_exists",
                    "ok": xlsx_exists,
                    "details": source_xlsx,
                }
            )
            if not xlsx_exists:
                error_codes.append("OPEX_SOURCE_XLSX_MISSING")
                errors.append(f"schedule source_xlsx missing: {source_xlsx}")

        modified = datetime.fromtimestamp(schedule_path.stat().st_mtime, tz=timezone.utc)
        future_ok = modified <= freshness_reference_utc
        checks.append(
            {
                "check": "schedule_not_newer_than_reference",
                "ok": future_ok,
                "details": (
                    f"modified_utc={modified.replace(microsecond=0).isoformat()} "
                    f"freshness_reference_utc={freshness_reference_utc.replace(microsecond=0).isoformat()}"
                ),
            }
        )
        if not future_ok:
            error_codes.append("OPEX_SCHEDULE_NEWER_THAN_REFERENCE")
            errors.append(
                "schedule yaml modified after freshness reference: "
                f"modified_utc={modified.replace(microsecond=0).isoformat()} "
                f"reference_utc={freshness_reference_utc.replace(microsecond=0).isoformat()}"
            )
        else:
            schedule_age_days = int((freshness_reference_utc - modified).total_seconds() // 86400)
            age_ok = schedule_age_days <= int(max_schedule_age_days)
            checks.append(
                {
                    "check": "schedule_age",
                    "ok": age_ok,
                    "details": f"age_days={schedule_age_days} max={int(max_schedule_age_days)}",
                }
            )
            if not age_ok:
                error_codes.append("OPEX_SCHEDULE_STALE")
                errors.append(
                    f"schedule yaml stale: age_days={schedule_age_days} exceeds max={int(max_schedule_age_days)}"
                )

    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    try:
        table_exists = (
            conn.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name='fact_cashflow_commitments'"
            ).fetchone()
            is not None
        )
        checks.append(
            {
                "check": "commitments_table_exists",
                "ok": table_exists,
                "details": "fact_cashflow_commitments",
            }
        )
        if not table_exists:
            error_codes.append("OPEX_TABLE_MISSING")
            errors.append("fact_cashflow_commitments table missing")
            row = None
        else:
            row = conn.execute(
                """
                SELECT
                    COUNT(*) AS total_rows,
                    SUM(CASE WHEN UPPER(COALESCE(commit_type,''))='OPEX' THEN 1 ELSE 0 END) AS opex_rows,
                    MAX(CASE WHEN UPPER(COALESCE(commit_type,''))='OPEX' THEN date(commit_date) END) AS max_opex_commit_date,
                    MIN(CASE WHEN UPPER(COALESCE(commit_type,''))='OPEX' THEN date(commit_date) END) AS min_opex_commit_date
                FROM fact_cashflow_commitments
                """
            ).fetchone()
    finally:
        conn.close()

    total_rows = int(row["total_rows"] or 0) if row is not None else 0
    opex_rows = int(row["opex_rows"] or 0) if row is not None else 0
    max_commit_date = str(row["max_opex_commit_date"] or "") if row is not None else ""
    min_commit_date = str(row["min_opex_commit_date"] or "") if row is not None else ""

    has_rows = opex_rows > 0
    checks.append(
        {
            "check": "opex_rows_present",
            "ok": has_rows,
            "details": f"opex_rows={opex_rows} total_rows={total_rows}",
        }
    )
    if not has_rows:
        error_codes.append("OPEX_ROWS_MISSING")
        errors.append("no OPEX rows found in fact_cashflow_commitments")

    horizon_ok = False
    horizon_days = None
    if max_commit_date:
        max_commit = date.fromisoformat(max_commit_date)
        horizon_days = (max_commit - as_of).days
        horizon_ok = horizon_days >= int(min_horizon_days)
    checks.append(
        {
            "check": "opex_horizon",
            "ok": bool(horizon_ok),
            "details": (
                f"max_commit_date={max_commit_date or 'none'} horizon_days={horizon_days if horizon_days is not None else 'n/a'} "
                f"min_required={int(min_horizon_days)}"
            ),
        }
    )
    if not horizon_ok:
        error_codes.append("OPEX_HORIZON_SHORT")
        errors.append(
            f"max opex commit date {max_commit_date or 'none'} does not meet min horizon {int(min_horizon_days)} days"
        )

    payload = {
        "generated_at": now_utc.replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "as_of": as_of.isoformat(),
        "status": "PASS" if not errors else "FAIL",
        "ok": len(errors) == 0,
        "error_code": error_codes[0] if error_codes else None,
        "error_codes": error_codes,
        "errors": errors,
        "checks": checks,
        "db_path": str(db_path.resolve()),
        "schedule_yaml": str(schedule_path),
        "schedule_source_xlsx": schedule_source_xlsx,
        "schedule_age_days": schedule_age_days,
        "freshness_cutoff_utc": freshness_reference_utc.replace(microsecond=0).isoformat(),
        "freshness_reference_utc": freshness_reference_utc.replace(microsecond=0).isoformat(),
        "max_schedule_age_days": int(max_schedule_age_days),
        "min_horizon_days": int(min_horizon_days),
        "total_rows": total_rows,
        "opex_rows": opex_rows,
        "min_commit_date": min_commit_date or None,
        "max_commit_date": max_commit_date or None,
        "horizon_days": horizon_days,
    }

    out_dir = output_root.resolve() / as_of.isoformat()
    out_dir.mkdir(parents=True, exist_ok=True)
    json_path = out_dir / "opex_readiness_report.json"
    md_path = out_dir / "opex_readiness_report.md"
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    md_path.write_text(_render_md(payload), encoding="utf-8")

    payload["json_path"] = str(json_path)
    payload["md_path"] = str(md_path)

    if strict and errors:
        raise OpexReadinessError("opex readiness failed")
    return payload


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Validate OPEX readiness for owner PnL publication")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument("--as-of", required=True)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--schedule-yaml", type=Path, default=DEFAULT_SCHEDULE_YAML)
    parser.add_argument("--max-schedule-age-days", type=int, default=30)
    parser.add_argument("--min-horizon-days", type=int, default=30)
    parser.add_argument("--strict", action="store_true")
    return parser


def main() -> int:
    args = _build_parser().parse_args()
    as_of = date.fromisoformat(str(args.as_of))
    try:
        report = validate_opex_readiness(
            db_path=args.db,
            as_of=as_of,
            output_root=args.output_root,
            schedule_yaml=args.schedule_yaml,
            max_schedule_age_days=int(args.max_schedule_age_days),
            min_horizon_days=int(args.min_horizon_days),
            strict=bool(args.strict),
        )
    except OpexReadinessError as exc:
        print("status=FAIL")
        print("error_code=OPEX_READINESS_FAIL")
        print(f"message={exc}")
        return 1

    print(f"opex_readiness_json={report['json_path']}")
    print(f"opex_readiness_md={report['md_path']}")
    print(f"status={report['status']}")
    if report.get("error_code"):
        print(f"error_code={report['error_code']}")
    return 0 if report["ok"] or not args.strict else 1


if __name__ == "__main__":
    raise SystemExit(main())
