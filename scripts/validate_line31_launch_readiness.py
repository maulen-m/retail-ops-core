#!/usr/bin/env python3
"""Validate LINE31 launch readiness evidence in one small command."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import json
from pathlib import Path
import sys
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.validate_line31_final_creative_mapping import (
    DEFAULT_MAPPING,
    validate_mapping,
)


DEFAULT_EVIDENCE_ROOT = (
    PROJECT_ROOT
    / "exports"
    / "validation"
    / "line31_goal_stock_dashboard_repair_20260601_133438"
)
DEFAULT_CURRENT_NONCREATIVE_MATRIX = (
    PROJECT_ROOT
    / "exports"
    / "validation"
    / "line31_current_noncreative_gate_refresh_current"
    / "CURRENT_NONCREATIVE_GATE_MATRIX.json"
)
DEFAULT_FALLBACK_NONCREATIVE_MATRIX = (
    PROJECT_ROOT
    / "exports"
    / "validation"
    / "line31_green_except_creative_round3_strict_unrelated_repair_20260601"
    / "final_synthesis"
    / "FINAL_GREEN_EXCEPT_CREATIVE_MATRIX.json"
)
DEFAULT_CURRENT_STATUS = PROJECT_ROOT / "docs" / "current" / "LINE31_LAUNCH_CURRENT_STATUS.json"
READY_GATE = "Gate: GREEN_DRY_RUN_EOD_SUCCESS_WITH_DECLARED_WARNINGS"
REQUIRED_CLOSEOUT_TOKENS = (
    "python3 scripts/validate_params.py --strict",
    "python3 scripts/run_end_of_day.py --dry-run --skip-api-sync --verbose",
    "STATUS: SUCCESS",
    "protected-surface hash sandwich around EOD dry-run",
    "final_creative_publish_intake_and_approval.md",
    "final_creative_asset_mapping_template.json",
)


@dataclass(frozen=True)
class LINE31ReadinessResult:
    ok: bool
    gate: str
    errors: list[str]
    warnings: list[str]
    metrics: dict[str, Any]


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _same_path(left: Path, right: Path) -> bool:
    try:
        return left.resolve() == right.resolve()
    except FileNotFoundError:
        return left.absolute() == right.absolute()


def _default_current_noncreative_matrix(evidence_root: Path) -> Path | None:
    if _same_path(evidence_root, DEFAULT_EVIDENCE_ROOT):
        if DEFAULT_CURRENT_NONCREATIVE_MATRIX.exists():
            return DEFAULT_CURRENT_NONCREATIVE_MATRIX
        if DEFAULT_FALLBACK_NONCREATIVE_MATRIX.exists():
            return DEFAULT_FALLBACK_NONCREATIVE_MATRIX
    return None


def _current_mapping_for_evidence(evidence_root: Path, mapping_path: Path | None) -> Path:
    if mapping_path is not None:
        return mapping_path
    local_mapping = evidence_root / DEFAULT_MAPPING.name
    if not _same_path(evidence_root, DEFAULT_EVIDENCE_ROOT):
        return local_mapping
    try:
        status = json.loads(DEFAULT_CURRENT_STATUS.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return local_mapping
    raw = str(status.get("mapping_path") or "").strip() if isinstance(status, dict) else ""
    current_mapping = Path(raw).expanduser() if raw else None
    return current_mapping if current_mapping and current_mapping.is_file() else local_mapping


def _validate_current_noncreative_matrix(matrix_path: Path) -> tuple[list[str], dict[str, Any]]:
    errors: list[str] = []
    metrics: dict[str, Any] = {"current_noncreative_matrix_path": str(matrix_path)}
    if not matrix_path.exists():
        errors.append(f"current non-creative matrix missing: {matrix_path}")
        metrics["current_noncreative_matrix_exists"] = False
        return errors, metrics

    try:
        matrix = json.loads(matrix_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        errors.append(f"current non-creative matrix invalid JSON: {matrix_path}: {exc}")
        metrics["current_noncreative_matrix_exists"] = True
        return errors, metrics

    metrics["current_noncreative_matrix_exists"] = True
    metrics["current_noncreative_overall_gate"] = matrix.get("overall_gate")
    metrics["current_noncreative_can_use_green_except_creative"] = bool(
        matrix.get("can_use_green_except_creative")
    )
    retained = matrix.get("retained_noncreative_blockers") or []
    metrics["current_noncreative_retained_blockers"] = retained

    if not matrix.get("can_use_green_except_creative"):
        reason = matrix.get("gate_reason") or "latest synthesis does not allow GREEN_EXCEPT_CREATIVE"
        blockers = ", ".join(str(item) for item in retained) or "unspecified"
        errors.append(
            "current non-creative gate is not green-except-creative: "
            f"{reason}; retained_noncreative_blockers={blockers}"
        )
    return errors, metrics


def validate_launch_readiness(
    evidence_root: Path = DEFAULT_EVIDENCE_ROOT,
    *,
    allow_pending_creative: bool = False,
    mapping_path: Path | None = None,
    current_noncreative_matrix: Path | None = None,
    ignore_current_noncreative_matrix: bool = False,
) -> LINE31ReadinessResult:
    errors: list[str] = []
    warnings: list[str] = []
    metrics: dict[str, Any] = {}

    closeout_path = evidence_root / "closeout.md"
    mapping = _current_mapping_for_evidence(evidence_root, mapping_path)

    if not closeout_path.exists():
        errors.append(f"missing closeout: {closeout_path}")
        closeout_text = ""
    else:
        closeout_text = _read_text(closeout_path)
        if READY_GATE not in closeout_text:
            errors.append(f"closeout missing required gate: {READY_GATE}")
        for token in REQUIRED_CLOSEOUT_TOKENS:
            if token not in closeout_text:
                errors.append(f"closeout missing required evidence token: {token}")

    if not mapping.exists():
        errors.append(f"missing creative mapping: {mapping}")
        template_result = None
        strict_result = None
    else:
        template_result = validate_mapping(mapping, template_ok=True)
        strict_result = validate_mapping(mapping, template_ok=False)
        if not template_result.ok:
            errors.extend([f"creative template invalid: {error}" for error in template_result.errors])
        if strict_result.warnings:
            warnings.extend([f"creative strict warning: {warning}" for warning in strict_result.warnings])
        metrics["creative_assets_count"] = template_result.metrics.get("assets_count", 0)

    creative_strict_ok = bool(strict_result and strict_result.ok)
    creative_template_ok = bool(template_result and template_result.ok)
    metrics["creative_template_ok"] = creative_template_ok
    metrics["creative_strict_ok"] = creative_strict_ok
    metrics["allow_pending_creative"] = allow_pending_creative

    matrix_path = None
    if not ignore_current_noncreative_matrix:
        matrix_path = current_noncreative_matrix or _default_current_noncreative_matrix(evidence_root)
    if matrix_path:
        matrix_errors, matrix_metrics = _validate_current_noncreative_matrix(matrix_path)
        errors.extend(matrix_errors)
        metrics.update(matrix_metrics)

    if creative_strict_ok:
        gate = "GREEN_LAUNCH_READY_FOR_OWNER_APPROVED_META_PUBLISH"
    elif allow_pending_creative and creative_template_ok:
        gate = "GREEN_EXCEPT_CREATIVE"
        warnings.append("final creative mapping and owner publish approval are still pending")
    else:
        gate = "YELLOW_CREATIVE_MAPPING_REQUIRED"
        if strict_result:
            errors.extend([f"creative publish not ready: {error}" for error in strict_result.errors])

    ok = not errors and (
        creative_strict_ok or (allow_pending_creative and creative_template_ok)
    )
    return LINE31ReadinessResult(
        ok=ok,
        gate=gate if ok else "YELLOW",
        errors=errors,
        warnings=warnings,
        metrics=metrics,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--evidence-root", type=Path, default=DEFAULT_EVIDENCE_ROOT)
    parser.add_argument("--mapping", type=Path, default=None)
    parser.add_argument(
        "--current-noncreative-matrix",
        type=Path,
        default=None,
        help="Optional latest synthesis matrix that must allow GREEN_EXCEPT_CREATIVE.",
    )
    parser.add_argument(
        "--ignore-current-noncreative-matrix",
        action="store_true",
        help="Validate only the supplied evidence root; intended for fixtures, not current launch state.",
    )
    parser.add_argument(
        "--allow-pending-creative",
        action="store_true",
        help="Pass when all non-creative readiness evidence is green and the creative template is valid.",
    )
    parser.add_argument("--json", action="store_true", help="Emit JSON output.")
    args = parser.parse_args(argv)

    result = validate_launch_readiness(
        args.evidence_root,
        allow_pending_creative=args.allow_pending_creative,
        mapping_path=args.mapping,
        current_noncreative_matrix=args.current_noncreative_matrix,
        ignore_current_noncreative_matrix=args.ignore_current_noncreative_matrix,
    )
    payload = {
        "ok": result.ok,
        "gate": result.gate,
        "errors": result.errors,
        "warnings": result.warnings,
        "metrics": result.metrics,
        "evidence_root": str(args.evidence_root),
        "mapping": str(_current_mapping_for_evidence(args.evidence_root, args.mapping)),
    }
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(f"{'PASS' if result.ok else 'FAIL'}: {result.gate}")
        for warning in result.warnings:
            print(f"WARN: {warning}")
        for error in result.errors:
            print(f"ERROR: {error}")
        print(json.dumps(result.metrics, ensure_ascii=False, sort_keys=True))
    return 0 if result.ok else 1


if __name__ == "__main__":
    sys.exit(main())
