#!/usr/bin/env python3
"""Run the June 15 Phase 2 production repair sequence under one guardrail.

Default mode writes only a command plan. Apply mode is intentionally strict:
daily ops must already be paused, production DB SHA is captured before each
writer, and every underlying writer still requires its own env gate.
"""

from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
from typing import Any, Callable


PROJECT_ROOT = Path(__file__).resolve().parent.parent
PYTHON = PROJECT_ROOT / ".venv" / "bin" / "python"
DEFAULT_DB = PROJECT_ROOT / "db" / "app.db"
DEFAULT_CRM = PROJECT_ROOT / "excel_ui" / "SALES_KSP_CRM_V3.xlsx"
DEFAULT_SHEET = "SALES_KSP_CRM_1"
DEFAULT_BI_OUTPUT_DIR = PROJECT_ROOT / "config" / "business_insides"
ENV_GATE = "ENABLE_PHASE2_JUNE15_PRODUCTION_APPLY"
PRE_SHA_TOKEN = "{PRE_SHA}"


@dataclass(frozen=True)
class StepSpec:
    name: str
    command: list[str]
    output_path: str
    env: dict[str, str]
    needs_pre_sha: bool = False
    assert_daily_ops_paused_report: bool = False


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _rel(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(PROJECT_ROOT))
    except ValueError:
        return str(path)


def _cmd(*parts: object) -> list[str]:
    return [str(part) for part in parts]


