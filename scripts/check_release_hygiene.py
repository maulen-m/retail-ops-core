#!/usr/bin/env python3
"""Enforce repo-relative active docs and no closeout-date overfit in active automation."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


DEFAULT_ACTIVE_DOCS = [
    Path("docs/validation/OWNER_PNL_PUBLICATION_CONTRACT.md"),
    Path("docs/validation/WEBUI_ARCHIVE_SINGLE_TRUTH_CONTRACT.md"),
    Path("docs/DAILY_SOP.md"),
    Path("docs/ops/KASPI_DAILY_OPS_WORKFLOW_CONTRACT.md"),
]

DEFAULT_ACTIVE_SCRIPTS = [
    Path("scripts/run_owner_truth_daily.py"),
    Path("scripts/generate_owner_truth_exceptions.py"),
    Path("scripts/generate_ops_selection_artifacts.py"),
    Path("scripts/smoke_test_owner_truth_daily.py"),
    Path("scripts/build_daily_ops_timings.py"),
    Path("scripts/validate_business_insides_ocean_drop_alignment.py"),
    Path("scripts/system_doctor.py"),
    Path("scripts/triage_owner_truth_stoplines.py"),
    Path("scripts/run_kaspi_import_scheduler.py"),
]

BANNED_ABSOLUTE_PATH_TOKENS = [
    "~/Docs/Autonomous_business",
    "~/Documents/useful tables",
]

BANNED_SCRIPT_DATE_TOKENS = [
    "2026-03-08",
    "20260308",
]


def _format_path(path: Path, root: Path) -> str:
    try:
        return str(path.resolve().relative_to(root.resolve()))
    except ValueError:
        return str(path)


def _scan_file(path: Path, banned_tokens: list[str], *, root: Path) -> list[str]:
    display_path = _format_path(path, root)
    if not path.exists():
        return [f"missing file: {display_path}"]
    text = path.read_text(encoding="utf-8", errors="replace")
    errors: list[str] = []
    for token in banned_tokens:
        if token in text:
            errors.append(f"{display_path}: banned token `{token}`")
    return errors


def check_release_hygiene(
    *,
    project_root: Path,
    active_docs: list[Path] | None = None,
    active_scripts: list[Path] | None = None,
) -> dict[str, Any]:
    root = project_root.resolve()
    docs = DEFAULT_ACTIVE_DOCS if active_docs is None else active_docs
    scripts = DEFAULT_ACTIVE_SCRIPTS if active_scripts is None else active_scripts

    errors: list[str] = []
    for rel_path in docs:
        errors.extend(_scan_file(root / rel_path, BANNED_ABSOLUTE_PATH_TOKENS, root=root))
    for rel_path in scripts:
        errors.extend(
            _scan_file(
                root / rel_path,
                BANNED_ABSOLUTE_PATH_TOKENS + BANNED_SCRIPT_DATE_TOKENS,
                root=root,
            )
        )

    return {
        "status": "PASS" if not errors else "FAIL",
        "ok": not errors,
        "project_root": str(root),
        "active_docs": [str(path) for path in docs],
        "active_scripts": [str(path) for path in scripts],
        "errors": errors,
    }


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Check active release hygiene for owner-truth stabilization")
    parser.add_argument("--project-root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--strict", action="store_true")
    return parser


def main() -> int:
    args = _build_parser().parse_args()
    report = check_release_hygiene(project_root=args.project_root)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["ok"] or not args.strict else 1


if __name__ == "__main__":
    raise SystemExit(main())
