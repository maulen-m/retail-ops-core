#!/usr/bin/env python3
"""Render a read-only Agent750 stopline checkpoint from live readiness evidence."""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.report_agent750_next_action import (
    CURRENT_GATE_STATUS_PATH,
    CURRENT_STOPLINE_POINTER,
    RUN_DOC_ROOT,
    WAITING_POINTER,
    build_next_action,
    run_readiness,
)


def _status_label(payload: dict) -> str:
    return str(payload.get("status") or "UNKNOWN")


def _scan_time(payload: dict) -> str:
    answer_search = payload.get("latest_answer_search")
    if isinstance(answer_search, dict):
        observed = answer_search.get("canonical_answer_scan_observed_at_local")
        if isinstance(observed, str) and observed:
            return observed
    return datetime.now().astimezone().strftime("%Y-%m-%dT%H:%M:%S%z")


def _scan_time_for_waiting_pointer(payload: dict) -> str:
    observed = _scan_time(payload)
    try:
        parsed = datetime.strptime(observed, "%Y-%m-%dT%H:%M:%S%z")
        return parsed.strftime("%Y-%m-%d %H:%M %z")
    except ValueError:
        return observed


def checkpoint_filename(payload: dict) -> str:
    observed = _scan_time(payload)
    try:
        parsed = datetime.strptime(observed, "%Y-%m-%dT%H:%M:%S%z")
        stamp = parsed.strftime("%Y%m%d_%H%M%S")
    except ValueError:
        stamp = datetime.now().astimezone().strftime("%Y%m%d_%H%M%S")
    return f"CURRENT_STOPLINE_CHECKPOINT_AGENT750_WAITING_{stamp}.md"


def run_checkpoint_path(payload: dict, run_doc_root: Path = RUN_DOC_ROOT) -> Path:
    return run_doc_root / checkpoint_filename(payload)


def _replace_required(pattern: str, replacement: str, text: str, *, label: str) -> str:
    updated, count = re.subn(pattern, replacement, text, count=1, flags=re.M)
    if count != 1:
        raise RuntimeError(f"unable_to_update_{label}")
    return updated


