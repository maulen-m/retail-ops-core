#!/usr/bin/env python3
"""Fail-closed validator for single-truth drift pack freshness/completeness."""

from __future__ import annotations

import argparse
import json
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_OUTPUT_ROOT = PROJECT_ROOT / "exports" / "validation"
PACK_JSON_NAME = "single_truth_drift_pack.json"
PACK_MD_NAME = "single_truth_drift_pack.md"
KNOWN_STATUSES = {"PASS", "WARN", "CRITICAL", "STOP_LINE"}
REQUIRED_KEYS = {
    "as_of",
    "generated_at",
    "status",
    "status_reasons",
    "workbook_overage",
    "cogs_integrity",
    "on_delivery_residuals",
    "dim_sku_alignment",
    "paid_capital_snapshot",
}


def validate_drift_pack_slo(
    *,
    output_root: Path = DEFAULT_OUTPUT_ROOT,
    as_of: str | None = None,
    max_age_hours: float = 36.0,
) -> dict[str, Any]:
    as_of_iso = as_of or date.today().isoformat()
    pack_dir = output_root / as_of_iso
    json_path = pack_dir / PACK_JSON_NAME
    md_path = pack_dir / PACK_MD_NAME

    errors: list[str] = []
    warnings: list[str] = []

    if not json_path.exists():
        errors.append(f"missing drift pack json: {json_path}")
    if not md_path.exists():
        errors.append(f"missing drift pack markdown: {md_path}")
    if errors:
        return {
            "ok": False,
            "as_of": as_of_iso,
            "json_path": str(json_path),
            "markdown_path": str(md_path),
            "errors": errors,
            "warnings": warnings,
        }

    payload: dict[str, Any]
    try:
        payload = json.loads(json_path.read_text(encoding="utf-8"))
    except Exception as exc:
        errors.append(f"invalid json payload: {exc}")
        return {
            "ok": False,
            "as_of": as_of_iso,
            "json_path": str(json_path),
            "markdown_path": str(md_path),
            "errors": errors,
            "warnings": warnings,
        }

    missing = sorted(REQUIRED_KEYS - set(payload.keys()))
    if missing:
        errors.append(f"missing required keys: {', '.join(missing)}")

    payload_as_of = str(payload.get("as_of") or "")
    if payload_as_of != as_of_iso:
        errors.append(f"as_of mismatch: payload={payload_as_of or '<empty>'} expected={as_of_iso}")

    status = str(payload.get("status") or "").upper()
    if status not in KNOWN_STATUSES:
        errors.append(f"unknown status={status or '<empty>'}")
    elif status in {"CRITICAL", "STOP_LINE"}:
        errors.append(f"status={status} breaches drift-pack SLO")
    elif status == "WARN":
        warnings.append("status=WARN (allowed by policy, monitor follow-up)")

    newest_mtime = max(
        json_path.stat().st_mtime,
        md_path.stat().st_mtime,
    )
    age_hours = (datetime.now(timezone.utc) - datetime.fromtimestamp(newest_mtime, timezone.utc)).total_seconds() / 3600.0
    if age_hours > max_age_hours:
        errors.append(
            f"drift pack older than max_age_hours: age_hours={age_hours:.2f} limit={max_age_hours:.2f}"
        )

    return {
        "ok": not errors,
        "as_of": as_of_iso,
        "json_path": str(json_path),
        "markdown_path": str(md_path),
        "status": status,
        "age_hours": round(age_hours, 2),
        "errors": errors,
        "warnings": warnings,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate single-truth drift pack SLO")
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--as-of", type=str, default=None)
    parser.add_argument("--max-age-hours", type=float, default=36.0)
    parser.add_argument("--strict", action="store_true", help="Require fail-closed behavior")
    args = parser.parse_args()

    report = validate_drift_pack_slo(
        output_root=args.output_root,
        as_of=args.as_of,
        max_age_hours=args.max_age_hours,
    )

    if report["ok"]:
        print("DRIFT_PACK_SLO PASS")
    else:
        print("DRIFT_PACK_SLO FAIL")
    print(f"as_of={report['as_of']}")
    print(f"json_path={report['json_path']}")
    print(f"markdown_path={report['markdown_path']}")
    if "status" in report:
        print(f"status={report['status']}")
    if "age_hours" in report:
        print(f"age_hours={report['age_hours']}")
    for warning in report.get("warnings", []):
        print(f"WARN: {warning}")
    for err in report.get("errors", []):
        print(f"ERROR: {err}")

    if args.strict:
        return 0 if report["ok"] else 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
