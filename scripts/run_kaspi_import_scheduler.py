#!/usr/bin/env python3
"""LaunchAgent entrypoint for the CRM-free daily shipping source refresh."""

from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent
SOURCE_REFRESH_PATH = PROJECT_ROOT / "scripts" / "run_google_ops_board_publish_scheduler.py"
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.google_ops_board_automation_common import (  # noqa: E402
    ensure_kaspi_api_call_ledger_env,
    run_guarded,
    today_almaty,
)


LOCK_CONTENTION_EXIT_CODE = 75
LOCK_RETRY_INTERVAL_SECONDS = 15
LOCK_RETRY_MAX_ATTEMPTS = 21


def run_forced_source_refresh(*, project_root: Path, env: dict[str, str]) -> int:
    command = [sys.executable, str(SOURCE_REFRESH_PATH), "--force-source-refresh"]
    for attempt in range(1, LOCK_RETRY_MAX_ATTEMPTS + 1):
        result = subprocess.run(command, cwd=str(project_root), env=env)
        returncode = int(result.returncode)
        if returncode != LOCK_CONTENTION_EXIT_CODE:
            return returncode
        if attempt == LOCK_RETRY_MAX_ATTEMPTS:
            print(
                "ERROR: forced shipping-source refresh exhausted the bounded "
                f"shared-lock retry window ({attempt} attempts).",
                file=sys.stderr,
            )
            return returncode
        print(
            "Shared Google Ops Board lock is busy; retrying forced source "
            f"refresh in {LOCK_RETRY_INTERVAL_SECONDS}s "
            f"({attempt}/{LOCK_RETRY_MAX_ATTEMPTS - 1}).",
            file=sys.stderr,
        )
        time.sleep(LOCK_RETRY_INTERVAL_SECONDS)
    return LOCK_CONTENTION_EXIT_CODE


def main() -> int:
    project_root = PROJECT_ROOT

    if not SOURCE_REFRESH_PATH.exists():
        print(f"ERROR: missing direct source refresh entrypoint: {SOURCE_REFRESH_PATH}", file=sys.stderr)
        return 78

    env = os.environ.copy()
    env.setdefault("TERM", "dumb")
    ensure_kaspi_api_call_ledger_env(env, target_date=today_almaty(), project_root=PROJECT_ROOT)
    if env.get("KASPI_API_CALL_LEDGER_PATH"):
        os.environ.setdefault("KASPI_API_CALL_LEDGER_PATH", env["KASPI_API_CALL_LEDGER_PATH"])

    return run_forced_source_refresh(project_root=project_root, env=env)


if __name__ == "__main__":
    raise SystemExit(run_guarded("run_kaspi_import_scheduler", main))
