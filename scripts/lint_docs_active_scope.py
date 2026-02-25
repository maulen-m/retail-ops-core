#!/usr/bin/env python3
"""Lint active authority docs for schedule/contract contradictions."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_ACTIVE_DOCS = [
    Path("docs/00_START_HERE.md"),
    Path("docs/DAILY_SOP.md"),
    Path("docs/ops/KASPI_DAILY_OPS_WORKFLOW_CONTRACT.md"),
    Path("docs/ops/KASPI_DAILY_OPS_ORCHESTRATOR_RUNBOOK.md"),
    Path("docs/ops/PROMOTION_MINIMUM_STANDARD.md"),
    Path("docs/authority/INDEX.md"),
]


def lint_active_docs(
    *,
    project_root: Path,
    docs: list[Path] | None = None,
    strict: bool = False,
) -> dict[str, Any]:
    root = Path(project_root).resolve()
    targets = docs or [root / rel for rel in DEFAULT_ACTIVE_DOCS]
    resolved: list[Path] = []
    for path in targets:
        resolved.append(path if path.is_absolute() else root / path)

    errors: list[str] = []
    checked: list[str] = []

    for path in resolved:
        checked.append(str(path))
        if not path.exists():
            errors.append(f"missing active doc: {path}")
            continue
        text = path.read_text(encoding="utf-8")
        if "/Users/" in text:
            errors.append(f"absolute personal path in active doc: {path}")
        if "16:05" in text:
            errors.append(f"deprecated schedule reference 16:05 found in active doc: {path}")

    report = {
        "ok": len(errors) == 0,
        "checked_docs": checked,
        "errors": errors,
    }
    if strict and errors:
        raise RuntimeError("; ".join(errors))
    return report


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Lint active docs scope for contradictions")
    parser.add_argument("--project-root", type=Path, default=PROJECT_ROOT)
    parser.add_argument("--strict", action="store_true")
    parser.add_argument("--doc", action="append", default=None, help="Optional specific doc path (repeatable)")
    return parser


def main() -> int:
    args = _build_parser().parse_args()
    docs = [Path(raw) for raw in args.doc] if args.doc else None
    try:
        report = lint_active_docs(
            project_root=args.project_root,
            docs=docs,
            strict=bool(args.strict),
        )
    except RuntimeError as exc:
        print(f"active_docs_lint: FAIL")
        print(f"ERROR: {exc}")
        return 1

    print("active_docs_lint: OK" if report["ok"] else "active_docs_lint: FAIL")
    for err in report["errors"]:
        print(f"ERROR: {err}")
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

