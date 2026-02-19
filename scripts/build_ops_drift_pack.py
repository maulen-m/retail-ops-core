#!/usr/bin/env python3
"""Build daily ops drift artifact (alias over single-truth drift pack)."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.build_single_truth_drift_pack import (
    DEFAULT_DB,
    DEFAULT_OUTPUT_ROOT,
    build_single_truth_drift_pack,
)


def build_ops_drift_pack(
    *,
    db_path: Path = DEFAULT_DB,
    as_of: str | None = None,
    output_root: Path = DEFAULT_OUTPUT_ROOT,
    workbook_path: Path | None = None,
    workbook_sheet: str = "SALES_KSP_CRM_1",
    max_lag_days: int = 1,
) -> dict[str, str]:
    return build_single_truth_drift_pack(
        db_path=db_path,
        as_of=as_of,
        output_root=output_root,
        workbook_path=workbook_path,
        workbook_sheet=workbook_sheet,
        max_lag_days=max_lag_days,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Build single-truth ops drift pack")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument("--as-of", type=str, default=None)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--workbook", type=Path, default=None)
    parser.add_argument("--workbook-sheet", type=str, default="SALES_KSP_CRM_1")
    parser.add_argument("--max-lag-days", type=int, default=1)
    args = parser.parse_args()

    result = build_ops_drift_pack(
        db_path=args.db,
        as_of=args.as_of,
        output_root=args.output_root,
        workbook_path=args.workbook,
        workbook_sheet=args.workbook_sheet,
        max_lag_days=args.max_lag_days,
    )
    print(f"json_path={result['json_path']}")
    print(f"markdown_path={result['markdown_path']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