def build_step_specs(
    *,
    run_root: Path,
    backup_root: Path,
    db_path: Path = DEFAULT_DB,
    crm_path: Path = DEFAULT_CRM,
    sheet_name: str = DEFAULT_SHEET,
    as_of: str = "2026-06-15",
    start_date: str = "2026-06-14",
    end_date: str = "2026-06-15",
    bi_output_dir: Path = DEFAULT_BI_OUTPUT_DIR,
) -> list[StepSpec]:
    """Return the exact ordered production-apply plan.

    PRE_SHA_TOKEN is replaced at execution time immediately before each
    SHA-gated writer, after previous writers have completed.
    """
    run_root = Path(run_root)
    backup_root = Path(backup_root)
    db = _rel(Path(db_path))
    crm = _rel(Path(crm_path))
    bi_output = _rel(Path(bi_output_dir))
    return [
        StepSpec(
            name="verify_daily_ops_paused",
            command=_cmd(
                PYTHON,
                "scripts/manage_business_automation.py",
                "verify",
                "--scope",
                "daily-ops",
                "--expect",
                "paused",
                "--json",
                "--output-json",
                run_root / "verify_daily_ops_paused_before_apply.json",
            ),
            output_path=str(run_root / "verify_daily_ops_paused_before_apply.stdout.json"),
            env={},
            assert_daily_ops_paused_report=True,
        ),
        StepSpec(
            name="check_local_app_db_before",
            command=_cmd(PYTHON, "scripts/check_local_app_db.py", "--db-path", db),
            output_path=str(run_root / "check_local_app_db_before.txt"),
            env={},
        ),
        StepSpec(
            name="reconcile_on_delivery_settlement",
            command=_cmd(
                PYTHON,
                "scripts/reconcile_on_delivery_settlement.py",
                "--db",
                db,
                "--until",
                end_date,
                "--apply",
                "--expected-pre-sha256",
                PRE_SHA_TOKEN,
                "--backup-dir",
                backup_root,
                "--run-id",
                "june15_phase2_production_settle_apply",
            ),
            output_path=str(run_root / "reconcile_on_delivery_settlement_prod_apply.txt"),
            env={"ENABLE_CASHFLOW_WRITE": "1", "ENABLE_CASHFLOW_PROD_WRITE": "1"},
            needs_pre_sha=True,
        ),
        StepSpec(
            name="translate_on_delivery_cashflow",
            command=_cmd(
                PYTHON,
                "scripts/translate_orders_to_cashflow_events.py",
                "--db",
                db,
                "--since",
                start_date,
                "--until",
                end_date,
                "--only-cashflow-status",
                "ON_DELIVERY",
                "--allow-missing",
                "--apply",
                "--expected-pre-sha256",
                PRE_SHA_TOKEN,
                "--backup-dir",
                backup_root,
                "--run-id",
                "june15_phase2_production_on_delivery_apply",
                "--output-path",
                run_root / "translate_on_delivery_prod_apply_report.txt",
            ),
            output_path=str(run_root / "translate_on_delivery_prod_apply_stdout.txt"),
            env={"ENABLE_CASHFLOW_WRITE": "1", "ENABLE_CASHFLOW_PROD_WRITE": "1"},
            needs_pre_sha=True,
        ),
        StepSpec(
            name="rebuild_cashflow_calendar",
            command=_cmd(
                PYTHON,
                "scripts/rebuild_cashflow_calendar.py",
                "--db",
                db,
                "--start-date",
                start_date,
                "--end-date",
                end_date,
                "--apply",
                "--expected-pre-sha256",
                PRE_SHA_TOKEN,
                "--backup-dir",
                backup_root,
                "--run-id",
                "june15_phase2_production_calendar_apply",
            ),
            output_path=str(run_root / "rebuild_cashflow_calendar_prod_apply.txt"),
            env={"ENABLE_CASHFLOW_WRITE": "1", "ENABLE_CASHFLOW_PROD_WRITE": "1"},
            needs_pre_sha=True,
        ),
        StepSpec(
            name="rebuild_sales_fact_v2",
            command=_cmd(
                PYTHON,
                "scripts/rebuild_sales_fact_v2_from_kaspi_entries.py",
                "--db",
                db,
                "--as-of",
                as_of,
                "--start-date",
                start_date,
                "--strict",
                "--apply",
                "--output-root",
                run_root / "sales_fact_v2_prod_apply",
                "--backup-root",
                backup_root,
            ),
            output_path=str(run_root / "sales_fact_v2_prod_apply_stdout.txt"),
            env={"ENABLE_SALES_FACT_V2_REBUILD_APPLY": "1"},
        ),
        StepSpec(
            name="apply_fact_sales_derived_replay",
            command=_cmd(
                PYTHON,
                "scripts/apply_fact_sales_derived_replay.py",
                "--db-path",
                db,
                "--crm-path",
                crm,
                "--sheet",
                sheet_name,
                "--output-dir",
                run_root / "fact_sales_replay_prod_apply",
                "--backup-dir",
                backup_root,
                "--from-date",
                start_date,
                "--to-date",
                end_date,
                "--as-of",
                as_of,
                "--expected-pre-sha256",
                PRE_SHA_TOKEN,
                "--apply",
            ),
            output_path=str(run_root / "fact_sales_replay_prod_apply_stdout.json"),
            env={"ENABLE_FACT_SALES_DERIVED_REPLAY_WRITE": "1"},
            needs_pre_sha=True,
        ),
        StepSpec(
            name="generate_business_insides",
            command=_cmd(
                PYTHON,
                "scripts/generate_business_insides.py",
                "--db",
                db,
                "--as-of",
                as_of,
                "--output-dir",
                bi_output,
                "--strict",
            ),
            output_path=str(run_root / "generate_business_insides_prod_stdout.txt"),
            env={},
        ),
        StepSpec(
            name="validate_on_delivery_freeze",
            command=_cmd(PYTHON, "scripts/validate_on_delivery_freeze.py", "--db", db, "--until", end_date),
            output_path=str(run_root / "validate_on_delivery_freeze_prod_after.txt"),
            env={},
        ),
        StepSpec(
            name="validate_cashflow_invariants",
            command=_cmd(PYTHON, "scripts/validate_cashflow_invariants.py", "--db", db),
            output_path=str(run_root / "validate_cashflow_invariants_prod_after.txt"),
            env={},
        ),
        StepSpec(
            name="validate_data_completeness",
            command=_cmd(PYTHON, "scripts/validate_data_completeness.py", "--db-path", db, "--as-of", as_of),
            output_path=str(run_root / "validate_data_completeness_prod_after.txt"),
            env={},
        ),
        StepSpec(
            name="validate_profit_publication_integrity",
            command=_cmd(
                PYTHON,
                "scripts/validate_profit_publication_integrity.py",
                "--db",
                db,
                "--as-of",
                as_of,
                "--business-insides",
                Path(bi_output) / f"BUSINESS_INSIDES_{as_of}.md",
            ),
            output_path=str(run_root / "validate_profit_publication_integrity_prod_after.txt"),
            env={},
        ),
        StepSpec(
            name="validate_params_strict",
            command=_cmd(
                PYTHON,
                "scripts/validate_params.py",
                "--strict",
                "--db",
                db,
                "--as-of",
                as_of,
                "--business-insides-output-dir",
                bi_output,
                "--json",
            ),
            output_path=str(run_root / "validate_params_prod_after.json"),
            env={},
        ),
        StepSpec(
            name="check_local_app_db_after",
            command=_cmd(PYTHON, "scripts/check_local_app_db.py", "--db-path", db),
            output_path=str(run_root / "check_local_app_db_after.txt"),
            env={},
        ),
    ]


