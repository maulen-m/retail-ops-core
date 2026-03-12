#!/usr/bin/env python3
"""Fail-closed validator for ads sidecar freshness and mapping coverage."""

from __future__ import annotations

import argparse
from datetime import date, datetime, timedelta, timezone
import json
import os
from pathlib import Path
import sqlite3
import sys
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.ads.sidecar_contract import resolve_ads_db_path, validate_ads_source
DEFAULT_DB = PROJECT_ROOT / "db" / "app.db"
DEFAULT_OUTPUT_ROOT = PROJECT_ROOT / "exports" / "validation" / "ads_sidecar_readiness"


class AdsReadinessError(RuntimeError):
    """Raised when strict ads readiness validation fails."""


def _table_exists(conn: sqlite3.Connection, name: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
        (name,),
    ).fetchone()
    return row is not None


def _load_sidecar_payload(*, db_path: Path, as_of: date) -> dict[str, Any]:
    start_date = as_of - timedelta(days=29)
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    try:
        if not _table_exists(conn, "ads_spend_sidecar_daily"):
            return {
                "status": "unavailable",
                "reason": "sidecar_table_missing",
                "mapped_rows": None,
                "unmapped_rows": None,
                "mapped_cost_kzt": None,
                "unmapped_cost_kzt": None,
                "total_cost_kzt": None,
                "mapping_coverage_pct": None,
            }
        row = conn.execute(
            """
            SELECT
                SUM(COALESCE(mapped_rows, 0)) AS mapped_rows,
                SUM(COALESCE(unmapped_rows, 0)) AS unmapped_rows,
                SUM(COALESCE(mapped_cost_kzt, 0)) AS mapped_cost_kzt,
                SUM(COALESCE(unmapped_cost_kzt, 0)) AS unmapped_cost_kzt,
                SUM(COALESCE(total_cost_kzt, 0)) AS total_cost_kzt
            FROM ads_spend_sidecar_daily
            WHERE date(date) BETWEEN ? AND ?
            """,
            (start_date.isoformat(), as_of.isoformat()),
        ).fetchone()
    finally:
        conn.close()

    mapped_rows = float((row["mapped_rows"] if row is not None else 0.0) or 0.0)
    unmapped_rows = float((row["unmapped_rows"] if row is not None else 0.0) or 0.0)
    mapped_cost = float((row["mapped_cost_kzt"] if row is not None else 0.0) or 0.0)
    unmapped_cost = float((row["unmapped_cost_kzt"] if row is not None else 0.0) or 0.0)
    total_cost = float((row["total_cost_kzt"] if row is not None else 0.0) or 0.0)
    total_rows = mapped_rows + unmapped_rows
    coverage = round((mapped_rows / total_rows) * 100.0, 2) if total_rows else 0.0
    return {
        "status": "available",
        "reason": "ok",
        "mapped_rows": mapped_rows,
        "unmapped_rows": unmapped_rows,
        "mapped_cost_kzt": round(mapped_cost, 2),
        "unmapped_cost_kzt": round(unmapped_cost, 2),
        "total_cost_kzt": round(total_cost, 2),
        "mapping_coverage_pct": coverage,
    }


def _render_md(report: dict[str, Any]) -> str:
    lines = [
        "# Ads Sidecar Readiness",
        "",
        f"- generated_at: `{report['generated_at']}`",
        f"- as_of: `{report['as_of']}`",
        f"- readiness_mode: `{report['readiness_mode']}`",
        f"- status: `{report['status']}`",
        f"- error_code: `{report.get('error_code') or 'none'}`",
        f"- ads_source_path: `{report.get('ads_source_path')}`",
        "",
        "| check | status | details |",
        "|---|---:|---|",
    ]
    for row in report["checks"]:
        lines.append(
            f"| `{row['check']}` | {'PASS' if row['ok'] else 'FAIL'} | {row['details']} |"
        )
    if report["errors"]:
        lines.extend(["", "## Errors", ""])
        for err in report["errors"]:
            lines.append(f"- {err}")
    if report.get("warnings"):
        lines.extend(["", "## Warnings", ""])
        for warning in report["warnings"]:
            lines.append(f"- {warning}")
    return "\n".join(lines) + "\n"


