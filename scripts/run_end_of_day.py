#!/usr/bin/env python3
"""
End-of-Day Pipeline: Full orchestration script (Part 5: Cutover Ladder)

Runs the complete end-of-day pipeline in sequence:
0. validate_params.py - Validate parameters FIRST (fail-fast)
1. sync_truth_workbook_to_db.py - Optional workbook sync (DB is source of truth)
2. sync_crm_to_db.py - Sync CRM sales data to sales_fact_v2 + fact_sales
2a. sync_kaspi_orders.py - Sync Kaspi API order statuses to fact_orders_kaspi
3. generate_po_dashboard_data.py - Generate demand estimates and PO data
4. smoke_test_dashboard.py - Validate dashboard invariants
5. update_po_dashboard.py - Update dashboard with new data
6. audit_dashboard_output.py - Validate output integrity
7. generate_shadow_scorecard.py - Generate shadow mode scorecard (Part 5)

Scheduled to run at 20:30 local time (Asia/Almaty) via LaunchAgent.

Features:
- Lock file prevents concurrent runs
- Workbook lock detection (graceful exit if Excel file is open)
- Smoke test validation before export
- Parameter validation FIRST (Part 3/5: fail-fast)
- Shadow scorecard generation with Telegram digest (Part 5)
- Run tracking with artifact persistence (Part 5)

Usage:
    python scripts/run_end_of_day.py
    python scripts/run_end_of_day.py --dry-run
    python scripts/run_end_of_day.py --skip-sync  # Skip CRM sync step
    python scripts/run_end_of_day.py --use-workbook-sync  # Enable workbook sync
    python scripts/run_end_of_day.py --skip-workbook-sync  # Skip workbook sync (default)
    python scripts/run_end_of_day.py --auto-assign-sizes  # DB-first size assignment
    python scripts/run_end_of_day.py --skip-day-complete  # Skip day-complete gate
    python scripts/run_end_of_day.py --po4-inbound /path/to/PO-4_inbound.xlsx
    python scripts/run_end_of_day.py --verbose
"""

import argparse
import fcntl
import json
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional

# Add project root to path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from core.tracking.run_tracker import RunTracker
from core.alerts.error_alerts import alert_from_run_tracker, send_shadow_mode_digest
from core.paths import data_path, get_data_root
from core.db.queries import get_cutoff_date_almaty

# Lock file for preventing concurrent runs
LOCK_FILE = PROJECT_ROOT / "logs" / ".end_of_day.lock"

# Default workbook path (can be overridden via TRUTH_WORKBOOK_PATH)
DEFAULT_WORKBOOK = data_path("excel", "Inventory_Core_V18.1_V2.xlsx")

# Database path
DB_PATH = PROJECT_ROOT / "db" / "app.db"

# Expected outputs
EXPECTED_OUTPUTS = [
    PROJECT_ROOT / "exports" / "po_dashboard_data.json",
    PROJECT_ROOT / "exports" / "demand_diagnostics.csv",
]

# Shadow scorecard output (dynamically named by date)
EXPORTS_DIR = PROJECT_ROOT / "exports"