def write_plan(path: Path, steps: list[StepSpec], *, db_path: Path, apply: bool) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema_version": 1,
        "apply": bool(apply),
        "env_gate": ENV_GATE,
        "db_path": str(db_path),
        "steps": [asdict(step) for step in steps],
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _run_step(
    step: StepSpec,
    *,
    db_path: Path,
    runner: Callable[..., subprocess.CompletedProcess[str]],
    environ: dict[str, str],
) -> dict[str, Any]:
    command = list(step.command)
    pre_sha: str | None = None
    if step.needs_pre_sha:
        pre_sha = _sha256_file(db_path)
        command = [pre_sha if part == PRE_SHA_TOKEN else part for part in command]

    output_path = Path(step.output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    env = dict(environ)
    env.update(step.env)
    with output_path.open("w", encoding="utf-8") as stdout:
        completed = runner(
            command,
            cwd=str(PROJECT_ROOT),
            env=env,
            stdout=stdout,
            stderr=subprocess.STDOUT,
            text=True,
            check=False,
        )
    if completed.returncode != 0:
        raise RuntimeError(f"{step.name} failed with rc={completed.returncode}; see {output_path}")

    if step.assert_daily_ops_paused_report:
        report_path = PROJECT_ROOT / "verify_daily_ops_paused_before_apply.json"
        for idx, value in enumerate(command):
            if value == "--output-json" and idx + 1 < len(command):
                report_path = (PROJECT_ROOT / command[idx + 1]).resolve()
                break
        report = json.loads(report_path.read_text(encoding="utf-8"))
        status = report.get("status") or report
        if not report.get("ok", False):
            raise RuntimeError("daily ops paused verification returned ok=false")
        if int(status.get("loaded_count") or 0) != 0:
            raise RuntimeError(f"daily ops are not paused: loaded_count={status.get('loaded_count')}")
        if not bool(report.get("quiet_protected_surfaces", status.get("quiet_protected_surfaces", False))):
            raise RuntimeError("protected surfaces are not quiet before production apply")

    return {
        "name": step.name,
        "returncode": completed.returncode,
        "output_path": str(output_path),
        "pre_sha256": pre_sha,
    }


def run_apply(
    *,
    run_root: Path,
    backup_root: Path,
    db_path: Path,
    steps: list[StepSpec],
    runner: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
    environ: dict[str, str] | None = None,
) -> dict[str, Any]:
    env = dict(os.environ if environ is None else environ)
    if env.get(ENV_GATE) != "1":
        raise RuntimeError(f"{ENV_GATE}=1 is required with --apply")
    if db_path.resolve() != DEFAULT_DB.resolve():
        raise RuntimeError("this wrapper is for production db/app.db only")

    run_root.mkdir(parents=True, exist_ok=True)
    backup_root.mkdir(parents=True, exist_ok=True)
    before_sha = _sha256_file(db_path)
    executed: list[dict[str, Any]] = []
    for step in steps:
        executed.append(_run_step(step, db_path=db_path, runner=runner, environ=env))
    after_sha = _sha256_file(db_path)
    summary = {
        "status": "APPLIED",
        "db_path": str(db_path),
        "source_db_sha256_before": before_sha,
        "source_db_sha256_after": after_sha,
        "source_db_sha256_changed": before_sha != after_sha,
        "steps": executed,
    }
    (run_root / "production_apply_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    (run_root / "prod_db_sha_after.txt").write_text(f"{after_sha}  {db_path}\n", encoding="utf-8")
    return summary


def main(
    argv: list[str] | None = None,
    *,
    runner: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
    environ: dict[str, str] | None = None,
) -> int:
    parser = argparse.ArgumentParser(description="Run June 15 Phase 2 production repair sequence")
    parser.add_argument("--run-root", type=Path, required=True)
    parser.add_argument("--backup-root", type=Path, default=None)
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument("--crm-path", type=Path, default=DEFAULT_CRM)
    parser.add_argument("--sheet", default=DEFAULT_SHEET)
    parser.add_argument("--business-insides-output-dir", type=Path, default=DEFAULT_BI_OUTPUT_DIR)
    parser.add_argument("--as-of", default="2026-06-15")
    parser.add_argument("--start-date", default="2026-06-14")
    parser.add_argument("--end-date", default="2026-06-15")
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args(argv)

    run_root = args.run_root
    backup_root = args.backup_root or run_root / "backups"
    steps = build_step_specs(
        run_root=run_root,
        backup_root=backup_root,
        db_path=args.db,
        crm_path=args.crm_path,
        sheet_name=args.sheet,
        as_of=args.as_of,
        start_date=args.start_date,
        end_date=args.end_date,
        bi_output_dir=args.business_insides_output_dir,
    )
    write_plan(run_root / "production_apply_plan.json", steps, db_path=args.db, apply=args.apply)
    if not args.apply:
        print(f"PLAN_ONLY: wrote {run_root / 'production_apply_plan.json'}")
        return 0

    try:
        summary = run_apply(
            run_root=run_root,
            backup_root=backup_root,
            db_path=args.db,
            steps=steps,
            runner=runner,
            environ=environ,
        )
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
