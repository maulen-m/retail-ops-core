#!/usr/bin/env python3
"""Validate H5 proving-run artifact completeness for one as-of day."""

from __future__ import annotations

import argparse
from datetime import date, datetime, timezone
import json
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_OUTPUT_ROOT = PROJECT_ROOT / "exports" / "validation" / "h5_artifact_set"


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
        "# H5 Artifact Set Validation",
        "",
        f"- generated_at: `{report['generated_at']}`",
        f"- as_of: `{report['as_of']}`",
        f"- status: `{report['status']}`",
        f"- require_weekly: `{str(report['require_weekly']).lower()}`",
        "",
        "| artifact | required | exists | artifact_as_of | status |",
        "|---|---:|---:|---|---:|",
    ]
    for row in report["checks"]:
        lines.append(
            f"| `{row['artifact']}` | {str(row['required']).lower()} | "
            f"{str(row['exists']).lower()} | `{row['artifact_as_of']}` | "
            f"{'PASS' if row['ok'] else 'FAIL'} |"
        )
    if report["errors"]:
        lines.extend(["", "## Errors", ""])
        for err in report["errors"]:
            lines.append(f"- {err}")
    return "\n".join(lines) + "\n"


def validate_h5_artifact_set(
    *,
    project_root: Path,
    as_of: str,
    output_root: Path,
    require_weekly: bool,
    strict: bool,
) -> dict[str, Any]:
    root = Path(project_root).resolve()
    as_of_day = date.fromisoformat(as_of)
    week_key = f"{as_of_day.isocalendar().year}-W{as_of_day.isocalendar().week:02d}"

    required_files: list[tuple[str, Path, bool]] = [
        ("daily_ops_report", root / "exports" / "daily" / as_of / "daily_ops_report.json", True),
        ("exceptions", root / "exports" / "exceptions" / as_of / "exceptions.json", True),
        ("system_health", root / "exports" / "diagnostics" / as_of / "system_health.json", True),
        ("daily_ops_timings", root / "exports" / "perf" / as_of / "daily_ops_timings.json", True),
        ("truth_drift_report", root / "exports" / "daily" / as_of / "truth_drift_report.json", True),
        (
            "weekly_health_scorecard",
            root / "exports" / "health" / "weekly" / week_key / "weekly_health_scorecard.json",
            bool(require_weekly),
        ),
    ]

    errors: list[str] = []
    checks: list[dict[str, Any]] = []
    for name, path, required in required_files:
        payload = _read_json(path)
        exists = payload is not None
        artifact_as_of = str((payload or {}).get("as_of") or "")
        ok = True
        if required:
            ok = exists and artifact_as_of == as_of
            if not exists:
                errors.append(f"missing or invalid JSON: {path}")
            elif artifact_as_of != as_of:
                errors.append(f"as_of mismatch in {path}: expected {as_of}, got {artifact_as_of}")
        checks.append(
            {
                "name": name,
                "artifact": str(path),
                "required": required,
                "exists": exists,
                "artifact_as_of": artifact_as_of if artifact_as_of else "<missing>",
                "ok": bool(ok),
            }
        )

    ok = len(errors) == 0
    out_dir = Path(output_root).resolve() / as_of
    out_dir.mkdir(parents=True, exist_ok=True)
    report = {
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "as_of": as_of,
        "status": "PASS" if ok else "FAIL",
        "ok": bool(ok),
        "require_weekly": bool(require_weekly),
        "project_root": str(root),
        "checks": checks,
        "errors": errors,
    }
    json_path = out_dir / "h5_artifact_set_report.json"
    md_path = out_dir / "h5_artifact_set_report.md"
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    md_path.write_text(_render_md(report), encoding="utf-8")
    report["json_path"] = str(json_path)
    report["md_path"] = str(md_path)

    if strict and not ok:
        raise RuntimeError("h5 artifact-set validation failed")
    return report


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Validate required H5 artifact set for a day")
    parser.add_argument("--project-root", type=Path, default=PROJECT_ROOT)
    parser.add_argument("--as-of", required=True)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--require-weekly", action="store_true")
    parser.add_argument("--strict", action="store_true")
    return parser


def main() -> int:
    args = _build_parser().parse_args()
    report = validate_h5_artifact_set(
        project_root=args.project_root,
        as_of=str(args.as_of),
        output_root=args.output_root,
        require_weekly=bool(args.require_weekly),
        strict=bool(args.strict),
    )
    print(f"h5_artifact_set_json={report['json_path']}")
    print(f"h5_artifact_set_md={report['md_path']}")
    print(f"status={report['status']}")
    return 0 if report["ok"] or not args.strict else 1


if __name__ == "__main__":
    raise SystemExit(main())
