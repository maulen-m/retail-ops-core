#!/usr/bin/env python3
"""Validate that required daily artifacts converge on one authoritative as-of date."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.resolve_as_of_date import resolve_as_of_date


def _read_json(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    return payload if isinstance(payload, dict) else None


def _render_md(report: dict[str, Any]) -> str:
    lines = [
        "# As-Of Consistency Report",
        "",
        f"- generated_at: `{report['generated_at']}`",
        f"- as_of: `{report['as_of']}`",
        f"- as_of_source: `{report['as_of_source']}`",
        f"- status: `{report['status']}`",
        "",
        "| artifact | required | exists | artifact_as_of | status |",
        "|---|---:|---:|---|---:|",
    ]
    for row in report["checks"]:
        lines.append(
            f"| `{row['artifact']}` | {str(row['required']).lower()} | {str(row['exists']).lower()} | "
            f"`{row['artifact_as_of']}` | {'PASS' if row['ok'] else 'FAIL'} |"
        )
    if report["errors"]:
        lines.extend(["", "## Errors", ""])
        for err in report["errors"]:
            lines.append(f"- {err}")
    return "\n".join(lines) + "\n"


def validate_as_of_consistency(
    *,
    project_root: Path,
    as_of: str,
    as_of_source: str,
    output_root: Path,
    strict: bool,
) -> dict[str, Any]:
    root = Path(project_root).resolve()
    required_artifacts = [
        root / "exports" / "daily" / as_of / "daily_ops_report.json",
        root / "exports" / "daily" / as_of / "po_scorecard.json",
        root / "exports" / "daily" / as_of / "inventory_scorecard.json",
        root / "exports" / "daily" / as_of / "cashflow_scorecard.json",
        root / "exports" / "daily" / as_of / "truth_drift_report.json",
        root / "exports" / "perf" / as_of / "daily_ops_timings.json",
        root / "exports" / "diagnostics" / as_of / "system_health.json",
        root / "exports" / "exceptions" / as_of / "exceptions.json",
    ]
    business_insides_candidates = [
        root / "config" / "business_insides" / f"BUSINESS_INSIDES_{as_of}.json",
        root / "config" / "business_insides" / "snapshots" / f"BUSINESS_INSIDES_{as_of}.json",
    ]
    waybill_selection_path = root / "excel_ui" / "ActiveOrders" / "waybills" / "_waybill_selection_orders.json"

    checks: list[dict[str, Any]] = []
    errors: list[str] = []

    for path in required_artifacts:
        payload = _read_json(path)
        exists = payload is not None
        artifact_as_of = str(payload.get("as_of") or "") if payload else ""
        ok = exists and artifact_as_of == as_of
        checks.append(
            {
                "artifact": str(path),
                "required": True,
                "exists": bool(exists),
                "artifact_as_of": artifact_as_of or "<missing>",
                "ok": bool(ok),
            }
        )
        if not exists:
            errors.append(f"missing or invalid JSON: {path}")
        elif artifact_as_of != as_of:
            errors.append(f"as_of mismatch in {path}: expected {as_of}, got {artifact_as_of}")

    business_payload = None
    business_payload_path = None
    for candidate in business_insides_candidates:
        payload = _read_json(candidate)
        if payload is None:
            continue
        business_payload = payload
        business_payload_path = candidate
        break
    business_as_of = ""
    business_ok = business_payload is not None
    if business_payload is not None:
        business_as_of = str(
            business_payload.get("as_of")
            or business_payload.get("as_of_date")
            or ""
        ).strip()
        business_ok = business_as_of == as_of
        if not business_ok:
            errors.append(
                "as_of mismatch in BUSINESS_INSIDES snapshot: "
                f"expected {as_of}, got {business_as_of or '<missing>'}"
            )
    else:
        errors.append(
            "missing BUSINESS_INSIDES JSON snapshot: "
            f"tried {business_insides_candidates[0]} and {business_insides_candidates[1]}"
        )
    checks.append(
        {
            "artifact": str(business_payload_path or business_insides_candidates[0]),
            "required": True,
            "exists": business_payload is not None,
            "artifact_as_of": business_as_of or "<missing>",
            "ok": bool(business_ok),
        }
    )

    waybill_payload = _read_json(waybill_selection_path)
    waybill_target_date = ""
    waybill_ok = True
    if waybill_payload is not None:
        waybill_target_date = str(waybill_payload.get("target_date") or "").strip()
        waybill_ok = waybill_target_date == as_of
    checks.append(
        {
            "artifact": str(waybill_selection_path),
            "required": False,
            "exists": waybill_payload is not None,
            "artifact_as_of": waybill_target_date or "<missing>",
            "ok": bool(waybill_ok),
        }
    )

    # Guardrail: no mixed-date as_of values in daily artifact folder.
    daily_dir = root / "exports" / "daily" / as_of
    if daily_dir.exists():
        for path in sorted(daily_dir.glob("*.json")):
            payload = _read_json(path)
            if not payload:
                continue
            value = payload.get("as_of")
            if value is None:
                continue
            if str(value) != as_of:
                errors.append(f"mixed as_of in daily folder: {path} has {value}, expected {as_of}")

    ok = len(errors) == 0
    out_dir = Path(output_root).resolve() / as_of
    out_dir.mkdir(parents=True, exist_ok=True)

    report = {
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "as_of": as_of,
        "as_of_source": as_of_source,
        "status": "PASS" if ok else "FAIL",
        "ok": bool(ok),
        "errors": errors,
        "checks": checks,
        "project_root": str(root),
    }
    json_path = out_dir / "asof_consistency_report.json"
    md_path = out_dir / "asof_consistency_report.md"
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    md_path.write_text(_render_md(report), encoding="utf-8")
    report["json_path"] = str(json_path)
    report["md_path"] = str(md_path)

    if strict and not ok:
        raise RuntimeError("as-of consistency validation failed")
    return report


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Validate as-of consistency across required artifacts")
    parser.add_argument("--project-root", type=Path, default=PROJECT_ROOT)
    parser.add_argument("--as-of", default=None)
    parser.add_argument("--output-root", type=Path, default=PROJECT_ROOT / "exports" / "validation" / "asof_consistency")
    parser.add_argument("--strict", action="store_true")
    return parser


def main() -> int:
    args = _build_parser().parse_args()
    resolution = resolve_as_of_date(
        project_root=args.project_root.resolve(),
        explicit_as_of=args.as_of,
        strict=bool(args.strict),
        daily_root=args.project_root.resolve() / "exports" / "daily",
    )
    report = validate_as_of_consistency(
        project_root=args.project_root,
        as_of=resolution.as_of,
        as_of_source=resolution.source,
        output_root=args.output_root,
        strict=bool(args.strict),
    )
    print(f"asof_consistency_json={report['json_path']}")
    print(f"asof_consistency_md={report['md_path']}")
    print(f"as_of_source={resolution.source}")
    print(f"status={report['status']}")
    return 0 if report["ok"] or not args.strict else 1


if __name__ == "__main__":
    raise SystemExit(main())