def validate_ads_sidecar_readiness(
    *,
    db_path: Path,
    as_of: date,
    output_root: Path,
    ads_db_path: Path | None = None,
    max_age_hours: float = 36.0,
    min_mapping_coverage_pct: float = 85.0,
    min_total_cost_kzt: float = 1.0,
    readiness_mode: str = "live",
    strict: bool = False,
) -> dict[str, Any]:
    if readiness_mode not in {"live", "apply"}:
        raise ValueError(f"unsupported readiness_mode={readiness_mode!r}")

    checks: list[dict[str, Any]] = []
    errors: list[str] = []
    error_codes: list[str] = []
    warnings: list[str] = []

    resolved_ads_db = resolve_ads_db_path(explicit=ads_db_path, require_exists=False)
    source_status = validate_ads_source(resolved_ads_db, max_age_hours=float(max_age_hours))
    source_ok = bool(source_status.get("ok"))
    source_reason = str(source_status.get("reason") or "unknown")
    checks.append(
        {
            "check": "ads_source_fresh",
            "ok": source_ok or readiness_mode == "live",
            "details": (
                f"mode={readiness_mode} "
                f"reason={source_reason} age_hours={source_status.get('age_hours')} "
                f"max_age_hours={float(max_age_hours)}"
            ),
        }
    )
    if not source_ok:
        if readiness_mode == "apply":
            error_codes.append("ADS_SOURCE_STALE")
            errors.append(
                f"ads source unavailable or stale: reason={source_reason} path={source_status.get('path')}"
            )
        else:
            warnings.append("ADS_SOURCE_STALE")

    ads_payload = _load_sidecar_payload(db_path=db_path.resolve(), as_of=as_of)
    if readiness_mode == "live" and ads_payload.get("status") == "available" and not source_ok:
        ads_payload["reason"] = "sidecar_runtime_ok"
    ads_status = str(ads_payload.get("status") or "")
    ads_reason = str(ads_payload.get("reason") or "unknown")
    checks.append(
        {
            "check": "ads_metrics_available",
            "ok": ads_status == "available",
            "details": f"status={ads_status or '<empty>'} reason={ads_reason}",
        }
    )
    if ads_status != "available":
        error_codes.append("ADS_DATA_UNAVAILABLE")
        errors.append(f"ads metrics unavailable: reason={ads_reason}")

    mapped_rows = float(ads_payload.get("mapped_rows") or 0.0)
    unmapped_rows = float(ads_payload.get("unmapped_rows") or 0.0)
    total_rows = mapped_rows + unmapped_rows
    mapped_cost = float(ads_payload.get("mapped_cost_kzt") or 0.0)
    unmapped_cost = float(ads_payload.get("unmapped_cost_kzt") or 0.0)
    total_cost = float(ads_payload.get("total_cost_kzt") or 0.0)
    coverage = ads_payload.get("mapping_coverage_pct")
    coverage_float = float(coverage) if coverage is not None else None

    coverage_gate_enabled = total_cost >= float(min_total_cost_kzt)
    coverage_ok = (
        (coverage_float is not None and coverage_float >= float(min_mapping_coverage_pct))
        if coverage_gate_enabled
        else True
    )
    checks.append(
        {
            "check": "ads_mapping_coverage",
            "ok": coverage_ok,
            "details": (
                f"coverage_pct={coverage_float if coverage_float is not None else 'None'} "
                f"threshold={float(min_mapping_coverage_pct)} "
                f"total_cost_kzt={round(total_cost, 2)} "
                f"gate_enabled={str(coverage_gate_enabled).lower()}"
            ),
        }
    )
    if not coverage_ok:
        error_codes.append("ADS_MAPPING_COVERAGE_FAIL")
        errors.append(
            f"ads mapping coverage below threshold: {coverage_float}% < {float(min_mapping_coverage_pct)}%"
        )

    report = {
        "generated_at": datetime.now(timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z"),
        "as_of": as_of.isoformat(),
        "readiness_mode": readiness_mode,
        "status": "PASS" if not errors else "FAIL",
        "ok": len(errors) == 0,
        "error_code": error_codes[0] if error_codes else None,
        "error_codes": error_codes,
        "warnings": warnings,
        "checks": checks,
        "errors": errors,
        "db_path": str(db_path.resolve()),
        "ads_source_path": str(source_status.get("path") or resolved_ads_db),
        "ads_source_status": source_status,
        "ads_payload": {
            "status": ads_status,
            "reason": ads_reason,
            "mapped_rows": mapped_rows,
            "unmapped_rows": unmapped_rows,
            "total_rows": total_rows,
            "mapped_cost_kzt": round(mapped_cost, 2),
            "unmapped_cost_kzt": round(unmapped_cost, 2),
            "total_cost_kzt": round(total_cost, 2),
            "mapping_coverage_pct": coverage_float,
        },
        "thresholds": {
            "max_age_hours": float(max_age_hours),
            "min_mapping_coverage_pct": float(min_mapping_coverage_pct),
            "min_total_cost_kzt": float(min_total_cost_kzt),
        },
    }

    out_dir = output_root.resolve() / as_of.isoformat()
    out_dir.mkdir(parents=True, exist_ok=True)
    json_path = out_dir / "ads_sidecar_readiness_report.json"
    md_path = out_dir / "ads_sidecar_readiness_report.md"
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    md_path.write_text(_render_md(report), encoding="utf-8")
    report["json_path"] = str(json_path)
    report["md_path"] = str(md_path)

    if strict and errors:
        raise AdsReadinessError("ads sidecar readiness failed")
    return report


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Validate ads sidecar freshness + mapping readiness.")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument("--as-of", required=True)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--ads-db", type=Path, default=None)
    parser.add_argument(
        "--max-age-hours",
        type=float,
        default=float(os.environ.get("AB_ADS_DB_MAX_AGE_HOURS", "36")),
    )
    parser.add_argument(
        "--min-mapping-coverage-pct",
        type=float,
        default=float(os.environ.get("AB_ADS_MAPPING_MIN_COVERAGE_PCT", "85")),
    )
    parser.add_argument(
        "--min-total-cost-kzt",
        type=float,
        default=float(os.environ.get("AB_ADS_MAPPING_MIN_TOTAL_COST_KZT", "1")),
    )
    parser.add_argument(
        "--readiness-mode",
        choices=("live", "apply"),
        default=os.environ.get("AB_ADS_READINESS_MODE", "live").strip().lower() or "live",
    )
    parser.add_argument("--strict", action="store_true")
    return parser


def main() -> int:
    args = _build_parser().parse_args()
    as_of = date.fromisoformat(str(args.as_of))
    report = validate_ads_sidecar_readiness(
        db_path=args.db,
        as_of=as_of,
        output_root=args.output_root,
        ads_db_path=args.ads_db,
        max_age_hours=float(args.max_age_hours),
        min_mapping_coverage_pct=float(args.min_mapping_coverage_pct),
        min_total_cost_kzt=float(args.min_total_cost_kzt),
        readiness_mode=str(args.readiness_mode),
        strict=bool(args.strict),
    )
    print(f"ads_sidecar_readiness_json={report['json_path']}")
    print(f"ads_sidecar_readiness_md={report['md_path']}")
    print(f"status={report['status']}")
    if report.get("error_code"):
        print(f"error_code={report['error_code']}")
    return 0 if report["ok"] or not args.strict else 1


if __name__ == "__main__":
    raise SystemExit(main())
