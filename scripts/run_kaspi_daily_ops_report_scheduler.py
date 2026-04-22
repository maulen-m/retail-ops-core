#!/usr/bin/env python3
"""Launchd entrypoint for daily ops report generation (read-only)."""

from __future__ import annotations

import argparse
import sys
from datetime import date
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.generate_daily_ops_report import generate_daily_ops_report
from scripts.run_kaspi_daily_ops import run_kaspi_daily_ops
from scripts.validate_daily_ops_report import validate_daily_ops_report

DEFAULT_RUNTIME_ROOT = PROJECT_ROOT / "exports" / "validation" / "board_v8_runtime"
DEFAULT_DAILY_ROOT = PROJECT_ROOT / "exports" / "daily"


def main() -> int:
    parser = argparse.ArgumentParser(description="Run daily ops orchestrator and publish daily report")
    parser.add_argument("--as-of", default=date.today().isoformat())
    parser.add_argument("--profile", choices=["today-fast", "catch-up"], default="catch-up")
    parser.add_argument("--runtime-root", type=Path, default=DEFAULT_RUNTIME_ROOT)
    parser.add_argument("--daily-root", type=Path, default=DEFAULT_DAILY_ROOT)
    args = parser.parse_args()

    summary = run_kaspi_daily_ops(
        project_root=PROJECT_ROOT,
        as_of=args.as_of,
        output_root=args.runtime_root,
        allow_store_failures=set(),
        profile=args.profile,
        dry_run=True,
    )

    report = generate_daily_ops_report(
        summary_json=Path(summary["summary_json"]),
        output_dir=args.daily_root / args.as_of,
    )
    validate_daily_ops_report(Path(report["json_path"]), strict=True)

    print(f"summary_json={summary['summary_json']}")
    print(f"daily_report_json={report['json_path']}")
    print(f"daily_report_md={report['md_path']}")
    return int(summary["exit_code"])


if __name__ == "__main__":
    raise SystemExit(main())
