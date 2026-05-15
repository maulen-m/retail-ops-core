#!/usr/bin/env python3
"""Scheduler wrapper for operational-stock daily truth.

The launchd plist pins this wrapper to the repo virtualenv. Scheduled runs
always use the fail-closed owner-publication mode; green publication remains a
manual CLI action after live blockers have been cleared and verified.
"""

from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys

PROJECT_ROOT = Path(__file__).resolve().parent.parent
VENV_RELATIVE = ".venv/bin/python"
VENV_PYTHON = PROJECT_ROOT / VENV_RELATIVE
RUNNER = PROJECT_ROOT / "scripts" / "run_operational_stock_daily_truth.py"


def _ensure_repo_python() -> None:
    if not VENV_PYTHON.exists():
        print(f"ERROR: required scheduler interpreter missing: {VENV_PYTHON}", file=sys.stderr)
        raise SystemExit(2)
    if Path(sys.executable).resolve() != VENV_PYTHON.resolve():
        os.execv(str(VENV_PYTHON), [str(VENV_PYTHON), str(Path(__file__).resolve()), *sys.argv[1:]])


def main() -> int:
    _ensure_repo_python()

    cmd = [str(VENV_PYTHON), str(RUNNER), *sys.argv[1:]]
    if os.environ.get("AB_OPERATIONAL_STOCK_ALLOW_GREEN_OWNER_OUTPUT") == "1":
        print(
            "WARNING: AB_OPERATIONAL_STOCK_ALLOW_GREEN_OWNER_OUTPUT is ignored by the scheduler; "
            "scheduled owner output remains fail-closed.",
            file=sys.stderr,
        )

    proc = subprocess.run(cmd, cwd=str(PROJECT_ROOT), text=True)
    return int(proc.returncode)


if __name__ == "__main__":
    raise SystemExit(main())
