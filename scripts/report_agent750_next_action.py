#!/usr/bin/env python3
"""Report the safe next action for the Agent750 -> Agent751/752/753 gate."""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.check_agent750_launch_readiness import (  # noqa: E402
    DEFAULT_DB_SHA256,
    DEFAULT_WORKBOOK_SHA256,
    GREEN_TOKEN,
    REPO_ROOT,
    ReadinessResult,
    check_readiness,
    current_answer_search_info,
)
from scripts.agent750_review_pack_status import (  # noqa: E402
    review_pack_blocking_errors,
    review_pack_info_from_status,
)
from scripts.launch_agent751_753_after_agent750 import ANSWER_DIR, HANDOFF_ROOT, LIVE_REGISTRY  # noqa: E402


ORACLE_REVIEW_PACK = ANSWER_DIR.parent
CURRENT_STOPLINE_POINTER = (
    REPO_ROOT
    / "docs"
    / "parallel_runs"
    / "2026-05-06_codecaptain_proscope_red_recovery"
    / "CURRENT_AGENT750_STOPLINE.md"
)
RUN_DOC_ROOT = CURRENT_STOPLINE_POINTER.parent
WAITING_POINTER = RUN_DOC_ROOT / "WAITING_FOR_EXTERNAL_REVIEW_AGENT750.md"
CURRENT_GATE_STATUS_PATH = RUN_DOC_ROOT / "current_gate_status_agent750_waiting_codecaptain.json"
DB_BOUNDARY_ERRORS = {
    "production_db_sha_mismatch",
    "protected_workbook_sha_mismatch",
    "production_db_missing",
    "protected_workbook_missing",
}


def current_review_pack_info() -> dict:
    return review_pack_info_from_status(CURRENT_GATE_STATUS_PATH)


def latest_current_objective_audit() -> Path | None:
    audits = sorted(RUN_DOC_ROOT.glob("CURRENT_OBJECTIVE_AUDIT_AGENT750_BLOCKED_*.md"))
    return audits[-1] if audits else None


def latest_completion_audit() -> Path | None:
    audits = sorted(RUN_DOC_ROOT.glob("ACTIVE_OBJECTIVE_COMPLETION_AUDIT_*.md"))
    return audits[-1] if audits else None


def latest_stopline_triage() -> Path | None:
    triage_files = sorted(RUN_DOC_ROOT.glob("STOPLINE_TRIAGE_NEXT_BEST_STEP_AGENT750_*.md"))
    return triage_files[-1] if triage_files else None


def latest_db_boundary_drift_triage() -> Path | None:
    triage_files = sorted(RUN_DOC_ROOT.glob("DB_BOUNDARY_DRIFT_TRIAGE_*.md"))
    return triage_files[-1] if triage_files else None


def latest_db_boundary_supplemental_review_request() -> Path | None:
    supplement_files = sorted(RUN_DOC_ROOT.glob("CODECAPTAIN_DB_BOUNDARY_SUPPLEMENT_AGENT750_*.md"))
    return supplement_files[-1] if supplement_files else None