class PipelineLock:
    """Context manager for exclusive pipeline lock using flock."""

    def __init__(self, lock_path: Path):
        self.lock_path = lock_path
        self.lock_file = None

    def __enter__(self):
        # Ensure logs directory exists
        self.lock_path.parent.mkdir(parents=True, exist_ok=True)

        self.lock_file = open(self.lock_path, 'w')
        try:
            fcntl.flock(self.lock_file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            # Write PID for debugging
            self.lock_file.write(f"{os.getpid()}\n")
            self.lock_file.flush()
            return self
        except BlockingIOError:
            self.lock_file.close()
            raise RuntimeError(
                "Another instance of end-of-day pipeline is already running.\n"
                f"Lock file: {self.lock_path}"
            )

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.lock_file:
            fcntl.flock(self.lock_file.fileno(), fcntl.LOCK_UN)
            self.lock_file.close()
            try:
                self.lock_path.unlink()
            except FileNotFoundError:
                pass
        return False


def check_workbook_locked(workbook_path: Path) -> tuple[bool, str]:
    """
    Check if an Excel workbook is locked/open.

    Returns:
        (is_locked, reason)
    """
    if not workbook_path.exists():
        return False, f"Workbook not found: {workbook_path}"

    # Check for Excel lock file (~$filename.xlsx)
    lock_file = workbook_path.parent / f"~${workbook_path.name}"
    if lock_file.exists():
        return True, f"Excel lock file exists: {lock_file.name}"

    # Try to open the file for exclusive write access
    try:
        with open(workbook_path, 'r+b') as f:
            # Try to get an exclusive lock
            fcntl.flock(f.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            fcntl.flock(f.fileno(), fcntl.LOCK_UN)
        return False, "Workbook is available"
    except BlockingIOError:
        return True, "Workbook is locked by another process"
    except PermissionError:
        return True, "Permission denied accessing workbook"
    except Exception as e:
        return True, f"Error checking workbook: {e}"


class PipelineStep:
    """Represents a single step in the pipeline."""

    def __init__(
        self,
        name: str,
        script: str,
        args: Optional[list[str]] = None,
        required: bool = True,
        skip_on_dry_run: bool = False
    ):
        self.name = name
        self.script = script
        self.args = args or []
        self.required = required
        self.skip_on_dry_run = skip_on_dry_run
        self.success: Optional[bool] = None
        self.duration_s: float = 0.0
        self.error: Optional[str] = None


def load_dotenv(dotenv_path: Path) -> None:
    """Load key=value pairs from a .env file without overriding existing env vars."""
    if not dotenv_path.exists():
        return

    try:
        with dotenv_path.open("r") as handle:
            for line in handle:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                if "=" not in line:
                    continue
                key, value = line.split("=", 1)
                key = key.strip()
                value = value.strip()
                if not key or key in os.environ:
                    continue
                os.environ[key] = value
    except Exception as exc:
        print(f"Warning: Failed to load env file {dotenv_path}: {exc}")


def resolve_truth_workbook(default_path: Path) -> Path:
    env_path = os.environ.get("TRUTH_WORKBOOK_PATH") or os.environ.get("TRUTH_WORKBOOK")
    if env_path:
        return Path(env_path).expanduser()
    return default_path


def resolve_po4_inbound_path() -> Optional[Path]:
    env_path = os.environ.get("PO4_INBOUND_PATH") or os.environ.get("PO4_INBOUND")
    if env_path:
        return Path(env_path).expanduser()
    return None


def _format_step_error(returncode: int, stdout: str, stderr: str) -> str:
    parts = [f"Exit code: {returncode}"]
    if stderr:
        parts.append(f"STDERR:\n{stderr}")
    if stdout:
        parts.append(f"STDOUT:\n{stdout}")
    return "\n".join(parts)


def _print_failure_output(stdout: str, stderr: str) -> None:
    stdout_display = stdout if stdout else "(empty)"
    stderr_display = stderr if stderr else "(empty)"
    print("  STDOUT:")
    print(stdout_display)
    print("  STDERR:")
    print(stderr_display)


def run_step(step: PipelineStep, dry_run: bool = False, verbose: bool = False) -> bool:
    """Run a single pipeline step. Returns True on success."""
    script_path = PROJECT_ROOT / "scripts" / step.script

    if not script_path.exists():
        step.error = f"Script not found: {script_path}"
        step.success = False
        return False

    if dry_run and step.skip_on_dry_run:
        print(f"  [DRY-RUN] Skipping {step.name}")
        step.success = True
        return True

    cmd = [sys.executable, str(script_path)] + step.args
    if dry_run:
        cmd.append("--dry-run")

    if verbose:
        print(f"  Running: {' '.join(cmd)}")

    start = datetime.now()
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            cwd=str(PROJECT_ROOT)
        )
        step.duration_s = (datetime.now() - start).total_seconds()

        stdout = (result.stdout or "").rstrip()
        stderr = (result.stderr or "").rstrip()

        if result.returncode != 0:
            _print_failure_output(stdout, stderr)
            step.error = _format_step_error(result.returncode, stdout, stderr)
            step.success = False
            return False

        if verbose:
            if stdout:
                print(stdout)
            if stderr:
                print(stderr, file=sys.stderr)

        step.success = True
        return True

    except Exception as e:
        step.duration_s = (datetime.now() - start).total_seconds()
        step.error = str(e)
        step.success = False
        return False


def verify_outputs() -> list[str]:
    """Verify expected output files exist and are recent."""
    issues = []
    now = datetime.now()

    for path in EXPECTED_OUTPUTS:
        if not path.exists():
            issues.append(f"Missing: {path.name}")
            continue

        # Check file age (should be < 10 minutes old)
        mtime = datetime.fromtimestamp(path.stat().st_mtime)
        age_mins = (now - mtime).total_seconds() / 60

        if age_mins > 10:
            issues.append(f"Stale ({age_mins:.0f}m old): {path.name}")

    return issues


def main():
    load_dotenv(PROJECT_ROOT / ".env")

    parser = argparse.ArgumentParser(
        description="End-of-Day Pipeline",
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--dry-run", action="store_true",
                        help="Don't write to DB or produce outputs")
    parser.add_argument("--skip-sync", action="store_true",
                        help="Skip CRM sync step")
    parser.add_argument(
        "--use-workbook-sync",
        action="store_true",
        help="Enable workbook sync (default: off; DB is source of truth)",
    )
    parser.add_argument(
        "--skip-workbook-sync",
        action="store_true",
        help="Skip truth workbook sync step (default; deprecated alias)",
    )
    parser.add_argument("--skip-api-sync", action="store_true",
                        help="Skip Kaspi API order status sync step (not recommended)")
    parser.add_argument("--skip-day-complete", action="store_true",
                        help="Skip day-complete validation gate (temporary)")
    parser.add_argument("--auto-assign-sizes", action="store_true",
                        help="Auto-assign sizes in DB before day-complete (DB-first, no CRM)")
    parser.add_argument("--size-store", type=str, default=None,
                        help="Store code for size assignment (default: all)")
    max_lookback_days = 13
    parser.add_argument(
        "--api-lookback-days",
        type=int,
        default=max_lookback_days,
        help=f"Lookback window for API order status sync (days, max {max_lookback_days})",
    )
    parser.add_argument(
        "--workbook",
        type=Path,
        default=None,
        help=(
            "Path to truth workbook (default: $TRUTH_WORKBOOK_PATH or "
            f"{DEFAULT_WORKBOOK})"
        ),
    )
    parser.add_argument(
        "--po4-inbound",
        type=Path,
        default=None,
        help="Path to PO-4 inbound workbook (default: $PO4_INBOUND_PATH)",
    )
    parser.add_argument("--verbose", "-v", action="store_true",
                        help="Show script output")
    parser.add_argument("--continue-on-error", action="store_true",
                        help="Continue pipeline even if a step fails")
    parser.add_argument("--no-lock", action="store_true",
                        help="Skip lock file (dangerous, for testing only)")
    args = parser.parse_args()

    if args.api_lookback_days > max_lookback_days:
        print(
            f"WARNING: api-lookback-days={args.api_lookback_days} exceeds max {max_lookback_days}; "
            f"clamping to {max_lookback_days}."
        )
        args.api_lookback_days = max_lookback_days

    start_time = datetime.now()

    print("=" * 70)
    print("END-OF-DAY PIPELINE")
    print("=" * 70)
    print(f"Started: {start_time.isoformat()}")
    print(f"Mode: {'DRY-RUN' if args.dry_run else 'LIVE'}")
    print()

    # Check for concurrent runs (unless --no-lock)
    if not args.no_lock:
        try:
            lock = PipelineLock(LOCK_FILE)
            lock.__enter__()
        except RuntimeError as e:
            print(f"ERROR: {e}")
            print("\nTo force run anyway, use --no-lock (dangerous)")
            sys.exit(2)
    else:
        lock = None
        print("WARNING: Running without lock file (--no-lock)")
        print()

    # Default: skip workbook sync unless explicitly enabled
    if not args.use_workbook_sync:
        args.skip_workbook_sync = True

    if not args.skip_workbook_sync:
        os.environ["AB_USE_TRUTH_WORKBOOK"] = "1"
    else:
        os.environ.pop("AB_USE_TRUTH_WORKBOOK", None)

    if args.workbook is None:
        args.workbook = resolve_truth_workbook(DEFAULT_WORKBOOK)

    if args.po4_inbound is None:
        args.po4_inbound = resolve_po4_inbound_path()
    if args.po4_inbound is not None:
        args.po4_inbound = args.po4_inbound.expanduser()
        if not args.po4_inbound.exists():
            print(f"ERROR: PO-4 inbound workbook not found: {args.po4_inbound}")
            print("Fix: set PO4_INBOUND_PATH=/path/to/PO-4_inbound.xlsx")
            if lock:
                lock.__exit__(None, None, None)
            sys.exit(3)

    # Check if workbook is locked (only if workbook sync enabled)
    if not args.skip_workbook_sync:
        if not args.workbook.exists():
            print(f"ERROR: Truth workbook not found: {args.workbook}")
            print("Fix: set TRUTH_WORKBOOK_PATH=/path/to/workbook")
            print("Or run with --skip-workbook-sync to skip this step.")
            if lock:
                lock.__exit__(None, None, None)
            sys.exit(3)

        print(f"Checking workbook: {args.workbook}")
        is_locked, reason = check_workbook_locked(args.workbook)
        if is_locked:
            print(f"ERROR: Workbook is locked - {reason}")
            print("\nPlease close the workbook in Excel and try again.")
            print("Or use --skip-workbook-sync to skip this step.")
            if lock:
                lock.__exit__(None, None, None)
            sys.exit(3)
        print(f"  OK: {reason}")
        print()

    try:
        return _run_pipeline(args, start_time)
    finally:
        if lock:
            lock.__exit__(None, None, None)


def _run_pipeline(args, start_time: datetime) -> int:
    """Run the actual pipeline steps. Returns exit code."""
    from datetime import date, timedelta
    cutoff_date = get_cutoff_date_almaty()
    os.environ.setdefault("AB_DAY_COMPLETE", "1")
    api_since = (cutoff_date - timedelta(days=args.api_lookback_days)).isoformat()

    # Define pipeline steps
    # Part 5: validate_params FIRST (fail-fast), scorecard LAST
    steps = [
        PipelineStep(
            name="0. Validate Parameters",
            script="validate_params.py",
            args=["--strict"],  # Part 5: fail on warnings too
            required=True  # MUST pass before any other step
        ),
        PipelineStep(
            name="1. Sync Truth Workbook",
            script="sync_truth_workbook_to_db.py",
            args=["--workbook", str(args.workbook)],
            required=not args.skip_workbook_sync
        ),
        PipelineStep(
            name="2. Sync CRM to DB",
            script="sync_crm_to_db.py",
            required=not args.skip_sync
        ),
        PipelineStep(
            name="2a. Sync Kaspi Orders (API)",
            script="sync_kaspi_orders.py",
            args=["--all", "--since", api_since],
            required=not args.skip_api_sync,
        ),
        PipelineStep(
            name="2a2. Validate Kaspi Orders Sync Freshness",
            script="validate_kaspi_order_sync_freshness.py",
            required=True,
        ),
        PipelineStep(
            name="2a3. Export On-Delivery Orders (econ)",
            script="export_on_delivery_with_econ.py",
            args=[
                "--days",
                os.environ.get("KASPI_ON_DELIVERY_LOOKBACK_DAYS")
                or os.environ.get("KASPI_LOOKBACK_DAYS_LONG")
                or "14",
            ],
            required=not args.skip_api_sync,
        ),
        PipelineStep(
            name="2b. Backfill Order Sizes (Archive)",
            script="backfill_kaspi_order_sizes.py",
            args=["--cutoff-date", cutoff_date.isoformat()],
            required=True,
        ),
        PipelineStep(
            name="2b2. Translate Orders to Cashflow",
            script="translate_orders_to_cashflow_events.py",
            args=["--since", api_since, "--until", cutoff_date.isoformat(), "--apply"],
            required=True,
            skip_on_dry_run=True,
        ),
        PipelineStep(
            name="2c. Sync PO Arrivals to Ledger (auto)",
            script="sync_po_arrivals_to_ledger.py",
            args=["--snapshot-date", cutoff_date.isoformat(), "--apply"],
            required=True,
            skip_on_dry_run=True,
        ),
        PipelineStep(
            name="2d. Clamp Negative Ledger (auto)",
            script="clamp_negative_ledger.py",
            args=["--snapshot-date", cutoff_date.isoformat(), "--apply", "--force"],
            required=True,
            skip_on_dry_run=True,
        ),
        PipelineStep(
            name="2e. Rebuild Inventory Snapshot (auto)",
            script="rebuild_snapshot.py",
            args=["--date", cutoff_date.isoformat(), "--mode", "auto"],
            required=True,
            skip_on_dry_run=True
        ),
    ]

    if args.auto_assign_sizes:
        size_args = ["--auto"]
        if args.size_store:
            size_args.extend(["--store", args.size_store])
        if args.dry_run:
            size_args.append("--dry-run")
        steps.insert(
            4,
            PipelineStep(
                name="2b. Auto-Assign Sizes (DB-first)",
                script="assign_sizes.py",
                args=size_args,
                required=True,
            ),
        )

    if args.po4_inbound:
        steps.append(
            PipelineStep(
                name="2d. Import PO-4 inbound",
                script="import_po4_inbound.py",
                args=[str(args.po4_inbound)],
                required=True,
            )
        )

    snapshot_z_path = PROJECT_ROOT / "excel" / "Inventory_Core_V18.1_V2.xlsx"
    snapshot_z_required = snapshot_z_path.exists()
    if not snapshot_z_required:
        print("Note: Snapshot_Z workbook missing; skipping validate_snapshot_vs_snapshot_z (DB is source of truth).")

    if snapshot_z_required:
        steps.append(
            PipelineStep(
                name="2f. Validate Snapshot vs Snapshot_Z",
                script="validate_snapshot_vs_snapshot_z.py",
                required=True
            )
        )

    steps.extend([
        PipelineStep(
            name="2g. Validate Day Complete",
            script="validate_day_complete.py",
            args=["--cutoff-date", cutoff_date.isoformat()],
            required=False
        ),
        PipelineStep(
            name="3. Generate PO Dashboard Data",
            script="generate_po_dashboard_data.py",
            required=True
        ),
        PipelineStep(
            name="4. Smoke Test Dashboard",
            script="smoke_test_dashboard.py",
            args=["--skip-generate"],  # Already generated in step 3
            required=True
        ),
        PipelineStep(
            name="5. Update PO Dashboard",
            script="update_po_dashboard.py",
            required=True
        ),
        PipelineStep(
            name="5a. Update Cashflow Dashboard",
            script="update_cashflow_dashboard.py",
            args=["--rebuild"],
            required=True
        ),
        PipelineStep(
            name="5a2. Cashflow PO Preflight",
            script="cashflow_preflight_po.py",
            args=(
                ["--override", "--reason", os.environ["CASHFLOW_PREFLIGHT_OVERRIDE_REASON"]]
                if os.environ.get("CASHFLOW_PREFLIGHT_OVERRIDE_REASON")
                else []
            ),
            required=True,
        ),
        PipelineStep(
            name="5b. Validate Inventory Cost Drift",
            script="validate_inventory_cost_drift.py",
            required=True
        ),
        PipelineStep(
            name="6. Audit Dashboard Output",
            script="audit_dashboard_output.py",
            required=True
        ),
        PipelineStep(
            name="7. Generate Shadow Scorecard",
            script="generate_shadow_scorecard.py",
            required=True  # Part 5: Always generate scorecard
        ),
    ])

    # Filter out skipped steps
    skip_scripts = []
    if args.skip_workbook_sync:
        skip_scripts.append("sync_truth_workbook_to_db.py")
        print("Note: DB is source of truth; skipping workbook sync")
    if args.skip_sync:
        skip_scripts.append("sync_crm_to_db.py")
        print("Note: Skipping CRM sync step")
    if args.skip_api_sync:
        skip_scripts.append("sync_kaspi_orders.py")
        print("Note: Skipping Kaspi API sync step")
    if args.skip_day_complete:
        skip_scripts.append("validate_day_complete.py")
        print("Note: Skipping day-complete validation")
    if skip_scripts:
        steps = [s for s in steps if s.script not in skip_scripts]
        print()

    # Part 5: Track run with RunTracker
    tracker = RunTracker(
        run_type="END_OF_DAY",
        db_path=DB_PATH,
        triggered_by="CRON" if os.environ.get("LAUNCHED_BY_LAUNCHD") else "MANUAL",
        environment=os.environ.get("ENVIRONMENT", "PRODUCTION")
    )
    tracker.start()

    # Run each step
    all_success = True
    scorecard_path = None  # Track scorecard output for Telegram

    for step in steps:
        print(f"[{step.name}]")
        tracker.start_step(step.name.lower().replace(" ", "_").replace(".", ""))

        success = run_step(step, dry_run=args.dry_run, verbose=args.verbose)

        if success:
            print(f"  OK ({step.duration_s:.1f}s)")
            tracker.complete_step()

            # Track scorecard output path
            if step.script == "generate_shadow_scorecard.py":
                scorecard_path = EXPORTS_DIR / f"shadow_scorecard_{date.today().isoformat()}.csv"
                if scorecard_path.exists():
                    tracker.add_output_file(str(scorecard_path))
        else:
            print(f"  FAILED: {step.error}")
            tracker.fail_step(step.error or "Unknown error")
            all_success = False

        if step.script == "validate_day_complete.py":
            if success:
                os.environ["AB_DAY_COMPLETE"] = "1"
            else:
                os.environ["AB_DAY_COMPLETE"] = "0"
                print("PROVISIONAL: sizes pending; exports blocked.")

            if step.required and not args.continue_on_error:
                print("\nPipeline aborted due to required step failure.")
                print("Use --continue-on-error to proceed anyway.")
                break

        print()

    # Verify outputs
    print("-" * 70)
    print("OUTPUT VERIFICATION")
    print("-" * 70)

    if args.dry_run:
        print("Skipped (dry-run mode)")
    else:
        issues = verify_outputs()
        if issues:
            print("Issues found:")
            for issue in issues:
                print(f"  - {issue}")
            all_success = False
        else:
            print("All expected outputs present and fresh")

    # Add expected outputs to tracker
    for path in EXPECTED_OUTPUTS:
        if path.exists():
            tracker.add_output_file(str(path))

    # Summary
    end_time = datetime.now()
    duration = (end_time - start_time).total_seconds()

    print()
    print("=" * 70)
    print("SUMMARY")
    print("=" * 70)
    print(f"Finished: {end_time.isoformat()}")
    print(f"Duration: {duration:.1f}s")
    print(f"Run ID: #{tracker.run_id}")

    # Step summary
    print("\nStep Results:")
    for step in steps:
        status = "OK" if step.success else "FAILED"
        print(f"  {step.name}: {status} ({step.duration_s:.1f}s)")
        if step.error:
            print(f"    Error: {step.error}")

    print()

    # Part 5: Finalize tracker and send Telegram alert
    if all_success:
        tracker.success()
        print("STATUS: SUCCESS")
        print()
        print("Expected outputs:")
        for path in EXPECTED_OUTPUTS:
            print(f"  - {path}")
        if scorecard_path and scorecard_path.exists():
            print(f"  - {scorecard_path}")

        # Send enhanced Shadow Mode digest with scorecard metrics (Part 5)
        print("\nSending Shadow Mode digest to Telegram...")
        try:
            summary = tracker.to_summary()
            digest_sent = send_shadow_mode_digest(
                run_id=tracker.run_id,
                duration_seconds=summary["duration_seconds"],
                db_path=str(DB_PATH),
            )
            if digest_sent:
                print("  Telegram digest sent successfully")
        except Exception as e:
            print(f"  Warning: Failed to send Telegram: {e}")

        return 0
    else:
        tracker.fail("; ".join(s.error for s in steps if s.error))
        print("STATUS: FAILED")

        # Send Telegram failure alert
        print("\nSending Telegram failure alert...")
        try:
            alert_sent = alert_from_run_tracker(tracker)
            if alert_sent:
                print("  Telegram alert sent successfully")
        except Exception as e:
            print(f"  Warning: Failed to send Telegram: {e}")

        return 1


if __name__ == "__main__":
    exit_code = main()
    if exit_code is not None:
        sys.exit(exit_code)