def refresh_current_surfaces(
    payload: dict,
    checkpoint_path: Path,
    *,
    status_path: Path = CURRENT_GATE_STATUS_PATH,
    current_stopline_path: Path = CURRENT_STOPLINE_POINTER,
    waiting_pointer_path: Path = WAITING_POINTER,
) -> list[Path]:
    """Refresh doc/status pointers after writing a generated checkpoint."""
    scan_time = _scan_time(payload)
    status = json.loads(status_path.read_text(encoding="utf-8"))
    if not isinstance(status, dict):
        raise RuntimeError("status_json_not_object")

    status["last_checked_local"] = scan_time
    status["status"] = _status_label(payload)
    status["local_action_state"] = payload.get("local_action_state")
    status["blocked_until"] = payload.get("blocked_until")
    status["current_blockers"] = list(payload.get("errors") or [])
    status["latest_stopline_checkpoint"] = str(checkpoint_path)

    current_boundary = status.setdefault("current_boundary", {})
    if isinstance(current_boundary, dict):
        if payload.get("db_sha256"):
            current_boundary["production_db_sha256"] = payload.get("db_sha256")
        if payload.get("workbook_sha256"):
            current_boundary["protected_workbook_sha256"] = payload.get("workbook_sha256")

    answer_search = payload.get("latest_answer_search")
    if isinstance(answer_search, dict):
        status_answer_search = status.setdefault("latest_answer_search", {})
        if isinstance(status_answer_search, dict):
            for key in (
                "status",
                "canonical_answer_folder",
                "canonical_answer_scan_observed_at_local",
                "canonical_answer_files",
                "canonical_answer_real_files",
                "canonical_answer_files_source",
                "canonical_answer_files_match_status",
                "searched_paths",
                "content_scan_terms",
                "non_authoritative_hits_summary",
                "launch_rule",
            ):
                if key in answer_search:
                    status_answer_search[key] = answer_search[key]

    status_path.write_text(
        json.dumps(status, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    current_text = current_stopline_path.read_text(encoding="utf-8")
    current_text = _replace_required(
        r"^Checked at: `[^`]+`$",
        f"Checked at: `{scan_time}`",
        current_text,
        label="current_stopline_checked_at",
    )
    current_text = _replace_required(
        r"^- Latest stopline checkpoint: `[^`]+`$",
        f"- Latest stopline checkpoint: `{checkpoint_path}`",
        current_text,
        label="current_stopline_checkpoint_pointer",
    )
    current_stopline_path.write_text(current_text, encoding="utf-8")

    waiting_text = waiting_pointer_path.read_text(encoding="utf-8")
    waiting_text = _replace_required(
        r"^Current .+ readiness remains blocked with:$",
        f"Current {_scan_time_for_waiting_pointer(payload)} readiness remains blocked with:",
        waiting_text,
        label="waiting_pointer_checked_at",
    )
    waiting_pointer_path.write_text(waiting_text, encoding="utf-8")

    return [status_path, current_stopline_path, waiting_pointer_path]


def render_checkpoint(payload: dict) -> str:
    status = _status_label(payload)
    answer_search = payload.get("latest_answer_search")
    if not isinstance(answer_search, dict):
        answer_search = {}
    review_pack = payload.get("review_pack")
    if not isinstance(review_pack, dict):
        review_pack = {}

    answer_files = payload.get("answer_files") or []
    current_answer_files = answer_search.get("canonical_answer_files") or []
    real_answer_files = answer_search.get("canonical_answer_real_files") or []
    errors = payload.get("errors") or []
    downstream_artifacts = payload.get("downstream_artifacts") or []
    misplaced_answer_files = payload.get("misplaced_answer_files") or []
    unexpected_answer_files = payload.get("unexpected_answer_files") or []
    scan_time = _scan_time(payload)

    def fmt_list(values: list[str]) -> str:
        return ", ".join(f"`{value}`" for value in values) if values else "none"

    def fmt_scalar(value: object) -> str:
        return "null" if value is None else str(value)

    readiness_status = "ok=true" if payload.get("readiness_ok") is True else "ok=false"
    answer_gate_clear = len(real_answer_files) == 1 and len(answer_files) == 1
    required_next_input = [
        "1. Resolve or explicitly review/re-anchor the current production DB/workbook boundary mismatches.",
        "2. Rerun `python3 scripts/check_agent750_launch_readiness.py` and require `ok=true` before selecting panes or launching.",
        "3. Only after readiness clears, use the existing guarded resume/launch path.",
    ]
    if not answer_gate_clear:
        required_next_input.insert(
            0,
            "1. Save or import exactly one real CodeCaptain Agent750 answer Markdown file into the canonical `Answer/` folder.",
        )
        required_next_input = [
            line.replace("1. Resolve", "2. Resolve")
            .replace("2. Rerun", "3. Rerun")
            .replace("3. Only", "4. Only")
            for line in required_next_input
        ]
    lines = [
        f"# Current Stopline Checkpoint - Agent750 Waiting - {scan_time}",
        "",
        f"Status: `{status}`",
        "",
        "## Objective Boundary",
        "",
        "The active objective is to complete the initial Option C validate-only plan successfully and reliably. The concrete launch deliverable is a guarded Agent751/752/753 validate-only wave, but only after all launch gates below are true at the same time.",
        "",
        "## Prompt-To-Artifact Checklist",
        "",
        "| Requirement | Evidence inspected | Current result | Status |",
        "| --- | --- | --- | --- |",
        "| Exactly one real external CodeCaptain Agent750 answer is present in the canonical `Answer/` folder | `latest_answer_search.canonical_answer_real_files`; readiness `answer_files` | "
        + f"Real answer files: {fmt_list(real_answer_files)}; readiness answer files: {fmt_list(answer_files)} | "
        + ("`PASS` |" if len(real_answer_files) == 1 and len(answer_files) == 1 else "`BLOCKED` |"),
        "| The answer contains the exact non-fenced GREEN launch token | readiness `decision_token` | "
        + f"`decision_token={fmt_scalar(payload.get('decision_token'))}` | "
        + ("`PASS` |" if payload.get("decision_token") == review_pack.get("allowed_green_token") else "`BLOCKED` |"),
        "| Current production DB boundary matches the reviewed Agent750 boundary or has been re-reviewed | readiness DB SHA comparison | "
        + f"Current DB SHA `{payload.get('db_sha256')}`; expected SHA `{payload.get('expected_db_sha256')}`; `db_sha256_matches_expected={str(payload.get('db_sha256_matches_expected')).lower()}` | "
        + ("`PASS` |" if payload.get("db_sha256_matches_expected") is True else "`BLOCKED` |"),
        "| Current protected workbook boundary matches the reviewed Agent750 boundary or has been re-reviewed | readiness workbook SHA comparison | "
        + f"Current workbook SHA `{payload.get('workbook_sha256')}`; expected SHA `{payload.get('expected_workbook_sha256')}`; `workbook_sha256_matches_expected={str(payload.get('workbook_sha256_matches_expected')).lower()}` | "
        + ("`PASS` |" if payload.get("workbook_sha256_matches_expected") is True else "`BLOCKED` |"),
        "| No premature Agent751/752/753 launch artifacts exist | readiness `downstream_artifacts` | "
        + f"Downstream artifacts: {fmt_list(downstream_artifacts)} | "
        + ("`PASS` |" if not downstream_artifacts else "`BLOCKED` |"),
        "| Tmux visibility and completion-ping kill switches remain active | readiness kill-switch fields | "
        + f"Visibility kill switch exists: `{str(payload.get('tmux_visibility_kill_switch_exists')).lower()}`; completion ping kill switch exists: `{str(payload.get('tmux_completion_ping_kill_switch_exists')).lower()}` | "
        + ("`PASS` |" if payload.get("tmux_visibility_kill_switch_exists") and payload.get("tmux_completion_ping_kill_switch_exists") else "`BLOCKED` |"),
        "| Review pack remains structurally valid and upload ZIP is byte-matched | review-pack validator manifest fields | "
        + f"Validator manifest ok: `{str(review_pack.get('latest_validator_manifest_ok')).lower()}`; optional ZIP SHA `{review_pack.get('optional_upload_zip_sha256')}`; source bytes match: `{str(review_pack.get('latest_validator_manifest_optional_upload_zip_source_bytes_match')).lower()}` | "
        + ("`PASS` |" if not payload.get("review_pack_blocking_errors") else "`BLOCKED` |"),
        "| Current readiness result is still fail-closed | readiness/report payload | "
        + f"`{readiness_status}` with errors {fmt_list(errors)} | "
        + ("`PASS` |" if payload.get("readiness_ok") is True else "`PASS_WITH_BLOCKERS` |"),
        "",
        "## Latest Live Evidence",
        "",
        f"- Canonical Answer folder: `{answer_search.get('canonical_answer_folder')}`",
        f"- Current Answer folder contents: {fmt_list(current_answer_files)}",
        f"- Live canonical Answer scan time: `{scan_time}`",
        f"- Readiness result: `{readiness_status}`",
        f"- Blocking errors: {fmt_list(errors)}",
        f"- Decision token: `{fmt_scalar(payload.get('decision_token'))}`",
        f"- Real answer files: {fmt_list(real_answer_files)}",
        f"- Misplaced answer files: {fmt_list(misplaced_answer_files)}",
        f"- Unexpected answer files: {fmt_list(unexpected_answer_files)}",
        f"- Downstream Agent751/752/753 artifacts: {fmt_list(downstream_artifacts)}",
        f"- Production DB SHA: `{payload.get('db_sha256')}`",
        f"- Expected reviewed DB SHA: `{payload.get('expected_db_sha256')}`",
        f"- Protected workbook SHA: `{payload.get('workbook_sha256')}`",
        f"- Expected reviewed workbook SHA: `{payload.get('expected_workbook_sha256')}`",
        f"- Proof-window lock exists: `{str(payload.get('proof_window_lock_exists')).lower()}`",
        "",
        "## Commands To Reproduce",
        "",
        "```bash",
        "find ~/Docs/Oracle/Autonomous_business/2026-05-09/224907_TASK-000_codecaptain-agent750-validate-only-plan-review/Answer -maxdepth 1 -type f -print",
        "python3 scripts/check_agent750_launch_readiness.py",
        "python3 scripts/report_agent750_next_action.py --json-only",
        "python3 scripts/build_agent750_stopline_checkpoint.py",
        "```",
        "",
        "## Required Next Input",
        "",
        *required_next_input,
        "",
        "## Still Not Authorized",
        "",
        "- no Agent751/752/753 launch;",
        "- no production DB write;",
        "- no workbook write;",
        "- no scheduler or LaunchAgent mutation;",
        "- no external-system write;",
        "- no owner approval request;",
        "- no `--visibility-pane LIVE`;",
        "- no `orchestrator_ping_mode=chat`;",
        "- no `orchestrator_ping_mode=receiver`;",
        "- no manual chat-pane pings by execution agents.",
        "",
    ]
    return "\n".join(lines)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Build a read-only Agent750 stopline checkpoint from current readiness evidence."
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=None,
        help="Optional output path. When omitted, checkpoint Markdown is printed to stdout.",
    )
    parser.add_argument(
        "--write-run-checkpoint",
        action="store_true",
        help="Write a timestamped checkpoint into the Agent750 run folder.",
    )
    parser.add_argument(
        "--refresh-current-surfaces",
        action="store_true",
        help="Write a timestamped checkpoint and refresh current Agent750 doc/status pointers.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if args.out and (args.write_run_checkpoint or args.refresh_current_surfaces):
        raise SystemExit("--out cannot be combined with run-folder write modes")
    if args.write_run_checkpoint and args.refresh_current_surfaces:
        raise SystemExit("--write-run-checkpoint and --refresh-current-surfaces are mutually exclusive")
    readiness = run_readiness()
    payload = build_next_action(readiness)
    text = render_checkpoint(payload)
    output_path = run_checkpoint_path(payload) if (
        args.write_run_checkpoint or args.refresh_current_surfaces
    ) else args.out
    if output_path:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(text, encoding="utf-8")
        if args.refresh_current_surfaces:
            refresh_current_surfaces(payload, output_path)
        print(output_path)
    else:
        print(text, end="")
    return 0 if readiness.ok else 2


if __name__ == "__main__":
    raise SystemExit(main())
