#!/usr/bin/env python3
"""One-command fail-closed preflight for copied-temp MVOS waves."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess
import sys
from typing import Any

from check_validation_disk_runway import build_runway_report
from cleanup_validation_db_artifacts import CleanupPlanError, build_cleanup_plan


PROJECT_ROOT = Path(__file__).resolve().parent.parent


def _repo_path(repo: Path, raw: str) -> Path:
    path = Path(raw)
    if not path.is_absolute():
        path = repo / path
    return path.resolve()


def _run_command(command: list[str], repo: Path) -> dict[str, Any]:
    completed = subprocess.run(
        command,
        cwd=repo,
        capture_output=True,
        text=True,
        check=False,
    )
    return {
        "command": command,
        "ok": completed.returncode == 0,
        "returncode": completed.returncode,
        "stdout_preview": completed.stdout[:1000],
        "stderr_preview": completed.stderr[:1000],
    }


def build_preflight_report(
    *,
    repo: Path,
    run_root: Path,
    min_free_gib: float,
    cleanup_manifest: Path | None,
    skip_db_guard: bool,
    skip_source_contract_registry: bool,
) -> dict[str, Any]:
    checks: list[dict[str, Any]] = []

    disk = build_runway_report(run_root, min_free_gib)
    checks.append(
        {
            "id": "validation_disk_runway",
            "ok": bool(disk["ok"]),
            "status": disk["status"],
            "details": disk,
        }
    )

    if cleanup_manifest is not None:
        try:
            plan = build_cleanup_plan(repo, cleanup_manifest)
            cleanup_ok = plan["eligible_count"] > 0 and plan["blocked_count"] == 0
            checks.append(
                {
                    "id": "cleanup_manifest_dry_run",
                    "ok": cleanup_ok,
                    "status": "PASS" if cleanup_ok else "FAIL_CLEANUP_MANIFEST",
                    "details": {
                        "manifest": str(cleanup_manifest),
                        "eligible_count": plan["eligible_count"],
                        "blocked_count": plan["blocked_count"],
                        "eligible_bytes": plan["eligible_bytes"],
                        "eligible_mib": round(plan["eligible_bytes"] / 1048576, 1),
                        "blocked": plan["blocked"],
                    },
                }
            )
        except CleanupPlanError as exc:
            checks.append(
                {
                    "id": "cleanup_manifest_dry_run",
                    "ok": False,
                    "status": "FAIL_CLEANUP_MANIFEST_ERROR",
                    "details": {"error": str(exc), "manifest": str(cleanup_manifest)},
                }
            )

    if skip_db_guard:
        checks.append({"id": "db_guard", "ok": True, "status": "SKIPPED", "details": {}})
    else:
        command_report = _run_command(["bash", "scripts/check_no_db_tracked.sh"], repo)
        checks.append(
            {
                "id": "db_guard",
                "ok": command_report["ok"],
                "status": "PASS" if command_report["ok"] else "FAIL_DB_GUARD",
                "details": command_report,
            }
        )

    if skip_source_contract_registry:
        checks.append(
            {
                "id": "source_contract_registry",
                "ok": True,
                "status": "SKIPPED",
                "details": {},
            }
        )
    else:
        command_report = _run_command(
            [sys.executable, "scripts/validate_mvos_source_contract_registry.py", "--strict"],
            repo,
        )
        checks.append(
            {
                "id": "source_contract_registry",
                "ok": command_report["ok"],
                "status": "PASS" if command_report["ok"] else "FAIL_SOURCE_CONTRACT_REGISTRY",
                "details": command_report,
            }
        )

    ok = all(bool(check["ok"]) for check in checks)
    return {
        "ok": ok,
        "status": "PASS" if ok else "FAIL_PRECHECK",
        "repo": str(repo),
        "run_root": str(run_root),
        "checks": checks,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Fail-closed preflight before copied-temp DB validation waves"
    )
    parser.add_argument("--repo", default=str(PROJECT_ROOT))
    parser.add_argument(
        "--run-root",
        default=None,
        help="Existing directory where copied-temp DB artifacts will be written; defaults to repo",
    )
    parser.add_argument("--min-free-gib", type=float, default=3.0)
    parser.add_argument("--cleanup-manifest", default=None)
    parser.add_argument("--skip-db-guard", action="store_true")
    parser.add_argument("--skip-source-contract-registry", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    repo = Path(args.repo).resolve()
    run_root = _repo_path(repo, args.run_root) if args.run_root else repo
    cleanup_manifest = (
        _repo_path(repo, args.cleanup_manifest) if args.cleanup_manifest else None
    )
    report = build_preflight_report(
        repo=repo,
        run_root=run_root,
        min_free_gib=args.min_free_gib,
        cleanup_manifest=cleanup_manifest,
        skip_db_guard=args.skip_db_guard,
        skip_source_contract_registry=args.skip_source_contract_registry,
    )
    if args.json:
        print(json.dumps(report, indent=2, ensure_ascii=False))
    elif report["ok"]:
        print("COPIED_TEMP_WAVE_PREFLIGHT PASS")
    else:
        print("COPIED_TEMP_WAVE_PREFLIGHT FAIL_PRECHECK")
        for check in report["checks"]:
            print(f"{check['id']}={check['status']}")
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
