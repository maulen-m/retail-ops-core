#!/usr/bin/env python3
"""Render portable launchd templates into concrete plists for the current project root."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_TEMPLATE_ROOT = PROJECT_ROOT / "config" / "launchd_templates"
DEFAULT_OUTPUT_ROOT = PROJECT_ROOT / "config" / "launchd_rendered"

PLACEHOLDERS = {
    "__PROJECT_ROOT__": lambda root: str(root),
    "__RUNTIME_LOG_DIR__": lambda root: str(root / "runtime_logs"),
    "__VENV_PYTHON__": lambda root: str(root / ".venv" / "bin" / "python"),
    "__RUN_KASPI_IMPORT_SCHEDULER__": lambda root: str(root / "scripts" / "run_kaspi_import_scheduler.py"),
    "__RUN_KASPI_DAILY_OPS_REPORT_SCHEDULER__": lambda root: str(root / "scripts" / "run_kaspi_daily_ops_report_scheduler.py"),
    "__RUN_MERGED_BUILD_WAYBILLS_COMMAND__": lambda root: str(root / "excel_ui" / "run_merged_build_waybills.command"),
}


def render_launchd_plists(
    *,
    project_root: Path,
    output_dir: Path,
    template_root: Path | None = None,
) -> dict[str, Any]:
    root = project_root.resolve()
    templates = (template_root or DEFAULT_TEMPLATE_ROOT).resolve()
    destination = output_dir.resolve()
    destination.mkdir(parents=True, exist_ok=True)

    rendered_files: dict[str, str] = {}
    for template_path in sorted(templates.glob("*.plist.tmpl")):
        text = template_path.read_text(encoding="utf-8")
        for token, resolver in PLACEHOLDERS.items():
            text = text.replace(token, resolver(root))
        out_name = template_path.name.replace(".tmpl", "")
        out_path = destination / out_name
        out_path.write_text(text, encoding="utf-8")
        rendered_files[out_name] = str(out_path)

    report = {
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "project_root": str(root),
        "template_root": str(templates),
        "output_dir": str(destination),
        "rendered_files": rendered_files,
    }
    return report


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Render portable launchd plist templates")
    parser.add_argument("--project-root", type=Path, default=PROJECT_ROOT)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--template-root", type=Path, default=None)
    parser.add_argument("--report-json", type=Path, default=None)
    return parser


def main() -> int:
    args = _build_parser().parse_args()
    report = render_launchd_plists(
        project_root=args.project_root,
        output_dir=args.output_dir,
        template_root=args.template_root,
    )
    if args.report_json is not None:
        args.report_json.parent.mkdir(parents=True, exist_ok=True)
        args.report_json.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"render_report={args.report_json}")
    else:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
