#!/usr/bin/env python3
"""
Run strict daily validation with workbook-anchor enforcement.

Fail closed when workbook path is not provided or missing.
Optionally emit lineage artifact.
"""

from __future__ import annotations

import argparse
from datetime import datetime
import os
from pathlib import Path
import subprocess
import sys
from typing import Tuple


PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DB = PROJECT_ROOT / "db" / "app.db"
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def emit_lineage_report(
    *,
    db_path: Path,
    workbook_path: Path,
    output_path: Path,
    strict_exit_code: int,
) -> None:
    from scripts.generate_lineage_report import generate_lineage_report

    generate_lineage_report(
        db_path=db_path,
        workbook_path=workbook_path,
        output_path=output_path,
        strict_exit_code=strict_exit_code,
    )


def run_preflight(
    *,
    db_path: Path = DEFAULT_DB,
    workbook_path: Path | None = None,
    emit_lineage: bool = False,
    lineage_output: Path | None = None,
) -> Tuple[int, str]:
    workbook = workbook_path
    if workbook is None:
        raw = os.environ.get("AB_CRM_WORKBOOK_PATH", "").strip()
        if raw:
            workbook = Path(raw).expanduser()

    if workbook is None:
        return 2, "STRICT_DAILY_PREFLIGHT FAIL: AB_CRM_WORKBOOK_PATH is required"
    if not workbook.exists():
        return 2, f"STRICT_DAILY_PREFLIGHT FAIL: workbook does not exist: {workbook}"

    env = os.environ.copy()
    env["AB_CRM_WORKBOOK_PATH"] = str(workbook)

    cmd = [sys.executable, "scripts/validate_params.py", "--strict", "--db", str(db_path)]
    completed = subprocess.run(cmd, cwd=str(PROJECT_ROOT), env=env, check=False)
    strict_code = int(completed.returncode)

    lineage_path = lineage_output
    if emit_lineage and lineage_path is None:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        lineage_path = PROJECT_ROOT / "exports" / "lineage" / f"lineage_{ts}.json"

    if emit_lineage and lineage_path is not None:
        lineage_path.parent.mkdir(parents=True, exist_ok=True)
        emit_lineage_report(
            db_path=db_path,
            workbook_path=workbook,
            output_path=lineage_path,
            strict_exit_code=strict_code,
        )

    status = "PASS" if strict_code == 0 else "FAIL"
    msg = f"STRICT_DAILY_PREFLIGHT {status}: validate_params --strict rc={strict_code}"
    if emit_lineage and lineage_path is not None:
        msg += f" lineage={lineage_path}"
    return strict_code, msg


def main() -> int:
    parser = argparse.ArgumentParser(description="Run strict daily preflight with workbook-anchor enforcement")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB, help="Database path")
    parser.add_argument("--workbook", type=Path, default=None, help="CRM workbook path (overrides env)")
    parser.add_argument("--emit-lineage", action="store_true", help="Emit lineage artifact JSON")
    parser.add_argument("--lineage-output", type=Path, default=None, help="Explicit lineage artifact path")
    args = parser.parse_args()

    code, summary = run_preflight(
        db_path=args.db,
        workbook_path=args.workbook,
        emit_lineage=bool(args.emit_lineage),
        lineage_output=args.lineage_output,
    )
    print(summary)
    return code


if __name__ == "__main__":
    raise SystemExit(main())
