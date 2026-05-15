#!/usr/bin/env python3
"""Safe resume controller for the Agent750 -> Agent751/752/753 gate."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
GREEN_TOKEN = "GREEN_TO_LAUNCH_AGENT751_752_753_VALIDATE_ONLY_WAVE"
DB_BOUNDARY_ERRORS = {
    "production_db_sha_mismatch",
    "protected_workbook_sha_mismatch",
    "production_db_missing",
    "protected_workbook_missing",
}
RUN_DOC_ROOT = REPO_ROOT / "docs" / "parallel_runs" / "2026-05-06_codecaptain_proscope_red_recovery"
WAITING_POINTER = RUN_DOC_ROOT / "WAITING_FOR_EXTERNAL_REVIEW_AGENT750.md"

sys.path.insert(0, str(REPO_ROOT))

from scripts.launch_agent751_753_after_agent750 import _validate_reuse_panes  # noqa: E402
from scripts.report_agent750_next_action import (  # noqa: E402
    current_answer_search_info,
    current_review_pack_info,
    latest_completion_audit,
    latest_stopline_triage,
)


def run_command(cmd: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        cmd,
        cwd=REPO_ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )


def _json_from_result(result: subprocess.CompletedProcess[str]) -> tuple[dict[str, Any], list[str]]:
    try:
        payload = json.loads(result.stdout or "{}")
    except json.JSONDecodeError:
        return {}, ["command_output_not_json"]
    if not isinstance(payload, dict):
        return {}, ["command_output_not_object"]
    return payload, []


def _step_payload(name: str, cmd: list[str], result: subprocess.CompletedProcess[str]) -> dict[str, Any]:
    payload, parse_errors = _json_from_result(result)
    return {
        "name": name,
        "command": cmd,
        "returncode": result.returncode,
        "payload": payload,
        "parse_errors": parse_errors,
        "stderr": result.stderr,
    }


def _print(payload: dict[str, Any]) -> None:
    print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))


def _latest_db_boundary_drift_triage() -> Path | None:
    triage_files = sorted(RUN_DOC_ROOT.glob("DB_BOUNDARY_DRIFT_TRIAGE_*.md"))
    return triage_files[-1] if triage_files else None


def _latest_db_boundary_supplemental_review_request() -> Path | None:
    supplement_files = sorted(RUN_DOC_ROOT.glob("CODECAPTAIN_DB_BOUNDARY_SUPPLEMENT_AGENT750_*.md"))
    return supplement_files[-1] if supplement_files else None


def _readiness_boundary_errors(readiness_payload: dict[str, Any]) -> list[str]:
    return sorted(set(readiness_payload.get("errors") or []) & DB_BOUNDARY_ERRORS)


def _blocked_metadata(readiness_payload: dict[str, Any]) -> dict[str, Any]:
    errors = set(readiness_payload.get("errors") or [])
    has_db_boundary_error = bool(errors & DB_BOUNDARY_ERRORS)
    db_boundary_drift_triage = _latest_db_boundary_drift_triage()
    db_boundary_supplemental_review = _latest_db_boundary_supplemental_review_request()
    db_boundary_metadata = {}
    completion_audit = latest_completion_audit()
    if completion_audit:
        db_boundary_metadata["latest_completion_audit"] = str(completion_audit)
    stopline_triage = latest_stopline_triage()
    if stopline_triage:
        db_boundary_metadata["latest_stopline_triage"] = str(stopline_triage)
    db_boundary_metadata["review_pack"] = current_review_pack_info()
    db_boundary_metadata["latest_answer_search"] = current_answer_search_info()
    db_boundary_metadata["db_sha256"] = readiness_payload.get("db_sha256")
    db_boundary_metadata["workbook_sha256"] = readiness_payload.get("workbook_sha256")
    db_boundary_metadata["expected_db_sha256"] = readiness_payload.get("expected_db_sha256")
    db_boundary_metadata["expected_workbook_sha256"] = readiness_payload.get(
        "expected_workbook_sha256"
    )
    db_boundary_metadata["db_sha256_matches_expected"] = readiness_payload.get(
        "db_sha256_matches_expected"
    )
    db_boundary_metadata["workbook_sha256_matches_expected"] = readiness_payload.get(
        "workbook_sha256_matches_expected"
    )
    if has_db_boundary_error and db_boundary_drift_triage:
        db_boundary_metadata["latest_db_boundary_drift_triage"] = str(db_boundary_drift_triage)
    if has_db_boundary_error and db_boundary_supplemental_review:
        db_boundary_metadata["latest_db_boundary_supplemental_review_request"] = str(
            db_boundary_supplemental_review
        )
    if "missing_codecaptain_answer_file" in errors:
        blocked_until = (
            "codecaptain_agent750_exact_green_answer_and_db_boundary_review"
            if has_db_boundary_error
            else "codecaptain_agent750_exact_green_answer"
        )
        return {
            "local_action_state": "EXTERNAL_INPUT_REQUIRED_NO_SAFE_LOCAL_ACTION",
            "blocked_until": blocked_until,
            "waiting_pointer": str(WAITING_POINTER),
            **db_boundary_metadata,
        }
    if has_db_boundary_error:
        return {
            "local_action_state": "LOCAL_DB_BOUNDARY_REVIEW_REQUIRED",
            "blocked_until": "current_production_db_boundary_review_resolved",
            "waiting_pointer": str(WAITING_POINTER),
            **db_boundary_metadata,
        }
    return {
        "local_action_state": "LOCAL_READINESS_REPAIR_REQUIRED",
        "blocked_until": "all_readiness_errors_resolved",
        "waiting_pointer": str(WAITING_POINTER),
    }


def _parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Resume safely after the Agent750 CodeCaptain answer arrives")
    p.add_argument("--source", help="Optional CodeCaptain answer Markdown file to validate/import first")
    p.add_argument("--apply-import", action="store_true", help="Actually import --source into the canonical Answer folder")
    p.add_argument("--replace", action="store_true", help="Pass --replace to the answer importer")
    p.add_argument("--reuse-panes", help="Optional explicit %%pane,%%pane,%%pane selection")
    p.add_argument("--launch", action="store_true", help="Actually invoke the guarded launcher after readiness passes")
    return p


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    steps: list[dict[str, Any]] = []

    argument_errors: list[str] = []
    if args.apply_import and not args.source:
        argument_errors.append("apply_import_requires_source")
    if args.replace and not args.source:
        argument_errors.append("replace_requires_source")
    if args.apply_import and args.launch:
        argument_errors.append("launch_requires_separate_run_after_apply_import")
    if argument_errors:
        _print(
            {
                "ok": False,
                "status": "INVALID_ARGUMENTS",
                "errors": argument_errors,
                "note": "--apply-import/--replace require --source; --launch must be a separate run after apply-import returns READY_FOR_GUARDED_LAUNCH.",
            }
        )
        return 2

    if args.source:
        import_cmd = [
            "python3",
            "scripts/ingest_agent750_codecaptain_answer.py",
            "--source",
            args.source,
        ]
        if args.replace:
            import_cmd.append("--replace")
        import_result = run_command(import_cmd)
        import_step = _step_payload("answer_import_dry_run", import_cmd, import_result)
        steps.append(import_step)
        import_payload = import_step["payload"]
        if import_result.returncode != 0 or import_step["parse_errors"] or not import_payload.get("ok"):
            _print(
                {
                    "ok": False,
                    "status": "IMPORT_BLOCKED",
                    "steps": steps,
                }
            )
            return 2
        if not args.apply_import:
            _print(
                {
                    "ok": False,
                    "status": "IMPORT_DRY_RUN_OK_NOT_APPLIED",
                    "next_command": [
                        "python3",
                        "scripts/resume_agent750_to_753.py",
                        "--source",
                        args.source,
                        "--apply-import",
                    ],
                    "steps": steps,
                }
            )
            return 2
        pre_import_readiness_cmd = ["python3", "scripts/check_agent750_launch_readiness.py"]
        pre_import_readiness_result = run_command(pre_import_readiness_cmd)
        pre_import_readiness_step = _step_payload(
            "pre_import_boundary_readiness",
            pre_import_readiness_cmd,
            pre_import_readiness_result,
        )
        steps.append(pre_import_readiness_step)
        pre_import_readiness_payload = pre_import_readiness_step["payload"]
        boundary_errors = _readiness_boundary_errors(pre_import_readiness_payload)
        if pre_import_readiness_step["parse_errors"] or boundary_errors:
            _print(
                {
                    "ok": False,
                    "status": "IMPORT_BLOCKED_BY_DB_BOUNDARY_REVIEW",
                    "errors": boundary_errors or pre_import_readiness_step["parse_errors"],
                    **_blocked_metadata(pre_import_readiness_payload),
                    "readiness": pre_import_readiness_payload,
                    "steps": steps,
                }
            )
            return 2
        import_apply_cmd = [
            "python3",
            "scripts/ingest_agent750_codecaptain_answer.py",
            "--source",
            args.source,
            "--apply",
        ]
        if args.replace:
            import_apply_cmd.append("--replace")
        import_apply_result = run_command(import_apply_cmd)
        import_apply_step = _step_payload(
            "answer_import_apply",
            import_apply_cmd,
            import_apply_result,
        )
        steps.append(import_apply_step)
        import_apply_payload = import_apply_step["payload"]
        if (
            import_apply_result.returncode != 0
            or import_apply_step["parse_errors"]
            or not import_apply_payload.get("ok")
        ):
            _print(
                {
                    "ok": False,
                    "status": "IMPORT_BLOCKED",
                    "steps": steps,
                }
            )
            return 2

    readiness_cmd = ["python3", "scripts/check_agent750_launch_readiness.py"]
    readiness_result = run_command(readiness_cmd)
    readiness_step = _step_payload("readiness", readiness_cmd, readiness_result)
    steps.append(readiness_step)
    readiness_payload = readiness_step["payload"]
    if readiness_result.returncode != 0 or readiness_step["parse_errors"] or not readiness_payload.get("ok"):
        _print(
            {
                "ok": False,
                "status": "BLOCKED_BY_READINESS",
                **_blocked_metadata(readiness_payload),
                "readiness": readiness_payload,
                "steps": steps,
            }
        )
        return 2
    if readiness_payload.get("decision_token") != GREEN_TOKEN:
        _print(
            {
                "ok": False,
                "status": "BLOCKED_BY_DECISION_TOKEN",
                "expected_decision_token": GREEN_TOKEN,
                "actual_decision_token": readiness_payload.get("decision_token"),
                "readiness": readiness_payload,
                "steps": steps,
            }
        )
        return 2

    reuse_panes = args.reuse_panes
    pane_payload: dict[str, Any] | None = None
    if not reuse_panes:
        pane_cmd = ["python3", "scripts/list_agent751_753_candidate_panes.py", "--json-only"]
        pane_result = run_command(pane_cmd)
        pane_step = _step_payload("pane_candidates", pane_cmd, pane_result)
        steps.append(pane_step)
        pane_payload = pane_step["payload"]
        if pane_result.returncode != 0 or pane_step["parse_errors"] or not pane_payload.get("ready_for_launch_selection"):
            _print(
                {
                    "ok": False,
                    "status": "BLOCKED_BY_PANE_SELECTION",
                    "local_action_state": "LOCAL_PANE_SELECTION_REQUIRED",
                    "blocked_until": "three_reusable_codex_panes_selected",
                    "errors": pane_payload.get("errors") or ["pane_selection_not_ready"],
                    "waiting_pointer": str(WAITING_POINTER),
                    "readiness": pane_payload.get("readiness") or readiness_payload,
                    "review_pack": pane_payload.get("review_pack") or current_review_pack_info(),
                    "pane_candidates": pane_payload,
                    "steps": steps,
                }
            )
            return 2
        reuse_panes = str(pane_payload.get("suggested_reuse_panes") or "")

    parsed_reuse_panes, reuse_pane_errors = _validate_reuse_panes(reuse_panes)
    if reuse_pane_errors:
        _print(
            {
                "ok": False,
                "status": "BLOCKED_BY_REUSE_PANES",
                "errors": reuse_pane_errors,
                "reuse_panes": reuse_panes,
                "reuse_pane_count": len(parsed_reuse_panes),
                "readiness": readiness_payload,
                "pane_candidates": pane_payload,
                "steps": steps,
            }
        )
        return 2

    launch_cmd = [
        "python3",
        "scripts/launch_agent751_753_after_agent750.py",
        "--reuse-panes",
        reuse_panes,
    ]
    launch_preflight_cmd = [*launch_cmd, "--dry-run"]
    launch_preflight_result = run_command(launch_preflight_cmd)
    launch_preflight_step = _step_payload(
        "guarded_launch_dry_run_preflight",
        launch_preflight_cmd,
        launch_preflight_result,
    )
    steps.append(launch_preflight_step)
    launch_preflight_payload = launch_preflight_step["payload"]
    if (
        launch_preflight_result.returncode != 0
        or launch_preflight_step["parse_errors"]
        or not launch_preflight_payload.get("ok")
    ):
        _print(
            {
                "ok": False,
                "status": "BLOCKED_BY_LAUNCH_PREFLIGHT",
                "launch_preflight": launch_preflight_payload,
                "steps": steps,
            }
        )
        return 2

    if not args.launch:
        _print(
            {
                "ok": True,
                "did_launch": False,
                "status": "READY_FOR_GUARDED_LAUNCH",
                "launch_command": launch_cmd,
                "next_resume_command": [
                    "python3",
                    "scripts/resume_agent750_to_753.py",
                    "--launch",
                ],
                "launch_preflight": launch_preflight_payload,
                "readiness": readiness_payload,
                "pane_candidates": pane_payload,
                "steps": steps,
                "note": "Dry-run controller only. Re-run with --launch to invoke the guarded monitor-only launcher.",
            }
        )
        return 0

    launch_result = run_command(launch_cmd)
    launch_step = _step_payload("guarded_launch", launch_cmd, launch_result)
    steps.append(launch_step)
    launch_payload = launch_step["payload"]
    launch_ok = (
        launch_result.returncode == 0
        and not launch_step["parse_errors"]
        and launch_payload.get("ok") is True
    )
    _print(
        {
            "ok": launch_ok,
            "status": "LAUNCH_COMMAND_COMPLETED" if launch_ok else "LAUNCH_COMMAND_FAILED",
            "launch": launch_payload,
            "steps": steps,
        }
    )
    return 0 if launch_ok else 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
