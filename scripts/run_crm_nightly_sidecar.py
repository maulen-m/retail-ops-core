#!/usr/bin/env python3
"""Run the legacy CRM writer as an isolated nightly compatibility sidecar.

This entrypoint deliberately does not refresh Kaspi, publish Google Ops Board,
write the production DB, or send messages. The canonical daily shipping path
owns those responsibilities. Live CRM mutation remains fail-closed behind an
explicit LaunchAgent environment gate and ``--apply``.
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import subprocess
import sys


PROJECT_ROOT = Path(__file__).resolve().parent.parent
PYTHON = PROJECT_ROOT / ".venv" / "bin" / "python"
IMPORT_SCRIPT = PROJECT_ROOT / "scripts" / "import_orders_to_crm.py"
TIMEOUT_SCRIPT = PROJECT_ROOT / "scripts" / "run_with_timeout.py"
ACTIVEORDERS_PATH = PROJECT_ROOT / "excel_ui" / "ActiveOrders" / "ActiveOrders.xlsx"
CRM_WORKBOOK_PATH = PROJECT_ROOT / "excel_ui" / "SALES_KSP_CRM_V3.xlsx"
SUMMARY_PATH = PROJECT_ROOT / "logs" / "import_orders_to_crm_nightly_latest.json"
APPLY_ENV_GATE = "ENABLE_CRM_NIGHTLY_SIDECAR"
# The final semantic readback reloads the full formula-heavy workbook and can
# legitimately take about 13 minutes after Excel has already saved it. Keep a
# hard outer bound while leaving enough headroom for the complete local run.
DEFAULT_TIMEOUT_SECONDS = 2700


def build_import_command(*, apply: bool, timeout_seconds: int) -> list[str]:
    command = [
        str(PYTHON),
        str(TIMEOUT_SCRIPT),
        "--timeout",
        str(timeout_seconds),
        "--",
        str(PYTHON),
        "-u",
        str(IMPORT_SCRIPT),
        "--orders-dir",
        str(ACTIVEORDERS_PATH.parent),
        "--crm-file",
        str(CRM_WORKBOOK_PATH),
        "--verbose",
        "--no-update",
        "--strict-excel",
        "--kaspi-core-override",
        "--include-overdue",
        "--overdue-lookback-days",
        "5",
        "--skip-fixed-backfill",
        "--fixed-values-scope",
        "new-only",
        "--no-gdrive-sync",
        "--summary-file",
        str(SUMMARY_PATH),
    ]
    if not apply:
        command.append("--dry-run")
    return command


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="Write the guarded local CRM workbook.")
    parser.add_argument("--timeout-seconds", type=int, default=DEFAULT_TIMEOUT_SECONDS)
    args = parser.parse_args(argv)

    if args.timeout_seconds < 1:
        print("ERROR: --timeout-seconds must be positive.", file=sys.stderr)
        return 64
    for required in (PYTHON, IMPORT_SCRIPT, TIMEOUT_SCRIPT, ACTIVEORDERS_PATH, CRM_WORKBOOK_PATH):
        if not required.exists():
            print(f"ERROR: required CRM sidecar surface is missing: {required}", file=sys.stderr)
            return 78
    if args.apply and str(os.environ.get(APPLY_ENV_GATE) or "").strip() != "1":
        print(f"ERROR: --apply requires {APPLY_ENV_GATE}=1.", file=sys.stderr)
        return 78

    env = os.environ.copy()
    env.setdefault("TERM", "dumb")
    env.setdefault("PYTHONUNBUFFERED", "1")

    preflight = subprocess.run(
        [str(PYTHON), str(IMPORT_SCRIPT), "--excel-session-preflight-only"],
        cwd=str(PROJECT_ROOT),
        env=env,
    )
    if preflight.returncode != 0:
        print("ERROR: CRM nightly sidecar Excel-session preflight failed.", file=sys.stderr)
        return int(preflight.returncode)

    SUMMARY_PATH.parent.mkdir(parents=True, exist_ok=True)
    result = subprocess.run(
        build_import_command(apply=args.apply, timeout_seconds=args.timeout_seconds),
        cwd=str(PROJECT_ROOT),
        env=env,
    )
    return int(result.returncode)


if __name__ == "__main__":
    raise SystemExit(main())
