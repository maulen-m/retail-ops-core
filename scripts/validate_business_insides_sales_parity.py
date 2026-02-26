#!/usr/bin/env python3
"""Validate BUSINESS_INSIDES sales freshness/parity signals for a target day."""

from __future__ import annotations

import argparse
from datetime import date, datetime, timezone
import json
from pathlib import Path
import sys
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.generate_business_insides import compute_sales_metrics


DEFAULT_DB = PROJECT_ROOT / "db" / "app.db"
DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "config" / "business_insides"
DEFAULT_REPORT_ROOT = PROJECT_ROOT / "exports" / "daily"


def _resolve_snapshot(output_dir: Path, as_of_iso: str) -> Path | None:
    direct = output_dir / f"BUSINESS_INSIDES_{as_of_iso}.md"
    if direct.exists():
        return direct
    alt = output_dir / "snapshots" / f"BUSINESS_INSIDES_{as_of_iso}.md"
    if alt.exists():
        return alt
    return None


def _render_md(report: dict[str, Any]) -> str:
    lines = [
        "# BUSINESS_INSIDES Sales Parity",
        "",
        f"- generated_at: `{report['generated_at']}`",
        f"- as_of: `{report['as_of']}`",
        f"- status: `{report['status']}`",
        f"- observed_days_last_7_calendar: `{report['observed_days_last_7_calendar']}`",
        f"- latest_sale_date_available: `{report['latest_sale_date_available']}`",
        f"- sales_truth_freshness_days: `{report['sales_truth_freshness_days']}`",
        "",
    ]
    if report["errors"]:
        lines.extend(["## Errors", ""])
        for err in report["errors"]:
            lines.append(f"- {err}")
        lines.append("")
    if report["warnings"]:
        lines.extend(["## Warnings", ""])
        for row in report["warnings"]:
            lines.append(f"- {row}")
        lines.append("")
    return "\n".join(lines)


def validate_business_insides_sales_parity(
    *,
    db_path: Path,
    output_dir: Path,
    as_of: str,
    report_root: Path,
    require_recent_sales: bool,
    max_sales_truth_lag_days: int,
    strict: bool,
) -> dict[str, Any]:
    as_of_date = date.fromisoformat(as_of)
    metrics = compute_sales_metrics(db_path=db_path, as_of=as_of_date)
    errors: list[str] = []
    warnings: list[str] = []

    snapshot = _resolve_snapshot(output_dir, as_of)
    if snapshot is None:
        errors.append(f"BUSINESS_INSIDES snapshot missing for as_of={as_of}")
    else:
        text = snapshot.read_text(encoding="utf-8")
        for marker in ("## Sales Truth Freshness", "## Latest Observed Sales Days (Truth)"):
            if marker not in text:
                errors.append(f"snapshot missing marker: {marker}")

    observed_days_last_7 = int(metrics.get("observed_days_last_7_calendar") or 0)
    freshness_days = metrics.get("sales_truth_freshness_days")
    if require_recent_sales and observed_days_last_7 <= 0:
        errors.append("no observed sales rows in last 7 calendar days")
    elif observed_days_last_7 <= 0:
        warnings.append("no observed sales rows in last 7 calendar days")

    if freshness_days is None:
        errors.append("no sales truth rows found in 30-day window")
    elif int(freshness_days) > int(max_sales_truth_lag_days):
        errors.append(
            "sales truth freshness lag above threshold: "
            f"lag_days={freshness_days} threshold={max_sales_truth_lag_days}"
        )

    ok = len(errors) == 0
    out_dir = report_root / as_of
    out_dir.mkdir(parents=True, exist_ok=True)
    report = {
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "as_of": as_of,
        "status": "PASS" if ok else "FAIL",
        "ok": ok,
        "snapshot_path": str(snapshot) if snapshot else None,
        "observed_days_last_7_calendar": observed_days_last_7,
        "latest_sale_date_available": metrics.get("latest_sale_date_available"),
        "sales_truth_freshness_days": freshness_days,
        "errors": errors,
        "warnings": warnings,
    }
    json_path = out_dir / "business_insides_sales_parity.json"
    md_path = out_dir / "business_insides_sales_parity.md"
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    md_path.write_text(_render_md(report), encoding="utf-8")
    report["json_path"] = str(json_path)
    report["md_path"] = str(md_path)

    if strict and not ok:
        raise RuntimeError("business_insides sales parity validation failed")
    return report


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Validate BUSINESS_INSIDES sales parity and freshness")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--as-of", required=True)
    parser.add_argument("--report-root", type=Path, default=DEFAULT_REPORT_ROOT)
    parser.add_argument("--max-sales-truth-lag-days", type=int, default=7)
    parser.add_argument("--require-recent-sales", action="store_true")
    parser.add_argument("--strict", action="store_true")
    return parser


def main() -> int:
    args = _build_parser().parse_args()
    report = validate_business_insides_sales_parity(
        db_path=args.db.resolve(),
        output_dir=args.output_dir.resolve(),
        as_of=str(args.as_of),
        report_root=args.report_root.resolve(),
        require_recent_sales=bool(args.require_recent_sales),
        max_sales_truth_lag_days=int(args.max_sales_truth_lag_days),
        strict=bool(args.strict),
    )
    print(f"business_insides_sales_parity_json={report['json_path']}")
    print(f"business_insides_sales_parity_md={report['md_path']}")
    print(f"status={report['status']}")
    return 0 if report["ok"] or not args.strict else 1


if __name__ == "__main__":
    raise SystemExit(main())
