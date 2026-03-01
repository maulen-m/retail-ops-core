#!/usr/bin/env python3
"""Fail-closed PO capital protection validator."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_OUTPUT_ROOT = PROJECT_ROOT / "exports" / "validation" / "po_capital_protection"
DEFAULT_PROPOSALS_ROOT = PROJECT_ROOT / "exports" / "po"

ROIC_FULL_PCT = 20.0
ROIC_FLAG_PCT = 10.0
ALLOWED_EXIT_PATHS = {
    "STANDARD_SELL_THROUGH",
    "MONITOR_AND_REPRICE",
    "LIQUIDATION_PLAN_REQUIRED",
    "NO_DEMAND_EXIT_REQUIRED",
}


def _expected_roic_action(roic_pct: float) -> str:
    if roic_pct >= ROIC_FULL_PCT:
        return "ORDER_FULL"
    if roic_pct >= ROIC_FLAG_PCT:
        return "ORDER_WITH_FLAG"
    return "REVIEW_REQUIRED"


def _render_md(report: dict[str, Any]) -> str:
    lines = [
        "# PO Capital Protection Validation",
        "",
        f"- generated_at: `{report['generated_at']}`",
        f"- as_of: `{report['as_of']}`",
        f"- status: `{report['status']}`",
        f"- proposals_json: `{report['proposals_json']}`",
        "",
        "| check | status | details |",
        "|---|---:|---|",
    ]
    for row in report["checks"]:
        lines.append(f"| `{row['check']}` | {'PASS' if row['ok'] else 'FAIL'} | {row['details']} |")
    if report["errors"]:
        lines.extend(["", "## Errors", ""])
        for err in report["errors"]:
            lines.append(f"- {err}")
    return "\n".join(lines) + "\n"


def _resolve_proposals_json(*, as_of: str, proposals_json: Path | None) -> Path:
    if proposals_json is not None:
        return proposals_json.resolve()
    return (DEFAULT_PROPOSALS_ROOT / as_of / "po_proposals.json").resolve()


def validate_po_capital_protection(
    *,
    as_of: str,
    proposals_json: Path | None = None,
    output_root: Path = DEFAULT_OUTPUT_ROOT,
    strict: bool = False,
) -> dict[str, Any]:
    errors: list[str] = []
    checks: list[dict[str, Any]] = []
    proposals_path = _resolve_proposals_json(as_of=as_of, proposals_json=proposals_json)
    payload: dict[str, Any] = {}

    if not proposals_path.exists():
        errors.append(f"po proposals file not found: {proposals_path}")
    else:
        try:
            payload = json.loads(proposals_path.read_text(encoding="utf-8"))
        except Exception as exc:
            errors.append(f"invalid proposals json: {exc}")

    lines = payload.get("lines") if isinstance(payload, dict) else None
    if not isinstance(lines, list):
        errors.append("po proposals json missing `lines` list")
        lines = []
    if len(lines) == 0:
        errors.append("po proposals list is empty")

    required_fields = {
        "sku_key",
        "store_code",
        "suggested_order_qty",
        "roic_monthly_pct",
        "roic_action",
        "capital_at_risk_kzt",
        "capital_share_pct",
        "is_new_sku",
        "new_sku_cap_limit_pct",
        "new_sku_cap_compliant",
        "exit_path",
        "requires_human_review",
    }

    roic_mismatches = 0
    new_sku_violations = 0
    missing_field_rows = 0
    review_flag_violations = 0
    bad_exit_paths = 0

    for idx, line in enumerate(lines):
        if not isinstance(line, dict):
            errors.append(f"line {idx}: invalid object")
            missing_field_rows += 1
            continue
        missing = sorted(field for field in required_fields if field not in line)
        if missing:
            missing_field_rows += 1
            errors.append(f"line {idx} missing fields: {', '.join(missing)}")
            continue

        roic_pct = float(line.get("roic_monthly_pct") or 0.0)
        expected_action = _expected_roic_action(roic_pct)
        actual_action = str(line.get("roic_action") or "").strip()
        if expected_action != actual_action:
            roic_mismatches += 1
            errors.append(
                f"line {idx} sku={line.get('sku_key')}: roic_action mismatch expected={expected_action} actual={actual_action}"
            )

        capital_at_risk = float(line.get("capital_at_risk_kzt") or 0.0)
        if capital_at_risk <= 0:
            errors.append(f"line {idx} sku={line.get('sku_key')}: capital_at_risk_kzt must be > 0")

        is_new = bool(line.get("is_new_sku"))
        cap_limit = float(line.get("new_sku_cap_limit_pct") or 0.0)
        cap_share = float(line.get("capital_share_pct") or 0.0)
        cap_compliant = bool(line.get("new_sku_cap_compliant"))
        if is_new and (cap_share > cap_limit + 1e-9 or not cap_compliant):
            new_sku_violations += 1
            errors.append(
                f"line {idx} sku={line.get('sku_key')}: new SKU cap breach share={cap_share:.2f}% limit={cap_limit:.2f}%"
            )

        exit_path = str(line.get("exit_path") or "").strip()
        if exit_path not in ALLOWED_EXIT_PATHS:
            bad_exit_paths += 1
            errors.append(f"line {idx} sku={line.get('sku_key')}: invalid exit_path={exit_path}")

        requires_human_review = bool(line.get("requires_human_review"))
        if actual_action == "REVIEW_REQUIRED" and not requires_human_review:
            review_flag_violations += 1
            errors.append(
                f"line {idx} sku={line.get('sku_key')}: REVIEW_REQUIRED must set requires_human_review=true"
            )

    checks.append(
        {"check": "required_fields_present", "ok": missing_field_rows == 0, "details": str(missing_field_rows)}
    )
    checks.append(
        {"check": "roic_action_threshold_match", "ok": roic_mismatches == 0, "details": str(roic_mismatches)}
    )
    checks.append(
        {"check": "new_sku_cap_compliance", "ok": new_sku_violations == 0, "details": str(new_sku_violations)}
    )
    checks.append(
        {"check": "review_required_flag", "ok": review_flag_violations == 0, "details": str(review_flag_violations)}
    )
    checks.append(
        {"check": "exit_path_valid", "ok": bad_exit_paths == 0, "details": str(bad_exit_paths)}
    )

    ok = len(errors) == 0
    out_dir = output_root.resolve() / as_of
    out_dir.mkdir(parents=True, exist_ok=True)
    report = {
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "as_of": as_of,
        "status": "PASS" if ok else "FAIL",
        "ok": bool(ok),
        "proposals_json": str(proposals_path),
        "checks": checks,
        "errors": errors,
    }
    json_path = out_dir / "capital_protection_report.json"
    md_path = out_dir / "capital_protection_report.md"
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    md_path.write_text(_render_md(report), encoding="utf-8")
    report["json_path"] = str(json_path)
    report["md_path"] = str(md_path)

    if strict and not ok:
        raise RuntimeError("capital protection validation failed")
    return report


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Validate PO capital protection contract")
    parser.add_argument("--as-of", required=True)
    parser.add_argument("--proposals-json", type=Path, default=None)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--strict", action="store_true")
    return parser


def main() -> int:
    args = _build_parser().parse_args()
    report = validate_po_capital_protection(
        as_of=str(args.as_of),
        proposals_json=args.proposals_json,
        output_root=args.output_root,
        strict=bool(args.strict),
    )
    print(f"po_capital_protection_json={report['json_path']}")
    print(f"po_capital_protection_md={report['md_path']}")
    print(f"status={report['status']}")
    return 0 if report["ok"] or not args.strict else 1


if __name__ == "__main__":
    raise SystemExit(main())
