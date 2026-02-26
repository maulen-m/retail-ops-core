#!/usr/bin/env python3
"""Validate daily autopilot exceptions schema (fail-closed)."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

ALLOWED_SEVERITIES = {"critical", "high", "medium", "low"}
TOP_LEVEL_REQUIRED = {"generated_at", "as_of", "status", "ok", "steps", "exceptions"}
EXCEPTION_REQUIRED = {
    "id",
    "step",
    "domain",
    "severity",
    "owner",
    "recommended_action",
    "evidence_paths",
    "rc",
    "reason",
}


def _is_non_empty_string(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def validate_exceptions_schema(path: Path, *, strict: bool = False) -> dict[str, Any]:
    target = Path(path)
    errors: list[str] = []
    payload: dict[str, Any] | None = None

    if not target.exists():
        errors.append(f"missing file: {target}")
    else:
        try:
            payload = json.loads(target.read_text(encoding="utf-8"))
        except Exception as exc:
            errors.append(f"invalid JSON: {exc}")

    critical_count = 0
    if isinstance(payload, dict):
        for key in sorted(TOP_LEVEL_REQUIRED):
            if key not in payload:
                errors.append(f"missing top-level field: {key}")

        if "as_of" in payload and not _is_non_empty_string(payload.get("as_of")):
            errors.append("top-level field as_of must be non-empty string")
        if "status" in payload and str(payload.get("status", "")).upper() not in {"GREEN", "RED"}:
            errors.append("top-level field status must be GREEN or RED")
        if "ok" in payload and not isinstance(payload.get("ok"), bool):
            errors.append("top-level field ok must be boolean")
        if "steps" in payload and not isinstance(payload.get("steps"), list):
            errors.append("top-level field steps must be list")
        if "exceptions" in payload and not isinstance(payload.get("exceptions"), list):
            errors.append("top-level field exceptions must be list")

        exceptions = payload.get("exceptions") if isinstance(payload.get("exceptions"), list) else []
        for idx, row in enumerate(exceptions):
            prefix = f"exceptions[{idx}]"
            if not isinstance(row, dict):
                errors.append(f"{prefix} must be object")
                continue
            for field in sorted(EXCEPTION_REQUIRED):
                if field not in row:
                    errors.append(f"{prefix} missing field: {field}")

            if "id" in row and not _is_non_empty_string(row.get("id")):
                errors.append(f"{prefix}.id must be non-empty string")
            if "step" in row and not _is_non_empty_string(row.get("step")):
                errors.append(f"{prefix}.step must be non-empty string")
            if "domain" in row and not _is_non_empty_string(row.get("domain")):
                errors.append(f"{prefix}.domain must be non-empty string")
            if "owner" in row and not _is_non_empty_string(row.get("owner")):
                errors.append(f"{prefix}.owner must be non-empty string")
            if "recommended_action" in row and not _is_non_empty_string(row.get("recommended_action")):
                errors.append(f"{prefix}.recommended_action must be non-empty string")
            if "reason" in row and not _is_non_empty_string(row.get("reason")):
                errors.append(f"{prefix}.reason must be non-empty string")
            if "rc" in row and not isinstance(row.get("rc"), int):
                errors.append(f"{prefix}.rc must be integer")

            severity = str(row.get("severity", "")).lower()
            if severity not in ALLOWED_SEVERITIES:
                errors.append(
                    f"{prefix}.severity must be one of {sorted(ALLOWED_SEVERITIES)}"
                )
            if severity == "critical":
                critical_count += 1

            evidence_paths = row.get("evidence_paths")
            if not isinstance(evidence_paths, list) or not evidence_paths:
                errors.append(f"{prefix}.evidence_paths must be non-empty list")
            else:
                for pidx, item in enumerate(evidence_paths):
                    if not _is_non_empty_string(item):
                        errors.append(f"{prefix}.evidence_paths[{pidx}] must be non-empty string")

        if isinstance(payload.get("ok"), bool) and payload.get("ok") and critical_count > 0:
            errors.append("payload ok=true is invalid when critical exceptions exist")
        status = str(payload.get("status", "")).upper()
        if status == "GREEN" and critical_count > 0:
            errors.append("payload status=GREEN is invalid when critical exceptions exist")

    elif payload is not None:
        errors.append("payload must be JSON object")

    report = {
        "path": str(target),
        "ok": len(errors) == 0,
        "errors": errors,
        "critical_count": critical_count,
    }
    if strict and errors:
        raise RuntimeError("exceptions schema validation failed: " + "; ".join(errors))
    return report


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Validate exceptions.json schema")
    parser.add_argument("path", type=Path)
    parser.add_argument("--strict", action="store_true")
    return parser


def main() -> int:
    args = _build_parser().parse_args()
    report = validate_exceptions_schema(args.path, strict=bool(args.strict))
    print(f"exceptions_schema_path={report['path']}")
    print(f"critical_count={report['critical_count']}")
    print("status=PASS" if report["ok"] else "status=FAIL")
    for err in report["errors"]:
        print(f"error: {err}")
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