def build_next_action(readiness: ReadinessResult) -> dict:
    errors = set(readiness.errors)
    db_boundary_errors = sorted(errors & DB_BOUNDARY_ERRORS)
    completion_audit = latest_completion_audit()
    current_objective_audit = latest_current_objective_audit()
    stopline_triage = latest_stopline_triage()
    db_boundary_drift_triage = latest_db_boundary_drift_triage()
    db_boundary_supplemental_review = latest_db_boundary_supplemental_review_request()
    review_pack = current_review_pack_info()
    answer_search = current_answer_search_info()
    review_pack_errors = review_pack_blocking_errors(review_pack)
    if readiness.ok and readiness.decision_token == GREEN_TOKEN and review_pack_errors:
        status = "BLOCKED_BY_REVIEW_PACK"
        local_action_state = "LOCAL_REVIEW_PACK_REPAIR_REQUIRED"
        blocked_until = "agent750_review_pack_evidence_healthy"
        next_steps = [
            "Do not launch Agents751/752/753.",
            "Repair the current Agent750 review-pack status, optional ZIP, and validator-manifest evidence.",
            "Rerun python3 scripts/validate_agent750_review_pack.py --manifest-out docs/parallel_runs/2026-05-06_codecaptain_proscope_red_recovery/agent750_review_pack_manifest_20260510_024500.json --json-only.",
            "Rerun python3 scripts/report_agent750_next_action.py --json-only and require BLOCKED_BY_REVIEW_PACK to clear before selecting panes.",
        ]
    elif readiness.ok and readiness.decision_token == GREEN_TOKEN:
        status = "READY_FOR_GUARDED_AGENT751_752_753_LAUNCH"
        local_action_state = "READY_FOR_GUARDED_LOCAL_LAUNCH"
        blocked_until = None
        next_steps = [
            "Preferred: run python3 scripts/resume_agent750_to_753.py --launch so readiness, pane listing, and guarded launcher dry-run preflight all run in sequence.",
            "Optional manual pane review: run python3 scripts/list_agent751_753_candidate_panes.py --json-only, then pass exactly three unique %number Codex panes currently in ~/Docs/Autonomous_business.",
            "Manual fallback after pane review: run ./scripts/launch_agent751_753_after_agent750.py --reuse-panes <PANE_751>,<PANE_752>,<PANE_753>.",
            "Do not add --visibility-pane, including LIVE, do not use orchestrator_ping_mode=chat or receiver, and do not ask execution agents to manually ping any chat pane.",
        ]
    elif readiness.ok:
        status = "BLOCKED_BY_DECISION_TOKEN"
        local_action_state = "LOCAL_REVIEW_REQUIRED_BEFORE_LAUNCH"
        blocked_until = "codecaptain_agent750_exact_green_answer"
        next_steps = [
            "Do not launch Agents751/752/753.",
            f"Expected CodeCaptain decision token is exactly {GREEN_TOKEN}.",
            "Rerun ./scripts/check_agent750_launch_readiness.py and inspect the answer file before selecting panes.",
        ]
    elif "missing_codecaptain_answer_file" in errors:
        if db_boundary_errors:
            status = "WAITING_FOR_CODECAPTAIN_AGENT750_ANSWER_AND_DB_BOUNDARY_REVIEW"
            blocked_until = "codecaptain_agent750_exact_green_answer_and_db_boundary_review"
        else:
            status = "WAITING_FOR_CODECAPTAIN_AGENT750_ANSWER"
            blocked_until = "codecaptain_agent750_exact_green_answer"
        local_action_state = "EXTERNAL_INPUT_REQUIRED_NO_SAFE_LOCAL_ACTION"
        next_steps = [
            f"Start with the stable current stopline pointer: {CURRENT_STOPLINE_POINTER}",
            f"If no CodeCaptain answer exists yet, use the stable waiting pointer: {WAITING_POINTER}",
            f"Review the latest completion audit: {completion_audit}" if completion_audit else "Review the latest completion audit once it exists.",
            f"Review the current objective audit: {current_objective_audit}" if current_objective_audit else "Review the current objective audit once it exists.",
            f"Review the latest stopline triage / next best step: {stopline_triage}" if stopline_triage else "Review the latest stopline triage / next best step once it exists.",
            f"Send the Oracle review pack to CodeCaptain: {ORACLE_REVIEW_PACK}",
            f"Preferred upload ZIP: {review_pack.get('optional_upload_zip')} (SHA256 {review_pack.get('optional_upload_zip_sha256')})",
            f"ZIP manifest: {review_pack.get('optional_upload_zip_manifest')}",
            f"Validator manifest: {review_pack.get('latest_validator_manifest')}; prompt SHA256 {review_pack.get('prompt_sha256')}",
            f"Include the DB-boundary drift triage supplement: {db_boundary_drift_triage}" if db_boundary_errors and db_boundary_drift_triage else "If readiness reports a DB/workbook boundary mismatch, include the latest DB-boundary drift triage supplement.",
            f"Include the DB-boundary supplemental review request: {db_boundary_supplemental_review}" if db_boundary_errors and db_boundary_supplemental_review else "If readiness reports a DB/workbook boundary mismatch, include the latest DB-boundary supplemental review request.",
            "Save or import exactly one real CodeCaptain answer Markdown file into the canonical Answer/ folder.",
            "If readiness also reports production_db_sha_mismatch or protected_workbook_sha_mismatch, review the current DB/workbook boundary before importing or launching.",
            "Preferred dry-run resume: python3 scripts/resume_agent750_to_753.py --source /path/to/CodeCaptain_answer.md",
            "If the dry-run import returns ok=true: python3 scripts/resume_agent750_to_753.py --source /path/to/CodeCaptain_answer.md --apply-import",
            "If that returns READY_FOR_GUARDED_LAUNCH and you are ready to start the validate-only wave: python3 scripts/resume_agent750_to_753.py --launch",
            "Lower-level fallback remains: python3 scripts/ingest_agent750_codecaptain_answer.py --source /path/to/CodeCaptain_answer.md",
        ]
    elif db_boundary_errors:
        status = "BLOCKED_BY_DB_BOUNDARY_REVIEW"
        local_action_state = "LOCAL_DB_BOUNDARY_REVIEW_REQUIRED"
        blocked_until = "current_production_db_boundary_review_resolved"
        next_steps = [
            "Do not launch Agents751/752/753.",
            "Review the current production DB/workbook boundary against the Agent750 review pack boundary.",
            f"Use the latest DB-boundary drift triage supplement: {db_boundary_drift_triage}" if db_boundary_drift_triage else "Create or review the latest DB-boundary drift triage supplement.",
            f"Use the latest DB-boundary supplemental review request: {db_boundary_supplemental_review}" if db_boundary_supplemental_review else "Create or review the latest DB-boundary supplemental review request.",
            "Rerun python3 scripts/check_agent750_launch_readiness.py and require ok=true before selecting panes or launching.",
        ]
    elif "codecaptain_answer_requires_fix_before_launch" in errors:
        status = "BLOCKED_BY_CODECAPTAIN_YELLOW_FIX_REQUIRED"
        local_action_state = "LOCAL_REPAIR_REQUIRED_BEFORE_REVIEW"
        blocked_until = "codecaptain_agent750_yellow_findings_resolved"
        next_steps = [
            "Do not launch Agents751/752/753.",
            "Patch the Agent750 plan/starter prompts according to CodeCaptain's YELLOW findings.",
            "Repackage or resend to CodeCaptain before implementation.",
        ]
    elif "codecaptain_answer_red_stopline" in errors:
        status = "BLOCKED_BY_CODECAPTAIN_RED_STOPLINE"
        local_action_state = "LOCAL_TRIAGE_REQUIRED_BEFORE_REVIEW"
        blocked_until = "codecaptain_agent750_red_stopline_resolved"
        next_steps = [
            "Do not launch Agents751/752/753.",
            "Write a RED decision memo and triage the CodeCaptain blockers into root-cause lanes.",
        ]
    else:
        status = "BLOCKED_BY_READINESS_ERRORS"
        local_action_state = "LOCAL_READINESS_REPAIR_REQUIRED"
        blocked_until = "all_readiness_errors_resolved"
        next_steps = [
            "Do not launch Agents751/752/753.",
            "Resolve every readiness error exactly as reported before selecting panes or launching.",
        ]

    return {
        "status": status,
        "local_action_state": local_action_state,
        "blocked_until": blocked_until,
        "readiness_ok": readiness.ok,
        "errors": readiness.errors,
        "decision_token": readiness.decision_token,
        "answer_files": readiness.answer_files,
        "misplaced_answer_files": readiness.misplaced_answer_files,
        "unexpected_answer_files": readiness.unexpected_answer_files,
        "downstream_artifacts": readiness.downstream_artifacts,
        "db_sha256": readiness.db_sha256,
        "workbook_sha256": readiness.workbook_sha256,
        "expected_db_sha256": readiness.expected_db_sha256,
        "expected_workbook_sha256": readiness.expected_workbook_sha256,
        "db_sha256_matches_expected": readiness.db_sha256_matches_expected,
        "workbook_sha256_matches_expected": readiness.workbook_sha256_matches_expected,
        "proof_window_lock_exists": readiness.proof_window_lock_exists,
        "review_pack_blocking_errors": review_pack_errors,
        "latest_answer_search": answer_search,
        "tmux_visibility_kill_switch": readiness.tmux_visibility_kill_switch,
        "tmux_visibility_kill_switch_exists": readiness.tmux_visibility_kill_switch_exists,
        "tmux_completion_ping_kill_switch": readiness.tmux_completion_ping_kill_switch,
        "tmux_completion_ping_kill_switch_exists": readiness.tmux_completion_ping_kill_switch_exists,
        "current_stopline_pointer": str(CURRENT_STOPLINE_POINTER),
        "waiting_pointer": str(WAITING_POINTER),
        "latest_completion_audit": str(completion_audit) if completion_audit else None,
        "latest_current_objective_audit": str(current_objective_audit) if current_objective_audit else None,
        "latest_stopline_triage": str(stopline_triage) if stopline_triage else None,
        "latest_db_boundary_drift_triage": str(db_boundary_drift_triage) if db_boundary_drift_triage else None,
        "latest_db_boundary_supplemental_review_request": str(db_boundary_supplemental_review) if db_boundary_supplemental_review else None,
        "review_pack": review_pack,
        "next_steps": next_steps,
        "hard_stoplines": [
            "No production DB write.",
            "No workbook write.",
            "No scheduler or LaunchAgent mutation.",
            "No external-system writes.",
            "No owner approval request.",
            "No --visibility-pane LIVE for this rollout.",
            "No human-visible tmux visibility panes for this rollout.",
            "No orchestrator_ping_mode=chat for this rollout.",
            "No orchestrator_ping_mode=receiver for this rollout.",
            "No manual chat-pane pings by execution agents.",
            "Do not proceed if tmux kill-switch files are missing.",
        ],
    }


