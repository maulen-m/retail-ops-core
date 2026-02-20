#!/usr/bin/env python3
"""LaunchAgent entrypoint for Kaspi import schedule."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


PROJECT_ROOT = Path("~/Docs/Autonomous_business")
COMMAND_PATH = Path("~/Docs/Autonomous_business/excel_ui/run_full_import.command")


def main() -> int:
    project_root = PROJECT_ROOT
    command_path = COMMAND_PATH

    if not command_path.exists():
        print(f"ERROR: missing scheduler command: {command_path}", file=sys.stderr)
        return 78

    env = os.environ.copy()
    env.setdefault("TERM", "dumb")

    result = subprocess.run(["/bin/bash", str(command_path)], cwd=str(project_root), env=env)
    return int(result.returncode)


if __name__ == "__main__":
    raise SystemExit(main())
