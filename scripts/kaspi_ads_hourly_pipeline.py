#!/usr/bin/env python3
"""Run hourly Kaspi ads snapshot then hourly profile/reconciliation."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SNAPSHOT_SCRIPT = PROJECT_ROOT / "scripts" / "kaspi_ads_hourly_snapshot.py"
PROFILE_SCRIPT = PROJECT_ROOT / "scripts" / "kaspi_ads_build_hourly_profile.py"


def _try_parse_json(stdout: str) -> dict[str, Any] | None:
    lines = [line.strip() for line in stdout.splitlines() if line.strip()]
    for line in reversed(lines):
        try:
            parsed = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, dict):
            return parsed
    return None


def _run_step(cmd: list[str]) -> tuple[int, str, str, dict[str, Any] | None]:
    proc = subprocess.run(cmd, capture_output=True, text=True)
    parsed = _try_parse_json(proc.stdout)
    return proc.returncode, proc.stdout, proc.stderr, parsed


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run hourly ads snapshot + profile builder pipeline")
    parser.add_argument("--ads-db", type=Path, default=None, help="Ads DB path (or set KASPI_MARKETING_DB_PATH)")
    parser.add_argument("--merchant-id", default=None)
    parser.add_argument("--profile-dir", default=None)
    parser.add_argument("--date", default=None)
    parser.add_argument("--snapshot-at", default=None)
    parser.add_argument("--headful", action="store_true")
    parser.add_argument("--manual-login", action="store_true")
    parser.add_argument("--login-timeout", type=float, default=None)
    parser.add_argument("--max-attempts", type=int, default=None)
    parser.add_argument("--backoff-seconds", type=float, default=None)
    parser.add_argument("--since", default=None)
    parser.add_argument("--until", default=None)
    parser.add_argument("--tolerance-pct", type=float, default=None)
    parser.add_argument("--strict-profile", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    snapshot_cmd = [sys.executable, str(SNAPSHOT_SCRIPT)]
    if args.ads_db is not None:
        snapshot_cmd.extend(["--ads-db", str(args.ads_db)])
    if args.merchant_id:
        snapshot_cmd.extend(["--merchant-id", str(args.merchant_id)])
    if args.profile_dir:
        snapshot_cmd.extend(["--profile-dir", str(args.profile_dir)])
    if args.date:
        snapshot_cmd.extend(["--date", str(args.date)])
    if args.snapshot_at:
        snapshot_cmd.extend(["--snapshot-at", str(args.snapshot_at)])
    if args.headful:
        snapshot_cmd.append("--headful")
    if args.manual_login:
        snapshot_cmd.append("--manual-login")
    if args.login_timeout is not None:
        snapshot_cmd.extend(["--login-timeout", str(args.login_timeout)])
    if args.max_attempts is not None:
        snapshot_cmd.extend(["--max-attempts", str(args.max_attempts)])
    if args.backoff_seconds is not None:
        snapshot_cmd.extend(["--backoff-seconds", str(args.backoff_seconds)])

    profile_cmd = [sys.executable, str(PROFILE_SCRIPT)]
    if args.ads_db is not None:
        profile_cmd.extend(["--ads-db", str(args.ads_db)])
    if args.since:
        profile_cmd.extend(["--since", str(args.since)])
    if args.until:
        profile_cmd.extend(["--until", str(args.until)])
    if args.tolerance_pct is not None:
        profile_cmd.extend(["--tolerance-pct", str(args.tolerance_pct)])
    if args.strict_profile:
        profile_cmd.append("--strict")

    snap_rc, snap_out, snap_err, snap_json = _run_step(snapshot_cmd)
    if snap_out:
        print(snap_out.rstrip())
    if snap_err:
        print(snap_err.rstrip(), file=sys.stderr)

    profile_rc = 1
    profile_out = ""
    profile_err = ""
    profile_json: dict[str, Any] | None = None
    if snap_rc == 0:
        profile_rc, profile_out, profile_err, profile_json = _run_step(profile_cmd)
        if profile_out:
            print(profile_out.rstrip())
        if profile_err:
            print(profile_err.rstrip(), file=sys.stderr)

    final = {
        "status": "ok" if snap_rc == 0 and profile_rc == 0 else "error",
        "snapshot_exit_code": snap_rc,
        "profile_exit_code": profile_rc,
        "snapshot": snap_json,
        "profile": profile_json,
    }
    print(json.dumps(final, ensure_ascii=False))
    return 0 if final["status"] == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())