def run_readiness() -> ReadinessResult:
    return check_readiness(
        answer_dir=ANSWER_DIR,
        db_path=REPO_ROOT / "db" / "app.db",
        workbook_path=REPO_ROOT / "excel_ui" / "SALES_KSP_CRM_V3.xlsx",
        expected_db_sha256=DEFAULT_DB_SHA256,
        expected_workbook_sha256=DEFAULT_WORKBOOK_SHA256,
        proof_window_lock=REPO_ROOT / "config" / "proof_window.lock",
        handoff_root=HANDOFF_ROOT,
        orchestration_root=REPO_ROOT / "runs" / "tmux_orchestration",
        live_registry=LIVE_REGISTRY,
        tmux_visibility_kill_switch=REPO_ROOT / "config" / "tmux_orchestrator_visibility_disabled.flag",
        tmux_completion_ping_kill_switch=REPO_ROOT / "config" / "tmux_orchestrator_pings_disabled.flag",
        require_live_pane_check=False,
    )


def _parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Read-only Agent750 next-action reporter")
    p.add_argument("--json-only", action="store_true", help="Print only the next-action JSON")
    return p


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    readiness = run_readiness()
    payload = build_next_action(readiness)
    if not args.json_only:
        payload["readiness"] = asdict(readiness)
    print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if readiness.ok else 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
